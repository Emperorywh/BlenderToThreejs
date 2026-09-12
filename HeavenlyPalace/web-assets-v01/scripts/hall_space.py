"""
统一维护殿内空间尺寸，并将既有精修构件转换为更高、更开阔的柱廊与月门。
每个对象保留原始网格和矩阵，重复调整先恢复基准，避免累计拉伸和破坏共享实例。
"""
import json
import math
import bpy
import bmesh
import numpy as np
from mathutils import Matrix, Vector

REVISION = 'hall-space-v3'
FLOOR_Z = 36.0
GATE_CENTER_Z = 49.0
GATE_RADIUS = 32.0
GATE_FRONT_Y = 246.0
UPPER_LIFT = 10.0
COLUMN_RADIUS_FACTOR = 1.05 / 1.18
MOON_NAME = 'V05_月门通厚石圈_净径44米'
BASE_MESH = 'H03_基准网格'
BASE_MATRIX = 'H03_基准矩阵'


def column_x(x):
    """
    中央开间由六十米扩为七十八米，两侧开间收至二十五点五米。
    外侧柱线与屋面总宽保持原边界，梁架与柱网共用连续的横向映射。
    """
    a = abs(x)
    return math.copysign(a * 1.3 if a <= 30 else 39 + (a - 30) * .85 if a < 90 else a, x)


def canonical_point(point):
    """
    将新屋面和梁架的世界坐标反算回既有解析曲面，供穿插核验使用。
    该逆变换只用于整体抬高的上部木构，不用于柱身或重新生成的圆门。
    """
    x, y, z = point
    a = abs(x)
    old_x = a / 1.3 if a <= 39 else 30 + (a - 39) / .85 if a < 90 else a
    return Vector((math.copysign(old_x, x), y, z - UPPER_LIFT))


def space_active():
    """
    以工程中的实际空间版本识别是否已经调整，旧工程仍可走原有检查路径。
    参数常量描述目标尺寸，版本属性描述当前工程状态，两者不混为一谈。
    """
    return bpy.context.scene.get('殿内空间版本') == REVISION


def remember(ob):
    """
    原始网格使用保留标记存入同一工程，恢复不依赖外部临时目录。
    保存完整世界矩阵，柱子的既有旋转与各开间的定位均可准确还原。
    """
    if BASE_MESH not in ob:
        ob[BASE_MESH] = ob.data.name
        ob[BASE_MATRIX] = json.dumps([list(row) for row in ob.matrix_world])
        ob.data.use_fake_user = True


def restore_space():
    """
    在重新生成梁架或藻井之前恢复基准，使原有构建器继续使用同一套标高。
    只处理明确记录过的对象；用户新增物体和其他场景内容不参与转换。
    """
    for ob in list(bpy.context.scene.objects):
        if BASE_MESH not in ob:
            continue
        baseline = bpy.data.meshes.get(ob[BASE_MESH])
        if baseline is None:
            raise RuntimeError('缺少空间基准网格：' + ob.name)
        modified = ob.data
        ob.data = baseline
        ob.matrix_world = Matrix(json.loads(ob[BASE_MATRIX]))
        baseline.use_fake_user = False
        del ob[BASE_MESH]
        del ob[BASE_MATRIX]
        if modified != baseline and modified.users == 0:
            bpy.data.meshes.remove(modified)
    bpy.context.scene.pop('殿内空间版本', None)
    moon = bpy.data.objects.get(MOON_NAME)
    if moon:
        moon['净开口直径_米'] = 44.0
        moon['门洞中心标高_米'] = 56.0
        moon['落地净宽_米'] = 2 * math.sqrt(22 ** 2 - 20 ** 2)
    bpy.context.view_layer.update()


def warp_x(values):
    """
    使用数组一次转换整个构件的横坐标，避免对屋面数十万顶点逐次调用操作器。
    映射严格递增，左右对称，外侧边界连续且不产生负缩放。
    """
    a = np.abs(values)
    return np.sign(values) * np.where(a <= 30, a * 1.3, np.where(a < 90, 39 + (a - 30) * .85, a))


def remap_objects():
    """
    柱身保持圆截面并同步柱础、柱头与浮雕，木构整体上抬而不拉厚天花。
    藻井采用中央与侧间两种共享横向比例，保留原来的七份网格和实例复用。
    """
    cache = {}
    centers_x = np.array([-90, -60, -30, 30, 60, 90])
    centers_y = np.array([245, 278.333333, 311.666667, 345])
    for ob in list(bpy.context.scene.objects):
        if ob.type != 'MESH':
            continue
        column = ob.name.startswith('主殿巨柱')
        generated = ob.name.startswith('H01_') and ob.name != 'H01_主殿台基石栏与须弥腰线'
        decoration = ob.name.startswith('V09_月门')
        if not (column or generated or decoration):
            continue
        remember(ob)
        source = ob.data
        original = ob.matrix_world.copy()
        destination = original.copy()
        bay = ob.name.startswith('H01_C02_') and '开间' in ob.name
        local_scale = 1.3 if abs(original.translation.x) < 1 else .85
        shaft = column and ob.name.endswith('_柱身')
        key = (source.name, 'shaft' if shaft else 'column' if column else 'bay' if bay else ob.name,
               local_scale if bay else 0)
        if column or bay:
            destination.translation.x = column_x(original.translation.x)
            if bay or ob.name.endswith('_承梁柱头'):
                destination.translation.z += UPPER_LIFT
        if key not in cache:
            data = source.copy()
            data.name = source.name + '_空间v3'
            coordinates = np.empty((len(data.vertices), 3), dtype=np.float64)
            data.vertices.foreach_get('co', coordinates.ravel())
            if column:
                # 柱径围绕各自轴线缩小，避免中央开间变宽时把圆柱横向拉成椭圆。
                # 柱脚保持落地，只有柱身长度和柱头安装标高随层高变化。
                coordinates[:, :2] *= COLUMN_RADIUS_FACTOR if shaft else .95
                if shaft:
                    coordinates[:, 2] = 37.6 + (coordinates[:, 2] - 37.6) * (52.8 / 42.8)
            elif bay:
                coordinates[:, 0] *= local_scale
            else:
                world = coordinates @ np.asarray(original.to_3x3()).T + np.asarray(original.translation)
                if ob.name in ('H01_覆盆莲瓣柱础与柱头', 'H01_柱身浅浮雕与束口'):
                    # 合并石构中的各根柱子仍按最近柱轴定位，脚座与柱头分别处理高度。
                    # 这样可以保留雕刻与柱面的贴合，同时避免抬起整块落地柱础。
                    cx = centers_x[np.argmin(np.abs(world[:, 0, None] - centers_x), axis=1)]
                    cy = centers_y[np.argmin(np.abs(world[:, 1, None] - centers_y), axis=1)]
                    world[:, 0] = warp_x(cx) + (world[:, 0] - cx) * COLUMN_RADIUS_FACTOR
                    world[:, 1] = cy + (world[:, 1] - cy) * COLUMN_RADIUS_FACTOR
                    z = world[:, 2].copy()
                    world[:, 2] = np.where(z > 75, z + UPPER_LIFT,
                                          np.where(z > 40, 37.6 + (z - 37.6) * (52.8 / 42.8), z))
                elif ob.name == 'V09_月门_连续如意卷草_全圈':
                    radius = np.hypot(world[:, 0], world[:, 2] - 56)
                    theta = np.arctan2(world[:, 2] - 56, world[:, 0])
                    theta = np.where(theta < -math.pi / 2, theta + math.tau, theta)
                    old_start = np.arcsin(-20 / radius)
                    new_radius = radius + GATE_RADIUS - 22
                    start = np.arcsin((FLOOR_Z - GATE_CENTER_Z) / new_radius)
                    angle = start + (theta - old_start) / (math.pi - 2 * old_start) * (math.pi - 2 * start)
                    world[:, 0] = new_radius * np.cos(angle)
                    world[:, 2] = GATE_CENTER_Z + new_radius * np.sin(angle)
                else:
                    world[:, 0] = warp_x(world[:, 0])
                    world[:, 2] += UPPER_LIFT
                inverse = original.inverted()
                coordinates = world @ np.asarray(inverse.to_3x3()).T + np.asarray(inverse.translation)
            data.vertices.foreach_set('co', coordinates.astype(np.float32).ravel())
            data.update()
            cache[key] = data
        ob.data = cache[key]
        ob.matrix_world = destination
    bpy.context.view_layer.update()


def replace_mesh(ob, vertices, faces, smooth=False):
    """
    用真实实体网格替换指定月门构件，沿用原材质并重新建立米制平面纹理坐标。
    清除退化边并重算法线，使导出的开口、倒角与厚度均可直接核验。
    """
    remember(ob)
    source = ob.data
    data = bpy.data.meshes.new(ob.name + '_空间v3')
    data.from_pydata(vertices, [], faces)
    for mat in source.materials:
        if mat is not None:
            data.materials.append(mat)
    bm = bmesh.new()
    bm.from_mesh(data)
    bmesh.ops.dissolve_degenerate(bm, edges=list(bm.edges), dist=.000001)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(data)
    bm.free()
    data.update()
    for face in data.polygons:
        face.use_smooth = smooth and abs(face.normal.z) < .999
    uv = data.uv_layers.new(name='TileUV')
    for face in data.polygons:
        axes = [i for i in range(3) if i != max(range(3), key=lambda i: abs(face.normal[i]))]
        for li in face.loop_indices:
            p = data.vertices[data.loops[li].vertex_index].co
            uv.data[li].uv = (p[axes[0]] / 4, p[axes[1]] / 4)
    ob.data = data
    ob.matrix_world = Matrix.Identity(4)
    return ob


def solid_box(ob, center, size):
    """
    按世界坐标重建墙体或壁柱的封闭长方体，尺寸来自本轮统一空间参数。
    后续布尔切刀只作用于月门厚墙与墙脚，不影响相邻柱列。
    """
    x, y, z = center
    w, d, h = [v / 2 for v in size]
    vertices = [(x-w,y-d,z-h),(x+w,y-d,z-h),(x+w,y+d,z-h),(x-w,y+d,z-h),
                (x-w,y-d,z+h),(x+w,y-d,z+h),(x+w,y+d,z+h),(x-w,y+d,z+h)]
    faces = [(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
    return replace_mesh(ob, vertices, faces)


def cut_opening(ob):
    """
    从厚墙中实际切除石圈外缘以内的圆柱体，保证门洞前后贯通。
    切刀计算完成立即移除，并将布尔后的材质与纹理坐标整理成可导出网格。
    """
    bpy.ops.mesh.primitive_cylinder_add(vertices=320, radius=GATE_RADIUS + 2.335, depth=18,
                                      location=(0, 243, GATE_CENTER_Z), rotation=(math.pi / 2, 0, 0))
    cutter = bpy.context.object
    bpy.context.view_layer.objects.active = ob
    modifier = ob.modifiers.new('六十四米月门实体开口', 'BOOLEAN')
    modifier.operation, modifier.solver, modifier.object = 'DIFFERENCE', 'EXACT', cutter
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    bpy.data.objects.remove(cutter, do_unlink=True)
    data = ob.data
    vertices = [tuple(v.co) for v in data.vertices]
    faces = [tuple(p.vertices) for p in data.polygons]
    replace_mesh(ob, vertices, faces)
    if data.users == 0:
        bpy.data.meshes.remove(data)


def rebuild_gate():
    """
    扩大圆门并降低圆心，底部仍精确裁在地坪，形成宽阔且没有门槛的通道。
    保留历史对象名称以兼容已有工程引用，实际尺寸由对象属性与资源清单明确记录。
    """
    wall = bpy.data.objects['V05_月门厚墙_两端入柱']
    solid_box(wall, (0, 243, 64), (78, 4.8, 56))
    cut_opening(wall)
    profile = [(22,-2.4),(22.08,-2.8),(22.4,-3),(22.65,-3),(22.8,-2.89),
               (23.75,-2.89),(24,-2.78),(24.2,-2.5),(24.35,-2.4),
               (24.35,2.4),(24.2,2.5),(24,2.78),(23.75,2.89),(22.8,2.89),
               (22.65,3),(22.4,3),(22.08,2.8),(22,2.4)]
    vertices, faces = [], []
    segments, n = 320, len(profile)
    for i in range(segments + 1):
        for old_radius, depth in profile:
            radius = old_radius + GATE_RADIUS - 22
            start = math.asin((FLOOR_Z - GATE_CENTER_Z) / radius)
            angle = start + (math.pi - 2 * start) * i / segments
            vertices.append((radius * math.cos(angle), 243 + depth, GATE_CENTER_Z + radius * math.sin(angle)))
    for i in range(segments):
        faces.extend((i*n+j,i*n+(j+1)%n,(i+1)*n+(j+1)%n,(i+1)*n+j) for j in range(n))
    faces.extend([tuple(reversed(range(n))), tuple(segments*n+j for j in range(n))])
    moon = replace_mesh(bpy.data.objects[MOON_NAME], vertices, faces, True)
    # 分裂法线保留退台棱线，仅沿圆周平滑，防止石圈断面看起来像充气圆管。
    # 圆口、石雕与墙体使用相同圆心，底部封口保持水平且不跨越通行范围。
    normals = [None] * len(moon.data.loops)
    for face in moon.data.polygons:
        radial = Vector((face.center.x, 0, face.center.z - GATE_CENTER_Z)).normalized()
        component = face.normal.dot(radial)
        for li in face.loop_indices:
            p = moon.data.vertices[moon.data.loops[li].vertex_index].co
            direction = Vector((p.x, 0, p.z - GATE_CENTER_Z)).normalized()
            normal = direction * component + Vector((0, face.normal.y, 0))
            normals[li] = tuple(face.normal if abs(face.normal.z) > .999 else normal.normalized())
    moon.data.normals_split_custom_set(normals)
    moon['净开口直径_米'] = GATE_RADIUS * 2
    moon['门洞中心标高_米'] = GATE_CENTER_Z
    moon['完成面标高_米'] = FLOOR_Z
    moon['落地净宽_米'] = 2 * math.sqrt(GATE_RADIUS ** 2 - (GATE_CENTER_Z - FLOOR_Z) ** 2)
    for ob in list(bpy.context.scene.objects):
        if ob.name.startswith('V05_月门墙脚_不跨通道_'):
            old_z = float(ob.name.rsplit('_', 1)[1])
            solid_box(ob, (0,243,old_z), (78,5.2,.7))
            cut_opening(ob)
    for side in (-1, 1):
        x = side * 35.65
        solid_box(bpy.data.objects[f'V05_月门抱柱壁柱_{side}'], (x,243,63.9), (1.65,6.15,55.8))
        solid_box(bpy.data.objects[f'V05_月门壁柱脚座_{side}'], (x,243,36.55), (2.1,6.6,1.1))
        solid_box(bpy.data.objects[f'V05_月门柱头衔接石_{side}'], (x,243,91.1), (3.5,6.5,1.8))
    bpy.context.view_layer.update()


def apply_space():
    """
    每次从同一基准应用目标尺寸，既可独立调整，也可接在完整主殿重建后运行。
    原始网格随工程保存，后续局部重建先恢复再应用，避免任何累计变形。
    """
    restore_space()
    remap_objects()
    rebuild_gate()
    bpy.context.scene['殿内空间版本'] = REVISION
    bpy.context.scene['殿内空间参数'] = json.dumps(dict(floor_z=FLOOR_Z, upper_lift=UPPER_LIFT,
        gate_radius=GATE_RADIUS, gate_center_z=GATE_CENTER_Z, central_bay_width=78,
        column_radius_factor=COLUMN_RADIUS_FACTOR), ensure_ascii=False)
    bpy.context.view_layer.update()
