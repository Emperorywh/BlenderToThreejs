"""
把整套南向云海统一移远并按比例展开，保留云层之间的遮挡与起伏关系。
按相同倍率降低体积密度以维持光学厚度，云海真实参与所有机位渲染。
"""
import bpy
import json
from pathlib import Path
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / 'v08_1' / 'qa'
scene = bpy.context.scene
records = json.loads((QA / 'adjustments.json').read_text(encoding='utf-8'))['clouds']
origin = Vector((24, 365, 37.65))
factor = 2.8
materials = {}
for record in records:
    ob = bpy.data.objects[record['name']]
    ob.location = origin + (Vector(record['location']) - origin) * factor
    ob.scale = Vector(record['scale']) * factor
    source = ob.material_slots[0].material
    if source.name not in materials:
        material = source.copy()
        material.name = 'V08_1_远移云海_' + source.name
        volume = next(n for n in material.node_tree.nodes if n.type == 'PRINCIPLED_VOLUME')
        density = volume.inputs['Density'].links[0].from_node
        density.inputs[1].default_value /= factor
        materials[source.name] = material
    ob.material_slots[0].link = 'OBJECT'
    ob.material_slots[0].material = materials[source.name]
cam = bpy.data.objects['CAM_04_殿内望云_v08_1']
cam.data.clip_end = 100000
scene.frame_set(4)
scene.camera = cam
scene.cycles.samples = 64
scene.render.resolution_percentage = 100
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT / 'HeavenlyPalace_Lookdev_v08_1.blend'), compress=True)
scene.render.resolution_percentage = 40
scene.cycles.samples = 16
for frame, name in [(4, 'L_depth_preserved_interior'), (2, 'L_depth_preserved_front')]:
    scene.frame_set(frame)
    scene.camera = next(m.camera for m in scene.timeline_markers if m.frame == frame)
    scene.render.filepath = str(QA / (name + '.png'))
    bpy.ops.render.render(write_still=True)
