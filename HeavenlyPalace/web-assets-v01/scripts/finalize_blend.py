"""
整理交付副本的无用户数据与内嵌导出脚本，使保存文件只保留有效网页资源。
修正柱纹法线使用的切线 UV，打包实际纹理并保存四个正式时间线机位。
"""
import bpy,json
from pathlib import Path
OUT=Path(__file__).resolve().parents[1]
scene=bpy.context.scene
for mat in bpy.data.materials:
    if 'web_spec' in mat and json.loads(mat['web_spec']).get('normal_uv')==1:
        for node in mat.node_tree.nodes:
            if node.type=='NORMAL_MAP':node.uv_map='ReliefUV'
for marker in list(scene.timeline_markers):
    if marker.frame>4:scene.timeline_markers.remove(marker)
for text in list(bpy.data.texts):bpy.data.texts.remove(text)
for name in ['export_glb.py','verify_scene.py']:
    text=bpy.data.texts.new('WEB_'+name)
    text.write((OUT/'scripts'/name).read_text(encoding='utf-8'))
for image in bpy.data.images:
    if image.users and image.source!='VIEWER':image.pack()
bpy.data.orphans_purge(do_local_ids=True,do_linked_ids=False,do_recursive=True)
bpy.context.preferences.filepaths.save_version=0
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'HeavenlyPalace_WebAssets_v01.blend'),compress=True)
print('FINAL_BLEND_READY',flush=True)
