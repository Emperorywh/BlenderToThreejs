"""
以镜头偏移收住右侧平台栏杆，让巨柱承担画面右边界。
继续保留原始人眼高度、完整月门和前景地面，不改变场景可见性。
"""
import bpy
from pathlib import Path
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
scene = bpy.context.scene
scene.frame_set(4)
cam = bpy.data.objects['CAM_04_殿内望云_v08_1']
cam.data.lens = 52
cam.data.shift_x = -.12
cam.rotation_euler = (Vector((0, 240, 53)) - cam.location).to_track_quat('-Z', 'Y').to_euler()
scene.camera = cam
scene.render.resolution_percentage = 40
scene.cycles.samples = 20
scene.render.filepath = str(ROOT / 'v08_1' / 'qa' / 'I_final_composition.png')
bpy.ops.render.render(write_still=True)
scene.render.resolution_percentage = 100
scene.cycles.samples = 64
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT / 'HeavenlyPalace_Lookdev_v08_1.blend'), compress=True)
