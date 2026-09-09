"""
渲染已保存的 V7 工程，不重新建模，不改变工程内相机和可见性。
正式图统一使用 V6 灯光、Cycles CPU、四十八最大采样与降噪。
"""
import bpy
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"v07"
P=json.loads(bpy.data.texts["09_v07环境参数.json"].as_string())
ARGS=sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
frames=[int(f) for f in ARGS[ARGS.index("--frames")+1].split(",")] if "--frames" in ARGS else [1,2,3,4,12,13,14,15,16]
names={1:"01_oblique",2:"02_front",3:"03_aerial",4:"04_interior"}
names.update({r["frame"]:r["output"] for r in P["detail_cameras"]})
scene=bpy.context.scene
scene.render.engine="CYCLES"
scene.cycles.device="CPU"
scene.cycles.samples=P["render_samples"]
scene.cycles.use_denoising=True
scene.render.resolution_x=P["render_width"]
scene.render.resolution_y=P["render_height"]
scene.render.resolution_percentage=60 if "--preview" in ARGS else 100
scene.render.threads_mode="FIXED"
scene.render.threads=P["render_threads"]
if "--preview" in ARGS:
    scene.cycles.samples=12

# 每个机位在同一场景中切换，禁止按机位切换物体可见性。
# 渲染脚本不保存工程，避免最终工程停在临时测试帧或预览分辨率。
for frame in frames:
    scene.frame_set(frame)
    scene.camera=next(m.camera for m in scene.timeline_markers if m.frame==frame)
    scene.render.filepath=str(OUT/("qa" if "--preview" in ARGS else "renders")/(names[frame]+".png"))
    bpy.ops.render.render(write_still=True)
    print("V07_RENDER",frame,scene.render.filepath,flush=True)
