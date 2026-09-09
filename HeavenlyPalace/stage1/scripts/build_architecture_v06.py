"""
以已验收 V5 为唯一基准统一全场建筑，主殿、月门与自然环境保持原样。
本脚本在 Blender 中创建真实网格和共享构件，参数与重建入口随工程内嵌。
所有长度为米；次要建筑按原柱网分别配比，不缩放已验收主殿。
"""
import bpy
import bmesh
import json
import math
import sys
import hashlib
from pathlib import Path
from mathutils import Vector

# 先把内嵌参数和脚本复制到普通字符串，再载入基准文件。
# 基准摘要不同则停止；任何入口都不会调用 V3 或 V4 的布局生成流程。
script_path=Path(__file__).resolve() if "__file__" in globals() and Path(__file__).is_file() else None
ROOT=script_path.parents[1] if script_path else Path(bpy.data.filepath).parent
if ROOT.name=="qa":
    ROOT=ROOT.parent.parent
OUT=ROOT/"v06"
for directory in (OUT,OUT/"qa",OUT/"renders"):
    directory.mkdir(parents=True,exist_ok=True)
if script_path is None and bpy.data.texts.get("07_v06建筑参数.json"):
    P=json.loads(bpy.data.texts["07_v06建筑参数.json"].as_string())
else:
    P=json.loads((OUT/"design_parameters_v06.json").read_text(encoding="utf-8"))
script_body=script_path.read_text(encoding="utf-8") if script_path else bpy.data.texts["08_v06建筑重建.py"].as_string()
ARGS=sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
source_path=ROOT/P["baseline_file"]
source_hash=hashlib.sha256(source_path.read_bytes()).hexdigest()
if source_hash!=P["baseline_sha256"]:
    raise RuntimeError("V5 基准摘要变化，请先核对已验收源文件。")
bpy.ops.wm.open_mainfile(filepath=str(source_path))
SCENE=bpy.context.scene
SCENE.name="天宫_建筑v06_全场结构统一"
COL={key:next(c for c in SCENE.collection.children if c.name.startswith(prefix)) for key,prefix in
     [("control","00_"),("base","02_"),("entry","05_"),("corridor","06_"),("stairs","07_"),("bridge","08_"),("camera","12_")]}
MAT={key:bpy.data.materials[name] for key,name in {
    "stone":"V05_石构_暖灰哑光","frame":"V05_门圈柱础_浅石哑光","wood":"V05_木构_沉棕哑光",
    "edge":"V05_承托与边线_浅棕哑光","panel":"V05_天花板_灰棕哑光",
    "roof":"V05_屋面_青灰哑光","ridge":"V05_脊与檐边_灰褐哑光","shaft":"白模_浅色檐口柱身"}.items()}
CACHE={}
REGION=""
ROOFS=[]
JOINTS=[]
REMOVED=[]
MODULE_USES={}
POST_POSITIONS=set()


# 区域集合与构件类别分两级管理，原有承台和通行对象保留名称。
# 重复尺寸、材质、形状的构件共享网格，每个实例仍可独立定位和编辑。
def region(key,label,parent):
    col=bpy.data.collections.new(label)
    COL[parent].children.link(col)
    COL[key]=col
    for kind,title in [("roof","屋面与檐口"),("frame","梁枋椽架"),("column","柱础柱头"),("stone","石构与地面"),("joint","连接节点")]:
        sub=bpy.data.collections.new(label+"_"+title)
        col.children.link(sub)
        COL[key+"_"+kind]=sub


region("entry_center","05B_中轴直口门厅","entry")
region("entry_west","05C_西入口长廊","entry")
region("entry_east","05D_东入口长廊","entry")
region("west_walk","06A_西侧连续回廊","corridor")
region("east_walk","06B_东侧连续回廊","corridor")
for index,record in enumerate(P["pavilions"]):
    region(record["region"],f"06{chr(67+index)}_"+record["prefix"],"bridge" if record["region"]=="view_pavilion" else "corridor")
for key,label,parent in [("terrace","02A_台基压顶与石栏","base"),("steps","07A_台阶侧墙与收口","stairs"),("stone_bridge","08A_桥面石栏与桥台","bridge")]:
    region(key,label,parent)


def mesh(name,verts,faces,kind="frame",mat="wood",key=None,smooth=False,bevel=0):
    cache_key=(mat,key) if key is not None else None
    if cache_key in CACHE:
        data=CACHE[cache_key]
    else:
        data=bpy.data.meshes.new(name+"_共享网格")
        data.from_pydata(verts,[],faces)
        data.update()
        bm=bmesh.new()
        bm.from_mesh(data)
        bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.00001)
        bmesh.ops.dissolve_degenerate(bm,edges=list(bm.edges),dist=.000001)
        bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
        bm.to_mesh(data)
        bm.free()
        data.materials.append(MAT[mat])
        for face in data.polygons:
            face.use_smooth=smooth and abs(face.normal.z)<.9999
        if cache_key is not None:
            CACHE[cache_key]=data
    ob=bpy.data.objects.new("V06_"+name,data)
    COL[REGION+"_"+kind].objects.link(ob)
    ob["阶段"]="V06 全场建筑结构统一"
    ob["建筑区域"]=REGION
    ob["构件类别"]=kind
    if key is not None:
        ob["共享模块"]=str(key)[:240]
        MODULE_USES[str(key)[:240]]=MODULE_USES.get(str(key)[:240],0)+1
    if bevel:
        mod=ob.modifiers.new("细部棱边_小倒角","BEVEL")
        mod.width=bevel
        mod.segments=2
    return ob


def box_geo(loc,dims,verts,faces):
    x,y,z=loc
    w,d,h=[v/2 for v in dims]
    offset=len(verts)
    verts.extend([(x-w,y-d,z-h),(x+w,y-d,z-h),(x+w,y+d,z-h),(x-w,y+d,z-h),
                  (x-w,y-d,z+h),(x+w,y-d,z+h),(x+w,y+d,z+h),(x-w,y+d,z+h)])
    faces.extend(tuple(offset+i for i in f) for f in [(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)])


def cube(name,loc,dims,kind="frame",mat="wood",bevel=.025):
    verts,faces=[],[]
    box_geo((0,0,0),dims,verts,faces)
    ob=mesh(name,verts,faces,kind,mat,key=("方材",tuple(round(v,5) for v in dims)),bevel=bevel)
    ob.location=loc
    return ob


def sweep(name,points,width,height,kind="frame",mat="wood",bevel=0):
    origin=Vector(points[0])
    points=[Vector(p)-origin for p in points]
    verts,faces=[],[]
    for i,p in enumerate(points):
        tangent=points[min(i+1,len(points)-1)]-points[max(i-1,0)]
        lateral=Vector((-tangent.y,tangent.x,0)).normalized()*width/2
        verts.extend([p-lateral+Vector((0,0,-height/2)),p+lateral+Vector((0,0,-height/2)),
                      p+lateral+Vector((0,0,height/2)),p-lateral+Vector((0,0,height/2))])
    for i in range(len(points)-1):
        a=i*4
        faces.extend((a+j,a+(j+1)%4,a+(j+1)%4+4,a+j+4) for j in range(4))
    faces.extend([(3,2,1,0),tuple((len(points)-1)*4+j for j in range(4))])
    key=("放样",round(width,4),round(height,4),tuple(tuple(round(v,4) for v in p) for p in points))
    ob=mesh(name,verts,faces,kind,mat,key=key,bevel=bevel)
    ob.location=origin
    return ob


def lathe(name,profile,loc,mat="frame"):
    verts,faces=[],[]
    count=32
    for z,r in profile:
        verts.extend((r*math.cos(i*math.tau/count),r*math.sin(i*math.tau/count),z) for i in range(count))
    for j in range(len(profile)-1):
        faces.extend((j*count+i,j*count+(i+1)%count,(j+1)*count+(i+1)%count,(j+1)*count+i) for i in range(count))
    faces.extend([tuple(reversed(range(count))),tuple((len(profile)-1)*count+i for i in range(count))])
    ob=mesh(name,verts,faces,"column",mat,key=("回转构件",tuple(tuple(round(v,5) for v in p) for p in profile)),smooth=True)
    ob.location=loc
    return ob


def remove(objects):
    for ob in list(objects):
        REMOVED.append(ob.name)
        bpy.data.objects.remove(ob,do_unlink=True)


def move_to_region(ob,kind):
    for col in list(ob.users_collection):
        col.objects.unlink(ob)
    COL[REGION+"_"+kind].objects.link(ob)


def assign_material(ob,mat):
    data=ob.data.copy()
    ob.data=data
    data.materials.clear()
    data.materials.append(MAT[mat])


# 柱身保留 V5 的原坐标和收分，石础与柱头在原高度区间内细化。
# 柱础外包尺寸不超原柱础的边界，同型柱身也链接到同一网格。
def detail_column(shaft,floor,height):
    x,y=shaft.location.x,shaft.location.y
    radius=max(v.co.x for v in shaft.data.vertices)
    label=shaft.name.removesuffix("_柱身")
    remove(ob for ob in list(SCENE.objects) if ob.name in (label+"_柱础",label+"_柱头"))
    cube(label+"_础座",(x,y,floor+.12),(radius*2.56,radius*2.56,.24),"column","stone",.035)
    lathe(label+"_覆盆柱础",[(.22,radius*1.24),(.43,radius*1.24),(.56,radius*1.12),(1.20,radius*1.03),(1.60,radius)],(x,y,floor))
    lathe(label+"_柱头",[(0,radius*.92),(.28,radius*.97),(.46,radius*1.13),(.80,radius*1.13),(1.34,radius*1.20),(1.60,radius*1.20)],(x,y,floor+height-1.6))
    move_to_region(shaft,"column")
    key=("既有柱身",round(radius,4),round(height,4))
    if key in CACHE:
        shaft.data=CACHE[key]
    else:
        CACHE[key]=shaft.data
    shaft["V06保留原柱身"]=True


# 小型斗拱只采用两跳，横向承拱与进深挑拱分层搭接。
# 构件按廊柱直径配比，亭与入口采用相近尺度的共享模块。
def bracket(name,loc,scale=1.0,angle=0):
    verts,faces=[],[]
    for center,dims in [((0,0,.16),(1.18,1.18,.32)),((0,0,.43),(2.8,.66,.32)),
                        ((-.95,0,.72),(.60,.64,.28)),((.95,0,.72),(.60,.64,.28)),
                        ((0,0,1.00),(.76,3.6,.40)),((0,-1.3,1.32),(.70,.62,.25)),
                        ((0,1.3,1.32),(.70,.62,.25)),((0,0,1.54),(3.8,.82,.24))]:
        box_geo(tuple(v*scale for v in center),tuple(v*scale for v in dims),verts,faces)
    ob=mesh(name,verts,faces,"frame","edge",key=("两跳简化斗拱",scale),bevel=.022)
    ob.location=loc
    ob.rotation_euler.z=angle
    return ob


# 屋面采用与 V5 相同的连续四坡放样，薄实体、角脊和连檐木独立建模。
# 所有形状先在局部坐标生成，成对亭子与入口翼廊直接共享网格。
def roof_surface(spec,side,s,u):
    w=spec["ridge_length"]+(spec["width"]-spec["ridge_length"])*u
    d=spec["depth"]*u
    base=spec["eave"]-P["roof_toe_lift"]
    z=base+(spec["eave"]+spec["rise"]-base)*(1-u)**P["roof_curve_power"]+P["roof_toe_lift"]*u**8
    z+=spec["corner"]*abs(s)**4*u**3
    xy=[(s*w/2,-d/2),(w/2,s*d/2),(-s*w/2,d/2),(-w/2,-s*d/2)][side]
    return Vector((xy[0],xy[1],z))


def roof_height(spec,x,y):
    x-=spec["center"][0]
    y-=spec["center"][1]
    ux=max(0,(abs(x)-spec["ridge_length"]/2)/((spec["width"]-spec["ridge_length"])/2))
    uy=abs(y)/(spec["depth"]/2)
    u=max(ux,uy)
    if u>1.0001:
        return None
    u=min(1,u)
    if uy>=ux:
        s=x/(spec["ridge_length"]/2+(spec["width"]-spec["ridge_length"])/2*u)
    else:
        s=y/(spec["depth"]/2*u)
    return roof_surface(spec,0,s,u).z


def hip_roof(name,cx,cy,width,depth,eave,rise,corner=1.2):
    spec={"name":name,"region":REGION,"kind":"hip","center":[cx,cy],"width":width,"depth":depth,
          "ridge_length":width*.48,"eave":eave,"rise":rise,"corner":corner,"thickness":P["secondary_roof_thickness"]}
    segments,rings=24,24
    count=segments*4
    verts,faces=[],[]
    for underside in (0,1):
        for j in range(rings+1):
            for side in range(4):
                for i in range(segments):
                    verts.append(roof_surface(spec,side,-1+2*i/segments,j/rings)-Vector((0,0,underside*spec["thickness"])))
    layer=(rings+1)*count
    for j in range(rings):
        for i in range(count):
            a=j*count+i
            b=j*count+(i+1)%count
            faces.extend([(a,b,b+count,a+count),(a+count+layer,b+count+layer,b+layer,a+layer)])
    for i in range(count):
        a=rings*count+i
        b=rings*count+(i+1)%count
        faces.append((a,b,b+layer,a+layer))
    shape=("四坡薄屋面",width,depth,eave,rise,corner,spec["thickness"])
    ob=mesh(name+"_连续曲面",verts,faces,"roof","roof",key=shape,smooth=True)
    ob.location=(cx,cy,0)
    ob["屋面实体厚度_米"]=spec["thickness"]
    spec["object"]=ob.name
    ROOFS.append(spec)
    offset=Vector((cx,cy,0))
    for side in range(4):
        pts=[offset+roof_surface(spec,side,-1+2*i/64,1) for i in range(65)]
        sweep(name+f"_薄檐口_{side}",[p-Vector((0,0,.12)) for p in pts],.27,.30,"roof","ridge")
        sweep(name+f"_连檐木_{side}",[p-Vector((0,0,.49)) for p in pts],.25,.26,"roof","edge")
        pts=[offset+roof_surface(spec,side,1,.006+.994*i/32)+Vector((0,0,.09)) for i in range(33)]
        sweep(name+f"_角脊_{side}",pts,.40,.24,"roof","ridge")
        rafter_count=max(12,round((width if side%2==0 else depth)/2))
        for i in range(rafter_count):
            s=-1+2*(i+.5)/rafter_count
            pts=[offset+roof_surface(spec,side,s,.025+.975*j/20)-Vector((0,0,spec["thickness"]+.105)) for j in range(21)]
            sweep(name+f"_椽条_{side}_{i:02}",pts,P["rafter_width"],P["rafter_height"],"frame","edge")
        for j,u in enumerate((.38,.68,.91)):
            pts=[offset+roof_surface(spec,side,-1+2*i/32,u)-Vector((0,0,spec["thickness"]+.44)) for i in range(33)]
            sweep(name+f"_曲线檩_{side}_{j}",pts,.44,.40,"frame","wood")
    pts=[(cx+spec["ridge_length"]*(-.5+i/32),cy,eave+rise+.24+.08*abs(-1+2*i/32)**8) for i in range(33)]
    sweep(name+"_正脊素收头",pts,.65,.44,"roof","ridge")
    return spec


# 长廊采用无分段接缝的两坡曲面，沿进深方向布置共享椽条。
# 两端低于亭檐，保留明确的高低檐层次，不把屋脊插进角亭屋面。
def corridor_height(x):
    q=P["corridor"]
    u=min(1,abs(x)/(q["width"]/2))
    return q["eave_z"]-.14+(q["rise"]+.14)*(1-u)**1.7+.14*u**8


def corridor_roof(name,cx):
    q=P["corridor"]
    length=q["north"]-q["south"]
    nx,ny=64,20
    verts,faces=[],[]
    for underside in (0,1):
        for j in range(ny+1):
            for i in range(nx+1):
                x=-q["width"]/2+q["width"]*i/nx
                verts.append((x,length*j/ny,corridor_height(x)-underside*q["thickness"]))
    layer=(nx+1)*(ny+1)
    for j in range(ny):
        for i in range(nx):
            a=j*(nx+1)+i
            faces.extend([(a,a+1,a+nx+2,a+nx+1),(a+layer+nx+1,a+layer+nx+2,a+layer+1,a+layer)])
    boundary=list(range(nx+1))+[j*(nx+1)+nx for j in range(1,ny+1)]
    boundary+=[ny*(nx+1)+i for i in range(nx-1,-1,-1)]+[j*(nx+1) for j in range(ny-1,0,-1)]
    faces.extend((a+layer,b+layer,b,a) for a,b in zip(boundary,boundary[1:]+boundary[:1]))
    ob=mesh(name+"_通长两坡薄屋面",verts,faces,"roof","roof",key=("连续廊顶",length,q["width"],q["rise"]),smooth=True)
    ob.location=(cx,q["south"],0)
    ob["屋面实体厚度_米"]=q["thickness"]
    spec={"name":name,"region":REGION,"kind":"corridor","center":[cx,(q["south"]+q["north"])/2],
          "width":q["width"],"depth":length,"object":ob.name,"eave":q["eave_z"],"rise":q["rise"],"thickness":q["thickness"]}
    ROOFS.append(spec)
    for side in (-1,1):
        x=cx+side*q["width"]/2
        sweep(name+f"_连续薄檐_{side}",[(x,q["south"],19.86),(x,q["north"],19.86)],.26,.28,"roof","ridge")
        sweep(name+f"_连续连檐木_{side}",[(x,q["south"],19.48),(x,q["north"],19.48)],.26,.26,"roof","edge")
        count=math.ceil(length/q["rafter_step"])
        for i in range(count+1):
            y=q["south"]+length*i/count
            pts=[(cx+side*q["width"]/2*j/24,y,corridor_height(q["width"]/2*j/24)-q["thickness"]-.10) for j in range(25)]
            sweep(name+f"_共享椽_{side}_{i:03}",pts,.22,.26,"frame","edge")
    for x in (-12.3,-7,0,7,12.3):
        z=corridor_height(x)-q["thickness"]-.43
        sweep(name+f"_通长檩_{x}",[(cx+x,q["south"],z),(cx+x,q["north"],z)],.50,.42,"frame","wood")
    sweep(name+"_通长素脊",[(cx,q["south"],q["eave_z"]+q["rise"]+.18),(cx,q["north"],q["eave_z"]+q["rise"]+.18)],.56,.38,"roof","ridge")
    return spec


# 承斗顶面逐角点贴合檩架下缘，避免斜坡上方材穿出屋面。
# 柱头到屋面之间的每条受力线均由梁、斗拱、短柱与承斗连续连接。
def roof_seat(name,x,y,base,spec,width=1.05):
    corners=[(x-width/2,y-width/2),(x+width/2,y-width/2),(x+width/2,y+width/2),(x-width/2,y+width/2)]
    heights=[roof_height(spec,px,py)-spec["thickness"]-.66 for px,py in corners]
    bottom=min(heights)-.27
    if bottom>base:
        cube(name+"_短柱",(x,y,(base+bottom)/2),(.66,.66,bottom-base),"frame","wood")
    else:
        bottom=base-.04
    verts=[(px-x,py-y,bottom) for px,py in corners]+[(px-x,py-y,z) for (px,py),z in zip(corners,heights)]
    faces=[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
    ob=mesh(name+"_随坡承斗",verts,faces,"frame","edge")
    ob.location=(x,y,0)


def hip_frame(name,spec,xs,ys,column_top,bracket_scale=.9):
    x0,x1=min(xs),max(xs)
    y0,y1=min(ys),max(ys)
    for y in ys:
        cube(name+f"_横向额枋_{y}",((x0+x1)/2,y,column_top+.58),(x1-x0+2,1.20,1.16),"frame","wood")
        cube(name+f"_额枋边线_{y}",((x0+x1)/2,y-.66,column_top+.32),(x1-x0+2,.16,.19),"frame","edge")
    for x in xs:
        cube(name+f"_跨进深梁_{x}",(x,(y0+y1)/2,column_top+.68),(1.18,y1-y0+2,1.30),"frame","wood")
        for y in ys:
            bracket(name+f"_柱头斗拱_{x}_{y}",(x,y,column_top+1.32),bracket_scale)
            roof_seat(name+f"_檐柱上承_{x}_{y}",x,y,column_top+1.32+1.66*bracket_scale,spec)
    for y in (y0,y1):
        pts=[(x0+(x1-x0)*i/48,y,roof_height(spec,x0+(x1-x0)*i/48,y)-spec["thickness"]-.46) for i in range(49)]
        sweep(name+f"_柱网上檩横_{y}",pts,.63,.45,"frame","wood")
    for x in (x0,x1):
        pts=[(x,y0+(y1-y0)*i/32,roof_height(spec,x,y0+(y1-y0)*i/32)-spec["thickness"]-.46) for i in range(33)]
        sweep(name+f"_柱网上檩纵_{x}",pts,.63,.45,"frame","wood")
    for i,x in enumerate(xs):
        for j,y in enumerate((y0*.5+y1*.5,)):
            top=roof_height(spec,x,y)-spec["thickness"]-.66
            base=column_top+1.30
            cube(name+f"_屋架瓜柱_{i}_{j}",(x,y,(base+top)/2),(.78,.78,top-base),"frame","wood")
    pts=[(x0+(x1-x0)*i/48,(y0+y1)/2,roof_height(spec,x0+(x1-x0)*i/48,(y0+y1)/2)-spec["thickness"]-.43) for i in range(49)]
    sweep(name+"_屋架脊檩",pts,.68,.48,"frame","wood")


# 高低檐之间增加实体封檐和上翻泛水，沿接缝逐点取两侧屋面高度。
# 记录搭接范围及最小高差，审查脚本随后检查这些真实接头的几何。
def stepped_joint(name,points,low_height,high_height):
    verts,faces=[],[]
    lows,highs=[],[]
    for i,(x,y) in enumerate(points):
        low=low_height(x,y)-.10
        high=high_height(x,y)-.08
        lows.append(low)
        highs.append(high)
        direction=Vector(points[min(i+1,len(points)-1)])-Vector(points[max(i-1,0)])
        side=Vector((-direction.y,direction.x)).normalized()*.09
        verts.extend([(x-side.x,y-side.y,low),(x+side.x,y+side.y,low),
                      (x+side.x,y+side.y,high),(x-side.x,y-side.y,high)])
    for i in range(len(points)-1):
        a=i*4
        faces.extend((a+j,a+(j+1)%4,a+(j+1)%4+4,a+j+4) for j in range(4))
    faces.extend([(3,2,1,0),tuple((len(points)-1)*4+j for j in range(4))])
    ob=mesh(name+"_高低檐封口",verts,faces,"joint","panel")
    sweep(name+"_上翻泛水",[(x,y,z+.05) for (x,y),z in zip(points,highs)],.35,.22,"joint","ridge")
    sweep(name+"_下缘收边",[(x,y,z+.05) for (x,y),z in zip(points,lows)],.22,.20,"joint","edge")
    JOINTS.append({"name":name,"object":ob.name,"region":REGION,"minimum_height_difference":min(b-a for a,b in zip(lows,highs)),"samples":len(points)})


# 入口保留已验收直口墙体，新增边框向孔外展开，不设横跨地面的门槛。
# 门厅和翼廊分别按各自的柱高与跨度构建，中央门厅仍低于主殿。
REGION="entry_center"
entry_wall=bpy.data.objects["前端入口_直口门墙"]
move_to_region(entry_wall,"stone")
assign_material(entry_wall,"stone")
remove(ob for ob in list(COL["entry"].objects) if "屋顶" in ob.name or "枋" in ob.name)
entry=P["entry"]
gy=entry["center_y"]
for side in (-1,1):
    # 孔内侧与原墙面错开三厘米，避免两张同向共面石面产生黑色闪烁。
    # 原墙的二十八米净口保持原状，附加边框只向孔外延伸。
    cube(f"入口直口侧框_{side}",(side*14.58,gy,14.5),(1.10,5.8,29),"stone","frame",.04)
    cube(f"入口侧墙墙脚_{side}",(side*24.04,gy,.40),(20.02,5.65,.80),"stone","frame",.035)
    cube(f"入口侧墙壁柱_{side}",(side*32.65,gy,16.4),(1.6,5.75,32.8),"stone","frame",.04)
cube("入口直口上框",(0,gy,29.53),(30.2,5.8,1.0),"stone","frame",.04)
cube("入口直口上额枋",(0,gy,32.9),(66,5.4,.8),"frame","wood",.03)
for x in (-30,30):
    for y in (gy-10,gy+10):
        label=f"入口门厅檐柱_{x}_{y}"
        shaft=lathe(label+"_柱身",[(1.6,2.1),(30.4,1.932)],(x,y,0),"shaft")
        detail_column(shaft,0,32)
central_roof=hip_roof("入口中央门厅",0,gy,entry["central_width"],entry["central_depth"],entry["central_eave_z"],entry["central_rise"],1.5)
hip_frame("入口中央门厅",central_roof,[-30,30],[gy-10,gy+10],32,.9)
wing_roofs={}
for side in (-1,1):
    REGION="entry_west" if side<0 else "entry_east"
    shafts=[ob for ob in list(COL["entry"].objects) if ob.name.startswith(f"月门侧长廊柱_{side}_") and ob.name.endswith("_柱身")]
    for shaft in shafts:
        detail_column(shaft,0,26)
    xs=[side*x for x in (45,68,91,114,139)]
    spec=hip_roof(f"入口翼廊_{side}",side*entry["wing_center_x"],gy,entry["wing_width"],entry["wing_depth"],entry["wing_eave_z"],entry["wing_rise"],.75)
    hip_frame(f"入口翼廊_{side}",spec,xs,[gy-10,gy+10],26,.75)
    wing_roofs[side]=spec
    x=side*38.90
    points=[(x,gy-16.8+33.6*i/64) for i in range(65)]
    stepped_joint(f"入口中央与翼廊_{side}",points,lambda x,y,spec=spec:roof_height(spec,x,y),lambda x,y:roof_height(central_roof,x,y))


# 清除次要建筑的粗屋面和整块承托，保留各亭地坪与原柱网。
# 前角亭加深前后出檐，覆盖原来入口与角亭之间的两米空隙。
remove(ob for ob in list(COL["corridor"].objects) if "屋顶" in ob.name or "_上部支撑" in ob.name or "连续梁" in ob.name)
remove(ob for ob in list(COL["bridge"].objects) if ob.name.startswith("东侧观景亭_") and ("屋顶" in ob.name or "上部支撑" in ob.name))
pavilion_roofs={}
for record in P["pavilions"]:
    REGION=record["region"]
    label=record["prefix"]
    x,y,z=record["center"]
    floor=bpy.data.objects[label+"_地坪"]
    move_to_region(floor,"stone")
    assign_material(floor,"frame")
    for shaft in [ob for ob in list(SCENE.objects) if ob.name.startswith(label+"_角柱_") and ob.name.endswith("_柱身")]:
        detail_column(shaft,z,record["column_height"])
    spec=hip_roof(label,x,y,record["roof_width"],record["roof_depth"],record["eave_z"],record["rise"],P["secondary_corner_lift"])
    half=record["grid"]/2
    hip_frame(label,spec,[x-half,x+half],[y-half,y+half],z+record["column_height"],.85)
    pavilion_roofs[label]=spec
    w,d=floor.dimensions.x,floor.dimensions.y
    for side in (-1,1):
        # 边檐放在原台面轮廓以外且略低于完成面，消除重叠顶面。
        # 地坪本体的尺寸和标高继续沿用验收基准。
        cube(label+f"_台面边缘横_{side}",(x,y+side*(d/2+.15),z-.20),(w,.3,.28),"stone","frame",.025)
        cube(label+f"_台面边缘纵_{side}",(x+side*(w/2+.15),y,z-.20),(.3,d,.28),"stone","frame",.025)


for side in (-1,1):
    REGION="west_walk" if side<0 else "east_walk"
    cx=side*P["corridor"]["center_x"]
    floor=bpy.data.objects[f"侧回廊地坪_{side}"]
    move_to_region(floor,"stone")
    assign_material(floor,"frame")
    cube(f"回廊地坪下补齐承托_{side}",(cx,-8,-.16),(24,318,.32),"stone","stone",0)
    shafts=[ob for ob in list(COL["corridor"].objects) if ob.name.startswith(f"侧回廊柱_{side}_") and ob.name.endswith("_柱身")]
    for shaft in shafts:
        if abs(shaft.location.y+151)<.01:
            label=shaft.name.removesuffix("_柱身")
            remove(ob for ob in list(SCENE.objects) if ob.name.startswith(label+"_"))
        else:
            detail_column(shaft,0,17)
    spec=corridor_roof(f"侧回廊_{side}",cx)
    for sx in (-1,1):
        cube(f"回廊连续额枋_{side}_{sx}",(cx+sx*7,-10,17.70),(1.55,276,1.40),"frame","wood")
        cube(f"回廊额枋收边_{side}_{sx}",(cx+sx*7+sx*.83,-10,17.38),(.14,276,.18),"frame","edge")
    for y in range(-133,120,18):
        cube(f"回廊跨通道梁_{side}_{y}",(cx,y,18.25),(16.4,1.10,1.05),"frame","wood")
        for sx in (-1,1):
            x=cx+sx*7
            bracket(f"回廊檐柱斗拱_{side}_{sx}_{y}",(x,y,18.775),.60,math.pi/2)
            seat_top=corridor_height(7)-P["corridor"]["thickness"]-.64
            base=18.775+1.66*.6
            if seat_top>base:
                cube(f"回廊柱头承檩_{side}_{sx}_{y}",(x,y,(base+seat_top)/2),(.62,.72,seat_top-base),"frame","wood")
        top=corridor_height(0)-P["corridor"]["thickness"]-.64
        cube(f"回廊脊下瓜柱_{side}_{y}",(cx,y,(18.775+top)/2),(.65,.75,top-18.775),"frame","wood")
        for sx in (-1,1):
            pts=[(cx+sx*14*j/24,y,corridor_height(14*j/24)-P["corridor"]["thickness"]-.52) for j in range(25)]
            sweep(f"回廊主椽承架_{side}_{sx}_{y}",pts,.48,.43,"frame","wood")
    front=pavilion_roofs[f"前庭角亭_{side}"]
    rear=pavilion_roofs[f"前庭后角亭_{side}"]
    for label,y,high in [("前角亭接连续廊",-138.90,front),("后角亭接连续廊",121.15,rear)]:
        points=[(cx-14.4+28.8*i/64,y) for i in range(65)]
        stepped_joint(label+str(side),points,lambda x,y,cx=cx:corridor_height(x-cx),lambda x,y,high=high:roof_height(high,x,y))
    REGION="west_front" if side<0 else "east_front"
    wing=wing_roofs[side]
    points=[(cx-15.75+31.5*i/64,-175.10) for i in range(65)]
    stepped_joint(f"入口回廊转角搭接_{side}",points,lambda x,y,front=front:roof_height(front,x,y),
                  lambda x,y,wing=wing:roof_height(wing,x,max(y,-175.0)))
    for sx in (-1,1):
        x=cx+sx*9
        sweep(f"入口角亭联系梁_{side}_{sx}",[(x,-182,26.65),(x,-166,23.60)],.95,1.15,"joint","wood")


# 石栏采用统一素面柱、退台柱帽、上下横档和简洁竖梃。
# 栏杆向临空一侧微移，新的柱脚和扶手不侵占 V5 的原通行边界。
def stone_railing(name,a,b,height=1.5,step=6.0):
    a,b=Vector(a),Vector(b)
    length=(b-a).length
    direction=(b-a).normalized()
    count=max(1,math.ceil(length/step))
    pitch=length/count
    # 连续石地栿下探至原承台，补足前庭边栏原有的三十厘米悬空。
    # 顶面微露三厘米并位于栏杆原占地内，避免与平台顶面共面闪烁。
    sweep(name+"_连续石地栿",[a-direction*.46+Vector((0,0,-.14)),b+direction*.46+Vector((0,0,-.14))],.84,.34,"stone","frame",.014)
    verts,faces=[],[]
    for loc,dims in [((0,0,.10),(.84,.84,.20)),((0,0,.24),(.65,.65,.10)),
                     ((0,0,(height+.26)/2),(.46,.46,height-.26)),
                     ((0,0,height-.02),(.65,.65,.16)),((0,0,height+.11),(.57,.57,.10))]:
        box_geo(loc,dims,verts,faces)
    for i in range(count+1):
        # 共用端点只保留一根望柱，转角和桥口不叠放两个相同柱帽。
        # 横档仍分别连接到该柱，保证分区域栏杆在节点处连续。
        position=a+(b-a)*i/count
        post_key=tuple(round(v,4) for v in position)+(height,)
        if post_key in POST_POSITIONS:
            continue
        POST_POSITIONS.add(post_key)
        ob=mesh(name+f"_素面望柱_{i:03}",verts,faces,"stone","frame",key=("素面石栏望柱",height),bevel=.028)
        ob.location=position
    for i in range(count):
        start=a+direction*(pitch*i+.23)
        end=a+direction*(pitch*(i+1)-.23)
        for z,w,h,mat in [(height-.13,.38,.23,"frame"),(.35,.26,.22,"stone"),(.78,.22,.16,"frame")]:
            sweep(name+f"_横档_{i:03}_{z:.2f}",[start+Vector((0,0,z)),end+Vector((0,0,z))],w,h,"stone",mat,.014)
        inner=max(2,math.ceil(pitch/1.5))
        for j in range(1,inner):
            loc=a+direction*(pitch*(i+j/inner))
            cube(name+f"_竖梃_{i:03}_{j}",loc+Vector((0,0,(height+.19)/2)),(.16,.16,height-.52),"stone","frame",.014)
    return count


rail_paths=[]
for parent in ("base","bridge"):
    for ob in list(COL[parent].objects):
        if ob.name.endswith("_扶手") and "护栏" in ob.name:
            label=ob.name.removesuffix("_扶手")
            extent=max(v.co.z for v in ob.data.vertices)
            a=ob.matrix_world@Vector((0,0,-extent))
            b=ob.matrix_world@Vector((0,0,extent))
            height=1.6 if label.startswith("东侧桥护栏") else 1.5
            a.z=round(a.z-height,3)
            b.z=round(b.z-height,3)
            rail_paths.append((parent,label,a,b,height))
for parent,label,a,b,height in rail_paths:
    REGION="terrace" if parent=="base" else "stone_bridge"
    remove(ob for ob in list(COL[parent].objects) if ob.name.startswith(label+"_"))
    if label.startswith("东侧桥护栏"):
        sign=1 if a.y>178 else -1
        a.y=b.y=178+sign*P["bridge"]["rail_offset"]
    elif abs(a.x-b.x)<.01:
        a.x+=.23*(1 if a.x>0 else -1)
        b.x=a.x
    else:
        a.y-=.23
        b.y=a.y
    if label=="东平台东护栏":
        a.y,b.y=141.77,214.5
    if label=="东平台南护栏":
        a.x,b.x=264.5,335.23
    stone_railing(label,a,b,height,P["stone_rail_module_length"])


# 平台主体、压顶上表面和广场分缝均沿用 V5，只细化外立面收边。
# 前缘收边避开所有台阶口，外侧新线脚始终低于原完成面。
REGION="terrace"
cube("入口至前庭同层接坪",(0,-171.5,-.17),(310,11,.34),"stone","frame",0)
# 入口后沿至广场前沿之间原来露出较低承台，形成三十厘米落差。
# 接坪只补齐两者之间的十一米连接带，原广场范围和零米标高均保持。
for ob in list(COL["base"].objects):
    if ob.type=="MESH" and (ob.name.startswith("台基") or ob.name in ("前庭总承台_宽310米","月门前平台_标高0")):
        assign_material(ob,"frame" if "压顶" in ob.name or "腰线" in ob.name else "stone")
for index,(width,front,back,top) in enumerate([(300,160,378,12),(272,197,372,24),(240,234,366,36)],1):
    # 压顶前挑原来覆盖末级踏步，缩短了末级可用踏面。
    # 仅在三处台阶口切回梯顶线，踏步原网格和平台完成面保持不变。
    cap=bpy.data.objects[f"台基{index}_压顶板"]
    for x,opening in [(0,64),(-(112-(index-1)*12),14),(112-(index-1)*12,14)]:
        cut=cube(f"临时压顶踏步口_{index}_{x}",(x,front-.5,top-.40),(opening,1.0,3.0),"stone","stone",0)
        bpy.context.view_layer.objects.active=cap
        mod=cap.modifiers.new("台阶口压顶收至梯顶","BOOLEAN")
        mod.operation="DIFFERENCE"
        mod.solver="EXACT"
        mod.object=cut
        bpy.ops.object.modifier_apply(modifier=mod.name)
        bpy.data.objects.remove(cut,do_unlink=True)
    cap["V06台阶口收口"]="只在64米中轴阶及两处14米辅助阶口去除0.8米前挑；原完成面标高不变。"
    for sign in (-1,1):
        for dz,w,h in [(-.28,.26,.20),(-1.05,.32,.22),(-1.48,.22,.18)]:
            cube(f"台基{index}_压顶外挑纵线_{sign}_{dz}",(sign*(width/2+.78),(front+back)/2,top+dz),(w,back-front+1.6,h),"stone","frame",.025)
        for low,high in [(34,97-(index-1)*12),(127-(index-1)*12,width/2+.8)]:
            if high>low:
                cube(f"台基{index}_前沿压顶收边_{sign}_{low}",(sign*(low+high)/2,front-.79,top-.34),(high-low,.25,.26),"stone","frame",.025)
    cube(f"台基{index}_后沿压顶收边",(0,back+.78,top-.34),(width+1.6,.24,.26),"stone","frame",.025)
for sign in (-1,1):
    cube(f"前庭外缘叠涩_{sign}",(sign*155.12,-30,-.70),(.40,406,.35),"stone","frame",.025)
    # 前平台与下层承台原有共面立面用独立外包薄石条收口。
    # 薄条避开四十八米登山台阶，不改动上表面或原平台标高。
    cube(f"前平台正面石构收口_{sign}",(sign*90.75,-233.055,-1.50),(130.5,.12,2.88),"stone","frame",.018)


# 台阶原始逐级踏面保留，仅把斜方杆侧边替换为落地侧墙和薄压顶。
# 所有侧墙内缘都在踏步净宽之外，平台转换段也不添加横向门槛。
REGION="steps"
stair_objects=[ob for ob in list(COL["stairs"].objects) if ob.type=="MESH" and "踏步高度_米" in ob]
for ob in stair_objects:
    assign_material(ob,"frame")
    verts=[ob.matrix_world@v.co for v in ob.data.vertices]
    xmin,xmax=min(v.x for v in verts),max(v.x for v in verts)
    y0,y1=min(v.y for v in verts),max(v.y for v in verts)
    z0=min(v.z for v in verts)+.7
    z1=max(v.z for v in verts)
    remove(o for o in list(COL["stairs"].objects) if o.name.startswith(ob.name+"_侧挡墙_"))
    for sign,x in [(-1,xmin-.8),(1,xmax+.8)]:
        w=.6
        vv=[(x-w,y0,z0-.7),(x+w,y0,z0-.7),(x+w,y1,z0-.7),(x-w,y1,z0-.7),
            (x-w,y0,z0+.34),(x+w,y0,z0+.34),(x+w,y1,z1+.34),(x-w,y1,z1+.34)]
        ff=[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
        mesh(ob.name+f"_实体侧墙_{sign}",vv,ff,"stone","stone",bevel=.035)
        sweep(ob.name+f"_侧墙薄压顶_{sign}",[(x,y0,z0+.46),(x,y1,z1+.46)],1.28,.24,"stone","frame",.024)
        sweep(ob.name+f"_侧面腰线_{sign}",[(x+sign*.62,y0,z0+.11),(x+sign*.62,y1,z1+.11)],.12,.15,"stone","frame")


# 东桥原桥面、腹墙和实体桥台继续承托，细化部件在原十二米桥面外侧。
# 新增桥端渐开栏杆与观景台缺失的边栏，桥口保留完整的贯通宽度。
REGION="stone_bridge"
bp=P["bridge"]
deck=bpy.data.objects["东侧桥_连续水平桥面"]
# V5 桥面与一级压顶重叠八十厘米，顶面共面导致接头出现黑带。
# 只把桥面西端收至原压顶外边，完整步行面仍由同高平台连续接到桥面。
deck.data=deck.data.copy()
for vertex in deck.data.vertices:
    if abs((deck.matrix_world@vertex.co).x-150)<.001:
        vertex.co.x+=.8
deck.data.update()
deck["V06桥面接头修正"]="西端由X150收至一级压顶外边X150.8；宽12米、顶Z12米和东端X264不变。"
for ob in list(COL["bridge"].objects):
    if ob.type=="MESH" and (ob.name.startswith(("侧桥拱形","桥台_实体","东侧桥_连续","东侧观景台_"))):
        assign_material(ob,"frame" if "桥面" in ob.name or "观景台" in ob.name else "stone")
for sign in (-1,1):
    cube(f"东桥外侧压顶承托_{sign}",(207.4,178+sign*6.44,11.70),(113.2,.88,.60),"stone","frame",.025)
    points=[]
    for i in range(49):
        t=i/48
        points.append((150+114*t,178+sign*6.025,-40+45*math.sin(math.pi*t)**.65+.34))
    sweep(f"东桥拱券外缘素线_{sign}",points,.26,.62,"stone","frame",.02)
    stone_railing(f"东桥西口渐开石栏_{sign}",(146,178+sign*6.90,12),(150,178+sign*6.44,12),1.6,6)
for x in (150,264):
    cube(f"东桥桥台承托帽_{x}",(x,178,8.95),(12.8,16.6,1.5),"stone","frame",.06)
    cube(f"东桥桥台束腰线_{x}",(x,178,7.66),(12.4,16.3,.4),"stone","frame",.04)
stone_railing("观景台北缘补全",(264.5,214.5,12),(335.23,214.5,12),1.5,6)
stone_railing("观景台西南缘补全",(264.5,141.77,12),(264.5,171.10,12),1.5,6)
stone_railing("观景台西北缘补全",(264.5,184.90,12),(264.5,214.5,12),1.5,6)
for sign in (-1,1):
    cube(f"观景平台纵向边檐_{sign}",(300+sign*35.7,178,11.52),(.6,74,.65),"stone","frame",.03)
    cube(f"观景平台横向边檐_{sign}",(300,178+sign*36.7,11.52),(72,.6,.65),"stone","frame",.03)


# 参数、重建脚本和阶段入口同时内嵌，旧版入口只保留为历史资料。
# 外部重建和工程内重建都先重新读取 V5，因此重复执行不会叠加对象。
def text_block(name,body):
    block=bpy.data.texts.get(name) or bpy.data.texts.new(name)
    block.clear()
    block.write(body)


text_block("07_v06建筑参数.json",json.dumps(P,ensure_ascii=False,indent=2))
text_block("08_v06建筑重建.py",script_body)
entry_script='# 当前阶段以已验收 V5 文件为唯一基准，保留主殿、月门和四机位。\n# 修改07_v06建筑参数.json后运行本入口；再次执行也不会叠加结构。\nimport bpy\nexec(compile(bpy.data.texts["08_v06建筑重建.py"].as_string(),"内嵌V06建筑重建","exec"),{"__name__":"__main__"})\n'
text_block("02_当前阶段重建入口.py",entry_script)
if (ROOT/"design_parameters.json").exists():
    text_block("01_设计参数.json",(ROOT/"design_parameters.json").read_text(encoding="utf-8"))
if (OUT/"v06验收说明.md").exists():
    text_block("00_v06验收说明.md",(OUT/"v06验收说明.md").read_text(encoding="utf-8"))
control=next(iter(COL["control"].objects))
control["参数编辑说明"]="当前 V06：修改07_v06建筑参数.json后运行02_当前阶段重建入口.py；始终读取已验收V5文件。"
control["v06_基准SHA256"]=source_hash
control["v06_原平台标高"]= [0.0,12.0,24.0,36.0]
SCENE["阶段"]="V06 全场建筑结构统一；完成后停止等待验收"
SCENE["V06基准文件"]=str(source_path)
SCENE["V06基准SHA256"]=source_hash
SCENE["V06重建入口"]="02_当前阶段重建入口.py；外部 scripts/build_architecture_v06.py"
SCENE["V06范围"]="入口、回廊、七亭与石构；主殿月门及自然环境原样保留"
SCENE["V06连接做法"]="入口与角亭、角亭与回廊采用高低檐泛水；桥面与台面原标高连续"
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
SCENE.frame_end=max(p["frame"] for p in P["detail_cameras"])
SCENE.render.engine="CYCLES"
SCENE.cycles.device="CPU"
SCENE.cycles.samples=P["render_samples"]
SCENE.cycles.adaptive_threshold=.04
SCENE.cycles.use_denoising=True
SCENE.render.resolution_x=P["render_width"]
SCENE.render.resolution_y=P["render_height"]
SCENE.render.resolution_percentage=100
SCENE.render.image_settings.file_format="PNG"
SCENE.render.threads_mode="FIXED"
SCENE.render.threads=P["render_threads"]
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
bpy.context.view_layer.update()
destination=OUT/"qa"/"v06_working.blend" if "--preview" in ARGS else ROOT/P["output_file"]
bpy.ops.wm.save_as_mainfile(filepath=str(destination),compress=True)
summary={"file":str(destination),"baseline_sha256":source_hash,"objects":len(SCENE.objects),
         "removed_secondary_objects":REMOVED,"roofs":ROOFS,"joints":JOINTS,
         "modules":MODULE_USES,"collections":{col.name:len(col.all_objects) for col in SCENE.collection.children}}
(OUT/"qa"/"build_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
print("V06_SAVED",str(destination),"OBJECTS",len(SCENE.objects),flush=True)
if "--preview" in ARGS or "--render" in ARGS:
    frames=[int(v) for v in ARGS[ARGS.index("--frames")+1].split(",")] if "--frames" in ARGS else [1,2,3,4,7,8,9,10,11]
    if "--preview" in ARGS:
        SCENE.cycles.samples=12
        SCENE.render.resolution_percentage=60
    names={1:"01_oblique",2:"02_front",3:"03_aerial",4:"04_interior",5:"05_roof_detail",6:"06_moon_detail"}
    names.update({p["frame"]:p["output"] for p in P["detail_cameras"]})
    for frame_number in frames:
        SCENE.frame_set(frame_number)
        SCENE.camera=next(m.camera for m in SCENE.timeline_markers if m.frame==frame_number)
        SCENE.render.filepath=str(OUT/("qa" if "--preview" in ARGS else "renders")/(names[frame_number]+".png"))
        bpy.ops.render.render(write_still=True)
        print("V06_RENDER",frame_number,SCENE.render.filepath,flush=True)
print("V06_COMPLETE",flush=True)
