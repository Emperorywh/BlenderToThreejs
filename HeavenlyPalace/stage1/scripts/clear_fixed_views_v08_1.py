"""
把南向近端云域移到三个外部固定相机后方，恢复入口与登山通路视线。
调整的是固定三维位置，所有相机继续共享同一套体积与可见性设置。
"""
import bpy
import json
from pathlib import Path
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
scene = bpy.context.scene
col = bpy.data.collections['18_V08_可渲染云海与水雾']
original_clouds = {r['name']: r for r in json.loads((ROOT / 'v08_1' / 'qa' / 'adjustments.json').read_text(encoding='utf-8'))['clouds']}
for ob in col.objects:
    if ob.name.startswith(('V08_1_南向积云_00_', 'V08_1_南向积云_01_')):
        # 云域远移时按空间比例展开起伏，保留殿内看到的云团角尺度。
        # 只调整环境云体，建筑、人物及相机尺度完全不参与此操作。
        origin = Vector((24, 365, 37.65))
        original = original_clouds[ob.name]
        ob.location = origin + (Vector(original['location']) - origin) * 2.8
        ob.scale = Vector(original['scale']) * 2.8
    if ob.name.startswith('V08_1_南向积云_'):
        bpy.context.view_layer.update()
        ymax = max((ob.matrix_world @ Vector(p)).y for p in ob.bound_box)
        if ymax > -1580:
            ob.location.y -= ymax + 1580
bed = bpy.data.objects['V08_南向云域_低位连续云床']
bed.location.y = -4400
bed.scale.y = 2500
scene.frame_set(4)
scene.camera = bpy.data.objects['CAM_04_殿内望云_v08_1']
scene.cycles.samples = 64
scene.render.resolution_percentage = 100
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT / 'HeavenlyPalace_Lookdev_v08_1.blend'), compress=True)
scene.render.resolution_percentage = 40
scene.cycles.samples = 16
for frame, name in [(4, 'K_clear_interior'), (2, 'K_clear_front')]:
    scene.frame_set(frame)
    scene.camera = next(m.camera for m in scene.timeline_markers if m.frame == frame)
    scene.render.filepath = str(ROOT / 'v08_1' / 'qa' / (name + '.png'))
    bpy.ops.render.render(write_still=True)
