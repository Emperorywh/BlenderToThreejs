"""
在候选场景上比较后退站位和镜头偏移，验证月门与柱梁的完整关系。
所有试拍共用同一套真实云域，不改变灯光、物体尺度或可见性。
"""
import bpy
import json
from pathlib import Path
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / 'v08_1' / 'qa'
scene = bpy.context.scene
cam = bpy.data.objects['CAM_04_殿内望云_v08_1']
baseline = {r['name']: r for r in json.loads((QA / 'baseline_scene.json').read_text(encoding='utf-8'))['objects']}
scene.frame_set(4)
scene.render.resolution_percentage = 40
scene.cycles.samples = 16
for label, x, y, lens in [('E_rear', 18, 354, 41), ('F_rear_right', 22, 365, 45), ('G_rear_right_wide', 22, 365, 41)]:
    cam.location = (x, y, 37.65)
    cam.rotation_euler = (Vector((0, 240, 55)) - cam.location).to_track_quat('-Z', 'Y').to_euler()
    cam.data.lens = lens
    cam.data.shift_y = 0
    for ob in scene.objects:
        if ob.name.startswith('尺度人形_01_'):
            ob.location = Vector(baseline[ob.name]['location']) + Vector((x - 3, y - 340, 0))
    bpy.context.view_layer.update()
    scene.camera = cam
    scene.render.filepath = str(QA / (label + '.png'))
    bpy.ops.render.render(write_still=True)
    print('REAR_PREVIEW_READY', label, flush=True)
