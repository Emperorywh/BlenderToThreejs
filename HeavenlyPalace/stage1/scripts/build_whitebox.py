"""
天宫第一阶段白模：在 Blender 中生成真实可编辑网格与固定机位。
所有设计单位为米；参数来自同目录的参数文件或工程内嵌文本。
本脚本仅生成整体结构，不包含瓦片、雕刻、植被细节或复杂材质。
"""
import bpy
import math
import json
import random
import sys
from pathlib import Path
from mathutils import Vector


# 集中读取主要设计参数，并允许工程内部携带参数与重建脚本。
# 修改参数后重建会创建一个新场景，原有其他场景不会被删除。
ROOT = Path(__file__).resolve().parents[1] if "__file__" in globals() else Path(bpy.data.filepath).parent
ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
PARAM_PATH = ROOT / "design_parameters.json"
if PARAM_PATH.exists():
    P = json.loads(PARAM_PATH.read_text(encoding="utf-8"))
else:
    P = json.loads(bpy.data.texts["01_设计参数.json"].as_string())
# 当前工程已经进入 V5 结构阶段，旧命令入口同步转到 V4 基准上的结构重建。
# 历史白模文件与下方原生成逻辑保留，防止误执行旧入口退回 V3 的月门布局。
if P.get("active_stage") == "v05":
    import runpy
    runpy.run_path(str(ROOT / P["active_rebuild_script"]), run_name="__main__")
    raise SystemExit
rng = random.Random(P["random_seed"])
SCENE = bpy.data.scenes.new("天宫_阶段一_整体白模")
bpy.context.window.scene = SCENE
SCENE.unit_settings.system = "METRIC"
SCENE.unit_settings.scale_length = 1.0
SCENE.unit_settings.length_unit = "METERS"
SCENE["阶段"] = "第一阶段：整体白模；验收前停止细化"
SCENE["坐标约定"] = "X向东，Y向主殿；Z=0为前庭完成面；长度单位米"
COL = {}
for key, label in [
    ("control", "00_参数与设计说明"), ("mountain", "01_主山体与支撑岩台"),
    ("base", "02_分层台基与前庭"), ("hall", "03_主殿柱网与梁架"),
    ("roof", "04_主殿屋顶大形"), ("gate", "05_月门长廊"),
    ("corridor", "06_两侧回廊与角亭"), ("stairs", "07_中央台阶与通行"),
    ("bridge", "08_东侧桥与观景平台"), ("pine", "09_古松占位"),
    ("water", "10_瀑布占位"), ("human", "11_一点八米人形参照"),
    ("camera", "12_四个固定机位"), ("light", "13_中性照明"),
    ("guide", "14_尺寸辅助_不渲染")
]:
    col = bpy.data.collections.new(label)
    SCENE.collection.children.link(col)
    COL[key] = col
COL["guide"].hide_render = True


# 单色材质只区分屋顶、石材和自然占位，以便阅读体块关系。
# 所有表面保持哑光，不启用雾、发光后期或纹理贴图。
def material(name, color, roughness=0.85):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


MAT = {
    "stone": material("白模_暖灰石材", (0.67, 0.65, 0.61)),
    "trim": material("白模_浅色檐口柱身", (0.81, 0.79, 0.75)),
    "roof": material("白模_中灰屋顶", (0.43, 0.46, 0.47)),
    "rock": material("白模_山体占位", (0.36, 0.38, 0.38)),
    "pine": material("白模_树冠占位", (0.27, 0.31, 0.30)),
    "trunk": material("白模_树干占位", (0.36, 0.35, 0.32)),
    "water": material("白模_瀑布占位", (0.72, 0.79, 0.80)),
    "human": material("尺度参照_深灰", (0.055, 0.068, 0.073)),
    "joint": material("白模_地面分区", (0.50, 0.51, 0.50)),
}


# 基础网格使用真实尺寸创建，便于继续进入编辑模式修改。
# 不把整个天宫合并为单个不可分辨的网格。
def mesh(name, verts, faces, group, mat="stone", smooth=False):
    data = bpy.data.meshes.new(name + "_网格")
    data.from_pydata(verts, [], faces)
    data.update()
    obj = bpy.data.objects.new(name, data)
    COL[group].objects.link(obj)
    data.materials.append(MAT[mat])
    if smooth:
        for poly in data.polygons:
            poly.use_smooth = True
    return obj


def cube(name, loc, dims, group, mat="stone", bevel=0):
    w, d, h = (v * 0.5 for v in dims)
    verts = [(-w, -d, -h), (w, -d, -h), (w, d, -h), (-w, d, -h),
             (-w, -d, h), (w, -d, h), (w, d, h), (-w, d, h)]
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
             (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]
    obj = mesh(name, verts, faces, group, mat)
    obj.location = loc
    if bevel:
        mod = obj.modifiers.new("白模边缘_单段倒角", "BEVEL")
        mod.width = bevel
        mod.segments = 1
    return obj


def cylinder(name, loc, radius, depth, group, mat="trim", vertices=24, r_top=None):
    r_top = radius if r_top is None else r_top
    verts = [(r * math.cos(i * math.tau / vertices), r * math.sin(i * math.tau / vertices), z)
             for z, r in [(-depth / 2, radius), (depth / 2, r_top)] for i in range(vertices)]
    faces = [tuple(reversed(range(vertices))), tuple(range(vertices, 2 * vertices))]
    faces += [(i, (i + 1) % vertices, (i + 1) % vertices + vertices, i + vertices) for i in range(vertices)]
    obj = mesh(name, verts, faces, group, mat)
    obj.location = loc
    for face in obj.data.polygons[2:]:
        face.use_smooth = True
    return obj


def beam_between(name, a, b, width, group, mat="stone", depth=None):
    a, b = Vector(a), Vector(b)
    obj = cube(name, (a + b) / 2, (width, depth or width, (b - a).length), group, mat)
    obj.rotation_euler = (b - a).to_track_quat("Z", "Y").to_euler()
    return obj


def tube(name, points, radius, group, mat="trim", resolution=0):
    data = bpy.data.curves.new(name + "_路径", "CURVE")
    data.dimensions = "3D"
    data.resolution_u = 1
    data.bevel_depth = radius
    data.bevel_resolution = resolution
    data.use_fill_caps = True
    sp = data.splines.new("POLY")
    sp.points.add(len(points) - 1)
    for p, co in zip(sp.points, points):
        p.co = (*co, 1)
    obj = bpy.data.objects.new(name, data)
    COL[group].objects.link(obj)
    data.materials.append(MAT[mat])
    return obj


# 山体用多圈不规则截面表达自然崖壁；顶面覆盖承台投影。
# 垂直岩柱与后方山峰都是占位，不做岩石雕刻或纹理细分。
def rock_mass(name, center, rx, ry, z_bottom, z_top, seed, group="mountain", count=16):
    local_rng = random.Random(seed)
    factors = [local_rng.uniform(0.85, 1.12) for i in range(count)]
    verts = []
    rings = [(z_bottom, 0.63), (z_bottom + (z_top-z_bottom)*0.24, 0.94),
             (z_bottom + (z_top-z_bottom)*0.73, 1.0), (z_top-5, 0.86), (z_top, 0.80)]
    for ring_id, (z, scale) in enumerate(rings):
        for i in range(count):
            theta = i * math.tau / count
            wobble = local_rng.uniform(-3, 3) if ring_id not in (0, 4) else 0
            verts.append((center[0]+rx*math.cos(theta)*scale*factors[i],
                          center[1]+ry*math.sin(theta)*scale*factors[i], z+wobble))
    faces = [tuple(reversed(range(count)))]
    for j in range(len(rings)-1):
        for i in range(count):
            a, b = j*count+i, j*count+(i+1)%count
            if j in (1, 2) and i % 3 == 0:
                faces.extend([(a, b, b+count), (a, b+count, a+count)])
            else:
                faces.append((a, b, b+count, a+count))
    faces.append(tuple(range((len(rings)-1)*count, len(rings)*count)))
    return mesh(name, verts, faces, group, "rock")


mw = P["mountain_width"] / 700
main_rock=rock_mass("主山体_承托全部中轴建筑", (0, 54), 292*mw, 444, P["mountain_bottom_z"], -6, 18, count=38)
for index, (x, y, rx, ry, top) in enumerate([
    (-219,-172,57,76,5), (214,-151,51,67,-4), (-222,13,56,83,23),
    (224,49,42,82,-2), (-214,190,64,67,38), (214,305,49,82,40),
    (-166,350,65,59,80), (170,386,47,60,112), (-121,423,54,69,170),
    (-53,451,47,49,207), (13,460,58,64,194), (91,444,47,57,231),
    (149,433,44,48,166), (-247,322,43,54,138)
]):
    rock_mass(f"崖壁与后山占位_{index+1:02}", (x*mw, y), rx*mw, ry, -210, top, 100+index, count=10)
rock_mass("东侧独立山台_桥端实体支撑", (300*mw, 178), 60*mw, 70, -230, 9, 316, count=14)
rock_mass("西侧松台_实体支撑", (-293*mw, 125), 53*mw, 73, -216, 2, 311, count=13)


# 前庭为完整的水平净空，侧廊放在净空之外。
# 各级台基有实体基础一直落至山顶，不使用悬浮平面代替支撑。
cw, cd, cy0 = P["courtyard_width"], P["courtyard_depth"], P["courtyard_front_y"]
court_end = cy0 + cd
cube("前庭总承台_宽310米", (0, -30, -5.15), (310, 406, 9.7), "base", bevel=0.3)
court = cube("前庭净空_220乘300米_标高0", (0, cy0+cd/2, -1.2), (cw, cd, 2.4), "base", "trim")
cube("月门前平台_标高0", (0, -205, -1.5), (312, 56, 3), "base", "trim")
levels = P["terrace_levels"]
tiers = [(300, 160, 378, levels[1]), (272, 197, 372, levels[2]), (240, 234, 366, levels[3])]
for i, (width, front, back, top) in enumerate(tiers):
    bottom = -6 if i == 0 else levels[i]
    cube(f"台基{i+1}_实体基座_顶标高{top:g}米", (0,(front+back)/2,(bottom+top-1.1)/2),
         (width,back-front,top-bottom-1.1), "base", bevel=0.28)
    cube(f"台基{i+1}_压顶板", (0,(front+back)/2,top-0.55),
         (width+1.6,back-front+1.6,1.1), "base", "trim")
    cube(f"台基{i+1}_水平腰线", (0,(front+back)/2,top-3.0),
         (width+0.7,back-front+0.7,0.55), "base", "trim")
for side in (-1,1):
    cube(f"前庭侧边通行带_{side}", (side*116, cy0+cd/2, -0.1), (10,cd,0.2), "base")
for x in (-92, -46, 46, 92):
    cube(f"广场尺度分缝_X{x}", (x,cy0+cd/2,0.012), (0.20,cd,0.024), "base", "joint")
for y in range(-140,135,25):
    cube(f"广场尺度分缝_Y{y}", (0,y,0.014), (cw,0.20,0.028), "base", "joint")
cube("广场中轴仪式通带_宽18米", (0,cy0+cd/2,0.018), (18,cd,0.036), "base", "stone")


# 台阶按约二十厘米高逐级生成，并保留每段间的水平休息平台。
# 大台阶中央及两翼的路线都接到真实台面，没有不可跨越的空隙。
def stairs(name, x, y0, y1, z0, z1, width, group="stairs"):
    n = max(1, round((z1-z0)/0.20))
    verts, faces = [], []
    for i in range(n):
        ya, yb = y0+(y1-y0)*i/n, y0+(y1-y0)*(i+1)/n
        z = z0+(z1-z0)*(i+1)/n
        k = len(verts)
        verts += [(x-width/2,ya,z0-0.7),(x+width/2,ya,z0-0.7),
                  (x+width/2,yb,z0-0.7),(x-width/2,yb,z0-0.7),
                  (x-width/2,ya,z),(x+width/2,ya,z),(x+width/2,yb,z),(x-width/2,yb,z)]
        faces += [tuple(k+j for j in f) for f in [(0,3,2,1),(4,5,6,7),(0,1,5,4),
                                                                (1,2,6,5),(2,3,7,6),(3,0,4,7)]]
    obj = mesh(name, verts, faces, group, "trim")
    obj["踏步高度_米"] = (z1-z0)/n
    obj["踏步深度_米"] = (y1-y0)/n
    for side in (-1,1):
        beam_between(name+f"_侧挡墙_{side}", (x+side*(width/2+0.8),y0,z0+0.4),
                     (x+side*(width/2+0.8),y1,z1+0.4), 1.2, group)
    return obj


for i,(y0,y1) in enumerate([(134,160),(171,197),(208,234)]):
    stairs(f"中轴第{i+1}段_升高12米",0,y0,y1,levels[i],levels[i+1],64)
    for side in (-1,1):
        stairs(f"两翼辅助台阶_{i+1}_{side}",side*(112-i*12),y0,y1,levels[i],levels[i+1],14)
stairs("前山入口下段",0,-355,-303,-48,-24,48)
cube("前山入口休息平台",(0,-294,-26),(56,18,4),"stairs","trim")
stairs("前山入口上段",0,-285,-233,-24,0,48)
rock_mass("前山入口承托岩脊",(0,-304),68,101,-215,-49,434,count=12)

# 入口在原始崖面上切出随阶梯升高的凹槽，清除挡住踏面的岩体。
# 切除只作用于中轴主山体，槽底仍低于台阶，不改变周围山脊。
verts=[(-30,-359,-60),(30,-359,-60),(30,-232,-10),(-30,-232,-10),
       (-30,-359,30),(30,-359,30),(30,-232,30),(-30,-232,30)]
cut=mesh("入口通道岩体裁切辅助",verts,[(0,3,2,1),(4,5,6,7),(0,1,5,4),
                                  (1,2,6,5),(2,3,7,6),(3,0,4,7)],"mountain","rock")
bpy.context.view_layer.objects.active=main_rock
mod=main_rock.modifiers.new("入口通行净空","BOOLEAN")
mod.operation="DIFFERENCE"
mod.solver="EXACT"
mod.object=cut
bpy.ops.object.modifier_apply(modifier=mod.name)
bpy.data.objects.remove(cut,do_unlink=True)


def railing(name, a, b, group="base", height=1.5, step=8):
    a, b = Vector(a), Vector(b)
    n = max(1, math.ceil((b-a).length/step))
    beam_between(name+"_扶手", a+Vector((0,0,height)), b+Vector((0,0,height)),0.24,group,"trim")
    beam_between(name+"_中横档", a+Vector((0,0,height*0.50)), b+Vector((0,0,height*0.50)),0.16,group,"trim")
    for i in range(n+1):
        p=a+(b-a)*i/n
        cube(name+f"_柱{i:02}",p+Vector((0,0,height/2)),(0.42,0.42,height),group,"trim")


for side in (-1,1):
    railing(f"前庭侧护栏_{side}",(side*153,-222,0),(side*153,149,0))
    railing(f"月门前沿护栏_{side}",(side*31,-229,0),(side*154,-229,0))
for i,(width,front,back,top) in enumerate(tiers):
    for side in (-1,1):
        railing(f"台基{i+1}前缘护栏_{side}",(side*35,front,top),(side*(97-i*12),front,top))
        railing(f"台基{i+1}边缘护栏_{side}",(side*(width/2),front+29,top),
                (side*(width/2),back,top))


# 连续屋面由简化的曲面歇山轮廓近似，保留长屋脊、低檐与角部起翘。
# 这是屋顶大形，不生成瓦片、斗拱、雕饰和复杂屋脊构件。
def roof(name, cx, cy, width, depth, eave, rise, upturn, group="roof", angle=0):
    nx, ny = 40, 24
    verts, faces = [], []
    c, s = math.cos(angle), math.sin(angle)
    def coord(x,y,z):
        return (cx+x*c-y*s, cy+x*s+y*c, z)
    def height(x,y):
        hip=max(abs(y)/(depth/2), max(0,(abs(x)-width*0.32)/(width*0.18)))
        hip=min(1,hip)
        return eave+rise*(1-hip)**1.62+upturn*(abs(x)/(width/2))**9*(abs(y)/(depth/2))**3
    for bottom in (0,1):
        for j in range(ny+1):
            y=-depth/2+depth*j/ny
            for i in range(nx+1):
                x=-width/2+width*i/nx
                verts.append(coord(x,y,height(x,y)-bottom*1.3))
    layer=(nx+1)*(ny+1)
    for j in range(ny):
        for i in range(nx):
            a=j*(nx+1)+i
            faces.append((a,a+1,a+nx+2,a+nx+1))
            faces.append((a+layer+nx+1,a+layer+nx+2,a+layer+1,a+layer))
    boundary=list(range(nx+1))
    boundary += [j*(nx+1)+nx for j in range(1,ny+1)]
    boundary += [ny*(nx+1)+i for i in range(nx-1,-1,-1)]
    boundary += [j*(nx+1) for j in range(ny-1,0,-1)]
    for a,b in zip(boundary,boundary[1:]+boundary[:1]):
        faces.append((a+layer,b+layer,b,a))
    obj=mesh(name,verts,faces,group,"roof",True)
    tube(name+"_简化檐边",[Vector(verts[i])+Vector((0,0,-0.35)) for i in boundary+[boundary[0]]],0.45,group,"trim")
    ridge=[]
    for i in range(25):
        x=-width*0.32+width*0.64*i/24
        ridge.append(coord(x,0,eave+rise+0.5))
    tube(name+"_长屋脊占位",ridge,0.5,group,"trim")
    return obj


def column(name, x,y,z,height,diameter,group="hall"):
    radius=diameter/2
    cylinder(name+"_柱础",(x,y,z+0.8),radius*1.28,1.6,group,"stone",32)
    cylinder(name+"_柱身",(x,y,z+1.6+(height-3.2)/2),radius,height-3.2,group,"trim",32,radius*0.92)
    cylinder(name+"_柱头",(x,y,z+height-0.8),radius*1.20,1.6,group,"stone",32)


hw, hd, hz, hy = P["hall_width"],P["hall_depth"],P["hall_floor_z"],P["hall_center_y"]
ch, diam = P["column_height"],P["column_diameter"]
aisle=P["central_aisle_width"]
xs=[-hw/2,-hw/3,-aisle/2,aisle/2,hw/3,hw/2]
ys=[hy-hd/2+i*hd/3 for i in range(4)]
# 主殿地面直接使用第三级台基压顶，不叠加共面地坪。
# 净尺寸由柱网和总控参数标识，避免渲染中的共面自遮挡。
for j,y in enumerate(ys):
    for i,x in enumerate(xs):
        column(f"主殿巨柱_列{i+1}_进{j+1}",x,y,hz,ch,diam)
for y in ys:
    cube(f"主殿横向主梁_Y{y:.1f}",(0,y,hz+ch+1.7),(hw+8,5.4,3.4),"hall")
for x in xs:
    cube(f"主殿纵向主梁_X{x:g}",(x,hy,hz+ch+1.1),(4.8,hd+8,2.2),"hall")
cube("殿顶平整天花占位_净高46米",(0,hy,hz+ch+4.1),(hw+4,hd+4,1.6),"hall","trim")
for x in (-75,-45,45,75):
    cube(f"殿顶次梁_X{x}",(x,hy,hz+ch+2.5),(1.8,hd,1.8),"hall","stone")
for y in (hy-37.5,hy-12.5,hy+12.5,hy+37.5):
    cube(f"殿顶次梁_Y{y}",(0,y,hz+ch+2.5),(hw,1.8,1.8),"hall","stone")
for side in (-1,1):
    cube(f"主殿侧向屏墙_{side}",(side*(hw/2),hy+hd*0.18,hz+12),(2.6,hd*0.50,24),"hall")
cube("主殿后屏墙_中央留门",(-58,hy+hd/2,hz+17),(59,2.6,34),"hall")
cube("主殿后屏墙_中央留门_东",(58,hy+hd/2,hz+17),(59,2.6,34),"hall")
eave=hz+ch+4
roof("主殿_单层巨型曲面屋顶",0,hy,hw+28,hd+30,eave,P["hall_height"]-ch-5,6)


# 圆形月门只有一处，位于前端长廊中轴，开口是真实穿洞网格。
# 圆心略降，形成平直落地通行弦段，避免圆底只有单点接地。
gy=P["gate_center_y"]
radius=P["gate_opening_diameter"]/2
wall=cube("月门中墙_真实圆形通口",(0,gy,16.5),(68,5,33),"gate","trim")
cutter=cylinder("月門布尔辅助",(0,gy,radius-1.5),radius,12,"gate",vertices=96)
cutter.rotation_euler[0]=math.pi/2
bpy.context.view_layer.objects.active=wall
wall.select_set(True)
mod=wall.modifiers.new("月门实际开口","BOOLEAN")
mod.operation="DIFFERENCE"
mod.solver="EXACT"
mod.object=cutter
bpy.ops.object.modifier_apply(modifier=mod.name)
bpy.data.objects.remove(cutter,do_unlink=True)
wall.select_set(False)
for face_side in (-1,1):
    pts=[]
    start=math.asin(-(radius-1.5)/radius)
    for i in range(97):
        theta=start+(math.pi-2*start)*i/96
        pts.append((radius*math.cos(theta),gy+face_side*2.65,radius-1.5+radius*math.sin(theta)))
    tube(f"月门素面边框_{face_side}",pts,0.7,"gate","stone",1)
roof("月门中央屋顶",0,gy,78,34,35,11,3.1,"gate")
for side in (-1,1):
    center=side*95
    for x0 in (45,68,91,114,139):
        for y0 in (gy-10,gy+10):
            column(f"月门侧长廊柱_{side}_{x0}_{y0}",side*x0,y0,0,26,4.2,"gate")
    cube(f"月门翼廊额枋_{side}",(center,gy-10,27),(116,3,2),"gate")
    cube(f"月门翼廊后枋_{side}",(center,gy+10,27),(116,3,2),"gate")
    roof(f"月门翼廊屋顶_{side}",center,gy,120,34,29,10,2.6,"gate")


# 侧廊位于广场边界外，由柱、连续梁和三段大屋面组成。
# 角亭与后端亭共享连接平台，不占用中央广场净空。
def pavilion(name,x,y,z,size=24,height=19,group="corridor"):
    cube(name+"_地坪",(x,y,z-0.41),(size+4,size+4,0.78),group,"trim")
    for sx in (-1,1):
        for sy in (-1,1):
            column(name+f"_角柱_{sx}_{sy}",x+sx*(size/2-3),y+sy*(size/2-3),z,height,2.6,group)
    cube(name+"_上部支撑",(x,y,z+height+0.7),(size-1,size-1,1.4),group)
    roof(name+"_屋顶",x,y,size+8,size+8,z+height+1.5,8,2.5,group)


for side in (-1,1):
    x=side*P["corridor_center_x"]
    cube(f"侧回廊地坪_{side}",(x,-8,0.05),(24,318,0.1),"corridor","trim")
    for y in range(-151,137,18):
        for sx in (-1,1):
            column(f"侧回廊柱_{side}_{sx}_{y}",x+sx*7,y,0,P["corridor_column_height"],2.5,"corridor")
    for sx in (-1,1):
        cube(f"侧回廊连续梁_{side}_{sx}",(x+sx*7,-9,18),(2.4,304,2),"corridor")
    for i,y in enumerate((-103,-8,87)):
        roof(f"侧回廊屋顶_{side}_{i+1}",x,y,99,29,20,7,2,"corridor",math.pi/2)
    pavilion(f"前庭角亭_{side}",x,-157,0,24,23)
    pavilion(f"前庭后角亭_{side}",x,137,0,24,21)
    pavilion(f"上庭侧亭_{side}",side*131,180,12,23,19)


# 侧桥采用一跨拱形腹墙，桥面保持十二米净宽并与一级平台同高。
# 两端桥台实体落入山台，拱下留空，以说明跨越悬崖的结构。
bx0,bx1,by=150,264*mw,178
deckz=P["bridge_deck_z"]
bw=P["bridge_deck_width"]
cube("东侧桥_连续水平桥面",((bx0+bx1)/2,by,deckz-1.1),(bx1-bx0,bw,2.2),"bridge","trim")
for side in (-1,1):
    verts,faces=[],[]
    for i in range(49):
        t=i/48
        x=bx0+(bx1-bx0)*t
        underside=-40+45*math.sin(math.pi*t)**0.65
        for y,z in [(by+side*(bw/2-0.65)-0.65,underside),(by+side*(bw/2-0.65)+0.65,underside),
                    (by+side*(bw/2-0.65)+0.65,deckz-2),(by+side*(bw/2-0.65)-0.65,deckz-2)]:
            verts.append((x,y,z))
    for i in range(48):
        k=i*4
        faces += [(k+j,k+(j+1)%4,k+(j+1)%4+4,k+j+4) for j in range(4)]
    faces += [(3,2,1,0),(192,193,194,195)]
    mesh(f"侧桥拱形实体腹墙_{side}",verts,faces,"bridge","stone")
    railing(f"东侧桥护栏_{side}",(bx0,by+side*bw/2,deckz),(bx1,by+side*bw/2,deckz),"bridge",1.6,7)
for x in (bx0,bx1):
    cube(f"桥台_实体支撑_{x:g}",(x,by,-15.1),(12,bw+4,49.8),"bridge")
cube("东侧观景台_标高12",(300*mw,178,10.5),(72,74,3),"bridge","trim")
pavilion("东侧观景亭",309*mw,196,12,22,17,"bridge")
railing("东平台东护栏",(335*mw,142,12),(335*mw,214,12),"bridge")
railing("东平台南护栏",(265*mw,142,12),(335*mw,142,12),"bridge")


# 古松用少量折线树干与扁球树冠表达古松姿态，不制作枝叶。
# 瀑布使用连续薄带，从崖顶下落至崖底，色差仅用于辨认占位。
def pine(name,x,y,z,height,spread,lean=0.22):
    trunk=[(x,y,z),(x+height*0.07,y,z+height*0.35),(x+height*lean,y+height*0.03,z+height*0.72),
           (x+height*lean*0.75,y,z+height)]
    tube(name+"_折干占位",trunk,height*0.038,"pine","trunk",1)
    for i,(dx,dy,dz,scale) in enumerate([(-0.32,0,0.64,0.65),(0.28,0.12,0.76,0.7),
                                        (-0.08,-0.18,0.90,0.74),(0.13,0.05,1.0,0.66)]):
        cx,cy,cz=x+height*lean+spread*dx,y+spread*dy,z+height*dz
        tube(name+f"_主枝{i}",[trunk[2],(cx,cy,cz)],height*0.018,"pine","trunk")
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1,radius=1,location=(cx,cy,cz))
        obj=bpy.context.object
        obj.name=name+f"_扁树冠占位{i}"
        for col in list(obj.users_collection):
            col.objects.unlink(obj)
        COL["pine"].objects.link(obj)
        obj.scale=(spread*scale,spread*scale*0.56,height*0.115)
        obj.data.materials.append(MAT["pine"])


for i,(x,y,z,h,w,lean) in enumerate([(-230,-175,5,43,25,.22),(219,-144,-2,38,24,-.25),
                                     (-292,125,2,53,34,.25),(299,162,12,42,28,-.3),
                                     (-215,210,35,36,24,.25),(170,385,110,39,25,-.2),
                                     (-160,365,77,38,27,.22),(214,313,36,39,24,-.16)]):
    pine(f"古松占位_{i+1:02}",x*mw,y,z,h,w,lean)
# 根据已经生成的岩体进行射线查询，把瀑布带放到可见崖面外侧。
# 每一段都保留清楚的落差占位，不用粒子或流体模拟进入细化阶段。
bpy.context.view_layer.update()
depsgraph=bpy.context.evaluated_depsgraph_get()
rocks=[ob.evaluated_get(depsgraph) for ob in COL["mountain"].objects if ob.type=="MESH"]
for index,(x,y,top,bottom,width) in enumerate([(-216,-240,0,-207,14),(219,-210,-6,-220,17),
                                            (304,137,8,-214,12),(-235,270,100,-160,10)]):
    verts=[]
    for i in range(19):
        t=i/18
        zz=top+(bottom-top)*t
        xx=x+math.sin(t*4+index)*0.7
        hit_y=[]
        for rock in rocks:
            hit,loc,normal,face=rock.ray_cast(Vector((xx,-1000,zz)),Vector((0,1,0)))
            if hit:
                hit_y.append(loc.y)
        yy=min(hit_y)-2.2 if hit_y else y
        ww=width*(1+0.10*math.sin(t*7))
        verts.extend([(xx-ww/2,yy,zz),(xx+ww/2,yy,zz)])
    faces=[(i*2,i*2+1,i*2+3,i*2+2) for i in range(18)]
    ob=mesh(f"瀑布占位_{index+1:02}_连续落差{top-bottom:g}米",verts,faces,"water","water")
    mod=ob.modifiers.new("占位薄带厚度","SOLIDIFY")
    mod.thickness=0.45


# 人形各肢体尺寸按一米八总高构成，保持人类真实比例。
# 主殿近景、远景与广场都放同一尺度，禁止为画面效果放大人物。
def human(name,x,y,z):
    s=P["human_height"]/1.8
    def point(px,py,pz):
        return (x+px*s,y+py*s,z+pz*s)
    parts=[]
    parts.append(cylinder(name+"_头",point(0,0,1.675),.125*s,.25*s,"human","human",16))
    parts.append(cube(name+"_躯干",point(0,0,1.20),(.40*s,.23*s,.64*s),"human","human",.05*s))
    for side in (-1,1):
        parts.append(beam_between(name+f"_腿{side}",point(side*.105,0,.90),point(side*.14,0,.10),.135*s,"human","human",.15*s))
        parts.append(beam_between(name+f"_臂{side}",point(side*.24,0,1.44),point(side*.30,.015,.88),.105*s,"human","human"))
        parts.append(cube(name+f"_脚{side}",point(side*.14,-.055,.05),(.15*s,.27*s,.10*s),"human","human"))
    for part in parts:
        part["人形总高_米"]=P["human_height"]
    return parts


for i,(x,y,z) in enumerate([(1,320,hz),(-7,274,hz),(12,253,hz),(0,-211,0),(5,-164,0),
                           (-9,-95,0),(3,10,0),(-4,83,0),(17,126,0),(10,167,12),
                           (-7,204,24),(279,178,12)]):
    human(f"尺度人形_{i+1:02}_高1点8米",x,y,z)


# 参数以工程内嵌文本和总控空物体两种形式保留，便于定位与核对。
# 总控属性是参数索引；精确重建时修改设计参数文件或内嵌文本后运行脚本。
control=bpy.data.objects.new("00_设计参数总控_单位米_见内嵌说明",None)
COL["control"].objects.link(control)
control.empty_display_type="PLAIN_AXES"
control.empty_display_size=15
control.location=(0,0,-265)
for key,value in P.items():
    if isinstance(value,(float,int,list)):
        control[key]=value
control["参数编辑说明"]="主要尺寸集中于01_设计参数.json；运行重建脚本生成新场景，先另存版本。"
param_text=bpy.data.texts.new("01_设计参数.json")
param_text.write(json.dumps(P,ensure_ascii=False,indent=2))
if "__file__" in globals():
    script_text=bpy.data.texts.new("02_重建白模.py")
    script_text.write(Path(__file__).read_text(encoding="utf-8"))
for name,loc in [("广场完成面_Z0",(0,0,0)),("一级台基_Z12",(0,161,12)),
                 ("二级台基_Z24",(0,198,24)),("主殿完成面_Z36",(0,236,36))]:
    obj=bpy.data.objects.new(name,None)
    COL["guide"].objects.link(obj)
    obj.location=loc
    obj.empty_display_type="CIRCLE"
    obj.empty_display_size=4
    obj.show_name=True


# 四个机位在时间线绑定一至四帧，打开工程即可按帧切换。
# 外景使用正常焦段或正交校核，人视机位严格保持一米六五眼高。
def camera(name,loc,target,lens=50,ortho=None):
    data=bpy.data.cameras.new(name)
    obj=bpy.data.objects.new(name,data)
    COL["camera"].objects.link(obj)
    obj.location=loc
    obj.rotation_euler=(Vector(target)-Vector(loc)).to_track_quat("-Z","Y").to_euler()
    data.lens=lens
    data.clip_start=0.08
    data.clip_end=6000
    data.passepartout_alpha=1
    if ortho:
        data.type="ORTHO"
        data.ortho_scale=ortho
    return obj


CAMS=[
    camera("CAM_01_整体斜视_55mm",(860,-1280,820),(0,55,-5),55),
    camera("CAM_02_正面_正交比例校核",(0,-1500,300),(0,65,10),ortho=840),
    camera("CAM_03_鸟瞰_50mm",(610,-880,1340),(0,62,-5),50),
    camera("CAM_04_殿内人视_眼高1点65米_32mm",(0,339,hz+P["eye_height"]),(0,223,67),32)
]
SCENE.frame_start=1
SCENE.frame_end=4
for i,cam in enumerate(CAMS,1):
    marker=SCENE.timeline_markers.new(cam.name,frame=i)
    marker.camera=cam
SCENE.camera=CAMS[0]
SCENE.frame_set(1)
world=bpy.data.worlds.new("中性天空_无雾")
world.use_nodes=True
world.node_tree.nodes["Background"].inputs["Color"].default_value=(0.74,0.78,0.82,1)
world.node_tree.nodes["Background"].inputs["Strength"].default_value=0.65
SCENE.world=world
ld=bpy.data.lights.new("主光_柔和日光","SUN")
lo=bpy.data.objects.new(ld.name,ld)
COL["light"].objects.link(lo)
lo.rotation_euler=(math.radians(24),math.radians(-31),math.radians(-28))
ld.energy=2.2
ld.angle=math.radians(12)
ld=bpy.data.lights.new("殿内入口_基础补光","AREA")
lo=bpy.data.objects.new(ld.name,ld)
COL["light"].objects.link(lo)
lo.location=(0,hy-60,hz+28)
lo.rotation_euler=(Vector((0,hy+30,hz+20))-lo.location).to_track_quat("-Z","Y").to_euler()
ld.energy=75000
ld.shape="RECTANGLE"
ld.size=120
ld.size_y=40
SCENE.render.engine="CYCLES"
SCENE.cycles.device="CPU"
SCENE.cycles.samples=P["render_samples"]
SCENE.cycles.use_denoising=True
SCENE.cycles.adaptive_threshold=0.07
SCENE.cycles.max_bounces=5
SCENE.cycles.diffuse_bounces=3
SCENE.render.resolution_x=P["render_width"]
SCENE.render.resolution_y=P["render_height"]
SCENE.render.resolution_percentage=100
SCENE.render.image_settings.file_format="PNG"
SCENE.render.film_transparent=False
SCENE.view_settings.view_transform="AgX"
SCENE.view_settings.look="AgX - Medium High Contrast"
SCENE.render.threads_mode="FIXED"
SCENE.render.threads=16


# 保存前整理视口，让打开工程时直接出现整体机位而非默认立方体。
# 工程中保留全部可编辑对象、相机和光源，渲染只是验收输出。
for area in bpy.context.screen.areas:
    if area.type=="VIEW_3D":
        area.spaces.active.clip_end=6000
        area.spaces.active.region_3d.view_perspective="CAMERA"
        area.spaces.active.overlay.show_extras=False
        area.spaces.active.shading.type="SOLID"
        area.spaces.active.shading.light="STUDIO"
        area.spaces.active.shading.color_type="MATERIAL"
        area.spaces.active.shading.show_cavity=True
        area.spaces.active.shading.cavity_type="BOTH"
bpy.ops.object.select_all(action="DESELECT")
SCENE["交付机位"]="第1帧整体斜视；第2帧正面；第3帧鸟瞰；第4帧殿内人视"
ROOT.mkdir(parents=True,exist_ok=True)
(ROOT/"renders").mkdir(exist_ok=True)
(ROOT/"qa").mkdir(exist_ok=True)
version=1
while (ROOT/f"HeavenlyPalace_Whitebox_v{version:02}.blend").exists():
    version+=1
BLEND=ROOT/f"HeavenlyPalace_Whitebox_v{version:02}.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(BLEND))
report={"blend":str(BLEND),"scene":SCENE.name,"object_count":len(SCENE.objects),
        "collections":{col.name:len(col.objects) for col in COL.values()},
        "cameras":[{"name":c.name,"position":list(c.location),"lens_mm":c.data.lens,"type":c.data.type} for c in CAMS],
        "parameters":P}
(ROOT/"qa"/"scene_report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print("WHITEBOX_SAVED",str(BLEND),flush=True)
if "--preview" in ARGS:
    SCENE.cycles.samples=12
    SCENE.render.resolution_percentage=65
if "--render" in ARGS or "--preview" in ARGS:
    names=["01_oblique","02_front","03_aerial","04_interior"]
    for i,name in enumerate(names):
        SCENE.frame_set(i+1)
        SCENE.camera=CAMS[i]
        SCENE.render.filepath=str(ROOT/("qa" if "--preview" in ARGS else "renders")/(name+".png"))
        bpy.ops.render.render(write_still=True)
        print("RENDER_DONE",name,flush=True)
    SCENE.frame_set(1)
    SCENE.camera=CAMS[0]
print("STAGE_ONE_COMPLETE",flush=True)
