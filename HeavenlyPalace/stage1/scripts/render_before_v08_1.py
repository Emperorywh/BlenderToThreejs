"""
从原始第八版文件独立渲染调整前图像，作为真实场景对比基准。
只改变本次输出采样与分辨率，不保存或覆盖原始工程。
"""
import bpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
scene = bpy.context.scene
scene.frame_set(4)
scene.camera = next(m.camera for m in scene.timeline_markers if m.frame == 4)
scene.render.resolution_x = 1800
scene.render.resolution_y = 1350
scene.render.resolution_percentage = 50
scene.cycles.samples = 32
scene.render.filepath = str(ROOT / 'v08_1' / 'renders' / '00_before_v08.png')
bpy.ops.render.render(write_still=True)
