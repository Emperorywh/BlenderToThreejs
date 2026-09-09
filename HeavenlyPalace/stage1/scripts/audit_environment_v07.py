"""
对照 V6 逐对象核验建筑保留，检查 V7 环境支撑、通路和月门视线。
使用真实求值网格与射线，不通过隐藏物体或修改相机让审查通过。
只读加载工程并写审查记录，不改动 V6 或待交付的 V7 文件。
"""
import bpy
import ast
import bmesh
import json
import math
import struct
import hashlib
from pathlib import Path
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"v07"/"qa"
P=json.loads((ROOT/"v07"/"design_parameters_v07.json").read_text(encoding="utf-8"))
BUILD=json.loads((OUT/"build_summary.json").read_text(encoding="utf-8"))
candidate=bpy.data.filepath

# 复用已验收阶段的只读摘要与通路采样方法，避免改变评判基准。
# 这里只执行函数定义；不会执行 V6 建模或保存逻辑。
old_tree=ast.parse((ROOT/"scripts"/"audit_architecture_v06.py").read_text(encoding="utf-8"))
definitions=[n for n in old_tree.body if isinstance(n,ast.FunctionDef) and n.name in
             ("signature","camera_record","world_record","tree_for","cast","axis_height","check_route")]
exec(compile(ast.Module(body=definitions,type_ignores=[]),"沿用验收审查函数","exec"),globals())
bpy.ops.wm.open_mainfile(filepath=str(ROOT/P["baseline_file"]))
source=bpy.context.scene
protected={o.name:signature(o) for c in source.collection.children if not c.name.startswith(("00_","01_","09_","10_","12_","15_")) for o in c.all_objects}
cameras={o.name:camera_record(o) for o in source.objects if o.type=="CAMERA"}
markers={m.frame:m.camera.name for m in source.timeline_markers}
world=world_record(source)
floor_names={o.name for o in source.objects if o.type=="MESH" and ("踏步高度_米" in o or "地坪" in o.name or "压顶板" in o.name or o.name.startswith("前庭侧边通行带_") or o.name in
    ("前庭净空_220乘300米_标高0","前庭总承台_宽310米","月门前平台_标高0","广场中轴仪式通带_宽18米","前山入口休息平台","东侧桥_连续水平桥面","东侧观景台_标高12"))}
bpy.ops.wm.open_mainfile(filepath=candidate)
scene=bpy.context.scene
scene.frame_set(4)
bpy.context.view_layer.update()
deps=bpy.context.evaluated_depsgraph_get()
changed=[n for n,d in protected.items() if n not in scene.objects or signature(scene.objects[n])!=d]
changed_cameras=[n for n,d in cameras.items() if n not in scene.objects or camera_record(scene.objects[n])!=d]
changed_markers=[f for f,n in markers.items() if not any(m.frame==f and m.camera.name==n for m in scene.timeline_markers)]
architecture={o for c in scene.collection.children if c.name.startswith(("02_","03_","04_","05_","05A_","06_","07_","08_")) for o in c.all_objects if o.type in ("MESH","CURVE") and not o.hide_render}
environment={o for c in scene.collection.children if c.name.startswith(("01_","09_","10_")) for o in c.all_objects if o.type=="MESH" and not o.hide_render}
rocks={o for c in scene.collection.children if c.name.startswith("01_") for o in c.all_objects if o.type=="MESH"}
tree,owners=tree_for(architecture|environment)
ground_objects=[o for o in architecture if o.name in floor_names or o.name.startswith(("V06_入口至前庭同层接坪","V06_回廊地坪下补齐承托")) or "_连续石地栿" in o.name]
ground_tree,ground_owners=tree_for(ground_objects)
rock_bvh,rock_owners=tree_for(rocks)
pine_objects={o for c in scene.collection.children if c.name.startswith("09_") for o in c.all_objects if o.type=="MESH"}
architecture_bvh,architecture_owners=tree_for(architecture)
pine_bvh,pine_owners=tree_for(pine_objects)
pine_architecture_contacts=sorted(set((architecture_owners[a],pine_owners[b]) for a,b in architecture_bvh.overlap(pine_bvh)))
print("V07_AUDIT_BVH_READY",flush=True)


# 月门检查覆盖殿内至门洞的视线与门圈贯通，参数沿用 V6。
# 通路同时纳入新岩石、根盘、枝叶与水体，禁止环境侵入已经验收的净空。
moon_blocked=[]
moon_through=[]
moon_samples=0
cam=scene.objects[next(n for n in cameras if n.startswith("CAM_04_"))]
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
routes=[]
for x in (-8,0,8):
    check_route(f"中轴全程_X{x}",[(x,-354.9+699.7*i/2799) for i in range(2800)],lambda x,y:axis_height(y))
for sign in (-1,1):
    for dx in (-5.1,0,5.1):
        check_route(f"侧廊_{sign}_{dx}",[(sign*130+dx,-175+310*i/620) for i in range(621)],lambda x,y:.1 if y>=-167 else 0)
    for i,(y0,y1,z0) in enumerate([(134,160,0),(171,197,12),(208,234,24)]):
        for dx in (-5,0,5):
            check_route(f"辅助阶_{sign}_{i}_{dx}",[(sign*(112-i*12)+dx,y0+.05+25.9*j/130) for j in range(131)],lambda x,y,y0=y0,z0=z0:z0+12*(y-y0)/26)
    check_route(f"后角亭转至侧阶_{sign}",[(sign*(130-18*i/72),132) for i in range(73)],lambda x,y:.1)
for dy in (-4,0,4):
    check_route(f"侧亭到桥面_{dy}",[(131+133*i/532,178+dy) for i in range(533)],lambda x,y:12)
for dy in (-5.97,5.97):
    check_route(f"十二米桥面边界_{dy}",[(151+112*i/448,178+dy) for i in range(449)],lambda x,y:12)
check_route("桥东端至观景亭",[(264+45*i/180,178) for i in range(181)]+[(309,178+18*i/72) for i in range(73)],lambda x,y:12)


# 各个岩体独立判断点是否在实体内，允许基础必要的嵌入。
# 不用合并表面的奇偶计数处理相互搭接的岩块，避免把重叠支撑误判为空洞。
rock_parts=[]
for ob in rocks:
    vv=[ob.matrix_world@v.co for v in ob.data.vertices]
    ff=[tuple(p.vertices) for p in ob.data.polygons]
    if not vv:
        continue
    lo=[min(p[i] for p in vv) for i in range(3)]
    hi=[max(p[i] for p in vv) for i in range(3)]
    rock_parts.append((ob.name,BVHTree.FromPolygons(vv,ff),lo,hi))


def inside_rock(p):
    p=Vector(p)
    direction=Vector((.00231,.00379,1)).normalized()
    for name,bvh,lo,hi in rock_parts:
        if not all(lo[i]-.002<=p[i]<=hi[i]+.002 for i in range(3)):
            continue
        start=p.copy()
        crossings=0
        for k in range(30):
            hit,n,index,distance=bvh.ray_cast(start,direction,3000)
            if hit is None:
                break
            crossings+=1
            start=hit+direction*.003
        if crossings%2:
            return name
    return None


supports=[]
support_failures=[]
for name,x0,x1,y0,y1,z,nx,ny in [("前庭承台",-154.7,154.7,-232.7,172.7,-10.04,31,42),
    ("一级台基",-149.7,149.7,160.3,377.7,-6.04,31,23),
    ("观景平台",264.3,335.7,141.3,214.7,8.96,15,16),
    ("桥西台",144.2,155.8,170.2,185.8,-40.04,6,7),("桥东台",258.2,269.8,170.2,185.8,-40.04,6,7),
    ("登山下段",-23.8,23.8,-354.8,-303.2,-48.74,9,22),
    ("登山休息平台",-27.8,27.8,-302.8,-285.2,-28.04,11,9),
    ("登山上段",-23.8,23.8,-284.8,-233.2,-24.74,9,22)]:
    count=0
    failures=[]
    for i in range(nx):
        for j in range(ny):
            point=(x0+(x1-x0)*i/(nx-1),y0+(y1-y0)*j/(ny-1),z)
            count+=1
            if inside_rock(point) is None:
                failures.append(list(point))
    supports.append({"name":name,"samples":count,"unsupported":failures})
    support_failures.extend({"name":name,"point":p} for p in failures)
gap_failures=[]
gap_samples=0
for x in range(169,252,6):
    for y in (166,178,190):
        for z in range(-210,-9,20):
            gap_samples+=1
            owner=inside_rock((x,y,z))
            if owner:
                gap_failures.append({"point":[x,y,z],"object":owner})
root_failures=[]
for record in BUILD["pines"]:
    x,y,z=record["root"]
    hit,n,i,d=rock_bvh.ray_cast(Vector((x,y,z+1)),Vector((0,0,-1)),3)
    if hit is None or abs(hit.z-z)>.06:
        root_failures.append({"tree":record["label"],"root":[x,y,z],"hit":list(hit) if hit else None})
    for root in record["root_tips"]:
        x,y,z=root["tip"]
        hit,n,i,d=rock_bvh.ray_cast(Vector((x,y,z+1)),Vector((0,0,-1)),3)
        if hit is None or abs(hit.z-z)>.35:
            root_failures.append({"tree":record["label"],"tip":[x,y,z],"hit":list(hit) if hit else None})


# 只把自由落水段纳入穿岩检查；出水潭与跌水潭本来就要贴近岩唇。
# 每段横向与纵向均取样，避免只测中心线而漏掉水幕边缘穿岩。
water_failures=[]
water_samples=0
for record in BUILD["waterfalls"]:
    path=record["path"]
    for section in record["sections"]:
        for j in range(section["start"],section["end"]):
            a,b=Vector(path[j]),Vector(path[j+1])
            for t in (.15,.5,.85):
                center=a.lerp(b,t)
                for side in (-.49,0,.49):
                    p=center+Vector((record["width"]*side,-.1,0))
                    water_samples+=1
                    owner=inside_rock(p)
                    if owner:
                        water_failures.append({"waterfall":record["label"],"point":list(p),"rock":owner})
unique={o.data for o in environment}
camera_inside_rock=[o.name for o in scene.objects if o.type=="CAMERA" and inside_rock(o.location)]
topology=[]
for data in unique:
    bm=bmesh.new()
    bm.from_mesh(data)
    loose=sum(not e.is_manifold for e in bm.edges)
    degenerate=sum(f.calc_area()<1e-10 for f in bm.faces)
    if loose or degenerate:
        topology.append({"mesh":data.name,"non_manifold_edges":loose,"degenerate_faces":degenerate})
    bm.free()
route_errors=sum(len(r["ground_gaps"])+len(r["headroom_obstructions"])+int(r["maximum_sample_step"]>.24) for r in routes)
report={"file":candidate,"baseline_sha256":P["baseline_sha256"],"objects":len(scene.objects),"protected_objects":len(protected),
        "changed_architecture":changed,"preserved_cameras":len(cameras),"changed_cameras":changed_cameras,"changed_markers":changed_markers,
        "lighting_and_world_unchanged":world_record(scene)==world,"moon_samples":moon_samples,"moon_blocked":moon_blocked,"moon_through":moon_through,
        "route_sample_count":sum(r["samples"] for r in routes),"route_errors":route_errors,"routes":routes,
        "supports":supports,"support_sample_count":sum(r["samples"] for r in supports),"support_failures":support_failures,
        "bridge_gap_samples":gap_samples,"bridge_gap_failures":gap_failures,"root_failures":root_failures,
        "pine_architecture_intersections":pine_architecture_contacts,
        "cameras_inside_rock":camera_inside_rock,
        "freefall_samples":water_samples,"water_rock_intrusions":water_failures,"topology_errors":topology,
        "environment_unique_meshes":len(unique),"environment_unique_vertices":sum(len(d.vertices) for d in unique),
        "shared_meshes":len([d for d in unique if d.users>1])}
report["passed"]=not any((changed,changed_cameras,changed_markers,not report["lighting_and_world_unchanged"],moon_blocked,moon_through,
    route_errors,support_failures,gap_failures,root_failures,pine_architecture_contacts,water_failures,topology,camera_inside_rock))
(OUT/"audit_v07.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({k:v for k,v in report.items() if k not in ("routes","supports")},ensure_ascii=False),flush=True)
if not report["passed"]:
    raise RuntimeError("V7 几何自查未通过，请修正审查记录中的实际问题。")
