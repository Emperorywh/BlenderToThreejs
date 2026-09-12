"""
通过真实建筑射线检查低角度日光能否进入殿内，记录地坪高度和遮挡对象。
仅在后台读取 Blender 工程，不修改模型、不保存工程，也不启动浏览器。
"""
import json
import math
from pathlib import Path

import bpy
from mathutils import Vector


def main():
    """
    在殿内四米网格取样，比较原太阳和候选太阳的真实直射覆盖范围。
    网格同时记录明暗分布，避免只靠灯光角度猜测檐下是否能够出现长投影。
    """
    scene = bpy.context.scene
    depsgraph = bpy.context.evaluated_depsgraph_get()
    floor = next(ob for ob in scene.objects if ob.type == 'MESH'
                 and any(mat and 'V09_白玉地坪' in mat.name for mat in ob.data.materials))
    corners = [floor.matrix_world @ Vector(point) for point in floor.bound_box]
    height = max(point.z for point in corners)
    candidates = {'original': (-520, -650, 790), 'warm_low': (650, -650, 430),
                  'warm_lower': (650, -650, 320)}
    report = {'floor': floor.name, 'floor_height': height, 'directions': {}}
    for name, values in candidates.items():
        direction = Vector(values).normalized()
        lit = []
        blockers = {}
        rows = []
        for y in range(249, 346, 4):
            row = ''
            for x in range(-84, 85, 4):
                origin = Vector((x, y, height + .06))
                hit, _, _, _, ob, _ = scene.ray_cast(depsgraph, origin, direction, distance=2400)
                row += '.' if hit else '*'
                if hit:
                    blockers[ob.name] = blockers.get(ob.name, 0) + 1
                else:
                    lit.append((x, y))
            rows.append(row)
        report['directions'][name] = {
            'three_direction': [direction.x, direction.z, -direction.y],
            'elevation_degrees': math.degrees(math.asin(direction.z)),
            'lit_fraction': len(lit) / (len(rows) * len(rows[0])),
            'lit_points': lit,
            'floor_rows_northward': rows,
            'main_blockers': sorted(blockers.items(), key=lambda item: -item[1])[:6],
        }
    output = Path(__file__).resolve().parents[1] / 'qa' / 'hall-lighting'
    output.mkdir(parents=True, exist_ok=True)
    (output / 'sun-audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({name: {key: value for key, value in row.items()
                            if key in ('elevation_degrees', 'lit_fraction', 'main_blockers')}
                      for name, row in report['directions'].items()}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
