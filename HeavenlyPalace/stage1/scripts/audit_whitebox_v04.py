"""
核对白模 v04 的同层月门视线、固定机位、真实尺度与保留几何。
检查射线是否在到达圆门之前遇到建筑，避免仅凭相机截图判断遮挡。
"""
import bpy
import json
import math
import hashlib
import struct
from pathlib import Path
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from bpy_extras.object_utils import world_to_camera_view


# 比较的是实际顶点、面索引和世界变换，材质色阶变化不算几何修改。
# 原版仅以只读方式打开，检查结束重新打开待检查工程，不写回源文件。
ROOT=Path(__file__).resolve().parents[1]
candidate=bpy.data.filepath
def geometry_signatures():
    records={}
    scene=bpy.context.scene
    prefixes=("02_","06_","07_","08_","11_")
    for col in scene.collection.children:
        if not col.name.startswith(prefixes):
            continue
        for ob in col.objects:
            if ob.type!="MESH":
                continue
            digest=hashlib.sha256()
            for row in ob.matrix_world:
                digest.update(struct.pack("4d",*row))
            for vertex in ob.data.vertices:
                digest.update(struct.pack("3d",*vertex.co))
            for face in ob.data.polygons:
                digest.update(struct.pack(f"{len(face.vertices)}I",*face.vertices))
            records[ob.name]=digest.hexdigest()
    return records


new_records=geometry_signatures()
bpy.ops.wm.open_mainfile(filepath=str(ROOT/"HeavenlyPalace_Whitebox_v03.blend"))
old_records=geometry_signatures()
bpy.ops.wm.open_mainfile(filepath=candidate)
scene=bpy.context.scene
params=json.loads(bpy.data.texts["03_v04设计参数.json"].as_string())
deps=bpy.context.evaluated_depsgraph_get()
cam=next(ob for ob in scene.objects if ob.type=="CAMERA" and ob.name.startswith("CAM_04_"))
scene.frame_set(4)
scene.camera=cam
bpy.context.view_layer.update()


# 将建筑和山体合为只读查询树；人形、植物和远景云海不当作结构遮挡。
# 圆门测试点向内缩，排除素面边框本身造成的边界误判。
verts,faces,owners=[],[],[]
included=("01_","02_","03_","04_","05_","05A_","06_","07_","08_")
for col in scene.collection.children:
    if not col.name.startswith(included):
        continue
    for original in col.objects:
        if original.type!="MESH":
            continue
        ob=original.evaluated_get(deps)
        data=ob.to_mesh()
        offset=len(verts)
        verts.extend(ob.matrix_world@vertex.co for vertex in data.vertices)
        for polygon in data.polygons:
            faces.append(tuple(offset+i for i in polygon.vertices))
            owners.append(original.name)
        ob.to_mesh_clear()
tree=BVHTree.FromPolygons(verts,faces,all_triangles=False)
r=params["moon_diameter"]/2
cz=params["moon_floor_z"]+params["moon_center_above_floor"]
my=params["moon_plane_y"]
tests,blocked=0,[]
for i in range(-20,21):
    for j in range(-20,21):
        x=r*.95*i/20
        z=cz+r*.95*j/20
        if x*x+(z-cz)**2>(r*.95)**2 or z<params["moon_floor_z"]+.6:
            continue
        target=Vector((x,my-params["moon_wall_thickness"]/2-.1,z))
        direction=target-cam.location
        hit,normal,index,distance=tree.ray_cast(cam.location,direction.normalized(),direction.length-.05)
        tests+=1
        if hit is not None:
            blocked.append({"target":list(target),"hit":owners[index],"position":list(hit)})
projected=[]
start=math.asin(-params["moon_center_above_floor"]/r)
for i in range(161):
    theta=start+(math.pi-2*start)*i/160
    p=world_to_camera_view(scene,cam,Vector((r*math.cos(theta),my,cz+r*math.sin(theta))))
    projected.append(list(p))
floor_hit,normal,index,distance=tree.ray_cast(cam.location,Vector((0,0,-1)),10)
floor_z=floor_hit.z if floor_hit is not None else None


# 同时抽查主中轴通路；向下射线分别读取台面与山体，防止把岩面误当成通路。
# 这里只验证这一轮需要保留的通行关系，不替代后续结构设计。
def top_surface(objects,x,y):
    hits=[]
    for original in objects:
        ob=original.evaluated_get(deps)
        inv=ob.matrix_world.inverted()
        hit,loc,normal,face=ob.ray_cast(inv@Vector((x,y,300)),(inv.to_3x3()@Vector((0,0,-1))).normalized())
        if hit:
            hits.append((ob.matrix_world@loc).z)
    return max(hits,default=None)


floors=[ob for col in scene.collection.children if col.name.startswith(("02_","07_")) for ob in col.objects if ob.type=="MESH"]
rocks=[ob for col in scene.collection.children if col.name.startswith("01_") for ob in col.objects if ob.type=="MESH"]
missing,intrusions=[],[]
for i in range(395):
    y=-354.87+1.5*i
    fz=top_surface(floors,.031,y)
    rz=top_surface(rocks,.031,y)
    if fz is None:
        missing.append(y)
    elif rz is not None and rz>fz+.025:
        intrusions.append({"y":y,"floor_z":fz,"rock_z":rz})
peak_verts=[ob.matrix_world@vertex.co for ob in rocks for vertex in ob.data.vertices]
report={"file":candidate,"unit_system":scene.unit_settings.system,"meters_per_unit":scene.unit_settings.scale_length,
        "eye_height_measured_m":cam.location.z-floor_z if floor_z is not None else None,
        "camera_lens_mm":cam.data.lens,"moon_top_z":cz+r,"moon_floor_z":params["moon_floor_z"],
        "moon_clear_height_m":cz+r-params["moon_floor_z"],"sightline_samples":tests,"blocked_samples":blocked,
        "projected_opening_bounds":{"x":[min(p[0] for p in projected),max(p[0] for p in projected)],
                                    "y":[min(p[1] for p in projected),max(p[1] for p in projected)]},
        "mountain_max_z":max(v.z for v in peak_verts),
        "retained_mesh_count":len(new_records),
        "changed_retained_meshes":[name for name,digest in old_records.items() if new_records.get(name)!=digest],
        "axis_missing_floor":missing,"axis_rock_intrusions":intrusions,
        "cameras":[{"frame":m.frame,"name":m.camera.name,"position":list(m.camera.location),"lens_mm":m.camera.data.lens} for m in scene.timeline_markers]}
(ROOT/"v04"/"qa"/"audit_v04.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(report,ensure_ascii=False),flush=True)
