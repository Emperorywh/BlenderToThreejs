"""
为百米级程序云启用明确步进的体积积分，避免默认空散射在大容器中开销过高。
云海仍为实际三维散射材质，并用两个原机位检查重叠区域和边缘质量。
"""
import bpy
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
scene=bpy.context.scene
scene.cycles.volume_biased=True
scene.cycles.volume_step_rate=1
scene.cycles.volume_max_steps=768
for mat in bpy.data.materials:
    if mat.name.startswith('V08_') and ('分形体积云' in mat.name or '局部水雾' in mat.name):
        mat.cycles.volume_step_rate=.35
        mat.cycles.volume_sampling='MULTIPLE_IMPORTANCE'
scene.render.resolution_percentage=100
scene.cycles.samples=48
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'HeavenlyPalace_Lookdev_v08.blend'),compress=True)
scene.render.resolution_percentage=40
scene.cycles.samples=16
for frame,name in [(1,'sample_01_oblique'),(4,'sample_04_interior')]:
    scene.frame_set(frame)
    scene.camera=next(m.camera for m in scene.timeline_markers if m.frame==frame)
    scene.render.filepath=str(ROOT/'v08'/'qa'/(name+'.png'))
    start=time.monotonic()
    bpy.ops.render.render(write_still=True)
    print('V08_VOLUME_BENCHMARK',frame,round(time.monotonic()-start,2),flush=True)
