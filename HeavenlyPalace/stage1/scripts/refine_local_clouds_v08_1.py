"""
根据外部固定机位检查收窄低云舌，避免大块白云侵入广场画面。
移除本轮新增且已不需要的遮挡云，只保留入口檐后极小范围云团。
"""
import bpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
scene = bpy.context.scene
col = bpy.data.collections['18_V08_可渲染云海与水雾']
for ob in list(col.objects):
    if ob.name.startswith('V08_1_西前崖外云团_'):
        bpy.data.objects.remove(ob, do_unlink=True)
    elif ob.name.startswith('V08_1_入口后侧低云舌_'):
        i = int(ob.name[-2:])
        if i == 0:
            bpy.data.objects.remove(ob, do_unlink=True)
            continue
        ob.location = (-145 + i * 25, -169, 33.5)
        ob.scale = (30, 9, 9)
mat = bpy.data.materials['V08_1_入口后侧云舌_局部体积']
vol = mat.node_tree.nodes['真实散射云雾']
vol.inputs['Density'].links[0].from_node.inputs[1].default_value = 1.8
# 沿用第八版云材质的密度比例环境补偿，防止入口投影使小云团变成黑块。
# 空密度区域同时保持零发光，补偿在所有机位生效且不影响室内曝光。
for link in list(vol.inputs['Emission Strength'].links):
    mat.node_tree.links.remove(link)
compensation = mat.node_tree.nodes.new('ShaderNodeMath')
compensation.name = '低云与远云一致的密度比例环境补偿'
compensation.operation = 'MULTIPLY'
compensation.inputs[1].default_value = .15
mat.node_tree.links.new(vol.inputs['Density'].links[0].from_socket, compensation.inputs[0])
mat.node_tree.links.new(compensation.outputs[0], vol.inputs['Emission Strength'])
scene.frame_set(4)
scene.camera = bpy.data.objects['CAM_04_殿内望云_v08_1']
scene.cycles.samples = 64
scene.render.resolution_percentage = 100
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT / 'HeavenlyPalace_Lookdev_v08_1.blend'), compress=True)
scene.cycles.samples = 16
scene.render.resolution_percentage = 40
scene.render.filepath = str(ROOT / 'v08_1' / 'qa' / 'J_refined_clouds.png')
bpy.ops.render.render(write_still=True)
