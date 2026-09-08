"""云顶天宫白模的可复用几何工具。
只创建带任务标签的数据，不依赖外部资产或插件。
"""
import math
import random

import bpy
import bmesh
from mathutils import Vector

TAG = "TIANGONG_PHASE1"
COLLECTIONS = {}
MATERIALS = {}
SHARED = {}


def register(obj, collection, material=None):
    """把新对象连接到专用集合并标注来源。
    共享网格使用同一材质，以便后续独立移动重复构件。
    """
    obj["task_tag"] = TAG
    if obj.data:
        obj.data["task_tag"] = TAG
    COLLECTIONS[collection].objects.link(obj)
    if material and len(obj.data.materials) == 0:
        obj.data.materials.append(MATERIALS[material])
    return obj


def mesh_object(name, vertices, faces, collection, material):
    """创建独立、可编辑的真实网格并统一法线。
    所有实体使用封闭面组，不以渲染贴片代替几何。
    """
    mesh = bpy.data.meshes.new(name + "_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(mesh)
    bm.free()
    return register(bpy.data.objects.new(name, mesh), collection, material)


def box(name, center, size, collection, material="plaster"):
    """方形构件复用单位立方体网格。
    长宽高保留在对象变换中，方便白模阶段直接调整。
    """
    key = ("box", material)
    if key not in SHARED:
        obj = mesh_object(name, [(x, y, z) for x in (-.5, .5) for y in (-.5, .5) for z in (-.5, .5)],
                          [(0, 4, 6, 2), (1, 3, 7, 5), (0, 1, 5, 4), (2, 6, 7, 3), (0, 2, 3, 1), (4, 5, 7, 6)], collection, material)
        SHARED[key] = obj.data
    else:
        obj = register(bpy.data.objects.new(name, SHARED[key]), collection)
    obj.location = center
    obj.scale = size
    return obj


def cylinder(name, center, radius, height, collection, material="plaster", segments=20):
    """柱子、柱础等采用共享的封闭圆柱。
    端面保持平面，侧面仅做法线平滑而不增加细分。
    """
    key = ("cylinder", material, segments)
    if key not in SHARED:
        verts = [(math.cos(i * math.tau / segments), math.sin(i * math.tau / segments), z)
                 for z in (-.5, .5) for i in range(segments)]
        faces = [tuple(reversed(range(segments))), tuple(range(segments, 2 * segments))]
        faces += [(i, (i + 1) % segments, (i + 1) % segments + segments, i + segments) for i in range(segments)]
        obj = mesh_object(name, verts, faces, collection, material)
        for polygon in obj.data.polygons[2:]:
            polygon.use_smooth = True
        SHARED[key] = obj.data
    else:
        obj = register(bpy.data.objects.new(name, SHARED[key]), collection)
    obj.location = center
    obj.scale = (radius, radius, height)
    return obj


def beam(name, start, end, width, collection, material="trim", depth=None):
    """连接两个真实端点，可用于栏杆和斜向构件。
    使用对象旋转保证坡道两侧扶手与实际路径一致。
    """
    a, b = Vector(start), Vector(end)
    obj = box(name, (a + b) / 2, (width, depth or width, (b - a).length), collection, material)
    obj.rotation_euler = (b - a).to_track_quat('Z', 'Y').to_euler()
    return obj


def curve(name, points, radius, collection, material, radii=None):
    """创建有实体截面的平滑空间曲线。
    树干的半径可逐点收细，屋脊和檐线则保持一致。
    """
    data = bpy.data.curves.new(name + "_Curve", 'CURVE')
    data.dimensions = '3D'
    data.resolution_u = 5
    data.bevel_depth = radius
    data.bevel_resolution = 2
    data.use_fill_caps = True
    spline = data.splines.new('BEZIER')
    spline.bezier_points.add(len(points) - 1)
    for index, (point, co) in enumerate(zip(spline.bezier_points, points)):
        point.co = co
        point.handle_left_type = 'AUTO'
        point.handle_right_type = 'AUTO'
        point.radius = radii[index] if radii else 1
    return register(bpy.data.objects.new(name, data), collection, material)


def outline(width, depth, corner):
    """返回切角矩形的逆时针轮廓。
    台面、饰带和收分基座共享轮廓拓扑以避免开底。
    """
    x, y, c = width / 2, depth / 2, corner
    return [(-x + c, -y), (x - c, -y), (x, -y + c), (x, y - c),
            (x - c, y), (-x + c, y), (-x, y - c), (-x, -y + c)]


def loft(name, center_xy, rings, collection, material):
    """连接多层切角截面，并封闭顶部与底部。
    每层参数依次为宽、深、切角和绝对高度。
    """
    verts = [(x + center_xy[0], y + center_xy[1], z)
             for w, d, c, z in rings for x, y in outline(w, d, c)]
    faces = [tuple(reversed(range(8))), tuple(range(len(verts) - 8, len(verts)))]
    for j in range(len(rings) - 1):
        faces += [(j * 8 + i, j * 8 + (i + 1) % 8, (j + 1) * 8 + (i + 1) % 8, (j + 1) * 8 + i) for i in range(8)]
    return mesh_object(name, verts, faces, collection, material)


def roof(name, center_xy, p, hall_config, collection="Architecture"):
    """用连续矩形截面生成中式庑殿屋顶，包含弧坡、出檐和角部起翘。
    屋面带封闭厚度，所有相机共用这份网格，不使用视角变形。
    """
    a, b = p["width"] / 2, p["depth"] / 2
    # 顶层主殿可延长正脊，让上部屋面具有更明确的横向展开。
    # 调整发生在参数生成阶段，既有屋顶网格不会被缩放拉伸。
    ridge = a * p["ridge_fraction"] if "ridge_fraction" in p else max(a - b * .86, a * .12)
    ns, nr = hall_config["roof_edge_segments"], hall_config["roof_ring_segments"]
    perimeter = []
    for side in range(4):
        for i in range(ns):
            u = i / ns
            perimeter.append([(-1 + 2 * u, -1), (1, -1 + 2 * u), (1 - 2 * u, 1), (-1, 1 - 2 * u)][side])
    n = len(perimeter)
    verts = []
    for lower in (False, True):
        for j in range(nr + 1):
            t = .002 + .998 * j / nr
            hx, hy = ridge + (a - ridge) * t, b * t
            for u, v in perimeter:
                # 每层屋顶单独定义弧坡和厚度，调整参数后重新生成所有顶点。
                # 侧门和小亭继续使用原有默认值，不随主殿一起放大。
                z = p["eave_z"] + p["rise"] * (1 - t) ** p.get("curve_power", hall_config["roof_curve_power"])
                z += p["corner_lift"] * t ** 6 * abs(u * v) ** 5 + p["edge_lift"] * t ** 8
                z += .22 * abs(u) ** 8 * (1 - t) ** 8
                verts.append((center_xy[0] + hx * u, center_xy[1] + hy * v, z - (p.get("thickness", hall_config["roof_thickness"]) if lower else 0)))
    count = n * (nr + 1)
    faces = []
    for offset in (0, count):
        for j in range(nr):
            for i in range(n):
                k = (i + 1) % n
                faces.append((offset + j * n + i, offset + j * n + k, offset + (j + 1) * n + k, offset + (j + 1) * n + i))
        faces.append(tuple(offset + i for i in range(n)))
    for i in range(n):
        k = (i + 1) % n
        faces.append((nr * n + i, nr * n + k, count + nr * n + k, count + nr * n + i))
    obj = mesh_object(name, verts, faces, collection, "roof")
    for face in obj.data.polygons:
        face.use_smooth = len(face.vertices) == 4
    edge_points = verts[nr * n:(nr + 1) * n]
    for side in range(4):
        points = [edge_points[(side * ns + i) % n] for i in range(ns + 1)]
        curve(name + "_Eave_%d" % side, points, .10, collection, "trim")
    curve(name + "_Ridge", [(center_xy[0] + ridge * u, center_xy[1], p["eave_z"] + p["rise"] + .25 * abs(u) ** 5) for u in (-1, -.8, 0, .8, 1)], .16, collection, "trim")
    obj["component_role"] = "curved_roof"
    return obj


def rock_mass(name, top_center, spec):
    """少量不规则大块组成岛底轮廓，不生成雕刻、碎石或表面噪声。
    各块使用不同偏心与下收角度，并以封闭凸包保证底面完整。
    """
    rng = random.Random(spec["seed"])
    w, d, height = spec["size"]
    lean_x, lean_y = spec["lean"]
    points = []
    for level, scale in ((0, 1), (.40, .93), (1, .34)):
        for i in range(8):
            angle = i * math.tau / 8 + .08 * level
            jitter = rng.uniform(.88, 1.10)
            xx = math.cos(angle) * w * .5 * scale * jitter + lean_x * level
            yy = math.sin(angle) * d * .5 * scale * rng.uniform(.90, 1.07) + lean_y * level
            zz = -height * level + (rng.uniform(-.7, .7) if level > 0 else 0)
            points.append((xx, yy, zz))
    bm = bmesh.new()
    for point in points:
        bm.verts.new(point)
    hull = bmesh.ops.convex_hull(bm, input=list(bm.verts), use_existing_faces=False)
    unused = [v for v in hull.get("geom_interior", []) if isinstance(v, bmesh.types.BMVert) and not v.link_faces]
    if unused:
        bmesh.ops.delete(bm, geom=unused, context='VERTS')
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    data = bpy.data.meshes.new(name + "_Mesh")
    bm.to_mesh(data)
    bm.free()
    obj = register(bpy.data.objects.new(name, data), "Bases", "stone")
    obj.location = top_center
    obj["component_role"] = "island_large_mass"
    return obj


def moon_gate(name, center, width, height, thickness, radius, center_height, ring_width, collection="Architecture"):
    """对独立墙体做贯穿布尔，并保留有厚度的圆弧门套。
    圆心略低于半径，使地面处形成可通行的开口而非点接触。
    """
    x, y, z = center
    wall = box(name + "_Wall", (x, y, z + height / 2), (width, thickness, height), collection)
    wall.data = wall.data.copy()
    wall.data["task_tag"] = TAG
    bpy.context.view_layer.objects.active = wall
    wall.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    wall.select_set(False)
    cutter = cylinder(name + "_TEMP_Cutter", (x, y, z + center_height), radius, thickness + 4, collection, segments=96)
    cutter.rotation_euler[0] = math.pi / 2
    modifier = wall.modifiers.new("真实贯通月门", 'BOOLEAN')
    modifier.operation = 'DIFFERENCE'
    modifier.solver = 'EXACT'
    modifier.object = cutter
    bpy.context.view_layer.objects.active = wall
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    bpy.data.objects.remove(cutter, do_unlink=True)
    angle0 = math.asin(-center_height / radius)
    verts = []
    segments = 80
    for yy in (y - thickness / 2 - .1, y + thickness / 2 + .1):
        for rr in (radius, radius + ring_width):
            for i in range(segments + 1):
                angle = angle0 + (math.pi - 2 * angle0) * i / segments
                verts.append((x + rr * math.cos(angle), yy, max(z, z + center_height + rr * math.sin(angle))))
    n = segments + 1
    faces = []
    for i in range(segments):
        faces.extend([(i, i + 1, n + i + 1, n + i), (2 * n + i, 3 * n + i, 3 * n + i + 1, 2 * n + i + 1),
                      (i, 2 * n + i, 2 * n + i + 1, i + 1), (n + i, n + i + 1, 3 * n + i + 1, 3 * n + i)])
    faces.extend([(0, n, 3 * n, 2 * n), (n - 1, 2 * n - 1, 4 * n - 1, 3 * n - 1)])
    mesh_object(name + "_PortalRing", verts, faces, collection, "trim")
    wall["component_role"] = "moon_gate_opening"
    wall["opening_radius"] = radius
    wall["opening_center"] = (x, y, z + center_height)
    return wall


def pine(p):
    """古松以弯曲主干、外展枝条和分层扁冠表达姿态。
    树冠是确定随机种子的低面数占位体，不生成松针。
    """
    rng = random.Random(p["seed"])
    base = Vector(p["position"])
    h, spread = p["height"], p["spread"]
    dx, dy = p["bend"]
    trunk = [base + Vector((dx * t + math.sin(t * math.tau) * h * .09, dy * t + math.sin(t * 5) * h * .045, h * t)) for t in (0, .18, .38, .60, .78, 1)]
    curve("Pine_" + p["id"] + "_Trunk", trunk, h * .055, "Plants", "plant", [1, .82, .68, .52, .33, .09])
    for layer, t in enumerate((.46, .66, .84, .98)):
        branch_origin = base + Vector((dx * t, dy * t, h * (t - .1)))
        for cluster in range(3 if layer < 3 else 2):
            angle = cluster * math.tau / 3 + layer * 1.24
            reach = spread * (.28 - layer * .045)
            tip = base + Vector((dx * t + math.cos(angle) * reach, dy * t + math.sin(angle) * reach * .72, h * t))
            curve("Pine_%s_Branch_%d_%d" % (p["id"], layer, cluster), [branch_origin, (branch_origin + tip) / 2 + Vector((0, 0, -.25)), tip], h * .024, "Plants", "plant", [1, .65, .15])
            sx = spread * (.205 - layer * .027)
            sy = sx * .70
            sz = max(.20, h * .045)
            verts = [(0, 0, -sz)]
            n = 14
            phases = [rng.uniform(.84, 1.16) for _ in range(n)]
            for ring_z, factor in ((-.40, .62), (0, 1), (.60, .88)):
                for i in range(n):
                    ang = i * math.tau / n
                    verts.append((math.cos(ang) * sx * factor * phases[i], math.sin(ang) * sy * factor * phases[i], sz * ring_z))
            verts.append((0, 0, sz))
            faces = [(0, 1 + (i + 1) % n, 1 + i) for i in range(n)]
            for j in range(2):
                faces += [(1 + j * n + i, 1 + j * n + (i + 1) % n, 1 + (j + 1) * n + (i + 1) % n, 1 + (j + 1) * n + i) for i in range(n)]
            faces += [(1 + 2 * n + i, 1 + 2 * n + (i + 1) % n, len(verts) - 1) for i in range(n)]
            canopy = mesh_object("Pine_%s_Canopy_%d_%d" % (p["id"], layer, cluster), verts, faces, "Plants", "plant")
            canopy.location = tip
    cylinder("Pine_" + p["id"] + "_RootMass", base + Vector((0, 0, .15)), h * .085, .3, "Plants", "stone", 12)
