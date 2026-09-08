"""对白模工程进行与视觉检查互补的实际结构检查。
检查封闭网格、月门贯通、桥梯端点、相机和参数一致性。
"""
import hashlib
import json
from pathlib import Path
import sys

import bpy
import bmesh
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from render_whitebox import fingerprint


def main():
    """在已保存工程中直接检查生成几何。
    结果写入项目报告，不改动交付模型。
    """
    scene = next(s for s in bpy.data.scenes if s.get("task_tag") == "TIANGONG_PHASE1")
    bpy.context.window.scene = scene
    bpy.context.view_layer.update()
    config = json.loads(scene["scene_config_json"])
    report = {"scene": scene.name, "revision": config["revision"], "checks": {}, "issues": [], "routes": [], "portals": [], "mesh_issues": []}
    checked = set()
    for obj in scene.objects:
        if obj.type != 'MESH' or obj.hide_render or obj.data.as_pointer() in checked:
            continue
        checked.add(obj.data.as_pointer())
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        boundary = sum(e.is_boundary for e in bm.edges)
        nonmanifold = sum(not e.is_manifold for e in bm.edges)
        zero_faces = sum(f.calc_area() < 1e-9 for f in bm.faces)
        volume = bm.calc_volume(signed=True)
        bm.free()
        if boundary or nonmanifold or zero_faces or volume <= 0:
            report["mesh_issues"].append({"object": obj.name, "boundary_edges": boundary, "nonmanifold_edges": nonmanifold, "zero_area_faces": zero_faces, "signed_local_volume": volume})
    platform_lookup = {p["id"]: p for p in config["platforms"]}
    for route in config["routes"]:
        checks = []
        for key, platform_key in (("start", "from"), ("end", "to")):
            point = Vector(route[key])
            p = platform_lookup[route[platform_key]]
            obj = next(o for o in scene.objects if o.get("platform_id") == p["id"])
            inverse = obj.matrix_world.inverted()
            # 边界上的精确射线受浮点误差影响，向台面内侧偏移两厘米取样。
            # 同时独立核对原始端点高度，避免偏移掩盖真正的桥台错接。
            inward = Vector((p["center"][0] - point.x, p["center"][1] - point.y, 0)).normalized()
            probe = point + inward * .02
            hit, location, _, _ = obj.ray_cast(inverse @ (probe + Vector((0, 0, 1))), Vector((0, 0, -1)), distance=2)
            actual_error = abs((obj.matrix_world @ location).z - point.z) if hit else None
            checks.append({"endpoint": key, "platform": p["id"], "top_error": abs(point.z - p["center"][2]), "surface_hit": hit, "actual_surface_error": actual_error})
        report["routes"].append({"id": route["id"], "ends": checks})
    for obj in scene.objects:
        if obj.get("component_role") == "moon_gate_opening":
            center = Vector(obj["opening_center"])
            inverse = obj.matrix_world.inverted()
            start = inverse @ (center + Vector((0, -4, 0)))
            hit, _, _, _ = obj.ray_cast(start, Vector((0, 1, 0)), distance=8)
            report["portals"].append({"name": obj.name, "center_ray_unobstructed": not hit})
    report["checks"]["all_rendered_meshes_closed_positive_volume"] = not report["mesh_issues"]
    report["checks"]["six_saved_cameras"] = sum(o.type == 'CAMERA' for o in scene.objects) == 6
    report["checks"]["three_real_moon_openings"] = len(report["portals"]) == 3 and all(p["center_ray_unobstructed"] for p in report["portals"])
    report["checks"]["six_routes_meet_platform_height"] = all(e["top_error"] < 1e-5 for r in report["routes"] for e in r["ends"])
    report["checks"]["all_twelve_endpoints_hit_real_decks"] = all(e["surface_hit"] and e["actual_surface_error"] < 1e-5 for r in report["routes"] for e in r["ends"])
    report["checks"]["configuration_matches_saved_scene"] = hashlib.sha256((ROOT / "scene_config.json").read_bytes()).hexdigest() == scene["config_sha256"]
    report["checks"]["metres_and_origin"] = scene.unit_settings.scale_length == 1 and platform_lookup["Welcome"]["center"] == [0, 0, 0]
    report["checks"]["no_rendering_cloud_helpers"] = all(o.hide_render for o in scene.objects if o.name.startswith("CloudSea_"))
    report["object_count"] = len(scene.objects)
    report["unique_meshes_checked"] = len(checked)
    report["scene_fingerprint"] = fingerprint(scene)
    report["preserved_other_scenes"] = [s.name for s in bpy.data.scenes if s != scene]
    # 保存无关场景的几何摘要，供实际重跑前后比较。
    # 这能验证保留内容未被清理逻辑意外修改，而不依赖对象数量推断。
    report["preserved_other_scene_fingerprints"] = {s.name: fingerprint(s) for s in bpy.data.scenes if s != scene}
    (ROOT / "output" / "validation_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("TIANGONG_VALIDATION " + json.dumps(report, ensure_ascii=True), flush=True)
    if not all(report["checks"].values()):
        raise RuntimeError("结构检查未通过，详见 validation_report.json")


if __name__ == "__main__":
    main()
