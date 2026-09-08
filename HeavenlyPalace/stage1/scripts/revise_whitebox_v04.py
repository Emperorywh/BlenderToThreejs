"""
在已保存的白模 v03 上修订月门视线、山体剪影与主殿檐口大形。
保留广场、台基、巨柱、侧廊与桥梁；输出为独立 v04 文件。
新增造型仅为白模体块，所有参数与脚本随工程内嵌保存。
"""
import ast
import bpy
import json
import math
import random
import sys
from pathlib import Path
from mathutils import Vector


# 从原工程复用几何工具函数，仅执行函数定义，不重新生成整个场景。
# 当前打开的其他 Blender 会话不受影响，磁盘 v03 始终保持原样。
# 外部运行时从脚本定位项目，工程内运行时优先使用当前工程所在目录。
# 参数文本作为随工程保存的后备来源，不依赖网络或材质外链。
ROOT=Path(__file__).resolve().parents[1] if "__file__" in globals() and Path(__file__).is_file() else Path(bpy.data.filepath).parent
OUT=ROOT/"v04"
ARGS=sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
SCENE=bpy.context.scene
if SCENE.get("v04设计取舍"):
    raise RuntimeError("请以保留的 v03 工程运行本修订脚本，避免在 v04 上叠加重复体块")
SCENE.name="天宫_白模v04_月门视线与轮廓修订"
P=json.loads(bpy.data.texts["01_设计参数.json"].as_string())
V=json.loads((OUT/"design_parameters_v04.json").read_text(encoding="utf-8")) if (OUT/"design_parameters_v04.json").exists() else json.loads(bpy.data.texts["03_v04设计参数.json"].as_string())
COL={}
for key,prefix in [("control","00_"),("mountain","01_"),("base","02_"),("hall","03_"),
                   ("roof","04_"),("gate","05_"),("corridor","06_"),("stairs","07_"),
                   ("bridge","08_"),("pine","09_"),("water","10_"),("human","11_"),
                   ("camera","12_"),("light","13_"),("guide","14_")]:
    COL[key]=next(col for col in SCENE.collection.children if col.name.startswith(prefix))
MAT={key:bpy.data.materials[name] for key,name in {
    "stone":"白模_暖灰石材","trim":"白模_浅色檐口柱身","roof":"白模_中灰屋顶",
    "rock":"白模_山体占位","pine":"白模_树冠占位","trunk":"白模_树干占位",
    "water":"白模_瀑布占位","human":"尺度参照_深灰","joint":"白模_地面分区"}.items()}
source=ast.parse(bpy.data.texts["02_重建白模.py"].as_string())
definitions=[node for node in source.body if isinstance(node,ast.FunctionDef)]
exec(compile(ast.Module(body=definitions,type_ignores=[]),"原白模几何工具","exec"),globals())
for key,label in [("moon","05A_主殿月门_同层完整视线"),("skyline","15_远景云海_无雾占位")]:
    col=bpy.data.collections.new(label)
    SCENE.collection.children.link(col)
    COL[key]=col
COL["gate"].name="05_前端入口长廊_直口通行"


# 只替换本次授权修改的对象；原工程中其他部分的网格和相机继续沿用。
# 临时布尔物体在完成几何操作后移除，不在交付场景中留下隐藏切刀。
def remove_objects(objects):
    for ob in list(objects):
        bpy.data.objects.remove(ob,do_unlink=True)


def apply_difference(target,cutter,label):
    bpy.context.view_layer.objects.active=target
    target.select_set(True)
    mod=target.modifiers.new(label,"BOOLEAN")
    mod.operation="DIFFERENCE"
    mod.solver="EXACT"
    mod.object=cutter
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(cutter,do_unlink=True)
    target.select_set(False)


# 唯一主月门移入主殿前檐，与殿内同层，避免通过降机位掩盖台基遮挡。
# 前端长廊保留原体量，其中央改为直口，轴线仍可贯穿整座建筑群。
remove_objects(ob for ob in COL["gate"].objects if ob.name.startswith(("月门中墙","月门素面边框")))
gy=P["gate_center_y"]
entry=cube("前端入口_直口门墙",(0,gy,16.5),(68,5,33),"gate","trim")
cut=cube("直口通道_临时切刀",(0,gy,V["entry_clear_height"]/2-0.1),
         (V["entry_clear_width"],12,V["entry_clear_height"]+0.2),"gate")
apply_difference(entry,cut,"贯通直口入口")
my,mz=V["moon_plane_y"],V["moon_floor_z"]
mr=V["moon_diameter"]/2
mcenter=mz+V["moon_center_above_floor"]
moon=cube("主殿月门_直径44米_落地弦口",(0,my,mz+V["moon_wall_height"]/2),
          (V["moon_wall_width"],V["moon_wall_thickness"],V["moon_wall_height"]),"moon","trim")
cut=cylinder("主殿月门_临时切刀",(0,my,mcenter),mr,12,"moon",vertices=128)
cut.rotation_euler.x=math.pi/2
apply_difference(moon,cut,"巨型圆形开口")
for side in (-1,1):
    start=math.asin(-V["moon_center_above_floor"]/mr)
    pts=[]
    for i in range(129):
        angle=start+(math.pi-2*start)*i/128
        pts.append((mr*math.cos(angle),my+side*(V["moon_wall_thickness"]/2+0.22),mcenter+mr*math.sin(angle)))
    tube(f"主殿月门_素面厚边_{side}",pts,0.55,"moon","stone",1)
moon["净开口直径_米"]=V["moon_diameter"]
moon["开口顶标高_米"]=mcenter+mr
moon["落地有效通行宽_米"]=2*math.sqrt(mr*mr-V["moon_center_above_floor"]**2)
cube("月门外同层短廊_台基侧壁标识",(0,238.5,34.4),(56,9,2.2),"moon","stone")


# 后山改为斜向收分的错落山脊，低中部为主殿屋脊留出轮廓空间。
# 每个山脊只有少量截面和大三角面，不做雕刻、噪声细分或岩石贴图。
def ridge_mass(name,x,y,rx,ry,top,leanx,leany,seed):
    gen=random.Random(seed)
    count=12
    shape=[gen.uniform(0.82,1.16) for i in range(count)]
    rings=[(-210,0.55,0),(-122,1.0,0.1),(-26,0.91,0.25),
           (top*0.48,0.66,0.54),(top*0.84,0.31,0.85),(top,0.065,1)]
    verts=[]
    for j,(z,scale,shift) in enumerate(rings):
        for i in range(count):
            a=math.tau*i/count
            zz=z+(gen.uniform(-8,6) if j in (2,3,4) else (gen.uniform(-3,0) if j==5 else 0))
            verts.append((x+leanx*shift+rx*math.cos(a)*scale*shape[i],
                          y+leany*shift+ry*math.sin(a)*scale*shape[i],zz))
    faces=[tuple(reversed(range(count)))]
    for j in range(len(rings)-1):
        for i in range(count):
            a=j*count+i
            b=j*count+(i+1)%count
            faces.extend([(a,b,b+count),(a,b+count,a+count)])
    faces.append(tuple(range(5*count,6*count)))
    return mesh(name,verts,faces,"mountain","rock")


remove_objects(ob for ob in COL["mountain"].objects if ob.name.startswith("崖壁与后山占位_"))
for i,(x,y,rx,ry,top,lx,ly) in enumerate([
    (-226,-169,53,72,12,-12,5),(225,-145,47,64,6,16,3),
    (-234,20,55,79,34,-18,8),(231,50,43,76,10,16,2),
    (-230,207,63,66,52,-17,10),(225,313,52,72,49,23,6),
    (-180,388,65,72,99,-27,16),(197,405,62,73,93,25,15),
    (-181,462,72,79,V["rear_peak_max_z"],-22,10),
    (-88,470,70,66,96,-23,9),(18,490,80,66,63,22,13),
    (130,470,67,76,126,18,18),(-279,358,47,70,112,-14,8)
]):
    ridge_mass(f"山脊占位_v04_{i+1:02}",x,y,rx,ry,top,lx,ly,611+i)


# 古松随修订山形重新落地，桥上古松仍以观景台完成面为基准。
# 射线查询只包含岩体，防止误把树冠或屋顶当作种植支撑面。
bpy.context.view_layer.update()
deps=bpy.context.evaluated_depsgraph_get()
rocks=[ob.evaluated_get(deps) for ob in COL["mountain"].objects if ob.type=="MESH"]
pine_bases=[(-230,-175,5),(219,-144,-2),(-292,125,2),(299,162,12),
            (-215,210,35),(170,385,110),(-160,365,77),(214,313,36)]
for i,(x,y,oldz) in enumerate(pine_bases,1):
    hits=[]
    for ob in rocks:
        hit,loc,normal,face=ob.ray_cast(Vector((x,y,400)),Vector((0,0,-1)))
        if hit:
            hits.append(loc.z)
    newz=12 if i==4 else max(hits,default=oldz)
    for ob in COL["pine"].objects:
        if ob.name.startswith(f"古松占位_{i:02}_"):
            ob.location.z+=newz-oldz


# 每条瀑布绑定一块连续的宿主崖壁，避免跨不同山峰投影形成斜拉长条。
# 后山瀑布重新放到西北山脊，其他瀑布只随其原有崖壁调整。
water_hosts={1:"山脊占位_v04_01",2:"山脊占位_v04_02",3:"东侧独立山台_桥端实体支撑",4:"山脊占位_v04_09"}
for waterfall_index,ob in enumerate(sorted(COL["water"].objects,key=lambda item:item.name),1):
    host=bpy.data.objects[water_hosts[waterfall_index]].evaluated_get(deps)
    front_mass=bpy.data.objects["主山体_承托全部中轴建筑"].evaluated_get(deps)
    for i in range(0,len(ob.data.vertices),2):
        left,right=ob.data.vertices[i],ob.data.vertices[i+1]
        x=(left.co.x+right.co.x)/2
        z=left.co.z
        if waterfall_index==4:
            t=i/(len(ob.data.vertices)-2)
            width=right.co.x-left.co.x
            x=-202
            z=142-317*t
            left.co.x,right.co.x=x-width/2,x+width/2
            left.co.z=right.co.z=z
        hits=[]
        candidates=[host,front_mass] if waterfall_index in (1,2) else [host]
        for candidate in candidates:
            for sample_x in (left.co.x,x,right.co.x):
                hit,loc,normal,face=candidate.ray_cast(Vector((sample_x,-1000,z)),Vector((0,1,0)))
                if hit:
                    hits.append(loc.y)
        if hits:
            left.co.y=right.co.y=min(hits)-2.2


# 下檐以环形屋面构成，不把第二座完整屋顶压进殿内空间。
# 上檐、承托层和外挑下檐形成三个可读层次，总屋脊高度仍约一百一十六米。
remove_objects(COL["roof"].objects)
def eave_skirt():
    corners=16
    rim=[]
    for side in range(4):
        for i in range(corners):
            t=i/corners
            rim.append([(-1+2*t,-1),(1,-1+2*t),(1-2*t,1),(-1,1-2*t)][side])
    count=len(rim)
    verts=[]
    rings=7
    for lower in (0,1):
        for j in range(rings):
            u=j/(rings-1)
            w=176+(V["lower_eave_width"]-176)*u
            d=98+(V["lower_eave_depth"]-98)*u
            for px,py in rim:
                z=V["lower_eave_z"]+(V["lower_eave_inner_z"]-V["lower_eave_z"])*(1-u)**1.55
                z+=V["lower_eave_corner_rise"]*(abs(px*py)**7)*u**2
                verts.append((px*w/2,295+py*d/2,z-lower*1.3))
    faces=[]
    layer=rings*count
    for j in range(rings-1):
        for i in range(count):
            a=j*count+i
            b=j*count+(i+1)%count
            faces.extend([(a,b,b+count,a+count),(a+layer+count,b+layer+count,b+layer,a+layer)])
    for j in (0,rings-1):
        for i in range(count):
            a=j*count+i
            b=j*count+(i+1)%count
            faces.append((a+layer,b+layer,b,a) if j==rings-1 else (a,b,b+layer,a+layer))
    obj=mesh("主殿下檐_外挑环形曲面",verts,faces,"roof","roof",True)
    edge=verts[(rings-1)*count:rings*count]
    tube("主殿下檐_连续厚檐口",[Vector(v)+Vector((0,0,-.65)) for v in edge+[edge[0]]],.75,"roof","trim",0)
    return obj


eave_skirt()
cube("主殿重檐承托层_大形",(0,295,90.4),(184,104,8.6),"roof","stone")
roof("主殿上层大屋面",0,295,V["upper_roof_width"],V["upper_roof_depth"],
     V["upper_eave_z"],V["upper_roof_rise"],4.0)
for ob in COL["hall"].objects:
    if ob.name.startswith("主殿横向主梁_"):
        ob.scale.y=6.4/5.4
        ob.scale.z=4.8/3.4
        ob.location.z=84.4
    elif ob.name.startswith("主殿纵向主梁_"):
        ob.scale.x=5.8/4.8
        ob.scale.z=3.6/2.2
        ob.location.z=84.0
for x in (-90,-60,-30,30,60,90):
    for y in (245,345):
        cube(f"檐下整块承托_{x}_{y}",(x,y,84.3),(10,10,3),"hall","stone")
        cube(f"檐下外挑枋_{x}_{y}",(x,y,86.3),(12,15,1.4),"hall","trim")


# 远处以少量扁球体提示云海地平线，不使用体积雾或发光材质。
# 占位位于建筑群以南一千六百米以外，不穿过建筑，也不遮挡检查比例的机位。
cloudmat=MAT["trim"].copy()
cloudmat.name="白模_远景云海占位"
cloudmat.diffuse_color=(.73,.76,.77,1)
cloudmat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value=(.73,.76,.77,1)
MAT["cloud"]=cloudmat
for index,(x,y,z,sx,sy,sz) in enumerate([
    (-1650,-1920,-20,850,360,125),(-700,-1770,-5,690,350,140),(250,-1890,4,810,320,132),(1330,-1970,-15,820,340,140),
    (-1450,-2520,45,860,380,178),(-410,-2440,60,690,330,208),(610,-2580,48,780,370,180),(1680,-2640,50,870,410,170),
    (-850,-3290,122,1020,470,210),(620,-3420,140,1180,500,233)
]):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32,ring_count=16,radius=1,location=(x,y,z))
    ob=bpy.context.object
    ob.name=f"远景云海占位_{index+1:02}"
    for col in list(ob.users_collection):
        col.objects.unlink(ob)
    COL["skyline"].objects.link(ob)
    # 以殿内眼点为中心整体后移并等比扩大，保持人视中的云海角尺度。
    # 全部实体退到正面机位之后，避免近处云体进入外景检查画面。
    eye=Vector((0,V["interior_camera_y"],V["moon_floor_z"]+V["eye_height"]))
    ob.location=eye+(Vector((x,y,z))-eye)*1.4
    ob.scale=(sx*1.4,sy*1.4,sz*1.4)
    ob.data.materials.append(cloudmat)
    for polygon in ob.data.polygons:
        polygon.use_smooth=True

# 屋面统一压至中灰，靠色阶读出上下檐轮廓，仍然只使用单色哑光。
# 这项调整不引入贴图、反射特效或装饰细节。
MAT["roof"].diffuse_color=(.28,.30,.31,1)
MAT["roof"].node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value=(.28,.30,.31,1)


# 三个外景机位保留 v03 的位置，保证前后版本可以直接比较。
# 人视机位只调整焦段和朝向，眼高始终是主殿地面以上一米六五。
cam=next(ob for ob in COL["camera"].objects if ob.name.startswith("CAM_04_"))
cam.name="CAM_04_殿内月门_眼高1点65米_35mm"
cam.location=(0,V["interior_camera_y"],mz+V["eye_height"])
cam.rotation_euler=(Vector((0,my,V["interior_target_z"]))-cam.location).to_track_quat("-Z","Y").to_euler()
cam.data.lens=V["interior_lens_mm"]
cam["固定眼高_米"]=V["eye_height"]
for ob in COL["camera"].objects:
    ob.data.clip_end=10000
for marker in SCENE.timeline_markers:
    marker.name=marker.camera.name
SCENE["阶段"]="白模v04；完成月门视线、山体剪影与重檐大形，验收前停止细化"
SCENE["v04设计取舍"]="主月门位于主殿前檐+36米；南入口长廊改直口；全场只有一处主圆门。"
control=next(iter(COL["control"].objects))
for key,value in V.items():
    control["v04_"+key]=value
control["v04参数位置"]="03_v04设计参数.json；04_v04修订脚本.py"
script_body=Path(__file__).read_text(encoding="utf-8") if "__file__" in globals() and Path(__file__).is_file() else bpy.data.texts["04_v04修订脚本.py"].as_string()
for name,content in [("03_v04设计参数.json",json.dumps(V,ensure_ascii=False,indent=2)),
                     ("04_v04修订脚本.py",script_body)]:
    block=bpy.data.texts.get(name) or bpy.data.texts.new(name)
    block.clear()
    block.write(content)
note_path=OUT/"v04验收说明.md"
if note_path.exists():
    note=bpy.data.texts.get("00_v04验收说明.md") or bpy.data.texts.new("00_v04验收说明.md")
    note.clear()
    note.write(note_path.read_text(encoding="utf-8"))
SCENE.render.resolution_x=V["final_render_width"]
SCENE.render.resolution_y=V["final_render_height"]
SCENE.render.resolution_percentage=100
SCENE.cycles.samples=V["final_render_samples"]
SCENE.cycles.adaptive_threshold=.045
SCENE.cycles.use_denoising=True
for ob in COL["light"].objects:
    if ob.data.type=="SUN":
        ob.data.angle=math.radians(8)
        ob.data.energy=2.1
SCENE.world.node_tree.nodes["Background"].inputs["Strength"].default_value=.5
bpy.ops.object.select_all(action="DESELECT")
for area in bpy.context.screen.areas:
    if area.type=="VIEW_3D":
        area.spaces.active.region_3d.view_perspective="CAMERA"
        area.spaces.active.overlay.show_extras=False
SCENE.frame_set(4)
SCENE.camera=cam
SCENE.render.filepath=str(OUT/"renders"/"04_interior.png")
destination=OUT/"qa"/"v04_working.blend" if "--preview" in ARGS else ROOT/"HeavenlyPalace_Whitebox_v04.blend"
if destination.exists() and "--preview" not in ARGS:
    raise RuntimeError("v04 已存在；请先保留原版本，不自动覆盖")
bpy.ops.wm.save_as_mainfile(filepath=str(destination))
print("V04_SAVED",str(destination),flush=True)
if "--render" in ARGS or "--preview" in ARGS:
    if "--preview" in ARGS:
        SCENE.cycles.samples=16
        SCENE.render.resolution_percentage=60
    for frame,label in [(4,"04_interior"),(1,"01_oblique"),(2,"02_front"),(3,"03_aerial")]:
        SCENE.frame_set(frame)
        SCENE.render.filepath=str(OUT/("qa" if "--preview" in ARGS else "renders")/(label+".png"))
        bpy.ops.render.render(write_still=True)
        print("V04_RENDER",label,flush=True)
print("V04_REVISION_COMPLETE",flush=True)
