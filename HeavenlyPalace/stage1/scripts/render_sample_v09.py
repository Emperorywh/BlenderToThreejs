"""
从已保存样板输出真正的柱雕和门圈近景，以时间线切换相机。
使用正式画幅的百分之七十五检查贴面关系，不修改或保存样板文件。
"""
import bpy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
scene=bpy.context.scene
scene.render.resolution_percentage=75
scene.cycles.samples=32
for frame,name in [(17,'02_sample_column'),(18,'03_sample_moon')]:
    scene.frame_set(frame)
    scene.camera=next(m.camera for m in scene.timeline_markers if m.frame==frame)
    scene.render.filepath=str(ROOT/'v09'/'qa'/(name+'.png'))
    bpy.ops.render.render(write_still=True)
