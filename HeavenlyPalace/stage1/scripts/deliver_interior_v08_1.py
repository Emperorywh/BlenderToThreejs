"""
从最终保存的第八点一版输出三个固定机位检查图与殿内正式图。
复用既有渲染入口，各次输出仅调整分辨率和采样，不更改场景布置。
"""
import bpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / 'scripts' / 'render_lookdev_v08.py'
original_args = sys.argv[:]
sys.argv = ['blender', '--', '--frames', '1,2,3', '--preview']
exec(compile(path.read_text(encoding='utf-8'), str(path), 'exec'), {'__name__': '__main__', '__file__': str(path)})
bpy.context.scene.cycles.samples = 64
bpy.context.scene.cycles.adaptive_threshold = .025
sys.argv = ['blender', '--', '--frames', '4']
exec(compile(path.read_text(encoding='utf-8'), str(path), 'exec'), {'__name__': '__main__', '__file__': str(path)})
sys.argv = original_args
print('V08_1_DELIVERY_RENDERS_COMPLETE', flush=True)
