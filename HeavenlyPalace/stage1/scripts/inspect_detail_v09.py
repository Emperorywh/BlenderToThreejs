"""
只读检查第八点一版，记录所有保护对象及材质、灯光与相机基准。
先输出真实殿内渲染，供第九版精修前确认云海与画面可见区域。
"""
import bpy
import json
import hashlib
import time
from pathlib import Path
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'v09'
for directory in (OUT, OUT / 'qa', OUT / 'renders', OUT / 'comparison'):
    directory.mkdir(parents=True, exist_ok=True)
scene = bpy.context.scene
rows = []
for ob in scene.objects:
    row = {'name': ob.name, 'type': ob.type, 'location': list(ob.location), 'rotation': list(ob.rotation_euler), 'scale': list(ob.scale), 'dimensions': list(ob.dimensions), 'hide_render': ob.hide_render, 'collections': [c.name for c in ob.users_collection]}
    if ob.type == 'MESH':
        pts = [ob.matrix_world @ Vector(v) for v in ob.bound_box]
        row.update(bounds=[[min(v[i] for v in pts), max(v[i] for v in pts)] for i in range(3)], vertices=len(ob.data.vertices), polygons=len(ob.data.polygons), data=ob.data.name, materials=[m.name if m else None for m in ob.data.materials], slots=[s.material.name if s.material else None for s in ob.material_slots], modifiers=[{'name': m.name, 'type': m.type} for m in ob.modifiers])
    if ob.type == 'CAMERA':
        row.update(lens=ob.data.lens, shift_x=ob.data.shift_x, shift_y=ob.data.shift_y)
    if ob.type == 'LIGHT':
        row.update(energy=ob.data.energy, color=list(ob.data.color))
    rows.append(row)
report = {'source_sha256': hashlib.sha256(Path(bpy.data.filepath).read_bytes()).hexdigest(), 'objects': rows, 'collections': {c.name: {'hide_render': c.hide_render, 'count': len(c.all_objects)} for c in bpy.data.collections}, 'markers': [(m.frame, m.name, m.camera.name if m.camera else None) for m in scene.timeline_markers], 'world': scene.world.name, 'exposure': scene.view_settings.exposure, 'render': {'samples': scene.cycles.samples, 'engine': scene.render.engine, 'device': scene.cycles.device, 'threads': scene.render.threads, 'volume_step_rate': scene.cycles.volume_step_rate}}
(OUT / 'qa' / 'baseline_v08_1.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
scene.frame_set(4)
scene.camera = bpy.data.objects['CAM_04_殿内望云_v08_1']
scene.render.resolution_x, scene.render.resolution_y = 1800, 1350
scene.render.resolution_percentage = 50
scene.cycles.samples = 24
scene.render.filepath = str(OUT / 'qa' / '00_baseline_interior.png')
started = time.monotonic()
bpy.ops.render.render(write_still=True)
(OUT / 'qa' / 'baseline_preview_time.json').write_text(json.dumps({'seconds': time.monotonic()-started, 'resolution': [900,675], 'samples': 24}), encoding='utf-8')
print('V09_BASELINE_READY', flush=True)
