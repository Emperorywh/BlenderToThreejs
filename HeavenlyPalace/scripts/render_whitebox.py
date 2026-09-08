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
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
TAG = "TIANGONG_PHASE1"


def fingerprint(scene, geometry_only=False):
    """记录对象变换、几何、材质和可见性的一致性摘要。
    每次渲染前后比较摘要，以检查机位之间没有隐式改动场景。
    """
    digest = hashlib.sha256()
    for obj in sorted(scene.objects, key=lambda o: o.name):
        if geometry_only and obj.type not in {'MESH', 'CURVE'}:
            continue
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


def apply_comparison_rig(scene, config):
    """为只读 V01 渲染设置与 V02 完全相同的相机和灯光。
    此操作不修改几何、材质或任何模型对象的可见性，也不保存回 V01。
    """
    original = fingerprint(scene, geometry_only=True)
    light_objects = [o for o in scene.objects if o.type == 'LIGHT']
    assert len(light_objects) == len(config["render"]["lights"])
    for p in config["render"]["lights"]:
        obj = next(o for o in light_objects if o.name == "Light_" + p["id"])
        obj.location = p["location"]
        obj.rotation_euler = (Vector(p["target"]) - obj.location).to_track_quat('-Z', 'Y').to_euler()
        obj.data.energy, obj.data.size = p["energy"], p["size"]
        obj.data.shape = 'DISK'
    scene.world.node_tree.nodes['Background'].inputs[0].default_value = config["render"]["world_color"]
    scene.world.node_tree.nodes['Background'].inputs[1].default_value = config["render"]["world_strength"]
    camera_collection = next(c for c in scene.collection.children if c.get("category") == "Cameras")
    for name in ("front", "oblique"):
        p = config["cameras"][name]
        obj = next((o for o in scene.objects if o.type == 'CAMERA' and o.get("view_id") == name), None)
        if obj is None:
            data = bpy.data.cameras.new("Comparison_Camera_" + name)
            obj = bpy.data.objects.new("Comparison_Camera_" + name, data)
            camera_collection.objects.link(obj)
            obj["view_id"] = name
        obj.location = p["location"]
        obj.rotation_euler = (Vector(p["target"]) - obj.location).to_track_quat('-Z', 'Y').to_euler()
        obj.data.type = p["type"]
        obj.data.lens = p["lens"]
        obj.data.sensor_width = 36
        obj.data.clip_start, obj.data.clip_end = .1, 2000
        obj.data.dof.use_dof = False
    scene.view_settings.exposure = config["render"]["exposure"]
    bpy.context.view_layer.update()
    assert fingerprint(scene, geometry_only=True) == original, "对照机位设置改动了 V01 模型"
    return original


def material_signature(scene):
    """记录实际白模材质节点值，用于两个版本间的公平对照。
    忽略自动命名后缀，比较的是颜色、粗糙度和金属度等实际值。
    """
    values = set()
    for obj in scene.objects:
        if obj.type not in {'MESH', 'CURVE'}:
            continue
        for material in obj.data.materials:
            node = material.node_tree.nodes.get('Principled BSDF')
            if node:
                values.add(tuple(round(v, 6) for v in node.inputs['Base Color'].default_value) + (round(node.inputs['Roughness'].default_value, 6), round(node.inputs['Metallic'].default_value, 6), round(node.inputs['Specular IOR Level'].default_value, 6)))
    return sorted(values)


def main():
    """读取工程内嵌配置，并核对它与项目配置一致。
    输出清单保存工程哈希和每张图片哈希，便于追溯最终交付。
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--draft", action="store_true")
    parser.add_argument("--views", nargs="+", default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--baseline-v01", action="store_true")
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    scene = next(s for s in bpy.data.scenes if s.get("task_tag") == TAG)
    bpy.context.window.scene = scene
    config_text = scene["scene_config_json"]
    config = json.loads(config_text)
    assert hashlib.sha256(config_text.encode("utf-8")).hexdigest() == scene["config_sha256"]
    current_text = (ROOT / "scene_config.json").read_text(encoding="utf-8")
    source_revision = config["revision"]
    baseline_geometry = None
    if args.baseline_v01:
        # 基线保留原始工程配置哈希，渲染装置单独使用当前共同比较参数。
        # 两版白模材质配置必须一致，禁止用换材质制造体量改善。
        current_config = json.loads(current_text)
        assert config["materials"] == current_config["materials"]
        baseline_geometry = apply_comparison_rig(scene, current_config)
        config = current_config
    else:
        assert current_text == config_text, "工程与当前配置不同，请先重建"
    saved_path = Path(bpy.data.filepath).resolve()
    assert saved_path.is_relative_to(ROOT) and saved_path.is_file(), "必须先打开项目内已保存的白模工程"
    destination = (ROOT / (args.output or config.get("outputs", {}).get("previews", "output/previews"))).resolve()
    assert destination.is_relative_to(ROOT), "只允许向本项目写入预览"
    destination.mkdir(parents=True, exist_ok=True)
    before = fingerprint(scene)
    original_camera = scene.camera
    views = args.views or (["front", "oblique"] if args.baseline_v01 else list(config["cameras"]))
    manifest = {"source_blend": str(saved_path), "source_blend_sha256": hashlib.sha256(saved_path.read_bytes()).hexdigest(),
                "config_sha256": scene["config_sha256"], "scene_fingerprint": before, "revision": source_revision,
                "blender_version": bpy.app.version_string, "draft": args.draft, "views": [],
                "material_values": material_signature(scene), "shared_lighting": config["render"],
                "actual_lights": [{"name": o.name, "location": list(o.location), "rotation": list(o.rotation_euler), "energy": o.data.energy, "size": o.data.size, "visible": not o.hide_render} for o in sorted(scene.objects, key=lambda o: o.name) if o.type == 'LIGHT'],
                "baseline_model_preserved": baseline_geometry is not None if args.baseline_v01 else None}
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
                                  "actual_camera": {"location": list(camera.location), "rotation": list(camera.rotation_euler), "lens": camera.data.lens, "sensor_width": camera.data.sensor_width, "ortho_scale": camera.data.ortho_scale, "clip": [camera.data.clip_start, camera.data.clip_end], "dof": camera.data.dof.use_dof},
                                  "parameters": p, "resolution": [scene.render.resolution_x, scene.render.resolution_y],
                                  "seconds": round(time.time() - start, 2), "image_sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        print("TIANGONG_RENDER_VIEW " + name, flush=True)
    scene.camera = original_camera
    manifest["same_geometry_and_visibility"] = fingerprint(scene) == before
    (destination / "render_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print("TIANGONG_RENDER_COMPLETE", flush=True)


if __name__ == "__main__":
    main()
