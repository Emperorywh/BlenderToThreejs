"""
以第八点一版为唯一源文件增量精修白玉、月门、梁架、地面与人物。
样板阶段先渲染一根近景巨柱和门圈局部；推广阶段共用网格并保留主体可编辑。
所有位置及尺寸采用米，不重建建筑布局，不改灯光、四个原机位与云海。
"""
import bpy
import bmesh
import math
import json
import sys
import hashlib
from pathlib import Path
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'v09'
QA = OUT / 'qa'
BASE = ROOT / 'HeavenlyPalace_Lookdev_v08_1.blend'
ARGS = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
SAMPLE = '--sample' in ARGS
SCENE = bpy.context.scene
BASELINE = json.loads((QA / 'baseline_v08_1.json').read_text(encoding='utf-8'))
assert hashlib.sha256(BASE.read_bytes()).hexdigest() == BASELINE['source_sha256']
assert Path(bpy.data.filepath).resolve() == BASE.resolve()
REPORT = {'source_sha256': BASELINE['source_sha256'], 'sample': SAMPLE, 'changed': [], 'added': []}
CACHE = {}


# 新增物体按部位进入独立集合，名称说明真实几何与共享关系。
# 原物体仅在必要部位替换网格或材质；装饰始终独立于建筑主体。
def collection(name):
    col = bpy.data.collections.new(name)
    SCENE.collection.children.link(col)
    return col


COL = {key: collection('19_V09_' + title) for key, title in [('stone','白玉浅浮雕'), ('moon','月门连续纹饰'), ('wood','朱漆梁枋与藻井'), ('roof','屋脊檐口细节'), ('people','长袍人物'), ('control','交付机位与记录')]}
JADE = bpy.data.materials['V08_白玉_柱身栏杆']
GOLD = bpy.data.materials['V08_哑金_脊线与细金饰']
ROOF = bpy.data.materials['V08_青绿琉璃瓦_分行釉面']
RED = bpy.data.materials['V08_朱红木构_顺x轴']


def material(name, color, roughness, metallic=0):
    mat = bpy.data.materials.new('V09_' + name)
    mat.use_nodes = True
    bs = mat.node_tree.nodes.get('Principled BSDF')
    bs.inputs['Base Color'].default_value = (*color,1)
    bs.inputs['Roughness'].default_value = roughness
    bs.inputs['Metallic'].default_value = metallic
    mat.diffuse_color = (*color,1)
    return mat


TEAL = material('藻井黛青底漆', (.012,.055,.047), .38)
ROBE = material('长袍_墨青织物', (.019,.051,.057), .78)
TRIM = material('长袍_灰青领缘', (.09,.145,.14), .66)
SKIN = material('人物_肤色', (.36,.215,.13), .6)
HAIR = material('人物_发髻与鞋', (.012,.009,.007), .63)


def mesh(name, verts, faces, col, mat, smooth=True):
    data = bpy.data.meshes.new(name + '_网格')
    data.from_pydata(verts, [], faces)
    data.update()
    bm = bmesh.new()
    bm.from_mesh(data)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(data)
    bm.free()
    data.materials.append(mat)
    for poly in data.polygons:
        poly.use_smooth = smooth
    ob = bpy.data.objects.new('V09_' + name, data)
    col.objects.link(ob)
    ob['制作说明'] = '第九版真实可编辑几何；全部相机共用可见性'
    REPORT['added'].append(ob.name)
    return ob


def bevel(ob, width=.045, segments=3):
    mod = ob.modifiers.new('V09_柔和实倒角', 'BEVEL')
    mod.width = width
    mod.segments = segments
    return mod


def cube(name, loc, size, col, mat, width=.025):
    key = ('box', tuple(round(v,5) for v in size), mat.name, width)
    if key in CACHE:
        ob = CACHE[key].copy()
        ob.data = CACHE[key].data
        ob.name = 'V09_' + name
        col.objects.link(ob)
        REPORT['added'].append(ob.name)
    else:
        w,d,h = (v/2 for v in size)
        verts = [(-w,-d,-h),(w,-d,-h),(w,d,-h),(-w,d,-h),(-w,-d,h),(w,-d,h),(w,d,h),(-w,d,h)]
        ob = mesh(name, verts, [(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)], col, mat, False)
        if width:
            bevel(ob,width,2)
        CACHE[key] = ob
    ob.location = loc
    return ob


def lathe_data(profile, sides, name):
    verts = [(r*math.cos(i*math.tau/sides),r*math.sin(i*math.tau/sides),z) for z,r in profile for i in range(sides)]
    faces = [(j*sides+i,j*sides+(i+1)%sides,(j+1)*sides+(i+1)%sides,(j+1)*sides+i) for j in range(len(profile)-1) for i in range(sides)]
    faces += [tuple(reversed(range(sides))), tuple((len(profile)-1)*sides+i for i in range(sides))]
    data = bpy.data.meshes.new(name)
    data.from_pydata(verts,[],faces)
    data.update()
    for poly in data.polygons:
        poly.use_smooth = poly.index < len(faces)-2
    return data


# 浮雕以建筑表面参数坐标制作，截面下缘嵌入主体约两厘米。
# 宽缓的凸起负责主要阴影，细纹由原白玉材质负责，避免悬浮线条与高密度细分。
def catmull(points, steps=8):
    pts = [Vector(p) for p in points]
    out = []
    for j in range(len(pts)-1):
        p0,p1,p2,p3 = pts[max(0,j-1)],pts[j],pts[j+1],pts[min(len(pts)-1,j+2)]
        for k in range(steps):
            t = k/steps
            out.append(.5*(2*p1+(-p0+p2)*t+(2*p0-5*p1+4*p2-p3)*t*t+(-p0+3*p1-3*p2+p3)*t*t*t))
    return out + [pts[-1]]


class Relief:
    def __init__(self, mapping):
        self.mapping = mapping
        self.verts, self.faces = [], []

    def ribbon(self, points, width=.18, height=.14, smooth=True, taper=True):
        pts = catmull(points) if smooth else [Vector(p) for p in points]
        offset = len(self.verts)
        cross = 10
        for j,p in enumerate(pts):
            tangent = (pts[min(j+1,len(pts)-1)]-pts[max(0,j-1)]).normalized()
            side = Vector((-tangent.y,tangent.x))
            fac = min(1,.12+j*.21,.12+(len(pts)-1-j)*.21) if taper else 1
            for k in range(cross):
                a = math.tau*k/cross
                q = p + side*width*math.cos(a)*fac
                depth = -.018 + height*(math.sin(a)*.52+.48)*fac
                self.verts.append(self.mapping(q.x,q.y,depth))
        for j in range(len(pts)-1):
            for k in range(cross):
                a,b = offset+j*cross+k,offset+j*cross+(k+1)%cross
                self.faces.append((a,b,b+cross,a+cross))
        self.faces += [tuple(offset+k for k in reversed(range(cross))),tuple(offset+(len(pts)-1)*cross+k for k in range(cross))]

    def petal(self, u,v,w,h,depth=.17,lean=0):
        offset = len(self.verts)
        rows,cols = 18,10
        for j in range(rows+1):
            t=j/rows
            width=max(.004,math.sin(math.pi*t)**.7*w)
            for k in range(cols+1):
                q=-1+2*k/cols
                self.verts.append(self.mapping(u+lean*t+q*width,v+h*t,-.018+depth*math.sin(math.pi*t)**.6*max(0,1-q*q)**.6))
        for j in range(rows):
            for k in range(cols):
                a=offset+j*(cols+1)+k
                self.faces.append((a,a+1,a+cols+2,a+cols+1))

    def finish(self,name,col,mat):
        return mesh(name,self.verts,self.faces,col,mat)


def cloud(rel, u, v, sx=1, sy=1, mirror=1):
    def path(points,width=.19,height=.16):
        rel.ribbon([(u+mirror*x*sx,v+y*sy) for x,y in points], width, height)
    path([(-.85,0),(-1.25,1.15),(-.85,2.35),(.42,3.35),(1.1,4.6),(.76,5.8),(-.28,6.15),(-.95,5.6),(-.76,4.85),(-.15,4.8),(.1,5.2),(-.18,5.48)],.24,.19)
    path([(-.7,2.3),(-1.7,2.4),(-1.95,3.2),(-1.55,3.85),(-.9,3.82),(-.75,3.3),(-1.12,3.15)],.18,.14)
    path([(.4,3.4),(1.48,3.15),(1.98,3.75),(1.65,4.45),(1.03,4.65)],.16,.14)
    path([(-1.25,1.2),(-.25,1.75),(.55,2.3),(.62,2.9)],.15,.115)
    rel.petal(u+mirror*.28*sx,v+1.1*sy,.35*sx,1.8*sy,.17,mirror*.65)
    rel.petal(u-mirror*1.12*sx,v+4.1*sy,.31*sx,1.6*sy,.15,-mirror*.22)


def shaft_mapping(u,v,h):
    radius = 3.6 - .288*v/42.8
    a = math.pi/2 + u/3.5
    return ((radius+h)*math.cos(a),(radius+h)*math.sin(a),37.6+v)


shafts = [ob for ob in SCENE.objects if ob.name.startswith('主殿巨柱') and ob.name.endswith('_柱身')]
targets = [bpy.data.objects['主殿巨柱_列4_进4_柱身']] if SAMPLE else shafts
shaft_data = lathe_data([(-21.4,3.6),(21.4,3.312)],192,'V09_巨柱身_192边共享_原收分')
shaft_data.materials.append(JADE)
orn = Relief(shaft_mapping)
for band in range(3):
    for sector in range(3):
        cloud(orn,sector*math.tau*3.5/3 + (band%2)*.75,3.4+band*12.2, .83,1.38, 1 if (sector+band)%2 else -1)
for i in range(20):
    u=i*math.tau*3.5/20
    orn.petal(u,.25,.43,2.0,.14)
    orn.ribbon([(u,.5),(u,1.45),(u,2.12)],.038,.18)
template = orn.finish('巨柱_卷云与仰莲_共享浅浮雕', COL['stone'], JADE)
for index,shaft in enumerate(targets):
    label = shaft.name.removesuffix('_柱身')
    shaft.data = shaft_data
    REPORT['changed'].append(shaft.name)
    ob = template if index == 0 else bpy.data.objects.new('V09_'+label+'_云纹装饰',template.data)
    if index:
        COL['stone'].objects.link(ob)
        REPORT['added'].append(ob.name)
    ob.location = (shaft.location.x,shaft.location.y,0)
    # 最近一根柱的正面被固定画幅裁去，将整组雕刻绕柱转向可见的西北侧。
    # 此调整是固定物体变换，对外部与细节机位同样生效。
    if shaft.name == '主殿巨柱_列4_进4_柱身':
        ob.rotation_euler.z = .82
    ob['依附主体'] = shaft.name
    ob['最大浮雕高度_米'] = .19
    ob['组织'] = '三组错落卷云，柱脚仰莲；大面积素面留白'
    for suffix in ['_覆盆柱础','_柱脚束口','_承梁柱头']:
        part = bpy.data.objects.get(label+suffix)
        if part:
            key = ('profile',part.data.name)
            if key not in CACHE:
                profile = sorted(set((round(v.co.z,5),round(math.hypot(v.co.x,v.co.y),5)) for v in part.data.vertices))
                data = lathe_data(profile,128,'V09_'+suffix+'_128边共享')
                for mat in part.data.materials:
                    data.materials.append(mat)
                CACHE[key] = data
            part.data = CACHE[key]
            bevel(part,.035,3)
            REPORT['changed'].append(part.name)


# 门圈纹样沿原石圈参数连续铺陈，端点停在地面以上且向圆外退让。
# 石圈原净半径二十二米与原主体网格完全保留；纹饰最低半径大于二十二点九米。
def moon_mapping(u,v,h):
    a=u/23.28
    radius=23.28+v
    return (radius*math.cos(a),245.89+h,56+radius*math.sin(a))


moon = Relief(moon_mapping)
start,end=math.asin(-19.1/23.28),math.pi-math.asin(-19.1/23.28)
angles=[start+(end-start)*i/36 for i in range(37)]
for index,a in enumerate(angles[:-1]):
    if SAMPLE and not 10 <= index <= 16:
        continue
    length=(end-start)*23.28/36
    u=a*23.28
    moon.ribbon([(u,-.16),(u+length*.27,-.10),(u+length*.56,.19),(u+length*.84,.20),(u+length,-.16)],.095,.095,taper=False)
    moon.ribbon([(u+length*.37,-.01),(u+length*.45,-.25),(u+length*.72,-.28),(u+length*.81,-.06),(u+length*.7,.04),(u+length*.59,-.02)],.073,.10)
moon_ob=moon.finish('月门_连续如意卷草_样板' if SAMPLE else '月门_连续如意卷草_全圈',COL['moon'],JADE)
moon_ob['净空保护'] = '全部新增顶点半径大于22米，不越过原月门通行净空'
moon_ob['依附主体'] = 'V05_月门通厚石圈_净径44米'


def add_camera(name,loc,target,lens,frame):
    data=bpy.data.cameras.new(name)
    cam=bpy.data.objects.new(name,data)
    COL['control'].objects.link(cam)
    cam.location=loc
    cam.rotation_euler=(Vector(target)-cam.location).to_track_quat('-Z','Y').to_euler()
    data.lens=lens
    data.clip_end=100000
    SCENE.timeline_markers.new(name,frame=frame).camera=cam
    REPORT['added'].append(cam.name)
    return cam


if not SAMPLE:
    # 月门墙的留白区采用少量对称卷云，避开圆洞和壁柱边界。
    # 宽面浅浮雕衬托窄石圈纹样，两个尺度各自可编辑。
    wallrel=Relief(lambda u,v,h:(u,245.405+h,v))
    for side in (-1,1):
        cloud(wallrel,side*24.75,65.7,.52,1.13,side)
        cloud(wallrel,side*15.3,77.5,.50,.52,-side)
    wallrel.finish('月门墙_两翼疏云浮雕',COL['moon'],JADE)

    # 可见梁枋使用黛青芯板、细金框与少量卷草，边饰贴合实际梁面。
    # 正式机位只见部分天花，藻井按原柱网浅层内收，不改变结构净高。
    for y in (245,278.3333435,311.6666565,345):
        for side in (-1,1):
            face_y=y+side*3.215
            for x,w in [(-75,24),(-45,24),(0,53),(45,24),(75,24)]:
                cube('横梁黛青芯板',(x,face_y,84.4),(w,.075,2.34),COL['wood'],TEAL,.018)
                for z in (83.18,85.62):
                    cube('横梁金线',(x,face_y+side*.049,z),(w+.12,.065,.075),COL['wood'],GOLD,.018)
                rel=Relief(lambda u,v,h,fy=face_y,sgn=side:(u,fy+sgn*(.055+h),v))
                count=max(1,int(w/6))
                for k in range(count):
                    center=x+(k-(count-1)/2)*5.7
                    rel.ribbon([(center-1.7,84.4),(center-.8,84.98),(center+.35,84.86),(center+1.45,84.37),(center+.7,83.88),(center-.1,84.05),(center+.05,84.46),(center+.52,84.5)],.067,.05)
                rel.finish('梁面疏卷草',COL['wood'],GOLD)
    for panel in [o for o in list(SCENE.objects) if o.name.startswith('V05_天花浅凹板_')]:
        x,y,z=panel.location
        if abs(x)>46:
            continue
        w,d=panel.dimensions.x,panel.dimensions.y
        for level,inset in enumerate((1.15,2.35,3.4)):
            zz=86.3+level*.2
            for side in (-1,1):
                cube('藻井内收横框',(x,y+side*(d/2-inset),zz),(w-2*inset,.48,.33),COL['wood'],GOLD if level!=1 else RED,.035)
                cube('藻井内收纵框',(x+side*(w/2-inset),y,zz),(.48,d-2*inset,.33),COL['wood'],GOLD if level!=1 else RED,.035)
        cube('藻井内芯黛青底',(x,y,86.91),(w-7.4,d-7.4,.09),COL['wood'],TEAL,.02)
        rel=Relief(lambda u,v,h,xx=x,yy=y:(xx+u,yy+v,86.86-h))
        for r in (min(d,w)*.23,min(d,w)*.255):
            rel.ribbon([(r*math.cos(i*math.tau/96),r*math.sin(i*math.tau/96)) for i in range(97)],.075,.055,False,False)
        for k in range(8):
            a=k*math.tau/8
            pts=[(r*math.cos(a+off),r*math.sin(a+off)) for r,off in [(1.8,0),(3.4,-.3),(5.3,0),(3.4,.3),(1.8,0)]]
            rel.ribbon(pts,.12,.10)
        rel.finish('藻井团莲金饰',COL['wood'],GOLD)

    # 石板完成面仍严格位于三十六米，接缝和边缘仅使用米制程序凹凸。
    # 四米大板的微弱色差与粗糙度变化控制柔和倒影，不新增覆盖平台的实体。
    floor=bpy.data.materials['V08_白玉_殿内润泽石板'].copy()
    floor.name='V09_白玉地坪_四米大板与柔和反射'
    nodes,links=floor.node_tree.nodes,floor.node_tree.links
    bs=next(n for n in nodes if n.type=='BSDF_PRINCIPLED')
    brick=next(n for n in nodes if n.type=='TEX_BRICK')
    brick.inputs['Brick Width'].default_value=4
    brick.inputs['Row Height'].default_value=4
    brick.inputs['Mortar Size'].default_value=.035
    brick.inputs['Mortar Smooth'].default_value=.022
    brick.inputs['Color1'].default_value=(.69,.73,.71,1)
    brick.inputs['Color2'].default_value=(.79,.79,.73,1)
    brick.inputs['Mortar'].default_value=(.29,.32,.30,1)
    tex=nodes.new('ShaderNodeTexNoise')
    tex.name='石板抛光细微粗糙度变化'
    tex.inputs['Scale'].default_value=.7
    coord=next(n for n in nodes if n.type=='TEX_COORD')
    links.new(coord.outputs['Object'],tex.inputs['Vector'])
    ramp=nodes.new('ShaderNodeMapRange')
    ramp.inputs['To Min'].default_value=.215
    ramp.inputs['To Max'].default_value=.315
    links.new(tex.outputs['Fac'],ramp.inputs['Value'])
    # 缝内表面更粗糙，减少白色镜面高光对接缝的冲淡。
    # 石板主体仍保留原有柔和反射，缝隙仅通过着色和微小凹凸表达。
    joint_rough=nodes.new('ShaderNodeMixRGB')
    joint_rough.name='接缝粗糙度_消退缝内镜面'
    joint_rough.inputs[2].default_value=(.76,.76,.76,1)
    links.new(brick.outputs['Fac'],joint_rough.inputs[0])
    links.new(ramp.outputs['Result'],joint_rough.inputs[1])
    links.new(joint_rough.outputs[0],bs.inputs['Roughness'])
    for node in nodes:
        if node.type=='BUMP' and abs(node.inputs['Distance'].default_value-.014)<.0001:
            node.inputs['Distance'].default_value=.018
            node.inputs['Strength'].default_value=.65
    for ob in SCENE.objects:
        for slot in ob.material_slots:
            if slot.material and slot.material.name=='V08_白玉_殿内润泽石板':
                slot.link='OBJECT'
                slot.material=floor
                REPORT['changed'].append(ob.name)

    # 主要三位人物在原脚底中心与原身高内替换为长袍，衣摆留出双鞋接触。
    # 纵向褶皱直接改变衣袍轮廓，脸部细节按正式成像尺寸保持简洁。
    def ellipsoid(name,loc,scale,mat):
        key=('ellipsoid',tuple(scale),mat.name)
        if key not in CACHE:
            data=lathe_data([(-math.cos(i*math.pi/20),max(.001,math.sin(i*math.pi/20))) for i in range(21)],32,name+'_共享')
            data.materials.append(mat)
            CACHE[key]=data
        ob=bpy.data.objects.new('V09_'+name,CACHE[key])
        COL['people'].objects.link(ob)
        ob.location=loc
        ob.scale=scale
        REPORT['added'].append(ob.name)
        return ob

    for number in ('01','02','03'):
        old=[o for o in list(SCENE.objects) if o.name.startswith('尺度人形_'+number+'_')]
        head=next(o for o in old if o.name.endswith('_头'))
        x,y=head.location.x,head.location.y
        for ob in old:
            REPORT['changed'].append(ob.name)
            bpy.data.objects.remove(ob,do_unlink=True)
        verts,faces=[],[]
        profile=[(.11,.265,.17),(.20,.26,.16),(.42,.23,.145),(.70,.205,.13),(.95,.16,.12),(1.10,.155,.125),(1.28,.21,.135),(1.44,.22,.12),(1.50,.105,.10)]
        for j,(z,rx,ry) in enumerate(profile):
            for k in range(64):
                a=k*math.tau/64
                fold=1+.065*math.cos(a*12+j*.10)+.022*math.sin(a*7)
                verts.append((x+rx*math.cos(a)*fold,y+ry*math.sin(a)*fold,36+z))
        for j in range(len(profile)-1):
            for k in range(64):
                a,b=j*64+k,j*64+(k+1)%64
                faces.append((a,b,b+64,a+64))
        faces.extend([tuple(reversed(range(64))),tuple((len(profile)-1)*64+k for k in range(64))])
        person=mesh('人物'+number+'_垂坠长袍',verts,faces,COL['people'],ROBE)
        person['原站位_米']=[x,y,36]
        person['含发髻身高_米']=1.8
        for side in (-1,1):
            # 衣袖采用向下垂落的多层截面和细纵褶，收掉椭球样板的鼓胀肩部。
            # 袖口靠近原手部，肩线保持窄而自然，适合固定远景中人物的成像尺寸。
            sv,sf=[],[]
            sections=[(1.44,.20,.095,.095),(1.34,.23,.115,.11),(1.16,.27,.125,.105),(.97,.29,.118,.095),(.85,.285,.067,.075)]
            for j,(z,cx,rx,ry) in enumerate(sections):
                for k in range(32):
                    a=k*math.tau/32
                    fold=1+.035*math.cos(a*8+j*.08)
                    sv.append((x+side*cx+rx*math.cos(a)*fold,y+ry*math.sin(a)*fold,36+z))
            for j in range(len(sections)-1):
                for k in range(32):
                    a,b=j*32+k,j*32+(k+1)%32
                    sf.append((a,b,b+32,a+32))
            sf.extend([tuple(reversed(range(32))),tuple((len(sections)-1)*32+k for k in range(32))])
            mesh('人物'+number+'_垂袖',sv,sf,COL['people'],ROBE)
            ellipsoid('人物'+number+'_手',(x+side*.285,y-.018,36.84),(.043,.052,.068),SKIN)
            # 平底鞋建立连续接触面，避免椭球鞋底仅单点触地造成悬浮观感。
            # 鞋底最低面严格落在三十六米完成面，原人物身高与站位不变。
            ellipsoid('人物'+number+'_鞋面',(x+side*.12,y-.047,36.071),(.081,.15,.062),HAIR)
            cube('人物'+number+'_平底鞋底',(x+side*.12,y-.047,36.023),(.148,.272,.046),COL['people'],HAIR,.008)
        ellipsoid('人物'+number+'_颈',(x,y,37.52),(.058,.06,.08),SKIN)
        ellipsoid('人物'+number+'_头',(x,y-.01,37.65),(.102,.102,.125),SKIN)
        ellipsoid('人物'+number+'_后发',(x,y+.028,37.684),(.106,.085,.091),HAIR)
        ellipsoid('人物'+number+'_发髻',(x,y+.036,37.765),(.053,.049,.035),HAIR)
        cube('人物'+number+'_腰封',(x,y+.124,37.06),(.325,.025,.067),COL['people'],TRIM,.008)
        rel=Relief(lambda u,v,h,xx=x,yy=y:(xx+u,yy+.131+h,36+v))
        rel.ribbon([(-.09,1.48),(-.01,1.29),(.13,1.1)],.013,.009)
        rel.finish('人物'+number+'_交领背缘',COL['people'],TRIM)

    # 屋面放样完全读取第五版已验收参数，附加瓦垄贴合原曲面。
    # 主殿屋顶以几何加强可见瓦口与分行，远处仍使用原釉面凹凸。
    P=json.loads((ROOT/'v05'/'design_parameters_v05.json').read_text(encoding='utf-8'))
    def surface(level,side,s,u):
        if level=='lower':
            w=P['lower_inner_width']+(P['lower_width']-P['lower_inner_width'])*u
            d=P['lower_inner_depth']+(P['lower_depth']-P['lower_inner_depth'])*u
            base=P['lower_eave_z']-P['lower_toe_lift']
            z=base+(P['lower_inner_z']-base)*(1-u)**P['lower_curve_power']+P['lower_toe_lift']*u**8
            z+=P['lower_corner_lift']*abs(s)**4*u**2.5
        else:
            w=P['upper_ridge_length']+(P['upper_width']-P['upper_ridge_length'])*u
            d=P['upper_depth']*u
            base=P['upper_eave_z']-P['upper_toe_lift']
            z=base+(P['upper_ridge_z']-base)*(1-u)**P['upper_curve_power']+P['upper_toe_lift']*u**8
            z+=P['upper_corner_lift']*abs(s)**4*u**3
        xy=[(s*w/2,-d/2),(w/2,s*d/2),(-s*w/2,d/2),(-w/2,-s*d/2)][side]
        return Vector((xy[0],295+xy[1],z))

    for level in ('lower','upper'):
        for side in range(4):
            span=P[level+'_width'] if side%2==0 else P[level+'_depth']
            count=round(span/1.24)
            verts,faces=[],[]
            for k in range(1,count):
                s=-1+2*k/count
                offset=len(verts)
                steps=24 if level=='upper' else 14
                for j in range(steps+1):
                    u=(.04 if level=='upper' else 0)+(1-(.04 if level=='upper' else 0))*j/steps
                    p=surface(level,side,s,u)
                    lateral=(surface(level,side,s+.001,u)-surface(level,side,s-.001,u)).normalized()
                    for q in range(7):
                        a=math.pi*q/6
                        verts.append(p+lateral*(math.cos(a)*.20)+Vector((0,0,.025+math.sin(a)*.16)))
                for j in range(steps):
                    for q in range(6):
                        a=offset+j*7+q
                        faces.append((a,a+1,a+8,a+7))
            mesh(level+'_贴面筒瓦垄_'+str(side),verts,faces,COL['roof'],ROOF)
            for k in range(1,count):
                s=-1+2*k/count
                p=surface(level,side,s,1)
                key=('瓦当',)
                if key not in CACHE:
                    data=lathe_data([(-.05,.21),(.04,.235),(.13,.205)],24,'V09_莲心瓦当_共享')
                    data.materials.append(GOLD)
                    CACHE[key]=data
                ob=bpy.data.objects.new('V09_莲心瓦当',CACHE[key])
                COL['roof'].objects.link(ob)
                ob.location=p+Vector((0,0,-.10))
                ob.rotation_euler=Vector([(0,-1,0),(1,0,0),(0,1,0),(-1,0,0)][side]).to_track_quat('Z','Y').to_euler()
                REPORT['added'].append(ob.name)
    for x in range(-60,61,3):
        cube('主脊分节压顶',(x,295,115.55),(2.92,1.22,.31),COL['roof'],GOLD,.065)
    # 将可复用的分节脊饰推广到入口与亭廊正脊，尺寸读取各自原构件。
    # 装饰只占正脊局部，不重算次要屋面，不改变其飞檐曲线。
    for ridge in [o for o in list(SCENE.objects) if o.name.startswith('V06_') and '正脊素收头' in o.name]:
        pts=[ridge.matrix_world@Vector(p) for p in ridge.bound_box]
        lo=[min(p[i] for p in pts) for i in range(3)]
        hi=[max(p[i] for p in pts) for i in range(3)]
        axis=0 if hi[0]-lo[0]>hi[1]-lo[1] else 1
        span=hi[axis]-lo[axis]
        count=max(2,round(span/3.5))
        for k in range(count):
            loc=[(lo[i]+hi[i])/2 for i in range(3)]
            loc[axis]=lo[axis]+(k+.5)*span/count
            loc[2]=hi[2]-.025
            size=[.78,.78,.14]
            size[axis]=.19
            cube('亭廊正脊分节细箍',loc,size,COL['roof'],GOLD,.025)

add_camera('CAM_17_V09_白玉柱雕近景',(20,363,43.8),(28.7,345,42.8),55,17)
add_camera('CAM_18_V09_月门纹饰近景',(1,284,62),(14,245,71),70,18)
SCENE.frame_set(4)
SCENE.camera=bpy.data.objects['CAM_04_殿内望云_v08_1']
SCENE.render.resolution_x,SCENE.render.resolution_y=1800,1350
SCENE.render.resolution_percentage=100
SCENE.cycles.samples=64
SCENE.cycles.adaptive_threshold=.025
SCENE['阶段']='V9 主殿重点区域精修'
SCENE.name='天宫_主殿精修v09'
SCENE['V09说明']='保留V8.1全部灯光云海与四主机位；几何浅浮雕独立可编辑；地坪完成面Z36；人高1.8米'
SCENE.render.filepath=str(OUT/'renders'/'04_interior.png')
for filename in ['build_detail_v09.py','render_detail_v09.py']:
    path=ROOT/'scripts'/filename
    if path.exists():
        text=bpy.data.texts.get('V09_'+filename) or bpy.data.texts.new('V09_'+filename)
        text.clear()
        text.write(path.read_text(encoding='utf-8'))
# 新原型仅作为内嵌参考资源，不进入材质、世界背景或合成器。
# 渲染所需的原资源统一打包，交付工程可独立打开。
reference=Path('C:/Users/12899/Downloads/ChatGPT Image 2026年9月9日 10_58_10.png')
if reference.exists():
    ref=bpy.data.images.load(str(reference),check_existing=True)
    ref.name='V09_本轮原型_仅参考不参与渲染'
    ref.pack()
bpy.ops.file.pack_all()
REPORT['object_count']=len(SCENE.objects)
REPORT['unique_mesh_vertices']=sum(len(m.vertices) for m in bpy.data.meshes if m.users)
(QA/('sample_build.json' if SAMPLE else 'build_report.json')).write_text(json.dumps(REPORT,ensure_ascii=False,indent=2),encoding='utf-8')
bpy.ops.wm.save_as_mainfile(filepath=str(QA/'sample_v09.blend' if SAMPLE else ROOT/'HeavenlyPalace_Detail_v09.blend'),compress=True)
if SAMPLE:
    SCENE.render.resolution_percentage=50
    SCENE.cycles.samples=24
    SCENE.render.filepath=str(QA/'01_sample_interior.png')
    bpy.ops.render.render(write_still=True)
    # 渲染时以时间线绑定选择近景，防止当前第四帧把相机重新切回正式殿内视角。
    # 两张样板图均来自同一个场景，只改变实际相机。
    SCENE.frame_set(17)
    SCENE.camera=bpy.data.objects['CAM_17_V09_白玉柱雕近景']
    SCENE.render.filepath=str(QA/'02_sample_column.png')
    bpy.ops.render.render(write_still=True)
    SCENE.frame_set(18)
    SCENE.camera=bpy.data.objects['CAM_18_V09_月门纹饰近景']
    SCENE.render.filepath=str(QA/'03_sample_moon.png')
    bpy.ops.render.render(write_still=True)
print('V09_DETAIL_BUILD_COMPLETE',flush=True)
if '--crop-check' in ARGS:
    # 以正式分辨率裁出地面和人物的检查区，只缩减渲染范围以控制返修成本。
    # 文件保存发生在此步骤之前，交付工程仍保留完整画幅与统一机位设置。
    SCENE.frame_set(4)
    SCENE.render.resolution_percentage=100
    SCENE.cycles.samples=32
    SCENE.render.use_border=True
    SCENE.render.use_crop_to_border=True
    SCENE.render.border_min_x=.30
    SCENE.render.border_max_x=.79
    SCENE.render.border_min_y=0
    SCENE.render.border_max_y=.33
    SCENE.render.filepath=str(QA/'floor_contact_refinement.png')
    bpy.ops.render.render(write_still=True)
