"""
建立以米为尺度的共享材质、暖阳冷天光、层叠远山和真实体积云。
此文件由第八版入口载入，所有机位共用同一场景、同一灯光与同一可见性。
"""
MAT={}
control=collection('16_V08_材质坐标与说明')
origin=bpy.data.objects.new('V08_米制纹理原点_一单位一米',None)
control.objects.link(origin)
origin.hide_render=True
origin.empty_display_size=2


# 节点名称使用中文标出实际尺度，方便在着色器编辑器继续修改。
# 统一世界坐标保证同类构件尺度一致，木梁根据最长轴选择纹理方向。
def material(name,color,rough=.5,metal=0):
    m=bpy.data.materials.new('V08_'+name)
    m.use_nodes=True
    m.diffuse_color=(*color,1)
    nodes=m.node_tree.nodes
    nodes.clear()
    out=nodes.new('ShaderNodeOutputMaterial')
    out.location=(920,60)
    bs=nodes.new('ShaderNodeBsdfPrincipled')
    bs.location=(650,60)
    bs.inputs['Base Color'].default_value=(*color,1)
    bs.inputs['Roughness'].default_value=rough
    bs.inputs['Metallic'].default_value=metal
    m.node_tree.links.new(bs.outputs['BSDF'],out.inputs['Surface'])
    m['纹理单位']='米；共享世界坐标或明确尺寸的局部装饰坐标'
    return m,bs


def node(m,kind,label):
    n=m.node_tree.nodes.new(kind)
    n.label=label
    n.name=label
    count=len(m.node_tree.nodes)
    n.location=(-1100+((count-3)%5)*290,520-((count-3)//5)*250)
    return n


def link(m,out,inp):
    m.node_tree.links.new(out,inp)


def coords(m,scale=None,generated=False):
    tc=node(m,'ShaderNodeTexCoord','米制共用坐标' if not generated else '构件局部装饰坐标')
    if not generated:
        tc.object=origin
    source=tc.outputs['Generated' if generated else 'Object']
    if scale:
        v=node(m,'ShaderNodeVectorMath','按米设置各向尺度')
        v.operation='MULTIPLY'
        v.inputs[1].default_value=scale
        link(m,source,v.inputs[0])
        source=v.outputs['Vector']
    return source


def texnoise(m,coord,scale,detail=3,label='自然细微变化'):
    n=node(m,'ShaderNodeTexNoise',label)
    n.inputs['Scale'].default_value=scale
    n.inputs['Detail'].default_value=detail
    n.inputs['Roughness'].default_value=.68
    link(m,coord,n.inputs['Vector'])
    return n.outputs['Fac']


def ramp(m,source,stops,label='颜色与强度范围'):
    n=node(m,'ShaderNodeValToRGB',label)
    for el in list(n.color_ramp.elements)[2:]:
        n.color_ramp.elements.remove(el)
    for i,(position,color) in enumerate(stops):
        el=n.color_ramp.elements[i] if i<2 else n.color_ramp.elements.new(position)
        el.position=position
        el.color=tuple(color) if len(color)==4 else (*color,1)
    link(m,source,n.inputs[0])
    return n.outputs['Color']


def calc(m,operation,a,b=None,label='数值处理'):
    n=node(m,'ShaderNodeMath',label)
    n.operation=operation
    if hasattr(a,'node'):
        link(m,a,n.inputs[0])
    else:
        n.inputs[0].default_value=a
    if b is not None:
        if hasattr(b,'node'):
            link(m,b,n.inputs[1])
        else:
            n.inputs[1].default_value=b
    return n.outputs[0]


def mix(m,factor,a,b,label='层次混合'):
    n=node(m,'ShaderNodeMixRGB',label)
    for i,v in enumerate([factor,a,b]):
        if hasattr(v,'node'):
            link(m,v,n.inputs[i])
        else:
            n.inputs[i].default_value=v
    return n.outputs[0]


def bump(m,bs,source,distance,strength=.3,previous=None):
    n=node(m,'ShaderNodeBump',f'表面起伏{distance:g}米')
    n.inputs['Distance'].default_value=distance
    n.inputs['Strength'].default_value=strength
    link(m,source,n.inputs['Height'])
    if previous:
        link(m,previous,n.inputs['Normal'])
    if bs:
        link(m,n.outputs['Normal'],bs.inputs['Normal'])
    return n.outputs['Normal']


# 玉石用浅灰暖白为主体，少量青灰纹理与亚毫米级反光变化。
# 地面另外叠加四米石板与细接缝，内殿适当降低粗糙度以读出阳光和柱影。
for key,title,rough in [('jade','白玉_柱身栏杆',.3),('stone','白玉_台基石构',.47),('floor','白玉_室外四米石板',.42),('interior','白玉_殿内润泽石板',.255)]:
    m,bs=material(title,(.76,.75,.68),rough)
    c=coords(m,(.7,1.1,.42))
    veins=texnoise(m,c,1.5,4,'米级柔和石纹')
    color=ramp(m,veins,[(.19,(.48,.55,.52)),(.37,(.72,.745,.69)),(.54,(.83,.82,.74)),(.78,(.66,.715,.685))])
    if key in ['floor','interior']:
        br=node(m,'ShaderNodeTexBrick','四米石板_接缝一厘米')
        br.inputs['Scale'].default_value=1
        br.inputs['Brick Width'].default_value=4
        br.inputs['Row Height'].default_value=4
        br.inputs['Mortar Size'].default_value=.009
        br.inputs['Mortar Smooth'].default_value=.008
        br.inputs['Color1'].default_value=(.79,.80,.75,1)
        br.inputs['Color2'].default_value=(.65,.71,.7,1)
        br.inputs['Mortar'].default_value=(.38,.41,.38,1)
        br.offset=0
        link(m,coords(m),br.inputs['Vector'])
        color=mix(m,.23,br.outputs['Color'],color,'石板底色叠加天然纹理')
        n1=bump(m,None,calc(m,'SUBTRACT',1,br.outputs['Fac']),.014,.5)
    else:
        n1=None
    link(m,color,bs.inputs['Base Color'])
    fine=texnoise(m,coords(m),28,2,'毫米至厘米级石质细节')
    bump(m,bs,fine,.006,.24,n1)
    bs.inputs['Coat Weight'].default_value=.16 if key in ['jade','interior'] else .04
    bs.inputs['Coat Roughness'].default_value=.28
    MAT[key]=m


# 木纹沿梁或柱的轴向拉伸，漆色保持朱红并保留暗部纹理。
# 金属只分配给细脊和边线，使用适度粗糙度避免大面积刺眼反射。
for axis,scale in [('x',(.11,5,5)),('y',(5,.11,5)),('z',(5,5,.11))]:
    m,bs=material('朱红木构_顺'+axis+'轴',(.31,.036,.018),.38)
    grain=texnoise(m,coords(m,scale),2.3,3,'木纹沿构件长度延伸')
    link(m,ramp(m,grain,[(.15,(.055,.004,.003)),(.43,(.17,.009,.007)),(.65,(.29,.035,.014)),(.88,(.16,.008,.006))]),bs.inputs['Base Color'])
    link(m,ramp(m,grain,[(.1,(.3,.3,.3)),(.9,(.47,.47,.47))]),bs.inputs['Roughness'])
    bump(m,bs,grain,.012,.22)
    bs.inputs['Coat Weight'].default_value=.22
    bs.inputs['Coat Roughness'].default_value=.3
    MAT['wood_'+axis]=m
m,bs=material('哑金_脊线与细金饰',(.52,.3,.083),.3,.78)
fine=texnoise(m,coords(m),37,2,'锤金微细起伏')
link(m,ramp(m,fine,[(.15,(.38,.195,.043)),(.85,(.68,.435,.14))]),bs.inputs['Base Color'])
link(m,ramp(m,fine,[(.1,(.26,.26,.26)),(.9,(.38,.38,.38))]),bs.inputs['Roughness'])
bump(m,bs,fine,.0018,.18)
MAT['gold']=m


# 琉璃瓦的筒瓦间距为六十二厘米，瓦行随屋面高度变化表现叠压。
# 避免新增海量瓦片网格，使用现有屋顶形状与尺度一致的釉面凹凸。
m,bs=material('青绿琉璃瓦_分行釉面',(.013,.085,.09),.36)
c=coords(m)
sep=node(m,'ShaderNodeSeparateXYZ','屋面米制坐标')
link(m,c,sep.inputs[0])
geom=node(m,'ShaderNodeNewGeometry','按坡面选择瓦垄方向')
normal=node(m,'ShaderNodeSeparateXYZ','屋面法线分量')
link(m,geom.outputs['Normal'],normal.inputs[0])
choose=calc(m,'GREATER_THAN',calc(m,'ABSOLUTE',normal.outputs['X']),calc(m,'ABSOLUTE',normal.outputs['Y']))
u=mix(m,choose,sep.outputs['X'],sep.outputs['Y'])
wave=calc(m,'SINE',calc(m,'MULTIPLY',u,math.tau/.62))
course=calc(m,'FRACT',calc(m,'MULTIPLY',sep.outputs['Z'],1/.36))
seam=calc(m,'LESS_THAN',course,.07)
bn=calc(m,'SUBTRACT',calc(m,'MULTIPLY',wave,.8),calc(m,'MULTIPLY',seam,.35))
bump(m,bs,bn,.082,.7)
variation=texnoise(m,coords(m,(.8,.8,1.5)),1.5,2,'釉色自然变化')
col=ramp(m,variation,[(.16,(.005,.023,.033)),(.43,(.009,.061,.075)),(.72,(.024,.139,.141)),(.91,(.045,.17,.146))])
link(m,mix(m,calc(m,'MULTIPLY',seam,.38),col,(.008,.035,.032,1)),bs.inputs['Base Color'])
bs.inputs['Coat Weight'].default_value=.16
bs.inputs['Coat Roughness'].default_value=.3
MAT['roof']=m


# 崖壁同时具有米级裂隙、竖向侵蚀和厘米级粗糙；湿区限定在四条落水附近。
# 材质通过世界位置识别水岸，避免整块岩体统一发黑或统一高光。
m,bs=material('山岩_干面裂隙苔色与湿岸',(.28,.3,.25),.84)
c=coords(m,(.8,.8,.22))
large=texnoise(m,c,.25,4,'四米级竖向岩质')
color=ramp(m,large,[(.17,(.075,.105,.09)),(.36,(.18,.235,.21)),(.55,(.34,.36,.285)),(.78,(.48,.46,.345))])
vor=node(m,'ShaderNodeTexVoronoi','不规则岩石裂隙_约两米')
vor.feature='DISTANCE_TO_EDGE'
vor.inputs['Scale'].default_value=.45
link(m,coords(m,(1,1,.3)),vor.inputs['Vector'])
cleft=calc(m,'LESS_THAN',vor.outputs['Distance'],.027)
color=mix(m,calc(m,'MULTIPLY',cleft,.38),color,(.08,.105,.09,1),'深色裂隙')
position=node(m,'ShaderNodeSeparateXYZ','判断瀑布湿润带')
link(m,coords(m),position.inputs[0])
wet=0
for xx in [-230,232,318,-296]:
    dist=calc(m,'ABSOLUTE',calc(m,'SUBTRACT',position.outputs['X'],xx))
    band=calc(m,'MAXIMUM',calc(m,'SUBTRACT',1,calc(m,'DIVIDE',dist,13)),0)
    wet=calc(m,'MAXIMUM',wet,band)
wet=calc(m,'MULTIPLY',wet,calc(m,'LESS_THAN',position.outputs['Z'],6))
color=mix(m,calc(m,'MULTIPLY',wet,.53),color,(.065,.12,.105,1),'水岸吸水变深')
link(m,color,bs.inputs['Base Color'])
link(m,mix(m,wet,(.85,.85,.85,1),(.36,.36,.36,1)),bs.inputs['Roughness'])
n1=bump(m,None,large,.48,.53)
medium=texnoise(m,coords(m,(1,1,.5)),2.8,3,'三十厘米级岩粒')
n2=bump(m,None,medium,.15,.55,n1)
bump(m,bs,texnoise(m,coords(m),21,2,'厘米级砂粒'),.016,.35,n2)
MAT['rock']=m


# 树皮有纵向块裂与横向细纹，叶簇混入少量暖梢，背光保持透光感。
# 颜色变化由共享材质完成，七百余叶簇继续复用十个网格。
m,bs=material('古松树皮_纵裂苍褐',(.14,.07,.028),.88)
grain=texnoise(m,coords(m,(3.8,3.8,.36)),1,4,'树皮纵向裂纹')
link(m,ramp(m,grain,[(.16,(.026,.018,.011)),(.4,(.095,.052,.023)),(.65,(.26,.14,.055)),(.85,(.39,.24,.11))]),bs.inputs['Base Color'])
n1=bump(m,None,grain,.14,.65)
bump(m,bs,texnoise(m,coords(m),18,2,'树皮细碎鳞片'),.024,.38,n1)
MAT['bark']=m
for i,col in enumerate([(.026,.07,.031),(.056,.125,.045),(.15,.20,.064)]):
    m,bs=material('松针_'+['深绿','中绿','暖梢'][i],col,.65)
    var=texnoise(m,coords(m),1.4,2,'松针小簇色差')
    link(m,ramp(m,var,[(.1,tuple(v*.65 for v in col)),(.9,tuple(v*1.25 for v in col))]),bs.inputs['Base Color'])
    bs.inputs['Subsurface Weight'].default_value=.055
    bs.inputs['Roughness'].default_value=.63
    MAT['leaf'+str(i)]=m


# 水帘用顺重力的流纹、白沫和不齐边缘；下端按高度逐渐透明进入低云。
# 水面仍是第七版连续中心线，不使用流体模拟，也不逐机位改变可见性。
m,bs=material('瀑布_流向水纹白沫与入云消隐',(.42,.65,.67),.18)
c=coords(m,(3.4,2,.12))
flow=texnoise(m,c,1.7,3,'沿重力拉长的水流纹理')
foam=ramp(m,flow,[(.24,(.03,.16,.19)),(.44,(.29,.52,.56)),(.57,(.77,.88,.86)),(.8,(.94,.97,.94))])
link(m,foam,bs.inputs['Base Color'])
bs.inputs['Transmission Weight'].default_value=.17
bs.inputs['IOR'].default_value=1.333
bs.inputs['Coat Weight'].default_value=.22
bump(m,bs,flow,.12,.48)
position=node(m,'ShaderNodeSeparateXYZ','入云高度控制')
link(m,coords(m),position.inputs[0])
fade=node(m,'ShaderNodeMapRange','负二百至负四百米逐渐消隐')
fade.clamp=True
fade.inputs['From Min'].default_value=-410
fade.inputs['From Max'].default_value=-190
link(m,position.outputs['Z'],fade.inputs['Value'])
edge=texnoise(m,coords(m,(2,2,.33)),2,2,'水帘稀疏破边')
opacity=calc(m,'MULTIPLY',fade.outputs['Result'],ramp(m,edge,[(.21,(.16,.16,.16)),(.38,(1,1,1))]))
trans=node(m,'ShaderNodeBsdfTransparent','稀薄水雾透明')
mixsh=node(m,'ShaderNodeMixShader','落水与云雾过渡')
link(m,opacity,mixsh.inputs[0])
link(m,trans.outputs[0],mixsh.inputs[1])
link(m,bs.outputs[0],mixsh.inputs[2])
link(m,mixsh.outputs[0],m.node_tree.nodes.get('Material Output').inputs['Surface'])
MAT['water']=m
m,bs=material('水沫_细散白色泡沫',(.8,.9,.88),.5)
bs.inputs['Subsurface Weight'].default_value=.08
MAT['foam']=m


# 藻井采用深朱红底与局部金色回纹，使殿内梁架具有层次。
# 纹样只是材质装饰，不改变已经确定的天花位置、尺寸或建筑构件。
m,bs=material('藻井_朱漆金线回纹',(.14,.019,.009),.4)
c=coords(m,generated=True)
se=node(m,'ShaderNodeSeparateXYZ','藻井局部平面')
link(m,c,se.inputs[0])
dx=calc(m,'ABSOLUTE',calc(m,'SUBTRACT',se.outputs['X'],.5))
dy=calc(m,'ABSOLUTE',calc(m,'SUBTRACT',se.outputs['Y'],.5))
dist=calc(m,'MAXIMUM',dx,dy)
border=calc(m,'MULTIPLY',calc(m,'GREATER_THAN',dist,.385),calc(m,'LESS_THAN',dist,.465))
lines=calc(m,'LESS_THAN',calc(m,'FRACT',calc(m,'MULTIPLY',dist,60)),.22)
border=calc(m,'MULTIPLY',border,lines)
radius=calc(m,'SQRT',calc(m,'ADD',calc(m,'MULTIPLY',dx,dx),calc(m,'MULTIPLY',dy,dy)))
medallion=calc(m,'MULTIPLY',calc(m,'GREATER_THAN',radius,.262),calc(m,'LESS_THAN',radius,.271))
orn=calc(m,'MAXIMUM',border,medallion)
link(m,mix(m,orn,(.1,.009,.004,1),(.54,.31,.077,1)),bs.inputs['Base Color'])
link(m,calc(m,'MULTIPLY',orn,.7),bs.inputs['Metallic'])
bump(m,bs,orn,.009,.25)
MAT['ceiling']=m


# 材质对应只变更插槽，建筑顶点、变换、相机参数完全不动。
# 同名重复构件引用相同材质，局部方向选择通过对象最长轴判定。
mapping={'V05_石构_暖灰哑光':'stone','V05_门圈柱础_浅石哑光':'jade','V05_门圈分段_微差石色':'jade',
         '白模_浅色檐口柱身':'jade','白模_暖灰石材':'stone','白模_地面分区':'stone','V05_天花板_灰棕哑光':'ceiling',
         'V05_屋面_青灰哑光':'roof','V05_脊与檐边_灰褐哑光':'gold','V05_承托与边线_浅棕哑光':'gold',
         'V07_岩体_灰青':'rock','V07_岩层_浅灰青':'rock','V07_古松树皮_褐灰':'bark','V07_针叶簇_深松绿':'leaf0',
         'V07_针叶簇_灰松绿':'leaf1','V07_针叶簇_浅梢':'leaf2','V07_落水_浅青白':'water','V07_水脊_灰白':'foam'}
assignments={}
for ob in list(S.objects):
    if ob.type!='MESH':
        continue
    for slot in ob.material_slots:
        if slot.material is None:
            continue
        old=slot.material.name
        key=mapping.get(old)
        if old=='V05_木构_沉棕哑光':
            axis='xyz'[max(range(3),key=lambda i:ob.dimensions[i])]
            key='wood_'+axis
        if key in ['stone','jade'] and any(s in ob.name for s in ['压顶板','地坪','广场实体','前庭实体','中轴仪式通带','平台面','桥面','观景台_标高','前庭净空_','前庭侧边通行带_','月门前平台_','入口休息平台']):
            key='interior' if ('台基3_' in ob.name or '主殿' in ob.name) else 'floor'
        if key:
            slot.link='OBJECT'
            slot.material=MAT[key]
            assignments[key]=assignments.get(key,0)+1


# 新远山为分层不规则峰群，方位覆盖主外景和殿内朝南的月门视线。
# 山脚下沉进云层，避免可见封底；远景颜色递进以控制空间层次。
farcol=collection('17_V08_层叠远山')
for depth,col in enumerate([(.24,.335,.35),(.31,.425,.47),(.43,.55,.61)]):
    m,bs=material('远山_空气透视_'+str(depth+1),col,.96)
    var=texnoise(m,coords(m,(1,1,.4)),.017,3,'远山大型岩褶')
    link(m,ramp(m,var,[(.15,tuple(v*.7 for v in col)),(.85,tuple(min(v*1.16,1) for v in col))]),bs.inputs['Base Color'])
    bs.inputs['Emission Color'].default_value=(*col,1)
    bs.inputs['Emission Strength'].default_value=.10+depth*.1
    MAT['far'+str(depth)]=m


def peak(name,center,radius,height,seed,mat):
    rng=random.Random(seed)
    x,y,base=center
    rx,ry=radius
    sides=19
    levels=[(0,1.25),(.18,1.13),(.34,.96),(.49,1.02),(.63,.77),(.79,.67),(.91,.49),(1,.20)]
    vv=[]
    lean=(rng.uniform(-.3,.3)*rx,rng.uniform(-.3,.3)*ry)
    for j,(t,w) in enumerate(levels):
        for k in range(sides):
            a=math.tau*k/sides
            f=1+.24*math.sin(a*5+seed)+rng.uniform(-.12,.12)
            vv.append((x+rx*math.cos(a)*w*f+lean[0]*t,y+ry*math.sin(a)*w*f+lean[1]*t,
                       base+height*t+height*rng.uniform(-.04,.03)))
    ff=[tuple(reversed(range(sides))),tuple(range(7*sides,8*sides))]
    for j in range(7):
        for k in range(sides):
            a=j*sides+k
            b=j*sides+(k+1)%sides
            ff.extend([(a,b,b+sides),(a,b+sides,a+sides)])
    return mesh(name,vv,ff,farcol,mat)


rng=random.Random(8452)
for band,(distance,count) in enumerate([(1600,18),(3000,24),(4900,30)]):
    for i in range(count):
        a=math.tau*i/count+rng.uniform(-.085,.085)
        x,y=math.cos(a)*distance,math.sin(a)*distance
        if y<-700:
            if band==0:
                continue
            base=220 if band==1 else 420
            height=rng.uniform(350,700) if band==1 else rng.uniform(500,980)
        else:
            base=-460
            height=rng.uniform(250,520) if band==0 else rng.uniform(320,660)
        if abs(x)<500 and y>0:
            height*=.72
        radius=(rng.uniform(58,122)*(1+band*.35),rng.uniform(52,119)*(1+band*.3))
        ob=peak(f'V08_远山层{band+1}_{i:02}',(x,y,base),radius,height,8500+band*100+i,MAT['far'+str(band)])
        for shoulder in range(2):
            peak(f'V08_远山层{band+1}_{i:02}_肩峰{shoulder}',(x+radius[0]*rng.uniform(-1.4,1.4),y+radius[1]*rng.uniform(-.8,.8),base),
                 (radius[0]*.62,radius[1]*.67),height*rng.uniform(.63,.84),8750+band*100+i*3+shoulder,MAT['far'+str(band)])


# 每个云团有有界密度和分形噪声，实体网格仅作为体积容器，不渲染硬表面。
# 密度随椭球边界平滑衰减，近云低于广场，远云逐步延伸至月门外的天际。
def cloud_material(name,density,detail_scale):
    m=bpy.data.materials.new('V08_'+name)
    m.use_nodes=True
    m.node_tree.nodes.clear()
    m.cycles.emission_sampling='NONE'
    m.cycles.volume_sampling='MULTIPLE_IMPORTANCE'
    m.cycles.volume_step_rate=.35
    out=node(m,'ShaderNodeOutputMaterial','云体积输出')
    vol=node(m,'ShaderNodeVolumePrincipled','真实散射云雾')
    vol.inputs['Color'].default_value=(.88,.935,1,1)
    vol.inputs['Anisotropy'].default_value=.22
    link(m,vol.outputs['Volume'],out.inputs['Volume'])
    tc=coords(m,generated=True)
    v=node(m,'ShaderNodeVectorMath','椭球体积边界')
    v.operation='SUBTRACT'
    v.inputs[1].default_value=(.5,.5,.5)
    link(m,tc,v.inputs[0])
    length=node(m,'ShaderNodeVectorMath','边界距离')
    length.operation='LENGTH'
    link(m,v.outputs[0],length.inputs[0])
    coarse=texnoise(m,tc,detail_scale,2.2,'云团翻滚层次')
    surface=calc(m,'ADD',.34,calc(m,'MULTIPLY',coarse,.25))
    boundary=calc(m,'MINIMUM',calc(m,'MAXIMUM',calc(m,'MULTIPLY',calc(m,'SUBTRACT',surface,length.outputs['Value']),35),0),1)
    d=calc(m,'MULTIPLY',boundary,density)
    link(m,d,vol.inputs['Density'])
    vol.inputs['Emission Color'].default_value=(.76,.84,1,1)
    link(m,calc(m,'MULTIPLY',d,.15),vol.inputs['Emission Strength'])
    m['资源策略']='低面数容器；共享体积材质；有限步进；不使用模拟缓存'
    return m


cloudmat=cloud_material('云海_分形体积云',.052,5)
mistmat=cloud_material('瀑布_稀薄局部水雾',.0018,4)
cloudcol=collection('18_V08_可渲染云海与水雾')
cubeverts=[(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]
cubefaces=[(0,3,2,1),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
clouddata=mesh('V08_云体积共享容器',cubeverts,cubefaces,cloudcol,cloudmat)
data=clouddata.data
bpy.data.objects.remove(clouddata,do_unlink=True)


def cloud(name,location,scale,mat=None):
    ob=bpy.data.objects.new(name,data)
    cloudcol.objects.link(ob)
    ob.location=location
    ob.scale=scale
    if mat:
        ob.material_slots[0].link='OBJECT'
        ob.material_slots[0].material=mat
    ob['云雾说明']='真实体积散射；不按相机隐藏；广场和门洞上方留空'
    return ob


rng=random.Random(8538)
cloudrecords=[]
for band,(distance,count,wide,tall) in enumerate([(540,11,295,135),(1050,13,490,165),(1950,16,730,185),(3600,18,1130,300),(6100,18,1550,440)]):
    for i in range(count):
        a=math.tau*i/count+rng.uniform(-.07,.07)
        x=distance*math.cos(a)
        y=distance*math.sin(a)
        z=-300+rng.uniform(-45,35)
        if y<-2100:
            z=440 if band==3 else 690
        scale=(wide*rng.uniform(.82,1.2),wide*rng.uniform(.7,1.12),tall*rng.uniform(.8,1.1))
        cloud(f'V08_云海层{band+1}_{i:02}',(x,y,z),scale)
        cloudrecords.append({'position':[x,y,z],'scale':list(scale)})
cloud('V08_岛底云床',(0,80,-350),(590,790,165))
rng=random.Random(8975)
for i in range(20):
    a=math.tau*i/20
    distance=660 if i%2 else 450
    cloud(f'V08_近景翻涌云峰_{i:02}',(distance*math.cos(a),distance*math.sin(a),-260+rng.uniform(-25,35)),
          (rng.uniform(80,140),rng.uniform(75,130),rng.uniform(70,125)))
for i in range(7):
    cloud(f'V08_月门远天云团_{i}',(-2300+i*760,-7100,1480+(i%3)*130),(660,580,230))
for ob in [o for o in S.objects if '连续可编辑水体' in o.name]:
    path=json.loads(ob['水流中心线'])
    for p in path:
        if -220<p[2]<-208:
            cloud('V08_'+ob.name+'_入云水雾',(p[0],p[1]-1,-230),(27,24,54),mistmat)
            break
    for j in range(5,len(path)-1):
        if abs(path[j+1][2]-path[j][2])<.5 and path[j][2]<-40:
            p=path[j]
            cloud('V08_'+ob.name+'_跌水轻雾',(p[0],p[1]-2,p[2]+2),(11,12,6),mistmat)
            break


# 采用一个暖色斜阳和统一冷天空，殿内固定补光从两侧与梁下补回细节。
# 不更改曝光来适应单个机位，室内外均使用同一色彩管理和灯光能量。
lights=next(c for c in S.collection.children if c.name.startswith('13_'))
for ob in list(lights.all_objects):
    if ob.type=='LIGHT':
        ob.hide_render=True
newlights=collection('19_V08_暖阳冷天光统一照明')


def light(name,kind,loc,target,color,power,size):
    ld=bpy.data.lights.new(name,kind)
    ob=bpy.data.objects.new(name,ld)
    newlights.objects.link(ob)
    ob.location=loc
    ob.rotation_euler=(Vector(target)-ob.location).to_track_quat('-Z','Y').to_euler()
    ld.color=color
    ld.energy=power
    if kind=='AREA':
        ld.shape='DISK'
        ld.size=size
    else:
        ld.angle=size
    return ob


light('V08_暖色斜射阳光','SUN',(-650,-1000,830),(0,70,0),(1,.79,.53),3.1,.045)
light('V08_殿前天空反弹','AREA',(0,230,70),(0,305,61),(.68,.81,1),69000,65)
light('V08_殿内梁架柔光','AREA',(0,310,69),(0,293,91),(1,.78,.55),35000,75)
light('V08_殿内侧向冷补','AREA',(-72,298,62),(10,299,49),(.68,.82,1),34000,42)
world=bpy.data.worlds.new('V08_清晨蓝金天空')
S.world=world
world.use_nodes=True
nodes=world.node_tree.nodes
nodes.clear()
out=nodes.new('ShaderNodeOutputWorld')
bg=nodes.new('ShaderNodeBackground')
bg.inputs['Strength'].default_value=.7
tc=nodes.new('ShaderNodeTexCoord')
sep=nodes.new('ShaderNodeSeparateXYZ')
world.node_tree.links.new(tc.outputs['Normal'],sep.inputs[0])
ram=nodes.new('ShaderNodeValToRGB')
ram.color_ramp.elements[0].position=0
ram.color_ramp.elements[0].color=(.23,.43,.67,1)
ram.color_ramp.elements[1].position=.75
ram.color_ramp.elements[1].color=(.075,.20,.43,1)
world.node_tree.links.new(sep.outputs['Z'],ram.inputs[0])
world.node_tree.links.new(ram.outputs[0],bg.inputs['Color'])
world.node_tree.links.new(bg.outputs[0],out.inputs[0])
S.view_settings.view_transform='AgX'
S.view_settings.look='AgX - Medium High Contrast'
S.view_settings.exposure=0
S.view_settings.gamma=1
S.name='天宫_V08_白玉朱漆青瓦云海'
S['阶段']='V08 第一版完整静态场景效果'
S['V08基准摘要']=BASE_HASH
S['V08说明']='保留V7建筑与十六台相机；修形、共享米制程序材质、统一暖阳冷光、真实体积云海'
S['V08渲染设置']='Cycles CPU；1800×1350；64最大采样；自适应0.035；降噪；体积反弹1'
configure_render(64,100)
S.frame_set(1)
S.camera=next(m.camera for m in S.timeline_markers if m.frame==1)
for name in ['build_lookdev_v08.py','lookdev_materials_v08.py']:
    block=bpy.data.texts.new('V08_'+name)
    block.write((ROOT/'scripts'/name).read_text(encoding='utf-8'))
reference=Path('C:/Users/12899/Downloads/ChatGPT Image 2026年9月8日 17_54_37.png')
if reference.exists():
    img=bpy.data.images.load(str(reference),check_existing=True)
    img.name='V08_色彩与氛围原型参考_非渲染背景'
    img.use_fake_user=True
    img.pack()
bpy.ops.file.pack_all()
REPORT.update(material_assignments=assignments,clouds=cloudrecords,far_mountains=len(farcol.objects),cloud_count=len(cloudcol.objects),materials=[m.name for m in MAT.values()])
(QA/'lookdev_build.json').write_text(json.dumps(REPORT,ensure_ascii=False,indent=2),encoding='utf-8')
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT/'HeavenlyPalace_Lookdev_v08.blend'),compress=True)
render(1,QA/'sample_01_oblique.png',16,40)
render(4,QA/'sample_04_interior.png',20,40)
print('V08_LOOKDEV_READY',flush=True)
