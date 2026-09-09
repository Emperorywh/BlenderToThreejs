"""
从只读第九版生成独立的网页资源副本，支持复用已经完成的烘焙贴图。
程序材质烘焙在隔离场景中完成，几何、相机与环境数据统一使用米制原点。
"""
import bpy, math, json, hashlib, time, sys
import numpy as np
from pathlib import Path
from mathutils import Matrix, Vector
from collections import defaultdict

OUT=Path(__file__).resolve().parents[1]
TEX=OUT/'assets'/'textures'
TEX.mkdir(parents=True,exist_ok=True)
SCENE=bpy.context.scene
AUDIT=json.loads((OUT/'qa'/'source-audit.json').read_text(encoding='utf-8'))
assert hashlib.sha256(Path(bpy.data.filepath).read_bytes()).hexdigest()==AUDIT['source_sha256']
ROWS={r['name']:r for r in AUDIT['objects']}
C=Matrix(((1,0,0,0),(0,0,1,0),(0,-1,0,0),(0,0,0,1)))
REPORT={'source_sha256':AUDIT['source_sha256'],'materials':[],'excluded':[],'geometry':[]}
# 默认复用当前版本已完成的烘焙，避免无变化时重复消耗渲染时间。
# 修改原始程序材质后显式重烘焙，确保共享贴图同步更新。
REBAKE='--rebake' in sys.argv
def write(path,data):
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
def flat(m):
    return [m[r][c] for c in range(4) for r in range(4)]
def point(p):
    return list(C.to_3x3()@Vector(p))
def volume(ob):
    return any(s.material and s.material.use_nodes and any(n.type=='PRINCIPLED_VOLUME' for n in s.material.node_tree.nodes) for s in ob.material_slots)
def bounds(ob):
    pts=[C@ob.matrix_world@Vector(v) for v in ob.bound_box]
    return {'min':[min(p[i] for p in pts) for i in range(3)],'max':[max(p[i] for p in pts) for i in range(3)]}

# 相机直接保存 Blender 实际投影矩阵，避免焦距和镜头偏移的单位误用。
# 相机局部轴仍是右、上、负方向观察，世界矩阵只左乘一次坐标转换。
deps=bpy.context.evaluated_depsgraph_get()
cameras=[]
for marker in sorted(SCENE.timeline_markers,key=lambda m:m.frame)[:4]:
    ob=marker.camera
    cam=ob.data
    projection=ob.calc_matrix_camera(deps,x=1280,y=960,scale_x=1,scale_y=1)
    world=C@ob.matrix_world
    cameras.append(dict(id=marker.frame,name=ob.name,position=list(world.translation),quaternion_xyzw=list(world.to_quaternion())[1:]+[world.to_quaternion().w],
        direction=list(world.to_3x3()@Vector((0,0,-1))),up=list(world.to_3x3()@Vector((0,1,0))),
        projection_type=cam.type,lens_mm=cam.lens,sensor_width_mm=cam.sensor_width,sensor_height_mm=cam.sensor_height,sensor_fit=cam.sensor_fit,
        shift_x=cam.shift_x,shift_y=cam.shift_y,near=cam.clip_start,far=cam.clip_end,
        vertical_fov_degrees=math.degrees(2*math.atan(1/projection[1][1])) if cam.type=='PERSP' else None,
        orthographic_width=cam.ortho_scale if cam.type=='ORTHO' else None,orthographic_height=cam.ortho_scale*.75 if cam.type=='ORTHO' else None,
        projection_matrix=flat(projection),world_matrix=flat(world)))
write(OUT/'assets'/'cameras.json',dict(unit='meter',coordinate_system='glTF Y-up; (x,y,z)=(Blender.x,Blender.z,-Blender.y)',matrix_storage='column-major; Three.Matrix4.fromArray; camera local forward=-Z',viewport=[1280,960],aspect=4/3,cameras=cameras))
environment=[]
water=[]
for ob in list(SCENE.objects):
    if ob.type=='MESH' and ROWS[ob.name]['visible']:
        if volume(ob):
            kind='entrance_roof_occluder' if '低云舌' in ob.name else ('waterfall_mist' if '水雾' in ob.name or '轻雾' in ob.name else ('distant_cloud_sea' if ('远移' in ' '.join(s.material.name for s in ob.material_slots if s.material) or ob.location.y < -1500) else 'near_island_cloud'))
            world=C@ob.matrix_world@C.inverted()
            environment.append(dict(name=ob.name,kind=kind,position=point(ob.matrix_world.translation),bounds=bounds(ob),dimensions=point(ob.dimensions)[:2]+[abs(ob.dimensions.y)],matrix=flat(world),
                direction=point(ob.matrix_world.to_3x3()@Vector((0,1,0))),purpose='遮挡入口屋檐，保证殿内月门视线只见云海' if kind=='entrance_roof_occluder' else '远景地平线云海' if kind=='distant_cloud_sea' else '水流入云及跌水薄雾' if kind=='waterfall_mist' else '岛底与岛边翻涌云层',
                source_materials=[s.material.name for s in ob.material_slots if s.material],properties=ROWS[ob.name]['properties']))
        if '水流中心线' in ob:
            path=[point(p) for p in json.loads(ob['水流中心线'])]
            water.append(dict(name=ob.name,material='WEB_Waterfall_Static_Preview',bounds=bounds(ob),outlet=path[0],lip=path[3],flow_direction=list((Vector(path[4])-Vector(path[3])).normalized()),centerline=path,gravity=[0,-1,0],purpose='保留完整水帘；后续沿中心线计算水流距离、速度及入云消隐',fade_height_m=[-410,-190]))
write(OUT/'assets'/'environment-layout.json',dict(unit='meter',coordinate_system='glTF Y-up',matrix_storage='column-major',origin=[0,0,0],effects=environment,waterfalls=water,
    interior_visibility_contract='五团入口局部云必须在所有机位存在，并与远景云海联合遮蔽入口屋檐；近岛低云只负责岛边与瀑布，不可替代入口遮挡。验证页尚未重建云海，因此殿内可能看到屋檐，不能据此移动建筑或相机。',
    reconstruction_status='云海、水雾、瀑布动画待 Web 重建；静态瀑布几何可用'))

# 将不需要的对象从副本中移除，参考图和历史参照不进入正式资源。
# 原始文件与审计表仍保存完整历史，副本只留下正式模型和四个主相机。
keep_cameras={c['name'] for c in cameras}
for ob in list(SCENE.objects):
    row=ROWS[ob.name]
    reason=None
    if not row['visible']: reason='隐藏或历史对象'
    elif ob.type=='MESH' and volume(ob): reason='体积容器转环境布局'
    elif any(c.startswith('11_') for c in row['collections']): reason='历史方块尺度参照'
    elif ob.type not in ('MESH','CAMERA'): reason='灯光或辅助对象'
    elif ob.type=='CAMERA' and ob.name not in keep_cameras: reason='非正式机位'
    if reason:
        REPORT['excluded'].append(dict(name=ob.name,reason=reason))
        bpy.data.objects.remove(ob,do_unlink=True)

meshes=[o for o in SCENE.objects if o.type=='MESH']
used=sorted({s.material for o in meshes for s in o.material_slots if s.material},key=lambda m:m.name)
BAKE=bpy.data.scenes.new('WEB_隔离烘焙场景')
bpy.context.window.scene=BAKE
BAKE.render.engine='CYCLES'
BAKE.cycles.device='CPU'
BAKE.cycles.samples=8
BAKE.render.threads_mode='FIXED'
BAKE.render.threads=12
BAKE.render.bake.margin=8
BAKE.world=bpy.data.worlds.new('WEB_烘焙无照明')
BAKE.world.use_nodes=True
BAKE.world.node_tree.nodes.get('Background').inputs['Strength'].default_value=0
origin=bpy.data.objects.new('WEB_烘焙米制原点',None)
BAKE.collection.objects.link(origin)
MATERIALS={}
SPECS={}

def image_load(path,noncolor=False):
    im=bpy.data.images.load(str(path),check_existing=True)
    im.colorspace_settings.name='Non-Color' if noncolor else 'sRGB'
    return im

def save_image(im,path):
    im.filepath_raw=str(path)
    im.file_format='PNG'
    im.save()

def bake_plane(mat,identifier):
    name=mat.name
    floor='石板' in name or '地坪' in name
    rock='山岩' in name
    roof='琉璃瓦' in name
    ceiling='回纹' in name
    size=1024 if floor or rock or roof or ceiling else 512
    extent=8 if floor else 16 if rock else 9.92 if roof else 1 if ceiling else 4
    vertical=('树皮' in name or '顺z' in name or '瀑布' in name or rock)
    if roof:
        vertices=[(0,0,0),(extent,0,0),(extent,5.76,5.76),(0,5.76,5.76)]
    elif vertical:
        vertices=[(0,0,0),(extent,0,0),(extent,0,extent),(0,0,extent)]
    else:
        z=36 if floor else 0
        vertices=[(0,0,z),(extent,0,z),(extent,extent,z),(0,extent,z)]
    data=bpy.data.meshes.new('WEB_材质样片')
    data.from_pydata(vertices,[],[(0,1,2,3)])
    uv=data.uv_layers.new(name='UVMap')
    for l,coord in zip(uv.data,[(0,0),(1,0),(1,1),(0,1)]):l.uv=coord
    ob=bpy.data.objects.new('WEB_材质烘焙样片',data)
    BAKE.collection.objects.link(ob)
    work=mat.copy()
    data.materials.append(work)
    for n in work.node_tree.nodes:
        if n.type=='TEX_COORD' and n.object:n.object=origin
    bs=next(n for n in work.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
    output=next(n for n in work.node_tree.nodes if n.type=='OUTPUT_MATERIAL')
    nodes,links=work.node_tree.nodes,work.node_tree.links
    target=nodes.new('ShaderNodeTexImage')
    nodes.active=target
    emit=nodes.new('ShaderNodeEmission')
    combine=nodes.new('ShaderNodeCombineXYZ')
    combine.inputs[0].default_value=1
    for channel,socket in [(1,'Roughness'),(2,'Metallic')]:
        if bs.inputs[socket].is_linked:links.new(bs.inputs[socket].links[0].from_socket,combine.inputs[channel])
        else:combine.inputs[channel].default_value=bs.inputs[socket].default_value
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True)
    bpy.context.view_layer.objects.active=ob
    files={}
    for channel in ['basecolor','orm','normal']:
        path=TEX/f'{identifier}_{channel}.png'
        files[channel]=path.name
        if path.exists() and not REBAKE:continue
        im=bpy.data.images.new(path.stem,width=size,height=size,alpha=False,float_buffer=False)
        im.colorspace_settings.name='sRGB' if channel=='basecolor' else 'Non-Color'
        target.image=im
        for link in list(output.inputs['Surface'].links):links.remove(link)
        if channel=='normal':
            links.new(bs.outputs['BSDF'],output.inputs['Surface'])
        else:
            for link in list(emit.inputs['Color'].links):links.remove(link)
            if channel=='orm':links.new(combine.outputs[0],emit.inputs['Color'])
            elif bs.inputs['Base Color'].is_linked:links.new(bs.inputs['Base Color'].links[0].from_socket,emit.inputs['Color'])
            else:emit.inputs['Color'].default_value=bs.inputs['Base Color'].default_value
            links.new(emit.outputs[0],output.inputs['Surface'])
        print('BAKE',name,channel,flush=True)
        bpy.ops.object.bake(type='NORMAL' if channel=='normal' else 'EMIT')
        # 平铺边界只在窄边带内镜像混合，避免噪声贴图重复时出现硬接缝。
        # 地面四米砖缝本身周期对齐；样片保留其真实砖缝，不参与该混合。
        if not floor and not ceiling:
            pixels=np.array(im.pixels[:],dtype=np.float32).reshape(size,size,4)
            for axis in (0,1):
                for k in range(8):
                    a=[slice(None),slice(None)];b=a.copy();a[axis]=k;b[axis]=size-1-k
                    aa,bb=tuple(a),tuple(b);mean=(pixels[aa]+pixels[bb])*.5;factor=(8-k)/8
                    pixels[aa]=pixels[aa]*(1-factor)+mean*factor;pixels[bb]=pixels[bb]*(1-factor)+mean*factor
            im.pixels.foreach_set(pixels.ravel())
        save_image(im,path)
        bpy.data.images.remove(im)
    spec=dict(id=identifier,source=name,size=size,tile_m=extent,vertical=vertical,ceiling=ceiling,roof=roof,files=files,
        base_color='sRGB; emission bake; no direct light/highlights/AO',normal='Non-Color; tangent +Y',orm='Non-Color; R=1 (no baked scene AO), G=roughness, B=metallic')
    bpy.data.objects.remove(ob,do_unlink=True)
    bpy.data.meshes.remove(data)
    bpy.data.materials.remove(work)
    return spec

# 一个程序材质只烘焙一套共享贴图；常量材质直接保留 PBR 参数。
# 透明体积另行交接，针叶使用原来的实体几何和不透明材质以避免排序问题。
for index,old in enumerate(used):
    if not any(n.type=='BSDF_PRINCIPLED' for n in old.node_tree.nodes):continue
    bs=next(n for n in old.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
    procedural=any(n.type.startswith('TEX_') for n in old.node_tree.nodes)
    spec=bake_plane(old,f'm{index:02}') if procedural else dict(id=f'm{index:02}',source=old.name,files={},tile_m=4)
    new=bpy.data.materials.new('WEB_'+old.name)
    new.use_nodes=True
    nb=new.node_tree.nodes.get('Principled BSDF')
    for socket in ['Base Color','Roughness','Metallic']:
        nb.inputs[socket].default_value=bs.inputs[socket].default_value
    if '瀑布' in old.name:
        new.name='WEB_Waterfall_Static_Preview'
    if procedural:
        for channel,socket in [('basecolor','Base Color'),('orm',None),('normal','Normal')]:
            tex=new.node_tree.nodes.new('ShaderNodeTexImage')
            tex.image=image_load(TEX/spec['files'][channel],channel!='basecolor')
            if channel=='orm':
                sep=new.node_tree.nodes.new('ShaderNodeSeparateColor')
                new.node_tree.links.new(tex.outputs['Color'],sep.inputs[0])
                new.node_tree.links.new(sep.outputs[1],nb.inputs['Roughness'])
                new.node_tree.links.new(sep.outputs[2],nb.inputs['Metallic'])
            elif channel=='normal':
                nm=new.node_tree.nodes.new('ShaderNodeNormalMap')
                new.node_tree.links.new(tex.outputs['Color'],nm.inputs['Color'])
                new.node_tree.links.new(nm.outputs[0],nb.inputs['Normal'])
            else:new.node_tree.links.new(tex.outputs['Color'],nb.inputs[socket])
    new.diffuse_color=old.diffuse_color
    spec.update(name=new.name,base_factor=list(bs.inputs['Base Color'].default_value) if not procedural else [1,1,1,1],roughness=bs.inputs['Roughness'].default_value,metallic=bs.inputs['Metallic'].default_value)
    new['web_spec']=json.dumps(spec,ensure_ascii=False)
    MATERIALS[old.name]=new
    SPECS[new.name]=spec
    REPORT['materials'].append(spec)

# 柱上浅浮雕投射到九十六边圆柱；所有巨柱复用同一张切线法线。
# 柱体圆周只转动 UV 对应方位，最近柱的原浮雕旋转保持为零点八二弧度。
source_shaft=next(o for o in meshes if o.name.startswith('主殿巨柱') and o.name.endswith('_柱身'))
source_relief=bpy.data.objects['V09_巨柱_卷云与仰莲_共享浅浮雕']
source_relief_data=source_relief.data
sides=96
verts=[(r*math.cos(i*math.tau/sides),r*math.sin(i*math.tau/sides),z) for z,r in [(37.6,3.6),(80.4,3.312)] for i in range(sides)]
faces=[(i,(i+1)%sides,(i+1)%sides+sides,i+sides) for i in range(sides)]
faces += [tuple(reversed(range(sides))),tuple(sides+i for i in range(sides))]
shaft_mesh=bpy.data.meshes.new('WEB_巨柱_96边_共享法线')
shaft_mesh.from_pydata(verts,[],faces)
uv=shaft_mesh.uv_layers.new(name='ReliefUV')
for p in shaft_mesh.polygons:
    p.use_smooth=p.index<sides
    for k,li in enumerate(p.loop_indices):
        if p.index<sides:uv.data[li].uv=[(p.index/sides,0),((p.index+1)/sides,0),((p.index+1)/sides,1),(p.index/sides,1)][k]
        else:uv.data[li].uv=(.001,.001)
normal_path=TEX/'column_relief_normal.png'
if REBAKE or not normal_path.exists():
    low=bpy.data.objects.new('WEB_柱纹法线接收体',shaft_mesh)
    BAKE.collection.objects.link(low)
    bake_mat=bpy.data.materials.new('WEB_柱纹法线烘焙')
    bake_mat.use_nodes=True
    shaft_mesh.materials.append(bake_mat)
    target=bake_mat.node_tree.nodes.new('ShaderNodeTexImage')
    im=bpy.data.images.new('column_relief_normal',width=2048,height=2048,alpha=False)
    im.colorspace_settings.name='Non-Color'
    target.image=im
    bake_mat.node_tree.nodes.active=target
    bpy.ops.object.select_all(action='DESELECT')
    high=[]
    for source in [source_shaft,source_relief]:
        ob=source.copy();ob.data=source.data.copy();BAKE.collection.objects.link(ob)
        ob.location.x=0;ob.location.y=0;ob.rotation_euler=(0,0,0)
        # 高模材质替换成无程序法线的白玉，专注保存真实雕刻形状。
        # 微观石纹通过基础材质颜色和粗糙度保留，不烘焙场景光照。
        ob.data.materials.clear();ob.data.materials.append(bake_mat.copy())
        ob.select_set(True);high.append(ob)
    low.select_set(True);bpy.context.view_layer.objects.active=low
    BAKE.render.bake.use_selected_to_active=True
    BAKE.render.bake.cage_extrusion=.32
    BAKE.render.bake.max_ray_distance=.8
    print('BAKE_COLUMN_RELIEF',flush=True)
    bpy.ops.object.bake(type='NORMAL')
    save_image(im,normal_path)
    BAKE.render.bake.use_selected_to_active=False
    for ob in high+[low]:bpy.data.objects.remove(ob,do_unlink=True)
    shaft_mesh.materials.clear()
column_mat=MATERIALS['V08_白玉_柱身栏杆'].copy()
column_mat.name='WEB_巨柱_烘焙卷云仰莲'
spec=dict(SPECS[MATERIALS['V08_白玉_柱身栏杆'].name])
spec.update(name=column_mat.name,normal_uv=1,files={**spec['files'],'normal':normal_path.name})
column_mat['web_spec']=json.dumps(spec,ensure_ascii=False)
SPECS[column_mat.name]=spec
nb=column_mat.node_tree.nodes.get('Principled BSDF')
for node in column_mat.node_tree.nodes:
    if node.type=='NORMAL_MAP':node.uv_map='ReliefUV'
    if node.type=='TEX_IMAGE' and 'normal' in node.image.name:
        node.image=image_load(normal_path,True)
        texuv=column_mat.node_tree.nodes.new('ShaderNodeUVMap');texuv.uv_map='ReliefUV'
        column_mat.node_tree.links.new(texuv.outputs[0],node.inputs['Vector'])
shaft_mesh.materials.append(column_mat)
bpy.context.window.scene=SCENE
bpy.data.scenes.remove(BAKE)

# 修改器先降低不影响轮廓的小倒角段数，再按相同网格和修改器复用求值结果。
# 大屋面和月门主体不做全局减面，远松针与贴面装饰有针对性地简化。
for ob in meshes:
    for mod in ob.modifiers:
        if mod.type=='BEVEL':mod.segments=1 if mod.width<.12 else min(mod.segments,2)
bpy.context.view_layer.update()
deps=bpy.context.evaluated_depsgraph_get()
cache={}
for i,ob in enumerate(meshes):
    if ob.data==source_relief_data:
        REPORT['excluded'].append(dict(name=ob.name,reason='浮雕已烘焙到共享巨柱法线'))
        bpy.data.objects.remove(ob,do_unlink=True)
        continue
    if ob.name.startswith('主殿巨柱') and ob.name.endswith('_柱身'):
        ob.data=shaft_mesh
        for slot in ob.material_slots:slot.link='DATA'
        ob.location.z=0
        ob.modifiers.clear()
        if ob.name=='主殿巨柱_列4_进4_柱身':ob.rotation_euler.z=.82
        continue
    key=(ob.data.name,tuple((m.type,m.width,m.segments) for m in ob.modifiers if m.type=='BEVEL'),tuple(s.material.name if s.material else '' for s in ob.material_slots))
    if key not in cache:
        data=bpy.data.meshes.new_from_object(ob.evaluated_get(deps),depsgraph=deps)
        # 针叶等构件在对象级覆盖材质，必须读取实际插槽而非网格的历史材质表。
        # 求值网格统一写入已烘焙材质，随后清除对象级覆盖以确保 Blender 与网页一致。
        actual=[slot.material for slot in ob.material_slots]
        data.materials.clear()
        fallback=next((MATERIALS[m.name] for m in actual if m and m.name in MATERIALS),None)
        for mat in actual:data.materials.append(MATERIALS.get(mat.name,fallback) if mat else fallback)
        ratio=1
        if any('松针' in m.name for m in data.materials if m):ratio=.28
        elif '贴面筒瓦垄' in ob.name:ratio=.45
        elif ob.name.startswith('V09_') and any(w in ob.name for w in ['卷草','浮雕','团莲']):ratio=.35
        elif any(c.name.startswith('17_') for c in ob.users_collection):ratio=.6
        if ratio<1:
            temp=bpy.data.objects.new('WEB_减面临时体',data);SCENE.collection.objects.link(temp)
            modifier=temp.modifiers.new('WEB_按画面贡献减面','DECIMATE');modifier.ratio=ratio
            deps.update()
            evaluated=bpy.data.meshes.new_from_object(temp.evaluated_get(deps),depsgraph=deps)
            bpy.data.objects.remove(temp,do_unlink=True);bpy.data.meshes.remove(data);data=evaluated
            data['web_decimated']=True
        cache[key]=data
    ob.data=cache[key]
    for slot in ob.material_slots:slot.link='DATA'
    ob.modifiers.clear()
    if i%500==0:print('GEOMETRY',i,len(meshes),flush=True)

# 为共享网格建立确定性的米制盒投影；唯一的大地形使用世界坐标以保持接缝连续。
# 柱纹使用第二套圆柱 UV，基础玉石继续使用每四米重复的独立 UV。
mesh_users=defaultdict(list)
for ob in SCENE.objects:
    if ob.type=='MESH':mesh_users[ob.data].append(ob)
for data,users in mesh_users.items():
    original_relief=data.uv_layers.get('ReliefUV')
    relief_coords=[tuple(v.uv) for v in original_relief.data] if original_relief else None
    while data.uv_layers:data.uv_layers.remove(data.uv_layers[0])
    uv=data.uv_layers.new(name='TileUV')
    ref=users[0]
    minimum=[min(v.co[i] for v in data.vertices) for i in range(3)]
    maximum=[max(v.co[i] for v in data.vertices) for i in range(3)]
    for poly in data.polygons:
        mat=data.materials[poly.material_index] if len(data.materials)>poly.material_index else None
        spec=SPECS.get(mat.name,{}) if mat else {}
        extent=spec.get('tile_m',4)
        axis=max(range(3),key=lambda i:abs(poly.normal[i]))
        axes=[i for i in range(3) if i!=axis]
        for li in poly.loop_indices:
            p=data.vertices[data.loops[li].vertex_index].co
            if len(users)==1 and not spec.get('ceiling'):p=ref.matrix_world@p
            coords=[p[j]/extent for j in axes]
            if spec.get('ceiling'):coords=[(p[j]-minimum[j])/max(.001,maximum[j]-minimum[j]) for j in [0,1]]
            uv.data[li].uv=coords
    if relief_coords:
        relief=data.uv_layers.new(name='ReliefUV')
        for item,coord in zip(relief.data,relief_coords):item.uv=coord
    data.uv_layers.active_index=0

SCENE.unit_settings.system='METRIC';SCENE.unit_settings.scale_length=1
SCENE.render.resolution_x=1280;SCENE.render.resolution_y=960;SCENE.render.resolution_percentage=100
SCENE['WEB_坐标说明']='工程为原始米制Z-up；GLB及JSON统一转为(x,z,-y)，禁止分别居中或额外旋转'
SCENE['WEB_云海状态']='体积已迁移environment-layout.json，需在Web重建入口五团遮檐云和远景云海'
SCENE['WEB_原文件SHA256']=AUDIT['source_sha256']
for image in list(bpy.data.images):
    if image.filepath and str(TEX) in bpy.path.abspath(image.filepath):image.pack()
    elif image.source!='VIEWER':bpy.data.images.remove(image)
SCENE.camera=bpy.data.objects[cameras[0]['name']]
SCENE.world=bpy.data.worlds.new('WEB_基础环境')
SCENE.world.use_nodes=True
SCENE.world.node_tree.nodes.get('Background').inputs['Color'].default_value=(.65,.72,.78,1)
SCENE.world.node_tree.nodes.get('Background').inputs['Strength'].default_value=.8
meshes=[o for o in SCENE.objects if o.type=='MESH']
for ob in meshes:
    ob.data.calc_loop_triangles()
    REPORT['geometry'].append(dict(name=ob.name,data=ob.data.name,triangles=len(ob.data.loop_triangles),vertices=len(ob.data.vertices),bounds=bounds(ob),negative_scale=ob.matrix_world.determinant()<0))
REPORT['after_triangles']=sum(r['triangles'] for r in REPORT['geometry'])
REPORT['after_objects']=len(meshes)
REPORT['after_unique_meshes']=len({o.data for o in meshes})
REPORT['before_triangles']=sum(r.get('triangles',0) for r in AUDIT['objects'] if r['visible'])
write(OUT/'qa'/'adaptation-report.json',REPORT)
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'HeavenlyPalace_WebAssets_v01.blend'),compress=True)
print('ADAPTATION_COMPLETE',REPORT['after_triangles'],flush=True)
