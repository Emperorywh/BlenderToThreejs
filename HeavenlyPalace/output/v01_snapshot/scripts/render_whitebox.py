"""重新打开已保存的白模后，输出同一模型的六个验收视图。
渲染只切换活动相机和输出分辨率，不改变几何或可见性。
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys
import time

import bpy

ROOT = Path(__file__).resolve().parents[1]
TAG = "TIANGONG_PHASE1"


def fingerprint(scene):
    """记录对象变换、几何、材质和可见性的一致性摘要。
    每次渲染前后比较摘要，以检查机位之间没有隐式改动场景。
    """
    digest = hashlib.sha256()
    for obj in sorted(scene.objects, key=lambda o: o.name):
        digest.update(obj.name.encode("utf-8"))
        digest.update(struct.pack("16f", *(v for row in obj.matrix_world for v in row)))
        digest.update(bytes((obj.hide_render, obj.hide_viewport)))
        if obj.type == 'MESH':
            for vertex in obj.data.vertices:
                digest.update(struct.pack("3f", *vertex.co))
            for face in obj.data.polygons:
                digest.update(struct.pack("%dI" % len(face.vertices), *face.vertices))
        elif obj.type == 'CURVE':
            for spline in obj.data.splines:
                for point in spline.bezier_points:
                    digest.update(struct.pack("4f", *point.co, point.radius))
        if obj.type in {'MESH', 'CURVE'}:
            for material in obj.data.materials:
                digest.update(material.name.encode("utf-8"))
                digest.update(struct.pack("4f", *material.diffuse_color))
    for col in sorted(scene.collection.children, key=lambda c: c.name):
        digest.update(col.name.encode("utf-8"))
        digest.update(bytes((col.hide_render, col.hide_viewport)))
    return digest.hexdigest()


def main():
    """读取工程内嵌配置，并核对它与项目配置一致。
    输出清单保存工程哈希和每张图片哈希，便于追溯最终交付。
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--draft", action="store_true")
    parser.add_argument("--views", nargs="+", default=None)
    parser.add_argument("--output", default="output/previews")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    scene = next(s for s in bpy.data.scenes if s.get("task_tag") == TAG)
    bpy.context.window.scene = scene
    config_text = scene["scene_config_json"]
    config = json.loads(config_text)
    assert hashlib.sha256(config_text.encode("utf-8")).hexdigest() == scene["config_sha256"]
    assert (ROOT / "scene_config.json").read_text(encoding="utf-8") == config_text, "工程与当前配置不同，请先重建"
    saved_path = Path(bpy.data.filepath).resolve()
    assert saved_path.is_relative_to(ROOT) and saved_path.is_file(), "必须先打开项目内已保存的白模工程"
    destination = (ROOT / args.output).resolve()
    assert destination.is_relative_to(ROOT), "只允许向本项目写入预览"
    destination.mkdir(parents=True, exist_ok=True)
    before = fingerprint(scene)
    original_camera = scene.camera
    views = args.views or list(config["cameras"])
    manifest = {"source_blend": str(saved_path), "source_blend_sha256": hashlib.sha256(saved_path.read_bytes()).hexdigest(),
                "config_sha256": scene["config_sha256"], "scene_fingerprint": before, "revision": config["revision"],
                "blender_version": bpy.app.version_string, "draft": args.draft, "views": []}
    for name in views:
        p = config["cameras"][name]
        camera = next(o for o in scene.objects if o.type == 'CAMERA' and o.get("view_id") == name)
        scene.camera = camera
        size = p.get("resolution", config["render"]["resolution"])
        factor = .625 if args.draft else 1
        scene.render.resolution_x, scene.render.resolution_y = [round(v * factor) for v in size]
        scene.render.resolution_percentage = 100
        scene.cycles.samples = config["render"]["draft_samples" if args.draft else "samples"]
        path = destination / (name + ".png")
        scene.render.filepath = str(path)
        start = time.time()
        assert fingerprint(scene) == before, "机位切换改变了场景内容"
        bpy.ops.render.render(write_still=True)
        assert fingerprint(scene) == before, "渲染期间场景发生改动"
        manifest["views"].append({"view": name, "camera": camera.name, "projection": camera.data.type,
                                  "parameters": p, "resolution": [scene.render.resolution_x, scene.render.resolution_y],
                                  "seconds": round(time.time() - start, 2), "image_sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        print("TIANGONG_RENDER_VIEW " + name, flush=True)
    scene.camera = original_camera
    manifest["same_geometry_and_visibility"] = fingerprint(scene) == before
    (destination / "render_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print("TIANGONG_RENDER_COMPLETE", flush=True)


if __name__ == "__main__":
    main()
