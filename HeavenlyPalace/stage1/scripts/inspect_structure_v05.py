"""
只读检查已验收的 V4 场景，记录主殿结构与渲染设备。
本脚本不保存工程，不改变任何已有对象或相机。
"""
import bpy
import json
from pathlib import Path
from mathutils import Vector

root=Path(__file__).resolve().parents[1]
out=root/"v05"/"qa"
out.mkdir(parents=True,exist_ok=True)
scene=bpy.context.scene
records=[]
for col in scene.collection.children:
    if col.name.startswith(("03_","04_","05A_","12_")):
        for ob in col.all_objects:
            points=[ob.matrix_world@Vector(corner) for corner in ob.bound_box]
            records.append({"name":ob.name,"collection":col.name,"type":ob.type,
                            "location":list(ob.location),"dimensions":list(ob.dimensions),
                            "bounds":[[min(p[i] for p in points),max(p[i] for p in points)] for i in range(3)],
                            "data":ob.data.name if ob.data else None})

# 仅查询设备能力，最终构建脚本另行选择可用的计算设备。
# 保留查询失败信息，避免把无输出误认为有可用显卡。
devices=[]
try:
    prefs=bpy.context.preferences.addons["cycles"].preferences
    prefs.get_devices()
    devices=[{"name":d.name,"type":d.type,"id":d.id} for d in prefs.devices]
except Exception as error:
    devices=[{"error":str(error)}]
report={"blender":bpy.app.version_string,"scene":scene.name,"objects":len(scene.objects),
        "collections":{c.name:len(c.all_objects) for c in scene.collection.children},
        "devices":devices,"structure":records,
        "render":{"engine":scene.render.engine,"samples":scene.cycles.samples,
                  "resolution":[scene.render.resolution_x,scene.render.resolution_y]},
        "texts":[t.name for t in bpy.data.texts]}
(out/"v04_inspection.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(report,ensure_ascii=False),flush=True)
