"""
殿内正式图完成后先生成同机位对照，供其余机位渲染期间查看。
两张实际渲染保持原始比例，仅添加版面留边和版本标签。
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'v09'
before=OUT/'comparison'/'00_v08_1_interior.png'
after=OUT/'renders'/'04_interior.png'
canvas=Image.new('RGB',(3660,1470),(24,31,35))
draw=ImageDraw.Draw(canvas)
font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',38)
small=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',24)
for x,path,label in [(20,before,'V8.1 · 精修前'),(1840,after,'V9 · 主殿重点精修')]:
    draw.text((x,12),label,font=font,fill=(235,231,218))
    with Image.open(path) as im:
        assert im.size==(1800,1350)
        canvas.paste(im,(x,70))
draw.text((20,1432),'相同相机与灯光 · 52 mm / Shift X -0.12 · Blender Cycles 实际渲染 · 仅排版',font=small,fill=(235,231,218))
canvas.save(OUT/'comparison'/'01_v08_1_vs_v09.png')
canvas.resize((1830,735),Image.Resampling.LANCZOS).save(OUT/'comparison'/'01_v08_1_vs_v09_preview.jpg',quality=94)
print('V09_COMPARISON_READY',flush=True)
