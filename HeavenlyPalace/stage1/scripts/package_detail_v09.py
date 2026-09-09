"""
只对实际 Blender 渲染做等比例排版，生成四机位总览与同机位版本对照。
汇总真实参数、资源与文件摘要，打包可独立渲染的第九版交付目录。
"""
import json
import hashlib
import zipfile
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'v09'
renders=OUT/'renders'
manifest=json.loads((OUT/'qa'/'render_manifest.json').read_text(encoding='utf-8'))
audit=json.loads((OUT/'qa'/'verification.json').read_text(encoding='utf-8'))
font_path='C:/Windows/Fonts/msyh.ttc'
title_font=ImageFont.truetype(font_path,38)
small_font=ImageFont.truetype(font_path,24)
background=(24,31,35)
foreground=(235,231,218)


# 每张图片检查实际尺寸与文件内容，不用参考图替换任何渲染像素。
# 拼版保留正式图原始分辨率，另提供缩小的便览版本。
rows=[]
# 四主机位先完成时可单独排版，近景结束后再执行完整核验和打包。
# 此模式仅提供已有实渲的总览，不把未完成近景写成已交付状态。
boards_only='--boards-only' in sys.argv
for key in (['1','2','3','4','baseline'] if boards_only else ['1','2','3','4','17','18','baseline']):
    p=Path(manifest[key]['file'])
    with Image.open(p) as im:
        assert im.size==(1800,1350)
        rows.append({'file':str(p.relative_to(ROOT)),'width':im.width,'height':im.height,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})

sheet=Image.new('RGB',(3660,2890),background)
draw=ImageDraw.Draw(sheet)
for index,(file,label) in enumerate([('01_oblique.png','01 整体全景'),('02_front.png','02 正面结构'),('03_aerial.png','03 鸟瞰布局'),('04_interior.png','04 殿内望云')]):
    x=20+(index%2)*1820
    y=20+(index//2)*1430
    draw.text((x,y),label,font=title_font,fill=foreground)
    with Image.open(renders/file) as im:
        sheet.paste(im,(x,y+62))
sheet.save(renders/'00_four_views.png')
sheet.resize((1830,1445),Image.Resampling.LANCZOS).save(renders/'00_four_views_preview.jpg',quality=94)

comparison=Image.new('RGB',(3660,1470),background)
draw=ImageDraw.Draw(comparison)
for x,path,label in [(20,OUT/'comparison'/'00_v08_1_interior.png','V8.1 · 精修前'),(1840,renders/'04_interior.png','V9 · 主殿重点精修')]:
    draw.text((x,12),label,font=title_font,fill=foreground)
    with Image.open(path) as im:
        comparison.paste(im,(x,70))
draw.text((20,1432),'相同相机与灯光 · 52 mm / Shift X -0.12 · Blender Cycles 实际渲染 · 仅排版',font=small_font,fill=foreground)
comparison.save(OUT/'comparison'/'01_v08_1_vs_v09.png')
comparison.resize((1830,735),Image.Resampling.LANCZOS).save(OUT/'comparison'/'01_v08_1_vs_v09_preview.jpg',quality=94)
if boards_only:
    print('V09_FOUR_VIEW_BOARDS_READY',flush=True)
    sys.exit(0)
(OUT/'qa'/'delivery_images.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')

baseline_seconds=manifest['baseline']['seconds']
v9_seconds=manifest['4']['seconds']
ratio=v9_seconds/baseline_seconds
readme=f'''# HeavenlyPalace V9 主殿重点区域精修

工程：[HeavenlyPalace_Detail_v09.blend](../HeavenlyPalace_Detail_v09.blend)。基于 V8.1 增量制作，原文件保留且 SHA-256 核验一致。所有交付图片均为 Blender 实际渲染；原型只作为内嵌参考资源，未用于背景替换或生成式修图。

## 图片

- [四机位总览](renders/00_four_views.png)
- [整体全景](renders/01_oblique.png)、[正面结构](renders/02_front.png)、[鸟瞰布局](renders/03_aerial.png)、[殿内望云](renders/04_interior.png)
- [巨柱近景](renders/05_column_detail.png)、[月门近景](renders/06_moon_detail.png)
- [V8.1/V9 同机位对比](comparison/01_v08_1_vs_v09.png)、[V8.1 本轮重渲原图](comparison/00_v08_1_interior.png)

六张单张交付图及 V8.1 对照原图均为 1800×1350、4:3。总览与对比仅排版，不修改场景渲染内容。

## 本轮完成

- 原有 24 根主殿巨柱保留 7.2 米柱径、原收分与柱网，柱身改为 192 边共享圆周网格；柱础、束口与柱头采用 128 边共享回转剖面及局部倒角。
- 独立贴面卷云、卷草与柱脚莲瓣浅浮雕形成主要阴影，最大起伏约 0.19 米。最近巨柱的装饰转向固定画幅中可见的一侧，其余区域保留较大素面。
- 月门通厚石圈主体网格不动，连续卷草与墙翼疏云分层保留；新增门圈纹饰最低半径 {audit['moon_ornament_minimum_radius_m']:.3f} 米，大于 22 米净半径。
- 可见横梁增加朱漆配黛青芯板、金线与疏卷草；九块重点天花增加三层浅内收框、黛青底和团莲金饰。
- 主殿原屋面曲线保留，补充贴面筒瓦垄、瓦当与分节脊饰，并将适用脊饰推广到入口及亭廊重点位置。重复构件共享网格或材质。
- 地面保留 Z=36 完成面及四米大板，以接缝、微弱色差和 0.215—0.315 板面粗糙度变化表现柔和反射；缝内粗糙度提高至 0.76，改善强反光下的可读性。
- 三位殿内方块参照替换为长袍人物，保留原站位、约 1.8 米身高和鞋底接地，使用衣摆轮廓、纵褶、垂袖及简洁发髻；平底鞋提供连续接触面。

## 保留与核验

正式殿内相机仍为 `CAM_04_殿内望云_v08_1`，位置 (24,365,37.65)，52 mm，Shift X=-0.12，眼高 1.65 米。四个原相机与时间线绑定不变；新增第 17、18 帧用于近景。

所有相机共用同一个场景和固定可见性。建筑布局、原屋面主体、平台标高、通路、月门净径与 V8.1 云海不变；未修改原灯光、曝光或世界节点。入口附近遮檐局部云仍在所有机位真实存在。逐对象核验结果见 [verification.json](qa/verification.json)。

## 实际渲染设置和资源

Blender 5.2.1 LTS / Cycles CPU，16 渲染线程；64 最大采样，自适应阈值 0.025，降噪；1800×1350 PNG RGB 8 位；沿用 AgX / AgX - Medium High Contrast、原曝光及体积步进设置。逐图设置与耗时见 [render_manifest.json](qa/render_manifest.json)。

本轮同设置殿内实测：V8.1 为 {baseline_seconds:.2f} 秒，V9 为 {v9_seconds:.2f} 秒，耗时比约 {ratio:.2f}。单次测量会受系统负载与缓存影响。唯一网格顶点由 {audit['source_unique_mesh_vertices']:,} 增至 {audit['v09_unique_mesh_vertices']:,}；新增细节没有使用全场细分。所有文件纹理已内嵌，程序材质无外部贴图依赖。

## 渲染入口

在 `scripts` 目录执行 `render_v09.ps1` 输出全部六张正式图；`-Frames '4'` 输出殿内；`-Frames '1,2,3' -Preview` 输出外景预览；`-Baseline` 从原 V8.1 生成对照。既有 `render_lookdev_v08.py` 也已识别 `_v09` 工程并转入此流程。所有新输出写入 `v09`，不覆盖旧版图片。

工程内嵌 `V09_render_detail_v09.py`，也可在 Blender 文本编辑器运行。交付包保留同样的目录层级。增量重建脚本另需保留在原工程目录的 V8.1 源文件；正常打开和渲染 V9 无需加载源文件。

## 剩余限制

本轮雕刻为可编辑的程序浅浮雕，仍是简化的卷云、卷草和莲瓣，尚未达到原型中完整云龙雕刻的复杂程度。固定机位只见少量顶面，因此天花重点做浅层分格，未制作画幅外的高密度藻井。人物按远景尺寸建模，未制作精细面部或布料模拟。沿用的 V8.1 天空、云海形态与整体光照仍与原型存在差异。入口西翼遮檐云在正面、斜视与鸟瞰中仍呈白色云缘并投影，维持了 V8.1 用于遮挡低角度屋檐的状态。
'''
(OUT/'V9交付说明.md').write_text(readme,encoding='utf-8')


# 交付包包含最终工程、实渲与直接渲染脚本；所有贴图在工程内部。
# 中间样板保留在工作目录追溯，避免把它们误当作最终交付图。
files=[ROOT/'HeavenlyPalace_Detail_v09.blend',OUT/'V9交付说明.md']
files+=list(renders.glob('*.png'))+list(renders.glob('*.jpg'))+list((OUT/'comparison').glob('*.png'))+list((OUT/'comparison').glob('*.jpg'))
files += [ROOT/'scripts'/n for n in ['build_detail_v09.py','render_detail_v09.py','render_v09.ps1','audit_detail_v09.py','package_detail_v09.py','render_lookdev_v08.py']]
files += [OUT/'qa'/n for n in ['build_report.json','verification.json','render_manifest.json','delivery_images.json','baseline_v08_1.json']]
files += [OUT/'qa'/'visual_review.json']
files += [ROOT/'v05'/'design_parameters_v05.json']
checksum={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
(OUT/'qa'/'delivery_checksums.json').write_text(json.dumps(checksum,ensure_ascii=False,indent=2),encoding='utf-8')
files.append(OUT/'qa'/'delivery_checksums.json')
with zipfile.ZipFile(OUT/'HeavenlyPalace_Detail_v09_Delivery.zip','w',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
    for p in files:
        archive.write(p,p.relative_to(ROOT))
print('V09_DELIVERY_PACKAGED',len(files),flush=True)
