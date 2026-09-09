"""
只读对照第八版与增量版，逐对象验证建筑、承托、灯光和原相机保留。
额外记录人物高度、云域边界和统一可见性，所有结果写入验收报告。
"""
import bpy
import ast
import json
import struct
import hashlib
from pathlib import Path
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / 'v08_1' / 'qa'
source_path = ROOT / 'HeavenlyPalace_Lookdev_v08.blend'
candidate = ROOT / 'HeavenlyPalace_Lookdev_v08_1.blend'
module = ast.parse((ROOT / 'scripts' / 'audit_architecture_v06.py').read_text(encoding='utf-8'))
exec(compile(ast.Module(body=[n for n in module.body if isinstance(n, ast.FunctionDef) and n.name in ['signature', 'camera_record']], type_ignores=[]), '原有只读签名函数', 'exec'), globals())


def capture():
    """固定场景内容的摘要包含几何、变换、材质、修改器和灯光。
    允许变化的范围仅为南向环境、新相机及整体平移的第一个人形。
    """
    scene = bpy.context.scene
    excluded = {o.name for c in bpy.data.collections if c.name.startswith(('17_', '18_')) for o in c.all_objects}
    return {'protected': {o.name: signature(o) for o in scene.objects if o.name not in excluded and not o.name.startswith(('CAM_04_殿内望云', '尺度人形_01_'))}, 'cameras': {o.name: camera_record(o) for o in scene.objects if o.type == 'CAMERA' and not o.name.startswith('CAM_04_殿内望云')}, 'visibility': {o.name: [o.hide_render, o.hide_viewport, o.visible_camera, o.visible_shadow] for o in scene.objects}, 'collections': {c.name: c.hide_render for c in bpy.data.collections}, 'markers': {m.frame: m.camera.name for m in scene.timeline_markers if m.camera}, 'human_geometry': {o.name: signature(o, False) for o in scene.objects if o.name.startswith('尺度人形_01_')}, 'world': str([(n.name, [(s.name, str(list(s.default_value)) if hasattr(s.default_value, '__len__') and not isinstance(s.default_value, str) else str(s.default_value)) for s in n.inputs if hasattr(s, 'default_value')]) for n in scene.world.node_tree.nodes]), 'view': [scene.view_settings.view_transform, scene.view_settings.look, scene.view_settings.exposure, scene.view_settings.gamma]}


bpy.ops.wm.open_mainfile(filepath=str(source_path))
before = capture()
source_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
bpy.ops.wm.open_mainfile(filepath=str(candidate))
after = capture()
scene = bpy.context.scene
cam = scene.objects['CAM_04_殿内望云_v08_1']
changed = [n for n, v in before['protected'].items() if after['protected'].get(n) != v]
visibility = [n for n, v in before['visibility'].items() if after['visibility'].get(n) != v]
cloud_ground = []
cloud_upper = []
for ob in bpy.data.collections['18_V08_可渲染云海与水雾'].objects:
    points = [ob.matrix_world @ Vector(p) for p in ob.bound_box]
    low = [min(p[i] for p in points) for i in range(3)]
    high = [max(p[i] for p in points) for i in range(3)]
    if low[0] < 155 and high[0] > -155 and low[1] < 160 and high[1] > -175:
        if low[2] < 2 and high[2] > 0:
            cloud_ground.append(ob.name)
        elif low[2] > 2 and high[2] > 0:
            cloud_upper.append({'name': ob.name, 'bounds': [low, high]})
people = []
for number in ['01', '02', '03']:
    points = [ob.matrix_world @ Vector(p) for ob in scene.objects if ob.name.startswith('尺度人形_' + number + '_') for p in ob.bound_box]
    people.append({'number': number, 'height': max(p.z for p in points) - min(p.z for p in points), 'foot_z': min(p.z for p in points)})
report = {'source_sha256': source_hash, 'protected_count': len(before['protected']), 'changed_protected_objects': changed, 'original_cameras_preserved': before['cameras'] == after['cameras'], 'fixed_markers_preserved': all(before['markers'][i] == after['markers'][i] for i in [1, 2, 3]), 'changed_visibility': visibility, 'collection_visibility_preserved': before['collections'] == after['collections'], 'world_preserved': before['world'] == after['world'], 'exposure_preserved': before['view'] == after['view'], 'new_camera': {'name': cam.name, 'position': list(cam.location), 'rotation_radians': list(cam.rotation_euler), 'lens_mm': cam.data.lens, 'shift': [cam.data.shift_x, cam.data.shift_y], 'eye_height': cam.location.z - 36}, 'people': people, 'clouds_touching_plaza_walking_height': cloud_ground, 'clouds_above_front_plaza': cloud_upper, 'moon_geometry_unchanged': 'V05_月门通厚石圈_净径44米' not in changed, 'source_support_and_route_audit': json.loads((ROOT / 'v08' / 'qa' / 'audit_v08.json').read_text(encoding='utf-8'))['passed']}
report['preservation_passed'] = not changed and not visibility and report['original_cameras_preserved'] and report['fixed_markers_preserved'] and report['collection_visibility_preserved'] and report['world_preserved'] and not cloud_ground
(QA / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print('V08_1_VERIFIED', json.dumps(report, ensure_ascii=False), flush=True)
