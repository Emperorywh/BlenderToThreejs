"""
实际执行 V7 工程内嵌重建入口两次，并逐对象核验几何、材质和相机。
只保存审查副本，正式 V7 与 V6 基准均保持原样。
"""
import bpy
import ast
import json
import struct
import hashlib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"v07"/"qa"
source=ast.parse((ROOT/"scripts"/"audit_architecture_v06.py").read_text(encoding="utf-8"))
defs=[n for n in source.body if isinstance(n,ast.FunctionDef) and n.name in ("signature","camera_record")]
exec(compile(ast.Module(body=defs,type_ignores=[]),"只读重建摘要函数","exec"),globals())


def snapshot():
    bpy.context.view_layer.update()
    return {o.name:(camera_record(o) if o.type=="CAMERA" else signature(o)) for o in bpy.context.scene.objects}


# 每次入口都重新载入受摘要保护的 V6，不在上一次 V7 的对象上追加。
# 副本输出路径作为唯一测试参数差异，不影响场景对象的可编辑性与一致性。
before=snapshot()
summary=(OUT/"build_summary.json").read_text(encoding="utf-8")
baseline=ROOT/"HeavenlyPalace_Architecture_v06.blend"
base_hash=hashlib.sha256(baseline.read_bytes()).hexdigest()
parameters=json.loads(bpy.data.texts["09_v07环境参数.json"].as_string())
parameters["output_file"]="v07/qa/v07_rebuild_check.blend"
block=bpy.data.texts["09_v07环境参数.json"]
block.clear()
block.write(json.dumps(parameters,ensure_ascii=False,indent=2))
results=[]
for pass_number in (1,2):
    body=bpy.data.texts["02_当前阶段重建入口.py"].as_string()
    exec(compile(body,"核验V7内嵌重建入口","exec"),{"__name__":"__main__"})
    after=snapshot()
    changed=[n for n,s in before.items() if after.get(n)!=s]
    added=sorted(set(after)-set(before))
    results.append({"pass":pass_number,"objects":len(after),"changed":changed,"added":added,"passed":not changed and not added})
report={"baseline_sha256":base_hash,"baseline_unchanged":hashlib.sha256(baseline.read_bytes()).hexdigest()==base_hash,
        "original_objects":len(before),"embedded_rebuilds":results}
report["passed"]=report["baseline_unchanged"] and all(r["passed"] for r in results)
(OUT/"build_summary.json").write_text(summary,encoding="utf-8")
(OUT/"rebuild_verification.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(report,ensure_ascii=False),flush=True)
if not report["passed"]:
    raise RuntimeError("V7 内嵌重建不一致，请先检查审查副本。")
