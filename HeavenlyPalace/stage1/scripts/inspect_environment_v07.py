"""
只读提取 V6 环境占位、固定相机和建筑支撑的实际坐标。
不保存或修改基准文件，为 V7 的岩体塑形和落点复核提供依据。
"""
import bpy
import json
import hashlib
from pathlib import Path
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"v07"/"qa"
OUT.mkdir(parents=True,exist_ok=True)
scene=bpy.context.scene
records=[]
for col in scene.collection.children:
    for ob in col.all_objects:
        if col.name.startswith(("01_","09_","10_","15_")) or ob.type=="CAMERA" or any(s in ob.name for s in ("实体基座","总承台","实体支撑","入口休息","连续水平桥面","观景台_标高")) or "踏步高度_米" in ob:
            points=[ob.matrix_world@Vector(p) for p in ob.bound_box]
            record={"name":ob.name,"collection":col.name,"type":ob.type,"location":list(ob.location),
                    "rotation":list(ob.rotation_euler),"scale":list(ob.scale),"dimensions":list(ob.dimensions),
                    "bounds":[[min(p[i] for p in points),max(p[i] for p in points)] for i in range(3)]}
            if ob.type=="MESH" and col.name.startswith(("01_","10_")):
                record["vertices"]=[list(ob.matrix_world@v.co) for v in ob.data.vertices]
            if ob.type=="CAMERA":
                record.update(lens=ob.data.lens,ortho=ob.data.ortho_scale,projection=ob.data.type)
            records.append(record)

# 设备信息只读取当前 Blender 能实际识别的结果。
# 保存摘要用于防止后续环境重建意外改写已经验收的建筑文件。
devices=[]
try:
    prefs=bpy.context.preferences.addons["cycles"].preferences
    for backend in ("OPTIX","CUDA"):
        try:
            prefs.compute_device_type=backend
            prefs.get_devices()
            devices.extend({"backend":backend,"name":d.name,"type":d.type} for d in prefs.devices)
        except Exception as error:
            devices.append({"backend":backend,"error":str(error)})
except Exception as error:
    devices.append({"error":str(error)})
report={"file":bpy.data.filepath,"sha256":hashlib.sha256(Path(bpy.data.filepath).read_bytes()).hexdigest(),
        "blender":bpy.app.version_string,"objects":len(scene.objects),"devices":devices,
        "collections":{c.name:len(c.all_objects) for c in scene.collection.children},"records":records}
(OUT/"v06_environment_inspection.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({k:v for k,v in report.items() if k!="records"},ensure_ascii=False),flush=True)
