"""
只读检查已验收的 V5 工程，提取本轮建筑、石构与相机的实际尺寸。
本脚本不保存工程，不修改任何基准对象，结果供 V6 建模和审查使用。
"""
import bpy
import json
from pathlib import Path
from mathutils import Vector

root=Path(__file__).resolve().parents[1]
out=root/"v06"/"qa"
out.mkdir(parents=True,exist_ok=True)
scene=bpy.context.scene
records=[]
for col in scene.collection.children:
    if col.name.startswith(("02_","05_","06_","07_","08_","12_")):
        for ob in col.all_objects:
            points=[ob.matrix_world@Vector(corner) for corner in ob.bound_box]
            records.append({"name":ob.name,"collection":col.name,"type":ob.type,
                            "location":list(ob.location),"rotation":list(ob.rotation_euler),
                            "dimensions":list(ob.dimensions),
                            "bounds":[[min(p[i] for p in points),max(p[i] for p in points)] for i in range(3)],
                            "data":ob.data.name if ob.data else None,
                            "materials":[m.name for m in ob.data.materials] if ob.type in ("MESH","CURVE") else []})

# 查询实际可用的渲染设备，并保留错误说明以便选择可靠的渲染设置。
# 不根据硬件型号猜测设备是否可用，也不改变保存中的渲染配置。
devices=[]
try:
    prefs=bpy.context.preferences.addons["cycles"].preferences
    prefs.get_devices()
    devices=[{"name":d.name,"type":d.type,"id":d.id} for d in prefs.devices]
except Exception as error:
    devices=[{"error":str(error)}]
report={"blender":bpy.app.version_string,"objects":len(scene.objects),
        "collections":{c.name:len(c.all_objects) for c in scene.collection.children},
        "devices":devices,"structure":records,"texts":[t.name for t in bpy.data.texts],
        "cameras":[{"name":o.name,"location":list(o.location),"rotation":list(o.rotation_euler),
                    "lens":o.data.lens,"type":o.data.type,"ortho":o.data.ortho_scale} for o in scene.objects if o.type=="CAMERA"]}
(out/"v05_inspection.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({k:v for k,v in report.items() if k!="structure"},ensure_ascii=False),flush=True)
