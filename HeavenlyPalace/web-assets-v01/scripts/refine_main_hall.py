"""
把现有网页工程中的主殿重建为可单独调整的建筑样板，保留场景原点与月门通道。
屋面、彩枋、斗拱、石柱和台基分别组织；重复执行先替换本轮构件，不叠加装饰。
"""
import bpy
import bmesh
import hashlib
import json
import math
import shutil
import sys
from pathlib import Path
from mathutils import Vector, Matrix

ROOT = Path(__file__).resolve().parents[1]
# 重建与导出采用同一保存入口，减少 Windows 下连续写同一个工程时的占用冲突。
# 该入口只负责完整写出及原子替换，不修改任何几何或材质。
sys.path.insert(0,str(Path(__file__).resolve().parent))
from blend_io import save_web_blend
# 空间调整在基准构件重建之后统一应用，重建之前恢复原始网格与标高。
# 这样主殿、藻井和独立空间阶段都复用同一份几何来源，不会累计抬高或缩放。
from hall_space import restore_space, apply_space
SCENE = bpy.context.scene
PREFIX = 'H01_'
CY = 295.0
P = dict(half_width=124.0, half_depth=76.0, ridge_half=72.0,
         ridge_z=124.0, eave_z=95.2, toe_lift=1.8, corner_lift=5.0,
         curve_power=1.62, shell_thickness=.85, column_radius_scale=1.18)
MATS = {}
COLS = {}
BOX_CACHE = {}
REPORT = {'revision': 'h01', 'parameters': P, 'removed_objects': [], 'trimmed_objects': []}


def material(key, title, color, roughness, metallic=0):
    """
    主殿使用独立的釉瓦、朱漆和古金材质，调整色彩不会牵动长廊或山体。
    同时写出网页导出规格，让 Blender 与 glTF 使用同一组物理材质参数。
    """
    mat = bpy.data.materials.get(PREFIX + title) or bpy.data.materials.new(PREFIX + title)
    mat.use_nodes = True
    mat.diffuse_color = (*color, 1)
    node = mat.node_tree.nodes.get('Principled BSDF')
    node.inputs['Base Color'].default_value = (*color, 1)
    node.inputs['Roughness'].default_value = roughness
    node.inputs['Metallic'].default_value = metallic
    mat['web_spec'] = json.dumps(dict(source=mat.name, name=mat.name, files={},
                                    base_factor=[*color, 1], roughness=roughness,
                                    metallic=metallic, tile_m=4), ensure_ascii=False)
    MATS[key] = mat


class Mesh:
    """
    将同类构件直接拼成可编辑网格，避免创建上万个对象拖慢场景与导出。
    每个构件保留真实厚度和独立面，几何法线与纹理坐标在写出时统一检查。
    """
    def __init__(self, name, group):
        self.name, self.group = name, group
        self.verts, self.faces, self.indices, self.smooth = [], [], [], []

    def add(self, verts, faces, mat, smooth=False):
        """
        追加局部构件并记录材质，只有曲面开启平滑。
        方材与雕刻边框保留平面法线，避免出现软塌的高光。
        """
        start = len(self.verts)
        self.verts.extend(tuple(v) for v in verts)
        self.faces.extend(tuple(start + i for i in face) for face in faces)
        self.indices.extend([mat] * len(faces))
        self.smooth.extend([smooth] * len(faces))

    def box(self, center, size, mat, bevel=.05, angle=0):
        """
        倒角方材按尺寸缓存一次，再按中心与朝向落位。
        倒角直接固化到网格，网页无需求值任何 Blender 修改器。
        """
        key = (*size, bevel)
        if key not in BOX_CACHE:
            bm = bmesh.new()
            bmesh.ops.create_cube(bm, size=1)
            for v in bm.verts:
                v.co = Vector(tuple(v.co[i] * size[i] for i in range(3)))
            if bevel:
                bmesh.ops.bevel(bm, geom=list(bm.edges), offset=min(bevel, min(size) / 4),
                                segments=1, affect='EDGES')
            bm.verts.ensure_lookup_table()
            bm.verts.index_update()
            BOX_CACHE[key] = ([tuple(v.co) for v in bm.verts], [tuple(v.index for v in f.verts) for f in bm.faces])
            bm.free()
        verts, faces = BOX_CACHE[key]
        c, s = math.cos(angle), math.sin(angle)
        self.add([(center[0] + x*c - y*s, center[1] + x*s + y*c, center[2] + z)
                  for x, y, z in verts], faces, mat)

    def tube(self, points, radius, mat, sides=8):
        """
        沿连续路径铺设筒瓦、屋脊和浅浮雕，采用平行参考轴减少截面扭转。
        两端补齐端盖，近景查看时不会露出空心断口。
        """
        points = [Vector(p) for p in points]
        verts, faces = [], []
        radii = radius if isinstance(radius, (list, tuple)) else [radius] * len(points)
        for i, point in enumerate(points):
            tangent = (points[min(i+1, len(points)-1)] - points[max(0, i-1)]).normalized()
            reference = Vector((0, 0, 1)) if abs(tangent.z) < .93 else Vector((0, 1, 0))
            a = tangent.cross(reference).normalized()
            b = tangent.cross(a).normalized()
            for j in range(sides):
                angle = 2 * math.pi * j / sides
                verts.append(point + radii[i] * (a * math.cos(angle) + b * math.sin(angle)))
        for i in range(len(points)-1):
            for j in range(sides):
                a, b = i*sides+j, i*sides+(j+1)%sides
                faces.append((a, b, b+sides, a+sides))
        faces.extend([tuple(reversed(range(sides))), tuple((len(points)-1)*sides+j for j in range(sides))])
        self.add(verts, faces, mat, True)

    def lathe(self, center, profile, mat, sides=48):
        """
        用回转断面建立石础、束腰和莲瓣承台，尺寸沿高度逐层收放。
        相邻断面共享环线，圆柱表面连续且不会出现可见棱角。
        """
        verts, faces = [], []
        for z, radius in profile:
            for j in range(sides):
                a = 2*math.pi*j/sides
                verts.append((center[0]+radius*math.cos(a), center[1]+radius*math.sin(a), center[2]+z))
        for i in range(len(profile)-1):
            for j in range(sides):
                a, b = i*sides+j, i*sides+(j+1)%sides
                faces.append((a, b, b+sides, a+sides))
        faces.extend([tuple(reversed(range(sides))), tuple((len(profile)-1)*sides+j for j in range(sides))])
        self.add(verts, faces, mat, True)

    def profile(self, points, depth, mat, origin=(0, 0, 0), angle=0):
        """
        将拱形或卷草轮廓挤出成实体，避免用矩形堆砌斗拱轮廓。
        深度沿局部横轴设置，同一攒的横拱与挑拱可以垂直交错。
        """
        c, s = math.cos(angle), math.sin(angle)
        verts = [(origin[0]+x*c-y*s, origin[1]+x*s+y*c, origin[2]+z)
                 for y in (-depth/2, depth/2) for x, z in points]
        n = len(points)
        faces = [tuple(reversed(range(n))), tuple(n+i for i in range(n))]
        faces.extend((i, (i+1)%n, (i+1)%n+n, i+n) for i in range(n))
        self.add(verts, faces, mat)

    def finish(self):
        """
        材质、面朝向与米制坐标统一写入，构件批次保持独立名称便于重建。
        自动清除退化面，保证脊线收束和倒角不会留下无效三角形。
        """
        if not self.faces:
            return None
        data = bpy.data.meshes.new(PREFIX + self.name + '_网格')
        data.from_pydata(self.verts, [], self.faces)
        keys = list(dict.fromkeys(self.indices))
        for key in keys:
            data.materials.append(MATS[key])
        for poly, key, smooth in zip(data.polygons, self.indices, self.smooth):
            poly.material_index, poly.use_smooth = keys.index(key), smooth
        bm = bmesh.new()
        bm.from_mesh(data)
        bmesh.ops.dissolve_degenerate(bm, edges=list(bm.edges), dist=.000001)
        bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
        bm.to_mesh(data)
        bm.free()
        data.update()
        uv = data.uv_layers.new(name='TileUV')
        for poly in data.polygons:
            axes = [i for i in range(3) if i != max(range(3), key=lambda i: abs(poly.normal[i]))]
            for li in poly.loop_indices:
                p = data.vertices[data.loops[li].vertex_index].co
                uv.data[li].uv = (p[axes[0]]/4, p[axes[1]]/4)
        ob = bpy.data.objects.new(PREFIX + self.name, data)
        COLS[self.group].objects.link(ob)
        ob['主殿样板构件'] = True
        return ob


def surface(side, s, u):
    """
    四坡共享同一条凹曲线，屋角只在外缘逐渐起翘，正脊保持舒展。
    瓦面、檐线和椽子全部由这一函数定位，调整参数时不会各自脱节。
    """
    w = P['ridge_half'] + (P['half_width']-P['ridge_half'])*u
    d = P['half_depth']*u
    base = P['eave_z']-P['toe_lift']
    z = base + (P['ridge_z']-base)*(1-u)**P['curve_power'] + P['toe_lift']*u**8
    z += P['corner_lift']*abs(s)**4*u**3
    x, y = [(s*w, -d), (w, s*d), (-s*w, d), (-w, -s*d)][side]
    return Vector((x, CY+y, z))


def roof_height(x, y):
    """
    从平面坐标反求屋面高度，为斗拱上承和檩条提供实际接触标高。
    边坡与正坡使用相同的解析曲面，角部不使用会穿出瓦面的统一高度。
    """
    uy = abs(y-CY)/P['half_depth']
    ux = max(0, (abs(x)-P['ridge_half'])/(P['half_width']-P['ridge_half']))
    u = max(ux, uy)
    if uy >= ux:
        s = x/(P['ridge_half']+(P['half_width']-P['ridge_half'])*u)
        return surface(0, s, u).z
    return surface(1, (y-CY)/(P['half_depth']*u), u).z


def remove_old_upper_structure():
    """
    历史导出把主殿与远处亭廊合在同一对象内，因此按连通构件的世界边界筛选。
    只删除主殿上部木构与屋面，跨范围构件直接报错，防止误伤其他建筑。
    """
    wooden = ('朱红木构', '哑金', '藻井', '琉璃瓦')
    for ob in list(SCENE.objects):
        if ob.type != 'MESH' or ob.name.startswith(PREFIX):
            continue
        materials = [m.name if m else '' for m in ob.data.materials]
        if not any(any(word in name for word in wooden) for name in materials):
            continue
        corners = [ob.matrix_world @ Vector(p) for p in ob.bound_box]
        if max(p.z for p in corners) < 78.4 or max(p.y for p in corners) < 215:
            continue
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        pending = set(bm.verts)
        remove = []
        while pending:
            stack = [pending.pop()]
            connected = set(stack)
            while stack:
                for edge in stack.pop().link_edges:
                    for v in edge.verts:
                        if v in pending:
                            pending.remove(v)
                            connected.add(v)
                            stack.append(v)
            points = [ob.matrix_world @ v.co for v in connected]
            inside = [abs(p.x)<132 and 210<p.y<381 and 78.4<p.z<160 for p in points]
            if all(inside):
                remove.extend(connected)
            elif any(inside):
                raise RuntimeError('主殿替换边界穿过了连续构件：' + ob.name)
        if len(remove) == len(bm.verts):
            REPORT['removed_objects'].append(ob.name)
            bm.free()
            bpy.data.objects.remove(ob, do_unlink=True)
        elif remove:
            REPORT['trimmed_objects'].append(dict(name=ob.name, vertices=len(remove)))
            ob.data = ob.data.copy()
            bmesh.ops.delete(bm, geom=remove, context='VERTS')
            bm.to_mesh(ob.data)
            bm.free()
        else:
            bm.free()


def roof():
    """
    单层庑殿屋顶采用实体壳、分行筒瓦、瓦当与双层檐板，保留清楚的轻重关系。
    主脊与四条垂脊配少量螭吻和脊钉，金色集中在轮廓而不覆盖大面积瓦面。
    """
    shell = Mesh('单檐庑殿_屋面', 'roof')
    ribs = Mesh('分行筒瓦与瓦当', 'roof')
    edges = Mesh('垂脊正脊与螭吻', 'roof')
    frame = Mesh('檐板连檐与椽架', 'frame')
    count, rings = 256, 44
    verts, faces = [], []
    for lower in (0, 1):
        for j in range(rings+1):
            u = .001 + .999*j/rings
            for side in range(4):
                for i in range(count//4):
                    verts.append(surface(side, -1+2*i/(count//4), u)-Vector((0, 0, lower*P['shell_thickness'])))
    layer = count*(rings+1)
    for j in range(rings):
        for i in range(count):
            a, b = j*count+i, j*count+(i+1)%count
            faces.extend([(a, b, b+count, a+count), (a+layer+count, b+layer+count, b+layer, a+layer)])
    for j in (0, rings):
        for i in range(count):
            a, b = j*count+i, j*count+(i+1)%count
            faces.append((a, b, b+layer, a+layer))
    shell.add(verts, faces, 'roof', True)
    for side in range(4):
        n = 202 if side%2 == 0 else 122
        for i in range(n):
            s = -1 + 2*(i+.5)/n
            # 瓦垄沿曲率均匀取样，六边截面只保留真正参与轮廓和高光的分辨率。
            # 分段数量按主殿尺寸控制，避免远景细分占用过多网页模型体积。
            points = [surface(side, s, .035+.965*j/24)+Vector((0, 0, .12)) for j in range(25)]
            ribs.tube(points, .255, 'tile' if i%5 else 'tile_alt', 6)
            end = points[-1]
            direction = (points[-1]-points[-2]).normalized()
            ribs.tube([end-direction*.16, end+direction*.20], .38, 'gold_dark', 10)
            if i%2 == 0:
                points = [surface(side, s, .60+.40*j/12)-Vector((0, 0, 1.18)) for j in range(13)]
                frame.tube(points, .34, 'wood', 6)
                frame.tube([points[-1]-direction*.1, points[-1]+direction*.12], .36, 'gold', 8)
        for j in range(1, 36):
            u = j/36
            ribs.tube([surface(side, -1+2*i/64, u)+Vector((0, 0, .03)) for i in range(65)], .045, 'roof_seam', 4)
        edge = [surface(side, -1+2*i/80, 1) for i in range(81)]
        for offset, radius, mat in ((.03, .19, 'gold'), (-.58, .29, 'wood'), (-1.18, .16, 'gold_dark')):
            frame.tube([p+Vector((0, 0, offset)) for p in edge], radius, mat, 8)
        for u in (.77, .89):
            frame.tube([surface(side, -1+2*i/56, u)-Vector((0, 0, 1.55)) for i in range(57)], .52, 'wood', 8)
        ridge = [surface(side, 1, .035+.965*j/60)+Vector((0, 0, .42)) for j in range(61)]
        edges.tube(ridge, .63, 'gold_dark', 10)
        edges.tube([p+Vector((0, 0, .45)) for p in ridge], .16, 'gold', 8)
        for u in (.65, .74, .83, .91):
            p = surface(side, 1, u)+Vector((0, 0, .65))
            edges.lathe(p, [(0,.6), (.45,.65), (.9,.34), (1.55,.18), (1.85,.02)], 'gold_dark', 12)
    edges.tube([(x, CY, P['ridge_z']+.7+.65*(abs(x)/72)**8) for x in range(-72,73,2)], 1.0, 'gold_dark', 12)
    for z, radius in ((P['ridge_z']+.12,.18),(P['ridge_z']+1.53,.23)):
        edges.tube([(-73,CY,z),(73,CY,z)], radius, 'gold', 8)
    for sign in (-1, 1):
        origin = Vector((sign*70, CY, P['ridge_z']+.7))
        spine = [origin+Vector((sign*x, 0, z)) for x,z in [(0,0),(1.2,2.2),(3.3,4.0),(4.4,6.6),(3.5,9.0),(1.5,10.3),(-.3,9.8),(-1.1,8.4)]]
        edges.tube(spine, [1.3,1.65,1.5,1.22,.95,.63,.40,.12], 'gold_dark', 12)
        for offset in (-1,1):
            edges.tube([p+Vector((0,offset*.85,.18)) for p in spine[:6]], .16, 'gold', 8)
        for i in range(5):
            p = origin+Vector((sign*(1.2+i*.58),0,1.3+i*1.1))
            edges.profile([(0,0),(-sign*2.6,1.0),(-sign*3.6,2.8),(-sign*.2,1.65)], .55, 'gold', p)
    for builder in (shell,ribs,edges,frame):
        builder.finish()


def open_side_colonnades():
    """
    移除白模阶段留下的两块侧向半高屏墙，让外圈石柱形成通透回廊。
    按原屏墙的精确尺寸识别连通块，主殿后屏墙、月门与其他石构继续保留。
    """
    removed=0
    for ob in list(SCENE.objects):
        if ob.type!='MESH' or ob.name.startswith(PREFIX):
            continue
        if not any(m and '白玉_台基石构' in m.name for m in ob.data.materials):
            continue
        points=[ob.matrix_world@Vector(p) for p in ob.bound_box]
        if max(p.y for p in points)<287 or max(p.z for p in points)<59:
            continue
        bm=bmesh.new()
        bm.from_mesh(ob.data)
        pending=set(bm.verts)
        delete=[]
        while pending:
            stack=[pending.pop()]
            group=set(stack)
            while stack:
                for edge in stack.pop().link_edges:
                    for v in edge.verts:
                        if v in pending:
                            pending.remove(v)
                            group.add(v)
                            stack.append(v)
            coords=[ob.matrix_world@v.co for v in group]
            low=[min(p[i] for p in coords) for i in range(3)]
            high=[max(p[i] for p in coords) for i in range(3)]
            if (abs(abs((low[0]+high[0])/2)-90)<.05 and abs(high[0]-low[0]-2.6)<.05
                    and abs(low[1]-288)<.05 and abs(high[1]-338)<.05
                    and abs(low[2]-36)<.05 and abs(high[2]-60)<.05):
                delete.extend(group)
                removed+=1
        if len(delete)==len(bm.verts):
            bm.free()
            bpy.data.objects.remove(ob,do_unlink=True)
        elif delete:
            ob.data=ob.data.copy()
            bmesh.ops.delete(bm,geom=delete,context='VERTS')
            bm.to_mesh(ob.data)
            bm.free()
        else:
            bm.free()
    REPORT['side_screenwalls_removed']=removed


def painted_beam(builder, a, b):
    """
    额枋按开间分段，朱漆外框、黛青画心与金色回纹构成可辨识的彩画层。
    装饰位于真实梁枋外侧，不使用悬空的贴片或单独一整条色带。
    """
    a,b = Vector(a),Vector(b)
    mid=(a+b)/2
    angle=math.atan2(b.y-a.y,b.x-a.x)
    length=(b-a).length
    builder.box((mid.x,mid.y,82.3),(length+1.3,3.6,4.4),'wood',.12,angle)
    normal=Vector((math.sin(angle),-math.cos(angle),0))
    along=(b-a).normalized()
    for side in (-1,1):
        front=mid+normal*side*1.87
        builder.box((front.x,front.y,82.4),(length-3.0,.24,2.4),'panel',.03,angle)
        for z in (80.55,81.08,83.69,84.17):
            builder.box((front.x,front.y,z),(length+.25,.26,.15),'gold',.025,angle)
        count=max(1,round(length/15))
        for i in range(count):
            center=front+along*((i+.5)*length/count-length/2)
            diamond=[(-2.0,0),(0,.78),(2,0),(0,-.78),(-2,0)]
            builder.tube([center+along*x+normal*side*.18+Vector((0,0,82.4+z)) for x,z in diamond], .10,'gold',6)
            for sign in (-1,1):
                path=[(sign*2.6,-.62),(sign*5.4,-.62),(sign*5.4,.62),(sign*3.0,.62),(sign*3.0,.08),(sign*4.3,.08)]
                builder.tube([center+along*x+normal*side*.18+Vector((0,0,82.4+z)) for x,z in path],.085,'gold',6)


def brackets_and_beams():
    """
    以原柱网为基础重建额枋与三跳斗拱，补间攒沿立面形成连续、有透空的承托层。
    每攒的上承件依照屋底高度收束，既能看到木构层次，也不会穿破瓦面。
    """
    beams=Mesh('朱漆额枋与金线彩画','frame')
    brackets=Mesh('柱头补间三跳斗拱','frame')
    support=Mesh('穿插檩梁与随坡上承','frame')
    xs=[-90,-60,-30,30,60,90]
    ys=[245,278.333333,311.666667,345]
    for y in (245,345):
        for a,b in zip(xs,xs[1:]):
            painted_beam(beams,(a,y,0),(b,y,0))
    for x in (-90,90):
        for a,b in zip(ys,ys[1:]):
            painted_beam(beams,(x,a,0),(x,b,0))
    positions=[]
    for y,angle in ((245,0),(345,math.pi)):
        positions.extend((x,y,angle) for x in range(-90,91,10))
    for x,angle in ((-90,-math.pi/2),(90,math.pi/2)):
        positions.extend((x,245+i*100/12,angle) for i in range(1,12))
    for index,(x,y,angle) in enumerate(positions):
        part=Mesh('临时斗拱','frame')
        part.box((0,0,.5),(3.5,3.5,1),'wood',.12)
        part.box((0,0,1.07),(4.05,3.8,.26),'gold_dark',.04)
        for tier,(length,z) in enumerate(((6.8,1.35),(8.6,2.7),(10.4,4.05))):
            profile=[(-length/2,z+.75),(-length/2,z+.18),(-length*.32,z+.04),
                     (-length*.16,z-.40),(length*.16,z-.40),(length*.32,z+.04),
                     (length/2,z+.18),(length/2,z+.75)]
            part.profile(profile,1.25,'wood',angle=(tier%2)*math.pi/2)
            for sign in (-1,1):
                cx,cy=(sign*length*.36,0) if tier%2==0 else (0,sign*length*.36)
                part.box((cx,cy,z+1.02),(1.5,1.5,.55),'gold_dark',.07)
                part.box((cx,cy,z+1.31),(1.78,1.78,.15),'gold',.025)
        part.box((0,0,5.65),(11.2,2.0,.45),'wood',.08)
        # 挑拱向檐口逐跳伸出，昂嘴微抬并保留可见底面。
        # 下方斜托与上方横拱相交承接，避免整块实心托盘遮蔽木构。
        for sign in (-1,1):
            part.profile([(0,1.0),(sign*5.0,3.1),(sign*6.6,4.0),(sign*6.3,4.7),(0,2.3)],1.12,'wood',angle=math.pi/2)
            part.box((0,sign*5.4,4.15),(2.8,1.5,.5),'gold_dark',.04)
        c,s=math.cos(angle),math.sin(angle)
        world=[]
        for vx,vy,vz in part.verts:
            wx,wy=x+vx*c-vy*s,y+vx*s+vy*c
            world.append((wx,wy,min(84.2+vz*1.55,roof_height(wx,wy)-1.65)))
        offset=len(brackets.verts)
        brackets.verts.extend(world)
        brackets.faces.extend(tuple(offset+i for i in face) for face in part.faces)
        brackets.indices.extend(part.indices)
        brackets.smooth.extend(part.smooth)
        top=roof_height(x,y)-1.27
        bottom=min(93.5,top-.45)
        support.box((x,y,(bottom+top)/2),(2.4,2.4,top-bottom),'wood',.04)
    for x in (-90,-60,-30,30,60,90):
        support.box((x,CY,85.2),(2.4,102,1.8),'wood',.08)
        for y in (264,283,307,326):
            top=roof_height(x,y)-1.2
            support.box((x,y,(86+top)/2),(1.8,1.8,top-86),'wood',.06)
    for y in (245,264,283,307,326,345):
        support.tube([(x,y,roof_height(x,y)-1.25) for x in range(-94,95,2)],.64,'wood',8)
    REPORT['bracket_sets']=len(positions)
    for builder in (beams,brackets,support):
        builder.finish()


def columns_and_ceiling():
    """
    石柱只调整径向比例，原柱网、高度与浮雕法线坐标继续沿用。
    新增覆盆、莲瓣柱础和分层藻井，使近景与殿内机位也有完整的建筑尺度。
    """
    stone=Mesh('覆盆莲瓣柱础与柱头','stone')
    ornament=Mesh('柱身浅浮雕与束口','stone')
    cache={}
    shafts=[ob for ob in SCENE.objects if ob.name.startswith('主殿巨柱') and ob.name.endswith('_柱身')]
    for ob in shafts:
        # 已经生成过样板时按新旧比例的比值调整，参数编辑不会再次叠乘。
        # 保留共享柱身网格和两套纹理坐标，支持重复重建及后续局部精修。
        factor=P['column_radius_scale']/ob.get('H01_径向加厚',1.0)
        if abs(factor-1)>1e-8:
            original=ob.data
            if original not in cache:
                data=original.copy()
                for v in data.vertices:
                    v.co.x*=factor
                    v.co.y*=factor
                cache[original]=data
            ob.data=cache[original]
            ob['H01_径向加厚']=P['column_radius_scale']
        x,y=ob.location.x,ob.location.y
        stone.box((x,y,36.35),(10.7,10.7,.7),'stone',.18)
        stone.lathe((x,y,36),[(.7,5.02),(1.1,5.02),(1.28,4.65),(1.72,4.65),
                                     (2.08,4.25),(2.7,4.12),(3.0,4.25),(3.2,4.25)],'jade')
        stone.lathe((x,y,0),[(78.7,3.95),(79.05,4.05),(79.25,4.28),(79.65,4.28),
                                  (80.25,4.85),(80.8,5.02),(81.2,5.02),(81.4,4.6),(82,4.6)],'jade')
        for index in range(20):
            angle=2*math.pi*index/20
            petal=[]
            for j in range(17):
                t=j/16
                a=angle+.135*math.sin(2*math.pi*t)
                r=4.65+.14*math.sin(math.pi*t)
                petal.append((x+r*math.cos(a),y+r*math.sin(a),37.1+1.4*math.sin(math.pi*t)))
            ornament.tube(petal,.085,'jade',5)
        # 浅雕以错落卷云强调大柱体量，雕刻深度远小于柱径。
        # 大部分柱身仍留素面，避免把整根柱子包成高反差纹理柱。
        for group in range(3):
            for side in range(2):
                points=[]
                for j in range(33):
                    t=j/32
                    spiral=math.pi*3.2*t
                    shrink=1-t*.82
                    a=side*math.pi+group*.62+.30*shrink*math.sin(spiral)
                    z=46+group*10+3.4*shrink*math.cos(spiral)
                    r=(3.6+(3.312-3.6)*(z-37.6)/42.8)*P['column_radius_scale']+.035
                    points.append((x+r*math.cos(a),y+r*math.sin(a),z))
                ornament.tube(points,.115,'jade',5)
    # 全量重建和单独藻井更新共用同一构建器，避免下一次重建退回稀疏圆环素板。
    # 模块共享当前材质表、集合和网格工具，不改柱网或主殿以外的场景数据。
    from hall_ceiling import build_ceiling
    build_ceiling(sys.modules[__name__])
    REPORT['columns']=len(shafts)
    for builder in (stone,ornament):
        builder.finish()


def terrace():
    """
    在主殿最高层台基加密石栏、须弥座腰线和浅刻板面，建立清晰的落地关系。
    正面中央七十米台阶口保持畅通，不添加跨越原台阶的挡板或门槛。
    """
    rails=Mesh('主殿台基石栏与须弥腰线','stone')
    # 原石栏与新栏位于同一条边线，仅清除这一层可确认的旧构件。
    # 合并批次中的其他台基仍保留，新增栏板覆盖原本纤细的边缘横档。
    for ob in list(SCENE.objects):
        if ob.name.startswith('V06_台基3') and '护栏' in ob.name:
            bpy.data.objects.remove(ob,do_unlink=True)
    paths=[((-119,234),(-35,234)),((35,234),(119,234)),
           ((-119,234),(-119,365)),((119,234),(119,365)),((-119,365),(119,365))]
    posts=set()
    for a,b in paths:
        va,vb=Vector((*a,0)),Vector((*b,0))
        length=(vb-va).length
        along=(vb-va).normalized()
        angle=math.atan2(along.y,along.x)
        segments=math.ceil(length/7)
        for i in range(segments+1):
            p=va+(vb-va)*i/segments
            key=(round(p.x,4),round(p.y,4))
            if key in posts:
                continue
            posts.add(key)
            rails.box((p.x,p.y,36.2),(1.45,1.45,.4),'stone',.08)
            rails.box((p.x,p.y,37.85),(1.03,1.03,3.1),'jade',.10)
            rails.lathe((p.x,p.y,0),[(39.1,.65),(39.35,.74),(39.58,.48),(39.9,.58),(40.2,.32),(40.38,.02)],'jade',16)
        for i in range(segments):
            p=va+(vb-va)*(i+.5)/segments
            span=length/segments-1.1
            for z,width,height in ((36.65,.55,.35),(39.03,.70,.43),(37.35,.35,.25)):
                rails.box((p.x,p.y,z),(span,width,height),'jade',.06,angle)
            for offset in (-.31,0,.31):
                q=p+along*(offset*span)
                rails.box((q.x,q.y,38.2),(.28,.40,1.43),'jade',.04,angle)
            for sign in (-1,1):
                q=p+along*sign*span*.16
                rails.tube([q+along*(.7*math.cos(t*math.tau/24))+Vector((0,0,38.16+.58*math.sin(t*math.tau/24))) for t in range(25)],.10,'jade',5)
    for sign in (-1,1):
        for z,overhang,height in ((25.0,.3,.55),(27,.15,.45),(33.7,.35,.40),(34.7,.45,.38)):
            rails.box((sign*(120+overhang),300,z),(.55,132,height),'jade',.06)
        for y in range(241,364,9):
            rails.box((sign*120.24,y,30.4),(.26,7.5,4.8),'stone',.06)
            for z in (28.25,32.55):
                rails.box((sign*120.40,y,z),(.22,6.9,.15),'jade',.025)
    rails.finish()


def protected_digest():
    """
    记录自然环境、人物和相机的内容摘要，用于确认本轮修改保持在主殿范围。
    只计算实际数据与变换，不将对象遍历顺序计入摘要。
    """
    digest=hashlib.sha256()
    for ob in sorted(SCENE.objects,key=lambda item:item.name):
        protected=ob.type=='CAMERA' or any(c.name.startswith(('01','09','10','17_','19_V09_长袍人物')) for c in ob.users_collection)
        if not protected:
            continue
        digest.update(ob.name.encode())
        digest.update(str([list(row) for row in ob.matrix_world]).encode())
        if ob.type=='MESH':
            digest.update(str([(tuple(v.co)) for v in ob.data.vertices]).encode())
    return digest.hexdigest()


def main():
    """
    首次执行保存可回退工程，后续重建只替换带版本前缀的样板构件。
    完成后保存可编辑主工程，样板构件单独归组供直接用 Blender 调整。
    """
    qa=ROOT/'qa'
    qa.mkdir(exist_ok=True)
    backup=qa/'before-hall-h01'
    backup.mkdir(exist_ok=True)
    if not (backup/'HeavenlyPalace_WebAssets_v01.blend').exists():
        shutil.copy2(bpy.data.filepath,backup/'HeavenlyPalace_WebAssets_v01.blend')
    restore_space()
    before=protected_digest()
    for ob in list(SCENE.objects):
        if ob.name.startswith(PREFIX):
            bpy.data.objects.remove(ob,do_unlink=True)
    for key,title in [('roof','屋面瓦作'),('frame','梁架斗拱彩画'),('stone','石柱台基')]:
        name='04H_主殿样板_'+title
        col=bpy.data.collections.get(name)
        if col is None:
            col=bpy.data.collections.new(name)
            SCENE.collection.children.link(col)
        COLS[key]=col
    material('roof','青灰屋面',(.027,.053,.058),.46,.10)
    material('tile','青釉筒瓦',(.042,.082,.088),.32,.17)
    material('tile_alt','釉瓦窑色',(.046,.073,.072),.39,.12)
    material('roof_seam','瓦缝暗色',(.016,.029,.030),.62)
    material('wood','朱漆木构',(.25,.043,.019),.38)
    material('panel','黛青彩画底',(.017,.068,.077),.42)
    material('gold','鎏金细饰',(.60,.335,.09),.31,.72)
    material('gold_dark','古金承斗与脊饰',(.36,.17,.038),.40,.65)
    material('jade','温润白玉',(.70,.68,.61),.36)
    material('stone','台基暖白石',(.56,.54,.49),.57)
    if not SCENE.get('主殿样板版本'):
        remove_old_upper_structure()
    open_side_colonnades()
    print('HALL_清理完成',flush=True)
    roof()
    print('HALL_屋顶完成',flush=True)
    brackets_and_beams()
    columns_and_ceiling()
    terrace()
    bpy.context.view_layer.update()
    assert protected_digest()==before,'主殿以外的受保护内容发生变化。'
    SCENE['主殿样板版本']='h01'
    SCENE['主殿样板参数']=json.dumps(P,ensure_ascii=False)
    REPORT['protected_scene_unchanged']=True
    REPORT['objects']=[ob.name for ob in SCENE.objects if ob.name.startswith(PREFIX)]
    REPORT['triangles']=0
    for ob in SCENE.objects:
        if ob.name.startswith(PREFIX) and ob.type=='MESH':
            ob.data.calc_loop_triangles()
            REPORT['triangles']+=len(ob.data.loop_triangles)
    (qa/'main-hall-build.json').write_text(json.dumps(REPORT,ensure_ascii=False,indent=2),encoding='utf-8')
    # 在屋顶、柱身和藻井全部生成后同步空间比例，结构连接使用同一个目标柱网。
    # 下一次完整重建会先恢复基准，因此几何始终可以重复生成。
    apply_space()
    save_web_blend(ROOT/'HeavenlyPalace_WebAssets_v01.blend')
    print('HALL_BUILD_COMPLETE',REPORT['triangles'],flush=True)


if __name__=='__main__':
    main()
