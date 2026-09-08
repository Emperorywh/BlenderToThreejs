"""在冻结的 V02 工程上制作两开间建筑样板，不重建全场景。
复用既有几何工具与灰模材质；每次从冻结源读取，另存为样板版本。
"""
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
import bmesh
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import whitebox_geometry as G
from build_whitebox import backup_existing
from render_whitebox import fingerprint

TAG = "TIANGONG_PHASE2_SAMPLE"
CONTACTS = []


def digest_object(obj):
    """记录实际模型的几何、变换、可见性与材质，识别范围外的意外变化。
    用对象各自的摘要比较，避免仅凭数量相同判断冻结内容未变。
    """
    data = {"matrix": [list(row) for row in obj.matrix_world], "type": obj.type,
            "visibility": [obj.hide_render, obj.hide_viewport, obj.hide_get()]}
    if obj.type == 'MESH':
        data["vertices"] = [list(v.co) for v in obj.data.vertices]
        data["faces"] = [list(p.vertices) for p in obj.data.polygons]
    elif obj.type == 'CURVE':
        data["splines"] = [[list(p.co) + list(p.handle_left) + list(p.handle_right) + [p.radius]
                            for p in s.bezier_points] for s in obj.data.splines]
        data["bevel"] = obj.data.bevel_depth
    if obj.type in {'MESH', 'CURVE'}:
        data["materials"] = [(m.name, list(m.diffuse_color)) for m in obj.data.materials]
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def object_map(scene):
    """建立模型对象摘要表，照相机和灯光由渲染清单独立检查。
    基线里的全部模型都纳入表中，包括浮岛、桥梯和占位物。
    """
    return {o.name: digest_object(o) for o in scene.objects if o.type in {'MESH', 'CURVE'}}


def bbox(objects):
    """读取实际世界空间包围盒，核对样板没有扩大主殿外轮廓。
    仅用于冻结检查，不用包围盒估算屋面支承高度。
    """
    points = [o.matrix_world @ Vector(p) for o in objects for p in o.bound_box]
    return [[min(p[i] for p in points) for i in range(3)], [max(p[i] for p in points) for i in range(3)]]


def top_at(roof, x, y):
    """向保存工程中的真实屋面射线取高，支承构件随原曲面生成。
    不缩放或改变 V02 屋顶网格，射线未命中时明确停止。
    """
    hit, co, _, _ = roof.ray_cast(Vector((x, y, 1000)), Vector((0, 0, -1)), distance=2000)
    assert hit, (roof.name, x, y)
    return co.z


def box(name, center, size, group, material="stone"):
    """为样板构件增加统一前缀及用途，保持可分别编辑。
    中等尺度构件直接使用原有共享立方体，不生成装饰贴图。
    """
    obj = G.box("S03_" + name, center, size, group, material)
    obj["sample_component"] = group
    return obj


def sweep(name, path, width, height, group, axis, material="stone"):
    """沿实际曲面采样线生成矩形实体，用于檩、椽和封檐板。
    路径表示构件上缘，截面向下展开；所有端头封闭，不以细圆管替代梁木。
    """
    vertices = []
    for x, y, z in path:
        dx, dy = (width / 2, 0) if axis == "Y" else (0, width / 2)
        vertices.extend([(x-dx, y-dy, z), (x+dx, y+dy, z),
                         (x+dx, y+dy, z-height), (x-dx, y-dy, z-height)])
    faces = [(3, 2, 1, 0), tuple(4 * (len(path)-1) + i for i in range(4))]
    for j in range(len(path)-1):
        for i in range(4):
            faces.append((4*j+i, 4*j+(i+1)%4, 4*(j+1)+(i+1)%4, 4*(j+1)+i))
    obj = G.mesh_object("S03_" + name, vertices, faces, group, material)
    obj["sample_component"] = group
    return obj


def profile_arm(name, x, y_front, y_back, z_front, z_back, width=.58):
    """用收分的纵向梁截面表现出挑承托，不堆砌零散悬空横板。
    梁前端接挑檐檩，后端穿入柱头承托区，粗尺度斜肩表达传力方向。
    """
    length = y_back - y_front
    profile = [(y_front, z_front), (y_back, z_back), (y_back, z_back-.70),
               (y_front+length*.50, (z_front+z_back)/2-.60), (y_front, z_front-.26)]
    vertices = [(xx, yy, zz) for xx in (x-width/2, x+width/2) for yy, zz in profile]
    n = len(profile)
    faces = [tuple(reversed(range(n))), tuple(range(n, 2*n))]
    faces += [(i, (i+1)%n, (i+1)%n+n, i+n) for i in range(n)]
    return G.mesh_object("S03_"+name, vertices, faces, "Frame", "stone")


def prepare_collections(scene):
    """在样板工程中新增独立集合，保留 V02 原有集合和材质。
    复用工具的标签只影响新建对象，不重新标记既有全场景对象。
    """
    G.TAG = TAG
    G.SHARED.clear()
    G.COLLECTIONS.clear()
    G.MATERIALS.clear()
    root = bpy.data.collections.new("TG_S03_主殿右侧两开间样板")
    root["task_tag"] = TAG
    scene.collection.children.link(root)
    for key, label in (("Capital", "01_柱头与额枋"), ("Frame", "02_出挑梁架"),
                       ("Roof", "03_檩椽与封檐"), ("Wall", "04_后退门墙")):
        col = bpy.data.collections.new("S03_"+label)
        root.children.link(col)
        col["task_tag"] = TAG
        G.COLLECTIONS[key] = col
    for key in ("stone", "plaster", "trim", "roof"):
        G.MATERIALS[key] = bpy.data.materials["TG_"+key]


def build_capitals(scene, sample, base, changed, removed):
    """只调整选中六根柱的上端，为柱头、坐斗式块和连续额枋留出空间。
    柱轴、柱径、柱础和柱廊进深不变；上部结构仍在 V02 殿堂包络内。
    """
    floor = base["hall"]["center"][2]
    cap = sample["capital"]
    # 先筛选柱身列表，后续删除旧柱头不会使遍历中的对象引用失效。
    # 不把即将删除的附属构件放入本次遍历。
    for obj in [o for o in scene.objects if o.get("component_role") == "hall_column"]:
        x, y = obj.location.x, obj.location.y
        if x not in sample["column_axes_x"] or y not in sample["column_rows_y"]:
            continue
        changed.append(obj.name)
        obj.location.z = (sample["shaft_top_z"] + floor) / 2
        obj.scale.z = sample["shaft_top_z"] - floor
        obj["sample_edit"] = "只缩短上端柱身，补入承托柱头；柱轴和直径冻结"
        abacus = bpy.data.objects[obj.name+"_Abacus"]
        removed.append(abacus.name)
        bpy.data.objects.remove(abacus, do_unlink=True)
        key = "%g_%g" % (x, y)
        G.cylinder("S03_Collar_"+key, (x,y,45.73), cap["collar_radius"], cap["collar_height"], "Capital", "trim", 32)
        box("HeadSeat_"+key, (x,y,46.11), (cap["seat_width"],cap["seat_width"],cap["seat_height"]), "Capital")
        box("HeadAbacus_"+key, (x,y,46.40), (2.45,2.35,.22), "Capital", "trim")
        box("CrossArm_"+key, (x,y,46.66), (cap["arm_width"],.82,.44), "Capital")
        for dx in (-1.12, 1.12):
            box("BearingBlock_%s_%g"%(key,dx), (x+dx,y,46.99), (.56,.88,.30), "Capital", "trim")
        box("AlongArm_"+key, (x,y,46.89), (.70,3.6,.48), "Capital")
    for y in sample["column_rows_y"]:
        for i, (a,b) in enumerate(zip(sample["column_axes_x"], sample["column_axes_x"][1:])):
            box("TieBeam_%g_%d"%(y,i), ((a+b)/2,y,45.70), (b-a, .84,.66), "Capital")
            box("TieFillet_%g_%d"%(y,i), ((a+b)/2,y-.02,45.28), (b-a,.91,.18), "Capital", "trim")
            # 柱头两侧用无雕花的斜肩承托接入额枋，避免柱与横梁只是点接触。
            # 每个开间两端各一件，形体保持中等尺度，不复制密集斗拱。
            for x, sign in ((a,1),(b,-1)):
                outline = [(x+sign*.70,45.58),(x+sign*2.45,45.58),
                           (x+sign*2.0,45.12),(x+sign*.70,44.53)]
                vertices = [(xx,yy,zz) for yy in (y-.31,y+.31) for xx,zz in outline]
                faces = [(3,2,1,0),(4,5,6,7)] + [(j,(j+1)%4,(j+1)%4+4,j+4) for j in range(4)]
                G.mesh_object("S03_KneeShoulder_%g_%g_%d"%(x,y,sign),vertices,faces,"Capital","stone")
    for x in sample["column_axes_x"]:
        for name in ("Hall_Front_RadialBeam_%g"%x, "Hall_EaveCantilever_%g_-1"%x):
            removed.append(name)
            bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
        box("DeepTie_%g"%x, (x,156.5,46.28), (.64,8.3,.74), "Frame")


def build_roof_sample(scene, sample, base):
    """在三层原屋面的同一段下面补齐椽、檩、短柱和出挑梁。
    屋面本身及层数完全冻结，层次来自可识别的支承关系，而不是加厚整片屋顶。
    """
    rp = sample["roof"]
    xa, xb = sample["edge_x"]
    xs = [xa+(xb-xa)*i/24 for i in range(25)]
    count = math.ceil((xb-xa)/rp["rafter_spacing"])
    for tier, roof_spec in enumerate(base["hall"]["roof_layers"]):
        roof = bpy.data.objects["Hall_Roof_Tier_%d"%(tier+1)]
        edge = base["hall"]["center"][1] - roof_spec["depth"]/2
        thick = roof_spec["thickness"]
        bearings = sample["roof_bearings"][tier]
        rear = max(bearings[-1]+.8,rp["structural_back_y"])
        under = lambda x,y: top_at(roof,x,y)-thick
        for index in range(count+1):
            x = xa+(xb-xa)*index/count
            path = [(x,edge+.20+(rear-edge-.20)*j/30,
                     under(x,edge+.20+(rear-edge-.20)*j/30)+.025) for j in range(31)]
            rafter = sweep("T%d_Rafter_%02d"%(tier+1,index), path, rp["rafter_width"], rp["rafter_height"], "Roof", "Y")
            rafter["support_layer"] = "屋面下方连续椽子"
            CONTACTS.append({"type":"rafter_to_roof", "object":rafter.name, "roof":roof.name,
                             "probe":[x,bearings[1]], "top":under(x,bearings[1])+.025})
        # 封檐板包住结构边缘，下方保留椽头的节奏，不再只有一条圆管檐线。
        # 新构件全部放在旧檐口平面以内，不增加殿堂外轮廓。
        sweep("T%d_Fascia"%(tier+1), [(x,edge+.15,under(x,edge+.15)+.20) for x in xs],
              rp["fascia_depth"],rp["fascia_height"],"Roof","X","trim")
        sweep("T%d_DripApron"%(tier+1), [(x,edge+.17,under(x,edge+.17)-.22) for x in xs], .31,.15,"Roof","X")
        for row, y in enumerate(bearings):
            sweep("T%d_Purlin_%d"%(tier+1,row), [(x,y,under(x,y)-rp["rafter_height"]+.065) for x in xs],
                  rp["purlin_width"],rp["purlin_height"],"Roof","X")
        for x in sample["column_axes_x"]:
            first, mid, back = bearings
            bottom = lambda yy: under(x,yy)-rp["rafter_height"]+.065-rp["purlin_height"]
            # 同一柱轴上的纵向承托梁承担层间短柱，连续跨过前后柱排。
            # 梁顶接入檩椽层，梁底与柱头、短柱交叠连接，不以屋面薄壳单独承重。
            ys = [mid+(rp["structural_back_y"]-mid)*j/24 for j in range(25)]
            sweep("T%d_TransferBeam_%g"%(tier+1,x),[(x,yy,under(x,yy)-rp["rafter_height"]+.09) for yy in ys],
                  rp["transfer_beam_width"],rp["transfer_beam_height"],"Frame","Y")
            if tier == 0:
                profile_arm("T1_Outrigger_%g"%x,x,first-.12,153.8,bottom(first)+.11,47.03)
                for y, base_z in ((153,46.88),(160,47.02)):
                    target_y = mid if y == 153 else back
                    top = bottom(target_y)+.10
                    if top > base_z:
                        box("T1_PurlinSeat_%g_%g"%(x,y),(x,target_y,(base_z+top)/2),(.75,.78,top-base_z),"Frame")
                # 后檩下短柱落在纵向梁与内排柱头上，使前后两排柱共同参与承托。
                # 这里的短梁是中等尺度结构，不暗示已经完成真实工程受力校核。
                box("T1_BackCorbel_%g"%x,(x,160.25,47.08),(.92,1.3,.38),"Frame")
            else:
                lower = bpy.data.objects["Hall_Roof_Tier_%d"%tier]
                for row, y in enumerate((mid, back)):
                    foot = top_at(lower,x,y)-.12
                    head = bottom(y)+.09
                    assert head > foot+.2
                    box("T%d_ShortPost_%g_%d"%(tier+1,x,row),(x,y,(foot+head)/2),(.68,.70,head-foot),"Frame")
                    box("T%d_PostSole_%g_%d"%(tier+1,x,row),(x,y,foot+.12),(1.30,1.18,.30),"Frame","trim")
                    box("T%d_PostHead_%g_%d"%(tier+1,x,row),(x,y,head-.12),(2.1,1.2,.36),"Frame")
                    lower_spec = base["hall"]["roof_layers"][tier-1]
                    bearing_z = top_at(lower,x,y)-lower_spec["thickness"]-rp["rafter_height"]+.035
                    transfer_top = foot+.25
                    block = box("T%d_ThroughRoofSeat_%g_%d"%(tier+1,x,row),(x,y,(bearing_z+transfer_top)/2),
                                (.72,.74,transfer_top-bearing_z),"Frame")
                    CONTACTS.append({"type":"through_roof_transfer", "object":block.name,
                                     "beam":"S03_T%d_TransferBeam_%g"%(tier,x),"post":"S03_T%d_ShortPost_%g_%d"%(tier+1,x,row),
                                     "probe":[x,y]})
                profile_arm("T%d_Outrigger_%g"%(tier+1,x),x,first-.12,mid+.65,bottom(first)+.09,bottom(mid)+.11,.48)
            CONTACTS.append({"type":"outboard_support", "tier":tier+1, "probe":[x,first], "purlin_bottom":bottom(first)})


def wall_frame(name,x,z,w,h,y,depth,bar,material="stone"):
    """用少量框料组成矩形门框或墙面分区，不生成密集花格。
    所有框料的正面均不越过冻结的门墙前平面。
    """
    box(name+"_Left",(x-w/2+bar/2,y,z),(bar,depth,h),"Wall",material)
    box(name+"_Right",(x+w/2-bar/2,y,z),(bar,depth,h),"Wall",material)
    box(name+"_Top",(x,y,z+h/2-bar/2),(w,depth,bar),"Wall",material)
    box(name+"_Bottom",(x,y,z-h/2+bar/2),(w,depth,bar),"Wall",material)


def build_wall_sample(sample, changed, removed):
    """两开间分别形成简化双扇门和槛窗，墙体上部以梁枋及分区收束。
    月门原网格、门墙位置与中央通道保持不变，只替换范围内的占位门框。
    """
    plane = sample["wall_plane_front_y"]
    depth = sample["wall_frame_depth"]
    y = plane+depth/2
    for index, cx in enumerate(sample["wall_bays"]):
        baseline_index = 3+index
        for sign in (-1,1):
            name = "Hall_RecessFrame_%d_%d"%(baseline_index,sign)
            removed.append(name)
            bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
        sill = bpy.data.objects["Hall_Facade_Sill_%d"%baseline_index]
        if index == 0:
            changed.append(sill.name)
            sill.location.z, sill.scale.z = 28.11,.22
        floor = 28.22 if index == 0 else 29.2
        width = 6.45
        top = 42.6
        wall_frame("Bay%d_OuterJamb"%index,cx,(floor+top)/2,width,top-floor,y,depth,.34)
        box("Bay%d_TransomBeam"%index,(cx,y,38.45),(width,.48,.46),"Wall")
        box("Bay%d_LintelCap"%index,(cx,y,42.75),(7.46,.48,.36),"Wall","trim")
        # 门扇和槛窗只有大板、竖梃及上亮子，保留灰模结构阅读。
        # 简化板件退后于外框，实际厚度及阴影表达门墙层次。
        for leaf in (-1,1):
            xx = cx+leaf*1.44
            wall_frame("Bay%d_Leaf_%d"%(index,leaf),xx,(floor+38.2)/2,2.88,38.2-floor,163.03,.36,.20)
            panel_top = 37.87 if index == 0 else 33.55
            panel_bottom = floor+.20
            box("Bay%d_Panel_%d"%(index,leaf),(xx,163.19,(panel_bottom+panel_top)/2),(2.43,.15,panel_top-panel_bottom),"Wall","plaster")
            if index == 0:
                box("Door_%d_CrossRail"%leaf,(xx,162.96,33.65),(2.65,.36,.22),"Wall")
            else:
                box("Window_%d_MidRail"%leaf,(xx,163.01,35.8),(2.65,.32,.18),"Wall")
        for dx in (-1.05,1.05):
            box("Bay%d_TransomStile_%g"%(index,dx),(cx+dx,162.80,40.60),(.18,.32,3.55),"Wall")
        for level, z in enumerate((43.65,46.55)):
            box("Bay%d_WallBeam_%d"%(index,level),(cx,y,z),(7.5,.48,.30),"Wall")
        for panel in (-1,1):
            wall_frame("Bay%d_UpperPanel_%d"%(index,panel),cx+panel*1.7,45.06,3.10,2.13,162.48,.46,.14,"trim")


def main():
    """读取冻结源、局部构建、核验变更边界，并保存独立可编辑工程。
    输出前保留已有样板备份；V02 文件及配置从不覆盖。
    """
    config_text = (ROOT/"hall_sample_config.json").read_text(encoding="utf-8")
    config = json.loads(config_text)
    source = (ROOT/config["base_blend"]).resolve()
    output = (ROOT/config["output_blend"]).resolve()
    assert source.is_relative_to(ROOT) and output.is_relative_to(ROOT) and source != output
    assert hashlib.sha256(source.read_bytes()).hexdigest() == config["base_blend_sha256"]
    assert hashlib.sha256((ROOT/config["base_config"]).read_bytes()).hexdigest() == config["base_config_sha256"]
    bpy.ops.wm.open_mainfile(filepath=str(source))
    scene = bpy.data.scenes["Tiangong_Whitebox"]
    bpy.context.window.scene = scene
    bpy.context.view_layer.update()
    base = json.loads(scene["scene_config_json"])
    before = object_map(scene)
    other = {s.name:fingerprint(s) for s in bpy.data.scenes if s != scene}
    hall_before = bbox([o for o in scene.objects if o.name.startswith("Hall_")])
    changed, removed = [], []
    prepare_collections(scene)
    build_capitals(scene,config["sample"],base,changed,removed)
    bpy.context.view_layer.update()
    build_roof_sample(scene,config["sample"],base)
    build_wall_sample(config["sample"],changed,removed)
    bpy.context.view_layer.update()
    after = object_map(scene)
    actual_changed = [name for name,value in before.items() if name in after and after[name] != value]
    actual_removed = [name for name in before if name not in after]
    assert set(actual_changed) == set(changed)
    assert set(actual_removed) == set(removed)
    hall_after = bbox([o for o in scene.objects if o.name.startswith(("Hall_","S03_"))])
    assert all(abs(hall_before[i][j]-hall_after[i][j]) < .001 for i in range(2) for j in range(3)), (hall_before,hall_after)
    mesh_issues = []
    for obj in scene.objects:
        if obj.type != 'MESH' or obj.get("task_tag") != TAG:
            continue
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        if any(not e.is_manifold for e in bm.edges) or any(f.calc_area()<1e-8 for f in bm.faces) or bm.calc_volume(signed=True)<=0:
            mesh_issues.append(obj.name)
        bm.free()
    assert not mesh_issues, mesh_issues
    from render_hall_sample import apply_cameras
    apply_cameras(scene,config)
    scene["phase"] = "PHASE2_MAIN_HALL_SAMPLE_REVIEW_ONLY"
    scene["sample_config_json"] = config_text
    scene["sample_config_sha256"] = hashlib.sha256(config_text.encode()).hexdigest()
    scene["sample_revision"] = config["revision"]
    scene["sample_scope"] = config["scope"]
    scene["sample_baseline_sha256"] = config["base_blend_sha256"]
    assert other == {s.name:fingerprint(s) for s in bpy.data.scenes if s != scene}
    report = {"revision":config["revision"],"source_sha256":config["base_blend_sha256"],
              "modified_baseline_objects":changed,"removed_baseline_objects":removed,
              "new_sample_objects":sorted(set(after)-set(before)),"baseline_models":before,
              "sample_models":after,"frozen_hall_bounds":hall_before,"current_hall_bounds":hall_after,
              "checks":{"outside_sample_unchanged":True,"hall_outer_dimensions_frozen":True,
                        "all_three_original_roofs_unchanged":all(before[n]==after[n] for n in before if n.startswith("Hall_Roof_")),
                        "moon_gate_unchanged":all(before[n]==after[n] for n in before if n.startswith("Hall_MainMoon")),
                        "closed_positive_sample_meshes":not mesh_issues,"other_scenes_unchanged":True},
              "connection_probes":CONTACTS,"scene_model_fingerprint":fingerprint(scene,geometry_only=True)}
    backup_existing(output)
    bpy.ops.wm.save_as_mainfile(filepath=str(output),compress=True)
    report["output_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    (ROOT/"output/sample_v03_build_report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("SAMPLE_BUILD_COMPLETE "+json.dumps({"checks":report["checks"],"changed":len(changed),"removed":len(removed),"added":len(report["new_sample_objects"])},ensure_ascii=False),flush=True)


if __name__ == "__main__":
    main()
