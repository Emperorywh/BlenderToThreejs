"""
整理交付副本的无用户数据与内嵌导出脚本，使保存文件只保留有效网页资源。
修正柱纹法线使用的切线 UV，打包实际纹理并保存四个正式时间线机位。
"""
import bpy,json,sys
from pathlib import Path
OUT=Path(__file__).resolve().parents[1]
# 工程整理同样采用临时副本加原子替换，防止文件占用导致交付工程保存中断。
# 临时副本与正式文件同目录，相对贴图和内嵌脚本无需重新定位。
sys.path.insert(0,str(Path(__file__).resolve().parent))
from blend_io import save_web_blend
scene=bpy.context.scene
for mat in bpy.data.materials:
    if 'web_spec' in mat and json.loads(mat['web_spec']).get('normal_uv')==1:
        for node in mat.node_tree.nodes:
            if node.type=='NORMAL_MAP':node.uv_map='ReliefUV'
for marker in list(scene.timeline_markers):
    if marker.frame>4:scene.timeline_markers.remove(marker)
for text in list(bpy.data.texts):bpy.data.texts.remove(text)
# 将质量升级与检查脚本同时归档到工程，便于定位生成来源。
# 实际重建仍使用同目录脚本，以保留模块之间正确的相对路径。
# 主殿的重建参数与检查入口同时内嵌，交付工程可直接追溯本轮构件来源。
# 外部脚本仍是正式执行入口，确保模块引用和输出目录保持确定。
# 殿内构图脚本与建筑生成脚本一起归档，工程内可追溯机位和人物站位参数。
# 原始脚本仍通过外部路径执行，保证备份、资源与核验报告写到同一交付目录。
# 藻井的局部重建入口、几何与材质模块一并归档，保存完整的生成依据。
# 内嵌文本用于追溯，实际执行仍从外部脚本目录解析模块与资源路径。
# 空间参数和独立调整入口随工程归档，便于追溯实际层高、柱径及月门尺寸。
# 外部模块仍为正式执行来源，内嵌副本用于阅读和重建依据核对。
for name in ['export_glb.py','verify_scene.py','upgrade_quality.py','quality_materials.py','review_quality.py','refine_main_hall.py','review_main_hall.py','compose_hall_view.py','blend_io.py','refine_hall_ceiling.py','hall_ceiling.py','hall_ceiling_materials.py','hall_space.py','refine_hall_space.py']:
    text=bpy.data.texts.new('WEB_'+name)
    text.write((OUT/'scripts'/name).read_text(encoding='utf-8'))
for image in bpy.data.images:
    if image.users and image.source!='VIEWER':image.pack()
bpy.data.orphans_purge(do_local_ids=True,do_linked_ids=False,do_recursive=True)
save_web_blend(OUT/'HeavenlyPalace_WebAssets_v01.blend')
print('FINAL_BLEND_READY',flush=True)
