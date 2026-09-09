"""
将增量说明、最终对象清单和统一渲染入口内嵌到新版工程。
仅整理元数据与文本，不改变任何几何、云域、灯光或相机渲染参数。
"""
import bpy
import json
import hashlib
from pathlib import Path
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'v08_1'
scene = bpy.context.scene
clouds = []
for ob in bpy.data.collections['18_V08_可渲染云海与水雾'].objects:
    points = [ob.matrix_world @ Vector(p) for p in ob.bound_box]
    clouds.append({'name': ob.name, 'position': list(ob.location), 'scale': list(ob.scale), 'bounds': [[min(p[i] for p in points), max(p[i] for p in points)] for i in range(3)], 'materials': [s.material.name for s in ob.material_slots if s.material]})
cam = scene.objects['CAM_04_殿内望云_v08_1']
inventory = {'scene': bpy.data.filepath, 'camera': {'name': cam.name, 'position': list(cam.location), 'rotation': list(cam.rotation_euler), 'lens': cam.data.lens, 'shift': [cam.data.shift_x, cam.data.shift_y], 'clip': [cam.data.clip_start, cam.data.clip_end]}, 'cloud_count': len(clouds), 'clouds': clouds, 'mountain_changes': json.loads((OUT / 'qa' / 'adjustments.json').read_text(encoding='utf-8'))['mountains'], 'source_sha256': hashlib.sha256((ROOT / 'HeavenlyPalace_Lookdev_v08.blend').read_bytes()).hexdigest()}
(OUT / 'qa' / 'final_scene_inventory.json').write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding='utf-8')
for label, path in [('V08_1_交付说明', OUT / 'V8.1交付说明.md'), ('V08_1_最终场景清单', OUT / 'qa' / 'final_scene_inventory.json'), ('V08_1_统一渲染入口', ROOT / 'scripts' / 'render_lookdev_v08.py'), ('V08_1_交付渲染流程', ROOT / 'scripts' / 'deliver_interior_v08_1.py')]:
    block = bpy.data.texts.get(label) or bpy.data.texts.new(label)
    block.clear()
    block.write(path.read_text(encoding='utf-8'))
scene['V08_1渲染设置'] = 'Cycles CPU；1800×1350；64最大采样；自适应0.025；降噪；沿用V8灯光曝光'
scene['V08_1相机说明'] = '帧4为新版殿内望云；原相机保留在相机集合；所有机位使用相同可见性'
scene.frame_set(4)
scene.camera = cam
scene.render.resolution_percentage = 100
scene.cycles.samples = 64
scene.render.filepath = str(OUT / 'renders' / '04_interior.png')
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT / 'HeavenlyPalace_Lookdev_v08_1.blend'), compress=True)
print('V08_1_PACKED', len(clouds), flush=True)
