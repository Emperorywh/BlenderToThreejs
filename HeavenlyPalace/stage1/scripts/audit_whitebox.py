"""
检查白模工程的米制尺度、固定机位与中轴通行连续性。
通过真实网格射线核对台阶、台面和山体遮挡，不依据截图猜测尺寸。
"""
import bpy
import json
from pathlib import Path
from mathutils import Vector


# 只在当前天宫场景读取数据，不修改几何与相机。
# 参数文本用于核对设计尺寸，包围盒记录实际生成范围。
scene=bpy.context.scene
root=Path(bpy.data.filepath).parent
params=json.loads(bpy.data.texts["01_设计参数.json"].as_string())
deps=bpy.context.evaluated_depsgraph_get()
cols={col.name[:2]:col for col in scene.collection.children}
def bounds(objects):
    verts=[ob.matrix_world@Vector(corner) for ob in objects if ob.type=="MESH" for corner in ob.bound_box]
    lo=[min(v[i] for v in verts) for i in range(3)]
    hi=[max(v[i] for v in verts) for i in range(3)]
    return {"min":lo,"max":hi,"size":[b-a for a,b in zip(lo,hi)]}


# 路面检查仅包含台基和台阶；山体单独检测，避免把遮挡岩体误认为通路。
# 采样点偏离边界，绕开相邻三角面共享边的数值误差。
floors=[ob.evaluated_get(deps) for colkey in ("02","07") for ob in cols[colkey].objects if ob.type=="MESH"]
rocks=[ob.evaluated_get(deps) for ob in cols["01"].objects if ob.type=="MESH"]
def height_at(objects,x,y):
    hits=[]
    for ob in objects:
        inv=ob.matrix_world.inverted()
        origin=inv@Vector((x,y,500))
        direction=(inv.to_3x3()@Vector((0,0,-1))).normalized()
        hit,loc,normal,index=ob.ray_cast(origin,direction)
        if hit:
            hits.append(((ob.matrix_world@loc).z,ob.name))
    return max(hits,default=(None,None),key=lambda pair:pair[0])


missing=[]
intrusions=[]
samples=[]
for step in range(1178):
    y=-354.87+step*0.5
    fz,fn=height_at(floors,0.031,y)
    rz,rn=height_at(rocks,0.031,y)
    if fz is None:
        missing.append(round(y,3))
    elif rz is not None and rz>fz+0.025:
        intrusions.append({"y":round(y,3),"floor":fz,"rock":rz,"object":rn})
    if step%50==0:
        samples.append({"y":round(y,3),"height":fz,"surface":fn})
report={"blend":str(Path(bpy.data.filepath)),"unit_system":scene.unit_settings.system,
        "meters_per_unit":scene.unit_settings.scale_length,"objects":len(scene.objects),
        "cameras":[{"name":m.camera.name,"frame":m.frame,"eye_z":m.camera.location.z,
                    "lens_mm":m.camera.data.lens} for m in scene.timeline_markers],
        "mountain_bounds_m":bounds(cols["01"].objects),
        "courtyard_bounds_m":bounds([ob for ob in cols["02"].objects if ob.name.startswith("前庭净空")]),
        "hall_roof_bounds_m":bounds(cols["04"].objects),
        "hero_human_bounds_m":bounds([ob for ob in cols["11"].objects if ob.name.startswith("尺度人形_01_")]),
        "axis_missing_floor":missing,"axis_rock_intrusions":intrusions,"axis_sample_heights":samples,
        "external_image_count":len([im for im in bpy.data.images if im.source=="FILE"]),
        "parameters":params}
(root/"qa"/"geometry_audit.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({k:v for k,v in report.items() if k not in ("axis_sample_heights","parameters")},ensure_ascii=False),flush=True)
