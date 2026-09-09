"""
只读核验第九版实际场景、依赖及相机投影。
统计以渲染可见对象和求值网格为准，原文件不会被保存或修改。
"""
import bpy, json, hashlib
from pathlib import Path
from mathutils import Vector

OUT = Path(__file__).resolve().parents[1]
(OUT / 'qa').mkdir(parents=True, exist_ok=True)
scene = bpy.context.scene
deps = bpy.context.evaluated_depsgraph_get()
hidden = set()
def visit(col, parent=False):
    invisible = parent or col.hide_render
    if invisible:
        hidden.update(o.name for o in col.objects)
    for child in col.children:
        visit(child, invisible)
visit(scene.collection)
rows = []
for ob in scene.objects:
    row = dict(name=ob.name, type=ob.type, visible=not ob.hide_render and ob.name not in hidden,
        collections=[c.name for c in ob.users_collection], location=list(ob.location), dimensions=list(ob.dimensions),
        matrix=[list(r) for r in ob.matrix_world], negative_scale=ob.matrix_world.determinant()<0,
        properties={k: str(v) for k,v in ob.items()})
    if ob.type in ('MESH','CURVE','SURFACE','FONT'):
        mesh=ob.evaluated_get(deps).to_mesh()
        mesh.calc_loop_triangles()
        row.update(data=ob.data.name, vertices=len(mesh.vertices), triangles=len(mesh.loop_triangles),
            uv=[u.name for u in mesh.uv_layers], materials=[s.material.name if s.material else None for s in ob.material_slots],
            modifiers=[dict(name=m.name,type=m.type,render=m.show_render,viewport=m.show_viewport,
                **{k:getattr(m,k) for k in ('levels','render_levels','segments','width','ratio') if hasattr(m,k)}) for m in ob.modifiers])
        ob.evaluated_get(deps).to_mesh_clear()
    if ob.type == 'CAMERA':
        cam=ob.data
        row.update(camera=dict(type=cam.type,lens=cam.lens,shift_x=cam.shift_x,shift_y=cam.shift_y,
            sensor_width=cam.sensor_width,sensor_height=cam.sensor_height,sensor_fit=cam.sensor_fit,
            near=cam.clip_start,far=cam.clip_end,ortho_scale=cam.ortho_scale,
            projection_rows=[list(r) for r in ob.calc_matrix_camera(deps,x=1280,y=960,scale_x=1,scale_y=1)]))
    rows.append(row)
mats=[]
for mat in bpy.data.materials:
    mats.append(dict(name=mat.name,users=mat.users,diffuse=list(mat.diffuse_color),nodes=[dict(name=n.name,type=n.type,
        inputs={i.name:list(i.default_value) if hasattr(i.default_value,'__len__') else i.default_value for i in n.inputs if hasattr(i,'default_value') and isinstance(i.default_value,(int,float,Vector))},
        **({'image':n.image.name if n.image else None} if n.type=='TEX_IMAGE' else {})) for n in mat.node_tree.nodes] if mat.use_nodes else [],
        links=[dict(from_node=l.from_node.name,from_socket=l.from_socket.name,to_node=l.to_node.name,to_socket=l.to_socket.name) for l in mat.node_tree.links] if mat.use_nodes else []))
report=dict(source=bpy.data.filepath,source_sha256=hashlib.sha256(Path(bpy.data.filepath).read_bytes()).hexdigest(),
    blender=bpy.app.version_string,units=dict(system=scene.unit_settings.system,scale_length=scene.unit_settings.scale_length),
    objects=rows,materials=mats,images=[dict(name=i.name,path=i.filepath,packed=bool(i.packed_file),size=list(i.size),source=i.source) for i in bpy.data.images],
    libraries=[l.filepath for l in bpy.data.libraries],markers=[dict(frame=m.frame,name=m.name,camera=m.camera.name if m.camera else None) for m in scene.timeline_markers])
(OUT/'qa'/'source-audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('AUDIT_COMPLETE',len(rows),sum(r.get('triangles',0) for r in rows if r['visible']),flush=True)
