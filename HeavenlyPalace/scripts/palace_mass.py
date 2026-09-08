"""V02 主殿体量：双排柱廊、后退门墙、殿内空间与压紧的三层屋顶。
复用项目几何工具，不添加贴图、精细斗拱或与主殿无关的新建筑。
"""
import math

import bpy
from mathutils import Vector

import whitebox_geometry as G


def column(name, x, y, floor_z, radius, height):
    """柱身与柱础独立建造，明确离墙的空间关系。
    柱顶仅用少量方梁体块表达承托重量，不制作斗拱细节。
    """
    obj = G.cylinder(name, (x, y, floor_z + height / 2), radius, height, "Architecture")
    obj["component_role"] = "hall_column"
    G.cylinder(name + "_Foot", (x, y, floor_z + .28), radius * 1.45, .56, "Architecture", "trim")
    G.box(name + "_Abacus", (x, y, floor_z + height - .18), (1.85, 1.85, .70), "Architecture", "stone")
    return obj


def roof_height(obj, x, y):
    """直接向已重建的曲面屋顶发射射线，求出支撑点高度。
    檐下梁架因此跟随曲面，不再用突出的白色楼层盒子托住薄屋面。
    """
    hit, location, _, _ = obj.ray_cast(Vector((x, y, 1000)), Vector((0, 0, -1)), distance=2000)
    assert hit, "梁架支点没有命中屋面"
    return location.z


def support_band(name, lower, upper, spec, roof_spec, center):
    """在上下屋面间布置矮柱和连续梁带，保留深色空隙。
    没有整块层间外墙，梁带端点高度由真实曲面决定。
    """
    x, y = center
    w, d = spec["width"], spec["depth"]
    corners = [(x - w / 2, y - d / 2), (x + w / 2, y - d / 2), (x + w / 2, y + d / 2), (x - w / 2, y + d / 2)]
    bpy.context.view_layer.update()
    for side, start in enumerate(corners):
        end = corners[(side + 1) % 4]
        count = max(1, math.ceil(math.dist(start, end) / spec["spacing"]))
        points = []
        for i in range(count + 1):
            xx = start[0] + (end[0] - start[0]) * i / count
            yy = start[1] + (end[1] - start[1]) * i / count
            bottom = roof_height(lower, xx, yy) - .08
            top = roof_height(upper, xx, yy) - roof_spec["thickness"] + .08
            assert top > bottom
            if i < count:
                G.box(name + "_ShortPost_%d_%d" % (side, i), (xx, yy, (bottom + top) / 2), (spec["post_width"], spec["post_width"], top - bottom), "Architecture", "stone")
            points.append(Vector((xx, yy, top - spec["beam_height"] / 2)))
        for i in range(count):
            G.beam(name + "_Header_%d_%d" % (side, i), points[i], points[i + 1], spec["beam_height"], "Architecture", "stone")


def build_palace(config):
    """从体量参数重建整座主殿，柱廊与殿内采用可通行的空腔。
    主立面由月门和两侧开间共同组成，避免仅是一面开圆洞的墙。
    """
    h = config["hall"]
    x, y, floor = h["center"]
    width, depth, body_height = h["body_size"]
    xs, ys = h["column_x"], h["column_y"]
    front, rear = ys[0], ys[-1]
    assert abs(xs[-1] - xs[0] - width) < 1e-6
    assert abs(rear - front - depth) < 1e-6
    row_positions = (front, h["inner_column_row_y"], rear)
    column_points = set()
    for yy in row_positions:
        for xx in xs:
            column_points.add((xx, yy))
    for xx in (xs[0], xs[-1]):
        for yy in ys:
            column_points.add((xx, yy))
    for index, (xx, yy) in enumerate(sorted(column_points)):
        column("Hall_Column_%02d" % index, xx, yy, floor, h["column_radius"], h["column_height"])
    header_z = floor + h["column_height"] - .25
    for yy in row_positions:
        G.box("Hall_Colonnade_Header_%g" % yy, (x, yy, header_z), (width + 2.6, 1.05, 1.1), "Architecture", "stone")
    for xx in xs:
        G.box("Hall_Front_RadialBeam_%g" % xx, (xx, (front + h["inner_column_row_y"]) / 2, header_z + .4), (.85, h["inner_column_row_y"] - front + 4.5, 1.0), "Architecture", "stone")
    for xx in (xs[0], xs[-1]):
        G.box("Hall_Side_Header_%g" % xx, (xx, y, header_z), (1.05, depth + 2.6, 1.1), "Architecture", "stone")
    gate = h["main_gate"]
    G.moon_gate("Hall_MainMoon", (x, h["wall_y"], floor), gate["width"], gate["height"], h["wall_thickness"], gate["radius"], gate["center_height"], gate["ring_width"])
    bays = h["facade_bays"]
    pier_positions = set()
    for index, center_x in enumerate(bays["centers"]):
        w = bays["width"]
        for sign in (-1, 1):
            pier_positions.add(center_x + sign * w / 2)
        G.box("Hall_Facade_Sill_%d" % index, (center_x, h["wall_y"], floor + bays["sill_height"] / 2), (w, h["wall_thickness"], bays["sill_height"]), "Architecture")
        top_band = h["wall_height"] - bays["opening_top"]
        G.box("Hall_Facade_Lintel_%d" % index, (center_x, h["wall_y"], floor + bays["opening_top"] + top_band / 2), (w, h["wall_thickness"], top_band), "Architecture")
        # 后退一层的少量竖向门框表达窗洞厚度，并维持殿内实际空间。
        # 这些是开间尺度的结构占位，不是精细门窗花格。
        for sign in (-1, 1):
            G.box("Hall_RecessFrame_%d_%d" % (index, sign), (center_x + sign * (w / 2 - 1.35), h["wall_y"] + 1.1, floor + 7.3), (.25, .38, 12.2), "Architecture", "stone")
    for xx in sorted(pier_positions):
        G.box("Hall_DoorWall_Pier_%g" % xx, (xx, h["wall_y"], floor + h["wall_height"] / 2), (bays["pier_width"], h["wall_thickness"], h["wall_height"]), "Architecture")
    chamber_depth = h["rear_wall_y"] - h["wall_y"]
    for sign in (-1, 1):
        G.box("Hall_Chamber_SideWall_%d" % sign, (sign * h["side_wall_x"], (h["wall_y"] + h["rear_wall_y"]) / 2, floor + h["wall_height"] / 2), (1.2, chamber_depth, h["wall_height"]), "Architecture")
        return_width = h["side_wall_x"] - 5
        G.box("Hall_Chamber_RearWall_%d" % sign, (sign * (5 + return_width / 2), h["rear_wall_y"], floor + h["wall_height"] / 2), (return_width, 1.2, h["wall_height"]), "Architecture")
        for yy in (174, 185):
            column("Hall_InnerAisle_%d_%d" % (sign, yy), sign * 15, yy, floor, h["column_radius"] * .87, h["column_height"])
    G.box("Hall_Chamber_RearHeader", (0, h["rear_wall_y"], floor + 16.6), (10, 1.2, 4.8), "Architecture")
    roofs = [G.roof("Hall_Roof_Tier_%d" % (i + 1), (x, y), p, h) for i, p in enumerate(h["roof_layers"])]
    for i, spec in enumerate(h["roof_support_bands"]):
        support_band("Hall_EaveFrame_%d" % (i + 1), roofs[i], roofs[i + 1], spec, h["roof_layers"][i + 1], (x, y))
    # 最下层挑檐使用有限数量的悬挑梁，与实体屋面下表面衔接。
    # 梁的位置沿柱轴重复，强调建筑重量，不以装饰填满整个屋檐。
    bpy.context.view_layer.update()
    for xx in xs:
        for side in (-1, 1):
            start_y = front + 1.0 if side < 0 else rear - 1.0
            end_y = y + side * (h["roof_layers"][0]["depth"] / 2 - 2.8)
            start_z = roof_height(roofs[0], xx, start_y) - .95
            end_z = roof_height(roofs[0], xx, end_y) - .75
            G.beam("Hall_EaveCantilever_%g_%d" % (xx, side), (xx, start_y, start_z), (xx, end_y, end_z), .60, "Architecture", "stone")
