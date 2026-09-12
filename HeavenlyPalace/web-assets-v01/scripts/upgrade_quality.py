"""
在网页副本中提升主体建筑、山崖与表面材质，并保留完整的可编辑网格。
执行一次后记录版本，重复调用不会叠加几何；重建从原始第九版重新适配开始。
"""
import bpy
import bmesh
import json
import math
import random
import shutil
import sys
import time
import numpy as np
from pathlib import Path
from mathutils import Vector, Matrix, noise
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from quality_materials import upgrade_materials

SCENE = bpy.context.scene
REVISION = 'q02'
REPORT = {'revision': REVISION, 'architecture': [], 'terrain': []}
CHANGED = set()
RNG = random.Random(20260912)


def mesh_object(name, verts, faces, collection, materials, smooth=False):
    """
    从明确顶点和面建立可编辑网格，统一修正面朝向与退化边。
    新增结构使用工程现有米制坐标，不引入额外的场景旋转或缩放。
    """
    data = bpy.data.meshes.new(name + '_网格')
    data.from_pydata(verts, [], faces)
    data.update()
    bm = bmesh.new()
    bm.from_mesh(data)
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=.00001)
    bmesh.ops.dissolve_degenerate(bm, edges=list(bm.edges), dist=.000001)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(data)
    bm.free()
    for mat in materials:
        data.materials.append(mat)
    for poly in data.polygons:
        poly.use_smooth = smooth
    ob = bpy.data.objects.new(name, data)
    collection.objects.link(ob)
    CHANGED.add(data)
    return ob


def box(name, center, size, collection, material, bevel=.06):
    """
    为门墙、台基和装饰线生成有体积的方材，小倒角提供真实边缘反光。
    修改器当场固化为网格，网页导出不需要解释 Blender 修改器。
    """
    x, y, z = center
    a, b, c = [s / 2 for s in size]
    verts = [(x + sx * a, y + sy * b, z + sz * c)
             for sz in (-1, 1) for sy in (-1, 1) for sx in (-1, 1)]
    faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    ob = mesh_object(name, verts, faces, collection, [material])
    if bevel:
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        bmesh.ops.bevel(bm, geom=list(bm.edges), offset=bevel, segments=2, affect='EDGES')
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.to_mesh(ob.data)
        bm.free()
    return ob


def moon_gate():
    """
    在前入口建立通厚圆门，开口落地且不改变主殿原有四十四米月门。
    圆门石圈采用分层断面，墙面与柱网衔接，构成原型的前景视觉中心。
    """
    collection = bpy.data.collections.new('05Q_入口月门与石构细节')
    SCENE.collection.children.link(collection)
    stone = bpy.data.materials['WEB_V08_白玉_台基石构']
    trim = bpy.data.materials['WEB_V08_白玉_柱身栏杆']
    wall = box('Q02_前入口月门厚墙', (0, -192, 15.9), (60, 4.2, 31.8), collection, stone, 0)
    bpy.ops.mesh.primitive_cylinder_add(vertices=192, radius=14, depth=10,
                                      location=(0, -192, 14), rotation=(math.pi / 2, 0, 0))
    cutter = bpy.context.object
    bpy.context.view_layer.objects.active = wall
    modifier = wall.modifiers.new('十四米半径贯通月门', 'BOOLEAN')
    modifier.operation = 'DIFFERENCE'
    modifier.solver = 'EXACT'
    modifier.object = cutter
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    bpy.data.objects.remove(cutter, do_unlink=True)
    CHANGED.add(wall.data)
    verts, faces = [], []
    profile = [(14, -2.11), (14.15, -2.43), (14.4, -2.54), (14.7, -2.54),
               (14.82, -2.38), (15.7, -2.38), (15.9, -2.54), (16.2, -2.54), (16.45, -2.11),
               (16.45, 2.11), (16.2, 2.54), (15.9, 2.54), (15.7, 2.38), (14.82, 2.38),
               (14.7, 2.54), (14.4, 2.54), (14.15, 2.43), (14, 2.11)]
    for i in range(193):
        for radius, depth in profile:
            start = math.asin(-14 / radius)
            angle = start + (math.pi - 2 * start) * i / 192
            verts.append((radius * math.cos(angle), -192 + depth, 14 + radius * math.sin(angle)))
    count = len(profile)
    for i in range(192):
        faces.extend((i * count + j, i * count + (j + 1) % count,
                      (i + 1) * count + (j + 1) % count, (i + 1) * count + j) for j in range(count))
    faces.extend([tuple(reversed(range(count))), tuple(192 * count + j for j in range(count))])
    ring = mesh_object('Q02_前入口月门_二十八米通厚石圈', verts, faces, collection, [trim], True)
    ring['净口直径_米'] = 28
    for side in (-1, 1):
        for z, height in ((1.0, .7), (30.9, .55)):
            box(f'Q02_前门墙压线_{side}_{z}', (side * 23.3, -194.3, z), (12.8, .38, height), collection, trim)
        for z in (4.0, 28.0):
            box(f'Q02_门侧石刻边框_{side}_{z}', (side * 23.4, -194.18, z), (9.2, .22, .18), collection, trim)
        for x in (19.0, 27.8):
            box(f'Q02_门侧石刻竖框_{side}_{x}', (side * x, -194.18, 16), (.18, .22, 24), collection, trim)
    REPORT['entrance_moon_diameter_m'] = 28


def decorate_hall():
    """
    在原有主梁外侧补充朱漆额枋、黛青画心和回纹金线，形成可读的檐下装饰带。
    柱头增加交错承托层，所有构件随后与屋架一起连续变形，保持节点连接。
    """
    col = bpy.data.collections.new('04Q_主殿彩枋与交错柱头')
    SCENE.collection.children.link(col)
    wood = bpy.data.materials['WEB_V08_朱红木构_顺x轴']
    gold = bpy.data.materials['WEB_V08_哑金_脊线与细金饰']
    panel = bpy.data.materials['WEB_V09_藻井黛青底漆']
    for side in (-1, 1):
        y = 295 + side * 53.55
        box(f'Q02_主殿彩枋底板_{side}', (0, y, 84.25), (188, .42, 4.35), col, wood)
        for z in (82.25, 86.25):
            box(f'Q02_主殿彩枋压金_{side}_{z}', (0, y + side * .29, z), (188, .19, .23), col, gold, .025)
        for index, x in enumerate(range(-84, 85, 14)):
            box(f'Q02_主殿画心_{side}_{index}', (x, y + side * .25, 84.25), (10.8, .15, 2.8), col, panel, .02)
            for z in (82.85, 85.65):
                box(f'Q02_画心边线_{side}_{index}_{z}', (x, y + side * .37, z), (11.0, .16, .15), col, gold, .02)
            for offset in (-5.4, 5.4):
                box(f'Q02_画心端线_{side}_{index}_{offset}', (x + offset, y + side * .37, 84.25), (.15, .16, 2.8), col, gold, .02)
            for sign in (-1, 1):
                points = [(-4.5, -.9), (-4.5, .9), (-.4, .9), (-.4, -.6), (-3.3, -.6), (-3.3, .15), (-1.6, .15)]
                for j, (a, b) in enumerate(zip(points, points[1:])):
                    center = (x + sign * (a[0] + b[0]) / 2, y + side * .39, 84.25 + (a[1] + b[1]) / 2)
                    dims = (max(.14, abs(b[0] - a[0])), .16, max(.14, abs(b[1] - a[1])))
                    box(f'Q02_回纹金线_{side}_{index}_{sign}_{j}', center, dims, col, gold, .02)
    positions = [(x, y) for x in (-90, -60, -30, 30, 60, 90) for y in (245, 345)]
    positions += [(x, y) for x in (-90, 90) for y in (278.333333, 311.666667)]
    for index, (x, y) in enumerate(positions):
        for level, dims, z in [(0, (4.5, 4.5, .8), 82.35), (1, (8.0, 1.6, .75), 83.12),
                               (2, (1.8, 9.0, .75), 83.85), (3, (10.4, 2.0, .8), 84.6)]:
            box(f'Q02_交错斗拱_{index}_{level}', (x, y, z), dims, col, wood, .085)
            if level:
                for sign in (-1, 1):
                    offset = (sign * dims[0] * .36, 0) if level != 2 else (0, sign * dims[1] * .36)
                    box(f'Q02_斗拱承斗_{index}_{level}_{sign}', (x + offset[0], y + offset[1], z + .4), (1.7, 1.7, .36), col, gold, .04)


def architecture():
    """
    主殿屋架从柱头标高连续增高，并逐渐扩大挑檐，保持承托关系连续。
    相同空间变形用于梁架、瓦垄和屋脊，避免分别缩放产生穿插或断缝。
    """
    decorate_hall()
    for ob in list(SCENE.objects):
        if ob.type != 'MESH' or any(c.name.startswith(('01', '09', '10', '17')) for c in ob.users_collection):
            continue
        corners = [ob.matrix_world @ Vector(p) for p in ob.bound_box]
        if max(p.z for p in corners) <= 82 or min(p.z for p in corners) > 150:
            continue
        if min(p.x for p in corners) < -145 or max(p.x for p in corners) > 145:
            continue
        if min(p.y for p in corners) < 210 or max(p.y for p in corners) > 385:
            continue
        data = ob.data.copy()
        transform = ob.matrix_world.copy()
        inverse = transform.inverted()
        for vertex in data.vertices:
            p = transform @ vertex.co
            height = max(0, p.z - 82)
            expansion = min(1, height / 12)
            p.x *= 1 + .08 * expansion
            p.y = 295 + (p.y - 295) * (1 + .06 * expansion)
            p.z = 82 + height * 1.28 if p.z > 82 else p.z
            vertex.co = inverse @ p
        data.update()
        ob.data = data
        CHANGED.add(data)
        REPORT['architecture'].append(ob.name)
    moon_gate()


def terrain(variants):
    """
    对原岩芯进行按边长细分和侵蚀塑形，以连续裂脊替代大块平直三角面。
    建筑承台、桥洞和瀑布出水附近限制位移，保持既有接合关系。
    """
    cache = {}
    for ob in list(SCENE.objects):
        if ob.type != 'MESH':
            continue
        near = any(c.name.startswith('01') for c in ob.users_collection)
        distant = any(c.name.startswith('17_') for c in ob.users_collection)
        if not (near or distant):
            continue
        source = ob.data
        if source in cache:
            ob.data = cache[source]
            continue
        data = source.copy()
        before = len(data.vertices)
        bm = bmesh.new()
        bm.from_mesh(data)
        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=.0001)
        bmesh.ops.triangulate(bm, faces=list(bm.faces))
        for _ in range(3 if near else 2):
            edges = [e for e in bm.edges if e.calc_length() > (7.5 if near else 42)]
            if not edges:
                break
            bmesh.ops.subdivide_edges(bm, edges=edges, cuts=1, use_grid_fill=True)
        bm.normal_update()
        bmesh.ops.smooth_vert(bm, verts=list(bm.verts), factor=.18 if near else .28,
                             use_axis_x=True, use_axis_y=True, use_axis_z=True)
        bm.normal_update()
        for vertex in bm.verts:
            p = vertex.co.copy()
            n = vertex.normal.copy()
            broad = noise.noise(Vector((p.x / 19, p.y / 19, p.z / 44)), noise_basis='PERLIN_ORIGINAL')
            fine = noise.noise(p / 4.3, noise_basis='PERLIN_ORIGINAL')
            striation = math.sin(p.x * .58 + p.y * .37 + broad * 4) * .5
            if near:
                displacement = broad * 3.7 + fine * .95 + striation * .9
                protection = .1 if n.z > .65 else 1.0
                if (abs(p.x) < 161 and -238 < p.y < 384 and p.z > -7) or (145 < p.x < 272 and 128 < p.y < 224):
                    protection *= .08
                if abs(abs(p.x) - 231) < 16 and p.y < -150:
                    protection *= .18
                vertex.co += Vector((n.x, n.y, n.z * .4)) * displacement * protection
            else:
                displacement = broad * 14 + fine * 3
                vertex.co += Vector((n.x, n.y, n.z * .6)) * displacement
        bmesh.ops.triangulate(bm, faces=list(bm.faces))
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.to_mesh(data)
        bm.free()
        if near:
            data.materials.clear()
            for key in ('rock', 'wet', 'moss'):
                data.materials.append(variants[key])
        for poly in data.polygons:
            poly.use_smooth = True
            if near:
                center = ob.matrix_world @ poly.center
                variation = noise.noise(center / 23, noise_basis='PERLIN_ORIGINAL')
                wet = abs(abs(center.x) - 231) < 12 and center.y < -160
                poly.material_index = 1 if wet else 2 if poly.normal.z > .32 and variation > -.15 else 0
        data.update()
        cache[source] = data
        ob.data = data
        CHANGED.add(data)
        REPORT['terrain'].append(dict(name=ob.name, before_vertices=before, after_vertices=len(data.vertices), near=near))
        print('QUALITY_ROCK', ob.name, before, len(data.vertices), flush=True)


def terrain_tree():
    """
    将近景岩体合成只读射线索引，植被必须真实附着于岩台表面。
    索引不包含建筑及桥面，避免树木进入宫殿、台阶和通行区域。
    """
    verts, faces = [], []
    for ob in SCENE.objects:
        if ob.type != 'MESH' or not any(c.name.startswith('01') for c in ob.users_collection):
            continue
        offset = len(verts)
        verts.extend(ob.matrix_world @ v.co for v in ob.data.vertices)
        faces.extend(tuple(offset + i for i in p.vertices) for p in ob.data.polygons)
    return BVHTree.FromPolygons(verts, faces)


def canopy(collection, material):
    """
    一个标准冠簇包含多个不规则叶团，边缘细分出短尖，避免规则球形树冠。
    远近植被都复用少量共享网格，保持网页实例绘制的效率。
    """
    variants = []
    for variant in range(4):
        rng = random.Random(913 + variant)
        verts, faces = [], []
        for lobe in range(5):
            angle = lobe * math.tau / 5 + rng.uniform(-.3, .3)
            center = Vector((math.cos(angle) * .45, math.sin(angle) * .4, rng.uniform(-.12, .15)))
            offset = len(verts)
            for j in range(1, 6):
                phi = math.pi * j / 6
                for i in range(12):
                    theta = math.tau * i / 12
                    radius = (1 + rng.uniform(-.18, .18)) * math.sin(phi) * .62
                    verts.append(center + Vector((math.cos(theta) * radius, math.sin(theta) * radius, math.cos(phi) * .35)))
            top, bottom = len(verts), len(verts) + 1
            verts.extend([center + Vector((0, 0, .36)), center - Vector((0, 0, .35))])
            for i in range(12):
                faces.append((top, offset + i, offset + (i + 1) % 12))
                faces.append((bottom, offset + 48 + (i + 1) % 12, offset + 48 + i))
                for j in range(4):
                    a = offset + j * 12 + i
                    b = offset + j * 12 + (i + 1) % 12
                    faces.append((a, a + 12, b + 12, b))
        ob = mesh_object(f'Q02_共享松冠样板_{variant}', verts, faces, collection, [material], True)
        variants.append(ob.data)
        bpy.data.objects.remove(ob, do_unlink=True)
    return variants


def vegetation():
    """
    为原有松针补充内部冠簇，并在有支撑的崖顶、台地种植低矮灌丛。
    中轴台阶和亭桥区域保持净空，植物疏密由地形法线及确定性种子控制。
    """
    col = bpy.data.collections.new('09_Q02_岩台灌丛与松冠层次')
    SCENE.collection.children.link(col)
    mat = bpy.data.materials['WEB_V08_松针_深绿']
    crowns = canopy(col, mat)
    leaves = [o for o in SCENE.objects if o.type == 'MESH' and '疏密针叶' in o.name]
    count = 0
    for index, leaf in enumerate(sorted(leaves, key=lambda o: o.name)):
        if index % 3:
            continue
        lo = Vector(tuple(min(v.co[i] for v in leaf.data.vertices) for i in range(3)))
        hi = Vector(tuple(max(v.co[i] for v in leaf.data.vertices) for i in range(3)))
        ob = bpy.data.objects.new(f'Q02_松冠内层_{index:04}', crowns[index % 4])
        col.objects.link(ob)
        size = hi - lo
        ob.matrix_world = leaf.matrix_world @ Matrix.Translation((lo + hi) / 2) @ Matrix.Diagonal((size.x * .42, size.y * .42, size.z * .66, 1))
        count += 1
    # 按原有针叶的位置聚类出主枝冠片，让树冠沿真实枝条展开。
    # 冠片保留高低错落和边缘留白，避免把整棵松树包成一个球体。
    tree_leaves = {}
    for leaf in leaves:
        center = leaf.matrix_world @ (sum((Vector(p) for p in leaf.bound_box), Vector()) / 8)
        key = leaf.users_collection[0].name
        tree_leaves.setdefault(key, []).append(tuple(center))
    crown_count = 0
    for tree_index, (key, points) in enumerate(sorted(tree_leaves.items())):
        points = np.array(points)
        groups = 7
        centers = points[np.linspace(0, len(points) - 1, groups).astype(int)].copy()
        for _ in range(12):
            labels = ((points[:, None, :] - centers[None, :, :])**2).sum(axis=2).argmin(axis=1)
            for index in range(groups):
                group = points[labels == index]
                if len(group):
                    centers[index] = group.mean(axis=0)
        for index, center in enumerate(centers):
            group = points[labels == index]
            if not len(group):
                continue
            spread = np.std(group, axis=0)
            ob = bpy.data.objects.new(f'Q02_主枝松冠_{tree_index}_{index}', crowns[index % 4])
            col.objects.link(ob)
            ob.location = center
            ob.scale = (max(5.5, spread[0] * 1.65), max(4.5, spread[1] * 1.65), max(3.2, min(6, spread[2] * 1.5)))
            ob.rotation_euler.z = RNG.uniform(-.4, .4)
            count += 1
            crown_count += 1
    tree = terrain_tree()
    for attempt in range(1900):
        x, y = RNG.uniform(-346, 354), RNG.uniform(-387, 518)
        if (abs(x) < 166 and -240 < y < 389) or (abs(x) < 37 and y < -235) or (147 < x < 280 and 130 < y < 225):
            continue
        hit, normal, _, _ = tree.ray_cast(Vector((x, y, 230)), Vector((0, 0, -1)), 510)
        if hit is None or hit.z < -92 or normal.z < .42:
            continue
        scale = RNG.uniform(2.4, 7.7)
        ob = bpy.data.objects.new(f'Q02_岩台灌丛_{attempt:04}', crowns[attempt % 4])
        col.objects.link(ob)
        ob.location = hit + Vector((0, 0, scale * .13))
        ob.scale = (scale, scale * RNG.uniform(.7, 1.2), scale * .8)
        ob.rotation_euler.z = RNG.uniform(0, math.tau)
        count += 1
    REPORT['added_canopy_instances'] = count
    REPORT['main_branch_canopies'] = crown_count
    print('QUALITY_VEGETATION', count, flush=True)


def update_uvs():
    """
    按最终材质的米制平铺范围重建第一套紫外坐标，保留柱纹第二套坐标。
    多个实例共用局部纹理；独立岩体按世界位置映射，减少块间比例差异。
    """
    users = {}
    for ob in SCENE.objects:
        if ob.type == 'MESH':
            users.setdefault(ob.data, []).append(ob)
    for data, objects in users.items():
        # 布尔开孔可能留下空的切刀材质槽，统一继承墙体原有石材。
        # 在读取导出描述前补齐备用槽，确保每个实际面都有确定的物理材质。
        fallback = next((m for m in data.materials if m), bpy.data.materials['WEB_V08_白玉_台基石构'])
        if not data.materials:
            data.materials.append(fallback)
        for index, mat in enumerate(data.materials):
            if mat is None:
                data.materials[index] = fallback
        specs = [json.loads(m['web_spec']) for m in data.materials]
        if data not in CHANGED and not any(s.get('quality_revision') == REVISION for s in specs):
            continue
        uv = data.uv_layers.get('TileUV') or data.uv_layers.new(name='TileUV')
        minimum = [min(v.co[i] for v in data.vertices) for i in range(3)]
        maximum = [max(v.co[i] for v in data.vertices) for i in range(3)]
        for poly in data.polygons:
            spec = specs[poly.material_index]
            axes = [i for i in range(3) if i != max(range(3), key=lambda i: abs(poly.normal[i]))]
            for li in poly.loop_indices:
                p = data.vertices[data.loops[li].vertex_index].co
                if len(objects) == 1 and not spec.get('ceiling'):
                    p = objects[0].matrix_world @ p
                coords = [p[j] / spec.get('tile_m', 4) for j in axes]
                if spec.get('ceiling'):
                    coords = [(p[j] - minimum[j]) / max(.001, maximum[j] - minimum[j]) for j in (0, 1)]
                uv.data[li].uv = coords


def main():
    """
    保存升级前副本后依次处理材质、建筑、山体与植被，最后写入可核验记录。
    原始建模工程不参与写入，网页继续通过同一个资源目录读取新资产。
    """
    if SCENE.get('主体资产质量版本') == REVISION:
        print('QUALITY_ALREADY_APPLIED', REVISION, flush=True)
        return
    start = time.time()
    qa = ROOT / 'qa'
    qa.mkdir(exist_ok=True)
    backup = qa / 'before-quality.blend'
    if not backup.exists():
        shutil.copy2(bpy.data.filepath, backup)
    variants, materials = upgrade_materials()
    REPORT['materials'] = materials
    architecture()
    terrain(variants)
    bpy.context.view_layer.update()
    vegetation()
    bpy.context.view_layer.update()
    update_uvs()
    SCENE['主体资产质量版本'] = REVISION
    REPORT['elapsed_seconds'] = round(time.time() - start, 2)
    REPORT['mesh_objects'] = sum(o.type == 'MESH' for o in SCENE.objects)
    (qa / 'quality-upgrade.json').write_text(json.dumps(REPORT, ensure_ascii=False, indent=2), encoding='utf-8')
    for im in bpy.data.images:
        if im.users and im.source == 'FILE':
            im.pack()
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(ROOT / 'HeavenlyPalace_WebAssets_v01.blend'), compress=True)
    print('QUALITY_COMPLETE', REPORT['elapsed_seconds'], flush=True)


if __name__ == '__main__':
    main()
