"""
为月门外生成有岩壁层次的山脊和伸向门洞的古松，全部使用真实三维网格。
几何以网页米制坐标设计，再转换到 Blender；同一份顶点用于工程与网页。
"""
import math
import random

import bmesh
import bpy
from mathutils import Vector, noise
from mathutils.bvhtree import BVHTree


def mesh_record(name, vertices, faces, kind="rock", layer=0):
    """
    将网页坐标网格写进 Blender 并计算朝外法线，导出时恢复 Y 向上坐标。
    所有小件按材质合并，古松的枝干和针叶分别只产生一个绘制调用。
    """
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([(x, -z, y) for x, y, z in vertices], [], faces)
    mesh.update()
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    mesh.calc_loop_triangles()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    color = {"rock": (0.30, 0.34, 0.29, 1), "bark": (0.20, 0.13, 0.075, 1),
             "needles": (0.12, 0.21, 0.07, 1)}[kind]
    material = bpy.data.materials.new(name + "_预览材质")
    material.diffuse_color = color
    obj.data.materials.append(material)
    record = {"name": name, "kind": kind, "layer": layer,
              "positions": [[round(v.co.x, 3), round(v.co.z, 3), round(-v.co.y, 3)] for v in mesh.vertices],
              "normals": [[round(v.normal.x, 5), round(v.normal.z, 5), round(-v.normal.y, 5)] for v in mesh.vertices],
              "indices": [int(i) for tri in mesh.loop_triangles for i in tri.vertices]}
    return obj, record


def add_crag(vertices, faces, center, radii, height, rng, sides=20, levels=20):
    """
    岩峰先形成宽肩与陡直壁面，再在上段收成偏斜的破碎峰顶。
    竖向沟槽贯穿多层，低频噪声改变岩块轮廓，避免尖锥和逐环横纹。
    """
    x, bottom, z = center
    rx, rz = radii
    offset = len(vertices)
    phase, lean = rng.uniform(0, math.tau), rng.uniform(-0.22, 0.22) * rx
    for ring in range(levels):
        t = ring / (levels - 1)
        crown = max(0, (t - 0.78) / 0.22)
        radius = (1.12 - 0.42 * t) * (1 - 0.73 * crown ** 1.6)
        for side in range(sides):
            a = math.tau * side / sides
            groove = 1 + 0.15 * math.sin(a * 5 + phase) + 0.075 * math.sin(a * 9 - phase)
            rough = noise.noise_vector(Vector((math.cos(a) * 2.1, math.sin(a) * 2.1, t * 4 + phase)))[0]
            summit = 1 + (0.07 * math.sin(a * 3 + phase) + 0.045 * math.cos(a * 7)) * t ** 4
            vertices.append((x + math.cos(a) * rx * radius * (groove + rough * 0.15) + lean * t,
                             bottom + height * t * summit,
                             z + math.sin(a) * rz * radius * (groove + rough * 0.12)))
    for ring in range(levels - 1):
        for side in range(sides):
            a, b = offset + ring * sides + side, offset + ring * sides + (side + 1) % sides
            faces.extend(((a, b, b + sides), (a, b + sides, a + sides)))
    faces.append(tuple(offset + i for i in reversed(range(sides))))
    faces.append(tuple(offset + (levels - 1) * sides + i for i in range(sides)))


def build_ridges():
    """
    近中远三圈山群替代原有环绕尖峰，殿内正前方保留成片云海与蓝天。
    南侧采用疏密变化的峰群，其余方位保留山脊，使环游也使用完整世界场景。
    """
    records = []
    for layer, distance in enumerate((5300, 9700, 16300)):
        rng = random.Random(6310 + layer)
        noise.seed_set(6310 + layer)
        vertices, faces = [], []
        # 月门正中安排低而破碎的远峰，主峰偏向两侧形成不对称的云谷。
        # 越远的山群角尺寸越小，山脚统一埋进云中而不露出截平底座。
        centers = ((-0.46, -0.40, -0.31, -0.05, 0.015, 0.065, 0.27, 0.34),
                   (-0.52, -0.36, -0.26, -0.10, -0.015, 0.13, 0.19, 0.32),
                   (-0.61, -0.43, -0.20, -0.12, 0.025, 0.08, 0.20, 0.39))[layer]
        for index, slope in enumerate(centers):
            top = rng.uniform(660, 1050) * (1 + layer * 0.40)
            if abs(slope) < 0.12:
                top *= 0.80
            x, z = slope * distance, distance + rng.uniform(-0.10, 0.10) * distance
            width = rng.uniform(160, 300) * (1 + layer * 0.35)
            add_crag(vertices, faces, (x, -950, z), (width, width * 0.8), top + 950, rng)
            add_crag(vertices, faces, (x + width * 0.88, -950, z - width * 0.15),
                     (width * 0.65, width * 0.7), 950 + top * rng.uniform(0.52, 0.76), rng, 14, 14)
        for index in range(16):
            angle = math.tau * index / 16 + 0.07 * layer
            if math.sin(angle) > 0.78:
                continue
            top = rng.uniform(480, 920) * (1 + layer * 0.32)
            add_crag(vertices, faces, (math.cos(angle) * distance, -950, math.sin(angle) * distance),
                     (rng.uniform(220, 420) * (1 + layer * 0.3), 300), top + 950, rng, 14, 14)
        _, record = mesh_record(f"云海山脊_{layer + 1}_破碎峰群", vertices, faces, layer=layer)
        records.append(record)
    return records


def add_branch(vertices, faces, points, radii, sides=9):
    """
    沿弯曲中心线建立逐渐变细的圆截面枝干，保留古松横向伸展与下垂转折。
    各节方向按相邻点计算，枝条连接处相互嵌入，避免离散圆柱的断裂。
    """
    offset = len(vertices)
    for index, point in enumerate(points):
        tangent = (Vector(points[min(index + 1, len(points) - 1)]) - Vector(points[max(0, index - 1)])).normalized()
        axis = tangent.cross(Vector((0, 0, 1))).normalized()
        second = tangent.cross(axis).normalized()
        for side in range(sides):
            angle = math.tau * side / sides
            position = Vector(point) + (axis * math.cos(angle) + second * math.sin(angle)) * radii[index]
            vertices.append(tuple(position))
    for index in range(len(points) - 1):
        for side in range(sides):
            a, b = offset + index * sides + side, offset + index * sides + (side + 1) % sides
            faces.extend(((a, b, b + sides), (a, b + sides, a + sides)))
    faces.append(tuple(offset + side for side in reversed(range(sides))))
    faces.append(tuple(offset + (len(points) - 1) * sides + side for side in range(sides)))


def add_foliage(vertices, faces, center, radius, rng):
    """
    每簇针叶采用不规则扁球实体，组合出古松疏密相间的伞状冠层。
    冠层之间保留透空，明暗由真实法线与统一日光决定，不依赖朝向相机的树片。
    """
    offset, sides, rings = len(vertices), 10, 6
    phase = rng.uniform(0, math.tau)
    for ring in range(rings):
        elevation = -math.pi / 2 + 0.12 + (math.pi - 0.24) * ring / (rings - 1)
        for side in range(sides):
            a = math.tau * side / sides
            ragged = 1 + 0.16 * math.sin(a * 5 + phase) + rng.uniform(-0.12, 0.12)
            vertices.append((center[0] + math.cos(elevation) * math.cos(a) * radius * ragged,
                             center[1] + math.sin(elevation) * radius * 0.28 * ragged,
                             center[2] + math.cos(elevation) * math.sin(a) * radius * 0.68 * ragged))
    for ring in range(rings - 1):
        for side in range(sides):
            a, b = offset + ring * sides + side, offset + ring * sides + (side + 1) % sides
            faces.extend(((a, b, b + sides), (a, b + sides, a + sides)))
    faces.append(tuple(offset + side for side in reversed(range(sides))))
    faces.append(tuple(offset + (rings - 1) * sides + side for side in range(sides)))


def build_gate_landmark():
    """
    殿内相机望向正 Z，画面右侧对应负 X；岩壁放在约两公里外的右侧门缘。
    古松向画面中心伸展，云海从左侧与树冠下穿过，提供明确的近景尺度参照。
    """
    rng = random.Random(920714)
    noise.seed_set(920714)
    rocks, rock_faces, branches, branch_faces, leaves, leaf_faces = [], [], [], [], [], []
    for center, radii, height in (((-365, -640, 1730), (122, 150), 1060),
                                  ((-430, -640, 1810), (108, 132), 1150),
                                  ((-290, -640, 1760), (74, 115), 920),
                                  ((-500, -640, 1870), (100, 125), 1270)):
        add_crag(rocks, rock_faces, center, radii, height, rng, 26, 26)
    trunk = [(-351, 404, 1700), (-342, 434, 1697), (-314, 466, 1698),
             (-297, 508, 1704), (-255, 550, 1712), (-233, 592, 1717)]
    # 根部从实际岩壁向下射线取得落点，主干向上接到已确定的树冠构图。
    # 不用岩峰的名义高度猜测接触点，避免粗糙峰顶收分后古松悬空。
    rock_tree = BVHTree.FromPolygons(rocks, rock_faces)
    contact = rock_tree.ray_cast(Vector((-351, 800, 1700)), Vector((0, -1, 0)), 1600)[0]
    assert contact is not None, "古松根部必须落在实际岩壁上。"
    anchor = (contact.x, contact.y - 1.5, contact.z)
    add_branch(branches, branch_faces, [anchor, (-362, (contact.y + 404) / 2, 1703), trunk[0]], [20, 18, 15])
    add_branch(branches, branch_faces, trunk, (15, 14, 12, 10, 7, 2))
    # 多层主枝有不同的伸展方向和长度，树冠上缘形成斜向门心的轮廓。
    # 下部细枝与根系补足生长逻辑，避免树冠像漂浮在山体上方的独立团块。
    limbs = [(2, (-170, 491, 1683), 7), (3, (-398, 535, 1705), 6),
             (3, (-153, 556, 1719), 7), (4, (-312, 580, 1750), 5),
             (5, (-174, 614, 1709), 4), (2, (-346, 476, 1650), 4)]
    for joint, end, radius in limbs:
        start = Vector(trunk[joint])
        finish = Vector(end)
        middle = start.lerp(finish, 0.52) + Vector((0, -12, -5))
        add_branch(branches, branch_faces, [tuple(start), tuple(middle), end], [radius, radius * 0.65, 1.3])
        for twig in range(5):
            point = middle.lerp(finish, 0.28 + twig * 0.18)
            tip = point + Vector((rng.uniform(-26, 29), rng.uniform(7, 21), rng.uniform(-32, 32)))
            add_branch(branches, branch_faces, [tuple(point), tuple(tip)], [2.2, 0.55], 6)
            for clump in range(5):
                center = tip + Vector((rng.uniform(-20, 20), rng.uniform(-3, 6), rng.uniform(-16, 16)))
                add_foliage(leaves, leaf_faces, center, rng.uniform(12, 23), rng)
    for offset in (-1, 1):
        root_tip = rock_tree.ray_cast(Vector((-351 + offset * 29, 800, 1695)), Vector((0, -1, 0)), 1600)[0]
        if root_tip is not None:
            middle = Vector(anchor).lerp(root_tip, 0.5) + Vector((0, 9, 0))
            add_branch(branches, branch_faces, [anchor, tuple(middle), tuple(root_tip)], [10, 6, 1.6])
    # 岩台缝隙加入少量低灌木，给岩壁与主松之间建立植被过渡。
    # 灌木保持远小于主松的尺度，不在门洞中形成第二个视觉中心。
    for index in range(35):
        point = Vector((-400 + rng.uniform(-48, 32), 800, 1690 + rng.uniform(-34, 30)))
        surface = rock_tree.ray_cast(point, Vector((0, -1, 0)), 1600)[0]
        if surface is not None:
            add_foliage(leaves, leaf_faces, surface + Vector((0, 2, 0)), rng.uniform(8, 16), rng)
    # 将实际根部接触点随几何写入布局，离线核验可直接检查它与岩壁的距离。
    # 元数据不参与网页绘制，只用于确保重建后的模型生长关系没有漂移。
    records = [mesh_record("月门右景_层叠岩壁", rocks, rock_faces, layer=-1)[1],
               mesh_record("月门右景_古松枝干", branches, branch_faces, "bark", -1)[1],
               mesh_record("月门右景_古松针叶", leaves, leaf_faces, "needles", -1)[1]]
    records[1]["anchor"] = [round(value, 3) for value in anchor]
    return records
