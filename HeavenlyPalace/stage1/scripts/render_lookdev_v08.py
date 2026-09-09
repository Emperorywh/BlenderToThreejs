"""
从已保存的第八版工程输出六个固定机位的真实渲染，不重新建模。
所有机位共用文件里的材质、灯光、曝光和可见性，逐张记录分辨率与耗时。
"""
import bpy
import json
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'v08'
ARGS=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
frames=[int(v) for v in ARGS[ARGS.index('--frames')+1].split(',')] if '--frames' in ARGS else [1,2,3,4,13,15]
preview='--preview' in ARGS
scene=bpy.context.scene
scene.render.resolution_percentage=50 if preview else 100
if preview:
    scene.cycles.samples=16
scene.render.image_settings.file_format='PNG'
scene.render.image_settings.color_mode='RGB'
scene.render.image_settings.color_depth='8'
names={1:'01_oblique',2:'02_front',3:'03_aerial',4:'04_interior',13:'05_hero_pine',15:'06_waterfall'}
manifest_path=OUT/'qa'/('preview_manifest.json' if preview else 'render_manifest.json')
manifest=json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {}
for frame in frames:
    scene.frame_set(frame)
    scene.camera=next(m.camera for m in scene.timeline_markers if m.frame==frame)
    path=OUT/('qa' if preview else 'renders')/(('preview_' if preview else '')+names[frame]+'.png')
    scene.render.filepath=str(path)
    started=time.monotonic()
    bpy.ops.render.render(write_still=True)
    manifest[str(frame)]={'file':str(path),'camera':scene.camera.name,'engine':scene.render.engine,'device':scene.cycles.device,
                         'resolution':[round(scene.render.resolution_x*scene.render.resolution_percentage/100),round(scene.render.resolution_y*scene.render.resolution_percentage/100)],
                         'samples':scene.cycles.samples,'denoising':scene.cycles.use_denoising,'seconds':round(time.monotonic()-started,2),'scene_file':bpy.data.filepath}
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print('V08_FINAL_RENDER',json.dumps(manifest[str(frame)],ensure_ascii=False),flush=True)
