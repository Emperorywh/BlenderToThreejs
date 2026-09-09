"""
将对象级材质覆盖固化为网页网格材质，补齐旧版针叶和月门的历史材质槽。
使用已经完成的烘焙结果重建丢弃的零用户材质，不重新烘焙也不修改原文件。
"""
import bpy,json
from pathlib import Path
from collections import defaultdict
OUT=Path(__file__).resolve().parents[1]
report=json.loads((OUT/'qa'/'adaptation-report.json').read_text(encoding='utf-8'))
specs={s['source']:s for s in report['materials']}
mapping={}
for source,spec in specs.items():
    mat=bpy.data.materials.get(spec['name'])
    if mat is None:
        mat=bpy.data.materials.new(spec['name']);mat.use_nodes=True
        bs=mat.node_tree.nodes.get('Principled BSDF')
        bs.inputs['Base Color'].default_value=spec['base_factor'];bs.inputs['Roughness'].default_value=spec['roughness'];bs.inputs['Metallic'].default_value=spec['metallic']
        for kind,file in spec['files'].items():
            tex=mat.node_tree.nodes.new('ShaderNodeTexImage')
            im=bpy.data.images.load(str(OUT/'assets'/'textures'/file),check_existing=True)
            im.colorspace_settings.name='sRGB' if kind=='basecolor' else 'Non-Color';im.pack();tex.image=im
            if kind=='basecolor':mat.node_tree.links.new(tex.outputs[0],bs.inputs['Base Color'])
            elif kind=='normal':
                nm=mat.node_tree.nodes.new('ShaderNodeNormalMap');mat.node_tree.links.new(tex.outputs[0],nm.inputs['Color']);mat.node_tree.links.new(nm.outputs[0],bs.inputs['Normal'])
            else:
                sep=mat.node_tree.nodes.new('ShaderNodeSeparateColor');mat.node_tree.links.new(tex.outputs[0],sep.inputs[0]);mat.node_tree.links.new(sep.outputs[1],bs.inputs['Roughness']);mat.node_tree.links.new(sep.outputs[2],bs.inputs['Metallic'])
        mat['web_spec']=json.dumps(spec,ensure_ascii=False)
    mapping[source]=mat
cache={};changed=[]
for mat in bpy.data.materials:
    if 'web_spec' in mat and json.loads(mat['web_spec']).get('normal_uv')==1:
        for node in mat.node_tree.nodes:
            if node.type=='NORMAL_MAP':node.uv_map='ReliefUV'
for ob in bpy.context.scene.objects:
    if ob.type!='MESH':continue
    actual=[s.material for s in ob.material_slots]
    if all(m and m.name.startswith('WEB_') for m in actual):continue
    converted=[mapping.get(m.name,m) if m else None for m in actual]
    if ob.name.startswith('主殿巨柱') and ob.name.endswith('_柱身'):converted=[bpy.data.materials['WEB_巨柱_烘焙卷云仰莲']]
    fallback=next(m for m in converted if m)
    converted=[m or fallback for m in converted]
    key=(ob.data.name,tuple(m.name for m in converted))
    if key not in cache:
        data=ob.data.copy();data.materials.clear()
        for mat in converted:data.materials.append(mat)
        cache[key]=data
    ob.data=cache[key]
    for slot in ob.material_slots:slot.link='DATA'
    changed.append(ob.name)
# 以最终实际材质重新生成平铺 UV，避免历史材质槽导致地面使用默认四米周期。
# 第二套柱纹 UV 原样保留，基本色使用最终材质定义的米制重复范围。
users=defaultdict(list)
for ob in bpy.context.scene.objects:
    if ob.type=='MESH':users[ob.data].append(ob)
for data,objects in users.items():
    ref=objects[0]
    uv=data.uv_layers.get('TileUV') or data.uv_layers.new(name='TileUV')
    minimum=[min(v.co[i] for v in data.vertices) for i in range(3)]
    maximum=[max(v.co[i] for v in data.vertices) for i in range(3)]
    for poly in data.polygons:
        mat=data.materials[poly.material_index]
        spec=json.loads(mat['web_spec'])
        axes=[i for i in range(3) if i!=max(range(3),key=lambda i:abs(poly.normal[i]))]
        for li in poly.loop_indices:
            p=data.vertices[data.loops[li].vertex_index].co
            if len(objects)==1 and not spec.get('ceiling'):p=ref.matrix_world@p
            coords=[p[j]/spec.get('tile_m',4) for j in axes]
            if spec.get('ceiling'):coords=[(p[j]-minimum[j])/max(.001,maximum[j]-minimum[j]) for j in [0,1]]
            uv.data[li].uv=coords
(OUT/'qa'/'material-slot-fixes.json').write_text(json.dumps(changed,ensure_ascii=False,indent=2),encoding='utf-8')
bpy.context.preferences.filepaths.save_version=0
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'HeavenlyPalace_WebAssets_v01.blend'),compress=True)
print('MATERIAL_SLOT_FIXES',len(changed),flush=True)
