"""
生成可平铺的石材、岩壁、瓦面和木纹物理材质，颜色与凹凸采用同一高度场。
贴图只包含表面属性；直接光照交给渲染器，网页和 Blender 共用同一组图片。
"""
import bpy
import json
import struct
import zlib
import numpy as np
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXTURES = ROOT / 'assets' / 'textures'


def noise(u, v, cells, seed, y_ratio=1):
    """
    使用周期晶格和五次插值生成连续噪声，贴图左右及上下可以无缝重复。
    不依赖外部图片、随机全局状态或额外的 Python 安装包。
    """
    rng = np.random.default_rng(seed)
    rows = max(1, round(cells * y_ratio))
    grid = rng.random((rows, cells)).astype(np.float32)
    x, y = u * cells, v * rows
    ix, iy = np.floor(x).astype(np.int32), np.floor(y).astype(np.int32)
    tx, ty = x - ix, y - iy
    tx, ty = tx**3 * (tx * (tx * 6 - 15) + 10), ty**3 * (ty * (ty * 6 - 15) + 10)
    a = grid[iy % rows, ix % cells] * (1 - tx) + grid[iy % rows, (ix + 1) % cells] * tx
    b = grid[(iy + 1) % rows, ix % cells] * (1 - tx) + grid[(iy + 1) % rows, (ix + 1) % cells] * tx
    return a * (1 - ty) + b * ty


def fractal(u, v, seed, start=4, octaves=6, y_ratio=1):
    """
    将不同尺度的纹理叠加为侵蚀、矿物和木纤维的共同底层。
    高层噪声逐级减弱，避免满屏同样强度的小斑点。
    """
    result = np.zeros_like(u)
    for octave in range(octaves):
        result += (noise(u, v, start * 2**octave, seed + octave, y_ratio) - .5) * .52**octave
    return result


def png(path, rgb):
    """
    直接写出八位 RGB 图片，基础色数值明确采用标准色彩空间。
    高度场按紫外坐标向上排列，写文件时转换为图片从上往下的行序。
    """
    pixels = np.flipud(np.clip(rgb * 255 + .5, 0, 255).astype(np.uint8))
    height, width, _ = pixels.shape
    raw = b''.join(b'\x00' + row.tobytes() for row in pixels)
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    path.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
                     + chunk(b'IDAT', zlib.compress(raw, 8)) + chunk(b'IEND', b''))


def surface(kind, size):
    """
    各类材质分别建立颜色、米制凹凸高度和粗糙度，避免用颜色假画阴影。
    岩石以竖向裂隙为主，石板以错缝为主，瓦面以连续筒瓦和搭接为主。
    """
    v, u = np.mgrid[0:size, 0:size].astype(np.float32) / size
    broad = fractal(u, v, 193)
    fine = fractal(u, v, 379, 32, 4)
    metallic = np.zeros_like(u)
    if kind == 'rock':
        warp = u + .035 * fractal(u, v, 817, 2)
        flutes = fractal(warp, v, 127, 32, 4, y_ratio=.25)
        fracture = np.exp(-np.abs(fractal(warp, v, 932, 8, 4, y_ratio=.5)) * 95)
        seams = np.maximum(0, np.sin((v * 18 + broad * .7) * np.pi * 2))**22
        mineral = np.clip(.48 + broad * .7 + flutes * .32 + fine * .12, .18, .78)
        rgb = np.stack((mineral * .91, mineral * .88, mineral * .81), axis=-1)
        rgb -= fracture[..., None] * .105 + seams[..., None] * .024
        moss = np.clip((fractal(u, v, 471, 4) - .12) * 2.5, 0, .7)
        rgb = rgb * (1 - moss[..., None]) + np.array([.21, .245, .14]) * moss[..., None]
        height = broad * .15 + flutes * .085 + fine * .022 - fracture * .026 - seams * .008
        rough = np.clip(.84 + fine * .18 - moss * .13, .6, .98)
        tile = 24
    elif kind == 'paving':
        row = np.floor(v * 4)
        px = (u * 4 + np.mod(row, 2) * .5) % 1
        py = (v * 4) % 1
        edge = np.minimum(np.minimum(px, 1 - px), np.minimum(py, 1 - py))
        seam = np.clip((.007 - edge) / .006, 0, 1)
        variation = noise((np.floor(u * 4 + np.mod(row, 2) * .5) + .5) / 4, (row + .5) / 4, 4, 791) - .5
        vein = np.exp(-np.abs(fractal(u, v, 811, 4) + .035 * fine) * 80)
        value = .73 + broad * .11 + fine * .035 + variation * .065 - vein * .025
        rgb = np.stack((value * 1.025, value, value * .945), axis=-1) - seam[..., None] * .16
        height = broad * .003 + fine * .0008 - seam * .018
        rough = .5 + fine * .1 + seam * .3
        tile = 16
    elif kind == 'stone':
        vein = np.exp(-np.abs(fractal(u + broad * .08, v, 918, 2) + .03 * fine) * 100)
        value = .74 + broad * .12 + fine * .025 - vein * .037
        rgb = np.stack((value * 1.035, value * 1.012, value * .958), axis=-1)
        height = broad * .002 + fine * .0008 - vein * .0005
        rough = .43 + broad * .11 + fine * .05
        tile = 6
    elif kind == 'roof':
        tx, ty = (u * 16) % 1, (v * 16) % 1
        ridge = np.maximum(0, np.cos((tx - .5) * np.pi))**1.8
        lap = np.clip((.035 - np.minimum(ty, 1 - ty)) / .03, 0, 1)
        tile_noise = noise((np.floor(u * 16) + .5) / 16, (np.floor(v * 16) + .5) / 16, 16, 481) - .5
        value = .23 + tile_noise * .08 + broad * .05 + fine * .025
        rgb = np.stack((value * .78, value * 1.045, value * 1.09), axis=-1) - lap[..., None] * .055
        height = ridge * .07 - lap * .014 + fine * .001
        rough = .35 + tile_noise * .11 + lap * .22
        tile = 9.92
    else:
        fibre = fractal(u, v, 636, 64, 4, y_ratio=.0625)
        streak = np.maximum(0, np.sin((u * 96 + broad * 1.2) * np.pi * 2))**18
        value = .35 + fibre * .17 + broad * .06 - streak * .045
        rgb = np.stack((value, value * .49, value * .255), axis=-1)
        height = fibre * .0018 - streak * .0009
        rough = .4 + fine * .1
        tile = 6
    return rgb, height, rough, metallic, tile


def generate(kind, size):
    """
    用同一高度场导出切线空间法线，使颜色裂隙与表面凹凸准确对齐。
    粗糙度和金属度打包，遮蔽通道保持一，交由真实光照建立场景阴影。
    """
    rgb, height, rough, metallic, tile = surface(kind, size)
    dx = (np.roll(height, -1, axis=1) - np.roll(height, 1, axis=1)) * size / (2 * tile)
    dy = (np.roll(height, -1, axis=0) - np.roll(height, 1, axis=0)) * size / (2 * tile)
    normal = np.stack((-dx, -dy, np.ones_like(dx)), axis=-1)
    normal /= np.linalg.norm(normal, axis=-1)[..., None]
    files = {key: f'q02_{kind}_{key}.png' for key in ('basecolor', 'normal', 'orm')}
    png(TEXTURES / files['basecolor'], rgb)
    png(TEXTURES / files['normal'], normal * .5 + .5)
    png(TEXTURES / files['orm'], np.stack((np.ones_like(rough), rough, metallic), axis=-1))
    print('QUALITY_TEXTURE', kind, size, flush=True)
    return dict(files=files, tile_m=tile, size=size)


def bind(mat, spec):
    """
    同步 Blender 节点和网页导出描述，确保两端读取相同的表面属性。
    巨柱原有的第二套浮雕紫外坐标仍专门用于柱身法线。
    """
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()
    output = nodes.new('ShaderNodeOutputMaterial')
    bs = nodes.new('ShaderNodeBsdfPrincipled')
    links.new(bs.outputs['BSDF'], output.inputs['Surface'])
    bs.inputs['Roughness'].default_value = spec['roughness']
    bs.inputs['Metallic'].default_value = spec['metallic']
    bs.inputs['Base Color'].default_value = spec['base_factor']
    for kind, filename in spec['files'].items():
        node = nodes.new('ShaderNodeTexImage')
        im = bpy.data.images.load(str(TEXTURES / filename), check_existing=True)
        im.colorspace_settings.name = 'sRGB' if kind == 'basecolor' else 'Non-Color'
        node.image = im
        if kind == 'basecolor':
            mix = nodes.new('ShaderNodeMixRGB')
            mix.blend_type = 'MULTIPLY'
            mix.inputs[0].default_value = 1
            mix.inputs[2].default_value = spec['base_factor']
            links.new(node.outputs['Color'], mix.inputs[1])
            links.new(mix.outputs[0], bs.inputs['Base Color'])
        elif kind == 'normal':
            nm = nodes.new('ShaderNodeNormalMap')
            nm.uv_map = 'ReliefUV' if spec.get('normal_uv') == 1 else 'TileUV'
            if spec.get('normal_uv') == 1:
                uv = nodes.new('ShaderNodeUVMap')
                uv.uv_map = 'ReliefUV'
                links.new(uv.outputs[0], node.inputs['Vector'])
            links.new(node.outputs[0], nm.inputs['Color'])
            links.new(nm.outputs[0], bs.inputs['Normal'])
        else:
            split = nodes.new('ShaderNodeSeparateColor')
            links.new(node.outputs[0], split.inputs[0])
            links.new(split.outputs[1], bs.inputs['Roughness'])
            links.new(split.outputs[2], bs.inputs['Metallic'])
    mat['web_spec'] = json.dumps(spec, ensure_ascii=False)


def upgrade_materials():
    """
    依据既有材质身份替换真实表面属性，不改人物、瀑布与藻井图案。
    新增干岩、湿岩和苔岩变体共用图片，只以物理基础色区分局部环境。
    """
    generated = {kind: generate(kind, 2048 if kind == 'rock' else 1024)
                 for kind in ('rock', 'stone', 'paving', 'roof', 'wood')}
    changed = []
    for mat in list(bpy.data.materials):
        if 'web_spec' not in mat:
            continue
        spec = json.loads(mat['web_spec'])
        kind = ('rock' if '山岩' in mat.name else 'paving' if '石板' in mat.name or '地坪' in mat.name
                else 'stone' if '白玉' in mat.name or '巨柱' in mat.name else 'roof' if '琉璃瓦' in mat.name
                else 'wood' if '朱红木构' in mat.name else None)
        if not kind:
            continue
        old_normal = spec['files'].get('normal')
        spec.update(generated[kind])
        spec['files'] = dict(spec['files'])
        if spec.get('normal_uv') == 1:
            spec['files']['normal'] = old_normal
        spec['base_factor'] = [1, 1, 1, 1]
        spec['quality_revision'] = 'q02'
        bind(mat, spec)
        changed.append(mat.name)
    base = bpy.data.materials['WEB_V08_山岩_干面裂隙苔色与湿岸']
    variants = {'rock': base}
    for key, title, color in [('wet', '湿岩', [.47, .53, .52, 1]), ('moss', '苔岩', [.50, .61, .34, 1])]:
        mat = base.copy()
        mat.name = 'WEB_Q02_' + title
        spec = json.loads(base['web_spec'])
        spec.update(name=mat.name, base_factor=color, source='Q02_' + title)
        bind(mat, spec)
        variants[key] = mat
    return variants, changed
