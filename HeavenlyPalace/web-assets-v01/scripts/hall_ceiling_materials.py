"""
为主殿藻井生成独立的朱漆、古金与卷草彩画，纹理按四米物理尺度无缝重复。
本模块导入时不生成文件或修改场景，只有显式调用入口才更新对应材质。
"""
import math
from pathlib import Path

import bpy
import numpy as np

from quality_materials import bind, fractal, noise, png


TEXTURES = Path(__file__).resolve().parents[1] / 'assets' / 'textures'
TILE_METERS = 4.0


def _stroke(field, points, width):
    """
    将连续线条以带抗锯齿的真实线宽写入周期画布，越过边缘的笔划自动回到对侧。
    每段只计算局部包围盒，密集卷草不需要为每条曲线遍历整张贴图。
    """
    size = field.shape[0]
    feather = 1.15 / size
    padding = width + feather
    for first, second in zip(points[:-1], points[1:]):
        first, second = np.asarray(first), np.asarray(second)
        low = np.floor((np.minimum(first, second) - padding) * size).astype(int)
        high = np.ceil((np.maximum(first, second) + padding) * size).astype(int)
        ix, iy = np.arange(low[0], high[0] + 1), np.arange(low[1], high[1] + 1)
        x, y = np.meshgrid((ix + .5) / size, (iy + .5) / size)
        delta = second - first
        length_squared = float(delta @ delta)
        along = np.clip(((x - first[0]) * delta[0] + (y - first[1]) * delta[1])
                        / max(length_squared, 1e-12), 0, 1)
        distance = np.sqrt((x - first[0] - along * delta[0]) ** 2
                           + (y - first[1] - along * delta[1]) ** 2)
        coverage = np.clip((width + feather - distance) / (2 * feather), 0, 1)
        address = np.ix_(iy % size, ix % size)
        field[address] = np.maximum(field[address], coverage)


def _leaf(field, veins, center, angle, length, width):
    """
    用两端收尖的叶片轮廓填充金箔，并沿叶轴刻出极细的漆底分缝。
    叶片采用相同的周期落点规则，重复铺设时不会在四米单元边界出现断叶。
    """
    size = field.shape[0]
    reach, feather = length * .6 + width, 1.15 / size
    ix = np.arange(math.floor((center[0] - reach) * size), math.ceil((center[0] + reach) * size) + 1)
    iy = np.arange(math.floor((center[1] - reach) * size), math.ceil((center[1] + reach) * size) + 1)
    x, y = np.meshgrid((ix + .5) / size - center[0], (iy + .5) / size - center[1])
    cosine, sine = math.cos(angle), math.sin(angle)
    along, across = x * cosine + y * sine, -x * sine + y * cosine
    progress = np.clip(along / length + .5, 0, 1)
    half_width = width * np.sin(math.pi * progress) ** .78
    distance = np.maximum(np.abs(across) - half_width, np.abs(along) - length * .5)
    coverage = np.clip(.5 - distance / (2 * feather), 0, 1)
    address = np.ix_(iy % size, ix % size)
    field[address] = np.maximum(field[address], coverage)
    direction = np.array([cosine, sine]) * length
    start, end = np.array(center) - direction * .39, np.array(center) + direction * .31
    _stroke(veins, [start, end], .00075)


def _scrollwork(size):
    """
    双藤沿横向连续生长，卷曲枝梢与成对尖叶填满藤间空隙，中央用小团花收束。
    金色面积由线宽与叶片决定，保留漆底留白；图案中不含假阴影或固定光源。
    """
    gold = np.zeros((size, size), dtype=np.float32)
    veins = np.zeros_like(gold)
    parameters = np.linspace(0, 1, 161)
    for sign in (-1, 1):
        points = [(t, .5 + sign * .205 * math.sin(math.tau * t)) for t in parameters]
        _stroke(gold, points, .0038)
        for index in range(8):
            t = (index + .25) / 8
            base = np.array([t, .5 + sign * .205 * math.sin(math.tau * t)])
            tangent = math.atan2(sign * .205 * math.tau * math.cos(math.tau * t), 1)
            side = sign * (-1 if index % 2 else 1)
            angle = tangent + side * .92
            center = base + .040 * np.array([math.cos(angle), math.sin(angle)])
            _leaf(gold, veins, center, angle, .085, .017)
    for cx in (.25, .75):
        for cy in (.23, .77):
            mirror = 1 if (cx < .5) == (cy < .5) else -1
            points = []
            for t in np.linspace(0, 1, 73):
                radius = .140 * (1 - t) + .010
                angle = mirror * (math.pi * .20 + t * math.tau * 1.18)
                points.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
            _stroke(gold, points, .0031)
            for index in (9, 22, 34):
                base = np.array(points[index])
                tangent = np.array(points[index + 1]) - np.array(points[index - 1])
                angle = math.atan2(tangent[1], tangent[0]) + mirror * .98
                center = base + .029 * np.array([math.cos(angle), math.sin(angle)])
                _leaf(gold, veins, center, angle, .063, .014)
    for cx, cy in ((0, 0), (.5, .5)):
        for index in range(8):
            angle = index * math.tau / 8
            center = (cx + .043 * math.cos(angle), cy + .043 * math.sin(angle))
            _leaf(gold, veins, center, angle, .054, .010)
        points = [(cx + .017 * math.cos(t), cy + .017 * math.sin(t))
                  for t in np.linspace(0, math.tau, 49)]
        _stroke(gold, points, .0035)
    return gold, np.minimum(veins, gold)


def _surface(kind, size):
    """
    先建立低反差漆面与金箔微表面，再将有组织的卷草遮罩混入彩画专用材质。
    基础色以标准色彩空间写图，高度使用米，金属度遮罩使漆底保持非金属。
    """
    v, u = np.mgrid[0:size, 0:size].astype(np.float32) / size
    broad = fractal(u, v, 402, 4, 4)
    grain = fractal(u, v, 913, 40, 3, y_ratio=.25)
    flecks = noise(u, v, 128, 763) - .5
    variation = 1 + broad * .11 + grain * .055
    lacquer = np.array([.49, .205, .112], dtype=np.float32)
    recess = np.array([.32, .110, .053], dtype=np.float32)
    gilding = np.array([.82, .594, .290], dtype=np.float32)
    height = grain * .00042 + flecks * .00006
    if kind == 'lacquer':
        color = variation[..., None] * lacquer
        roughness = .39 + broad * .038 + grain * .035
        metallic = np.zeros_like(u)
    elif kind == 'recess':
        color = variation[..., None] * recess
        roughness = .49 + broad * .036 + grain * .04
        metallic = np.zeros_like(u)
    elif kind == 'gold':
        # 旧金的磨耗只形成柔和色差和粗糙度变化，不把金饰做成密集黑色脏斑。
        # 适当保留非金属成分，让处于梁底阴影中的细饰仍有可读的暖色层次。
        wear = np.clip((broad + .12) * 1.6, 0, .55)
        color = gilding * (1 + grain[..., None] * .07 - wear[..., None] * .13)
        roughness = .34 + wear * .15 + flecks * .025
        metallic = .78 - wear * .10
        height = grain * .00032 + flecks * .00007
    else:
        gold, veins = _scrollwork(size)
        gold *= 1 - veins * .7
        # 金箔图案保留毫米级漆饰厚度，只有真实表面法线随场景光照产生明暗。
        # 色料与金属遮罩共用轮廓，防止卷草边缘出现浮空金属高光。
        base = np.array([.385, .137, .067], dtype=np.float32) * variation[..., None]
        gold_color = gilding * (1 + broad[..., None] * .055 + grain[..., None] * .04)
        color = base * (1 - gold[..., None]) + gold_color * gold[..., None]
        roughness = (.47 + grain * .025) * (1 - gold) + (.355 + broad * .04) * gold
        metallic = gold * .75
        height += gold * .0028 - veins * .0006
    return np.clip(color, 0, 1), height, np.clip(roughness, .2, .75), np.clip(metallic, 0, 1)


def _write_material(key, title, size):
    """
    为每个材质同时写出基础色、切线法线和遮蔽粗糙金属三通道，满足现有导出器。
    图片复用原工程的纵轴翻转约定，节点与网页描述始终绑定同一批实际文件。
    """
    kind = key.removeprefix('c02_')
    color, height, roughness, metallic = _surface(kind, size)
    dx = (np.roll(height, -1, axis=1) - np.roll(height, 1, axis=1)) * size / (2 * TILE_METERS)
    dy = (np.roll(height, -1, axis=0) - np.roll(height, 1, axis=0)) * size / (2 * TILE_METERS)
    normal = np.stack((-dx, -dy, np.ones_like(dx)), axis=-1)
    normal /= np.linalg.norm(normal, axis=-1)[..., None]
    files = {channel: f'{key}_{channel}.png' for channel in ('basecolor', 'normal', 'orm')}
    png(TEXTURES / files['basecolor'], color)
    png(TEXTURES / files['normal'], normal * .5 + .5)
    png(TEXTURES / files['orm'], np.stack((np.ones_like(roughness), roughness, metallic), axis=-1))
    name = 'H01_C02_' + title
    material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    spec = dict(source=name, name=name, files=files, base_factor=[1, 1, 1, 1],
                roughness=float(np.mean(roughness)), metallic=float(np.mean(metallic)),
                tile_m=TILE_METERS, size=size, quality_revision='c02', normal_uv=0)
    bind(material, spec)
    # Blender 的图片缓存可能仍保存上一次生成的像素，重复构建时主动重载本材质图片。
    # 该步骤只更新明确绑定的三张文件，不影响工程里其他材质使用的图像。
    for node in material.node_tree.nodes:
        if node.type == 'TEX_IMAGE' and node.image:
            node.image.reload()
    return material


def create_ceiling_materials():
    """
    显式创建四种藻井专用材质并按稳定键返回，供几何构建器直接加入材质字典。
    默认紫外坐标每四米重复，卷草沿第一坐标连续铺展，第二坐标保持同样周期。
    """
    TEXTURES.mkdir(parents=True, exist_ok=True)
    definitions = (('c02_lacquer', '暖朱褐漆', 512), ('c02_gold', '磨耗哑亮金', 512),
                   ('c02_recess', '深赭漆槽', 512), ('c02_pattern', '金卷草彩画', 1024))
    return {key: _write_material(key, title, size) for key, title, size in definitions}
