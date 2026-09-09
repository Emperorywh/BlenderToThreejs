"""
只读检查第八版建筑保留、十六台相机、月门净空、基础支撑与文件资源。
沿用之前已验证的射线方法，报告实际失败点，不为通过检查改变可见性。
"""
import bpy
import bmesh
import ast
import json
import hashlib
import struct
from pathlib import Path
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'v08'/'qa'
candidate=bpy.data.filepath
old=ast.parse((ROOT/'scripts'/'audit_architecture_v06.py').read_text(encoding='utf-8'))
defs=[n for n in old.body if isinstance(n,ast.FunctionDef) and n.name in ['signature','camera_record','tree_for','cast','axis_height','check_route']]
exec(compile(ast.Module(body=defs,type_ignores=[]),'沿用只读核验函数','exec'),globals())
bpy.ops.wm.open_mainfile(filepath=str(ROOT/'HeavenlyPalace_Environment_v07.blend'))
source=bpy.context.scene
protected={o.name:signature(o,False) for c in source.collection.children if c.name.startswith(('02_','03_','04_','05_','05A_','06_','07_','08_','11_','14_')) for o in c.all_objects}
cameras={o.name:camera_record(o) for o in source.objects if o.type=='CAMERA'}
markers={m.frame:m.camera.name for m in source.timeline_markers if m.camera}
resolution=[source.render.resolution_x,source.render.resolution_y,source.render.pixel_aspect_x,source.render.pixel_aspect_y]
waterpaths={o.name:o['水流中心线'] for o in source.objects if '水流中心线' in o}
floor_names={o.name for o in source.objects if o.type=='MESH' and ('踏步高度_米' in o or '地坪' in o.name or '压顶板' in o.name or o.name.startswith('前庭侧边通行带_') or o.name in ['前庭净空_220乘300米_标高0','前庭总承台_宽310米','月门前平台_标高0','广场中轴仪式通带_宽18米','前山入口休息平台','东侧桥_连续水平桥面','东侧观景台_标高12'])}
bpy.ops.wm.open_mainfile(filepath=candidate)
scene=bpy.context.scene
scene.frame_set(4)
bpy.context.view_layer.update()
deps=bpy.context.evaluated_depsgraph_get()
changed=[n for n,s in protected.items() if n not in scene.objects or signature(scene.objects[n],False)!=s]
changed_cameras=[n for n,c in cameras.items() if n not in scene.objects or camera_record(scene.objects[n])!=c]
changed_markers=[f for f,n in markers.items() if not any(m.frame==f and m.camera and m.camera.name==n for m in scene.timeline_markers)]
architecture={o for c in scene.collection.children if c.name.startswith(('02_','03_','04_','05_','05A_','06_','07_','08_')) for o in c.all_objects if o.type in ('MESH','CURVE') and not o.hide_render}
rocks={o for c in scene.collection.children if c.name.startswith('01_') for o in c.all_objects if o.type=='MESH' and not o.hide_render}
pines={o for c in scene.collection.children if c.name.startswith('09_') for o in c.all_objects if o.type=='MESH' and not o.hide_render}
water={o for c in scene.collection.children if c.name.startswith('10_') for o in c.all_objects if o.type=='MESH' and not o.hide_render}
tree,owners=tree_for(architecture|rocks|pines|water)
ground_objects=[o for o in architecture if o.name in floor_names or o.name.startswith(('V06_入口至前庭同层接坪','V06_回廊地坪下补齐承托')) or '_连续石地栿' in o.name]
ground_tree,ground_owners=tree_for(ground_objects)
rock_tree,rock_owners=tree_for(rocks)
print('V08_AUDIT_BVH_READY',flush=True)


# 月门与中轴采用既有坐标采样，含所有新环境和水体。
# 体积云不参与实心碰撞；另用云团包围范围检查广场上空是否存在云容器。
moon_blocked=[]
moon_through=[]
moon_samples=0
cam=next(o for o in scene.objects if o.name.startswith('CAM_04_'))
for i in range(-30,31):
    for j in range(-30,31):
        x,z=22*.96*i/30,56+22*.96*j/30
        if x*x+(z-56)**2>(22*.96)**2 or z<36.3:
            continue
        moon_samples+=1
        hit=cast(cam.location,(x,239.92,z))
        if hit:
            moon_blocked.append(hit)
        hit=cast((x,239,z),(x,247,z))
        if hit:
            moon_through.append(hit)
entry_blocked=[hit for x in (-13.8,-8,0,8,13.8) for z in (.20,1.80,28.8) if (hit:=cast((x,-197,z),(x,-187,z)))]
routes=[]
for x in [-8,0,8]:
    check_route(f'中轴全程_X{x}',[(x,-354.9+699.7*i/1399) for i in range(1400)],lambda x,y:axis_height(y))
for sign in [-1,1]:
    for dx in [-5.1,0,5.1]:
        check_route(f'侧廊_{sign}_{dx}',[(sign*130+dx,-175+310*i/310) for i in range(311)],lambda x,y:.1 if y>=-167 else 0)
for dy in [-5.97,0,5.97]:
    check_route(f'亭桥通路_{dy}',[(151+184.5*i/370,178+dy) for i in range(371)],lambda x,y:12)


# 每块岩体单独做实体内测试，避免相接岩块的重叠表面干扰奇偶计数。
# 建筑基础和台阶原岩采用第七版相同采样标高。
rock_parts=[]
for ob in rocks:
    vv=[ob.matrix_world@v.co for v in ob.data.vertices]
    ff=[tuple(p.vertices) for p in ob.data.polygons]
    lo=[min(v[i] for v in vv) for i in range(3)]
    hi=[max(v[i] for v in vv) for i in range(3)]
    rock_parts.append((ob.name,BVHTree.FromPolygons(vv,ff),lo,hi))


def inside_rock(p):
    p=Vector(p)
    direction=Vector((.00231,.00379,1)).normalized()
    for name,bvh,lo,hi in rock_parts:
        if not all(lo[i]-.002<=p[i]<=hi[i]+.002 for i in range(3)):
            continue
        start=p.copy()
        crossings=0
        for k in range(40):
            hit,n,index,distance=bvh.ray_cast(start,direction,3000)
            if hit is None:
                break
            crossings+=1
            start=hit+direction*.003
        if crossings%2:
            return name
    return None


support_failures=[]
support_samples=0
for name,x0,x1,y0,y1,z,nx,ny in [('前庭承台',-154.7,154.7,-232.7,172.7,-10.04,31,42),('一级台基',-149.7,149.7,160.3,377.7,-6.04,31,23),
    ('观景平台',264.3,335.7,141.3,214.7,8.96,15,16),('桥西台',144.2,155.8,170.2,185.8,-40.04,6,7),('桥东台',258.2,269.8,170.2,185.8,-40.04,6,7),
    ('登山下段',-23.8,23.8,-354.8,-303.2,-48.74,9,22),('登山休息平台',-27.8,27.8,-302.8,-285.2,-28.04,11,9),('登山上段',-23.8,23.8,-284.8,-233.2,-24.74,9,22)]:
    for i in range(nx):
        for j in range(ny):
            p=(x0+(x1-x0)*i/(nx-1),y0+(y1-y0)*j/(ny-1),z)
            support_samples+=1
            if inside_rock(p) is None:
                support_failures.append({'name':name,'point':p})
root_failures=[]
for ob in pines:
    if '根部落点' in ob:
        p=Vector(ob['根部落点'])
        hit,n,i,d=rock_tree.ray_cast(p+Vector((0,0,1)),Vector((0,0,-1)),4)
        if hit is None or abs(hit.z-p.z)>.08:
            root_failures.append({'name':ob.name,'root':list(p),'hit':list(hit) if hit else None})
cloud_intrusions=[]
for col in scene.collection.children:
    if not col.name.startswith('18_'):
        continue
    for ob in col.objects:
        pts=[ob.matrix_world@Vector(p) for p in ob.bound_box]
        lo=[min(v[i] for v in pts) for i in range(3)]
        hi=[max(v[i] for v in pts) for i in range(3)]
        if lo[0]<155 and hi[0]>-155 and lo[1]<380 and hi[1]>-233 and lo[2]<130 and hi[2]>0:
            cloud_intrusions.append(ob.name)
images=[{'name':im.name,'source':im.source,'packed':bool(im.packed_file),'path':im.filepath} for im in bpy.data.images if im.source=='FILE']
report={'file':candidate,'blender':bpy.app.version_string,'baseline_sha256':hashlib.sha256((ROOT/'HeavenlyPalace_Environment_v07.blend').read_bytes()).hexdigest(),
        'protected_objects':len(protected),'changed_architecture':changed,'camera_count':len(cameras),'changed_cameras':changed_cameras,'changed_markers':changed_markers,
        'resolution_preserved':resolution==[scene.render.resolution_x,scene.render.resolution_y,scene.render.pixel_aspect_x,scene.render.pixel_aspect_y],
        'water_centerlines_preserved':all(n in scene.objects and scene.objects[n]['水流中心线']==p for n,p in waterpaths.items()),
        'moon_samples':moon_samples,'moon_blocked':moon_blocked,'moon_through_blocked':moon_through,'rectangular_entry_blocked':entry_blocked,
        'route_samples':sum(r['samples'] for r in routes),'route_gaps':sum(len(r['ground_gaps']) for r in routes),'route_obstructions':sum(len(r['headroom_obstructions']) for r in routes),'routes':routes,
        'support_samples':support_samples,'support_failures':support_failures,'root_failures':root_failures,'cloud_intrusions_over_plaza':cloud_intrusions,
        'images':images,'visible_mesh_objects':sum(o.type=='MESH' and not o.hide_render for o in scene.objects),
        'unique_mesh_vertices':sum(len(d.vertices) for d in {o.data for o in scene.objects if o.type=='MESH' and not o.hide_render}),
        'render':{'engine':scene.render.engine,'device':scene.cycles.device,'samples':scene.cycles.samples,'adaptive_threshold':scene.cycles.adaptive_threshold,'denoising':scene.cycles.use_denoising,'volume_bounces':scene.cycles.volume_bounces,'volume_step_rate':scene.cycles.volume_step_rate,'volume_biased':scene.cycles.volume_biased}}
report['passed']=not any([changed,changed_cameras,changed_markers,moon_blocked,moon_through,entry_blocked,support_failures,root_failures,cloud_intrusions,report['route_gaps'],report['route_obstructions']])
(OUT/'audit_v08.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('V08_AUDIT',json.dumps({k:v for k,v in report.items() if k not in ['routes','images','support_failures','root_failures']},ensure_ascii=False),flush=True)
print('V08_SUPPORT_FAILURES',support_failures[:15],flush=True)
print('V08_ROOT_FAILURES',root_failures,flush=True)
