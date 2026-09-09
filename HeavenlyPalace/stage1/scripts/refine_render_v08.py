"""
关闭云材质的独立发光采样，避免每个体积容器成为昂贵的采样目标。
保留统一的云雾外观和照明，先检查优化后的两个机位，再保存正式设置。
"""
import bpy
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
scene=bpy.context.scene
for mat in bpy.data.materials:
    if mat.name.startswith('V08_') and ('分形体积云' in mat.name or '局部水雾' in mat.name):
        mat.cycles.emission_sampling='NONE'
        mat.cycles.volume_sampling='DISTANCE'
        mat.cycles.volume_step_rate=2
scene.cycles.volume_step_rate=4
scene.cycles.volume_max_steps=192
scene.cycles.samples=48
scene.cycles.adaptive_threshold=.045
scene.render.resolution_percentage=100
scene.frame_set(1)
scene.camera=next(m.camera for m in scene.timeline_markers if m.frame==1)
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'HeavenlyPalace_Lookdev_v08.blend'),compress=True)
scene.render.resolution_percentage=40
scene.cycles.samples=16
for frame,name in [(1,'sample_01_oblique'),(4,'sample_04_interior')]:
    scene.frame_set(frame)
    scene.camera=next(m.camera for m in scene.timeline_markers if m.frame==frame)
    scene.render.filepath=str(ROOT/'v08'/'qa'/(name+'.png'))
    bpy.ops.render.render(write_still=True)
    print('V08_OPTIMIZED_PREVIEW',frame,flush=True)
