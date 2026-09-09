"""
将适配副本按资源类别写成标准 glTF 二进制文件，纹理通过共同相对目录共享。
实例数据显式写入扩展，禁止以 Blender 网格共享替代真正的 GPU 实例交付。
"""
import bpy, json, math, struct, hashlib
import numpy as np
from pathlib import Path
from collections import defaultdict
from mathutils import Matrix, Vector

OUT=Path(__file__).resolve().parents[1]
ASSETS=OUT/'assets'
SCENE=bpy.context.scene
C=Matrix(((1,0,0,0),(0,0,1,0),(0,-1,0,0),(0,0,0,1)))
def flat(m):return [m[r][c] for c in range(4) for r in range(4)]
def category(ob):
    cols=[c.name for c in ob.users_collection]
    if any(c.startswith('09_') for c in cols):return 'vegetation'
    if any(c.startswith('10_') for c in cols):return 'waterfalls'
    if any('长袍人物' in c for c in cols):return 'characters'
    if any(c.startswith(('01','17_')) for c in cols):return 'terrain'
    return 'architecture'
def region(ob):
    p=ob.matrix_world@sum((Vector(v) for v in ob.bound_box),Vector())/8
    size=180 if category(ob)!='terrain' else 500
    return (math.floor(p.x/size),math.floor(p.y/size))

# 静态小件按空间区域和材质合并，重复网格保留供扩展实例化。
# 月门、主柱、人物、水帘以及大屋面保留明确名称和独立对象。
all_meshes=[o for o in SCENE.objects if o.type=='MESH']
# 月门布尔构件含空的备用材质槽，统一继承第一槽白玉以免导出遗漏墙面。
# 不改变真实面索引；该修复只为没有指定材质的备用槽提供确定性结果。
for ob in all_meshes:
    if ob.data.materials and any(m is None for m in ob.data.materials):
        fallback=next(m for m in ob.data.materials if m)
        for i,mat in enumerate(ob.data.materials):
            if mat is None:ob.data.materials[i]=fallback
counts=defaultdict(int)
for ob in all_meshes:counts[(category(ob),region(ob),ob.data.name)]+=1
merge_groups=defaultdict(list)
for ob in all_meshes:
    ob.data.calc_loop_triangles()
    if (counts[(category(ob),region(ob),ob.data.name)]<3 and len(ob.data.materials)==1 and
        len(ob.data.loop_triangles)<4000 and category(ob) not in ('characters','waterfalls') and
        not any(w in ob.name for w in ('月门','巨柱','屋面','贴面筒瓦'))):
        merge_groups[(category(ob),region(ob),ob.data.materials[0].name)].append(ob)
merged=[]
for index,(key,group) in enumerate(merge_groups.items()):
    if len(group)<2:continue
    names=[o.name for o in group]
    # 直接拼接网格数组，避免逐次调用选择和合并操作触发全场依赖图刷新。
    # 各小件变换仅烘入一次顶点，合并体位于原点且保留逐面平滑与原 UV。
    vertices=[];faces=[];uvs=[];smooth=[]
    for source in group:
        offset=len(vertices)
        vertices.extend(tuple(source.matrix_world@v.co) for v in source.data.vertices)
        faces.extend(tuple(v+offset for v in p.vertices) for p in source.data.polygons)
        smooth.extend(p.use_smooth for p in source.data.polygons)
        uvs.extend(tuple(item.uv) for item in source.data.uv_layers[0].data)
    data=bpy.data.meshes.new(f'WEB_区域合并网格_{index}')
    data.from_pydata(vertices,[],faces)
    data.materials.append(group[0].data.materials[0])
    uv=data.uv_layers.new(name='TileUV')
    uv.data.foreach_set('uv',np.array(uvs,dtype=np.float32).ravel())
    for poly,flag in zip(data.polygons,smooth):poly.use_smooth=flag
    ob=bpy.data.objects.new(f'WEB_{key[0]}_区域{key[1][0]}_{key[1][1]}_{key[2]}',data)
    group[0].users_collection[0].objects.link(ob)
    ob['web_sources']=json.dumps(names,ensure_ascii=False)
    merged.append({'name':ob.name,'source_count':len(names),'sources':names})
    for source in group:bpy.data.objects.remove(source,do_unlink=True)
    if index%40==0:print('MERGE',index,len(merge_groups),flush=True)

class GLB:
    def __init__(self):
        self.doc={'asset':{'version':'2.0','generator':'HeavenlyPalace WebAssets v01 / Blender Python'},'scene':0,'scenes':[{'nodes':[]}],
            'nodes':[],'meshes':[],'materials':[],'textures':[],'images':[],'samplers':[{'magFilter':9729,'minFilter':9987,'wrapS':10497,'wrapT':10497}],
            'accessors':[],'bufferViews':[],'buffers':[{}]}
        self.bin=bytearray();self.mats={};self.tex={};self.geometry={};self.instances=[]
    def accessor(self,array,kind,component=5126,target=None):
        dtype={5126:'<f4',5125:'<u4'}[component]
        array=np.ascontiguousarray(array,dtype=dtype)
        while len(self.bin)%4:self.bin.append(0)
        view={'buffer':0,'byteOffset':len(self.bin),'byteLength':array.nbytes}
        if target:view['target']=target
        self.bin.extend(array.tobytes());vi=len(self.doc['bufferViews']);self.doc['bufferViews'].append(view)
        row={'bufferView':vi,'componentType':component,'count':len(array),'type':kind}
        if kind=='VEC3':row.update(min=array.min(axis=0).tolist(),max=array.max(axis=0).tolist())
        i=len(self.doc['accessors']);self.doc['accessors'].append(row);return i
    def texture(self,file):
        if file not in self.tex:
            i=len(self.doc['textures']);self.tex[file]=i
            self.doc['images'].append({'uri':'textures/'+file})
            self.doc['textures'].append({'source':i,'sampler':0})
        return self.tex[file]
    def material(self,mat):
        if mat.name in self.mats:return self.mats[mat.name]
        spec=json.loads(mat['web_spec'])
        files=spec['files']
        pbr={'baseColorFactor':spec['base_factor'],'roughnessFactor':1 if files else spec['roughness'],'metallicFactor':1 if files else spec['metallic']}
        row={'name':mat.name,'pbrMetallicRoughness':pbr,'doubleSided':False,'extras':{'sourceMaterial':spec['source']}}
        if files:
            pbr['baseColorTexture']={'index':self.texture(files['basecolor'])}
            pbr['metallicRoughnessTexture']={'index':self.texture(files['orm'])}
            row['normalTexture']={'index':self.texture(files['normal']),'texCoord':spec.get('normal_uv',0)}
        if 'Waterfall' in mat.name:row['doubleSided']=True;row['extras']['pending']='Web water shader and height fade'
        i=len(self.doc['materials']);self.mats[mat.name]=i;self.doc['materials'].append(row);return i
    def mesh(self,ob):
        data=ob.data
        key=(data.name,tuple(m.name for m in data.materials))
        if key in self.geometry:return self.geometry[key]
        data.calc_loop_triangles()
        primitives=[]
        normals=np.empty(len(data.corner_normals)*3,dtype=np.float32);data.corner_normals.foreach_get('vector',normals);normals=normals.reshape(-1,3)
        positions=np.empty(len(data.vertices)*3,dtype=np.float32);data.vertices.foreach_get('co',positions);positions=positions.reshape(-1,3)
        loop_vertices=np.empty(len(data.loops),dtype=np.int32);data.loops.foreach_get('vertex_index',loop_vertices)
        uv_arrays=[]
        for uv in data.uv_layers:
            a=np.empty(len(data.loops)*2,dtype=np.float32);uv.data.foreach_get('uv',a);a=a.reshape(-1,2);a[:,1]=1-a[:,1];uv_arrays.append(a)
        for mi,mat in enumerate(data.materials):
            loops=np.array([li for t in data.loop_triangles if t.material_index==mi for li in t.loops],dtype=np.int32)
            if len(loops)==0:continue
            p=positions[loop_vertices[loops]][:,[0,2,1]].copy();p[:,2]*=-1
            n=normals[loops][:,[0,2,1]].copy();n[:,2]*=-1
            n/=np.maximum(np.linalg.norm(n,axis=1,keepdims=True),1e-12)
            joined=np.concatenate([p,n]+[uv[loops] for uv in uv_arrays],axis=1)
            unique,inverse=np.unique(joined,axis=0,return_inverse=True)
            attrs={'POSITION':self.accessor(unique[:,:3],'VEC3',target=34962),'NORMAL':self.accessor(unique[:,3:6],'VEC3',target=34962)}
            for j in range(len(uv_arrays)):attrs['TEXCOORD_'+str(j)]=self.accessor(unique[:,6+j*2:8+j*2],'VEC2',target=34962)
            primitives.append({'attributes':attrs,'indices':self.accessor(inverse,'SCALAR',5125,34963),'material':self.material(mat)})
        i=len(self.doc['meshes']);self.doc['meshes'].append({'name':data.name,'primitives':primitives});self.geometry[key]=i;return i
    def group(self,objects):
        first=objects[0]
        mesh=self.mesh(first)
        row={'name':first.name,'mesh':mesh}
        if len(objects)>=3:
            translations=[];rotations=[];scales=[]
            for ob in objects:
                matrix=C@ob.matrix_world@C.inverted()
                t,q,s=matrix.decompose();translations.append(list(t));rotations.append([q.x,q.y,q.z,q.w]);scales.append(list(s))
            row['name']=f'INSTANCE_{category(first)}_{region(first)}_{first.data.name}'
            row['extensions']={'EXT_mesh_gpu_instancing':{'attributes':{
                'TRANSLATION':self.accessor(translations,'VEC3'),'ROTATION':self.accessor(rotations,'VEC4'),'SCALE':self.accessor(scales,'VEC3')}}}
            row['extras']={'instanceNames':[o.name for o in objects]}
            self.doc['extensionsUsed']=['EXT_mesh_gpu_instancing'];self.doc['extensionsRequired']=['EXT_mesh_gpu_instancing']
            self.instances.append({'name':row['name'],'count':len(objects),'primitives':len(self.doc['meshes'][mesh]['primitives'])})
        else:
            row['matrix']=flat(C@first.matrix_world@C.inverted())
            if 'web_sources' in first:row['extras']={'mergedSources':json.loads(first['web_sources'])}
        index=len(self.doc['nodes']);self.doc['nodes'].append(row);self.doc['scenes'][0]['nodes'].append(index)
    def save(self,path):
        # glTF 可选集合在为空时必须省略，人物常量材质无需图像或纹理数组。
        # 不写空集合，使输出通过标准验证器的结构检查。
        for key in ['images','textures']:
            if not self.doc[key]:del self.doc[key]
        while len(self.bin)%4:self.bin.append(0)
        self.doc['buffers'][0]['byteLength']=len(self.bin)
        encoded=json.dumps(self.doc,ensure_ascii=False,separators=(',',':')).encode('utf-8')
        encoded+=b' '*((-len(encoded))%4)
        payload=struct.pack('<4sII',b'glTF',2,12+8+len(encoded)+8+len(self.bin))+struct.pack('<I4s',len(encoded),b'JSON')+encoded+struct.pack('<I4s',len(self.bin),b'BIN\0')+self.bin
        path.write_bytes(payload)
        return {'file':path.name,'bytes':len(payload),'sha256':hashlib.sha256(payload).hexdigest(),'nodes':len(self.doc['nodes']),'meshes':len(self.doc['meshes']),
            'materials':len(self.doc['materials']),'textures':len(self.doc.get('textures',[])),'instance_groups':self.instances,'instances':sum(g['count'] for g in self.instances)}

manifest={'version':'v01','unit':'meter','coordinate_system':'glTF Y-up; x,z,-y; common origin','origin':[0,0,0],'compression':'none (baseline)',
    'source_blend':'HeavenlyPalace_WebAssets_v01.blend','files':[],'pending_effects':['远景云海','近岛云雾','入口五团遮檐云','瀑布水雾和动画'],
    'camera_file':'cameras.json','environment_file':'environment-layout.json'}
used_textures=set()
used_materials={}
for kind in ['architecture','terrain','vegetation','characters','waterfalls']:
    exporter=GLB();groups=defaultdict(list)
    for ob in SCENE.objects:
        if ob.type=='MESH' and category(ob)==kind:groups[(ob.data.name,region(ob),tuple(m.name for m in ob.data.materials))].append(ob)
    for group in groups.values():
        if len(group)>=3:exporter.group(group)
        else:
            for ob in group:exporter.group([ob])
    manifest['files'].append(exporter.save(ASSETS/(kind+'.glb')))
    used_textures.update(image['uri'] for image in exporter.doc.get('images',[]) if 'uri' in image)
    for name in exporter.mats:used_materials[name]=json.loads(bpy.data.materials[name]['web_spec'])
    print('GLB_WRITTEN',kind,manifest['files'][-1]['bytes'],flush=True)
# 纹理目录是本流程生成的输出，仅保留最终 GLB 实际引用的图片。
# 避免程序材质烘焙中间图再次进入交付清单与构建产物。
for image_path in (ASSETS/'textures').glob('*.png'):
    if 'textures/'+image_path.name not in used_textures:image_path.unlink()
manifest['textures']=[{'file':uri,'bytes':(ASSETS/uri).stat().st_size,'sha256':hashlib.sha256((ASSETS/uri).read_bytes()).hexdigest()} for uri in sorted(used_textures)]
manifest['material_file']='materials.json'
(ASSETS/'materials.json').write_text(json.dumps({'materials':list(used_materials.values())},ensure_ascii=False,indent=2),encoding='utf-8')
(ASSETS/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
(OUT/'qa'/'merge-report.json').write_text(json.dumps(merged,ensure_ascii=False,indent=2),encoding='utf-8')
SCENE['WEB_静态合并']='按区域与材质合并；实例数据由可重复导出脚本显式写入EXT_mesh_gpu_instancing'
bpy.context.preferences.filepaths.save_version=0
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'HeavenlyPalace_WebAssets_v01.blend'),compress=True)
print('EXPORT_COMPLETE',flush=True)
