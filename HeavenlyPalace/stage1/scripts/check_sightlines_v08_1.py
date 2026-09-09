"""
用实际场景网格构建射线加速结构，查验新机位各开口的外部遮挡。
体积容器不作为实心碰撞，射线检查不修改任何物体可见性或材质。
"""
import bpy
import json
import math
from pathlib import Path
from collections import Counter
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / 'v08_1' / 'qa'
scene = bpy.context.scene
cam = bpy.data.objects['CAM_04_殿内望云_v08_1']
hidden = set()


def collect_hidden(col, excluded=False):
    """继承原场景集合的渲染排除状态，只读取已有设置。
    历史占位和辅助尺寸不会被错误计入实际可见几何。
    """
    excluded = excluded or col.hide_render
    if excluded:
        hidden.update(o.name for o in col.all_objects)
    for child in col.children:
        collect_hidden(child, excluded)


collect_hidden(scene.collection)
vertices, faces, owners = [], [], []
deps = bpy.context.evaluated_depsgraph_get()
for ob in scene.objects:
    if ob.type not in ('MESH', 'CURVE') or ob.hide_render or ob.name in hidden or any(c.name.startswith('18_') for c in ob.users_collection):
        continue
    evaluated = ob.evaluated_get(deps)
    mesh = evaluated.to_mesh()
    offset = len(vertices)
    vertices.extend(ob.matrix_world @ v.co for v in mesh.vertices)
    faces.extend(tuple(offset + i for i in p.vertices) for p in mesh.polygons)
    owners.extend([ob.name] * len(mesh.polygons))
    evaluated.to_mesh_clear()
tree = BVHTree.FromPolygons(vertices, faces)
print('SIGHT_BVH_READY', len(faces), flush=True)
results = []
for y in [280, 290, 300, 310, 330, 350, 365]:
    for x in [36, 44, 52, 60, 68, 76, 84]:
        cam.location = (x, y, 37.65)
        cam.data.lens = math.hypot(y - 240, x) * .36
        cam.rotation_euler = (Vector((0, 240, 55)) - cam.location).to_track_quat('-Z', 'Y').to_euler()
        bpy.context.view_layer.update()
        corners = cam.data.view_frame(scene=scene)
        low_x, high_x = min(p.x for p in corners), max(p.x for p in corners)
        low_y, high_y = min(p.y for p in corners), max(p.y for p in corners)
        external = Counter()
        moon = Counter()
        for i in range(100):
            for j in range(75):
                direction = cam.matrix_world.to_3x3() @ Vector((low_x + (high_x-low_x)*(i+.5)/100, low_y+(high_y-low_y)*(j+.5)/75, corners[0].z))
                hit, normal, index, distance = tree.ray_cast(cam.location, direction.normalized(), 30000)
                if hit is not None and hit.y < 230:
                    external[owners[index]] += 1
        for i in range(96):
            a = 2 * math.pi * i / 96
            target = Vector((21.6 * math.cos(a), 239.9, 56 + 21.6 * math.sin(a)))
            if target.z < 36.4:
                continue
            direction = target - cam.location
            hit, normal, index, distance = tree.ray_cast(cam.location, direction.normalized(), direction.length - .2)
            if hit is not None and not owners[index].startswith(('V05_月门', '尺度人形')):
                moon[owners[index]] += 1
        results.append({'x':x,'y':y,'lens':cam.data.lens,'external_pixels':sum(external.values()),'moon_blocked':sum(moon.values()),'external':dict(external),'moon':dict(moon)})
(QA / 'sightline_candidates.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print('BEST_SIGHTLINES',json.dumps(sorted(results,key=lambda r:(r['moon_blocked'],r['external_pixels']))[:12],ensure_ascii=False),flush=True)
