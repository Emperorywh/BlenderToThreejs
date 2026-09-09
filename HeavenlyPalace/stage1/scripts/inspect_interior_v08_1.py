"""
只读检查第八版的机位、殿内几何和南向环境，输出增量制作基准。
保留原工程内容，不执行任何重建脚本，也不保存原文件。
"""
import bpy
import json
from pathlib import Path
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'v08_1' / 'qa'
OUT.mkdir(parents=True, exist_ok=True)
scene = bpy.context.scene
rows = []
for ob in scene.objects:
    row = {'name': ob.name, 'type': ob.type, 'collections': [c.name for c in ob.users_collection], 'location': list(ob.location), 'rotation': list(ob.rotation_euler), 'scale': list(ob.scale), 'hide_render': ob.hide_render, 'dimensions': list(ob.dimensions)}
    if ob.type == 'CAMERA':
        row.update(lens=ob.data.lens, shift_x=ob.data.shift_x, shift_y=ob.data.shift_y, clip_end=ob.data.clip_end)
    if ob.type == 'MESH':
        points = [ob.matrix_world @ Vector(v) for v in ob.bound_box]
        row['bounds'] = [[min(v[i] for v in points), max(v[i] for v in points)] for i in range(3)]
    rows.append(row)
report = {'objects': rows, 'collections': {c.name: len(c.all_objects) for c in bpy.data.collections}, 'markers': [(m.frame, m.name, m.camera.name if m.camera else None) for m in scene.timeline_markers], 'render': {'engine': scene.render.engine, 'samples': scene.cycles.samples, 'threads': scene.render.threads, 'resolution': [scene.render.resolution_x, scene.render.resolution_y]}, 'cloud_materials': {m.name: [(n.name, n.type, {i.name: str(i.default_value) for i in n.inputs if hasattr(i, 'default_value')}) for n in m.node_tree.nodes] for m in bpy.data.materials if m.use_nodes and '云' in m.name}}
(OUT / 'baseline_scene.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print('INSPECTION_READY', flush=True)
scene.frame_set(4)
scene.camera = next(m.camera for m in scene.timeline_markers if m.frame == 4)
scene.render.resolution_percentage = 33
scene.cycles.samples = 12
scene.render.filepath = str(OUT / 'before_preview.png')
bpy.ops.render.render(write_still=True)
