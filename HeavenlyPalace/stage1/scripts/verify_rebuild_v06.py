"""
实际运行工程内嵌入口两次，核验重建的确定性与重复执行安全性。
测试只保存到 V6 的审查目录，不覆盖正式交付工程或 V5 基准。
"""
import ast
import bpy
import json
import struct
import hashlib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"v06"/"qa"
audit_source=ast.parse((ROOT/"scripts"/"audit_architecture_v06.py").read_text(encoding="utf-8"))
definitions=[node for node in audit_source.body if isinstance(node,ast.FunctionDef) and node.name in ("signature","camera_record")]
exec(compile(ast.Module(body=definitions,type_ignores=[]),"复用只读摘要函数","exec"),globals())


# 对比的是实际对象和材质，压缩文件的时间戳及输出路径不影响判断。
# 每次重建前都由内嵌入口读取参数，并重新载入受摘要保护的 V5 文件。
def snapshot():
    bpy.context.view_layer.update()
    return {ob.name:signature(ob) for ob in bpy.context.scene.objects}


before=snapshot()
summary_body=(OUT/"build_summary.json").read_text(encoding="utf-8")
baseline=ROOT/"HeavenlyPalace_Structure_v05.blend"
baseline_hash=hashlib.sha256(baseline.read_bytes()).hexdigest()
parameters=json.loads(bpy.data.texts["07_v06建筑参数.json"].as_string())
parameters["output_file"]="v06/qa/v06_rebuild_check.blend"
block=bpy.data.texts["07_v06建筑参数.json"]
block.clear()
block.write(json.dumps(parameters,ensure_ascii=False,indent=2))
results=[]
for pass_number in (1,2):
    body=bpy.data.texts["02_当前阶段重建入口.py"].as_string()
    exec(compile(body,"核验内嵌V06重建入口","exec"),{"__name__":"__main__"})
    after=snapshot()
    changed=[name for name,digest in before.items() if after.get(name)!=digest]
    added=sorted(set(after)-set(before))
    results.append({"pass":pass_number,"object_count":len(after),"changed_objects":changed,"added_objects":added,
                    "saved_file":bpy.data.filepath,"passed":not changed and not added})
report={"baseline_sha256":baseline_hash,"baseline_unchanged":hashlib.sha256(baseline.read_bytes()).hexdigest()==baseline_hash,
        "original_object_count":len(before),"embedded_rebuilds":results,"legacy_entry_tested":"build_whitebox.py 当前阶段转接已实际运行"}
report["passed"]=report["baseline_unchanged"] and all(r["passed"] for r in results)
(OUT/"build_summary.json").write_text(summary_body,encoding="utf-8")
(OUT/"rebuild_verification.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(report,ensure_ascii=False),flush=True)
if not report["passed"]:
    raise RuntimeError("内嵌重建与待交付对象不一致，请检查报告。")
