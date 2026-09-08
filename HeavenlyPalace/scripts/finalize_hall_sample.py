"""在最终图片全部保存后生成统一渲染清单，并重新读取本地文件校验哈希。
并排板仅原样粘贴 Blender 渲染像素，不裁切、不缩放、不调色。
"""
import datetime
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    """直接读取落盘文件计算摘要，避免把内存中的旧值当作最终结果。
    原始 PNG、对照板和工程均使用同一 SHA-256 算法。
    """
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    """先制作完全部对照板，再收集最终图片并重建 render_manifest。
    清单写入之后独立重读每个文件，输出实际本地校验记录。
    """
    config_path = ROOT/"hall_sample_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    out = ROOT/config["output_images"]
    before = json.loads((out/"before/render_receipt.json").read_text(encoding="utf-8"))
    after = json.loads((out/"after/render_receipt.json").read_text(encoding="utf-8"))
    report = json.loads((ROOT/"output/sample_v03_build_report.json").read_text(encoding="utf-8"))
    assert not before["draft"] and not after["draft"]
    assert all(report["checks"].values())
    assert before["source_sha256"] == config["base_blend_sha256"] == sha(ROOT/config["base_blend"])
    assert after["source_sha256"] == report["output_sha256"] == sha(ROOT/config["output_blend"])
    assert before["sample_config_sha256"] == after["sample_config_sha256"] == sha(config_path)
    assert sha(ROOT/config["base_config"]) == config["base_config_sha256"]
    for key in ("materials","lights","world","render_settings"):
        assert before[key] == after[key], key
    assert before["same_models_and_visibility_for_all_views"] and after["same_models_and_visibility_for_all_views"]
    labels = {"sample_close":"样板近景", "joint_detail":"柱头与檐下连接", "hall_front":"完整主殿 · 正面", "hall_oblique":"完整主殿 · 斜视"}
    font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc",32)
    small = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc",23)
    images, comparisons = [], []
    bviews = {v["name"]:v for v in before["views"]}
    aviews = {v["name"]:v for v in after["views"]}
    assert set(bviews) == set(aviews) == set(config["cameras"])
    for name in config["cameras"]:
        b, a = bviews[name], aviews[name]
        assert b["camera"] == a["camera"] and b["resolution"] == a["resolution"]
        for variant, view in (("before",b),("after",a)):
            path = Path(view["file"])
            assert path.resolve().is_relative_to(out.resolve()) and sha(path) == view["sha256"]
            with Image.open(path) as check:
                check.load()
                assert list(check.size) == view["resolution"]
            images.append({"file":str(path.relative_to(out)),"kind":"original","variant":variant,"view":name})
        left, right = Image.open(b["file"]).convert("RGB"), Image.open(a["file"]).convert("RGB")
        w,h = left.size
        board = Image.new("RGB",(w*2+64,h+154),(237,237,234))
        board.paste(left,(24,88))
        board.paste(right,(w+40,88))
        draw = ImageDraw.Draw(board)
        draw.text((24,22),"V02 · 冻结基线 / "+labels[name],font=font,fill=(34,38,39))
        draw.text((w+40,22),"V03 · 主殿两开间样板 / "+labels[name],font=font,fill=(34,38,39))
        draw.text((24,h+106),"相同机位、照明和灰模材质；原像素并排。仅正立面右侧两开间完善结构，其余区域保持 V02。",font=small,fill=(55,58,59))
        path = out/("comparison_"+name+".png")
        board.save(path)
        # 从刚保存的对照板重新读回图像区域，验证拼接没有改变源渲染像素。
        # 此处的裁切仅用于检查，不生成经裁切的交付渲染。
        saved = Image.open(path).convert("RGB")
        assert ImageChops.difference(saved.crop((24,88,w+24,h+88)),left).getbbox() is None
        assert ImageChops.difference(saved.crop((w+40,88,w*2+40,h+88)),right).getbbox() is None
        images.append({"file":path.name,"kind":"comparison","view":name})
        comparisons.append({"view":name,"same_actual_camera":True,"source_pixels_unchanged":True,"camera":a["camera"],"resolution":a["resolution"]})
    # 全部最终 PNG 此时都已落盘，下面重新计算清单中的每一个图片哈希。
    # 不复制旧阶段 render_manifest，不把预览图的摘要沿用到最终图。
    for item in images:
        path = out/item["file"]
        item["sha256"] = sha(path)
        item["bytes"] = path.stat().st_size
        with Image.open(path) as img:
            item["resolution"] = list(img.size)
    manifest = {"generated_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),"revision":config["revision"],
                "scope":config["scope"],"sample_config_sha256":sha(config_path),
                "sources":[{"variant":"before","file":config["base_blend"],"sha256":sha(ROOT/config["base_blend"])},
                           {"variant":"after","file":config["output_blend"],"sha256":sha(ROOT/config["output_blend"])}],
                "checks":{"same_lights":True,"same_materials":True,"same_world_and_render":True,
                          "same_model_for_all_after_views":True,"v02_preserved":True,"all_frozen_geometry_checks_pass":True},
                "render_settings":after["render_settings"],"lights":after["lights"],"materials":after["materials"],
                "comparisons":comparisons,"images":images}
    manifest_path = out/"render_manifest.json"
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    reread = json.loads(manifest_path.read_text(encoding="utf-8"))
    verified = [{"file":item["file"],"matches":sha(out/item["file"])==item["sha256"]} for item in reread["images"]]
    assert len(verified)==12 and all(item["matches"] for item in verified)
    verification = {"manifest_sha256":sha(manifest_path),"image_count":len(verified),"all_hashes_match":True,"files":verified}
    (out/"hash_verification.json").write_text(json.dumps(verification,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"manifest":str(manifest_path),"image_count":len(verified),"all_hashes_match":True},ensure_ascii=False))


if __name__ == "__main__":
    main()
