"""
把入口檐后五团局部云改为真实闭合云体，消除体积容器边缘的矩形漏缝。
密度保持明确下限，云体轮廓由三维网格决定，不依赖相机遮罩或图像修补。
"""
import bpy
import bmesh
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
scene = bpy.context.scene
mesh = bpy.data.meshes.new('V08_1_局部云舌_闭合椭球容器')
bm = bmesh.new()
bmesh.ops.create_icosphere(bm, subdivisions=3, radius=1)
bm.to_mesh(mesh)
bm.free()
mat = bpy.data.materials.new('V08_1_局部云舌_连续保底散射')
mat.use_nodes = True
mat.node_tree.nodes.clear()
out = mat.node_tree.nodes.new('ShaderNodeOutputMaterial')
volume = mat.node_tree.nodes.new('ShaderNodeVolumePrincipled')
volume.inputs['Density'].default_value = 1.5
volume.inputs['Color'].default_value = (.95, .97, 1, 1)
volume.inputs['Anisotropy'].default_value = .22
volume.inputs['Emission Color'].default_value = (.76, .84, 1, 1)
volume.inputs['Emission Strength'].default_value = .225
mat.node_tree.links.new(volume.outputs['Volume'], out.inputs['Volume'])
mat.cycles.volume_step_rate = .1
mesh.materials.append(mat)
for ob in bpy.data.collections['18_V08_可渲染云海与水雾'].objects:
    if ob.name.startswith('V08_1_入口后侧低云舌_'):
        ob.data = mesh
        ob.material_slots[0].link = 'OBJECT'
        ob.material_slots[0].material = mat
scene.frame_set(4)
scene.camera = bpy.data.objects['CAM_04_殿内望云_v08_1']
scene.render.use_border = False
scene.render.use_crop_to_border = False
scene.render.resolution_percentage = 100
scene.cycles.samples = 64
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT / 'HeavenlyPalace_Lookdev_v08_1.blend'), compress=True)
# 先对正式分辨率下的门洞底边做局部真实渲染，快速检查漏缝。
# 裁剪只用于诊断输出；保存的工程仍为完整四比三画幅。
scene.cycles.samples = 24
scene.render.use_border = True
scene.render.use_crop_to_border = True
scene.render.border_min_x = .46
scene.render.border_max_x = .87
scene.render.border_min_y = .22
scene.render.border_max_y = .32
scene.render.filepath = str(ROOT / 'v08_1' / 'qa' / 'M_roof_detail.png')
bpy.ops.render.render(write_still=True)
