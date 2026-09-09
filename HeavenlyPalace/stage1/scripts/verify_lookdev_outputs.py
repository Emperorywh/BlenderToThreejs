"""
核实七张交付图片均为实际生成的完整PNG，记录尺寸、文件摘要与高亮像素比例。
只读取图片进行统计，不裁切、不调色、不重绘，也不改变Blender原始渲染结果。
"""
import json
import hashlib
from pathlib import Path
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'v08'
names=['01_oblique','02_front','03_aerial','04_interior','05_hero_pine','06_waterfall','07_neutral_environment']
records=[]
for name in names:
    path=OUT/'renders'/(name+'.png')
    if not path.exists():
        records.append({'name':name,'exists':False})
        continue
    with Image.open(path) as im:
        im.load()
        rgb=im.convert('RGB')
        histogram=rgb.histogram()
        near_white=sum(1 for r,g,b in rgb.getdata() if min(r,g,b)>=250)
        near_black=sum(1 for r,g,b in rgb.getdata() if max(r,g,b)<=3)
        records.append({'name':name,'exists':True,'size':list(im.size),'mode':im.mode,'format':im.format,'bytes':path.stat().st_size,
                        'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'near_white_fraction':round(near_white/(im.width*im.height),6),
                        'near_black_fraction':round(near_black/(im.width*im.height),6),'extrema':rgb.getextrema()})
report={'images':records,'passed':all(r.get('exists') and r.get('size')==[1800,1350] and r.get('format')=='PNG' for r in records)}
(OUT/'qa'/'image_verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
if not report['passed']:
    raise SystemExit(1)
