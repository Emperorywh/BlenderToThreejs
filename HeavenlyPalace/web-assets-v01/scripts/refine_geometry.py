"""
在独立网页副本内针对已确认的松针、瓦垄、浮雕和远山应用减面。
显式更新依赖图后获取求值网格，统计与保存都使用实际生效后的结果。
"""
import bpy,json,time
from pathlib import Path

OUT=Path(__file__).resolve().parents[1]
scene=bpy.context.scene
deps=bpy.context.evaluated_depsgraph_get()
data_objects={}
for ob in scene.objects:
    if ob.type=='MESH':data_objects.setdefault(ob.data,[]).append(ob)
changes=[]
for data,objects in data_objects.items():
    ob=objects[0]
    ratio=1
    if any(m and '松针' in m.name for m in data.materials):ratio=.28
    elif '贴面筒瓦垄' in ob.name:ratio=.45
    elif ob.name.startswith('V09_') and any(w in ob.name for w in ['卷草','浮雕','团莲']):ratio=.35
    elif any(c.name.startswith('17_') for c in ob.users_collection):ratio=.6
    if ratio==1 or ob.get('web_decimated') or data.get('web_decimated'):continue
    data.calc_loop_triangles();before=len(data.loop_triangles)
    modifier=ob.modifiers.new('WEB_实际应用画面贡献减面','DECIMATE');modifier.ratio=ratio
    deps.update()
    result=bpy.data.meshes.new_from_object(ob.evaluated_get(deps),depsgraph=deps)
    result.calc_loop_triangles()
    after=len(result.loop_triangles)
    result['web_decimated']=True
    assert after<before,(ob.name,before,after)
    ob.modifiers.clear()
    for user in objects:user.data=result;user['web_decimated']=True
    changes.append(dict(name=ob.name,before=before,after=after,copies=len(objects)))
    print('REFINE',ob.name,before,after,flush=True)
stats=[]
for ob in scene.objects:
    if ob.type=='MESH':
        ob.data.calc_loop_triangles()
        stats.append(dict(name=ob.name,triangles=len(ob.data.loop_triangles),vertices=len(ob.data.vertices),data=ob.data.name))
report=dict(changes=changes,objects=stats,triangles=sum(o['triangles'] for o in stats),unique_meshes=len({o['data'] for o in stats}))
(OUT/'qa'/'final-geometry.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
bpy.context.preferences.filepaths.save_version=0
bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'HeavenlyPalace_WebAssets_v01.blend'),compress=True)
print('REFINE_COMPLETE',report['triangles'],flush=True)
