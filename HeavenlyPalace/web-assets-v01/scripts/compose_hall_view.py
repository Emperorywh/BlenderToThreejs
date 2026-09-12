"""
以中轴广角建筑机位重新组织殿内望云构图，让柱列、藻井、石坪和月门共同入画。
直接修改网页副本的第四机位与前景人物，导出完整相机矩阵；预览模式只改内存。
"""
import argparse
import hashlib
import json
import math
import shutil
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from blend_io import save_web_blend
from hall_space import FLOOR_Z, GATE_CENTER_Z, GATE_RADIUS, GATE_FRONT_Y, UPPER_LIFT

# 镜头保持水平，通过镜头上移收进抬高后的藻井，避免柱线向中心倾斜。
# 宽屏按导出的构图参数适度收紧，门口地坪保持在同一高度，人物仍采用绝对落点。
REVISION = 'hall-view-v3'
EYE = (0.0, 363.0, 39.0)
LENS_MM = 28.0
SHIFT_Y = 0.19
PERSON_XY = (0.0, 330.0)
BASE_ASPECT = 4 / 3
FRAMING_REFERENCE_ASPECT = 3 / 2
FRAMING_WIDE_ASPECT = 12 / 5
FRAMING_WIDE_SCALE = 1.16
CONVERSION = Matrix(((1, 0, 0, 0), (0, 0, 1, 0), (0, -1, 0, 0), (0, 0, 0, 1)))


def flat(matrix):
    """
    以列主序输出矩阵，与网页 Matrix4.fromArray 的读取方式一致。
    坐标转换只施加在世界矩阵左侧，相机自身的局部观察轴保持不变。
    """
    return [matrix[row][column] for column in range(4) for row in range(4)]


def write_json(path, data):
    """
    统一采用可读的简体中文与实际换行保存构图参数和核验结果。
    报告写入被忽略的检查目录，正式数据仍留在原有资源入口。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def composition_framing(camera, projection):
    """
    用实际门口地坪的投影位置定义宽屏取景锚点，保证地面前景不会随收紧镜头消失。
    同一组参数写入相机数据并用于离线核验，网页无需维护第二套几何尺寸。
    """
    clip = projection @ camera.matrix_world.inverted() @ Vector((0, GATE_FRONT_Y, FLOOR_Z, 1))
    assert clip.w > 0, '门口地坪必须位于相机前方。'
    return dict(reference_aspect=FRAMING_REFERENCE_ASPECT, wide_aspect=FRAMING_WIDE_ASPECT,
                wide_scale=FRAMING_WIDE_SCALE, floor_anchor_ndc=clip.y / clip.w)


def viewport_projection(projection, aspect, framing):
    """
    复现网页的等比扩幅及殿内宽屏收紧，水平与竖向尺度使用相同倍率，圆弧不会变椭圆。
    收紧围绕门口地坪进行，三比二保留参考构图，更宽画幅逐步减少无关的侧向空间。
    """
    result = projection.copy()
    horizontal = min(1, BASE_ASPECT / aspect)
    vertical = min(1, aspect / BASE_ASPECT)
    result[0][0] *= horizontal
    result[1][1] *= vertical
    result[0][2] *= horizontal
    result[1][2] *= vertical
    progress = min(1, max(0, (aspect - framing['reference_aspect']) /
                          (framing['wide_aspect'] - framing['reference_aspect'])))
    scale = 1 + progress * (framing['wide_scale'] - 1)
    result[0][0] *= scale
    result[1][1] *= scale
    result[0][2] *= scale
    result[1][2] = result[1][2] * scale + (scale - 1) * framing['floor_anchor_ndc']
    return result


def camera_record(camera, previous):
    """
    从 Blender 实际求值的相机同步全部字段，避免只改焦距却留下旧投影矩阵。
    保留相机原有名称与编号，使时间线、网页导航及历史工程引用继续有效。
    """
    data = camera.data
    projection = camera.calc_matrix_camera(bpy.context.evaluated_depsgraph_get(), x=1280, y=960)
    world = CONVERSION @ camera.matrix_world
    quaternion = world.to_quaternion()
    return dict(previous, position=list(world.translation),
                quaternion_xyzw=[quaternion.x, quaternion.y, quaternion.z, quaternion.w],
                direction=list(world.to_3x3() @ Vector((0, 0, -1))),
                up=list(world.to_3x3() @ Vector((0, 1, 0))), projection_type=data.type,
                lens_mm=data.lens, sensor_width_mm=data.sensor_width,
                sensor_height_mm=data.sensor_height, sensor_fit=data.sensor_fit,
                shift_x=data.shift_x, shift_y=data.shift_y, near=data.clip_start, far=data.clip_end,
                vertical_fov_degrees=math.degrees(2 * math.atan(1 / projection[1][1])),
                orthographic_width=None, orthographic_height=None,
                projection_matrix=flat(projection), world_matrix=flat(world),
                composition_revision=REVISION,
                composition_framing=composition_framing(camera, projection))


def configure(camera):
    """
    配合抬高的殿堂和拓宽的柱网建立对称纵深，调整第四机位与第一位人物的平移。
    不改变人物身高、模型网格或材料；其余三台相机仍采用既有构图。
    """
    camera.location = EYE
    camera.rotation_euler = Vector((0, -1, 0)).to_track_quat('-Z', 'Y').to_euler()
    camera.data.type = 'PERSP'
    camera.data.lens = LENS_MM
    camera.data.sensor_width = 36
    camera.data.sensor_height = 24
    camera.data.sensor_fit = 'AUTO'
    camera.data.shift_x = 0
    camera.data.shift_y = SHIFT_Y
    camera.data.clip_start = 0.08
    camera.data.clip_end = 100000
    head = bpy.data.objects['V09_人物01_头']
    offset = Vector((PERSON_XY[0] - head.location.x, PERSON_XY[1] - (head.location.y + 0.01), 0))
    for ob in bpy.context.scene.objects:
        if ob.name.startswith('V09_人物01_'):
            ob.location += offset
    bpy.context.view_layer.update()


def measure(camera):
    """
    在参考画幅、常见宽屏与超宽屏中检查真实门洞和柱列，按网页相同算法计算取景。
    同时检查圆弧等比投影、门内通视及人物尺度，所有结果来自几何数据而非截图。
    """
    scene = bpy.context.scene
    deps = bpy.context.evaluated_depsgraph_get()
    projection = camera.calc_matrix_camera(deps, x=1280, y=960)
    framing = composition_framing(camera, projection)
    view = camera.matrix_world.inverted()

    def screen(point, transform):
        """
        将真实米制锚点变换为左上角原点的归一化画面坐标。
        该结果只用于取景判断，不生成或读取浏览器截图。
        """
        clip = transform @ Vector((*point, 1))
        assert clip.w > 0, '构图锚点落在相机后方。'
        return [(clip.x / clip.w + 1) / 2, (1 - clip.y / clip.w) / 2]

    world_anchors = {
        'gate_left': (-GATE_RADIUS, GATE_FRONT_Y, GATE_CENTER_Z),
        'gate_right': (GATE_RADIUS, GATE_FRONT_Y, GATE_CENTER_Z),
        'gate_top': (0, GATE_FRONT_Y, GATE_CENTER_Z + GATE_RADIUS),
        'gate_bottom': (0, GATE_FRONT_Y, FLOOR_Z),
        'ceiling_front': (0, GATE_FRONT_Y - 1, 80 + UPPER_LIFT),
        'person_foot': (*PERSON_XY, FLOOR_Z), 'person_top': (*PERSON_XY, FLOOR_Z + 1.8),
    }
    result = dict(revision=REVISION, eye_blender=list(camera.location), lens_mm=camera.data.lens,
                  shift_y=camera.data.shift_y, composition_framing=framing, viewports={})
    for label, aspect in (('4_3', BASE_ASPECT), ('3_2', 3 / 2), ('16_9', 16 / 9), ('12_5', 12 / 5), ('9_16', 9 / 16)):
        viewport = viewport_projection(projection, aspect, framing)
        transform = viewport @ view
        anchors = {name: screen(point, transform) for name, point in world_anchors.items()}
        # 三比二的近柱允许切入画面边缘，柱身包围盒与画面的交集决定是否仍参与构图。
        # 使用实际柱网而不是旧版中心点阈值，避免拓宽中轴后误判边缘柱子完全不可见。
        rows = []
        for row in (1, 2, 3):
            pair = []
            for column in (3, 4):
                ob = bpy.data.objects[f'主殿巨柱_列{column}_进{row}_柱身']
                corners = [screen(ob.matrix_world @ Vector(corner), transform) for corner in ob.bound_box]
                bounds = [min(p[0] for p in corners), min(p[1] for p in corners),
                          max(p[0] for p in corners), max(p[1] for p in corners)]
                visible = bounds[2] > 0 and bounds[0] < 1 and bounds[3] > 0 and bounds[1] < 1
                if label in ('3_2', '12_5'):
                    assert visible, '柱列未形成可辨认的纵深：' + label + '/' + ob.name
                pair.append(dict(name=ob.name, bounds=bounds, visible=visible,
                                 center=screen((ob.location.x, ob.location.y, GATE_CENTER_Z), transform)))
            rows.append(pair)
        circular_scale_error = abs(viewport[0][0] * aspect / viewport[1][1] - 1)
        assert circular_scale_error < 1e-6, '投影横纵缩放不一致，月门会变形。'
        result['viewports'][label] = dict(aspect=aspect, anchors=anchors, column_rows=rows,
            gate_width_fraction=abs(anchors['gate_right'][0] - anchors['gate_left'][0]),
            ceiling_front_fraction=anchors['ceiling_front'][1],
            floor_foreground_fraction=1 - anchors['gate_bottom'][1],
            person_height_fraction=anchors['person_foot'][1] - anchors['person_top'][1],
            circular_scale_error=circular_scale_error)
    # 保留基准字段方便旧报告工具读取，同时把新的宽屏结果作为独立可检查的记录。
    # 验收比例使用三比二参考画幅和用户当前的超宽画幅，不把四比三数字冒充宽屏效果。
    reference = result['viewports']['3_2']
    wide = result['viewports']['12_5']
    result['anchors'] = reference['anchors']
    result['gate_width_fraction_4_3'] = result['viewports']['4_3']['gate_width_fraction']
    result['gate_width_fraction_3_2'] = reference['gate_width_fraction']
    result['gate_width_fraction_12_5'] = wide['gate_width_fraction']
    for key in ('ceiling_front_fraction', 'floor_foreground_fraction', 'person_height_fraction'):
        result[key] = reference[key]
    result['clear_sightlines'] = []
    for x, z in ((0, FLOOR_Z + 3), (0, GATE_CENTER_Z), (0, GATE_CENTER_Z + 24),
                 (-26, GATE_CENTER_Z), (26, GATE_CENTER_Z), (-24, FLOOR_Z + 3), (24, FLOOR_Z + 3)):
        point = (x, GATE_FRONT_Y - 2, z)
        direction = Vector(point) - camera.location
        hit = scene.ray_cast(deps, camera.location, direction.normalized(), distance=direction.length)
        assert not hit[0], '月门视线被遮挡：' + (hit[4].name if hit[0] else '')
        result['clear_sightlines'].append(list(point))
    result['visible_column_rows'] = reference['column_rows']
    people = [ob for ob in scene.objects if ob.type == 'MESH' and ob.name.startswith('V09_人物01_')]
    points = [ob.matrix_world @ Vector(corner) for ob in people for corner in ob.bound_box]
    bottom, top = min(p.z for p in points), max(p.z for p in points)
    assert abs(bottom - FLOOR_Z) < 0.002 and abs(top - bottom - 1.8) < 0.015, '人物尺度或落地位置异常。'
    result['person_height_m'] = top - bottom
    assert 0.35 < result['gate_width_fraction_3_2'] < 0.41, '参考画幅的月门占比偏离目标。'
    assert 0.25 < result['gate_width_fraction_12_5'] < 0.30, '超宽画幅的月门仍然偏小。'
    assert 0.28 < result['ceiling_front_fraction'] < 0.34, '前檐位置没有留出足够的藻井。'
    assert 0.20 < result['floor_foreground_fraction'] < 0.24, '石坪前景比例异常。'
    assert 0.045 < result['person_height_fraction'] < 0.07, '人物缺少合适的尺度参照。'
    assert 0.20 < wide['ceiling_front_fraction'] < 0.26, '超宽画幅裁掉了过多藻井。'
    assert abs(wide['floor_foreground_fraction'] - reference['floor_foreground_fraction']) < 1e-6, '宽屏收紧改变了地坪锚点。'
    result['passed'] = True
    return result


def preview(camera):
    """
    仅渲染低采样的 Blender 构图预览，不把预览灯光或画幅设置写回正式工程。
    宽屏投影按网页的扩幅规则换算，避免离线预览悄悄裁掉两侧柱列。
    """
    scene = bpy.context.scene
    for ob in scene.objects:
        if ob.type == 'LIGHT':
            ob.hide_render = True
    world = bpy.data.worlds.new('构图检查天空')
    world.use_nodes = True
    world.node_tree.nodes['Background'].inputs[0].default_value = (0.31, 0.39, 0.49, 1)
    world.node_tree.nodes['Background'].inputs[1].default_value = 0.65
    scene.world = world
    light = bpy.data.lights.new('构图检查日光', 'SUN')
    light.energy, light.angle, light.color = 3.0, 0.08, (1, 0.88, 0.73)
    sun = bpy.data.objects.new(light.name, light)
    scene.collection.objects.link(sun)
    sun.rotation_euler = Vector((-650, 650, -430)).to_track_quat('-Z', 'Y').to_euler()
    camera.data.sensor_fit = 'VERTICAL'
    camera.data.sensor_height = 27
    camera.data.shift_x *= 4 / 3
    camera.data.shift_y *= 4 / 3
    scene.timeline_markers.clear()
    scene.camera = camera
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 16
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 4
    scene.render.use_border = False
    scene.render.use_compositing = False
    scene.render.use_sequencer = False
    scene.render.resolution_x, scene.render.resolution_y = 960, 640
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.film_transparent = False
    scene.view_settings.view_transform = 'AgX'
    scene.view_settings.exposure = 0
    # 预览采用参考图三比二画幅，宽屏适配另由几何投影核验覆盖。
    # 文件名跟随构图版本，避免覆盖此前留存的比较图。
    scene.render.filepath = str(ROOT / 'qa' / f'{REVISION}-preview.png')
    bpy.ops.render.render(write_still=True)


def main():
    """
    保存首次修改前的工程、机位和人物资源，并让全量重建与局部构图更新共用同一入口。
    核验模式只读回实际工程；预览模式不保存工程，也不覆盖正式 JSON 或 GLB。
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preview', action='store_true')
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
    path = ROOT / 'assets' / 'cameras.json'
    document = json.loads(path.read_text(encoding='utf-8'))
    original = document['cameras'][3]
    camera = bpy.data.objects[original['name']]
    if not args.preview and not args.verify:
        # 新版本单独保留修改前的工程和相机记录，以便与本轮空间调整一起复核。
        # 首次备份只创建一次，重复运行不会把旧状态替换成已经修改的结果。
        backup = ROOT / 'qa' / f'before-{REVISION}'
        backup.mkdir(parents=True, exist_ok=True)
        for source in (Path(bpy.data.filepath), path, ROOT / 'assets' / 'characters.glb', ROOT / 'assets' / 'manifest.json'):
            if not (backup / source.name).exists():
                shutil.copy2(source, backup / source.name)
    if not args.verify:
        configure(camera)
    report = measure(camera)
    record = camera_record(camera, original)
    if args.verify:
        for key in ('world_matrix', 'projection_matrix', 'position', 'direction', 'up', 'quaternion_xyzw'):
            assert max(abs(a - b) for a, b in zip(record[key], original[key])) < 1e-6, '导出的相机字段与工程不一致：' + key
        assert original.get('composition_revision') == REVISION, '正式相机尚未更新。'
        # 宽屏取景也属于相机正式数据，核验时同时检查网页需要的全部参数。
        # 数值来自实际地坪投影，不能仅核验焦距后遗漏镜头锚点。
        for key, value in record['composition_framing'].items():
            assert abs(original.get('composition_framing', {}).get(key, math.inf) - value) < 1e-6, '导出的宽屏构图参数与工程不一致：' + key
    elif args.preview:
        write_json(ROOT / 'qa' / f'{REVISION}-preview.json', report)
        preview(camera)
        return
    else:
        document['cameras'][3] = record
        bpy.context.scene['殿内构图版本'] = REVISION
        bpy.context.scene['殿内构图参数'] = json.dumps(dict(eye=EYE, lens_mm=LENS_MM, shift_y=SHIFT_Y, person_xy=PERSON_XY), ensure_ascii=False)
        save_web_blend(ROOT / 'HeavenlyPalace_WebAssets_v01.blend')
        write_json(path, document)
    report['camera_file_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    # 核验报告与构图版本保持一致，旧报告继续保留供前后比较。
    # 正式资源校验值用于确认网页实际加载了本次生成的相机数据。
    write_json(ROOT / 'qa' / f'{REVISION}-verification.json', report)
    print('HALL_VIEW_COMPLETE', json.dumps(report, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
