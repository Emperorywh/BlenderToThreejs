"""
从已保存的第八版增量调整殿内机位与南向远景，不重建建筑。
所有变化均为固定三维空间布置，不按相机切换对象可见性。
"""
import bpy
import json
import math
import random
import sys
from pathlib import Path
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'v08_1'
QA = OUT / 'qa'
QA.mkdir(parents=True, exist_ok=True)
scene = bpy.context.scene
old = bpy.data.objects['CAM_04_殿内月门_眼高1点65米_35mm']
cam = old.copy()
cam.data = old.data.copy()
cam.name = 'CAM_04_殿内望云_v08_1'
old.users_collection[0].objects.link(cam)
# 渲染启动时 Blender 会重新应用当前帧的相机标记，因此明确绑定新机位。
# 原相机保留在场景中供对照，前三帧的固定机位绑定不变。
next(m for m in scene.timeline_markers if m.frame == 4).camera = cam
report = {'mountains': [], 'clouds': [], 'candidates': []}

# 南向山峰按整个主峰组平移至东西两翼，肩峰使用完全相同的位移。
# 原有承托山体、其他方向远山和全部建筑始终保持原始位置及形状。
col = bpy.data.collections['17_V08_层叠远山']
for ob in list(col.objects):
    if '肩峰' in ob.name:
        continue
    points = [ob.matrix_world @ Vector(v) for v in ob.bound_box]
    center = sum(points, Vector()) / 8
    radius = max((p - center).length for p in points)
    if center.y < -600 and abs(center.x) < (339 - center.y) * .95 + radius:
        sign = 1 if center.x >= 0 else -1
        dx = sign * ((339 - center.y) * 1.3 + radius + 300) - center.x
        for part in col.objects:
            if part.name == ob.name or part.name.startswith(ob.name + '_肩峰'):
                part.location.x += dx
                report['mountains'].append({'name': part.name, 'translation': [dx, 0, 0]})

# 重排已有南向云团形成多段纵深，再补充不同尺度的体积云团。
# 云容器远离广场和殿内；材质沿用第八版散射结构与统一日照。
cloudcol = bpy.data.collections['18_V08_可渲染云海与水雾']
material = bpy.data.materials['V08_云海_分形体积云'].copy()
material.name = 'V08_1_南向积云_细节散射'
material.node_tree.nodes['云团翻滚层次'].inputs['Scale'].default_value = 8
material.node_tree.nodes['云团翻滚层次'].inputs['Detail'].default_value = 3.2
data = next(iter(cloudcol.objects)).data
rng = random.Random(8109)
southern = sorted([o for o in cloudcol.objects if o.name.startswith('V08_南向云域_')], key=lambda o: o.name)
for i, ob in enumerate(southern):
    if '低位连续云床' in ob.name:
        ob.location = (0, -3600, -160)
        ob.scale = (4700, 2800, 370)
        ob.rotation_euler.z = 0
    elif '远天薄云' in ob.name:
        ob.location.z -= 1250
    else:
        ob.location.z = 80 + (-ob.location.y - 1700) * .18 + rng.uniform(-50, 50)
        ob.scale.z *= .72
    report['clouds'].append({'name': ob.name, 'location': list(ob.location), 'scale': list(ob.scale)})
for layer, (distance, height, size, count) in enumerate([(800, 30, 150, 19), (1250, 110, 190, 21), (1900, 230, 230, 25), (2900, 480, 280, 29), (4300, 830, 340, 33), (6200, 1320, 400, 35)]):
    for i in range(count):
        ob = bpy.data.objects.new(f'V08_1_南向积云_{layer:02}_{i:02}', data)
        cloudcol.objects.link(ob)
        ob.location = ((i - (count - 1) / 2) * size * 1.18 + rng.uniform(-size * .3, size * .3), -distance + rng.uniform(-size * .6, size * .6), height + rng.uniform(-size * .20, size * .22))
        ob.scale = (size * rng.uniform(.8, 1.25), size * rng.uniform(.8, 1.3), size * rng.uniform(.45, .75))
        ob.rotation_euler.z = rng.uniform(-1, 1)
        ob.material_slots[0].link = 'OBJECT'
        ob.material_slots[0].material = material
        report['clouds'].append({'name': ob.name, 'location': list(ob.location), 'scale': list(ob.scale)})


def configure_camera(x, y, lens, target_z, shift):
    """相机高度依据原殿内地面标高三十六米设置。
    只移动相机和改变镜头，不通过缩放建筑与人物获取构图。
    """
    cam.location = (x, y, 37.65)
    cam.rotation_euler = (Vector((0, 240, target_z)) - cam.location).to_track_quat('-Z', 'Y').to_euler()
    cam.data.lens = lens
    cam.data.shift_y = shift
    cam.data.shift_x = 0
    scene.camera = cam
    bpy.context.view_layer.update()


candidates = [('A_center', 0, 315, 28, 55, 0), ('B_offset', 18, 315, 28, 55, 0), ('C_forward', 16, 295, 22, 55, 0), ('D_close', 12, 280, 18, 54, 0)]
scene.frame_set(4)
scene.render.resolution_x = 1800
scene.render.resolution_y = 1350
scene.render.resolution_percentage = 33
scene.cycles.samples = 12
for label, x, y, lens, z, shift in candidates:
    configure_camera(x, y, lens, z, shift)
    # 将原有近处人形整体平移到新相机前方，保持全部部件相对位置。
    # 两个人形仍留在门前作远处参照，人物高度及网格完全不变。
    for ob in scene.objects:
        if ob.name.startswith('尺度人形_01_'):
            base = next(r for r in json.loads((QA / 'baseline_scene.json').read_text(encoding='utf-8'))['objects'] if r['name'] == ob.name)
            ob.location = Vector(base['location']) + Vector((x - 3, y - 340, 0))
    scene.render.filepath = str(QA / (label + '.png'))
    report['candidates'].append({'label': label, 'position': list(cam.location), 'lens': lens, 'target_z': z, 'shift': shift})
    bpy.ops.render.render(write_still=True)
    print('CANDIDATE_READY', label, flush=True)
(QA / 'adjustments.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
bpy.ops.wm.save_as_mainfile(filepath=str(QA / 'candidate_scene.blend'), compress=True)
