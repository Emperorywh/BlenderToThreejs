"""
从正式实渲原图裁取验收重点区域，便于逐像素检查云海边缘和人物接地。
裁图不重绘、不调色，也不作为正式原图的替代品。
"""
import json
from pathlib import Path
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'v09'
image_path=OUT/'renders'/'04_interior.png'
if image_path.exists():
    with Image.open(image_path) as im:
        assert im.size==(1800,1350)
        for name,box in [('interior_moon_bottom',(610,840,1610,1070)),('interior_moon_sides',(490,180,1800,1050)),('interior_person_contact',(900,950,1110,1280)),('interior_column_surface',(0,0,550,1350))]:
            im.crop(box).save(OUT/'qa'/(name+'.png'))
    print('V09_PIXEL_REVIEW_CROPS_READY',flush=True)
