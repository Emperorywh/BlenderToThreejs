"""核验两版的共同机位、实际灯光与白模材质，再制作并排对照板。
原渲染图不裁切、不缩放、不调色，像素原样粘贴，原始图片同时保留。
"""
import hashlib
import json
from pathlib import Path
import shutil

from PIL import Image, ImageChops, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output/comparison"


def sha(path):
    """读取文件内容哈希，核对图片确实来自指定工程版本。
    不依赖文件名或修改时间判断对照是否有效。
    """
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    """生成两张机械拼接对照板，并写入可复核的一致性记录。
    只有真实相机、灯光、材质及源文件检查均通过才交付对照板。
    """
    v1 = json.loads((OUT / "v01/render_manifest.json").read_text(encoding="utf-8"))
    v2 = json.loads((ROOT / "output/previews_v02/render_manifest.json").read_text(encoding="utf-8"))
    source_snapshot = json.loads((ROOT / "output/v01_snapshot/render_manifest.json").read_text(encoding="utf-8"))
    assert v1["source_blend_sha256"] == source_snapshot["source_blend_sha256"] == sha(v1["source_blend"])
    assert v2["source_blend_sha256"] == sha(v2["source_blend"])
    assert v2["config_sha256"] == sha(ROOT / "scene_config.json")
    assert v1["baseline_model_preserved"] and v1["same_geometry_and_visibility"] and v2["same_geometry_and_visibility"]
    assert v1["material_values"] == v2["material_values"]
    assert v1["actual_lights"] == v2["actual_lights"]
    assert v1["shared_lighting"] == v2["shared_lighting"]
    (OUT / "v02").mkdir(exist_ok=True)
    font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 32)
    small = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 22)
    result = {"v01_frozen_blend_unchanged": True, "v02_blend_and_config_match": True, "same_actual_materials": True,
              "same_actual_lights": True, "same_render_settings": True, "v01_model_not_modified_for_comparison": True,
              "all_v02_views_same_scene": True, "views": []}
    for name, label in (("front", "正面"), ("oblique", "斜视")):
        one = next(v for v in v1["views"] if v["view"] == name)
        two = next(v for v in v2["views"] if v["view"] == name)
        assert one["parameters"] == two["parameters"] and one["actual_camera"] == two["actual_camera"]
        assert one["resolution"] == two["resolution"]
        path1, path2 = OUT / "v01" / (name + ".png"), ROOT / "output/previews_v02" / (name + ".png")
        assert sha(path1) == one["image_sha256"] and sha(path2) == two["image_sha256"]
        shutil.copy2(path2, OUT / "v02" / (name + ".png"))
        im1, im2 = Image.open(path1).convert("RGB"), Image.open(path2).convert("RGB")
        w, h = im1.size
        gap, margin, header, footer = 20, 24, 92, 54
        sheet = Image.new("RGB", (2 * w + gap + 2 * margin, h + header + footer), (237, 237, 233))
        positions = [(margin, header), (margin + w + gap, header)]
        sheet.paste(im1, positions[0])
        sheet.paste(im2, positions[1])
        draw = ImageDraw.Draw(sheet)
        draw.text((margin, 18), "V01  ·  冻结基线  /  " + label, font=font, fill=(35, 38, 40))
        draw.text((positions[1][0], 18), "V02  ·  体量与比例修正  /  " + label, font=font, fill=(35, 38, 40))
        draw.text((margin, header + h + 14), "共同机位、相同白模材质和照明。渲染画面原样并排，无裁切、无单独缩放、无调色。", font=small, fill=(65, 67, 68))
        for source, position in zip((im1, im2), positions):
            copied = sheet.crop((position[0], position[1], position[0] + w, position[1] + h))
            assert ImageChops.difference(source, copied).getbbox() is None
        output = OUT / ("comparison_" + name + ".png")
        sheet.save(output)
        result["views"].append({"view": name, "actual_camera_equal": True, "source_pixels_unchanged": True, "v01_image_sha256": sha(path1), "v02_image_sha256": sha(path2), "comparison_sha256": sha(output)})
    (OUT / "comparison_report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
