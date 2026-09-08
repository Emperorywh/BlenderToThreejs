"""
以已验收 V4 工程为唯一基准细化主殿与月门，独立保存 V5。
保留其余集合、巨柱柱身及四个相机；不重新生成 V3 布局。
主尺寸集中在 V5 参数中，重复构件共享网格，新增构件使用简体中文名称。
"""
import bpy
import bmesh
import json
import math
import sys
import hashlib
from pathlib import Path
from mathutils import Vector


# 外部脚本和工程内嵌脚本共用同一入口，重建始终先读取磁盘 V4。
# 参数可从旁存文件或工程文本读取；源文件摘要不符时停止，防止基准被误换。
script_path=Path(__file__).resolve() if "__file__" in globals() and Path(__file__).is_file() else None
ROOT=script_path.parents[1] if script_path else Path(bpy.data.filepath).parent
if ROOT.name=="qa":
    ROOT=ROOT.parent.parent
OUT=ROOT/"v05"
for directory in (OUT,OUT/"qa",OUT/"renders"):
    directory.mkdir(parents=True,exist_ok=True)
param_path=OUT/"design_parameters_v05.json"
# 工程内运行优先采用内嵌参数，外部运行优先采用旁存参数。
# 两种入口共享相同校验，避免用户在工程中调整参数却被磁盘旧值覆盖。
if script_path is None and bpy.data.texts.get("05_v05结构参数.json"):
    P=json.loads(bpy.data.texts["05_v05结构参数.json"].as_string())
else:
    P=json.loads(param_path.read_text(encoding="utf-8")) if param_path.exists() else json.loads(bpy.data.texts["05_v05结构参数.json"].as_string())
ARGS=sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
source_path=ROOT/P["baseline_file"]
source_hash=hashlib.sha256(source_path.read_bytes()).hexdigest()
if source_hash!=P["baseline_sha256"]:
    raise RuntimeError("V4 源文件摘要与验收基准不同，请先核对源文件。")
script_body=script_path.read_text(encoding="utf-8") if script_path else bpy.data.texts["06_v05结构重建.py"].as_string()
bpy.ops.wm.open_mainfile(filepath=str(source_path))
SCENE=bpy.context.scene
SCENE.name="天宫_结构v05_主殿与月门样板"
COL={}
for key,prefix in [("control","00_"),("hall","03_"),("roof","04_"),("moon","05A_"),("camera","12_")]:
    COL[key]=next(c for c in SCENE.collection.children if c.name.startswith(prefix))
COL["roof"].name="04_主殿重檐_结构v05"
COL["moon"].name="05A_主殿月门_结构v05"
for key,label,parent in [("column","03A_柱础与柱头","hall"),("beam","03B_额枋与天花","hall"),
                         ("bracket","03C_简化斗拱_共享网格","hall"),("support","04A_重檐承托与檩架","roof"),
                         ("lower","04B_下檐曲面与椽架","roof"),("upper","04C_上屋面与屋脊","roof")]:
    col=bpy.data.collections.new(label)
    COL[parent].children.link(col)
    COL[key]=col


# 材质全部为单色高粗糙度，只作用于本轮主殿和月门。
# 不修改 V4 共用材质的数据，避免其他建筑跟着变色。
def material(name,color):
    data=bpy.data.materials.new(name)
    data.diffuse_color=(*color,1)
    data.use_nodes=True
    bsdf=data.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value=(*color,1)
    bsdf.inputs["Roughness"].default_value=.88
    return data


MAT={"stone":material("V05_石构_暖灰哑光",(.63,.60,.54)),
     "frame":material("V05_门圈柱础_浅石哑光",(.79,.76,.68)),
     "wood":material("V05_木构_沉棕哑光",(.26,.16,.095)),
     "edge":material("V05_承托与边线_浅棕哑光",(.43,.30,.17)),
     "panel":material("V05_天花板_灰棕哑光",(.38,.31,.23)),
     "roof":material("V05_屋面_青灰哑光",(.19,.235,.25)),
     "ridge":material("V05_脊与檐边_灰褐哑光",(.47,.43,.34)),
     "joint":material("V05_门圈分段_微差石色",(.75,.72,.65))}
CACHE={}
MODULE_USES={}


# 网格生成工具只在 V5 新集合中创建对象；缓存键包含材质及实际尺寸。
# 小倒角保留构件厚度，关闭无关角面的平滑，避免木枋出现鼓包阴影。
def mesh(name,verts,faces,group,mat="wood",smooth=False,key=None,bevel=0):
    cache_key=(key,mat) if key else None
    if cache_key and cache_key in CACHE:
        data=CACHE[cache_key]
    else:
        data=bpy.data.meshes.new(name+"_网格")
        data.from_pydata(verts,[],faces)
        data.update()
        bm=bmesh.new()
        bm.from_mesh(data)
        bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=.00005)
        bmesh.ops.dissolve_degenerate(bm,edges=list(bm.edges),dist=.00002)
        bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces))
        bm.to_mesh(data)
        bm.free()
        data.materials.append(MAT[mat])
        for face in data.polygons:
            face.use_smooth=smooth
        if cache_key:
            CACHE[cache_key]=data
    ob=bpy.data.objects.new(name,data)
    COL[group].objects.link(ob)
    ob["阶段"]="V05 主殿与月门结构样板"
    if key:
        ob["共享模块"]=str(key)
        MODULE_USES[str(key)]=MODULE_USES.get(str(key),0)+1
    if bevel:
        mod=ob.modifiers.new("构件棱边_小倒角","BEVEL")
        mod.width=bevel
        mod.segments=2
    return ob


def box_geometry(loc,dims,verts,faces):
    x,y,z=loc
    w,d,h=[v/2 for v in dims]
    offset=len(verts)
    verts.extend([(x-w,y-d,z-h),(x+w,y-d,z-h),(x+w,y+d,z-h),(x-w,y+d,z-h),
                  (x-w,y-d,z+h),(x+w,y-d,z+h),(x+w,y+d,z+h),(x-w,y+d,z+h)])
    faces.extend(tuple(offset+i for i in face) for face in [(0,3,2,1),(4,5,6,7),(0,1,5,4),
                                                           (1,2,6,5),(2,3,7,6),(3,0,4,7)])


def cube(name,loc,dims,group,mat="wood",bevel=.06):
    verts,faces=[],[]
    box_geometry((0,0,0),dims,verts,faces)
    ob=mesh(name,verts,faces,group,mat,key=("方材",tuple(round(v,4) for v in dims)),bevel=bevel)
    ob.location=loc
    return ob


def sweep(name,points,width,height,group,mat="wood",bevel=0,key=None):
    verts,faces=[],[]
    points=[Vector(p) for p in points]
    for i,p in enumerate(points):
        tangent=points[min(i+1,len(points)-1)]-points[max(i-1,0)]
        lateral=Vector((-tangent.y,tangent.x,0)).normalized()*width/2
        verts.extend([p-lateral+Vector((0,0,-height/2)),p+lateral+Vector((0,0,-height/2)),
                      p+lateral+Vector((0,0,height/2)),p-lateral+Vector((0,0,height/2))])
    for i in range(len(points)-1):
        a=i*4
        faces.extend((a+j,a+(j+1)%4,a+(j+1)%4+4,a+j+4) for j in range(4))
    faces.extend([(3,2,1,0),tuple((len(points)-1)*4+j for j in range(4))])
    return mesh(name,verts,faces,group,mat,key=key,bevel=bevel)


def lathe(name,profile,loc,mat,key):
    verts,faces=[],[]
    count=64
    for z,r in profile:
        verts.extend((r*math.cos(i*math.tau/count),r*math.sin(i*math.tau/count),z) for i in range(count))
    for j in range(len(profile)-1):
        faces.extend((j*count+i,j*count+(i+1)%count,(j+1)*count+(i+1)%count,(j+1)*count+i) for i in range(count))
    faces.extend([tuple(reversed(range(count))),tuple((len(profile)-1)*count+i for i in range(count))])
    ob=mesh(name,verts,faces,"column",mat,smooth=True,key=key)
    ob.location=loc
    for face in ob.data.polygons:
        if abs(face.normal.z)>.99:
            face.use_smooth=False
    return ob


def remove(objects):
    for ob in list(objects):
        bpy.data.objects.remove(ob,do_unlink=True)


# 柱身沿用 V4 原网格和世界变换，柱础与柱头在原有高度区间内细化。
# 主梁保留尺寸与位置，增加哑光木色及少量收边，以明确承托和跨越方向。
shafts=[ob for ob in COL["hall"].objects if ob.name.endswith("_柱身")]
remove(ob for ob in COL["hall"].objects if ob.name.endswith(("_柱础","_柱头")) or ob.name.startswith(("檐下整块承托_","檐下外挑枋_","殿顶平整天花占位")))
for shaft in shafts:
    x,y=shaft.location.x,shaft.location.y
    label=shaft.name.removesuffix("_柱身")
    cube(label+"_方形础座",(x,y,36.18),(9.216,9.216,.36),"column","stone",.09)
    lathe(label+"_覆盆柱础",[(.34,4.45),(.55,4.45),(.7,4.15),(1.15,3.82),(1.5,3.73),(1.6,3.73)],
          (x,y,36),"frame","覆盆柱础_统一7点2米巨柱")
    lathe(label+"_柱脚束口",[(0,3.73),(.2,3.73),(.36,3.60)],(x,y,37.6),"stone","柱脚束口")
    lathe(label+"_承梁柱头",[(0,3.32),(.25,3.48),(.4,3.83),(.7,3.83),(1.16,4.32),(1.6,4.32)],
          (x,y,80.4),"frame","承梁柱头_标高82米")
for ob in list(COL["hall"].objects):
    if ob.name.startswith(("主殿横向主梁_","主殿纵向主梁_","殿顶次梁_")):
        ob.data=ob.data.copy()
        ob.data.materials.clear()
        ob.data.materials.append(MAT["wood"])
        mod=ob.modifiers.new("主梁棱线_小倒角","BEVEL")
        mod.width=.06
        mod.segments=2


# 横向额枋、柱间花板及浅凹天花按柱网分格，中央六十米跨内不添落地柱。
# 天花只做建筑分层与边界，保持原有开阔净空，不加入复杂藻井或雕刻。
hy=P["hall_center_y"]
for y in P["column_y"]:
    for sy in (-1,1):
        for z in (82.28,86.35):
            cube(f"V05_主梁边线_Y{y:.2f}_{sy}_{z}",(0,y+sy*3.19,z),(187,.22,.24),"beam","edge",.035)
for x in P["column_x"]:
    for sx in (-1,1):
        cube(f"V05_纵枋边线_{x}_{sx}",(x+sx*2.88,hy,82.5),(.2,106,.26),"beam","edge",.035)
for y in (245,345):
    for a,b in zip(P["column_x"][:-1],P["column_x"][1:]):
        if a<0<b and y==245:
            continue
        cube(f"V05_柱间额枋_{y}_{a}",((a+b)/2,y,79.7),(b-a-5.4,1.5,1.55),"beam","wood")
        cube(f"V05_额枋素面芯板_{y}_{a}",((a+b)/2,y-.82,79.72),(b-a-7.3,.15,.72),"beam","edge",.025)
for i,(a,b) in enumerate(zip(P["column_x"][:-1],P["column_x"][1:])):
    for j,(c,d) in enumerate(zip(P["column_y"][:-1],P["column_y"][1:])):
        cx,cy=(a+b)/2,(c+d)/2
        w,depth=b-a-4.8,d-c-5.4
        cube(f"V05_天花浅凹板_{i+1}_{j+1}",(cx,cy,87.25),(w,depth,.55),"beam","panel",.035)
        for sy in (-1,1):
            cube(f"V05_天花边框横_{i}_{j}_{sy}",(cx,cy+sy*(depth/2-.5),86.62),(w,1,.75),"beam","edge")
        for sx in (-1,1):
            cube(f"V05_天花边框纵_{i}_{j}_{sx}",(cx+sx*(w/2-.5),cy,86.62),(1,depth,.75),"beam","edge")
cube("V05_天花上承板",(0,hy,87.65),(184,104,.35),"support","wood",0)


# 曲面按连续等高圈放样，角部起翘沿两侧分散，不采用集中竖起的尖檐边。
# 上屋面收至长脊，下檐保留中央孔洞，两层之间由真实的短柱和檩架承托。
remove(COL["roof"].objects)
def surface(level,side,s,u):
    if level=="lower":
        w=P["lower_inner_width"]+(P["lower_width"]-P["lower_inner_width"])*u
        d=P["lower_inner_depth"]+(P["lower_depth"]-P["lower_inner_depth"])*u
        base=P["lower_eave_z"]-P["lower_toe_lift"]
        z=base+(P["lower_inner_z"]-base)*(1-u)**P["lower_curve_power"]+P["lower_toe_lift"]*u**8
        z+=P["lower_corner_lift"]*abs(s)**4*u**2.5
    else:
        w=P["upper_ridge_length"]+(P["upper_width"]-P["upper_ridge_length"])*u
        d=P["upper_depth"]*u
        base=P["upper_eave_z"]-P["upper_toe_lift"]
        z=base+(P["upper_ridge_z"]-base)*(1-u)**P["upper_curve_power"]+P["upper_toe_lift"]*u**8
        z+=P["upper_corner_lift"]*abs(s)**4*u**3
    xy=[(s*w/2,-d/2),(w/2,s*d/2),(-s*w/2,d/2),(-w/2,-s*d/2)][side]
    return Vector((xy[0],hy+xy[1],z))


def roof_shell(level):
    verts,faces=[],[]
    segments=48
    rings=32
    thickness=P[level+"_shell_thickness"]
    count=segments*4
    for underside in (0,1):
        for j in range(rings+1):
            u=j/rings
            for side in range(4):
                for i in range(segments):
                    p=surface(level,side,-1+2*i/segments,u)
                    verts.append(p-Vector((0,0,underside*thickness)))
    layer=(rings+1)*count
    for j in range(rings):
        for i in range(count):
            a=j*count+i
            b=j*count+(i+1)%count
            faces.extend([(a,b,b+count,a+count),(a+count+layer,b+count+layer,b+layer,a+layer)])
    # 上屋面内圈收束为一条屋脊，不再生成内部封口以免形成重复面。
    # 下檐内圈保持真实环孔，因此内外两条边界都要封闭厚度。
    for j in ((0,rings) if level=="lower" else (rings,)):
        for i in range(count):
            a=j*count+i
            b=j*count+(i+1)%count
            faces.append((a,b,b+layer,a+layer))
    ob=mesh("V05_"+("下檐_环形连续曲面" if level=="lower" else "上屋面_舒展四坡"),verts,faces,level,"roof",smooth=True)
    ob.data.materials.append(MAT["wood"])
    for f in ob.data.polygons:
        if f.normal.z<-.15:
            f.material_index=1
        if abs(f.normal.z)<.2:
            f.use_smooth=False
    ob["屋面实体厚度_米"]=thickness
    for side in range(4):
        edge=[surface(level,side,-1+2*i/96,1)-Vector((0,0,thickness*.45)) for i in range(97)]
        sweep(f"V05_{level}_薄檐口_{side}",edge,P["fascia_width"],P["fascia_height"],level,"ridge")
        timber=[p-Vector((0,0,.53)) for p in edge]
        sweep(f"V05_{level}_连檐木_{side}",timber,.42,.4,level,"edge")
        for index,u in enumerate((.2,.62,.91) if level=="lower" else (.54,.79,.94)):
            pts=[surface(level,side,-1+2*i/48,u)-Vector((0,0,thickness+.65)) for i in range(49)]
            sweep(f"V05_{level}_曲线檩条_{side}_{index}",pts,.72,.58,level,"wood")
        count_rafter=48 if side%2==0 else 30
        for i in range(count_rafter):
            s=-1+2*(i+.5)/count_rafter
            start=0 if level=="lower" else .38
            pts=[surface(level,side,s,start+(1-start)*j/16)-Vector((0,0,thickness+.22)) for j in range(17)]
            sweep(f"V05_{level}_承檐椽_{side}_{i+1:02}",pts,P["rafter_width"],P["rafter_height"],level,"edge")
    return ob


roof_shell("lower")
roof_shell("upper")
for side in range(4):
    for level in ("upper","lower"):
        start=.015 if level=="upper" else 0
        pts=[surface(level,side,1,start+(1-start)*i/48)+Vector((0,0,.12)) for i in range(49)]
        sweep(f"V05_{level}_角脊_{side}",pts,.78,.45,level,"ridge")
ridge=[(x,hy,P["upper_ridge_z"]+.3+.16*(abs(x)/64)**8) for x in [-64+128*i/96 for i in range(97)]]
sweep("V05_正脊_素面收头",ridge,1.25,.75,"upper","ridge")


# 一攒斗拱由交替出跳拱、承斗和上承枋组成，统一为一个共享网格。
# 位置依附原柱网与主梁，檐柱处和补间处共用模块，不增加地面支柱。
def bracket_mesh():
    verts,faces=[],[]
    box_geometry((0,0,.28),(3.0,3.0,.56),verts,faces)
    box_geometry((0,0,.69),(3.7,3.3,.32),verts,faces)
    for axis,length,z in [(0,7.6,1.10),(1,8.6,1.93),(0,10.8,2.7)]:
        profile=[(-length/2,z-.08),(-length*.35,z-.31),(-length*.16,z-.48),
                 (length*.16,z-.48),(length*.35,z-.31),(length/2,z-.08),
                 (length/2,z+.47),(-length/2,z+.47)]
        off=len(verts)
        for y in (-.69,.69):
            for x,zz in profile:
                verts.append((x,y,zz) if axis==0 else (y,x,zz))
        n=len(profile)
        faces.extend([tuple(off+i for i in reversed(range(n))),tuple(off+n+i for i in range(n))])
        faces.extend((off+i,off+(i+1)%n,off+(i+1)%n+n,off+i+n) for i in range(n))
        if axis<2 and z<2.5:
            for sign in (-1,1):
                p=(sign*length*.36,0,z+.65) if axis==0 else (0,sign*length*.36,z+.65)
                box_geometry(p,(1.8,1.8,.5),verts,faces)
    box_geometry((0,0,3.16),(11.4,2.1,.28),verts,faces)
    return verts,faces


verts,faces=bracket_mesh()
bracket_positions=[]
for side in (-1,1):
    for x in P["bracket_front_x"]:
        bracket_positions.append((x,hy+side*50,0))
    for y in (261.667,278.333333,295,311.666667,328.333):
        bracket_positions.append((side*90,y,math.pi/2))
for i,(x,y,angle) in enumerate(bracket_positions):
    ob=mesh(f"V05_下檐斗拱_{i+1:02}",verts,faces,"bracket","edge",key="三层简化斗拱_共享标准攒",bevel=.045)
    ob.location=(x,y,P["bracket_base_z"])
    ob.rotation_euler.z=angle


# 重檐承托层改为上下环枋、短柱和内收木壁，取代原来的整块实心盒子。
# 墙内的承梁与短柱从天花上承板起步，向上接触屋面，不留下悬空的上屋顶。
fw,fd=P["upper_frame_half_width"],P["upper_frame_half_depth"]
def upper_height(x,y):
    ux=max(0,(abs(x)-P["upper_ridge_length"]/2)/((P["upper_width"]-P["upper_ridge_length"])/2))
    uy=abs(y)/(P["upper_depth"]/2)
    u=max(ux,uy)
    if uy>=ux:
        s=x/(P["upper_ridge_length"]/2+(P["upper_width"]-P["upper_ridge_length"])/2*u)
        return surface("upper",0,s,u).z
    s=y/(P["upper_depth"]/2*u)
    return surface("upper",1,s,u).z


# 承斗的上表面按屋面底面逐角点贴合，斜坡上不使用会冒出屋面的水平方块。
# 下表面保持水平供短柱承接，返回接触标高用于生成下方短柱。
def roof_seat(name,x,y,width,depth):
    corners=[(x-width/2,y-depth/2),(x+width/2,y-depth/2),(x+width/2,y+depth/2),(x-width/2,y+depth/2)]
    heights=[upper_height(px,py)-P["upper_shell_thickness"] for px,py in corners]
    base=min(heights)-.7
    verts=[(px,hy+py,base) for px,py in corners]+[(px,hy+py,z) for (px,py),z in zip(corners,heights)]
    faces=[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
    mesh(name,verts,faces,"support","edge",bevel=.025)
    return base


for side in (-1,1):
    for z,h in [(88.6,1.55),(94.5,1.0)]:
        cube(f"V05_上层环枋横_{side}_{z}",(0,hy+side*fd,z),(2*fw+3,2.4,h),"support","wood")
        cube(f"V05_上层环枋纵_{side}_{z}",(side*fw,hy,z),(2.4,2*fd+3,h),"support","wood")
    # 上层檩口随屋面实际曲率抬升，侧面及角部不靠统一高度的短柱硬接。
    # 每根短柱与承斗以同一点的屋面底高为终点，消除坡下可见悬空。
    top_x=[(x,hy+side*fd,upper_height(x,side*fd)-1.18) for x in [-fw+2*fw*i/64 for i in range(65)]]
    top_y=[(side*fw,hy+y,upper_height(side*fw,y)-1.18) for y in [-fd+2*fd*i/64 for i in range(65)]]
    sweep(f"V05_随坡上承枋横_{side}",top_x,2.4,.75,"support","wood")
    sweep(f"V05_随坡上承枋纵_{side}",top_y,2.4,.75,"support","wood")
    cube(f"V05_重檐木壁横_{side}",(0,hy+side*fd,92.15),(2*fw,1.3,5.7),"support","panel")
    cube(f"V05_重檐木壁纵_{side}",(side*fw,hy,92.15),(1.3,2*fd,5.7),"support","panel")
    for x in (-75,-60,-45,-30,-15,0,15,30,45,60,75):
        top=roof_seat(f"V05_上层托斗横_{side}_{x}",x,side*fd,3.7,3.1)+.05
        cube(f"V05_上层短柱横_{side}_{x}",(x,hy+side*fd,(88.5+top)/2),(1.8,2,top-88.5),"support","wood")
    for y in (-33,-16.5,0,16.5,33):
        top=roof_seat(f"V05_上层托斗纵_{side}_{y}",side*fw,y,3.1,3.7)+.05
        cube(f"V05_上层短柱纵_{side}_{y}",(side*fw,hy+y,(88.5+top)/2),(2,1.8,top-88.5),"support","wood")
    cube(f"V05_内转承梁横_{side}",(0,hy+side*fd,88.05),(2*fw+4,4,.55),"support","wood")
for x in (-60,-30,30,60):
    cube(f"V05_屋架底梁_{x}",(x,hy,95.2),(2.3,89,1.4),"support","wood")
    for y in (-25,0,25):
        roof_z=surface("upper",0,0,abs(y)/62).z-.8
        base=95.9
        cube(f"V05_屋架瓜柱_{x}_{y}",(x,hy+y,(base+roof_z)/2),(2.1,2.1,roof_z-base),"support","wood")
for y in (-25,0,25):
    roof_z=surface("upper",0,0,abs(y)/62).z-.78
    cube(f"V05_上屋面主檩_Y{y}",(0,hy+y,roof_z-.45),(122 if y==0 else 128,1.65,.9),"support","wood")


# 月门墙体向两侧柱头接合，圆形净口半径恒为二十二米。
# 门圈断面只向孔外扩展，底部逐圈裁到三十六米，不添加跨通道门槛。
remove(ob for ob in COL["moon"].objects if ob.name.startswith("主殿月门_"))
my=P["moon_plane_y"]
mz=P["moon_floor_z"]
cz=mz+P["moon_center_above_floor"]
radius=P["moon_diameter"]/2
outer=P["moon_frame_outer_radius"]
def cut_circle(ob,cut_radius):
    bpy.ops.mesh.primitive_cylinder_add(vertices=P["moon_segments"],radius=cut_radius,depth=16,location=(0,my,cz),rotation=(math.pi/2,0,0))
    cutter=bpy.context.object
    cutter.name="V05_临时孔洞切刀"
    bpy.context.view_layer.objects.active=ob
    mod=ob.modifiers.new("门圈外缘_实际贯通孔","BOOLEAN")
    mod.operation="DIFFERENCE"
    mod.solver="EXACT"
    mod.object=cutter
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(cutter,do_unlink=True)


wall=cube("V05_月门厚墙_两端入柱",(0,my,59),(60,P["moon_wall_thickness"],46),"moon","stone",0)
cut_circle(wall,outer-.015)
profile=[(22,-2.4),(22.08,-2.80),(22.4,-3.0),(22.65,-3.0),(22.8,-2.89),
         (23.75,-2.89),(24.0,-2.78),(24.2,-2.50),(24.35,-2.4),
         (24.35,2.4),(24.2,2.50),(24.0,2.78),(23.75,2.89),(22.8,2.89),
         (22.65,3.0),(22.4,3.0),(22.08,2.8),(22,2.4)]
verts,faces=[],[]
segments=P["moon_segments"]
for i in range(segments+1):
    t=i/segments
    for r,dy in profile:
        start=math.asin(-P["moon_center_above_floor"]/r)
        angle=start+(math.pi-2*start)*t
        verts.append((r*math.cos(angle),my+dy,cz+r*math.sin(angle)))
n=len(profile)
for i in range(segments):
    faces.extend((i*n+j,i*n+(j+1)%n,(i+1)*n+(j+1)%n,(i+1)*n+j) for j in range(n))
faces.extend([tuple(reversed(range(n))),tuple(segments*n+j for j in range(n))])
frame=mesh("V05_月门通厚石圈_净径44米",verts,faces,"moon","frame",smooth=True)
frame.data.materials.append(MAT["joint"])
frame.data.update()
for face in frame.data.polygons:
    if abs(face.normal.z)>.999:
        face.use_smooth=False
    if abs(face.normal.y)>.85:
        angle=math.atan2(face.center.z-cz,face.center.x)
        face.material_index=1 if int((angle+math.pi)*9/math.pi)%2 else 0
# 门圈沿圆周保持平滑，断面各道退台保留清楚棱线。
# 采用分裂法线而不拆断网格，使石圈仍是可编辑的闭合实体。
loop_normals=[None]*len(frame.data.loops)
for face in frame.data.polygons:
    center_radial=Vector((face.center.x,0,face.center.z-cz)).normalized()
    radial_component=face.normal.dot(center_radial)
    for loop_index in face.loop_indices:
        co=frame.data.vertices[frame.data.loops[loop_index].vertex_index].co
        radial=Vector((co.x,0,co.z-cz)).normalized()
        normal=radial*radial_component+Vector((0,face.normal.y,0))
        loop_normals[loop_index]=tuple(face.normal if abs(face.normal.z)>.999 else normal.normalized())
frame.data.normals_split_custom_set(loop_normals)
frame["净开口直径_米"]=44.0
frame["完成面标高_米"]=36.0
frame["落地净宽_米"]=2*math.sqrt(radius**2-P["moon_center_above_floor"]**2)
for z,h,depth in [(36.25,.5,5.55),(36.85,.7,5.2)]:
    plinth=cube(f"V05_月门墙脚_不跨通道_{z}",(0,my,z),(60,depth,h),"moon","frame",0)
    cut_circle(plinth,outer-.01)
for side in (-1,1):
    cube(f"V05_月门抱柱壁柱_{side}",(side*26.65,my,58.9),(1.65,6.15,45.8),"moon","frame",.06)
    cube(f"V05_月门壁柱脚座_{side}",(side*26.65,my,36.55),(2.1,6.6,1.1),"moon","stone",.06)
    cube(f"V05_月门柱头衔接石_{side}",(side*26.65,my,81.1),(3.5,6.5,1.8),"moon","frame",.055)
cube("V05_月门上额枋_接前檐主梁",(0,my,81.35),(53.3,5.0,1.3),"moon","wood",.05)
for side in (-1,1):
    cube(f"V05_月门额枋收边_{side}",(0,my+side*2.55,81.1),(52.9,.2,.26),"moon","edge",.025)


# 原四机位的数据、位置、焦段、朝向和时间线绑定保持原样。
# 新增第五第六帧用于檐下和月门衔接，验收时可按帧切换同一套几何。
def add_camera(name,loc,target,lens,frame_number):
    data=bpy.data.cameras.new(name)
    ob=bpy.data.objects.new(name,data)
    COL["camera"].objects.link(ob)
    ob.location=loc
    ob.rotation_euler=(Vector(target)-Vector(loc)).to_track_quat("-Z","Y").to_euler()
    data.lens=lens
    data.clip_start=.08
    data.clip_end=10000
    data.passepartout_alpha=1
    marker=SCENE.timeline_markers.new(name,frame=frame_number)
    marker.camera=ob
    return ob


add_camera("CAM_05_屋顶檐下_结构衔接",P["closeup_roof_location"],P["closeup_roof_target"],P["closeup_roof_lens"],5)
add_camera("CAM_06_月门衔接_石圈与柱梁",P["closeup_moon_location"],P["closeup_moon_target"],P["closeup_moon_lens"],6)
SCENE.frame_end=6
SCENE["阶段"]="V05 主殿与月门结构样板；停止等待验收"
SCENE["V05基准文件"]=str(source_path)
SCENE["V05基准SHA256"]=source_hash
SCENE["V05重建入口"]="06_v05结构重建.py；外部 scripts/build_structure_v05.py；只读取 V4 基准"
SCENE["交付机位"]="第1至4帧保留V4验收机位；第5帧屋顶檐下；第6帧月门衔接"
SCENE["V05范围"]="主殿巨柱柱身保持；细化柱础柱头、梁枋、简化斗拱、重檐、月门；其余场景沿用V4"
control=next(iter(COL["control"].objects))
for key,value in P.items():
    control["v05_"+key]=value
control["参数编辑说明"]="当前阶段 V05：修改05_v05结构参数.json后运行06_v05结构重建.py；始终从V4文件重建。"
for name,body in [("05_v05结构参数.json",json.dumps(P,ensure_ascii=False,indent=2)),("06_v05结构重建.py",script_body)]:
    block=bpy.data.texts.get(name) or bpy.data.texts.new(name)
    block.clear()
    block.write(body)
# 当前说明和入口参数随工程保存，历史脚本仅保存在归档文本中。
# 文件即使移到离线环境也能看到阶段边界、尺寸及 V4 源文件要求。
for name,path in [("00_v05验收说明.md",OUT/"v05验收说明.md"),("01_设计参数.json",ROOT/"design_parameters.json")]:
    if path.exists():
        block=bpy.data.texts.get(name) or bpy.data.texts.new(name)
        block.clear()
        block.write(path.read_text(encoding="utf-8"))
for legacy_name in ("00_v04验收说明.md","02_重建白模.py","04_v04修订脚本.py"):
    legacy=bpy.data.texts.get(legacy_name)
    if legacy:
        legacy.name="归档_"+legacy_name
entry=bpy.data.texts.new("02_当前阶段重建入口.py")
entry.write('# 当前交付以 V4 为唯一基准，防止误运行旧版退回 V3 布局。\n# 修改 V5 参数后，可直接在此文本点击运行脚本。\nimport bpy\nexec(compile(bpy.data.texts["06_v05结构重建.py"].as_string(),"内嵌V05结构重建","exec"),{"__name__":"__main__"})\n')
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
SCENE.render.threads=16
bpy.ops.object.select_all(action="DESELECT")
SCENE.frame_set(4)
SCENE.camera=next(m.camera for m in SCENE.timeline_markers if m.frame==4)
for area in bpy.context.screen.areas:
    if area.type=="VIEW_3D":
        area.spaces.active.region_3d.view_perspective="CAMERA"
        area.spaces.active.shading.color_type="MATERIAL"
        area.spaces.active.overlay.show_extras=False
destination=OUT/"qa"/"v05_working.blend" if "--preview" in ARGS else ROOT/"HeavenlyPalace_Structure_v05.blend"
SCENE.render.filepath=str(OUT/"renders"/"04_interior.png")
bpy.ops.wm.save_as_mainfile(filepath=str(destination),compress=True)
summary={"file":str(destination),"baseline_sha256":source_hash,"objects":len(SCENE.objects),
         "preserved_column_shafts":len(shafts),"modules":MODULE_USES,
         "collections":{col.name:len(col.all_objects) for col in SCENE.collection.children}}
(OUT/"qa"/"build_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
print("V05_SAVED",str(destination),flush=True)
if "--preview" in ARGS or "--render" in ARGS:
    frames=[int(v) for v in ARGS[ARGS.index("--frames")+1].split(",")] if "--frames" in ARGS else [4,5,6,2,1,3]
    if "--preview" in ARGS:
        SCENE.cycles.samples=16
        SCENE.render.resolution_percentage=60
    names={1:"01_oblique",2:"02_front",3:"03_aerial",4:"04_interior",5:"05_roof_detail",6:"06_moon_detail"}
    for frame_number in frames:
        SCENE.frame_set(frame_number)
        SCENE.camera=next(m.camera for m in SCENE.timeline_markers if m.frame==frame_number)
        SCENE.render.filepath=str(OUT/("qa" if "--preview" in ARGS else "renders")/(names[frame_number]+".png"))
        bpy.ops.render.render(write_still=True)
        print("V05_RENDER",frame_number,SCENE.render.filepath,flush=True)
print("V05_COMPLETE",flush=True)
