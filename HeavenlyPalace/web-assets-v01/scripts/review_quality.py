"""
核验主体升级的实体开口、材质坐标与网格数值，并输出一张 Blender 离线资产预览。
本脚本不启动浏览器、不操作网页，预览只用于检查模型本身的穿插和表面效果。
"""
import bpy
import json
import math
import sys
import numpy as np
from pathlib import Path
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
SCENE = bpy.context.scene
# 质量流程可能在主殿空间调整之前或之后执行，因此使用实际场景版本选择目标。
# 月门名称保持历史兼容，净径与中心均按几何和实体元数据重新核对。
sys.path.insert(0, str(ROOT / 'scripts'))
from hall_space import GATE_CENTER_Z, GATE_RADIUS, space_active


def verify():
    """
    对圆门的内部和实体石圈分别发射射线，确认开孔真正贯通。
    同时检查无效坐标、缺失贴图和负缩放，阻止损坏网格进入网页资源。
    """
    report = {'revision': SCENE.get('主体资产质量版本'), 'invalid_meshes': [], 'missing_textures': []}
    report['entrance_open'] = []
    gate = [bpy.data.objects['Q02_前入口月门厚墙'], bpy.data.objects['Q02_前入口月门_二十八米通厚石圈']]
    for x, z in ((0, 1), (0, 14), (0, 27), (-13, 14), (13, 14)):
        blocked = any(ob.ray_cast(Vector((x, -208, z)), Vector((0, 1, 0)), distance=30)[0] for ob in gate)
        report['entrance_open'].append(not blocked)
    report['stone_ring_solid'] = any(ob.ray_cast(Vector((15, -208, 14)), Vector((0, 1, 0)), distance=30)[0] for ob in gate)
    moon = bpy.data.objects['V05_月门通厚石圈_净径44米']
    center=float(moon.get('门洞中心标高_米',GATE_CENTER_Z if space_active() else 56.0))
    expected_diameter=2*GATE_RADIUS if space_active() else 44.0
    report['moon_diameter_m'] = 2 * min(math.hypot(p.x, p.z - center) for p in (moon.matrix_world @ v.co for v in moon.data.vertices))
    report['moon_expected_diameter_m']=expected_diameter
    report['moon_recorded_diameter_m']=float(moon.get('净开口直径_米',expected_diameter))
    unique = {ob.data for ob in SCENE.objects if ob.type == 'MESH'}
    report['unique_triangles'] = 0
    for data in unique:
        data.calc_loop_triangles()
        report['unique_triangles'] += len(data.loop_triangles)
        coords = np.empty(len(data.vertices) * 3, dtype=np.float32)
        data.vertices.foreach_get('co', coords)
        invalid = not np.isfinite(coords).all() or not data.uv_layers or any(m is None for m in data.materials)
        for uv in data.uv_layers:
            values = np.empty(len(uv.data) * 2, dtype=np.float32)
            uv.data.foreach_get('uv', values)
            invalid |= not np.isfinite(values).all()
        if invalid:
            report['invalid_meshes'].append(data.name)
    # 按实际面的材质索引核验资源，空备用槽不参与网页导出。
    # 布尔构件保留的历史材质槽可能仍有引用，但没有任何面使用这些材质。
    for mat in {data.materials[i] for data in unique for i in {p.material_index for p in data.polygons}}:
        if 'web_spec' not in mat:
            continue
        for file in json.loads(mat['web_spec'])['files'].values():
            if not (ROOT / 'assets' / 'textures' / file).is_file():
                report['missing_textures'].append(file)
    report['negative_scale'] = [ob.name for ob in SCENE.objects if ob.type == 'MESH' and ob.matrix_world.determinant() <= 0]
    report['passed'] = (report['revision'] == 'q02' and all(report['entrance_open']) and report['stone_ring_solid']
                        and abs(report['moon_diameter_m'] - expected_diameter) < .002
                        and abs(report['moon_recorded_diameter_m'] - expected_diameter) < .002 and not report['invalid_meshes']
                        and not report['missing_textures'] and not report['negative_scale'])
    (ROOT / 'qa' / 'quality-verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False), flush=True)
    assert report['passed'], '主体资产核验未通过，请检查质量报告。'


def render():
    """
    使用独立的暖色日光和柔和天空照明查看建筑及岩壁细节。
    临时灯光、机位和渲染设置只在内存中使用，不写回交付工程。
    """
    for ob in list(SCENE.objects):
        if ob.type == 'LIGHT':
            bpy.data.objects.remove(ob, do_unlink=True)
        elif ob.type == 'MESH' and any(c.name.startswith(('10', '17_')) for c in ob.users_collection):
            ob.hide_render = True
    world = bpy.data.worlds.new('质量检查柔和天空')
    world.use_nodes = True
    world.node_tree.nodes['Background'].inputs[0].default_value = (.31, .39, .49, 1)
    world.node_tree.nodes['Background'].inputs[1].default_value = .65
    SCENE.world = world
    light = bpy.data.lights.new('质量检查日光', 'SUN')
    light.energy = 3.0
    light.angle = .08
    light.color = (1, .88, .73)
    sun = bpy.data.objects.new('质量检查日光', light)
    SCENE.collection.objects.link(sun)
    sun.rotation_euler = Vector((520, 650, -790)).to_track_quat('-Z', 'Y').to_euler()
    cam_data = bpy.data.cameras.new('质量检查相机')
    cam = bpy.data.objects.new('质量检查相机', cam_data)
    SCENE.collection.objects.link(cam)
    detail = '--detail' in sys.argv
    cam.location = (220, 70, 119) if detail else (700, -1100, 650)
    target = Vector((0, 285, 79) if detail else (0, 70, -30))
    cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()
    cam_data.lens = 36 if detail else 53
    cam_data.clip_end = 10000
    # 原场景的时间线会在渲染开始时重新绑定正式机位，检查时移除这些临时绑定。
    # 清除裁切与合成设置，保证输出完整地反映指定资产机位。
    SCENE.timeline_markers.clear()
    SCENE.camera = cam
    SCENE.render.use_border = False
    SCENE.render.use_compositing = False
    SCENE.render.use_sequencer = False
    SCENE.render.engine = 'CYCLES'
    SCENE.cycles.samples = 24
    SCENE.cycles.use_denoising = True
    SCENE.render.resolution_x = 1200
    SCENE.render.resolution_y = 900
    SCENE.render.resolution_percentage = 100
    SCENE.render.image_settings.file_format = 'PNG'
    SCENE.render.film_transparent = False
    SCENE.view_settings.view_transform = 'AgX'
    SCENE.view_settings.exposure = 0
    SCENE.render.filepath = str(ROOT / 'qa' / ('quality-hall.png' if detail else 'quality-overview.png'))
    bpy.ops.render.render(write_still=True)


verify()
if '--render' in sys.argv:
    render()
