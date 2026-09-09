"""
逐项核验第九版与第八点一版的建筑保护范围、月门净空和相机灯光。
此脚本为交付数据审计，不改场景，不保存任一工程。
"""
import bpy
import json
import math
import hashlib
import struct
from pathlib import Path
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'v09'
source=ROOT/'HeavenlyPalace_Lookdev_v08_1.blend'
dest=ROOT/'HeavenlyPalace_Detail_v09.blend'
report=json.loads((OUT/'qa'/'build_report.json').read_text(encoding='utf-8'))


# 共享网格只计算一次几何摘要；局部修改被明确列入允许清单。
# 云海、屋顶主体、路线、平台与全部原相机必须与源工程一致。
def fingerprint(data):
    digest=hashlib.sha256()
    for v in data.vertices:
        digest.update(struct.pack('<3f',*v.co))
    for p in data.polygons:
        digest.update(struct.pack('<'+'I'*len(p.vertices),*p.vertices))
    return digest.hexdigest()


def nodes_state(tree):
    return [(n.name,n.type,[(s.name,str(s.default_value)) for s in n.inputs if hasattr(s,'default_value')]) for n in tree.nodes] if tree else []


def snapshot(path):
    bpy.ops.wm.open_mainfile(filepath=str(path))
    scene=bpy.context.scene
    meshes={m.name:fingerprint(m) for m in bpy.data.meshes if m.users}
    objects={}
    for ob in scene.objects:
        row={'type':ob.type,'transform':[list(r) for r in ob.matrix_world],'hide_render':ob.hide_render,'hide_viewport':ob.hide_viewport,'collections':sorted(c.name for c in ob.users_collection)}
        if ob.type=='MESH':
            row['geometry']=meshes[ob.data.name]
            row['modifiers']=[(m.name,m.type) for m in ob.modifiers]
        elif ob.type=='CAMERA':
            row['optics']=[ob.data.lens,ob.data.shift_x,ob.data.shift_y,ob.data.clip_start,ob.data.clip_end]
        elif ob.type=='LIGHT':
            row['light']=[ob.data.energy,list(ob.data.color),nodes_state(ob.data.node_tree)]
        objects[ob.name]=row
    return {'objects':objects,'collections':{c.name:(c.hide_render,c.hide_viewport) for c in bpy.data.collections},'world':nodes_state(scene.world.node_tree),'exposure':scene.view_settings.exposure,'markers':{m.frame:m.camera.name for m in scene.timeline_markers if m.camera},'cloud_materials':{m.name:nodes_state(m.node_tree) for m in bpy.data.materials if '云' in m.name and m.use_nodes},'vertices':sum(len(m.vertices) for m in bpy.data.meshes if m.users),'polygons':sum(len(m.polygons) for m in bpy.data.meshes if m.users)}


before=snapshot(source)
after=snapshot(dest)
allowed=set(report['changed'])
unexpected=[]
for name,row in before['objects'].items():
    if name not in allowed and after['objects'].get(name)!=row:
        unexpected.append(name)
camera_changes=[name for name,row in before['objects'].items() if row['type']=='CAMERA' and after['objects'].get(name)!=row]
light_changes=[name for name,row in before['objects'].items() if row['type']=='LIGHT' and after['objects'].get(name)!=row]
collection_changes=[name for name,state in before['collections'].items() if after['collections'].get(name)!=state]
moon=bpy.data.objects['V05_月门通厚石圈_净径44米']
ornaments=[ob for ob in bpy.context.scene.objects if ob.name.startswith('V09_月门_连续')]
minimum_radius=min(math.hypot(v.co.x,v.co.z-56) for ob in ornaments for v in ob.data.vertices)
people=[]
for number in ('01','02','03'):
    parts=[ob for ob in bpy.context.scene.objects if ob.name.startswith('V09_人物'+number+'_')]
    points=[ob.matrix_world@Vector(p) for ob in parts for p in ob.bound_box]
    people.append({'number':number,'min_z':min(v.z for v in points),'max_z':max(v.z for v in points),'height':max(v.z for v in points)-min(v.z for v in points)})
cam=bpy.data.objects['CAM_04_殿内望云_v08_1']
external_images=[{'name':im.name,'path':im.filepath} for im in bpy.data.images if im.source=='FILE' and not im.packed_file]
result={'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'source_unchanged':hashlib.sha256(source.read_bytes()).hexdigest()==report['source_sha256'],'protected_object_count':len(before['objects'])-len(allowed),'unexpected_changes':unexpected,'original_camera_changes':camera_changes,'light_changes':light_changes,'collection_visibility_changes':collection_changes,'world_unchanged':before['world']==after['world'],'exposure_unchanged':before['exposure']==after['exposure'],'cloud_materials_unchanged':before['cloud_materials']==after['cloud_materials'],'four_camera_bindings_unchanged':all(before['markers'][i]==after['markers'][i] for i in range(1,5)),'moon_subject_geometry_unchanged':before['objects'][moon.name]['geometry']==after['objects'][moon.name]['geometry'],'moon_net_diameter_m':moon.get('净开口直径_米'),'moon_ornament_minimum_radius_m':minimum_radius,'camera_position':list(cam.location),'camera_lens_mm':cam.data.lens,'camera_shift_x':cam.data.shift_x,'eye_height_m':cam.location.z-36,'people':people,'unpacked_file_images':external_images,'source_unique_mesh_vertices':before['vertices'],'v09_unique_mesh_vertices':after['vertices'],'source_unique_polygons':before['polygons'],'v09_unique_polygons':after['polygons'],'new_object_count':len(after['objects'])-len(before['objects'])}
result['passed']=all([result['source_unchanged'],not unexpected,not camera_changes,not light_changes,not collection_changes,result['world_unchanged'],result['exposure_unchanged'],result['cloud_materials_unchanged'],result['four_camera_bindings_unchanged'],result['moon_subject_geometry_unchanged'],minimum_radius>22,all(abs(p['height']-1.8)<.002 and abs(p['min_z']-36)<.002 for p in people),not external_images])
(OUT/'qa'/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print('V09_AUDIT',json.dumps(result,ensure_ascii=False),flush=True)
assert result['passed'], '第九版交付核验存在未通过项，请检查报告。'
