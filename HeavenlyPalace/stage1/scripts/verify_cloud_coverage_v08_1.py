"""
沿已记录的屋檐射线计算局部闭合云体内部路径，确认不存在透明漏缝。
使用略小于实际网格的内接椭球给出保守光学厚度，不改变相机或场景。
"""
import bpy
import json
import math
from pathlib import Path
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / 'v08_1' / 'qa'
camera = bpy.data.objects['CAM_04_殿内望云_v08_1']
clouds = [o for o in bpy.context.scene.objects if o.name.startswith('V08_1_入口后侧低云舌_')]
rows = json.loads((QA / 'final_roof_rays.json').read_text(encoding='utf-8'))
results = []
for row in rows:
    target = Vector(row['hit'])
    delta = target - camera.location
    maximum = delta.length
    direction = delta.normalized()
    optical = 0
    for cloud in clouds:
        local_start = cloud.matrix_world.inverted() @ camera.location
        local_direction = cloud.matrix_world.inverted().to_3x3() @ direction
        a = local_direction.dot(local_direction)
        b = 2 * local_start.dot(local_direction)
        c = local_start.dot(local_start) - .95 ** 2
        discriminant = b * b - 4 * a * c
        if discriminant > 0:
            near = max(0, (-b - math.sqrt(discriminant)) / (2 * a))
            far = min(maximum, (-b + math.sqrt(discriminant)) / (2 * a))
            optical += max(0, far - near) * 1.5
    results.append({'pixel': row['pixel'], 'optical_depth_lower_bound': optical, 'transmittance_upper_bound': math.exp(-optical)})
report = {'samples': len(results), 'minimum_optical_depth': min(r['optical_depth_lower_bound'] for r in results), 'maximum_transmittance': max(r['transmittance_upper_bound'] for r in results), 'thin_paths': [r for r in results if r['optical_depth_lower_bound'] < 12]}
(QA / 'cloud_coverage.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print('CLOUD_COVERAGE', json.dumps(report, ensure_ascii=False), flush=True)
