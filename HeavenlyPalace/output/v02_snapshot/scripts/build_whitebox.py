"""使用本机 Blender Python 构建云顶天宫第一阶段白模。
入口可重跑；只管理本任务标签的数据，保留用户原有场景和对象。
"""
import argparse
import datetime
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import whitebox_geometry as G

SCENE_NAME = "Tiangong_Whitebox"
OUT = ROOT / "output"


def backup_existing(path):
    """覆盖前在项目内备份已有工程。
    此函数只读取明确的工程路径，不移动用户文件。
    """
    path = Path(path)
    if path.is_file():
        backup_dir = OUT / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        shutil.copy2(path, backup_dir / (path.stem + "_" + stamp + path.suffix))


def prepare_scene(config):
    """仅清理带任务标签的对象和空数据块。
    专用场景以外的内容保留，即使脚本在现有工程中运行也不清空场景。
    """
    G.COLLECTIONS.clear()
    G.MATERIALS.clear()
    G.SHARED.clear()
    for obj in list(bpy.data.objects):
        if obj.get("task_tag") == G.TAG:
            bpy.data.objects.remove(obj, do_unlink=True)
    for col in list(bpy.data.collections):
        if col.get("task_tag") == G.TAG and not col.objects and not col.children:
            bpy.data.collections.remove(col)
    for library in (bpy.data.meshes, bpy.data.curves, bpy.data.materials, bpy.data.cameras, bpy.data.lights, bpy.data.worlds):
        for item in list(library):
            if item.get("task_tag") == G.TAG and item.users == 0:
                library.remove(item)
    scene = next((s for s in bpy.data.scenes if s.get("task_tag") == G.TAG), None)
    if scene is None:
        scene = bpy.data.scenes.new(SCENE_NAME)
    scene["task_tag"] = G.TAG
    bpy.context.window.scene = scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.scale_length = config["coordinates"]["unit_scale"]
    names = [("Architecture", "01_建筑_主殿月门亭台"), ("Platforms", "02_平台与台面"),
             ("Bridges", "03_桥梯与桥栏"), ("Bases", "04_悬浮基座"),
             ("Railings", "05_平台栏杆"), ("Plants", "06_古松占位"),
             ("Waterfalls", "07_瀑布占位"), ("Humans", "08_尺度参照"),
             ("Cameras", "09_六个验收相机"), ("Lighting", "10_中性照明"), ("Helpers", "11_非渲染辅助")]
    for key, label in names:
        col = next((c for c in scene.collection.children if c.get("task_tag") == G.TAG and c.get("category") == key), None)
        if col is None:
            col = bpy.data.collections.new("TG_" + label)
            scene.collection.children.link(col)
        col["task_tag"] = G.TAG
        col["category"] = key
        G.COLLECTIONS[key] = col
    for name, rgba in config["materials"].items():
        mat = bpy.data.materials.new("TG_" + name)
        mat["task_tag"] = G.TAG
        mat.diffuse_color = rgba
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        bsdf.inputs["Base Color"].default_value = rgba
        bsdf.inputs["Roughness"].default_value = .87
        bsdf.inputs["Metallic"].default_value = 0
        bsdf.inputs["Specular IOR Level"].default_value = .18
        G.MATERIALS[name] = mat
    return scene


def railing(name, a, b, config, collection="Railings"):
    """栏杆保留柱、上下横杆和稀疏栏芯。
    其尺度统一来自配置，端点位于真实台面或梯段扶手线。
    """
    a, b = Vector(a), Vector(b)
    r = config["railings"]
    length = (b - a).length
    if length < .2:
        return
    count = max(1, math.ceil(length / r["post_spacing"]))
    for i in range(count + 1):
        p = a.lerp(b, i / count)
        # 相邻栏段共用转角与休息平台端柱，避免同位置叠放两根柱子。
        # 缓存仅在本次构建中有效，重跑时会随任务几何一起清空。
        post_key = ("rail_post", collection, *(round(v, 5) for v in p))
        if post_key in G.SHARED:
            continue
        G.SHARED[post_key] = True
        G.box(name + "_Post_%03d" % i, p + Vector((0, 0, r["height"] / 2)), (r["post_size"], r["post_size"], r["height"]), collection, "trim")
        G.box(name + "_Cap_%03d" % i, p + Vector((0, 0, r["height"])), (r["post_size"] * 1.5, r["post_size"] * 1.5, .11), collection, "trim")
    for z in (.32, r["height"] - .12):
        G.beam(name + "_Horizontal_%.2f" % z, a + Vector((0, 0, z)), b + Vector((0, 0, z)), r["beam_size"], collection)
    for i in range(count):
        for fraction in (.33, .67):
            p = a.lerp(b, (i + fraction) / count)
            G.box(name + "_Baluster_%03d_%d" % (i, int(fraction * 100)), p + Vector((0, 0, .65)), (.10, .10, .66), collection, "plaster")


def platform_rails(platform, config):
    """沿平台边缘布栏，并按连接端点自动预留开口。
    瀑布出水口也保留缺口，避免栏杆横穿通道和跌水口。
    """
    x, y, z = platform["center"]
    w, d = platform["size"]
    inset = config["railings"]["edge_inset"]
    pts = [Vector((x + px, y + py, z)) for px, py in G.outline(w - 2 * inset, d - 2 * inset, platform["corner"])]
    openings = []
    for route in config["routes"]:
        if route["from"] == platform["id"]:
            openings.append((Vector(route["start"]), route["width"] / 2 + config["railings"]["portal_clearance"]))
        if route["to"] == platform["id"]:
            openings.append((Vector(route["end"]), route["width"] / 2 + config["railings"]["portal_clearance"]))
    for fall in config["waterfalls"]:
        if abs(fall["lip"][2] - z) < .01:
            openings.append((Vector(fall["lip"]), fall["width"] / 2 + .35))
    for index, a in enumerate(pts):
        b = pts[(index + 1) % len(pts)]
        direction = (b - a).normalized()
        length = (b - a).length
        exclusions = []
        for p, half in openings:
            along = (p - a).dot(direction)
            distance = ((p - a) - along * direction).length
            if distance < 1 and -half < along < length + half:
                exclusions.append((max(0, along - half), min(length, along + half)))
        cursor = 0
        for start, end in sorted(exclusions) + [(length, length)]:
            if start > cursor:
                railing("Rail_%s_E%d_%.1f" % (platform["id"], index, cursor), a + direction * cursor, a + direction * start, config)
            cursor = max(cursor, end)


def platforms(config):
    """台面、承托边带和倒锥基座分别可选。
    所有基座封底，收分属于背面和底部的补充设计。
    """
    for p in config["platforms"]:
        x, y, z = p["center"]
        w, d = p["size"]
        c, slab, drop = p["corner"], p["slab"], p["base_depth"]
        top = G.loft("Platform_" + p["id"] + "_Deck", (x, y), [(w, d, c, z - slab), (w, d, c, z)], "Platforms", "plaster")
        top["component_role"] = "platform_deck"
        top["platform_id"] = p["id"]
        top["top_z"] = z
        G.loft("Base_" + p["id"] + "_Rim", (x, y), [(w * .97, d * .97, c, z - slab - 1), (w * 1.015, d * 1.015, c, z - slab + .05)], "Bases", "trim")
        # V02 保留人工高台的水平承托带，下面改由不同大块形成轮廓。
        # 旧版参数仍可走原始基座逻辑，便于保留可复用构件。
        if p["id"] in config.get("island_masses", {}):
            shoulder_depth = 5.1 if p["id"] == "Main" else 3.5
            G.loft("Base_" + p["id"] + "_ArchitecturalShoulder", (x, y), [(w * .92, d * .92, c, z - shoulder_depth), (w * .97, d * .97, c, z - slab - 1)], "Bases", "plaster")
            for index, spec in enumerate(config["island_masses"][p["id"]]):
                center = Vector(p["center"]) + Vector(spec["offset"])
                G.rock_mass("Base_%s_LargeMass_%02d" % (p["id"], index), center, spec)
            platform_rails(p, config)
            continue
        G.loft("Base_" + p["id"] + "_Shoulder", (x, y), [(w * .83, d * .83, c * 1.3, z - drop * .30), (w * .97, d * .97, c, z - slab - 1)], "Bases", "stone")
        G.loft("Base_" + p["id"] + "_Taper", (x, y), [(w * .36, d * .36, c * .7, z - drop), (w * .58, d * .58, c, z - drop * .78), (w * .83, d * .83, c * 1.3, z - drop * .30)], "Bases", "stone")
        G.loft("Base_" + p["id"] + "_Belt", (x, y), [(w * .85, d * .85, c * 1.3, z - drop * .30 - .35), (w * .86, d * .86, c * 1.3, z - drop * .30 + .18)], "Bases", "plaster")
        platform_rails(p, config)


def route_geometry(route, config):
    """把踏步节奏与休息平台挤出成封闭的桥梯实体。
    首尾边界严格取配置端点，扶手沿相同分段坡度生成。
    """
    a, b = Vector(route["start"]), Vector(route["end"])
    horizontal = Vector((b.x - a.x, b.y - a.y, 0))
    length = horizontal.length
    forward = horizontal.normalized()
    across = Vector((forward.y, -forward.x, 0))
    steps = route["steps"]
    width = route["width"]
    profile = [(0, a.z)]
    rail_keys = [(0, a.z)]
    # 分段路径允许平桥、梯段和休息平台组成真正的登临序列。
    # 底板也沿分段坡度生成，不能用一条斜底面穿过水平桥面。
    if route.get("segments"):
        distance, height = 0, a.z
        segment_stats = []
        for part in route["segments"]:
            count = part["steps"]
            if count:
                tread, rise = part["run"] / count, part["rise"] / count
                for i in range(count):
                    height += rise
                    profile.append((distance, height))
                    distance += tread
                    profile.append((distance, height))
            else:
                assert part["rise"] == 0
                distance += part["run"]
                profile.append((distance, height))
            rail_keys.append((distance, height))
            segment_stats.append({**part, "tread": part["run"] / count if count else None, "riser": part["rise"] / count if count else 0})
        assert abs(distance - length) < 1e-5 and abs(height - b.z) < 1e-5
        assert sum(part["steps"] for part in route["segments"]) == steps
    elif steps:
        every = route["landing_every"]
        landings = (steps - 1) // every if every else 0
        tread = (length - landings * route["landing_length"]) / steps
        rise = (b.z - a.z) / steps
        distance = 0
        for i in range(steps):
            height = a.z + rise * (i + 1)
            profile.append((distance, height))
            distance += tread
            profile.append((distance, height))
            if every and (i + 1) % every == 0 and i + 1 < steps:
                rail_keys.append((distance, height))
                distance += route["landing_length"]
                profile.append((distance, height))
                rail_keys.append((distance, height))
    else:
        profile.append((length, b.z))
        tread, rise = 0, 0
    if rail_keys[-1] != (length, b.z):
        if abs(rail_keys[-1][0] - length) < 1e-5:
            rail_keys[-1] = (length, b.z)
        else:
            rail_keys.append((length, b.z))
    profile[-1] = (length, b.z)
    profile.extend([(distance, height - route["thickness"]) for distance, height in reversed(rail_keys)])
    verts = []
    for side in (-1, 1):
        for distance, z in profile:
            point = a + forward * distance + across * width / 2 * side
            verts.append((point.x, point.y, z))
    n = len(profile)
    faces = [tuple(reversed(range(n))), tuple(range(n, 2 * n))]
    faces += [(i, (i + 1) % n, (i + 1) % n + n, i + n) for i in range(n)]
    obj = G.mesh_object("Bridge_" + route["id"] + "_SolidSteps", verts, faces, "Bridges", "plaster")
    obj["component_role"] = "route"
    obj["route_id"] = route["id"]
    obj["start"] = list(a)
    obj["end"] = list(b)
    obj["step_rise"] = rise
    obj["step_run"] = tread
    if route.get("segments"):
        obj["segments_json"] = json.dumps(segment_stats)
    for side in (-1, 1):
        for index in range(len(rail_keys) - 1):
            s0, z0 = rail_keys[index]
            s1, z1 = rail_keys[index + 1]
            start = a + forward * s0 + across * side * (width / 2 - .22)
            end = a + forward * s1 + across * side * (width / 2 - .22)
            start.z, end.z = z0, z1
            railing("Bridge_%s_Rail_%d_%d" % (route["id"], side, index), start, end, config, "Bridges")
    return {"id": route["id"], "horizontal_length": length, "rise": b.z - a.z, "slope_degrees": math.degrees(math.atan2(b.z - a.z, length)), "step_rise": rise, "step_run": tread, "segments": segment_stats if route.get("segments") else []}


def hall(config):
    """主殿由柱网、贯穿月门、侧墙与三层曲面屋顶组成。
    未展示的后部用开敞柱廊与薄墙补全，不虚构另一座大型建筑。
    """
    h = config["hall"]
    # 体量版主殿采用独立双排柱廊、后退门墙和实际殿内空间。
    # 继续复用圆柱、月门及曲面屋顶工具，旧版分支保留供历史参数重建。
    if h.get("roof_support_bands"):
        from palace_mass import build_palace
        return build_palace(config)
    x, y, z = h["center"]
    front, back = h["column_y"][0], h["column_y"][-1]
    # 主体宽深高参与实际墙体和梁架生成，不只作为说明性字段保存。
    # 柱网采用绝对坐标，配置中的体量必须与该柱网相容。
    body_width, body_depth, body_height = h["body_size"]
    assert abs(h["column_x"][-1] - h["column_x"][0] - body_width) < 1e-6
    assert abs(back - front - body_depth) < 1e-6
    gate = h["main_gate"]
    panel_width = (body_width - gate["width"]) / 2
    side_wall_x = body_width / 2 - 2.5
    header_z = z + body_height - .9
    for xx in h["column_x"]:
        for yy in (front, back):
            label = "Hall_Column_%g_%g" % (xx, yy)
            col = G.cylinder(label, (xx, yy, z + h["column_height"] / 2), h["column_radius"], h["column_height"], "Architecture")
            col["component_role"] = "hall_column"
            G.cylinder(label + "_Foot", (xx, yy, z + .24), h["column_radius"] * 1.48, .48, "Architecture", "trim")
            G.box(label + "_Capital", (xx, yy, z + h["column_height"] - .22), (1.65, 1.65, .65), "Architecture", "trim")
    for xx in (h["column_x"][0], h["column_x"][-1]):
        for yy in h["column_y"][1:-1]:
            col = G.cylinder("Hall_SideColumn_%g_%g" % (xx, yy), (xx, yy, z + h["column_height"] / 2), h["column_radius"], h["column_height"], "Architecture")
            col["component_role"] = "hall_column"
            G.cylinder(col.name + "_Foot", (xx, yy, z + .24), h["column_radius"] * 1.48, .48, "Architecture", "trim")
    for yy in (front, back):
        G.box("Hall_Header_%g" % yy, (x, yy, header_z), (body_width + 2, 1.3, 1.3), "Architecture", "stone")
    for xx in (h["column_x"][0], h["column_x"][-1]):
        G.box("Hall_SideHeader_%g" % xx, (xx, y, header_z), (1.3, body_depth, 1.3), "Architecture", "stone")
    G.moon_gate("Hall_MainMoon", (0, h["wall_y"], z), gate["width"], gate["height"], h["wall_thickness"], gate["radius"], gate["center_height"], gate["ring_width"])
    for sign in (-1, 1):
        G.box("Hall_FrontWall_%d" % sign, (x + sign * (gate["width"] / 2 + panel_width / 2), h["wall_y"], z + h["wall_height"] / 2), (panel_width, h["wall_thickness"], h["wall_height"]), "Architecture")
        G.box("Hall_SideWall_%d" % sign, (x + sign * side_wall_x, (h["wall_y"] + back) / 2, z + h["wall_height"] / 2), (1, back - h["wall_y"] - 1, h["wall_height"]), "Architecture")
        G.box("Hall_RearReturn_%d" % sign, (x + sign * (side_wall_x - 5), back - .8, z + h["wall_height"] / 2), (10, 1, h["wall_height"]), "Architecture")
        for xx in (gate["width"] / 2 + panel_width * .25, gate["width"] / 2 + panel_width * .75):
            G.box("Hall_FacadeInset_%g" % (xx * sign), (xx * sign, h["wall_y"] - .52, z + 6.8), (4.8, .12, 9.8), "Architecture", "stone")
    for i, p in enumerate(h["clerestories"]):
        G.box("Hall_UpperBody_%d" % (i + 1), (0, y, p["center_z"]), p["size"], "Architecture", "plaster")
    for i, p in enumerate(h["roof_layers"]):
        G.roof("Hall_Roof_Tier_%d" % (i + 1), (0, y), p, h)


def side_architecture(config):
    """两个月门与两个小亭按同一布局分别建立。
    小亭维持开敞柱式体量，层数和尺寸不压过主殿。
    """
    for p in config["side_gates"]:
        x, y, z = p["center"]
        G.moon_gate(p["id"], p["center"], p["width"], p["height"], p["thickness"], p["radius"], p["center_height"], p["ring_width"])
        for sign in (-1, 1):
            G.box(p["id"] + "_Pier_%d" % sign, (x + sign * (p["width"] / 2 - .45), y, z + p["height"] / 2), (1.0, 1.65, p["height"]), "Architecture", "trim")
        G.roof(p["id"] + "_Roof", (x, y), {"width": p["roof_width"], "depth": p["roof_depth"], "eave_z": z + p["height"], "rise": p["roof_rise"], "corner_lift": .65, "edge_lift": .12}, config["hall"])
    for p in config["pavilions"]:
        x, y, z = p["center"]
        w, d, h = p["body_size"]
        for sx in (-1, 1):
            for sy in (-1, 1):
                G.cylinder(p["id"] + "_Column_%d_%d" % (sx, sy), (x + sx * w / 2, y + sy * d / 2, z + h / 2), p["column_radius"], h, "Architecture")
        for sy in (-1, 1):
            G.box(p["id"] + "_HeaderY_%d" % sy, (x, y + sy * d / 2, z + h - .2), (w + .5, .5, .55), "Architecture", "stone")
        for sx in (-1, 1):
            G.box(p["id"] + "_HeaderX_%d" % sx, (x + sx * w / 2, y, z + h - .2), (.5, d + .5, .55), "Architecture", "stone")
        for tier, scale in enumerate((1, .72)):
            G.roof(p["id"] + "_Roof_%d" % tier, (x, y), {"width": p["roof_size"][0] * scale, "depth": p["roof_size"][1] * scale, "eave_z": z + h + tier * 2.2, "rise": p["roof_rise"] * (.85 if tier else 1), "corner_lift": .75, "edge_lift": .10}, config["hall"])


def landscape(config):
    """放置古松、独立瀑布几何和少量尺度人物。
    云海只使用非渲染辅助平面，实际渲染保持无遮挡。
    """
    for p in config["pines"]:
        G.pine(p)
    for p in config["waterfalls"]:
        x, y, z = p["lip"]
        width, drop = p["width"], p["drop"]
        verts = []
        nx, nz = 12, 20
        for back in (0, 1):
            for j in range(nz + 1):
                t = j / nz
                for i in range(nx + 1):
                    u = i / nx
                    outward = .13 + .75 * (1 - math.exp(-t * 8))
                    xx = x + (u - .5) * width * (1 + .08 * t)
                    yy = y - outward + .1 * math.sin(u * math.pi * 8 + t * 3) + back * .18
                    zz = z - drop * t + .10 * math.sin(u * math.pi * 6) * t
                    verts.append((xx, yy, zz))
        n = (nx + 1) * (nz + 1)
        faces = []
        for offset in (0, n):
            for j in range(nz):
                for i in range(nx):
                    k = j * (nx + 1) + i + offset
                    faces.append((k, k + 1, k + nx + 2, k + nx + 1))
        boundary = list(range(nx + 1)) + [j * (nx + 1) + nx for j in range(1, nz + 1)] + list(range(n - 2, n - nx - 2, -1)) + [j * (nx + 1) for j in range(nz - 1, 0, -1)]
        faces += [(k, boundary[(i + 1) % len(boundary)], boundary[(i + 1) % len(boundary)] + n, k + n) for i, k in enumerate(boundary)]
        obj = G.mesh_object(p["id"] + "_Placeholder", verts, faces, "Waterfalls", "water")
        obj["component_role"] = "waterfall_placeholder"
        G.box(p["id"] + "_Outlet", (x, y + .25, z + .06), (width, .8, .12), "Waterfalls", "water")
    h = config["human_height"]
    for i, base in enumerate(config["humans"]):
        x, y, z = base
        name = "ScaleHuman_%02d" % (i + 1)
        for sign in (-1, 1):
            # 补足 V01 人形脚底约六厘米的空隙，头顶标高保持原定尺度。
            # 这是落脚修正，人物并不随主殿或桥梯扩大。
            if config["revision"].startswith("V02"):
                G.box(name + "_Foot_%d" % sign, (x + sign * .10, y - .03, z + .05), (.16, .28, .10), "Humans", "human")
            G.beam(name + "_Leg_%d" % sign, (x + sign * .10, y, z + .06), (x + sign * .09, y, z + h * .48), .13, "Humans", "human")
            G.beam(name + "_Arm_%d" % sign, (x + sign * .21, y, z + h * .75), (x + sign * .30, y -.04, z + h * .48), .11, "Humans", "human")
        G.box(name + "_Torso", (x, y, z + h * .62), (.37, .22, h * .32), "Humans", "human")
        G.cylinder(name + "_Neck", (x, y, z + h * .80), .065, .12, "Humans", "human")
        head = G.cylinder(name + "_Head", (x, y, z + h - .145), .118, .29, "Humans", "human", 12)
        head["design_height_m"] = h
    marker = G.box("CloudSea_Level_Helper", (0, 58, config["cloud_marker_z"]), (166, 155, .02), "Helpers", "stone")
    marker.hide_render = True
    marker.display_type = 'WIRE'
    marker["description"] = "云海高度辅助，仅作空间标记，不参与渲染"
    origin = G.register(bpy.data.objects.new("Origin_Welcome_Z0_Y_to_Hall", None), "Helpers")
    origin.empty_display_type = 'ARROWS'
    origin.empty_display_size = 4


def setup_render(scene, config):
    """固定六个相机和同一套中性光照。
    相机不随渲染视角移动建筑，也不切换任何几何可见性。
    """
    render = config["render"]
    world = bpy.data.worlds.new("TG_NeutralWorld")
    world["task_tag"] = G.TAG
    world.use_nodes = True
    world.node_tree.nodes['Background'].inputs[0].default_value = render["world_color"]
    world.node_tree.nodes['Background'].inputs[1].default_value = render["world_strength"]
    scene.world = world
    for p in render["lights"]:
        data = bpy.data.lights.new("TG_" + p["id"], 'AREA')
        data.energy = p["energy"]
        data.shape = 'DISK'
        data.size = p["size"]
        obj = G.register(bpy.data.objects.new("Light_" + p["id"], data), "Lighting")
        obj.location = p["location"]
        obj.rotation_euler = (Vector(p["target"]) - obj.location).to_track_quat('-Z', 'Y').to_euler()
    for name, p in config["cameras"].items():
        data = bpy.data.cameras.new("TG_Camera_" + name)
        data.type = p["type"]
        data.clip_start, data.clip_end = .1, 2000
        data.dof.use_dof = False
        if data.type == 'ORTHO':
            data.ortho_scale = p["ortho_scale"]
        else:
            data.lens = p["lens"]
            data.sensor_width = 36
        obj = G.register(bpy.data.objects.new("Camera_" + name, data), "Cameras")
        obj.location = p["location"]
        obj.rotation_euler = (Vector(p["target"]) - obj.location).to_track_quat('-Z', 'Y').to_euler()
        obj["view_id"] = name
    scene.camera = bpy.data.objects["Camera_overview"]
    scene.render.engine = render["engine"]
    scene.cycles.device = 'CPU'
    scene.cycles.samples = render["samples"]
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 6
    scene.render.resolution_x, scene.render.resolution_y = render["resolution"]
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGB'
    scene.render.film_transparent = False
    scene.view_settings.view_transform = 'AgX'
    scene.view_settings.exposure = render["exposure"]
    scene.render.filepath = str(ROOT / config.get("outputs", {}).get("previews", "output/previews") / "overview.png")
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                area.spaces.active.region_3d.view_perspective = 'CAMERA'
                area.spaces.active.clip_end = 2000


def main():
    """从唯一配置构建并保存首版或修订版工程。
    默认仅构建，渲染脚本在独立 Blender 进程中重新打开已保存工程。
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=str(ROOT / "scene_config.json"))
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    config_path = Path(args.config).resolve()
    if not config_path.is_relative_to(ROOT):
        raise ValueError("配置必须位于当前项目内")
    config_text = config_path.read_text(encoding="utf-8")
    config = json.loads(config_text)
    OUT.mkdir(exist_ok=True)
    preview_dir = (ROOT / config.get("outputs", {}).get("previews", "output/previews")).resolve()
    target = (ROOT / config.get("outputs", {}).get("blend", "output/tiangong_whitebox.blend")).resolve()
    # V01 和 V02 使用独立交付路径，避免重跑覆盖已经冻结的对照基线。
    # 所有输出必须继续位于当前项目，不允许配置逃逸到外部目录。
    assert target.is_relative_to(ROOT) and preview_dir.is_relative_to(ROOT)
    preview_dir.mkdir(exist_ok=True, parents=True)
    backup_existing(target)
    scene = prepare_scene(config)
    platforms(config)
    route_stats = [route_geometry(route, config) for route in config["routes"]]
    hall(config)
    side_architecture(config)
    landscape(config)
    setup_render(scene, config)
    scene["scene_config_json"] = config_text
    scene["config_sha256"] = hashlib.sha256(config_text.encode("utf-8")).hexdigest()
    scene["design_revision"] = config["revision"]
    scene["reference_priority"] = "01_overview > 02_front > 03_oblique > 04_waterfall_side；布局仅以01为准"
    scene["phase"] = "PHASE1_WHITEBOX_REVIEW_ONLY"
    # 工程内保留与当前版本一致的设计边界，避免误称不可见区域的精确还原。
    # 体量、内部梁架和岛底大块仍属于白模阶段的补充设计。
    scene["supplemental_design"] = "尺寸为设计假设；背面、内部梁架、岛底大块与不可见连接均为补充设计"
    bpy.context.view_layer.update()
    for obj in bpy.context.selected_objects:
        obj.select_set(False)
    bpy.context.view_layer.objects.active = None
    bpy.ops.wm.save_as_mainfile(filepath=str(target), compress=True)
    report = {"blender_version": bpy.app.version_string, "scene": scene.name, "revision": config["revision"],
              "config_sha256": scene["config_sha256"], "object_count": len(scene.objects),
              "collections": {key: len(col.objects) for key, col in G.COLLECTIONS.items()}, "routes": route_stats,
              "mesh_count": len({o.data.as_pointer() for o in scene.objects if o.type == 'MESH'}),
              "camera_count": sum(o.type == 'CAMERA' for o in scene.objects), "saved_blend": str(target)}
    suffix = config.get("outputs", {}).get("report_suffix", "")
    (OUT / ("build_report" + suffix + ".json")).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("TIANGONG_BUILD_COMPLETE " + json.dumps(report, ensure_ascii=True), flush=True)


if __name__ == "__main__":
    main()
