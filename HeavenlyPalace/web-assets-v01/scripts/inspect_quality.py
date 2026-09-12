"""
读取网页源工程中的构件边界、材质和集合，供资产升级确定修改范围。
只输出审计数据，不保存或修改已打开的工程文件。
"""
import bpy
import json
from pathlib import Path
from mathutils import Vector

root = Path(__file__).resolve().parents[1]
rows = []
for ob in bpy.context.scene.objects:
    if ob.type != 'MESH':
        continue
    points = [ob.matrix_world @ Vector(p) for p in ob.bound_box]
    rows.append(dict(name=ob.name, mesh=ob.data.name, vertices=len(ob.data.vertices),
                     bounds=[[min(p[i] for p in points) for i in range(3)],
                             [max(p[i] for p in points) for i in range(3)]],
                     materials=[m.name if m else None for m in ob.data.materials],
                     collections=[c.name for c in ob.users_collection],
                     properties={k: str(ob[k])[:300] for k in ob.keys()}))
report = dict(objects=rows, materials=[dict(name=m.name, spec=json.loads(m['web_spec']))
                                     for m in bpy.data.materials if 'web_spec' in m])
(root / 'qa').mkdir(exist_ok=True)
(root / 'qa' / 'quality-inventory.json').write_text(json.dumps(report, ensure_ascii=False), encoding='utf-8')
print('QUALITY_INVENTORY', len(rows), len(report['materials']), flush=True)
