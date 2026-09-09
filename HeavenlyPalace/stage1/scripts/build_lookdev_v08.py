"""
从第七版生成第八版，分开执行环境修形与材质灯光，便于先检查中性轮廓。
建筑网格、对象变换与全部原相机保持原始数据，只在新文件中编辑环境和着色。
所有随机量固定种子，尺寸为米；共享叶簇与程序纹理限制静态场景的资源开销。
"""
import bpy
import bmesh
import math
import random
import json
import sys
import hashlib
import struct
from pathlib import Path
from mathutils import Vector, noise

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'v08'
QA=OUT/'qa'
for directory in [OUT,QA,OUT/'renders']:
    directory.mkdir(parents=True,exist_ok=True)
ARGS=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
STAGE=ARGS[ARGS.index('--stage')+1] if '--stage' in ARGS else 'environment'
BASE=ROOT/'HeavenlyPalace_Environment_v07.blend'
BASE_HASH='35f97b548ec813fc7f15de03837e0a8b483fcd5eaa78c6c292559983586f4efb'
if hashlib.sha256(BASE.read_bytes()).hexdigest()!=BASE_HASH:
    raise RuntimeError('第七版基准摘要变化，停止生成以免使用错误布局。')
bpy.ops.wm.open_mainfile(filepath=str(BASE if STAGE=='environment' else QA/'v08_environment.blend'))
S=bpy.context.scene
P=json.loads((ROOT/'v07'/'design_parameters_v07.json').read_text(encoding='utf-8'))
REPORT={'baseline_sha256':BASE_HASH,'stage':STAGE}


# 通用工具只创建第八版数据；原建筑的共享网格不复制、不细分。
# 新环境按类别进入独立集合，方便在工程内逐项选择和继续调整。
def collection(name,parent=None):
    c=bpy.data.collections.get(name) or bpy.data.collections.new(name)
    owner=parent or S.collection
    if c.name not in owner.children:
        owner.children.link(c)
    return c


def mesh(name,verts,faces,col,mat=None,smooth=False):
    data=bpy.data.meshes.new(name+'_网格')
    data.from_pydata(verts,[],faces)
    data.update()
    if mat:
        data.materials.append(mat)
    for p in data.polygons:
        p.use_smooth=smooth
    ob=bpy.data.objects.new(name,data)
    col.objects.link(ob)
    ob['制作阶段']='V08 静态场景'
    return ob


def simple_material(name,color,rough=.65):
    m=bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes=True
    m.diffuse_color=(*color,1)
    bs=m.node_tree.nodes.get('Principled BSDF')
    if bs:
        bs.inputs['Base Color'].default_value=(*color,1)
        bs.inputs['Roughness'].default_value=rough
    return m


def tube(name,points,radii,col,mat,sides=9,steps=3):
    pts=[Vector(p) for p in points]
    centers=[]
    widths=[]
    for j in range(len(pts)-1):
        p0,p1,p2,p3=pts[max(0,j-1)],pts[j],pts[j+1],pts[min(len(pts)-1,j+2)]
        for k in range(steps):
            t=k/steps
            centers.append(.5*(2*p1+(-p0+p2)*t+(2*p0-5*p1+4*p2-p3)*t*t+(-p0+3*p1-3*p2+p3)*t*t*t))
            widths.append(radii[j]*(1-t)+radii[j+1]*t)
    centers.append(pts[-1])
    widths.append(radii[-1])
    vv=[]
    for i,(p,r) in enumerate(zip(centers,widths)):
        tangent=(centers[min(i+1,len(centers)-1)]-centers[max(0,i-1)]).normalized()
        ref=Vector((0,1,0)) if abs(tangent.y)<.93 else Vector((1,0,0))
        u=tangent.cross(ref).normalized()
        v=tangent.cross(u).normalized()
        for k in range(sides):
            a=math.tau*k/sides
            rr=r*(1+.075*math.sin(a*5+i*.13)+.045*math.cos(a*3-i*.2))
            vv.append(p+rr*(math.cos(a)*u+math.sin(a)*v))
    ff=[tuple(reversed(range(sides)))]
    for j in range(len(centers)-1):
        for k in range(sides):
            a=j*sides+k
            b=j*sides+(k+1)%sides
            ff.append((a,b,b+sides,a+sides))
    ff.append(tuple(range(len(vv)-sides,len(vv))))
    return mesh(name,vv,ff,col,mat,True)


def configure_render(samples=48,percent=100):
    S.render.engine='CYCLES'
    S.cycles.device='CPU'
    S.cycles.samples=samples
    S.cycles.use_denoising=True
    S.cycles.adaptive_threshold=.035
    S.cycles.max_bounces=7
    S.cycles.diffuse_bounces=3
    S.cycles.glossy_bounces=3
    S.cycles.transmission_bounces=4
    S.cycles.transparent_max_bounces=12
    S.cycles.volume_bounces=1
    S.cycles.volume_biased=True
    S.cycles.volume_step_rate=1
    S.cycles.volume_max_steps=768
    S.cycles.sample_clamp_indirect=3
    S.render.threads_mode='FIXED'
    S.render.threads=16
    S.render.resolution_x=1800
    S.render.resolution_y=1350
    S.render.resolution_percentage=percent
    S.render.image_settings.file_format='PNG'
    S.render.image_settings.color_mode='RGB'
    S.render.image_settings.color_depth='8'
    S.render.film_transparent=False


def render(frame,path,samples=24,percent=50):
    configure_render(samples,percent)
    S.frame_set(frame)
    S.camera=next(m.camera for m in S.timeline_markers if m.frame==frame)
    S.render.filepath=str(path)
    bpy.ops.render.render(write_still=True)
    print('V08_RENDER',frame,str(path),flush=True)


# 修形避让区根据第七版实际台基、前阶和亭桥定义。
# 保留根盘周围与水潭岸岩的接触位置，避免局部起伏破坏承托关系。
def protection(p):
    x,y,z=p
    if -161<x<161 and -237<y<383 and z>-10:
        return 0.0
    if abs(x)<34 and -367<y<-229 and z>-58:
        return 0.0
    if 254<x<341 and 133<y<221 and z>-12:
        return 0.0
    if 165<x<254 and 110<y<262:
        return 0.0
    for rec in P['pine_records']:
        if (x-rec['xy'][0])**2+(y-rec['xy'][1])**2<42**2 and z>-20:
            return 0.0
    return 1.0


def environment():
    rockcol=next(c for c in S.collection.children if c.name.startswith('01_'))
    pinecol=next(c for c in S.collection.children if c.name.startswith('09_'))
    watercol=next(c for c in S.collection.children if c.name.startswith('10_'))
    oldcloud=next(c for c in S.collection.children if c.name.startswith('15_'))
    for ob in list(oldcloud.all_objects):
        ob.hide_render=True
        ob.hide_set(True)
    rockmat=bpy.data.materials['V07_岩体_灰青']
    changed=[]
    for ob in list(rockcol.all_objects):
        if ob.type!='MESH' or any(s in ob.name for s in ['岸岩','岩唇','承托','阶床']):
            continue
        bm=bmesh.new()
        bm.from_mesh(ob.data)
        bmesh.ops.triangulate(bm,faces=list(bm.faces))
        bmesh.ops.subdivide_edges(bm,edges=list(bm.edges),cuts=2,use_grid_fill=True)
        bm.normal_update()
        for v in bm.verts:
            p=v.co.copy()
            f=protection(p)
            if not f:
                continue
            broad=noise.noise_vector(Vector((p.x*.022,p.y*.024,p.z*.006)))
            fine=noise.noise_vector(p*.12)
            shift=Vector((broad.x*2.6+fine.x*.65,broad.y*2.6+fine.y*.65,0))
            if p.z<-22:
                shift.z=8.5*math.sin(p.x*.057+p.y*.041)+3.0*noise.noise(Vector((p.x*.055,p.y*.055,p.z*.011)))
            else:
                shift.z=broad.z*1.4
            v.co+=shift*f+v.normal*f*(noise.noise(p*.17)*.95)
        bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
        bm.to_mesh(ob.data)
        bm.free()
        ob.data.update()
        ob['V08修形']='局部断层错台、竖向不规则起伏；避开承托和种植接触'
        changed.append(ob.name)
    ribs=collection('01E_V08_竖向节理与破碎岩块',rockcol)
    rng=random.Random(8101)
    outline=P['main_outline']
    for i,(x,y) in enumerate(outline):
        if 110<y<250 and x>0 or abs(x)<95 and y<-330:
            continue
        rx,ry=rng.uniform(6,13),rng.uniform(7,17)
        ztop=rng.uniform(-44,-14)
        bottom=rng.uniform(-215,-125)
        vv=[]
        for j,(t,w) in enumerate([(0,.32),(.22,.68),(.57,1),(.81,.82),(1,.35)]):
            for k in range(9):
                a=math.tau*k/9
                factor=rng.uniform(.78,1.22)
                vv.append((x*.955+math.cos(a)*rx*w*factor+math.sin(t*3+i)*4,
                           66+(y-66)*.955+math.sin(a)*ry*w*factor,bottom+(ztop-bottom)*t+rng.uniform(-4,4)))
        ff=[tuple(reversed(range(9))),tuple(range(36,45))]
        for j in range(4):
            for k in range(9):
                a=j*9+k
                b=j*9+(k+1)%9
                ff.extend([(a,b,b+9),(a,b+9,a+9)])
        mesh(f'V08_断续竖向岩脊_{i:02}',vv,ff,ribs,rockmat)
    print('V08_ROCKS_REFINED',len(changed),flush=True)

    # 松树以不等距转折、长短侧枝和空缺冠层组织，根盘沿用原有接触。
    # 针叶以共享立体小簇表现，避免连续圆盘，也避免逐针几何造成过高内存。
    bark=bpy.data.materials['V07_古松树皮_褐灰']
    leafmats=[bpy.data.materials[n] for n in ['V07_针叶簇_深松绿','V07_针叶簇_灰松绿','V07_针叶簇_浅梢']]
    leafdata=[]
    for variation in range(10):
        rng=random.Random(8160+variation)
        vv,ff,mi=[],[],[]
        for j in range(150):
            a=rng.uniform(0,math.tau)
            rad=math.sqrt(rng.random())
            center=Vector((math.cos(a)*rad,math.sin(a)*rad*.8,rng.uniform(-.24,.35)*(1-.45*rad)))
            center.x+=.15*math.sin(center.y*7+variation)
            for k in range(7):
                angle=a+k*2.4+rng.uniform(-.3,.3)
                direction=Vector((math.cos(angle),math.sin(angle),rng.uniform(.15,.9))).normalized()
                length=rng.uniform(.14,.34)
                side=direction.cross(Vector((0,0,1))).normalized()*rng.uniform(.017,.028)
                n=len(vv)
                vv.extend([center,center+direction*length*.48+side,center+direction*length,center+direction*length*.48-side])
                ff.append((n,n+1,n+2,n+3))
                mi.append(2 if j%13==0 else (1 if j%3==0 else 0))
        tmp=mesh(f'V08_针叶簇共享_{variation:02}',vv,ff,pinecol,leafmats[0])
        for mat in leafmats[1:]:
            tmp.data.materials.append(mat)
        for poly,idx in zip(tmp.data.polygons,mi):
            poly.material_index=idx
        leafdata.append(tmp.data)
        bpy.data.objects.remove(tmp,do_unlink=True)
    trees=[]
    for rec in sorted(P['pine_records'],key=lambda p:p['id']!=4):
        col=next(c for c in pinecol.children if c.name.startswith(f"09_{rec['id']:02}_"))
        oldtrunk=next(o for o in col.objects if '盘曲斜干' in o.name)
        root=Vector(oldtrunk['根部落点'])
        for ob in list(col.objects):
            if '抓岩根' not in ob.name:
                bpy.data.objects.remove(ob,do_unlink=True)
        h,w,angle=rec['height'],rec['spread'],rec['angle']
        rng=random.Random(8240+rec['id']*29)
        def point(p):
            return root+Vector((p[0]*math.cos(angle)-p[1]*math.sin(angle),p[0]*math.sin(angle)+p[1]*math.cos(angle),p[2]))
        trunk=[(0,0,-.4),(-.026*h,.016*h,.12*h),(.055*h,-.012*h,.35*h),(.142*h,.026*h,.56*h),
               (.155*h,.055*h,.76*h),(.258*h,.008*h,.93*h),(.27*h,.022*h,h)]
        tr=tube('V08_'+rec['label']+'_苍劲斜干',[point(p) for p in trunk],[h*.047,h*.042,h*.032,h*.025,h*.017,h*.008,.06],col,bark,14,5)
        tr['根部落点']=list(root)
        clusters=0
        specs=[(2,.15,1.0,.53),(2,2.87,.81,.60),(3,-1.52,.69,.78),(3,1.4,.87,.83),(4,-2.77,.67,.92),(5,.27,.48,1.015)]
        for bi,(attach,az,span,level) in enumerate(specs):
            az+=rng.uniform(-.32,.32)+(rec['variant']*.18)
            span*=w*rng.uniform(.85,1.08)
            base=Vector(trunk[attach])
            direction=Vector((math.cos(az),math.sin(az),0))
            side=Vector((-math.sin(az),math.cos(az),0))
            end=base+direction*span+side*rng.uniform(-2.3,2.3)
            end.z=h*level+rng.uniform(-1.2,1.2)
            joint1=base+direction*span*.23+side*rng.uniform(-1.3,1.3)
            joint1.z=base.z+rng.uniform(-1.6,.5)
            joint2=base.lerp(end,.63)+side*rng.uniform(-2.1,1.1)
            joint2.z-=rng.uniform(.4,2.5)
            limb=[base,joint1,joint2,end]
            tube(f"V08_{rec['label']}_主枝_{bi}",[point(p) for p in limb],[h*.022*(1-.08*bi),h*.015,h*.008,.065],col,bark,10,4)
            for fi in range(4 if bi<4 else 3):
                t=.42+fi*.16
                start=joint1.lerp(end,t)
                tip=start+direction*rng.uniform(2.0,4.8)+side*((-1 if fi%2 else 1)*rng.uniform(2.3,5.3))
                tip.z=end.z+rng.uniform(-1.5,1.35)
                tube(f"V08_{rec['label']}_次枝_{bi}_{fi}",[point(start),point(start.lerp(tip,.62)+side*.75),point(tip)],[.25,.13,.035],col,bark,7,3)
                for ci in range(rng.randint(3,5)):
                    theta=rng.uniform(0,math.tau)
                    radial=rng.uniform(.2,2.5)
                    center=tip+Vector((math.cos(theta)*radial,math.sin(theta)*radial,rng.uniform(.12,1.15)))
                    data=leafdata[(bi*3+fi+ci+rec['id'])%10]
                    leaf=bpy.data.objects.new(f"V08_{rec['label']}_疏密针叶_{clusters:03}",data)
                    col.objects.link(leaf)
                    leaf.location=point(center)
                    size=rng.uniform(1.65,2.8)*(w/27)
                    leaf.scale=(size*rng.uniform(.8,1.2),size*rng.uniform(.74,1.05),size*rng.uniform(.88,1.4))
                    leaf.rotation_euler=(rng.uniform(-.25,.25),rng.uniform(-.3,.3),rng.uniform(0,math.tau))
                    clusters+=1
        for di in range(2):
            base=Vector(trunk[2+di])
            tip=base+Vector((-7-di*2,3-di*5,2+di))
            tube(f"V08_{rec['label']}_枯梢_{di}",[point(base),point(base.lerp(tip,.65)),point(tip)],[.38,.18,.014],col,bark,7,3)
        trees.append({'id':rec['id'],'root':list(root),'clusters':clusters})
    print('V08_PINES_REFINED',json.dumps(trees),flush=True)

    # 保留四条水流的出水口、跌水潭和中心落差，只调整横向宽度及水帘边缘。
    # 原来均匀的明脊改成不等长的分流，避免管束或规则窗帘的外观。
    waterstats=[]
    for col in watercol.children:
        body=next((o for o in col.objects if '连续可编辑水体' in o.name),None)
        if body is None:
            continue
        path=json.loads(body['水流中心线'])
        for ob in list(col.objects):
            if '分流明脊' in ob.name:
                bpy.data.objects.remove(ob,do_unlink=True)
        count=len(path)
        for vert in body.data.vertices:
            idx=vert.index%(count*17)
            j,k=divmod(idx,17)
            px,py,pz=path[j]
            blend=min(1,max(0,(path[0][2]-pz)/14))
            widthfactor=1+blend*(.16*math.sin(j*.59)+.095*math.cos(j*1.27)-.07)
            vert.co.x=px+(vert.co.x-px)*widthfactor+blend*.27*math.sin(j*.7+k*.65)
            vert.co.y-=blend*(.15*math.sin(k*1.4+j*.31)+.1*math.cos(j*1.7))
        body['V08水帘']='宽度收放、非周期边缘、保留原出水口和跌水潭'
        waterstats.append(body.name)
    REPORT.update(rock_refined=changed,pines=trees,waterfalls=waterstats)
    S.name='天宫_V08_环境修形检查'
    configure_render(32,100)
    S.frame_set(1)
    S.camera=next(m.camera for m in S.timeline_markers if m.frame==1)
    bpy.ops.wm.save_as_mainfile(filepath=str(QA/'v08_environment.blend'),compress=True)
    clay=simple_material('V08_中性检查_统一灰',(.42,.42,.42),.8)
    S.view_layers[0].material_override=clay
    render(1,QA/'neutral_oblique_preview.png',12,50)
    render(13,QA/'neutral_pine_preview.png',12,50)
    render(15,QA/'neutral_waterfall_preview.png',12,50)
    render(1,OUT/'renders'/'07_neutral_environment.png',32,100)


if STAGE=='environment':
    environment()
    (QA/'environment_build.json').write_text(json.dumps(REPORT,ensure_ascii=False,indent=2),encoding='utf-8')
elif STAGE=='materials':
    exec(compile((ROOT/'scripts'/'lookdev_materials_v08.py').read_text(encoding='utf-8'),str(ROOT/'scripts'/'lookdev_materials_v08.py'),'exec'),globals())
