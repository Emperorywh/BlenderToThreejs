# 云顶天宫 · 第二阶段主殿建筑样板 V03

## 当前范围与冻结基线

V02 总布局与大体量已由用户基本验收。本轮仅完善主殿正立面右侧连续两开间：柱轴 X=7.5、15、22.5，柱排 Y=153、160，包含三条柱轴、六根柱、两处后退门墙开间和对应三层前檐。两开间轴线合计宽 15 米，约为主殿面阔的四分之一。未向整殿侧面、背面或其他开间复制。

主轴、七个平台位置、六条桥梯、侧岛与亭台数量、人工高台及浮岛占位全部冻结。主殿柱网仍为 60 × 42 米，含檐线外轮廓仍约 80.2 × 58.2 米，台面至最高脊线仍约 36.91 米。原三层屋顶网格和曲线数据保持不变，没有整体放大建筑或增加楼层。

使用原有 Blender 5.2.1 LTS 本地后台 Python 通道，未安装插件、重配环境或下载资产。样板保存在原场景 Tiangong_Whitebox 中，集合 TG_S03_主殿右侧两开间样板 下分柱头、梁架、檩椽、门墙四类，构件可独立编辑。无关启动场景 Scene 保留。

## 建筑样板处理

本轮重新查看正面与斜视原参考，检查柱头、檐下承托和门墙层次。总布局仍服从原 01_overview.png，不重新匹配概念图之间不同的布局。样板是基于参考方向的补充建筑设计，不宣称还原完整历史营造制式。

选中六根柱只把上端柱身从 Z=47.2 调整到 Z=46.0，为柱头座块、横向拱臂、纵向托臂及小承托块留出高度。柱轴、柱径、柱础及台面不变。同排柱补入连续额枋与简化斜肩承托，两排柱之间由纵向梁连接，原有全宽主梁继续参与承托。

三层屋面外形及厚度保持 V02。样板区域新增封檐板、下缘压条、矩形椽、横向檩和收分出挑梁。椽沿实际屋面下表面生成；檩接椽，出挑梁接外檩，纵向承托梁接柱头或层间短柱。层间短柱下方另设穿过屋面厚度的承托块，与下一层纵向梁相接，形成连续的几何连接。屋面、檐口收边与檐下支承因此各有可辨认的层次。

两处后退门墙开间分别制作简化双扇门与槛窗，包含外框、后退扇框、大板、稀疏竖梃、上亮子和墙面上部梁枋分区。中央月门墙体、门套及开口完全保留。新增框料前缘不越过原门墙前平面 Y=162.25，前排柱后缘至门墙的 8.30 米净深保留。人物仍为 1.75 米，栏杆立柱仍为 1.18 米。

没有制作密集雕花、龙纹、完整瓦片、云海、复杂水体或精细植被。浮岛、树木和瀑布占位保持原状，灰模材质及照明沿用 V02。

## 参数、工程与复现

scene_config.json 是冻结的 V02 全场景参数，内容和哈希保持不变。hall_sample_config.json 是当前样板的增量参数，指定区域、截面、支承位置、四个共同机位与输出路径，并通过基线工程及配置哈希锁定 V02。局部简化节点由构建模块生成，不构成第二套全场景尺寸。

- output/tiangong_whitebox_v02.blend：冻结基线，保留原文件及路径。
- output/v02_snapshot/：进入样板阶段前的 V02 参数、说明和脚本快照。
- output/tiangong_hall_sample_v03.blend：独立样板工程，包含完整 V02 场景与这一段建筑样板。
- scripts/build_hall_sample.py：当前构建入口，每次从冻结 V02 读取，只修改限定对象并另存样板。
- scripts/render_hall_sample.py：重开保存工程，输出两版共同机位。
- scripts/validate_hall_sample.py：检查实际网格接头及冻结边界。
- scripts/finalize_hall_sample.py：全部最终原图保存后制作对照板，重新生成统一清单并核验哈希。

原 build_whitebox.py、palace_mass.py、whitebox_geometry.py 保留，前两者继续用于 V02 复现，样板入口也复用几何工具。重跑会重新生成样板，已有样板自动备份到 output/backups/。手动修改样板对象时，请先另存工程或同步修改构建参数。

在项目根目录运行：

```powershell
# 从冻结 V02 创建或重建两开间样板，保留旧样板备份。
# 入口直接读取基线文件，不依赖当前 Blender 打开的文件。
& 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe' --background --python-exit-code 1 --python scripts/build_hall_sample.py

# 为 V02 输出相同机位、照明和灰模材质的修改前原图。
# 只在内存添加对照相机，不保存回 V02。
& 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe' --background --python-exit-code 1 --python scripts/render_hall_sample.py -- --before

# 重开样板，输出同一场景全部修改后原图。
# 各机位不改变模型位置或可见性。
& 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe' --background --python-exit-code 1 --python scripts/render_hall_sample.py

# 原图全部保存后制作对照板和最终清单。
# 使用本机已有 Pillow，重读全部图片核验 SHA-256。
python scripts/finalize_hall_sample.py

# 重开工程，只读检查冻结对象及真实网格接头。
# 验证报告写入 output/sample_v03_validation.json。
& 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe' --background --python-exit-code 1 --python scripts/validate_hall_sample.py
```

## 实际复核与对照条件

四个固定机位为 sample_close（柱身、门墙及前檐近景）、joint_detail（柱头与檐下连接）、hall_front（完整主殿正面）、hall_oblique（完整主殿斜视）。两个版本共用同一参数表，保留相同灯光、白模材质和色彩管理。每个版本的四张图都来自同一个重新打开的工程，不按机位隐藏或移动模型。

已实际打开首轮八张前后对照图。首轮檐口和门墙层次更清楚，但层间短柱仍需继续向下连接纵向梁；随后补入穿屋面承托块、连续纵梁及柱头斜肩，再次渲染并查看了近景、连接图与完整正面。样板边界与未完善区域的差别可见，符合局部试做范围。

最终工程重新打开后十二项检查通过：范围外模型摘要不变；主殿包围尺寸、原三层屋面、月门、基线文件和配置均保持原数据；新增网格封闭、正向体积；无关场景保留；保存模型与构建记录一致；门墙前平面和中央通道保留；四个相机已保存。66 处真实网格接头检查覆盖椽与屋面、出挑梁与外檩、穿屋面承托块与上下构件。

实际重跑的模型摘要及新增对象数量一致，没有重复叠加。新增 256 个样板对象，修改七个旧对象（六根柱的上端和一处门槛），替换十六个范围内旧柱头、纵梁及门框占位，其余旧模型不变。记录在 output/sample_v03_build_report.json、sample_v03_validation.json、sample_v03_rerun.json。

最终四组前后原图均已完成并逐张实际打开复核。近景为 1600 × 1600，其余原图为 1600 × 1100。近景可见柱头、额枋、出挑梁、檩椽和后退门墙层次，完整主殿的外轮廓与比例保持 V02。全部原图及对照板保存后重新生成 render_manifest.json，再读回清单并逐张计算本地 SHA-256；8 张原图和 4 张对照板共 12 张图片全部匹配，实际相机、照明、材质和渲染设置的前后一致性检查通过。

## 交付图片与清单

全部最终图片位于 output/previews_sample_v03/：

- before/、after/：四个机位的修改前后原始 PNG。
- comparison_sample_close.png：样板近景对照。
- comparison_joint_detail.png：柱头、梁架和檐下连接对照。
- comparison_hall_front.png、comparison_hall_oblique.png：完整主殿对照。
- render_manifest.json：全部最终图片保存后重新生成，记录实际相机、照明、材质、源工程及图片 SHA-256。
- hash_verification.json：清单写入后再次读取全部图片的本地核验结果。

对照板图片区域保持源像素，无缩放、裁切或调色。过程图位于 output/review_sample_v03_initial/ 和 output/review_sample_v03_corrected/，不作为最终验收图。

## 待确认与停止点

样板仍是中等尺度灰模结构，没有榫卯、精细斗拱、雕花和完整瓦作；几何接触检查不代表真实建筑受力校核。屋面仍保留 V02 简化庑殿大形，未重塑已验收的总体轮廓。样板两端与原白模相接，其余主殿区域仍可见原简化檐下关系。

本轮等待确认柱头承托尺度、檩椽和檐口层次、门墙分区及它们与整殿的协调程度。停止在建筑样板确认阶段，尚未向全殿复用，也未展开全场景精雕。
