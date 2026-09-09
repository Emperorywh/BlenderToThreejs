"""
确定殿内望云机位，并用入口后侧的局部立体云舌衔接远方云海。
建筑、主岛、人物尺度及原相机全部保留，另存增量版本用于统一渲染。
"""
import bpy
import json
from pathlib import Path
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'v08_1'
QA = OUT / 'qa'
scene = bpy.context.scene
cam = bpy.data.objects['CAM_04_殿内望云_v08_1']
scene.frame_set(4)
cam.location = (24, 365, 37.65)
cam.rotation_euler = (Vector((0, 240, 55)) - cam.location).to_track_quat('-Z', 'Y').to_euler()
cam.data.lens = 45
cam.data.shift_x = 0
cam.data.shift_y = 0
baseline = {r['name']: r for r in json.loads((QA / 'baseline_scene.json').read_text(encoding='utf-8'))['objects']}
for ob in scene.objects:
    if ob.name.startswith('尺度人形_01_'):
        ob.location = Vector(baseline[ob.name]['location']) + Vector((20, 25, 0))

# 云舌位于入口屋顶后方的高处，与广场地面保留明确垂直距离。
# 仅补齐极低角度的屋檐视线，不把雾布置在月门、柱础或人物周围。
col = bpy.data.collections['18_V08_可渲染云海与水雾']
data = next(iter(col.objects)).data
mat = bpy.data.materials['V08_1_南向积云_细节散射'].copy()
mat.name = 'V08_1_入口后侧云舌_局部体积'
vol = mat.node_tree.nodes['真实散射云雾']
vol.inputs['Density'].links[0].from_node.inputs[1].default_value = .55
vol.inputs['Color'].default_value = (.95, .97, 1, 1)
local = []
for i, x in enumerate([-145, -120, -95, -70, -45, -20]):
    ob = bpy.data.objects.new(f'V08_1_入口后侧低云舌_{i:02}', data)
    col.objects.link(ob)
    ob.location = (x, -150 + (i % 2) * 7, 31.5 + (i % 3) * .7)
    ob.scale = (32, 24, 8)
    ob.material_slots[0].link = 'OBJECT'
    ob.material_slots[0].material = mat
    local.append({'name': ob.name, 'location': list(ob.location), 'scale': list(ob.scale)})

# 殿侧远处的树冠通过悬崖外部局部云团自然遮挡，根盘与树体不动。
# 云团位于广场边界以外，同样参与全部相机的散射、遮挡与阴影。
for i, (loc, scale) in enumerate([((-220, -115, 24), (55, 45, 28)), ((-275, -180, 35), (75, 55, 32))]):
    ob = bpy.data.objects.new(f'V08_1_西前崖外云团_{i:02}', data)
    col.objects.link(ob)
    ob.location, ob.scale = loc, scale
    ob.material_slots[0].link = 'OBJECT'
    ob.material_slots[0].material = mat
    local.append({'name': ob.name, 'location': list(ob.location), 'scale': list(ob.scale)})
scene.camera = cam
bpy.context.view_layer.update()
scene.render.resolution_percentage = 40
scene.cycles.samples = 20
scene.render.filepath = str(QA / 'H_cloud_transition.png')
bpy.ops.render.render(write_still=True)
(QA / 'local_clouds.json').write_text(json.dumps(local, ensure_ascii=False, indent=2), encoding='utf-8')
scene.render.resolution_percentage = 100
scene.cycles.samples = 64
scene.cycles.adaptive_threshold = .025
scene.render.resolution_x = 1800
scene.render.resolution_y = 1350
scene['阶段'] = 'V8.1 殿内望云增量构图'
scene['V08_1说明'] = '全场共用固定三维场景；帧4使用新版殿内相机；原殿内相机保留'
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT / 'HeavenlyPalace_Lookdev_v08_1.blend'), compress=True)
