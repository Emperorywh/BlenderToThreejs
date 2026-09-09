"""
最终保存、只读核验、内嵌交付说明与六机位渲染按顺序执行。
任一实质检查失败立即停止正式渲染，避免把未通过核验的场景当作交付版本。
"""
import bpy
import json
import gc
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
bed=bpy.data.objects.get('V08_南向云域_低位连续云床')
if bed:
    bed.rotation_euler.z=0
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'HeavenlyPalace_Lookdev_v08.blend'),compress=True)
for script in ['audit_lookdev_v08.py','finish_lookdev_v08.py','render_lookdev_v08.py']:
    path=ROOT/'scripts'/script
    exec(compile(path.read_text(encoding='utf-8'),str(path),'exec'),{'__name__':'__main__','__file__':str(path)})
    gc.collect()
    if script=='audit_lookdev_v08.py':
        report=json.loads((ROOT/'v08'/'qa'/'audit_v08.json').read_text(encoding='utf-8'))
        if not report['passed']:
            raise RuntimeError('第八版最终几何核验未通过，正式渲染停止。')
print('V08_ALL_DELIVERABLE_RENDERS_COMPLETE',flush=True)
