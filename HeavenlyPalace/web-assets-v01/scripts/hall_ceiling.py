"""
以可实例化的朱金藻井模块替换大面积素板，建立退晕、盘龙画心和雕花梁腹。
近景轮廓使用实体浅雕，微小漆纹由物理贴图承担，所有构件继续走正式网页导出。
"""
import math
import bpy
from mathutils import Vector
from hall_ceiling_materials import create_ceiling_materials

REVISION = 'ceiling-c02'
PREFIX = 'H01_C02_'


def relief(builder, points, z, radius, material='c02_gold', flatten=.46):
    """
    将圆截面线饰压成贴伏在木面的浅浮雕，避免卷草看起来像悬空的金属电线。
    保留真实侧壁和圆润棱缘，让侧光、遮挡与反射随观察方向自然变化。
    """
    start = len(builder.verts)
    builder.tube([(x, y, z) for x, y in points], radius, material, 6)
    for index in range(start, len(builder.verts)):
        x, y, height = builder.verts[index]
        builder.verts[index] = (x, y, z + (height-z)*flatten)


def leaf(builder, center, length, width, angle, z, material='c02_gold'):
    """
    尖叶由两侧叶缘与中脊组成带底盖的实体，远看形成成片金饰，近看有雕刻起伏。
    每片叶使用少量面，避免把植物装饰转换成高成本的细分曲面。
    """
    c, s = math.cos(angle), math.sin(angle)
    outline = [(0, 0), (.25*length, width*.5), (.65*length, width*.42),
               (length, 0), (.65*length, -width*.42), (.25*length, -width*.5)]
    vertices = [(center[0]+x*c-y*s, center[1]+x*s+y*c, z) for x, y in outline]
    vertices.append((center[0]+length*.48*c, center[1]+length*.48*s, z-.14))
    faces = [(i, (i+1) % 6, 6) for i in range(6)]
    faces.append(tuple(reversed(range(6))))
    builder.add(vertices, faces, material)


def scroll(builder, center, scale, z, angle=0):
    """
    对称卷草同时包含主藤、收紧的涡卷与尖叶，填充画心四隅而保留中央主纹。
    同一图案支持旋转和缩放，使不同开间仍遵循统一的装饰秩序。
    """
    c, s = math.cos(angle), math.sin(angle)
    def world(x, y):
        """
        局部二维纹样统一落到顶棚平面，镜像只作用于图案路径。
        不使用负缩放对象，避免网页实例的面朝向和切线出现翻转。
        """
        return (center[0]+scale*(x*c-y*s), center[1]+scale*(x*s+y*c))
    for sign in (-1, 1):
        points = []
        for j in range(36):
            t = j/35
            phase = -math.pi*.6 + t*math.pi*2.1
            radius = 1.6*(1-.88*t)
            points.append(world(sign*(.85+radius*math.cos(phase)), radius*math.sin(phase)))
        relief(builder, points, z, .115*scale)
        for x, y, direction in ((1.1,-1.28,-.8),(2.15,-.3,.35),(1.65,.85,1.35)):
            leaf(builder, world(sign*x,y), .9*scale, .42*scale,
                 angle+(direction if sign>0 else math.pi-direction), z-.015)
    leaf(builder, world(0,-1.4), scale*1.8, scale*.63, angle+math.pi/2,z)


def dragon(builder, radius, z):
    """
    盘龙使用渐细躯干、鳞脊、四肢、三趾、鹿角和长须组成可辨认的浅浮雕。
    造型按画心半径缩放；主体保留正反面和侧壁，不依赖透明贴片或发光描边。
    """
    scale = radius/6.4
    path = []
    for i in range(100):
        t = i/99
        angle = -.65 + t*math.tau*.91
        r = 5.25-2.8*t + .24*math.sin(t*math.tau*3)
        path.append(Vector((r*math.cos(angle), r*math.sin(angle))))
    radii = [scale*(.08+.51*math.sin(i/99*math.pi*.5)) for i in range(100)]
    relief(builder, [tuple(p*scale) for p in path], z-.08, radii, flatten=.64)
    # 鳞脊与身体方向一致，密度沿尾部递减，避免用均匀圆点代替龙身结构。
    # 鳞片稍低于主脊，在阴影面也能形成可读的金色轮廓与暗缝。
    for i in range(13,94,2):
        tangent = (path[i+1]-path[i-1]).normalized()
        normal = Vector((-tangent.y,tangent.x))
        angle = math.atan2(tangent.y,tangent.x)
        for sign in (-1,1):
            p = (path[i]+normal*sign*.23)*scale
            # 交错鳞片采用细弧而非大尖刺，在龙身上形成连续的鳞甲肌理。
            # 暗金分缝位于压低的圆弧之间，主龙仍以完整躯干轮廓被读出。
            points=[p+scale*(normal*sign*.19*math.sin(t*math.pi)+tangent*(t-.5)*.35)
                    for t in (0,.2,.4,.6,.8,1)]
            relief(builder,[tuple(q) for q in points],z-.43*scale,.048*scale)
        if i%4==1:
            p = (path[i]+normal*.57)*scale
            leaf(builder,p,.27*scale,.16*scale,angle+1.4,z-.07)
    for index, sign in ((32,-1),(49,1),(69,-1),(83,1)):
        p = path[index]
        tangent = (path[index+1]-path[index-1]).normalized()
        normal = Vector((-tangent.y,tangent.x))*sign
        elbow = p+normal*.94-tangent*.32
        palm = elbow+normal*.65+tangent*.58
        relief(builder,[tuple(q*scale) for q in (p,elbow,palm)],z-.13,
               [scale*.27,scale*.18,scale*.13])
        for toe in (-1,0,1):
            root = palm+tangent*toe*.15
            end = root+normal*.50+tangent*toe*.22
            tip = end-tangent*.18+normal*.14
            relief(builder,[tuple(q*scale) for q in (root,end,tip)],z-.15,
                   [scale*.12,scale*.075,scale*.02])
    head = path[-1]
    forward = (path[-1]-path[-3]).normalized()
    side = Vector((-forward.y,forward.x))
    def head_point(x,y):
        """
        龙首细节沿颈部朝向布置，眉骨、吻部、角与须共享同一局部坐标。
        保持图案全部位于盘龙圆框内，避免头部装饰穿过边框。
        """
        return tuple((head+forward*x+side*y)*scale)
    relief(builder,[head_point(-.22,0),head_point(.44,0),head_point(1.12,0)],z-.18,
           [scale*.61,scale*.70,scale*.32],flatten=.78)
    for sign in (-1,1):
        relief(builder,[head_point(-.10,sign*.5),head_point(-.55,sign*.98),
                        head_point(-1.00,sign*1.20),head_point(-1.45,sign*1.13)],
               z-.15,[scale*.19,scale*.15,scale*.10,scale*.025])
        relief(builder,[head_point(-.62,sign*1.0),head_point(-.56,sign*1.45),
                        head_point(-.80,sign*1.66)],z-.15,[scale*.12,scale*.08,scale*.02])
        relief(builder,[head_point(.12,sign*.42),head_point(.52,sign*.49)],
               z-.65*scale,scale*.14,'c02_recess')
        relief(builder,[head_point(.08,sign*.49),head_point(.32,sign*.61),
                        head_point(.64,sign*.49)],z-.72*scale,scale*.085)
        whisker = [head_point(.85+t*.8,sign*(.35+1.1*t+.3*math.sin(t*math.tau)))
                   for t in [j/21 for j in range(22)]]
        relief(builder,whisker,z-.21,[scale*(.08-.065*j/21) for j in range(22)])
    relief(builder,[head_point(.73,-.22),head_point(1.15,0),head_point(.73,.22)],
           z-.42*scale,scale*.055,'c02_recess')
    # 火珠与环焰位于盘龙留出的中央空白，建立盘绕方向与画心焦点。
    # 小珠采用回转实体；火焰以逐渐变细的曲线收束。
    builder.lathe((.1*scale,.3*scale,z-.12),[(-.40,.02),(-.35,.36),(-.15,.48),(0,.35),(.08,.02)],'c02_gold',20)
    for i in range(7):
        angle = i*math.tau/7
        points = [((.1+( .68+t*.55)*math.cos(angle+t*.7))*scale,
                   (.3+( .68+t*.55)*math.sin(angle+t*.7))*scale) for t in (0,.25,.5,.75,1)]
        relief(builder,points,z-.1,[.11*scale,.10*scale,.08*scale,.05*scale,.012*scale])


def ring(builder, width, height, inset, z, thickness, material):
    """
    矩形边框由四根真实方材围合，中央完全留空，形成可见的层间遮挡。
    边框高度逐级上升，替代旧版本几条悬空的平面金线。
    """
    w,h = width-2*inset,height-2*inset
    for sign in (-1,1):
        builder.box((0,sign*(h-thickness)/2,z),(w,thickness,.40),material,.035)
        builder.box((sign*(w-thickness)/2,0,z),(thickness,h-2*thickness,.40),material,.035)


def cassette(hall, width):
    """
    单格藻井保留五级朱金退晕、连续纹带、盘龙团纹及四角卷草。
    大开间另外设置两侧团花，使中轴主纹与侧翼装饰有明确主次。
    """
    structure = hall.Mesh(f'C02_{width}米开间_五重退晕木作','frame')
    carving = hall.Mesh(f'C02_{width}米开间_盘龙卷草浅雕','frame')
    pattern = hall.Mesh(f'C02_{width}米开间_金地彩画','frame')
    height=30
    # 通长背衬跨到开间中心线，与相邻背衬搭接，封住井字梁侧的安装缝。
    # 下方五级退晕仍保持真实空腔，仰视不会透过边缝看到屋架背面。
    structure.box((0,0,85.02),(width+3.02,33.36,.36),'c02_recess',0)
    # 画心以连续细金锦地承接中等尺度浅雕，避免主纹周围再次出现整片素色空板。
    # 纹样周期远小于盘龙和边框，只作为次级层次，不替代雕刻的真实厚度。
    structure.box((0,0,84.55),(width-7.7,height-7.7,.6),'c02_pattern',.06)
    for tier in range(5):
        inset=.12+tier*.79
        z=80.65+tier*.78
        ring(structure,width,height,inset,z,.84,'c02_lacquer' if tier%2==0 else 'c02_recess')
        ring(carving,width,height,inset+.06,z-.24,.15,'c02_gold')
        # 阶梯之间用实体竖向牙板封合，既有进深也不会从缝隙看到屋架背面。
        # 中间一级的贴金牙板与末级连续纹带共同承接小尺度装饰。
        for sign in (-1,1):
            w,h=width-2*inset,height-2*inset
            pattern.box((0,sign*(h/2-.79),z+.28),(w-1.15,.23,.82),'c02_pattern',.02)
            pattern.box((sign*(w/2-.79),0,z+.28),(.23,h-1.2,.82),'c02_pattern',.02)
        if tier in (0,2):
            for along_width in (True,False):
                length=(width if along_width else height)-2*inset-2
                count=max(1,round(length/1.6))
                for i in range(count):
                    offset=(i+.5)*length/count-length/2
                    for sign in (-1,1):
                        x,y=(offset,sign*(height/2-inset-.43)) if along_width else (sign*(width/2-inset-.43),offset)
                        carving.box((x,y,z-.24),(.35,.35,.16),'c02_gold',.045,math.pi/4)
    radius=7.1 if width==27 else 8.05
    structure.lathe((0,0,84.16),[(0,radius+.42),(.23,radius+.42)],'c02_recess',96)
    for r in (radius+.04,radius+.40):
        relief(carving,[(r*math.cos(i*math.tau/96),r*math.sin(i*math.tau/96)) for i in range(97)],84.08,.12)
    for i in range(40):
        angle=i*math.tau/40
        leaf(carving,((radius-.3)*math.cos(angle),(radius-.3)*math.sin(angle)),.40,.22,angle,84.03)
    dragon(carving,radius-.85,83.98)
    # 团龙外围以错落云气填充环形空白，云尾均沿盘绕方向排列。
    # 云纹线径小于龙身，形成主体、伴纹和锦地三种可区分的尺度。
    for i in range(10):
        angle=i*math.tau/10+.12
        center=((radius-1.28)*math.cos(angle),(radius-1.28)*math.sin(angle))
        scroll(carving,center,.36,84.05,angle+math.pi/2)
    for xsign in (-1,1):
        for ysign in (-1,1):
            scroll(carving,(xsign*(width/2-6.3),ysign*8.0),.98,84.12,
                   0 if ysign<0 else math.pi)
    if width>30:
        # 中央龙井与两侧花枋分别围合，宽开间也有明确的短跨分格和交叠层次。
        # 所有分格均在原开间内部，面朝下的金边与背后锦地保持独立深度。
        for center,span in ((0,21.4),(-17.6,10.8),(17.6,10.8)):
            for sign in (-1,1):
                structure.box((center,sign*10.5,84.06),(span,.48,.36),'c02_recess',.035)
                carving.box((center,sign*10.51,83.83),(span,.105,.10),'c02_gold',.02)
                structure.box((center+sign*span/2,0,84.06),(.48,21.0,.36),'c02_recess',.035)
                carving.box((center+sign*span/2,0,83.83),(.105,21.0,.10),'c02_gold',.02)
        for sign in (-1,1):
            center=sign*17.6
            for dy in (-4.1,4.1):
                scroll(carving,(center,dy),1.75,84.1,0 if dy<0 else math.pi)
            # 侧翼中心以菱花连接上下卷草，不再用突出的整块横条遮断纹样。
            # 细叶沿菱形四角转向，与粗卷草保持同一建筑纹饰语言。
            relief(carving,[(center-2,0),(center,1.1),(center+2,0),(center,-1.1),(center-2,0)],84.0,.11)
            for angle in (0,math.pi/2,math.pi,math.pi*1.5):
                leaf(carving,(center,0),1.0,.35,angle,83.98)
    # 纹样放在画心四角的小块锦地上；漆面留白用于衬托主龙和边框的体量。
    # 每四米平铺的坐标由公共构建器生成，与材质模块的米制约定保持一致。
    for sign in (-1,1):
        pattern.box((0,sign*10.45,84.19),(width-9.4,.78,.18),'c02_pattern',.02)
    return [builder.finish() for builder in (structure,carving,pattern)]


def beam_grid(hall):
    """
    内部井字梁使用足尺梁腹、贴金边和连续彩画，填补相邻藻井之间的空洞。
    附加小斗与牙子集中在交点，保留柱头原有的承重关系与门洞净空。
    """
    builder=hall.Mesh('C02_殿内雕花井字梁与交点小斗','frame')
    xs=(-90,-60,-30,30,60,90)
    ys=(245,278.333333,311.666667,345)
    for x in xs:
        builder.box((x,295,80.1),(2.5,100,2.9),'c02_lacquer',.10)
        builder.box((x,295,78.59),(1.54,99,.16),'c02_pattern',.03)
        for sign in (-1,1):
            builder.box((x+sign*1.26,295,80.1),(.13,99,1.62),'c02_pattern',.025)
            builder.box((x+sign*1.08,295,78.53),(.15,100,.17),'c02_gold',.03)
    for y in ys:
        builder.box((0,y,80.0),(182,2.6,3.0),'c02_lacquer',.10)
        builder.box((0,y,78.44),(181,1.64,.17),'c02_pattern',.02)
        for sign in (-1,1):
            builder.box((0,y+sign*1.32,80.0),(181,.13,1.67),'c02_pattern',.025)
            builder.box((0,y+sign*1.15,78.39),(182,.16,.18),'c02_gold',.025)
    for x in xs:
        for y in ys:
            builder.box((x,y,78.6),(3.65,3.65,.40),'c02_gold',.08)
            builder.box((x,y,78.92),(4.6,3.25,.40),'c02_lacquer',.06)
            builder.box((x,y,79.24),(3.1,4.65,.32),'c02_gold',.06)
    return builder.finish()


def build_ceiling(hall):
    """
    局部重建与完整主殿重建调用同一函数，替换已知旧藻井后创建两种共享开间。
    十二格侧间、三格中央开间共用原型网格，网页导出可以直接生成实例批次。
    """
    old_meshes=set()
    for ob in list(bpy.context.scene.objects):
        if ob.name=='H01_井字梁架与分层藻井' or ob.name.startswith(PREFIX):
            if ob.type=='MESH':
                old_meshes.add(ob.data)
            bpy.data.objects.remove(ob,do_unlink=True)
    # 仅移除本轮替换后已无用户的旧网格，使重复重建的共享网格名称保持稳定。
    # 其他对象仍引用的网格原样保留，不进行全场数据清理。
    for mesh in old_meshes:
        if mesh.users==0:
            bpy.data.meshes.remove(mesh)
    hall.MATS.update(create_ceiling_materials())
    created=[beam_grid(hall)]
    for width,positions in ((27,[(-75,y) for y in (261.67,295,328.33)]+[(-45,y) for y in (261.67,295,328.33)]+
                            [(45,y) for y in (261.67,295,328.33)]+[(75,y) for y in (261.67,295,328.33)]),
                           (57,[(0,y) for y in (261.67,295,328.33)])):
        templates=cassette(hall,width)
        for template in templates:
            for index,(x,y) in enumerate(positions):
                ob=template if index==0 else bpy.data.objects.new(template.name+f'_开间{index+1:02d}',template.data)
                if index:
                    hall.COLS['frame'].objects.link(ob)
                ob.location=(x,y,0)
                ob['藻井版本']=REVISION
                created.append(ob)
    bpy.context.scene['殿内藻井版本']=REVISION
    bpy.context.view_layer.update()
    return created
