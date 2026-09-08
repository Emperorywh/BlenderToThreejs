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
    if config["revision"].startswith("V02"):
        # 按实际踏步中心和水平桥段中点采样，不能只核对配置里的端点。
        # 底板、踏步和休息平台即使参数正确，也必须在真实网格上连续命中。
        route_samples = []
        for route in config["routes"]:
            obj = next(o for o in scene.objects if o.get("route_id") == route["id"])
            a, b = Vector(route["start"]), Vector(route["end"])
            direction = Vector((b.x - a.x, b.y - a.y, 0)).normalized()
            parts = route.get("segments") or [{"run": Vector((b.x - a.x, b.y - a.y, 0)).length, "rise": b.z - a.z, "steps": route["steps"]}]
            distance, height = 0, a.z
            errors = []
            for part in parts:
                count = part["steps"] or 1
                for index in range(count):
                    along = distance + part["run"] * (index + .5) / count
                    expected = height + part["rise"] * (index + 1) / count
                    point = a + direction * along
                    hit, location, _, _ = obj.ray_cast(Vector((point.x, point.y, 1000)), Vector((0, 0, -1)), distance=2000)
                    errors.append(abs(location.z - expected) if hit else 1000)
                distance += part["run"]
                height += part["rise"]
            route_samples.append({"route": route["id"], "sample_count": len(errors), "maximum_height_error": max(errors)})
        report["route_surface_samples"] = route_samples
        report["checks"]["every_tread_and_landing_hits_actual_mesh"] = all(r["maximum_height_error"] < .0002 for r in route_samples)
        from inspect_dimensions import bounds
        floor = config["hall"]["center"][2]
        portal = next(o for o in scene.objects if o.name == "Hall_MainMoon_Wall")
        columns = [o for o in scene.objects if o.get("component_role") == "hall_column"]
        first_column = min(columns, key=lambda o: o.location.y)
        clearance = bounds([portal])["min"][1] - bounds([first_column])["max"][1]
        report["clear_colonnade_depth"] = clearance
        report["checks"]["deep_independent_colonnade"] = clearance > 7 and any(abs(o.location.y - config["hall"]["inner_column_row_y"]) < .01 for o in columns)
        depsgraph = bpy.context.evaluated_depsgraph_get()
        start = Vector((0, config["hall"]["column_y"][0] - 2, floor + 1))
        travel = config["hall"]["rear_wall_y"] - start.y + 1
        hit = scene.ray_cast(depsgraph, start, Vector((0, 1, 0)), distance=travel)[0]
        report["checks"]["central_passage_has_real_depth"] = not hit
        report["checks"]["three_roofs_without_storey_boxes"] = sum(o.type == 'MESH' and o.name.startswith("Hall_Roof_Tier_") for o in scene.objects) == 3 and not any(o.name.startswith("Hall_UpperBody_") for o in scene.objects)
        archived = json.loads((ROOT / "output/v01_snapshot/scene_config.json").read_text(encoding="utf-8"))
        report["checks"]["human_and_railing_scale_preserved"] = config["human_height"] == archived["human_height"] and config["railings"] == archived["railings"]
        first_human = bounds([o for o in scene.objects if o.name.startswith("ScaleHuman_01_")])
        report["checks"]["human_actually_stands_at_selected_height"] = abs(first_human["min"][2]) < .0001 and abs(first_human["size"][2] - config["human_height"]) < .0001
        report["checks"]["small_pavilions_not_scaled_with_palace"] = all(p["body_size"] == old["body_size"] and p["roof_size"] == old["roof_size"] for p, old in zip(config["pavilions"], archived["pavilions"]))
        report["checks"]["islands_use_individual_large_masses"] = sum(o.get("component_role") == "island_large_mass" for o in scene.objects) == sum(len(items) for items in config["island_masses"].values())
    report["object_count"] = len(scene.objects)
    report["unique_meshes_checked"] = len(checked)
    report["scene_fingerprint"] = fingerprint(scene)
    report["preserved_other_scenes"] = [s.name for s in bpy.data.scenes if s != scene]
    # 保存无关场景的几何摘要，供实际重跑前后比较。
    # 这能验证保留内容未被清理逻辑意外修改，而不依赖对象数量推断。
    report["preserved_other_scene_fingerprints"] = {s.name: fingerprint(s) for s in bpy.data.scenes if s != scene}
    suffix = config.get("outputs", {}).get("report_suffix", "")
    (ROOT / "output" / ("validation_report" + suffix + ".json")).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("TIANGONG_VALIDATION " + json.dumps(report, ensure_ascii=True), flush=True)
    if not all(report["checks"].values()):
        raise RuntimeError("结构检查未通过，详见 validation_report.json")


if __name__ == "__main__":
    main()
