"""
对照 V5 检查 V6 保留范围、通行、屋面接头与网格闭合性。
审查使用实际求值网格和固定相机射线，报告与工程分开保存。
本脚本只读加载工程，不保存或更改交付模型。
"""
import bpy
import bmesh
import json
import math
import struct
import hashlib
from pathlib import Path
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"v06"/"qa"
P=json.loads((ROOT/"v06"/"design_parameters_v06.json").read_text(encoding="utf-8"))
candidate=bpy.data.filepath
BUILD=json.loads((OUT/"build_summary.json").read_text(encoding="utf-8"))


# 保留范围逐对象比较网格、变换、可见性、材质和修改器。
# 台面、桥面及踏步允许统一材质，因此另用不含材质的几何摘要检查。
def signature(ob,materials=True):
    digest=hashlib.sha256()
    for row in ob.matrix_world:
        digest.update(struct.pack("4d",*row))
    digest.update(str((ob.type,ob.hide_render,ob.hide_viewport)).encode())
    if ob.type=="MESH":
        for vertex in ob.data.vertices:
            digest.update(struct.pack("3d",*vertex.co))
        for face in ob.data.polygons:
            digest.update(struct.pack(f"{len(face.vertices)}I",*face.vertices))
            digest.update(str((face.use_smooth,face.material_index)).encode())
    if ob.type=="CURVE":
        digest.update(str((ob.data.bevel_depth,ob.data.bevel_resolution,ob.data.resolution_u)).encode())
        for spline in ob.data.splines:
            for point in spline.points:
                digest.update(struct.pack("4d",*point.co))
    if materials and ob.type in ("MESH","CURVE"):
        for mat in ob.data.materials:
            # 尺寸辅助对象允许空材质槽，空槽本身也纳入保留比较。
            # 不因为辅助标注缺材质而跳过整项几何或中断审查。
            if mat is None:
                digest.update(b"EMPTY_MATERIAL_SLOT")
                continue
            digest.update(str((mat.name,list(mat.diffuse_color))).encode())
            if mat.use_nodes:
                for node in mat.node_tree.nodes:
                    digest.update(node.bl_idname.encode())
                    for socket in node.inputs:
                        if hasattr(socket,"default_value"):
                            value=socket.default_value
                            digest.update(str(list(value) if hasattr(value,"__len__") and not isinstance(value,str) else value).encode())
    for mod in ob.modifiers:
        digest.update(str((mod.name,mod.type,mod.show_render,mod.show_viewport)).encode())
        for attr in ("width","segments","thickness","offset","levels","render_levels"):
            if hasattr(mod,attr):
                digest.update(str((attr,getattr(mod,attr))).encode())
    if ob.type=="LIGHT":
        digest.update(str((ob.data.type,ob.data.energy,list(ob.data.color),ob.data.angle if ob.data.type=="SUN" else ob.data.size)).encode())
    return digest.hexdigest()


def camera_record(ob):
    d=ob.data
    return {"matrix":[list(row) for row in ob.matrix_world],"lens":d.lens,"type":d.type,"ortho_scale":d.ortho_scale,
            "shift":[d.shift_x,d.shift_y],"sensor":[d.sensor_width,d.sensor_height,d.sensor_fit],"clip":[d.clip_start,d.clip_end]}


def world_record(scene):
    bg=scene.world.node_tree.nodes["Background"]
    return {"color":list(bg.inputs["Color"].default_value),"strength":bg.inputs["Strength"].default_value,
            "view":scene.view_settings.view_transform,"look":scene.view_settings.look,"exposure":scene.view_settings.exposure,
            "gamma":scene.view_settings.gamma,"resolution":[scene.render.resolution_x,scene.render.resolution_y]}


bpy.ops.wm.open_mainfile(filepath=str(ROOT/P["baseline_file"]))
source=bpy.context.scene
protected={ob.name:signature(ob) for col in source.collection.children if col.name.startswith(("01_","03_","04_","05A_","09_","10_","11_","13_","14_","15_")) for ob in col.all_objects}
fixed_cameras={ob.name:camera_record(ob) for ob in source.objects if ob.type=="CAMERA"}
markers={m.frame:m.camera.name for m in source.timeline_markers}
world=world_record(source)
floor_names={ob.name for ob in source.objects if ob.type=="MESH" and ("踏步高度_米" in ob or "地坪" in ob.name or "压顶板" in ob.name or ob.name.startswith("前庭侧边通行带_") or ob.name in
             ("前庭净空_220乘300米_标高0","前庭总承台_宽310米","月门前平台_标高0","广场中轴仪式通带_宽18米","前山入口休息平台","东侧桥_连续水平桥面","东侧观景台_标高12","前端入口_直口门墙"))}
floors={name:signature(source.objects[name],False) for name in floor_names if name!="东侧桥_连续水平桥面" and "压顶板" not in name}
shafts={ob.name:signature(ob,False) for ob in source.objects if ob.name.endswith("_柱身") and not (ob.name.startswith("侧回廊柱_") and abs(ob.location.y+151)<.01)}
bpy.ops.wm.open_mainfile(filepath=candidate)
scene=bpy.context.scene
scene.frame_set(4)
scene.camera=next(ob for ob in scene.objects if ob.name.startswith("CAM_04_"))
bpy.context.view_layer.update()
changed_protected=[n for n,d in protected.items() if n not in scene.objects or signature(scene.objects[n])!=d]
changed_floors=[n for n,d in floors.items() if n not in scene.objects or signature(scene.objects[n],False)!=d]
changed_shafts=[n for n,d in shafts.items() if n not in scene.objects or signature(scene.objects[n],False)!=d]
changed_cameras=[n for n,d in fixed_cameras.items() if n not in scene.objects or camera_record(scene.objects[n])!=d]
changed_markers=[frame for frame,name in markers.items() if not any(m.frame==frame and m.camera.name==name for m in scene.timeline_markers)]
deps=bpy.context.evaluated_depsgraph_get()


# 实际求值网格包含倒角与曲线厚度，射线不依赖物体包围盒。
# 人形参照不当作障碍；山体纳入通行检查，防止用隐藏岩体掩盖断路。
def tree_for(objects):
    verts,faces,owners=[],[],[]
    for original in objects:
        ob=original.evaluated_get(deps)
        data=ob.to_mesh()
        offset=len(verts)
        verts.extend(ob.matrix_world@v.co for v in data.vertices)
        for polygon in data.polygons:
            faces.append(tuple(offset+i for i in polygon.vertices))
            owners.append(original.name)
        ob.to_mesh_clear()
    return BVHTree.FromPolygons(verts,faces,all_triangles=False),owners


architecture={ob for col in scene.collection.children if col.name.startswith(("01_","02_","03_","04_","05_","05A_","06_","07_","08_")) for ob in col.all_objects if ob.type in ("MESH","CURVE") and not ob.hide_render}
tree,owners=tree_for(architecture)
walk_objects=[ob for ob in architecture if ob.name in floor_names and ob.name!="前端入口_直口门墙" or ob.name.startswith(("V06_入口至前庭同层接坪","V06_回廊地坪下补齐承托")) or "_连续石地栿" in ob.name]
ground_tree,ground_owners=tree_for(walk_objects)
print("V06_AUDIT_BVH_READY",len(architecture),flush=True)


def cast(start,end):
    start,end=Vector(start),Vector(end)
    delta=end-start
    hit,normal,index,distance=tree.ray_cast(start,delta.normalized(),delta.length)
    return {"object":owners[index],"hit":list(hit)} if hit is not None else None


# 原殿内机位到月门及门洞贯通同时检查，采样范围与 V5 一致。
# 中轴、入口、侧廊、三级辅助台阶与亭桥通路分别检查脚下连续性和头部净空。
moon_blocked=[]
moon_through=[]
moon_samples=0
cam=scene.camera
for i in range(-30,31):
    for j in range(-30,31):
        x,z=22*.96*i/30,56+22*.96*j/30
        if x*x+(z-56)**2>(22*.96)**2 or z<36.3:
            continue
        moon_samples+=1
        hit=cast(cam.location,(x,239.92,z))
        if hit:
            moon_blocked.append(hit)
        hit=cast((x,239,z),(x,247,z))
        if hit:
            moon_through.append(hit)
axis_blocked=[hit for x in (-8,-4,0,4,8) for z in (36.12,37.65,39) if (hit:=cast((x,235,z),(x,344,z)))]
entry_blocked=[hit for x in (-13.8,-8,0,8,13.8) for z in (.20,1.80,28.8) if (hit:=cast((x,-197,z),(x,-187,z)))]
routes=[]


def axis_height(y):
    for y0,y1,z0,z1 in [(-355,-303,-48,-24),(-285,-233,-24,0),(134,160,0,12),(171,197,12,24),(208,234,24,36)]:
        if y0<=y<=y1:
            return z0+(z1-z0)*(y-y0)/(y1-y0)
    return -24 if y<-285 else 0 if y<134 else 12 if y<171 else 24 if y<208 else 36


def check_route(name,points,expected):
    gaps,blocked,heights=[],[],[]
    for x,y in points:
        guess=expected(x,y)
        hit,normal,index,distance=ground_tree.ray_cast(Vector((x,y,guess+.55)),Vector((0,0,-1)),1.15)
        if hit is None:
            gaps.append([x,y,guess])
            continue
        heights.append(hit.z)
        obstruction=cast((x,y,hit.z+.28),(x,y,hit.z+2.10))
        if obstruction:
            blocked.append({"point":[x,y],**obstruction})
    maximum_step=max((abs(b-a) for a,b in zip(heights[:-1],heights[1:])),default=0)
    routes.append({"name":name,"samples":len(points),"ground_gaps":gaps,"headroom_obstructions":blocked,"maximum_sample_step":maximum_step,
                   "minimum_floor_z":min(heights) if heights else None,"maximum_floor_z":max(heights) if heights else None})


for x in (-8,0,8):
    points=[(x,-354.9+699.7*i/2799) for i in range(2800)]
    check_route(f"中轴全程_X{x}",points,lambda x,y:axis_height(y))
for sign in (-1,1):
    for dx in (-5.1,0,5.1):
        points=[(sign*130+dx,-175+310*i/620) for i in range(621)]
        check_route(f"侧廊_{sign}_横偏{dx}",points,lambda x,y:.1 if y>=-167 else 0)
    for i,(y0,y1,z0) in enumerate([(134,160,0),(171,197,12),(208,234,24)]):
        for dx in (-5,0,5):
            points=[(sign*(112-i*12)+dx,y0+.05+25.9*j/130) for j in range(131)]
            check_route(f"辅助阶_{sign}_{i}_{dx}",points,lambda x,y,y0=y0,z0=z0:z0+12*(y-y0)/26)
    check_route(f"后角亭转至侧阶_{sign}",[(sign*(130-18*i/72),132) for i in range(73)],lambda x,y:.1)
for dy in (-4,0,4):
    check_route(f"侧亭到桥面_{dy}",[(131+133*i/532,178+dy) for i in range(533)],lambda x,y:12)
for dy in (-5.97,5.97):
    check_route(f"十二米桥面边界_{dy}",[(151+112*i/448,178+dy) for i in range(449)],lambda x,y:12)
check_route("桥东端至观景亭",[(264+45*i/180,178) for i in range(181)]+[(309,178+18*i/72) for i in range(73)],lambda x,y:12)
footings=[]
for ob in scene.objects:
    if ob.name.startswith("V06_") and ("_础座" in ob.name or "_素面望柱_" in ob.name):
        bottom=min((ob.matrix_world@v.co).z for v in ob.data.vertices)
        x,y=ob.location.x,ob.location.y
        hit,normal,index,distance=ground_tree.ray_cast(Vector((x,y,bottom+.25)),Vector((0,0,-1)),.70)
        if hit is None or hit.z<bottom-.06:
            footings.append({"object":ob.name,"base_z":bottom,"floor_z":hit.z if hit else None})


# 每个新增网格只检查一次闭合性与退化面；共享构件不重复统计。
# 屋面实体两两检查真实三角面的相交，梁架逐顶点检查是否穿出屋面。
topology=[]
checked=set()
nonfinite=[]
for ob in scene.objects:
    if ob.type!="MESH" or not (ob.name.startswith("V06_") or "V06台阶口收口" in ob) or ob.data.as_pointer() in checked:
        continue
    checked.add(ob.data.as_pointer())
    bm=bmesh.new()
    bm.from_mesh(ob.data)
    bad=sum(not e.is_manifold for e in bm.edges)
    zero=sum(f.calc_area()<1e-9 for f in bm.faces)
    if bad or zero:
        topology.append({"name":ob.name,"nonmanifold_edges":bad,"zero_area_faces":zero})
    bm.free()
    if any(not math.isfinite(c) for v in ob.data.vertices for c in v.co):
        nonfinite.append(ob.name)
roof_trees={s["name"]:tree_for([scene.objects[s["object"]]])[0] for s in BUILD["roofs"]}
roof_overlaps=[]
for i,a in enumerate(BUILD["roofs"]):
    for b in BUILD["roofs"][i+1:]:
        overlaps=roof_trees[a["name"]].overlap(roof_trees[b["name"]])
        if overlaps:
            roof_overlaps.append({"a":a["name"],"b":b["name"],"face_intersections":len(overlaps)})


def height_at(s,x,y):
    x-=s["center"][0]
    y-=s["center"][1]
    if s["kind"]=="corridor":
        if abs(x)>s["width"]/2+.001 or abs(y)>s["depth"]/2+.001:
            return None
        u=min(1,abs(x)/(s["width"]/2))
        return s["eave"]-.14+(s["rise"]+.14)*(1-u)**1.7+.14*u**8
    ux=max(0,(abs(x)-s["ridge_length"]/2)/((s["width"]-s["ridge_length"])/2))
    uy=abs(y)/(s["depth"]/2)
    u=max(ux,uy)
    if u>1.0001:
        return None
    u=min(1,u)
    v=x/(s["ridge_length"]/2+(s["width"]-s["ridge_length"])/2*u) if uy>=ux else y/(s["depth"]/2*u)
    return s["eave"]-.2+(s["rise"]+.2)*(1-u)**1.7+.2*u**8+s["corner"]*abs(v)**4*u**3


intrusions=[]
for spec in BUILD["roofs"]:
    for ob in scene.objects:
        if ob.type!="MESH" or ob.get("建筑区域")!=spec["region"] or ob.get("构件类别")!="frame":
            continue
        maximum=0
        for v in ob.data.vertices:
            p=ob.matrix_world@v.co
            z=height_at(spec,p.x,p.y)
            if z is not None:
                maximum=max(maximum,p.z-z)
        if maximum>.015:
            intrusions.append({"object":ob.name,"roof":spec["name"],"protrusion_m":maximum})
shared=[{"name":data.name,"users":data.users} for data in bpy.data.meshes if data.users>1]
deck=scene.objects["东侧桥_连续水平桥面"]
deck_verts=[deck.matrix_world@v.co for v in deck.data.vertices]
deck_bounds=[[min(v[i] for v in deck_verts),max(v[i] for v in deck_verts)] for i in range(3)]
# 桥西端去除共面重叠属于授权的接头修正，单独核验实际尺寸。
# 十二米原宽、十二米顶高、东端位置与八十厘米收口量必须同时正确。
deck_expected=[[150.8,264.0],[172.0,184.0],[9.8,12.0]]
deck_preserved=all(abs(a-b)<.0001 for actual,expected in zip(deck_bounds,deck_expected) for a,b in zip(actual,expected))
cap_records=[]
for index,(width,front,back,top) in enumerate([(300,160,378,12),(272,197,372,24),(240,234,366,36)],1):
    cap=scene.objects[f"台基{index}_压顶板"]
    points=[cap.matrix_world@v.co for v in cap.data.vertices]
    bounds=[[min(v[i] for v in points),max(v[i] for v in points)] for i in range(3)]
    expected=[[-width/2-.8,width/2+.8],[front-.8,back+.8],[top-1.1,top]]
    correct=all(abs(a-b)<.0001 for actual,wanted in zip(bounds,expected) for a,b in zip(actual,wanted))
    cap_records.append({"name":cap.name,"bounds":bounds,"original_extent_and_level_preserved":correct})
report={"file":candidate,"baseline_sha256":hashlib.sha256((ROOT/P["baseline_file"]).read_bytes()).hexdigest(),
        "protected_objects_checked":len(protected),"changed_protected_objects":changed_protected,
        "retained_floors_and_entry_checked":len(floors),"changed_floors_or_entry":changed_floors,
        "retained_column_shafts_checked":len(shafts),"changed_column_shafts":changed_shafts,
        "changed_cameras":changed_cameras,"changed_markers":changed_markers,"world_and_color_management_unchanged":world_record(scene)==world,
        "bridge_deck_bounds":deck_bounds,"bridge_width_height_and_junction_preserved":deck_preserved,
        "terrace_cap_records":cap_records,
        "moon_sightline_samples":moon_samples,"moon_blocked":moon_blocked,"moon_through_blocked":moon_through,
        "axis_blocked":axis_blocked,"entry_clearance_blocked":entry_blocked,"routes":routes,"floating_column_bases":footings,
        "new_meshes_checked":len(checked),"topology_issues":topology,"nonfinite_meshes":nonfinite,
        "roof_shell_intersections":roof_overlaps,"roof_frame_intrusions":intrusions,"joints":BUILD["joints"],
        "objects":len(scene.objects),"mesh_instances":sum(ob.type=="MESH" for ob in scene.objects),"unique_meshes":sum(d.users>0 for d in bpy.data.meshes),
        "shared_mesh_count":len(shared),"shared_meshes":shared,"camera_records":{ob.name:camera_record(ob) for ob in scene.objects if ob.type=="CAMERA"}}
route_errors=sum(len(r["ground_gaps"])+len(r["headroom_obstructions"])+int(r["maximum_sample_step"]>.24) for r in routes)
report["route_sample_count"]=sum(r["samples"] for r in routes)
report["passed"]=not any([changed_protected,changed_floors,changed_shafts,changed_cameras,changed_markers,
                          not report["world_and_color_management_unchanged"],moon_blocked,moon_through,axis_blocked,entry_blocked,
                          route_errors,not deck_preserved,any(not r["original_extent_and_level_preserved"] for r in cap_records),footings,topology,nonfinite,roof_overlaps,intrusions])
(OUT/"audit_v06.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
compact={k:v for k,v in report.items() if k not in ("shared_meshes","camera_records","routes","joints")}
compact["route_errors"]=route_errors
compact["failed_routes"]=[{**r,"ground_gaps":r["ground_gaps"][:6],"headroom_obstructions":r["headroom_obstructions"][:6]} for r in routes if r["ground_gaps"] or r["headroom_obstructions"] or r["maximum_sample_step"]>.24]
print(json.dumps(compact,ensure_ascii=False),flush=True)
