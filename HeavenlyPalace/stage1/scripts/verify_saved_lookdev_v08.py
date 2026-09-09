"""
重新打开成品后核实相机、分辨率与打包资源，确认保存结果可直接使用。
这里只读工程并输出记录，不更改场景，不触发额外渲染或几何生成。
"""
import bpy
import json
import hashlib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'v08'/'qa'
scene=bpy.context.scene
baseline=json.loads((OUT/'v07_baseline.json').read_text(encoding='utf-8'))
camera_errors=[]
for rec in baseline['objects']:
    if rec['type']!='CAMERA':
        continue
    ob=scene.objects.get(rec['name'])
    if not ob:
        camera_errors.append(rec['name'])
        continue
    changed=any(abs(ob.matrix_world[i][j]-rec['matrix'][i][j])>1e-6 for i in range(4) for j in range(4))
    changed=changed or any(abs(getattr(ob.data,key)-rec[key])>1e-6 for key in ['lens','sensor_width','sensor_height','shift_x','shift_y','clip_start','clip_end'])
    changed=changed or ob.data.type!=rec['projection'] or ob.data.ortho_scale!=rec['ortho'] or ob.data.sensor_fit!=rec['sensor_fit']
    if changed:
        camera_errors.append(rec['name'])
images=[{'name':im.name,'packed':bool(im.packed_file),'keep_on_reload':im.use_fake_user,'size':list(im.size)} for im in bpy.data.images if im.source=='FILE']
report={'file':bpy.data.filepath,'blend_bytes':Path(bpy.data.filepath).stat().st_size,'blend_sha256':hashlib.sha256(Path(bpy.data.filepath).read_bytes()).hexdigest(),
        'baseline_v07_unchanged':hashlib.sha256((ROOT/'HeavenlyPalace_Environment_v07.blend').read_bytes()).hexdigest()==baseline['sha256'],
        'camera_count':sum(o.type=='CAMERA' for o in scene.objects),'camera_errors':camera_errors,'active_camera':scene.camera.name,
        'resolution':[scene.render.resolution_x,scene.render.resolution_y,scene.render.resolution_percentage],
        'engine':scene.render.engine,'samples':scene.cycles.samples,'denoising':scene.cycles.use_denoising,'packed_images':images,
        'geometry_audit_passed':json.loads((OUT/'audit_v08.json').read_text(encoding='utf-8'))['passed']}
report['passed']=report['baseline_v07_unchanged'] and not camera_errors and report['resolution']==[1800,1350,100] and len(images)>=1 and all(i['packed'] for i in images) and report['geometry_audit_passed']
(OUT/'saved_file_verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
if not report['passed']:
    raise RuntimeError('交付文件重新打开后的核验未通过。')
