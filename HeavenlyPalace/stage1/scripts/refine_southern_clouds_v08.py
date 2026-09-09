"""
重排南向远景云域，使用高差不同的小云团覆盖远山山脚并打破水平云板。
这是场景中的固定空间布置，不读取当前相机来隐藏或切换任何对象。
"""
import bpy
import random
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
scene=bpy.context.scene
col=bpy.data.collections['18_V08_可渲染云海与水雾']
cloudmat=bpy.data.materials['V08_云海_分形体积云']
data=next(iter(col.objects)).data
for ob in list(col.objects):
    if ob.location.y<-2100:
        bpy.data.objects.remove(ob,do_unlink=True)
thin=cloudmat.copy()
thin.name='V08_南天高云_轻薄体积'
vol=next(n for n in thin.node_tree.nodes if n.type=='PRINCIPLED_VOLUME')
vol.inputs['Density'].links[0].from_node.inputs[1].default_value=.012
rng=random.Random(8998)


# 大云床只补齐低处远景，起伏云峰沿不同纵深错开，避免远山露出截平山脚。
# 高云保留较大的蓝天间隙，月门本身和近处建筑周围继续保持无云容器。
def cloud(name,loc,scale,mat=cloudmat):
    ob=bpy.data.objects.new('V08_南向云域_'+name,data)
    col.objects.link(ob)
    ob.location=loc
    ob.scale=scale
    ob.rotation_euler.z=rng.uniform(-.8,.8)
    ob.material_slots[0].link='OBJECT'
    ob.material_slots[0].material=mat
    return ob


bed=cloud('低位连续云床',(0,-4200,-80),(3350,2400,520))
bed.rotation_euler.z=0
for layer,(y,z,count,spacing) in enumerate([(-2800,255,12,330),(-4300,565,13,430),(-6000,880,12,610)]):
    for i in range(count):
        x=(i-(count-1)/2)*spacing+rng.uniform(-110,110)
        cloud(f'错落云峰_{layer}_{i}',(x,y+rng.uniform(-240,240),z+rng.uniform(-165,135)),
              (rng.uniform(240,410),rng.uniform(230,420),rng.uniform(160,320)))
for i in range(8):
    cloud(f'远天薄云_{i}',(-2300+i*680,-7100+rng.uniform(-350,150),2450+rng.uniform(-240,180)),
          (rng.uniform(400,700),rng.uniform(290,530),rng.uniform(130,250)),thin)
scene.frame_set(1)
scene.camera=next(m.camera for m in scene.timeline_markers if m.frame==1)
scene.render.resolution_percentage=100
scene.cycles.samples=48
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'HeavenlyPalace_Lookdev_v08.blend'),compress=True)
scene.frame_set(4)
scene.camera=next(m.camera for m in scene.timeline_markers if m.frame==4)
scene.render.resolution_percentage=40
scene.cycles.samples=20
scene.render.filepath=str(ROOT/'v08'/'qa'/'sample_04_interior.png')
bpy.ops.render.render(write_still=True)
print('V08_SOUTHERN_CLOUDS_READY',flush=True)
