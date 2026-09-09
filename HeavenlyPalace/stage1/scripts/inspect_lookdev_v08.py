"""
只读记录第七版建筑、相机、材质和环境对象，为第八版建立可核验的基准。
此脚本只输出检查资料及低分辨率原始预览，不保存或覆盖第七版工程。
"""
import bpy
import json
import hashlib
from pathlib import Path
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'v08'/'qa'
OUT.mkdir(parents=True,exist_ok=True)
scene=bpy.context.scene
records=[]
for ob in scene.objects:
    row={'name':ob.name,'type':ob.type,'collections':[c.name for c in ob.users_collection],
         'matrix':[list(r) for r in ob.matrix_world],'materials':[m.name if m else None for m in ob.data.materials] if hasattr(ob.data,'materials') else [],
         'props':{k:v.to_list() if hasattr(v,'to_list') else v for k,v in ob.items() if k!='_RNA_UI'},'hide_render':ob.hide_render}
    if ob.type=='MESH':
        points=[ob.matrix_world@Vector(p) for p in ob.bound_box]
        row['bounds']=[[min(p[i] for p in points),max(p[i] for p in points)] for i in range(3)]
        row['mesh']=ob.data.name
        row['vertices']=len(ob.data.vertices)
        row['geometry_hash']=hashlib.sha256(b''.join(__import__('struct').pack('3f',*v.co) for v in ob.data.vertices)+b''.join(__import__('struct').pack('I',i) for p in ob.data.polygons for i in p.vertices)).hexdigest()
    if ob.type=='CAMERA':
        row.update(lens=ob.data.lens,projection=ob.data.type,ortho=ob.data.ortho_scale,sensor_width=ob.data.sensor_width,sensor_height=ob.data.sensor_height,sensor_fit=ob.data.sensor_fit,shift_x=ob.data.shift_x,shift_y=ob.data.shift_y,clip_start=ob.data.clip_start,clip_end=ob.data.clip_end)
    if ob.type=='LIGHT':
        row.update(light_type=ob.data.type,energy=ob.data.energy,color=list(ob.data.color))
    records.append(row)
devices=[]
prefs=bpy.context.preferences.addons['cycles'].preferences
for backend in ['OPTIX','CUDA','HIP','ONEAPI']:
    try:
        prefs.compute_device_type=backend
        prefs.get_devices()
        devices.extend({'backend':backend,'name':d.name,'type':d.type} for d in prefs.devices)
    except Exception as error:
        devices.append({'backend':backend,'error':str(error)})
report={'file':bpy.data.filepath,'sha256':hashlib.sha256(Path(bpy.data.filepath).read_bytes()).hexdigest(),
        'blender':bpy.app.version_string,'devices':devices,'resolution':[scene.render.resolution_x,scene.render.resolution_y,scene.render.pixel_aspect_x,scene.render.pixel_aspect_y],
        'units':{'system':scene.unit_settings.system,'scale_length':scene.unit_settings.scale_length},
        'materials':[{'name':m.name,'color':list(m.diffuse_color),'users':m.users} for m in bpy.data.materials],
        'markers':[{'name':m.name,'frame':m.frame,'camera':m.camera.name if m.camera else None} for m in scene.timeline_markers],
        'collections':{c.name:len(c.all_objects) for c in scene.collection.children},'objects':records,
        'view_settings':{'transform':scene.view_settings.view_transform,'look':scene.view_settings.look,'exposure':scene.view_settings.exposure}}
(OUT/'v07_baseline.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
print('V08_INSPECT',json.dumps({k:v for k,v in report.items() if k not in ['objects']},ensure_ascii=False),flush=True)
scene.render.engine='CYCLES'
scene.cycles.device='CPU'
scene.cycles.samples=8
scene.cycles.use_denoising=True
scene.render.threads_mode='FIXED'
scene.render.threads=16
scene.render.resolution_percentage=40
for frame in [1,4,13,15]:
    scene.frame_set(frame)
    scene.camera=next(m.camera for m in scene.timeline_markers if m.frame==frame)
    scene.render.filepath=str(OUT/f'baseline_{frame:02}.png')
    bpy.ops.render.render(write_still=True)
    print('V08_BASELINE_PREVIEW',frame,flush=True)
