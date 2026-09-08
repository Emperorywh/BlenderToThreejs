"""
对照 V4 实际几何和相机，检查 V5 范围、门口净空及结构网格。
仅以只读方式加载两个工程，将结果写入独立审查报告。
"""
import bpy
import bmesh
import json
import math
import hashlib
import struct
from pathlib import Path
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from bpy_extras.object_utils import world_to_camera_view

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"v05"/"qa"
candidate=bpy.data.filepath
P=json.loads((ROOT/"v05"/"design_parameters_v05.json").read_text(encoding="utf-8"))


# 摘要包含原始网格、曲线路径、世界变换、可见性及材质指向。
# 对相机单独记录投影参数，避免仅核对坐标却遗漏焦段或朝向变化。
def signature(ob):
    digest=hashlib.sha256()
    for row in ob.matrix_world:
        digest.update(struct.pack("4d",*row))
    digest.update(str((ob.type,ob.hide_render,ob.hide_viewport)).encode())
    if ob.type=="MESH":
        for vertex in ob.data.vertices:
            digest.update(struct.pack("3d",*vertex.co))
        for face in ob.data.polygons:
            digest.update(struct.pack(f"{len(face.vertices)}I",*face.vertices))
    if ob.type=="CURVE":
        digest.update(str((ob.data.bevel_depth,ob.data.bevel_resolution,ob.data.resolution_u)).encode())
        for spline in ob.data.splines:
            for point in spline.points:
                digest.update(struct.pack("4d",*point.co))
    if ob.type in ("MESH","CURVE"):
        for mat in ob.data.materials:
            digest.update(str((mat.name,list(mat.diffuse_color))).encode())
    if ob.type=="LIGHT":
        digest.update(str((ob.data.type,ob.data.energy,list(ob.data.color),ob.data.angle if ob.data.type=="SUN" else ob.data.size)).encode())
    return digest.hexdigest()


def camera_record(ob):
    data=ob.data
    return {"matrix":[list(row) for row in ob.matrix_world],"lens":data.lens,"type":data.type,
            "ortho_scale":data.ortho_scale,"shift":[data.shift_x,data.shift_y],
            "sensor":[data.sensor_width,data.sensor_height,data.sensor_fit],
            "clip":[data.clip_start,data.clip_end]}


bpy.ops.wm.open_mainfile(filepath=str(ROOT/P["baseline_file"]))
baseline_scene=bpy.context.scene
retained={ob.name:signature(ob) for col in baseline_scene.collection.children
          if not col.name.startswith(("00_","03_","04_","05A_","12_")) for ob in col.all_objects}
shafts={ob.name:signature(ob) for ob in baseline_scene.objects if ob.name.startswith("主殿巨柱_") and ob.name.endswith("_柱身")}
cameras={ob.name:camera_record(ob) for ob in baseline_scene.objects if ob.type=="CAMERA"}
markers={marker.frame:marker.camera.name for marker in baseline_scene.timeline_markers}
world_color=list(baseline_scene.world.node_tree.nodes["Background"].inputs["Color"].default_value)
world_strength=baseline_scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value
bpy.ops.wm.open_mainfile(filepath=candidate)
scene=bpy.context.scene
scene.frame_set(4)
cam=next(ob for ob in scene.objects if ob.name.startswith("CAM_04_"))
scene.camera=cam
bpy.context.view_layer.update()
changed_retained=[name for name,digest in retained.items() if name not in scene.objects or signature(scene.objects[name])!=digest]
changed_shafts=[name for name,digest in shafts.items() if name not in scene.objects or signature(scene.objects[name])!=digest]
changed_cameras=[name for name,record in cameras.items() if name not in scene.objects or camera_record(scene.objects[name])!=record]
changed_markers=[frame for frame,name in markers.items() if not any(m.frame==frame and m.camera.name==name for m in scene.timeline_markers)]


# 以求值后的真实网格构建射线查询树，包括本轮新增嵌套集合内的构件。
# 人形和远景云层不参与结构遮挡判断，但它们的原始几何已在保留摘要中比较。
verts,faces,owners=[],[],[]
deps=bpy.context.evaluated_depsgraph_get()
include=set()
for col in scene.collection.children:
    if col.name.startswith(("01_","02_","03_","04_","05_","05A_","06_","07_","08_")):
        include.update(ob for ob in col.all_objects if ob.type in ("MESH","CURVE"))
for original in include:
    ob=original.evaluated_get(deps)
    data=ob.to_mesh()
    offset=len(verts)
    verts.extend(ob.matrix_world@v.co for v in data.vertices)
    for polygon in data.polygons:
        faces.append(tuple(offset+i for i in polygon.vertices))
        owners.append(original.name)
    ob.to_mesh_clear()
tree=BVHTree.FromPolygons(verts,faces,all_triangles=False)
my=P["moon_plane_y"]
cz=P["moon_floor_z"]+P["moon_center_above_floor"]
r=P["moon_diameter"]/2
samples,blocked=0,[]
through_samples,through_blocked=0,[]
for i in range(-30,31):
    for j in range(-30,31):
        x,z=r*.96*i/30,cz+r*.96*j/30
        if x*x+(z-cz)**2>(r*.96)**2 or z<P["moon_floor_z"]+.3:
            continue
        target=Vector((x,my-P["moon_frame_max_depth"]/2-.05,z))
        direction=target-cam.location
        hit,normal,index,distance=tree.ray_cast(cam.location,direction.normalized(),direction.length-.03)
        samples+=1
        if hit is not None:
            blocked.append({"target":list(target),"object":owners[index],"position":list(hit)})
        start=Vector((x,my-4,z))
        hit,normal,index,distance=tree.ray_cast(start,Vector((0,1,0)),8)
        through_samples+=1
        if hit is not None:
            through_blocked.append({"target":list(start),"object":owners[index]})
axis_blocked=[]
for x in (-8,-4,0,4,8):
    for z in (36.12,37.65,39.0):
        hit,normal,index,distance=tree.ray_cast(Vector((x,235,z)),Vector((0,1,0)),109)
        if hit is not None:
            axis_blocked.append({"x":x,"z":z,"object":owners[index],"position":list(hit)})
start=math.asin(-P["moon_center_above_floor"]/r)
projected=[]
for i in range(257):
    angle=start+(math.pi-2*start)*i/256
    projected.append(world_to_camera_view(scene,cam,Vector((r*math.cos(angle),my,cz+r*math.sin(angle)))))


# 闭合性用于发现屋脊收束或布尔孔的拓扑问题，不把独立构件的正常搭接当作错误。
# 共享网格只检查一次，同时记录屋顶最大标高及重复模块的实际复用数量。
bad_meshes=[]
checked=set()
for ob in scene.objects:
    if ob.type!="MESH" or not ob.name.startswith("V05_") or ob.data.as_pointer() in checked:
        continue
    checked.add(ob.data.as_pointer())
    bm=bmesh.new()
    bm.from_mesh(ob.data)
    boundary=sum(not e.is_manifold for e in bm.edges)
    zero=sum(f.calc_area()<1e-8 for f in bm.faces)
    if boundary or zero:
        bad_meshes.append({"name":ob.name,"nonmanifold_edges":boundary,"zero_area_faces":zero})
    bm.free()
roof_col=next(c for c in scene.collection.children if c.name.startswith("04_"))
roof_top=max((ob.matrix_world@v.co).z for ob in roof_col.all_objects if ob.type=="MESH" for v in ob.data.vertices)
# 检查承托构件是否穿出上屋面，尤其是斜率较大的侧坡木斗和方檩端部。
# 使用集中参数的同一曲面公式逐顶点比较，结果包含具体对象便于修正。
def upper_surface_z(x,y):
    ux=max(0,(abs(x)-P["upper_ridge_length"]/2)/((P["upper_width"]-P["upper_ridge_length"])/2))
    uy=abs(y)/(P["upper_depth"]/2)
    u=max(ux,uy)
    if u>1:
        return None
    s=x/(P["upper_ridge_length"]/2+(P["upper_width"]-P["upper_ridge_length"])/2*u) if uy>=ux else y/(P["upper_depth"]/2*u)
    base=P["upper_eave_z"]-P["upper_toe_lift"]
    return base+(P["upper_ridge_z"]-base)*(1-u)**P["upper_curve_power"]+P["upper_toe_lift"]*u**8+P["upper_corner_lift"]*abs(s)**4*u**3
roof_intrusions=[]
support_col=next(c for c in roof_col.children if c.name.startswith("04A_"))
for ob in support_col.all_objects:
    if ob.type!="MESH":
        continue
    protrusions=[]
    for vertex in ob.data.vertices:
        p=ob.matrix_world@vertex.co
        top=upper_surface_z(p.x,p.y-P["hall_center_y"])
        if top is not None and p.z>top-.03:
            protrusions.append(p.z-top)
    if protrusions:
        roof_intrusions.append({"object":ob.name,"maximum_protrusion_m":max(protrusions),"vertices":len(protrusions)})
shared=[{"name":data.name,"users":data.users} for data in bpy.data.meshes if data.users>1 and any(ob.data==data and ob.name.startswith("V05_") for ob in scene.objects if ob.type=="MESH")]
report={"file":candidate,"baseline_sha256":hashlib.sha256((ROOT/P["baseline_file"]).read_bytes()).hexdigest(),
        "retained_objects_checked":len(retained),"changed_retained_objects":changed_retained,
        "column_shafts_checked":len(shafts),"changed_column_shafts":changed_shafts,
        "changed_original_cameras":changed_cameras,"changed_original_markers":changed_markers,
        "world_unchanged":world_color==list(scene.world.node_tree.nodes["Background"].inputs["Color"].default_value) and world_strength==scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value,
        "moon_opening_diameter_m":2*r,"moon_floor_z":P["moon_floor_z"],"moon_clear_height_m":cz+r-P["moon_floor_z"],
        "moon_floor_clear_width_m":2*math.sqrt(r*r-P["moon_center_above_floor"]**2),
        "sightline_samples":samples,"blocked_sightlines":blocked,"through_opening_samples":through_samples,"blocked_opening_samples":through_blocked,
        "axis_clearance_samples":15,"axis_blocked":axis_blocked,
        "moon_projected_bounds":{"x":[min(v.x for v in projected),max(v.x for v in projected)],"y":[min(v.y for v in projected),max(v.y for v in projected)]},
        "roof_top_z":roof_top,"hall_total_height_m":roof_top-P["hall_floor_z"],
        "new_meshes_checked":len(checked),"topology_issues":bad_meshes,"roof_support_intrusions":roof_intrusions,"shared_meshes":shared,
        "camera_records":{ob.name:camera_record(ob) for ob in scene.objects if ob.type=="CAMERA"}}
report["passed"]=not any([changed_retained,changed_shafts,changed_cameras,changed_markers,blocked,through_blocked,axis_blocked,bad_meshes,roof_intrusions])
(OUT/"audit_v05.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
compact={key:value for key,value in report.items() if key not in ("shared_meshes","camera_records","blocked_sightlines")}
compact["blocked_sightline_count"]=len(blocked)
print(json.dumps(compact,ensure_ascii=False),flush=True)
