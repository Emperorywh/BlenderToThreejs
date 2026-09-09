"""
读取主殿柱网的投影与局部剖面，精确确定前景样板所在的原构件。
只输出数据，不修改工程或原有机位。
"""
import bpy
import json
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector
scene = bpy.context.scene
cam = bpy.data.objects['CAM_04_殿内望云_v08_1']
for ob in scene.objects:
    if ob.name.startswith('主殿巨柱') and ob.name.endswith('_柱身'):
        p = world_to_camera_view(scene, cam, Vector((ob.location.x, ob.location.y, 44)))
        print(ob.name, '投影', tuple(round(v,3) for v in p), '剖面', sorted(set((round(v.co.z,4),round((v.co.x**2+v.co.y**2)**.5,4)) for v in ob.data.vertices)), '变换', list(ob.scale), flush=True)
print('纹理资源', [(i.name,i.filepath,bool(i.packed_file)) for i in bpy.data.images], flush=True)
print('渲染', scene.cycles.samples, scene.view_settings.view_transform,scene.view_settings.look, flush=True)
