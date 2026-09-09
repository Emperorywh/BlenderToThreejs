"""
把松散雾层收束为有边界的翻涌云团，保留低位布局与统一灯光。
复用正式材质构建函数和共享体积容器，控制新增近云数量与总体网格开销。
"""
import bpy
import ast
import math
import random
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
tree=ast.parse((ROOT/'scripts'/'lookdev_materials_v08.py').read_text(encoding='utf-8'))
needed=['node','link','coords','texnoise','calc','cloud_material']
defs=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in needed]
origin=bpy.data.objects['V08_米制纹理原点_一单位一米']
exec(compile(ast.Module(body=defs,type_ignores=[]),'云体积构建函数','exec'),globals())
scene=bpy.context.scene
col=bpy.data.collections['18_V08_可渲染云海与水雾']
oldcloud=bpy.data.materials['V08_云海_分形体积云']
oldmist=bpy.data.materials['V08_瀑布_稀薄局部水雾']
oldcloud.name='历史_雾状云海材质'
oldmist.name='历史_雾状水雾材质'
cloudmat=cloud_material('云海_分形体积云',.052,5)
mistmat=cloud_material('瀑布_稀薄局部水雾',.0018,4)
for ob in list(col.objects):
    for slot in ob.material_slots:
        old=slot.material
        slot.link='OBJECT'
        slot.material=mistmat if old==oldmist else cloudmat
data=next(iter(col.objects)).data
rng=random.Random(8975)
for i in range(20):
    a=math.tau*i/20
    distance=660 if i%2 else 450
    ob=bpy.data.objects.new(f'V08_近景翻涌云峰_{i:02}',data)
    col.objects.link(ob)
    ob.location=(distance*math.cos(a),distance*math.sin(a),-260+rng.uniform(-25,35))
    ob.scale=(rng.uniform(80,140),rng.uniform(75,130),rng.uniform(70,125))
    ob.material_slots[0].link='OBJECT'
    ob.material_slots[0].material=cloudmat
scene.cycles.samples=48
scene.render.resolution_percentage=100
scene.frame_set(1)
scene.camera=next(m.camera for m in scene.timeline_markers if m.frame==1)
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'HeavenlyPalace_Lookdev_v08.blend'),compress=True)
scene.render.resolution_percentage=40
scene.cycles.samples=16
scene.render.filepath=str(ROOT/'v08'/'qa'/'sample_01_oblique.png')
bpy.ops.render.render(write_still=True)
print('V08_CUMULUS_PREVIEW_READY',flush=True)
