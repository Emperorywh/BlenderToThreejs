"""
读取最终相机，定位门洞底部潜在露出的精确三维位置。
仅复用射线结构构建部分，不运行候选相机搜索，也不保存场景。
"""
import bpy
import ast
import json
from pathlib import Path
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / 'scripts' / 'check_sightlines_v08_1.py'
module = ast.parse(path.read_text(encoding='utf-8'))
nodes = []
for node in module.body:
    if isinstance(node, ast.For) and isinstance(node.target, ast.Name) and node.target.id == 'y':
        break
    nodes.append(node)
exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), globals())
corners = cam.data.view_frame(scene=scene)
low_x, high_x = min(p.x for p in corners), max(p.x for p in corners)
low_y, high_y = min(p.y for p in corners), max(p.y for p in corners)
results = []
for px in range(350, 610, 2):
    for py in range(388, 412):
        direction = (cam.matrix_world.to_3x3() @ Vector((low_x + (high_x-low_x)*(px+.5)/720, high_y-(high_y-low_y)*(py+.5)/540, corners[0].z))).normalized()
        hit, normal, index, distance = tree.ray_cast(cam.location, direction, 30000)
        if hit is not None and hit.y < 230:
            at_cloud = cam.location + direction * ((-169-cam.location.y) / direction.y)
            results.append({'pixel': [px,py], 'object': owners[index], 'hit': list(hit), 'at_cloud': list(at_cloud)})
(QA / 'final_roof_rays.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print('FINAL_ROOF_RAYS', len(results), flush=True)
