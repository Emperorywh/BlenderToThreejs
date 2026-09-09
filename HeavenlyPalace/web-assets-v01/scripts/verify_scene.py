"""
核验副本内的保护尺寸、相机与有效材质，以及投影至固定画幅的几何锚点。
仅追加读取原始工程中的少量保护网格供对照，完成后退出且不保存检查场景。
"""
import bpy,json,math,hashlib
from pathlib import Path
from mathutils import Vector,Matrix

OUT=Path(__file__).resolve().parents[1]
SOURCE=OUT.parent/'stage1'/'HeavenlyPalace_Detail_v09.blend'
scene=bpy.context.scene
camera_json=json.loads((OUT/'assets'/'cameras.json').read_text(encoding='utf-8'))
audit=json.loads((OUT/'qa'/'source-audit.json').read_text(encoding='utf-8'))
checks={}
C=Matrix(((1,0,0,0),(0,0,1,0),(0,-1,0,0),(0,0,0,1)))
checks['original_sha256_unchanged']=hashlib.sha256(SOURCE.read_bytes()).hexdigest()==audit['source_sha256']
moon=bpy.data.objects['V05_月门通厚石圈_净径44米']
moon_vertices=[moon.matrix_world@v.co for v in moon.data.vertices]
radius=min(math.hypot(v.x,v.z-56) for v in moon_vertices)
checks['moon_clear_diameter_m']=radius*2
checks['moon_diameter_44m']=abs(radius-22)<.001
checks['people']=[]
landmarks=[dict(name='月门左净边',position=[-22,56,-246]),dict(name='月门右净边',position=[22,56,-246]),dict(name='月门上净边',position=[0,78,-246])]
for index in range(1,4):
    objects=[o for o in scene.objects if o.name.startswith(f'V09_人物{index:02}_')]
    vertices=[o.matrix_world@Vector(c) for o in objects for c in o.bound_box]
    bottom=min(v.z for v in vertices);top=max(v.z for v in vertices)
    checks['people'].append(dict(index=index,height_m=top-bottom,bottom_z=bottom))
    head=bpy.data.objects[f'V09_人物{index:02}_头']
    landmarks.append(dict(name=f'人物{index}头部',position=list(C@head.matrix_world.translation)))
checks['people_height_and_platform']=all(abs(p['height_m']-1.8)<.015 and abs(p['bottom_z']-36)<.002 for p in checks['people'])
for name in ['主殿巨柱_列4_进4_柱身','主殿巨柱_列3_进4_柱身']:
    ob=bpy.data.objects[name]
    for suffix,z in [('柱脚',37.6),('柱顶',80.4)]:landmarks.append(dict(name=name+suffix,position=[ob.location.x,z,-ob.location.y]))
checks['negative_scale_objects']=[o.name for o in scene.objects if o.type=='MESH' and o.matrix_world.determinant()<0]
checks['missing_uv_objects']=[o.name for o in scene.objects if o.type=='MESH' and not o.data.uv_layers]
checks['volume_objects']=[o.name for o in scene.objects if o.type=='MESH' and any(m and m.use_nodes and any(n.type=='PRINCIPLED_VOLUME' for n in m.node_tree.nodes) for m in o.data.materials)]
checks['projection_max_error']=0
projection_rows=[]
deps=bpy.context.evaluated_depsgraph_get()
for data in camera_json['cameras']:
    ob=bpy.data.objects[data['name']]
    P=ob.calc_matrix_camera(deps,x=1280,y=960,scale_x=1,scale_y=1)
    exported=Matrix([data['projection_matrix'][i::4] for i in range(4)])
    error=max(abs(P[r][c]-exported[r][c]) for r in range(4) for c in range(4))
    checks['projection_max_error']=max(checks['projection_max_error'],error)
    V=(C@ob.matrix_world).inverted()
    row=dict(camera=data['name'],points=[])
    for landmark in landmarks:
        clip=P@V@Vector((*landmark['position'],1))
        row['points'].append(dict(**landmark,pixel=[(clip.x/clip.w+1)*640,(1-clip.y/clip.w)*480],in_front=clip.w>0))
    projection_rows.append(row)
checks['passed']=checks['original_sha256_unchanged'] and checks['moon_diameter_44m'] and checks['people_height_and_platform'] and not checks['negative_scale_objects'] and not checks['missing_uv_objects'] and not checks['volume_objects'] and checks['projection_max_error']<1e-6
(OUT/'qa'/'scene-verification.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
# 投影锚点仅用于导出核验，保存到被忽略的中间目录。
# 正式 Web 资源目录只保留运行与后续场景接入需要的数据。
(OUT/'qa'/'projection-landmarks.json').write_text(json.dumps(projection_rows,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(checks,ensure_ascii=False),flush=True)
assert checks['passed']
