"""
核验主殿样板的柱网、门洞、屋面承托和有效网格，并按需生成 Blender 离线预览。
所有渲染设置只在内存中修改，不启动浏览器，也不把检查灯光写回网页工程。
"""
import bpy
import json
import math
import sys
from pathlib import Path
from mathutils import Vector
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(Path(__file__).resolve().parent))
from refine_main_hall import roof_height
# 空间参数与实际场景版本共同确定验收尺寸，原始工程仍可执行基准检查。
# 屋顶解析函数继续使用基准空间，核验时反变换实际世界顶点再比较净空。
from hall_space import FLOOR_Z, GATE_CENTER_Z, GATE_RADIUS, canonical_point, space_active


def verify():
    """
    同时检查结构约束与可导出的数据，特别关注屋檐穿插和月门净空。
    面积阈值采用米制小量，排除真正退化面而保留细小金线和雕刻。
    """
    scene=bpy.context.scene
    report={'revision':scene.get('主殿样板版本'),'meshes':[],'issues':[]}
    columns=[o for o in scene.objects if o.name.startswith('主殿巨柱') and o.name.endswith('_柱身')]
    report['columns']=len(columns)
    for ob in scene.objects:
        if ob.type!='MESH' or not ob.name.startswith('H01_'):
            continue
        data=ob.data
        data.calc_loop_triangles()
        coordinates=np.empty(len(data.vertices)*3,dtype=np.float32)
        data.vertices.foreach_get('co',coordinates)
        if not np.isfinite(coordinates).all() or not data.uv_layers:
            report['issues'].append(ob.name+': 坐标或纹理坐标无效')
        if any(m is None or 'web_spec' not in m for m in data.materials):
            report['issues'].append(ob.name+': 缺失网页材质规格')
        if ob.matrix_world.determinant()<=0:
            report['issues'].append(ob.name+': 存在翻转缩放')
        degenerate=sum(t.area<1e-8 for t in data.loop_triangles)
        if degenerate:
            report['issues'].append(ob.name+f': {degenerate} 个退化三角形')
        report['meshes'].append({'name':ob.name,'triangles':len(data.loop_triangles)})
    bracket=bpy.data.objects['H01_柱头补间三跳斗拱']
    points=[bracket.matrix_world@v.co for v in bracket.data.vertices]
    if space_active():
        points=[canonical_point(point) for point in points]
    penetration=max(point.z-roof_height(point.x,point.y)+.85 for point in points)
    report['brackets_roof_clearance_m']=-penetration
    if penetration>0:
        report['issues'].append('斗拱穿出瓦面')
    moon=bpy.data.objects['V05_月门通厚石圈_净径44米']
    # 旧对象名继续作为稳定引用，实际门洞中心、完成面和净径从实体元数据读取。
    # 同时与空间版本的目标净径比较，避免旧尺寸元数据使错误模型通过检查。
    center=float(moon.get('门洞中心标高_米',GATE_CENTER_Z if space_active() else 56.0))
    floor=float(moon.get('完成面标高_米',FLOOR_Z))
    expected_radius=GATE_RADIUS if space_active() else 22.0
    recorded_radius=float(moon.get('净开口直径_米',expected_radius*2))/2
    vertices=[moon.matrix_world@v.co for v in moon.data.vertices]
    front=max(point.y for point in vertices)
    radius=min(math.hypot(point.x,point.z-center) for point in vertices)
    report['moon_diameter_m']=radius*2
    report['moon_center_z']=center
    report['space_revision']=scene.get('殿内空间版本','baseline')
    report['moon_open']=[]
    # 以整座主殿为射线检查对象，确保新梁架与石栏没有挡住原门洞。
    # 月门底部与上缘分别取样，同时检查中央台阶口的人行高度。
    targets=[o for o in scene.objects if o.type=='MESH' and
             (o.name.startswith('H01_') or any(c.name.startswith('05A_') for c in o.users_collection))]
    for x,z in ((0,floor+1),(0,center),(0,center+expected_radius-1),
                (expected_radius-2,center),(-expected_radius+2,center)):
        blocked=False
        for ob in targets:
            inv=ob.matrix_world.inverted()
            origin=inv@Vector((x,front-16,z))
            direction=(inv.to_3x3()@Vector((0,1,0))).normalized()
            if ob.ray_cast(origin,direction,distance=23)[0]:
                blocked=True
                break
        report['moon_open'].append(not blocked)
    report['passed']=(report['revision']=='h01' and len(columns)==24 and
                      abs(radius-expected_radius)<.002 and abs(recorded_radius-expected_radius)<.002
                      and all(report['moon_open']) and not report['issues'])
    (ROOT/'qa'/'main-hall-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False),flush=True)
    assert report['passed'],'主殿样板未通过实体核验。'


def render():
    """
    外景以主殿三分之四角机位检查完整轮廓，同时提供灰模和殿内细节检查。
    灰模仅用于判断形体，彩色预览用于检查材质分区，两者均不能替代网页验收。
    """
    scene=bpy.context.scene
    for ob in list(scene.objects):
        if ob.type=='LIGHT':
            bpy.data.objects.remove(ob,do_unlink=True)
        elif ob.type=='MESH' and any(c.name.startswith(('10','17_')) for c in ob.users_collection):
            ob.hide_render=True
    world=bpy.data.worlds.new('主殿检查天空')
    world.use_nodes=True
    world.node_tree.nodes['Background'].inputs[0].default_value=(.31,.39,.49,1)
    world.node_tree.nodes['Background'].inputs[1].default_value=.65
    scene.world=world
    data=bpy.data.lights.new('主殿检查日光','SUN')
    data.energy=3.0
    data.angle=.08
    data.color=(1,.88,.73)
    sun=bpy.data.objects.new('主殿检查日光',data)
    scene.collection.objects.link(sun)
    sun.rotation_euler=Vector((520,650,-790)).to_track_quat('-Z','Y').to_euler()
    camera_data=bpy.data.cameras.new('主殿检查机位')
    camera=bpy.data.objects.new('主殿检查机位',camera_data)
    scene.collection.objects.link(camera)
    interior='--interior' in sys.argv
    clay='--clay' in sys.argv
    camera.location=(42,324,43) if interior else (240,44,125)
    target=Vector((-12,255,79) if interior else (0,285,79))
    camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler()
    camera_data.lens=19 if interior else 36
    camera_data.clip_end=10000
    scene.timeline_markers.clear()
    scene.camera=camera
    scene.render.engine='CYCLES'
    scene.cycles.samples=32
    scene.cycles.use_denoising=True
    scene.render.use_border=False
    scene.render.use_compositing=False
    scene.render.use_sequencer=False
    scene.render.resolution_x=1500
    scene.render.resolution_y=1125
    scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG'
    scene.render.film_transparent=False
    scene.view_settings.view_transform='AgX'
    scene.view_settings.exposure=0
    if clay:
        override=bpy.data.materials.new('主殿检查灰模')
        override.use_nodes=True
        override.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value=(.42,.42,.42,1)
        override.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value=.70
        bpy.context.view_layer.material_override=override
    suffix='interior' if interior else 'clay' if clay else 'exterior'
    scene.render.filepath=str(ROOT/'qa'/f'main-hall-{suffix}.png')
    bpy.ops.render.render(write_still=True)


if __name__=='__main__':
    verify()
    if '--render' in sys.argv:
        render()
