"""
在 Blender 中从已验收 V6 建立 V7 环境，全部建筑对象直接沿用。
山体以大断崖、倾斜岩层和错落岩台组织；古松与水体均为可编辑网格。
外部脚本和工程内嵌入口使用同一参数与基准摘要，重复执行不会叠加模型。
"""
import bpy
import bmesh
import json
import math
import random
import hashlib
import sys
from pathlib import Path
from mathutils import Vector
from mathutils.bvhtree import BVHTree

# 打开基准前缓存内嵌文本，防止加载文件时丢失用户刚编辑的环境参数。
# 基准只读打开，所有保存目标均限定为 V7 文件，原 V6 永远不被覆盖。
script_path=Path(__file__).resolve() if "__file__" in globals() and Path(__file__).is_file() else None
ROOT=script_path.parents[1] if script_path else Path(bpy.data.filepath).parent
if ROOT.name=="qa":
    ROOT=ROOT.parent.parent
OUT=ROOT/"v07"
for directory in (OUT,OUT/"qa",OUT/"renders"):
    directory.mkdir(parents=True,exist_ok=True)
P=json.loads((OUT/"design_parameters_v07.json").read_text(encoding="utf-8")) if script_path else json.loads(bpy.data.texts["09_v07环境参数.json"].as_string())
script_body=script_path.read_text(encoding="utf-8") if script_path else bpy.data.texts["10_v07环境重建.py"].as_string()
ARGS=sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
baseline=ROOT/P["baseline_file"]
if hashlib.sha256(baseline.read_bytes()).hexdigest()!=P["baseline_sha256"]:
    raise RuntimeError("V6 建筑基准摘要不符，已停止环境重建。")
if (ROOT/P["output_file"]).resolve()==baseline.resolve():
    raise RuntimeError("V7 输出不能指向 V6 基准。")
bpy.ops.wm.open_mainfile(filepath=str(baseline))
SCENE=bpy.context.scene
SCENE.name="天宫_环境v07_山体古松瀑布"
COL={key:next(c for c in SCENE.collection.children if c.name.startswith(prefix)) for key,prefix in
     [("control","00_"),("rock","01_"),("pine","09_"),("water","10_"),("camera","12_"),("cloud","15_")]}
REMOVED=[]
for key in ("rock","pine","water"):
    for ob in list(COL[key].all_objects):
        REMOVED.append(ob.name)
        bpy.data.objects.remove(ob,do_unlink=True)
COL["rock"].name="01_V07_山体断崖与承托"
COL["pine"].name="09_V07_古松主干主枝与针叶簇"
COL["water"].name="10_V07_出水口与连续叠瀑"
COL["cloud"].name="15_V07_远山云海低复杂度占位"
for key,label,parent in [("core","01A_主岛岩层与峡谷","rock"),("ridge","01B_错落岩脊与后山","rock"),
                         ("shelf","01C_崖台与建筑基础过渡","rock"),("joint","01D_中尺度断裂与岩脊","rock"),
                         ("far","15A_低复杂度远山","cloud"),("mist","15B_低位云海布局","cloud")]:
    col=bpy.data.collections.new(label)
    COL[parent].children.link(col)
    COL[key]=col
MAT={}
CACHE={}
ROCKS=[]
PINES=[]
FALLS=[]


# 分色只用于读形，保留 V6 已验收的灯光、建筑材质与色彩管理。
# 岩层色差保持轻微，不使用置换纹理、复杂材质或体积雾掩盖网格形体。
def material(key,label,color,roughness=.88):
    mat=bpy.data.materials.new("V07_"+label)
    mat.diffuse_color=(*color,1)
    mat.use_nodes=True
    node=mat.node_tree.nodes.get("Principled BSDF")
    node.inputs["Base Color"].default_value=(*color,1)
    node.inputs["Roughness"].default_value=roughness
    MAT[key]=mat
    return mat


for key,label,color in [("rock","岩体_灰青",(.30,.345,.35)),("bed","岩层_浅灰青",(.332,.375,.38)),
                        ("cleft","裂隙_深灰",(.235,.275,.28)),("soil","岩台_灰褐",(.34,.34,.29)),
                        ("bark","古松树皮_褐灰",(.23,.185,.145)),("bark_light","古松主脊_浅褐",(.305,.255,.19)),
                        ("leaf","针叶簇_深松绿",(.075,.155,.118)),("leaf_light","针叶簇_灰松绿",(.115,.205,.154)),
                        ("leaf_tip","针叶簇_浅梢",(.175,.265,.185)),("water","落水_浅青白",(.53,.735,.77)),
                        ("water_light","水脊_灰白",(.79,.865,.86)),("pool","水潭_青灰",(.24,.49,.52)),
                        ("far1","中远山_灰青",(.60,.68,.70)),("far2","远山_浅灰青",(.68,.74,.76)),
                        ("cloud","云海占位_雾白",(.73,.785,.80))]:
    material(key,label,color,.42 if key in ("water","pool") else .9)


# 网格按地质体、单株树和单条瀑布分组，同类针叶簇共享数据块。
# 法线在创建时统一，避免渲染中出现倒面或靠双面材质掩盖拓扑错误。
def mesh(name,verts,faces,group,mat="rock",smooth=False,key=None):
    if key is not None and key in CACHE:
        data=CACHE[key]
    else:
        data=bpy.data.meshes.new("V07_"+name+"_网格")
        data.from_pydata(verts,[],faces)
        data.update()
        bm=bmesh.new()
        bm.from_mesh(data)
        bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
        bm.to_mesh(data)
        bm.free()
        data.materials.append(MAT[mat])
        for poly in data.polygons:
            poly.use_smooth=smooth
        if key is not None:
            CACHE[key]=data
    ob=bpy.data.objects.new("V07_"+name,data)
    COL[group].objects.link(ob)
    ob["阶段"]="V07 环境建模"
    if key is not None:
        ob["共享网格模块"]=str(key)
    if group in ("core","ridge","shelf","joint"):
        ROCKS.append(ob)
    return ob


def cube(name,lo,hi,group="shelf",mat="rock"):
    x,y,z=lo
    X,Y,Z=hi
    return mesh(name,[(x,y,z),(X,y,z),(X,Y,z),(x,Y,z),(x,y,Z),(X,y,Z),(X,Y,Z),(x,Y,Z)],
                [(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)],group,mat)


def difference(target,cutter):
    bpy.context.view_layer.objects.active=target
    mod=target.modifiers.new("环境避让保护体","BOOLEAN")
    mod.operation="DIFFERENCE"
    mod.solver="EXACT"
    mod.object=cutter
    bpy.ops.object.modifier_apply(modifier=mod.name)


def cross(a,b):
    return a.x*b.y-a.y*b.x


def radial_hit(theta,polygon,center=(0,66)):
    origin=Vector(center)
    direction=Vector((math.cos(theta),math.sin(theta)))
    hits=[]
    for a,b in zip(polygon,polygon[1:]+polygon[:1]):
        a,b=Vector(a),Vector(b)
        edge=b-a
        denominator=cross(direction,edge)
        if abs(denominator)<1e-8:
            continue
        t=cross(a-origin,edge)/denominator
        u=cross(a-origin,direction)/denominator
        if t>0 and -.00001<=u<=1.00001:
            hits.append(t)
    return origin+direction*min(hits)


# 主岛外边界继承七百米级尺度，桥下在各个标高都维持明确峡谷。
# 纵剖面按收分、断崖、退台交替设计；小幅变化只打破直线，不控制整体轮廓。
angles=sorted(set([round(math.tau*i/116,7) for i in range(116)]+[
    round(math.atan2(y-66,x)%math.tau,7) for x,y in P["main_outline"]]+[
    round(math.atan2(y-66,x)%math.tau,7) for x,y in [(-156,-234),(156,-234),(156,380),(-156,380)]]))
N=len(angles)
profile=[(-250,.43),(-238,.57),(-215,.72),(-181,.91),(-174,.855),(-146,.99),(-139,.93),(-101,1.0),(-94,.945),(-51,.98),(-44,.927),(None,.90)]
verts=[]
for j,(z,scale) in enumerate(profile):
    for i,a in enumerate(angles):
        outline=radial_hit(a,P["main_outline"])
        joint=.022*math.sin(9*a+.35)+.014*math.sin(17*a+.8)
        folded=.018*math.sin(3*a+j*.32)
        factor=scale+joint+folded
        x,y=outline.x*factor,66+(outline.y-66)*factor
        x+=3.4*math.sin(a*3+j*.4)
        zz=z if z is not None else -14-22*max(0,-math.sin(a))**2-9*math.sin(a*4+.6)**2
        if j not in (0,len(profile)-1):
            zz+=8*math.sin(3*a+.24*j)+4*math.cos(7*a)+.016*x
        if 122<y<240 and x>0:
            limit=158+max(0,abs(y-178)-27)*.36
            x=min(x,limit)
        verts.append((x,y,zz))
faces=[tuple(reversed(range(N)))]
for j in range(len(profile)-1):
    for i in range(N):
        a,b=j*N+i,j*N+(i+1)%N
        faces.extend([(a,b,b+N),(a,b+N,a+N)])
outer_start=(len(profile)-1)*N
rectangle=[[-156,-234],[156,-234],[156,380],[-156,380]]
for ring,t in enumerate((.5,1.0)):
    for i,a in enumerate(angles):
        inner=radial_hit(a,rectangle)
        outer=Vector(verts[outer_start+i])
        x,y=outer.x*(1-t)+inner.x*t,outer.y*(1-t)+inner.y*t
        zz=outer.z*(1-t)+(-5.8)*t
        if t<1:
            zz-=3*math.sin(5*a)**2
        verts.append((x,y,zz))
    start=outer_start+ring*N
    for i in range(N):
        a,b=start+i,start+(i+1)%N
        faces.extend([(a,b,b+N),(a,b+N,a+N)])
faces.append(tuple(range(len(verts)-N,len(verts))))
main=mesh("主岛_分层断崖连续岩芯",verts,faces,"core")
main.data.materials.append(MAT["bed"])
for poly in main.data.polygons:
    if poly.normal.z>.55:
        poly.material_index=1
main["造型层级"]="主轮廓收分、十二层断崖退台、中尺度裂隙；上层完整托住 V6 建筑"


# 次级山脊使用不对称刃状截面和破损脊顶，避免规则锥体与同尺寸碎石堆。
# 每条山脊的收分、倾向和顶部高差可由参数独立编辑。
def crag(name,center,radii,bottom,top,lean,seed,group="ridge",flat=False,mat="rock"):
    rng=random.Random(seed)
    outline=[(1,.10),(.77,.65),(.22,.92),(-.28,.73),(-.48,1),(-.94,.45),
             (-.76,.04),(-1,-.35),(-.42,-.88),(.1,-.61),(.34,-1),(.83,-.54)]
    count=len(outline)
    shape=[1+.07*math.sin(i*1.71+seed) for i in range(count)]
    h=top-bottom
    levels=[(0,.48),(.13,.72),(.36,.94),(.40,.84),(.68,1.0),(.73,.79),(.91,.64),(1,.86 if flat else .37)]
    vv=[]
    for j,(t,scale) in enumerate(levels):
        for i in range(count):
            a=math.tau*i/count
            px,py=outline[(i+seed%3)%count]
            sx=radii[0]*px*shape[i]*scale
            sy=radii[1]*py*shape[i]*scale
            x=center[0]+sx+lean[0]*t*t
            y=center[1]+sy+lean[1]*t*t
            z=bottom+h*t
            if 0<j<len(levels)-1:
                z+=h*(.037*math.sin(2*a+seed)+.014*math.cos(5*a+j*.4))
            if j==len(levels)-1 and not flat:
                z-=h*(.01+.09*(.5+.5*math.sin(a+.6))+.04*abs(math.cos(a*2)))
                if i in (2,3):
                    z=top-(i-2)*2
            vv.append((x,y,z))
    ff=[tuple(reversed(range(count)))]
    for j in range(len(levels)-1):
        for i in range(count):
            a,b=j*count+i,j*count+(i+1)%count
            ff.extend([(a,b,b+count),(a,b+count,a+count)])
    if flat:
        ff.append(tuple(range(len(vv)-count,len(vv))))
    else:
        vv.append((center[0]+lean[0]-radii[0]*.07,center[1]+lean[1],top-h*.032))
        for i in range(count):
            ff.append((len(vv)-1,(len(levels)-1)*count+i,(len(levels)-1)*count+(i+1)%count))
    ob=mesh(name,vv,ff,group,mat)
    if mat=="rock":
        ob.data.materials.append(MAT["bed"])
        for poly in ob.data.polygons:
            if poly.normal.z>.60:
                poly.material_index=1
    return ob


for r in P["ridge_records"]:
    crag(r["name"],r["center"],r["radius"],-216,r["top"],r["lean"],r["seed"])
island=crag("东侧独立山台_偏心收分与桥台承托",(303,180),(64,79),-230,9,(0,0),719,"core",True)
crag("西侧松台_横向岩肩",(-292,125),(57,76),-216,3,(-5,0),720,"core",True)

# 岛顶增设与岩芯相接的自然岩台，完整覆盖观景平台投影。
# 原桥台中心 X150、X264 及全部平台尺寸保持不变。
top_outline=[(259,138),(286,130),(318,133),(348,145),(356,166),(347,203),(333,223),(299,226),(263,215),(255,190),(256,159)]
vv=[(x,y,9) for x,y in top_outline]+[(303+(x-303)*.90,180+(y-180)*.92,-54) for x,y in top_outline]
nn=len(top_outline)
ff=[tuple(range(nn)),tuple(reversed(range(nn,nn*2)))]+[(i,(i+1)%nn,(i+1)%nn+nn,i+nn) for i in range(nn)]
mesh("观景台下_连续原岩承托",vv,ff,"shelf")
crag("观景亭古松_外侧种植岩肩",(342,155),(26,30),-57,13,(0,0),721,"shelf",True)

# 前方两道台阶的岩肩按原踏步标高衔接，中心保留六十米施工净槽。
# 这些是长短不同的整体岩脊，数量受控，避免用密集小石块模拟大山。
for side in (-1,1):
    for k,(x,y,rx,ry,z) in enumerate([(62,-342,32,44,-26),(102,-291,46,60,-8),(167,-241,36,45,-6)]):
        crag(f"登山阶侧岩肩_{side}_{k}",(side*x,y),(rx,ry),-224+k*16,z,(side*(7+k*2),5),740+k+int(side>0)*8,"joint")
for k,(x,y,rx,ry,z,lx,ly) in enumerate([(184,-265,21,32,-32,10,-9),(259,-113,17,29,-30,13,2),
    (245,-34,24,37,-45,15,0),(-267,-137,19,34,-30,-11,-1),(-291,15,18,38,-30,-9,1),
    (163,153,13,15,-38,-8,0),(164,204,12,17,-28,-8,2),(266,167,16,21,-33,3,0),
    (345,182,19,28,-26,8,3),(319,220,21,25,-40,4,6)]):
    crag(f"长断裂侧翼_{k:02}",(x,y),(rx,ry),-215,z,(lx,ly),770+k,"joint")


# 峡谷收窄岩芯后，单独补足两端桥台脚下的完整原岩承托。
# 承托岩肩向主岛和侧岛内部搭接，中段仍保持八十五米岩体净距。
def abutment_rock(name,outline,top,center):
    vv=[]
    nn=len(outline)
    for dz,scale in [(0,1),(-62,1.02),(-145,.87),(-214,.57)]:
        vv.extend((center[0]+(x-center[0])*scale,center[1]+(y-center[1])*scale,top+dz) for x,y in outline)
    ff=[tuple(range(nn)),tuple(reversed(range(3*nn,4*nn)))]
    for layer in range(3):
        for i in range(nn):
            a,b=layer*nn+i,layer*nn+(i+1)%nn
            ff.extend([(a,b,b+nn),(a,b+nn,a+nn)])
    return mesh(name,vv,ff,"shelf")


abutment_rock("桥西岩肩_脚下连续承托",[(121,119),(157,122),(164,142),(164,202),(158,230),(127,226),(111,202),(113,147)],-6,(135,178))
abutment_rock("桥东岩肩_脚下连续承托",[(255,151),(279,145),(291,165),(291,194),(277,211),(256,204),(254,181)],9,(273,178))

# 原台阶是保留的独立踏步实体，下方岩床直接承接其最低底面。
# 补齐下段首级与中间休息平台的接触，避免只检查踏面通行却漏掉底部悬空。
abutment_rock("登山下段_完整原岩阶床",[(-27,-359),(27,-359),(31,-330),(28,-302),(-28,-302),(-32,-329)],-48.68,(0,-330))
abutment_rock("登山休息平台_原岩阶床",[(-29,-304),(29,-304),(31,-284),(-30,-284)],-27.98,(0,-294))
abutment_rock("登山上段_完整原岩阶床",[(-27,-286),(27,-286),(29,-231),(-30,-231)],-24.68,(0,-256))

# 用保护体一次性裁出建筑净空与桥下峡谷，裁切只作用于本轮岩体。
# 建筑原网格、材质、变换、桥拱和所有台阶不参与任何布尔操作。
cutters=[cube("临时_建筑保护",(-159,-235,-6),(159,380,400)),
         cube("临时_观景平台保护",(263,140,9),(337,216,200)),
         cube("临时_桥下贯通峡谷",(P["bridge_clear_x"][0],P["bridge_clear_y"][0],-270),(P["bridge_clear_x"][1],P["bridge_clear_y"][1],10))]
for y0,y1,z0,z1 in [(-361,-303,-50,-25),(-303,-285,-28,-28),(-285,-232,-24.65,-.5)]:
    vv=[(-30,y0,z0),(30,y0,z0),(30,y1,z1),(-30,y1,z1),(-30,y0,300),(30,y0,300),(30,y1,300),(-30,y1,300)]
    cutters.append(mesh("临时_登山阶净槽",vv,[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)],"shelf"))
bpy.context.view_layer.update()
for ob in [o for o in ROCKS if o not in cutters]:
    omin=[min(v.co[i] for v in ob.data.vertices) for i in range(3)]
    omax=[max(v.co[i] for v in ob.data.vertices) for i in range(3)]
    for cutter in cutters:
        cmin=[min(v.co[i] for v in cutter.data.vertices) for i in range(3)]
        cmax=[max(v.co[i] for v in cutter.data.vertices) for i in range(3)]
        if all(omin[i]<cmax[i] and omax[i]>cmin[i] for i in range(3)):
            difference(ob,cutter)
for cutter in cutters:
    ROCKS.remove(cutter)
    bpy.data.objects.remove(cutter,do_unlink=True)

# 侧岛承托岩面相接处做真实并集，消除同一标高的重叠面产生的黑缝。
# 只合并四块相连原岩，保留桥台、观景平台和亭的所有 V6 网格不变。
island_parts=[o for o in ROCKS if o!=island and any(label in o.name for label in ("观景台下_连续原岩承托","观景亭古松_外侧种植岩肩","桥东岩肩_脚下连续承托"))]
for part in island_parts:
    bpy.context.view_layer.objects.active=island
    mod=island.modifiers.new("连续原岩并集消除共面黑缝","BOOLEAN")
    mod.operation="UNION"
    mod.solver="EXACT"
    mod.object=part
    bpy.ops.object.modifier_apply(modifier=mod.name)
    ROCKS.remove(part)
    bpy.data.objects.remove(part,do_unlink=True)


# 支撑射线始终查询真实岩体，不把树叶、水面或建筑屋顶误当作种植面。
# 水流出水口也用同一岩面数据定位，随后再增加与宿主相接的岩唇。
def rock_tree():
    vv,ff=[],[]
    for ob in ROCKS:
        offset=len(vv)
        vv.extend(ob.matrix_world@v.co for v in ob.data.vertices)
        ff.extend(tuple(offset+i for i in p.vertices) for p in ob.data.polygons)
    return BVHTree.FromPolygons(vv,ff)


TREE=rock_tree()
def ground(x,y):
    hit,n,i,d=TREE.ray_cast(Vector((x,y,600)),Vector((0,0,-1)),1000)
    if hit is None:
        raise RuntimeError(f"种植落点缺少岩面支撑：{x},{y}")
    return hit.z


print("V07_ROCKS_READY",len(ROCKS),flush=True)


# 管状网格沿自然转折的中心线连续放样，半径逐段收细。
# 主干与主枝保留少量纵向树皮棱线，避免用直圆柱拼成折线树。
def tube(name,points,radii,group,mat="bark",sides=10,steps=4,texture=False):
    points=[Vector(p) for p in points]
    centers=[]
    sizes=[]
    for j in range(len(points)-1):
        p0=points[max(0,j-1)]
        p1,p2=points[j],points[j+1]
        p3=points[min(len(points)-1,j+2)]
        for k in range(steps):
            t=k/steps
            c=.5*((2*p1)+(-p0+p2)*t+(2*p0-5*p1+4*p2-p3)*t*t+(-p0+3*p1-3*p2+p3)*t*t*t)
            centers.append(c)
            sizes.append(radii[j]*(1-t)+radii[j+1]*t)
    centers.append(points[-1])
    sizes.append(radii[-1])
    vv=[]
    for i,(point,radius) in enumerate(zip(centers,sizes)):
        tangent=centers[min(i+1,len(centers)-1)]-centers[max(0,i-1)]
        tangent.normalize()
        ref=Vector((0,1,0)) if abs(tangent.y)<.95 else Vector((1,0,0))
        u=tangent.cross(ref).normalized()
        v=tangent.cross(u).normalized()
        for k in range(sides):
            a=math.tau*k/sides
            f=1+.095*math.sin(5*a+i*.09) if texture else 1
            vv.append(point+radius*f*(math.cos(a)*u+math.sin(a)*v))
    ff=[tuple(reversed(range(sides)))]
    for i in range(len(centers)-1):
        for k in range(sides):
            a,b=i*sides+k,i*sides+(k+1)%sides
            ff.append((a,b,b+sides,a+sides))
    ff.append(tuple(range(len(vv)-sides,len(vv))))
    return mesh(name,vv,ff,group,mat,True)


def foliage_data(variant):
    key=("针叶簇",variant)
    if key in CACHE:
        return CACHE[key]
    count=18
    vv=[]
    for j,(z,r) in enumerate([(-.58,.24),(-.37,.74),(-.04,1),(.23,.91),(.51,.58),(.64,.18)]):
        for i in range(count):
            a=math.tau*i/count
            lobe=1+.16*math.sin(5*a+variant)+.095*math.sin(9*a+.7*variant)
            vv.append((r*math.cos(a)*lobe,r*math.sin(a)*lobe*(.85+.05*math.sin(a)),z+.055*math.sin(3*a+variant)*r))
    ff=[tuple(reversed(range(count)))]
    for j in range(5):
        for i in range(count):
            a,b=j*count+i,j*count+(i+1)%count
            ff.extend([(a,b,b+count),(a,b+count,a+count)])
    ff.append(tuple(range(5*count,6*count)))
    temp=mesh("针叶簇模块",vv,ff,"pine","leaf",False,key)
    data=temp.data
    data.materials.append(MAT["leaf_light"])
    data.materials.append(MAT["leaf_tip"])
    for poly in data.polygons:
        poly.material_index=1 if poly.normal.z>.40 else 0
        if poly.normal.z>.6 and poly.index%11==variant%11:
            poly.material_index=2
    bpy.data.objects.remove(temp,do_unlink=True)
    return data


# 每株树保留七组有主次的枝冠，针叶只做到成簇层次。
# 通过斜干方向、主枝长度与空缺冠层形成变体，所有叶簇复用七种基础网格。
for record in sorted(P["pine_records"],key=lambda p:p["id"]!=4):
    tid=record["id"]
    col=bpy.data.collections.new(f"09_{tid:02}_"+record["label"])
    COL["pine"].children.link(col)
    key=f"tree{tid}"
    COL[key]=col
    x,y=record["xy"]
    z=ground(x,y)
    h,w=record["height"],record["spread"]
    angle=record["angle"]
    variant=record["variant"]
    rng=random.Random(P["random_seed"]+tid*37)
    def point(v):
        xx,yy,zz=v
        return Vector((x+xx*math.cos(angle)-yy*math.sin(angle),y+xx*math.sin(angle)+yy*math.cos(angle),z+zz))
    trunk=[(0,0,-.55),(-.075*h,.015*h,.22*h),(.025*h,-.025*h,.43*h),(.155*h,.005*h,.62*h),
           (.09*h,.035*h,.80*h),(.205*h,.02*h,h)]
    if variant==1:
        trunk[2]=(-.055*h,.025*h,.43*h)
        trunk[4]=(.19*h,-.02*h,.81*h)
    elif variant==2:
        trunk[1]=(.045*h,-.025*h,.21*h)
        trunk[3]=(.215*h,.025*h,.62*h)
    trunk_ob=tube(record["label"]+"_盘曲斜干",[point(v) for v in trunk],[h*.047,h*.039,h*.031,h*.023,h*.015,h*.0028],key,sides=14,steps=5,texture=True)
    trunk_ob["根部落点"]= [x,y,z]
    trunk_ob["原占位位置"]= [299,162] if tid==4 else record["xy"]
    trunk_ob["样板说明"]="可复用斜干、七组主枝、疏密枝冠及七种共享针叶簇"
    root_records=[]
    for ri in range(7):
        a=angle+ri*2.399+.19*math.sin(ri*3+tid)
        length=h*(.115+.06*rng.random())
        pts=[]
        for k in range(6):
            t=k/5
            curve=math.sin(t*math.pi)*length*.15*math.sin(ri+tid)
            rx=x+math.cos(a)*length*t-math.sin(a)*curve
            ry=y+math.sin(a)*length*t+math.cos(a)*curve
            gz=ground(rx,ry)
            pts.append((rx,ry,gz+(.48-.52*t)))
        tube(record["label"]+f"_抓岩根_{ri}",pts,[h*.026,h*.023,h*.017,h*.011,h*.006,.055],key,sides=9,steps=2,texture=True)
        root_records.append({"tip":list(pts[-1]),"ground_z":ground(pts[-1][0],pts[-1][1])})
    limb_specs=[(1,.25,1.04,.55),(2,2.92,.88,.67),(2,-1.35,.79,.77),(3,1.26,.72,.86),
                (3,-2.65,.84,.87),(4,.20,.69,.99),(4,2.43,.56,1.06)]
    clusters=0
    for bi,(attach,azimuth,lengthfactor,heightfactor) in enumerate(limb_specs):
        azimuth+=variant*.29+.10*math.sin(tid+bi)
        length=w*lengthfactor*(.80+rng.random()*.20+.09*math.sin(tid*.7+bi*1.13))
        base=Vector(trunk[attach])
        direction=Vector((math.cos(azimuth),math.sin(azimuth),0))
        end=base+direction*length
        end.z=h*heightfactor
        bend1=base+direction*length*.25+Vector((0,0,-h*.035))
        bend2=base+direction*length*.61+Vector((0,0,(end.z-base.z)*.38))
        bend3=base+direction*length*.86+Vector((0,0,(end.z-base.z)*.90))
        limb=[base,bend1,bend2,bend3,end]
        tube(record["label"]+f"_主枝_{bi:02}",[point(v) for v in limb],[h*.023*(1-bi*.075),h*.018,h*.013,.23,.085],key,steps=4,texture=True)
        for fork in range(3):
            start=bend2.lerp(end,.22+fork*.27)
            side=Vector((-math.sin(azimuth),math.cos(azimuth),0))
            tip=start+direction*w*(.17+.035*fork)+side*w*((fork-1)*.19)
            tip.z=end.z+(fork-1)*h*.035
            tube(record["label"]+f"_冠层分枝_{bi}_{fork}",[point(start),point(start.lerp(tip,.45)+Vector((0,0,-.45))),point(tip)],
                 [.26,.16,.04],key,sides=7,steps=3)
            for ci in range(5 if not (bi==2 and variant==1) else 3):
                a=ci*2.399+bi*.53
                radial=0 if ci==0 else (1.5+ci*.51)
                local=tip+Vector((math.cos(a)*radial,math.sin(a)*radial*.73,.40+ci*.19))
                data=foliage_data((bi+ci+variant)%7)
                ob=bpy.data.objects.new(f"V07_{record['label']}_针叶簇_{clusters:03}",data)
                col.objects.link(ob)
                ob.location=point(local)
                sz=w*(.102+.028*rng.random())*(1 if bi<5 else .86)
                ob.scale=(sz*(1.07+rng.random()*.3),sz*(.72+rng.random()*.25),sz*(.44+rng.random()*.12))
                ob.rotation_euler=(rng.uniform(-.11,.11),rng.uniform(-.12,.12),angle+azimuth+ci*.4)
                ob["阶段"]="V07 环境建模"
                ob["共享网格模块"]="针叶簇七种模块"
                clusters+=1
    PINES.append({"id":tid,"label":record["label"],"root":[x,y,z],"height":h,"clusters":clusters,"root_tips":root_records,"collection":col.name})
print("V07_PINES_READY",len(PINES),flush=True)


# 瀑布按出水潭、岩唇、自由落水、跌水潭和次级垂落连续建模。
# 落水中心线由少量物理段落控制，不逐层贴合凹凸岩面，也不制作流体模拟。
def front_at(x,z,selected):
    hits=[]
    for ob in selected:
        hit,loc,n,i=ob.ray_cast(Vector((x,-1000,z)),Vector((0,1,0)))
        if hit:
            hits.append(loc.y)
    return min(hits) if hits else None


def lip_ledge(label,x,lip,back,z,width):
    back=max(lip+14,back)
    hw=width*.94
    poly=[(x-hw*.77,lip-.4),(x+hw*.62,lip-.7),(x+hw,lip+3),(x+hw*.9,back-3),
          (x+hw*.51,back+2),(x-hw*.86,back),(x-hw*1.12,lip+7)]
    nn=len(poly)
    vv=[(px,py,z-.38) for px,py in poly]
    vv.extend((x+(px-x)*(1.16+.1*math.sin(i)),py+2,z-7-3*math.sin(i+.7)) for i,(px,py) in enumerate(poly))
    vv.extend((x+(px-x)*.74,py+12,z-29-7*math.sin(i+.2)) for i,(px,py) in enumerate(poly))
    ff=[tuple(range(nn)),tuple(reversed(range(nn*2,nn*3)))]
    for layer in range(2):
        ff.extend((layer*nn+i,layer*nn+(i+1)%nn,(layer+1)*nn+(i+1)%nn,(layer+1)*nn+i) for i in range(nn))
    ob=mesh(label+"_与宿主相接岩唇",vv,ff,"shelf","bed")
    for side in (-1,1):
        crag(label+f"_出水口岸岩_{side}",(x+side*width*.74,lip+7),(width*.20,6.3),z-7,z+1.8,(side*.7,0),812+side,"shelf",False,"bed")
    return ob


def sheet(name,path,widths,group,mat="water"):
    vv=[]
    across=16
    for layer in (0,1):
        for j,p in enumerate(path):
            p=Vector(p)
            direction=Vector(path[min(j+1,len(path)-1)])-Vector(path[max(0,j-1)])
            normal=Vector((0,direction.z,-direction.y)).normalized()
            for k in range(across+1):
                u=k/across
                ripple=.13*math.sin(u*math.tau*5+j*.16)+.065*math.sin(u*math.tau*11-j*.26)
                width=widths[j]*(1+.02*math.sin(j*.53))
                vv.append(p+Vector(((u-.5)*width,0,0))+normal*(ripple-layer*.24))
    layer_count=len(path)*(across+1)
    ff=[]
    for j in range(len(path)-1):
        for k in range(across):
            a=j*(across+1)+k
            b=a+1
            ff.extend([(a,b,b+across+1,a+across+1),(a+layer_count+across+1,b+layer_count+across+1,b+layer_count,a+layer_count)])
    for j in range(len(path)-1):
        for k in (0,across):
            a=j*(across+1)+k
            b=a+across+1
            ff.append((a,b,b+layer_count,a+layer_count))
    for j in (0,len(path)-1):
        for k in range(across):
            a=j*(across+1)+k
            ff.append((a,a+1,a+1+layer_count,a+layer_count))
    ob=mesh(name,vv,ff,group,mat,True)
    ob["水流中心线"]=json.dumps(path)
    return ob


for record in P["waterfalls"]:
    wid=record["id"]
    col=bpy.data.collections.new(f"10_{wid:02}_"+record["label"])
    COL["water"].children.link(col)
    group=f"fall{wid}"
    COL[group]=col
    x,top,bottom,width=record["x"],record["source_z"],record["bottom_z"],record["width"]
    selected=[ob for ob in ROCKS if ("西侧远肩" in ob.name or "西后山主脊" in ob.name)] if wid==4 else list(ROCKS)
    breakz=record["break_z"]
    end1=breakz if breakz is not None else bottom
    sample_end=max(end1,-270.0)
    sample_count=max(25,int((top-sample_end)/4)+1)
    raw=[front_at(x+dx,top+(sample_end-top)*j/sample_count,selected) for dx in (-width*.56,0,width*.56) for j in range(sample_count+1)]
    surfaces=[v for v in raw if v is not None]
    if not surfaces:
        raise RuntimeError("瀑布宿主缺失："+record["label"])
    lip1=min(surfaces)-3.0
    host=front_at(x,top-4,selected)
    if host is None:
        host=max(surfaces)
    lip_ledge(record["label"]+"_上段",x,lip1,host+10,top,width)
    path=[(x,host+7,top),(x,lip1+9,top-.04),(x,lip1+2,top-.16),(x,lip1-.25,top-.8),(x,lip1-1.1,top-3.2)]
    widths=[width*1.15,width*1.18,width*1.10,width,width*.95]
    n=max(8,int((top-end1)/8))
    first_start=len(path)
    for j in range(1,n+1):
        t=j/n
        zz=top-3.2+(end1+.55-(top-3.2))*t
        path.append((x+.35*math.sin(t*2.8),lip1-1.1-1.3*t,zz))
        widths.append(width*(.95+.14*t))
    sections=[{"start":first_start,"end":len(path)-1,"lip":lip1}]
    if breakz is not None:
        sample_end=max(bottom,-270.0)
        sample_count=max(25,int((breakz-sample_end)/4)+1)
        raw=[front_at(x+dx,breakz+(sample_end-breakz)*j/sample_count,list(ROCKS)) for dx in (-width*.7,0,width*.7) for j in range(sample_count+1)]
        low=[v for v in raw if v is not None]
        lip2=min(lip1-10,min(low)-4 if low else lip1-10)
        host2=front_at(x,breakz-4,selected)
        lip_ledge(record["label"]+"_跌水潭",x,lip2,(host2 if host2 is not None else lip1+6)+7,breakz,width*1.2)
        path.extend([(x,lip1-3.8,breakz+.23),(x,lip2+5,breakz+.17),(x,lip2+.6,breakz+.03),
                     (x,lip2-1,breakz-1.8),(x,lip2-1.7,breakz-5)])
        widths.extend([width*1.28,width*1.45,width*1.18,width*1.09,width])
        start=len(path)
        n=max(9,int((breakz-bottom)/8))
        for j in range(1,n+1):
            t=j/n
            path.append((x+.52*math.sin(t*2.5),lip2-1.7-1.8*t,breakz-5+(bottom-breakz+5)*t))
            widths.append(width*(1+.18*t))
        sections.append({"start":start,"end":len(path)-1,"lip":lip2})
    water=sheet(record["label"]+"_连续可编辑水体",path,widths,group)
    water["造型说明"]="水潭连岩唇，自由垂落为主；中段只在跌水潭改变水平位置"
    for sec_index,section in enumerate(sections):
        segment=path[section["start"]-1:section["end"]+1]
        for stripe,fraction in enumerate((-.39,-.24,-.065,.17,.35)):
            pts=[(px+width*fraction+.12*math.sin(j*.4+stripe),py-.21,pz) for j,(px,py,pz) in enumerate(segment)]
            tube(record["label"]+f"_分流明脊_{sec_index}_{stripe}",pts,[width*(.010+.003*math.sin(j*.3+stripe)) for j in range(len(pts))],
                 group,"water_light",sides=6,steps=2)
    FALLS.append({"id":wid,"label":record["label"],"object":water.name,"path":[list(p) for p in path],"width":width,"sections":sections,"source_host_front":host})
print("V07_WATER_READY",len(FALLS),flush=True)


# 云海仍用低复杂度实体占位，近处云层顶面低于全部岩体支撑。
# 原南向云海保留远距离关系并压薄，补少量远山供外景与殿内月门共同阅读。
cloud_source=next(ob for ob in COL["cloud"].objects if ob.type=="MESH")
cloud_data=cloud_source.data.copy()
cloud_data.name="V07_云海占位共享网格"
cloud_data.materials.clear()
cloud_data.materials.append(MAT["cloud"])
for ob in list(COL["cloud"].objects):
    if ob.type=="MESH":
        ob.data=cloud_data
        ob.scale.z*=P["cloud_height_scale"]
        ob.location.z+=P["cloud_height_offset"]
        ob["V07整理"]="保留远处云海分布，压薄高度；不使用体积雾"

# 远山的山脚延伸到画面下方，禁止把带封底的浮岛放大当作远景山海。
# 三组截面只描述长山脊、山腰和山脚，面数低且不重复近景岩层条带。
def distant_ridge(name,x,y,rx,ry,top,seed,mat):
    n=18
    vv=[]
    for level,(scale,zbase) in enumerate([(1.65,top-1650),(1.12,top-370),(.76,top)]):
        for i in range(n):
            a=math.tau*i/n
            px=math.cos(a)*(1+.13*math.sin(3*a+seed))
            py=math.sin(a)*(1+.16*math.cos(5*a))
            z=zbase
            if level==2:
                z-=150*(.65+.40*math.sin(a*3+seed)+.35*abs(math.sin(a)))
                if i==3:
                    z=top
            vv.append((x+rx*px*scale,y+ry*py*scale,z))
    ff=[tuple(reversed(range(n)))]
    for layer in range(2):
        for i in range(n):
            a,b=layer*n+i,layer*n+(i+1)%n
            ff.extend([(a,b,b+n),(a,b+n,a+n)])
    vv.append((x-rx*.10,y,top-35))
    ff.extend((len(vv)-1,2*n+i,2*n+(i+1)%n) for i in range(n))
    return mesh(name,vv,ff,"far",mat)
for i,(x,y,rx,ry,top,lx) in enumerate(P["distant_mountains"]):
    distant_ridge(f"远山_{i:02}_简化山脊",x,y,rx,ry,top,900+i,"far1" if i<3 else "far2")


# 环境细节相机只追加在第十二至十六帧，原十一台相机与时间线绑定全部保留。
# 所有图共用一套可见性和 V6 灯光，不对不同机位偷偷隐藏支撑或植物。
for record in P["detail_cameras"]:
    data=bpy.data.cameras.new(record["name"])
    ob=bpy.data.objects.new(record["name"],data)
    COL["camera"].objects.link(ob)
    ob.location=record["location"]
    ob.rotation_euler=(Vector(record["target"])-ob.location).to_track_quat("-Z","Y").to_euler()
    data.lens=record["lens"]
    data.clip_start=.08
    data.clip_end=10000
    marker=SCENE.timeline_markers.new(record["name"],frame=record["frame"])
    marker.camera=ob


def text_block(name,body):
    block=bpy.data.texts.get(name) or bpy.data.texts.new(name)
    block.clear()
    block.write(body)


text_block("09_v07环境参数.json",json.dumps(P,ensure_ascii=False,indent=2))
text_block("10_v07环境重建.py",script_body)
text_block("02_当前阶段重建入口.py",'# 当前 V7 环境直接读取已验收 V6 建筑文件，摘要不符时停止。\n# 编辑09_v07环境参数.json后运行，原V6与全部建筑成果始终保留。\nimport bpy\nexec(compile(bpy.data.texts["10_v07环境重建.py"].as_string(),"内嵌V07环境重建","exec"),{"__name__":"__main__"})\n')
if (OUT/"v07验收说明.md").exists():
    text_block("00_v07验收说明.md",(OUT/"v07验收说明.md").read_text(encoding="utf-8"))
if (ROOT/"design_parameters.json").exists():
    text_block("01_设计参数.json",(ROOT/"design_parameters.json").read_text(encoding="utf-8"))
control=next(iter(COL["control"].objects))
control["参数编辑说明"]="当前 V07：编辑09_v07环境参数.json后运行02_当前阶段重建入口.py；以V6建筑工程为唯一基准。"
control["v07_基准SHA256"]=P["baseline_sha256"]
SCENE["阶段"]="V07 山体、古松、瀑布环境建模；完成后停止等待验收"
SCENE["V07基准文件"]=str(baseline)
SCENE["V07基准SHA256"]=P["baseline_sha256"]
SCENE["V07重建入口"]="02_当前阶段重建入口.py；外部scripts/build_environment_v07.py"
SCENE["V07范围"]="可编辑山体岩层、古松主枝与共享针叶簇、四道连续叠瀑、低复杂度远山与云海布局"
SCENE["V07验收机位"]="1至4原固定机位；12主崖壁；13古松样板；14亭桥峡谷；15瀑布出水口；16桥拱仰视"
SCENE.render.engine="CYCLES"
SCENE.cycles.device="CPU"
SCENE.cycles.samples=P["render_samples"]
SCENE.cycles.use_denoising=True
SCENE.cycles.adaptive_threshold=.045
SCENE.render.resolution_x=P["render_width"]
SCENE.render.resolution_y=P["render_height"]
SCENE.render.resolution_percentage=100
SCENE.render.image_settings.file_format="PNG"
SCENE.render.threads_mode="FIXED"
SCENE.render.threads=P["render_threads"]
SCENE.frame_end=max(r["frame"] for r in P["detail_cameras"])
SCENE.frame_set(1)
SCENE.camera=next(m.camera for m in SCENE.timeline_markers if m.frame==1)
SCENE.render.filepath=str(OUT/"renders"/"01_oblique.png")
bpy.ops.object.select_all(action="DESELECT")
if bpy.context.screen:
    for area in bpy.context.screen.areas:
        if area.type=="VIEW_3D":
            area.spaces.active.region_3d.view_perspective="CAMERA"
            area.spaces.active.shading.color_type="MATERIAL"
            area.spaces.active.overlay.show_extras=False
            area.spaces.active.overlay.show_floor=False
            area.spaces.active.clip_end=10000
bpy.context.view_layer.update()
destination=OUT/"qa"/"v07_working.blend" if "--preview" in ARGS else ROOT/P["output_file"]
bpy.ops.wm.save_as_mainfile(filepath=str(destination),compress=True)
summary={"file":str(destination),"baseline_sha256":P["baseline_sha256"],"objects":len(SCENE.objects),
         "removed_environment_placeholders":REMOVED,"rock_objects":[o.name for o in ROCKS],"pines":PINES,"waterfalls":FALLS,
         "collections":{c.name:len(c.all_objects) for c in SCENE.collection.children},
         "environment_unique_meshes":len({o.data for o in SCENE.objects if o.type=="MESH" and o.name.startswith("V07_")}),
         "environment_unique_vertices":sum(len(m.vertices) for m in {o.data for o in SCENE.objects if o.type=="MESH" and o.name.startswith("V07_")})}
(OUT/"qa"/"build_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
print("V07_SAVED",str(destination),"OBJECTS",len(SCENE.objects),flush=True)
if "--preview" in ARGS or "--render" in ARGS:
    frames=[int(v) for v in ARGS[ARGS.index("--frames")+1].split(",")] if "--frames" in ARGS else [1,2,3,4,12,13,14,15,16]
    if "--preview" in ARGS:
        SCENE.cycles.samples=12
        SCENE.render.resolution_percentage=60
    names={1:"01_oblique",2:"02_front",3:"03_aerial",4:"04_interior"}
    names.update({r["frame"]:r["output"] for r in P["detail_cameras"]})
    for frame in frames:
        SCENE.frame_set(frame)
        SCENE.camera=next(m.camera for m in SCENE.timeline_markers if m.frame==frame)
        SCENE.render.filepath=str(OUT/("qa" if "--preview" in ARGS else "renders")/(names[frame]+".png"))
        bpy.ops.render.render(write_still=True)
        print("V07_RENDER",frame,SCENE.render.filepath,flush=True)
print("V07_COMPLETE",flush=True)
