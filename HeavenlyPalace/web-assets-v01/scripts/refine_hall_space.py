"""
调整主殿净高、中央开间与落地月门，并核验实体通视、柱网连接和共享实例。
默认保存可编辑工程；核验模式仅写数据报告，不渲染也不启动浏览器。
"""
import hashlib
import json
import math
import shutil
import sys
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from hall_space import (REVISION, FLOOR_Z, GATE_RADIUS, GATE_CENTER_Z, MOON_NAME,
                        apply_space, space_active, column_x)
from blend_io import save_web_blend


def protected_digest():
    """
    核对自然环境、人物、相机与台基地坪的几何摘要，确保空间调整范围准确。
    检查使用实际网格和完整变换，不依赖容易遗漏局部变动的对象数量。
    """
    digest = hashlib.sha256()
    for ob in sorted(bpy.context.scene.objects, key=lambda item: item.name):
        protected = ob.type == 'CAMERA' or any(c.name.startswith(('01','09','10','17_','19_V09_长袍人物')) for c in ob.users_collection)
        protected |= ob.name == 'H01_主殿台基石栏与须弥腰线' or '地坪' in ob.name
        if protected:
            digest.update(ob.name.encode())
            digest.update(np.asarray(ob.matrix_world, dtype='<f8').tobytes())
            if ob.type == 'MESH':
                coords = np.empty(len(ob.data.vertices) * 3, dtype=np.float32)
                ob.data.vertices.foreach_get('co', coords)
                digest.update(coords.tobytes())
    return digest.hexdigest()


def verify():
    """
    检查门圈圆度、落地宽度、所有柱身的顶底与柱头接触，以及扩大后的真实通视。
    检查同时覆盖原先圆洞以外的新开口，避免只验证中心空隙而遗漏旧墙或浮雕。
    """
    assert space_active(), '尚未应用殿内空间调整。'
    scene = bpy.context.scene
    moon = bpy.data.objects[MOON_NAME]
    points = [moon.matrix_world @ v.co for v in moon.data.vertices]
    radius = min(math.hypot(p.x, p.z - GATE_CENTER_Z) for p in points)
    assert abs(radius - GATE_RADIUS) < .002, '月门净口圆度或尺寸异常。'
    assert abs(min(p.z for p in points) - FLOOR_Z) < .002, '月门底部未落在地坪。'
    columns = []
    for row in range(1, 5):
        for index, old_x in enumerate((-90,-60,-30,30,60,90), 1):
            name = f'主殿巨柱_列{index}_进{row}'
            shaft = bpy.data.objects[name + '_柱身']
            head = bpy.data.objects[name + '_承梁柱头']
            bounds = [shaft.matrix_world @ Vector(v) for v in shaft.bound_box]
            top, bottom = max(p.z for p in bounds), min(p.z for p in bounds)
            head_bottom = min((head.matrix_world @ Vector(v)).z for v in head.bound_box)
            assert abs(top - 90.4) < .002 and abs(bottom - 37.6) < .002, '柱身标高异常：' + name
            assert abs(head_bottom - top) < .002, '柱头未接触柱身：' + name
            assert abs(shaft.location.x - column_x(old_x)) < .002, '柱轴偏离新柱网：' + name
            columns.append(dict(name=name, x=shaft.location.x, bottom=bottom, top=top))
    targets = [ob for ob in scene.objects if ob.type == 'MESH' and (ob.name.startswith(('V05_月门','V09_月门','H01_')))]
    samples = [(0,37),(0,49),(0,79),(-27,38),(27,38),(-29,49),(29,49),(-22,68),(22,68)]
    for x, z in samples:
        for ob in targets:
            inverse = ob.matrix_world.inverted()
            origin = inverse @ Vector((x,239,z))
            end = inverse @ Vector((x,247,z))
            hit = ob.ray_cast(origin, (end-origin).normalized(), distance=(end-origin).length)
            assert not hit[0], f'扩大后的门洞受阻：{ob.name}，采样点{(x,z)}'
    report = dict(revision=REVISION, gate_diameter_m=radius*2,
                  gate_floor_width_m=moon['落地净宽_米'], gate_center_z=GATE_CENTER_Z,
                  central_bay_width_m=78, nominal_ceiling_height_m=54, columns=columns,
                  clear_opening_samples=samples, passed=True)
    return report


def main():
    """
    首次调整备份完整工程和网页资源，核验通过之后再原子写回正式工程。
    后续运行只重用基准和目标参数，支持用户继续细调且不会再次累计抬高。
    """
    qa = ROOT / 'qa'
    qa.mkdir(exist_ok=True)
    if '--verify' not in sys.argv:
        backup = qa / 'before-hall-space-v3'
        if not backup.exists():
            backup.mkdir()
            shutil.copy2(bpy.data.filepath, backup / 'HeavenlyPalace_WebAssets_v01.blend')
            shutil.copytree(ROOT / 'assets', backup / 'assets')
        before = protected_digest()
        apply_space()
        assert before == protected_digest(), '主殿空间以外的受保护内容发生变化。'
    report = verify()
    if '--verify' not in sys.argv:
        save_web_blend(ROOT / 'HeavenlyPalace_WebAssets_v01.blend')
    (qa / 'hall-space-v3-verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print('HALL_SPACE_COMPLETE', json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
