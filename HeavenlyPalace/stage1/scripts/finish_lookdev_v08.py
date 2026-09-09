"""
整理第八版交付入口、内嵌说明与正式渲染设置，不更改环境形体和建筑布局。
保存后六个机位只读取此工程渲染，保证它们采用同一材质、光照与曝光。
"""
import bpy
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'v08'
scene=bpy.context.scene
scene.render.engine='CYCLES'
scene.cycles.device='CPU'
scene.cycles.samples=48
scene.cycles.adaptive_threshold=.045
scene.cycles.use_denoising=True
scene.cycles.volume_bounces=1
scene.cycles.volume_biased=True
scene.cycles.volume_step_rate=1
scene.cycles.volume_max_steps=768
scene.render.resolution_x=1800
scene.render.resolution_y=1350
scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG'
scene.render.image_settings.color_mode='RGB'
scene.render.image_settings.color_depth='8'
scene.render.threads_mode='FIXED'
scene.render.threads=16
scene.frame_set(1)
scene.camera=next(m.camera for m in scene.timeline_markers if m.frame==1)
scene.render.filepath='//v08/renders/01_oblique.png'
scene['V08渲染设置']='Cycles CPU；1800×1350；48最大采样；自适应0.045；降噪；体积反弹1；固定同一套灯光'
scene['V08时间线']='帧1整体斜视、2正面、3鸟瞰、4殿内月门、13古松、15瀑布；全部16台原相机保留'
scene['V08交付说明']='00_V08交付说明.md；材质与参考图已打包；无外部贴图依赖'

# 参考图不参与渲染，因此显式保留数据块，避免无用户图像在重新打开时被清除。
# 所有实际表面仍使用工程内的程序材质，参考图只作为色彩与氛围记录。
reference=Path('C:/Users/12899/Downloads/ChatGPT Image 2026年9月8日 17_54_37.png')
if reference.exists():
    img=bpy.data.images.load(str(reference),check_existing=True)
    img.name='V08_色彩与氛围原型参考_非渲染背景'
    img.use_fake_user=True
    img.pack()


# 明确区分历史重建入口和当前成品，避免误运行旧阶段脚本覆盖正在查看的场景。
# 旧数据仍保留在工程内用于追溯，第八版入口指向已有的制作脚本与渲染脚本。
old=bpy.data.texts.get('02_当前阶段重建入口.py')
if old:
    old.name='历史_V07_重建入口.py'
guide=bpy.data.texts.get('02_V08制作与渲染说明.md') or bpy.data.texts.new('02_V08制作与渲染说明.md')
guide.clear()
guide.write('当前为V08静态场景成品。直接编辑01、09、10集合中的环境，以及17远山、18云海、19灯光。\n材质均为V08开头的共享程序材质，世界一单位等于一米。\n重建顺序：scripts/build_lookdev_v08.py先执行environment阶段，再执行materials阶段；随后执行refine_southern_clouds_v08.py整理南向云域，最后执行finish_lookdev_v08.py冻结正式设置。\nrefine_clouds_v08.py与volume_sampling_v08.py为迭代记录，最终材质入口已经包含它们的调整，不需要重复执行。\n最终渲染使用scripts/render_lookdev_v08.py；该脚本只切换原时间线相机，不修改场景。\n历史V07入口只作追溯，不用于V08继续制作。\n')
for ob in scene.objects:
    if '参数编辑说明' in ob:
        ob['参数编辑说明']='当前V08：参阅02_V08制作与渲染说明.md，直接编辑可见环境、共享材质、云海与灯光集合。'
for name in ['build_lookdev_v08.py','lookdev_materials_v08.py','refine_clouds_v08.py','volume_sampling_v08.py','refine_southern_clouds_v08.py','render_lookdev_v08.py','audit_lookdev_v08.py','finish_lookdev_v08.py']:
    block=bpy.data.texts.get('V08_'+name) or bpy.data.texts.new('V08_'+name)
    block.clear()
    block.write((ROOT/'scripts'/name).read_text(encoding='utf-8'))
readme=OUT/'V08交付说明.md'
if readme.exists():
    block=bpy.data.texts.get('00_V08交付说明.md') or bpy.data.texts.new('00_V08交付说明.md')
    block.clear()
    block.write(readme.read_text(encoding='utf-8'))
audit=OUT/'qa'/'audit_v08.json'
if audit.exists():
    record=json.loads(audit.read_text(encoding='utf-8'))
    record['images']=[{'name':im.name,'source':im.source,'packed':bool(im.packed_file),'path':im.filepath} for im in bpy.data.images if im.source=='FILE']
    audit.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    block=bpy.data.texts.get('V08_建筑与环境核验.json') or bpy.data.texts.new('V08_建筑与环境核验.json')
    block.clear()
    block.write(audit.read_text(encoding='utf-8'))
bpy.ops.file.pack_all()
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'HeavenlyPalace_Lookdev_v08.blend'),compress=True)
print('V08_DELIVERY_FILE_READY',bpy.data.filepath,flush=True)
