"""
第九版统一真实渲染入口，四主机位与两细节机位共用已保存场景和可见性。
对照图从原第八点一版重新渲染，仅统一分辨率与采样，不更改相机和灯光。
"""
import bpy
import json
import sys
import time
import hashlib
from pathlib import Path

# 内嵌文本可直接在 Blender 文本编辑器执行，使用当前工程所在目录。
# 外部命令行执行时仍按脚本目录定位，二者共享同一输出结构。
ROOT=Path(__file__).resolve().parents[1] if '__file__' in globals() else Path(bpy.data.filepath).parent
OUT=ROOT/'v09'
ARGS=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
frames=[int(v) for v in ARGS[ARGS.index('--frames')+1].split(',')] if '--frames' in ARGS else [1,2,3,4,17,18]
preview='--preview' in ARGS
baseline='--baseline' in ARGS
scene=bpy.context.scene
if baseline:
    assert Path(bpy.data.filepath).name=='HeavenlyPalace_Lookdev_v08_1.blend'
    assert frames==[4]
else:
    assert Path(bpy.data.filepath).name=='HeavenlyPalace_Detail_v09.blend'
scene.render.resolution_x,scene.render.resolution_y=1800,1350
scene.render.resolution_percentage=50 if preview else 100
scene.render.image_settings.file_format='PNG'
scene.render.image_settings.color_mode='RGB'
scene.render.image_settings.color_depth='8'
scene.cycles.samples=24 if preview else 64
scene.cycles.adaptive_threshold=.025
scene.cycles.use_denoising=True
scene.render.threads_mode='FIXED'
scene.render.threads=16
names={1:'01_oblique',2:'02_front',3:'03_aerial',4:'04_interior',17:'05_column_detail',18:'06_moon_detail'}
manifest_path=OUT/'qa'/('preview_manifest.json' if preview else 'render_manifest.json')
manifest=json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {}


# 可见性摘要在每帧渲染前核对；只切换绑定相机，不使用按相机开关物体的方案。
# 记录相机、色彩管理、采样、体积步长与实际耗时，方便比较资源开销。
def visibility_hash():
    state=[(o.name,o.hide_render) for o in scene.objects]
    state.extend((c.name,c.hide_render) for c in bpy.data.collections)
    return hashlib.sha256(json.dumps(sorted(state)).encode()).hexdigest()


visibility=visibility_hash()
for frame in frames:
    scene.frame_set(frame)
    scene.camera=next(m.camera for m in scene.timeline_markers if m.frame==frame)
    assert visibility_hash()==visibility
    path=OUT/('qa' if preview else ('comparison' if baseline else 'renders'))/(('preview_' if preview else '')+('00_v08_1_interior' if baseline else names[frame])+'.png')
    path.parent.mkdir(parents=True,exist_ok=True)
    scene.render.filepath=str(path)
    started=time.monotonic()
    print('V09_RENDER_START',frame,str(path),flush=True)
    bpy.ops.render.render(write_still=True)
    row={'file':str(path),'camera':scene.camera.name,'location':list(scene.camera.location),'rotation':list(scene.camera.rotation_euler),'lens_mm':scene.camera.data.lens,'shift':[scene.camera.data.shift_x,scene.camera.data.shift_y],'engine':scene.render.engine,'device':scene.cycles.device,'resolution':[900,675] if preview else [1800,1350],'samples':scene.cycles.samples,'adaptive_threshold':scene.cycles.adaptive_threshold,'denoising':scene.cycles.use_denoising,'volume_step_rate':scene.cycles.volume_step_rate,'volume_max_steps':scene.cycles.volume_max_steps,'view_transform':scene.view_settings.view_transform,'look':scene.view_settings.look,'exposure':scene.view_settings.exposure,'visibility_sha256':visibility,'seconds':round(time.monotonic()-started,2),'scene_file':bpy.data.filepath}
    manifest['baseline' if baseline else str(frame)]=row
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print('V09_RENDER_COMPLETE',json.dumps(row,ensure_ascii=False),flush=True)
