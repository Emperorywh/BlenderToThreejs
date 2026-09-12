"""
使用 Blender Python 制作殿外云海：烘焙体积云图集，生成米制云层布局与远山。
独立保存云海工程，不读取或覆盖建筑工程；网页读取同一份布局和烘焙结果。
"""
import argparse
import json
import math
import random
import struct
import sys
import zlib
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

# 山脊与古松由独立几何模块生成，保留统一坐标和确定性随机种子。
# 主入口仍负责体积烘焙与最终保存，重复运行即可完整重现本轮门外环境。
sys.path.insert(0, str(Path(__file__).resolve().parent))
from moon_gate_landscape import build_gate_landmark, build_ridges
from blend_io import save_web_blend

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "assets" / "cloud-sea"
QA = ROOT / "qa" / "cloud-sea"


def save_atlas_png(path, pixels):
    """
    将已解除预乘的线性像素明确编码为标准 sRGB PNG，避免保存时再次除以透明度。
    Blender 像素从下往上排列，PNG 从上往下排列；行顺序在此统一转换一次。
    """
    rgb = np.clip(pixels[:, :, :3], 0, 1)
    srgb = np.where(rgb <= 0.0031308, rgb * 12.92, 1.055 * np.power(rgb, 1 / 2.4) - 0.055)
    rgba = np.concatenate((srgb, np.clip(pixels[:, :, 3:4], 0, 1)), axis=2)
    encoded = np.round(rgba[::-1] * 255).astype(np.uint8)
    height, width = encoded.shape[:2]

    def chunk(kind, payload):
        """
        PNG 数据块包含长度、内容与校验值，使用标准库即可稳定复现文件。
        输出不依赖额外图片软件，也不更改烘焙得到的透明遮罩。
        """
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff)

    scanlines = b"".join(b"\x00" + row.tobytes() for row in encoded)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
                     + chunk(b"sRGB", b"\x00") + chunk(b"IDAT", zlib.compress(scanlines, 8)) + chunk(b"IEND", b""))


def volume_material(index):
    """
    多个不规则椭球合并成连续密度场，叠加大小两级噪声雕刻积云边缘。
    真正的体积散射负责暖色亮沿与蓝灰自阴影，透明区域不包含天空颜色。
    """
    material = bpy.data.materials.new(f"云团_{index + 1}_分形体积")
    material.use_nodes = True
    nodes, links = material.node_tree.nodes, material.node_tree.links
    nodes.clear()

    def math_node(operation, a, b):
        """
        统一连接标量运算节点，常量与节点输出都能作为输入。
        运算保留在可编辑材质中，方便在 Blender 中调整密度和轮廓。
        """
        node = nodes.new("ShaderNodeMath")
        node.operation = operation
        for socket, value in zip(node.inputs, (a, b)):
            if isinstance(value, (int, float)):
                socket.default_value = value
            else:
                links.new(value, socket)
        return node.outputs[0]

    coord = nodes.new("ShaderNodeTexCoord").outputs["Generated"]
    rng = random.Random(9230 + index)
    distance = None
    lobes = [(0.5, 0.5, 0.34, 0.34, 0.29, 0.18)]
    # 大云瓣建立连续云浪，小云瓣在表面形成翻卷细节，减少棉团般光滑的轮廓。
    # 所有云瓣都属于同一个密度场，离线散射能计算它们之间的真实遮光。
    for _ in range(22):
        x, y = rng.uniform(0.23, 0.77), rng.uniform(0.29, 0.71)
        height = 0.47 + (1 - abs(x - 0.5) * 2) * rng.uniform(0.04, 0.19)
        radius = rng.uniform(0.11, 0.18)
        lobes.append((x, y, height, radius, radius * 1.1, radius * 1.2))
    for _ in range(26):
        parent = rng.choice(lobes[1:23])
        radius = rng.uniform(0.035, 0.073)
        lobes.append((parent[0] + rng.uniform(-0.095, 0.095), parent[1] + rng.uniform(-0.08, 0.08),
                      min(0.79, parent[2] + parent[5] * rng.uniform(0.32, 0.82)), radius, radius, radius * 1.12))
    for x, y, z, rx, ry, rz in lobes:
        subtract = nodes.new("ShaderNodeVectorMath")
        subtract.operation = "SUBTRACT"
        links.new(coord, subtract.inputs[0])
        subtract.inputs[1].default_value = (x, y, z)
        divide = nodes.new("ShaderNodeVectorMath")
        divide.operation = "DIVIDE"
        links.new(subtract.outputs[0], divide.inputs[0])
        divide.inputs[1].default_value = (rx, ry, rz)
        length = nodes.new("ShaderNodeVectorMath")
        length.operation = "LENGTH"
        links.new(divide.outputs[0], length.inputs[0])
        distance = length.outputs["Value"] if distance is None else math_node("MINIMUM", distance, length.outputs["Value"])
    texture = nodes.new("ShaderNodeTexNoise")
    # 提高边缘噪声频率并降低侵蚀幅度，保留云瓣层级与柔软的破碎边缘。
    # 体积核心不再被大幅噪声掏空，因此细节增加后仍有厚实自阴影。
    texture.inputs["Scale"].default_value = 29
    texture.inputs["Detail"].default_value = 5
    texture.inputs["Roughness"].default_value = 0.72
    links.new(coord, texture.inputs["Vector"])
    perturbation = math_node("MULTIPLY", math_node("SUBTRACT", texture.outputs["Fac"], 0.5), 0.42)
    field = math_node("SUBTRACT", 1.0, math_node("ADD", distance, perturbation))
    density = math_node("MULTIPLY", math_node("MAXIMUM", field, 0), 0.14)
    # 实例放大时等比例降低密度，让编辑工程中的公里级云团保留母版光学厚度。
    # 母版物体颜色为纯白，因此离线图集的默认密度与此前保持一致。
    object_info = nodes.new("ShaderNodeObjectInfo")
    density = math_node("MULTIPLY", density, object_info.outputs["Color"])
    volume = nodes.new("ShaderNodeVolumePrincipled")
    volume.inputs["Color"].default_value = (0.96, 0.975, 1, 1)
    volume.inputs["Anisotropy"].default_value = 0.25
    links.new(density, volume.inputs["Density"])
    output = nodes.new("ShaderNodeOutputMaterial")
    links.new(volume.outputs["Volume"], output.inputs["Volume"])
    return material


def bake_atlas(scene, prototypes, size, samples):
    """
    图集四列对应不同云形，两行分别记录平视与俯视，降低环游时的纸片感。
    烘焙使用透明背景与标准色彩变换，网页再统一进行曝光和显示变换。
    """
    scene.render.engine = "CYCLES"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.cycles.volume_step_rate = 0.65
    scene.cycles.volume_max_steps = 512
    # 多次散射把日光送入云体，形成明亮积云而非只有亮边的浓烟。
    # 这部分计算离线完成，网页仅采样最终的体积明暗图集。
    scene.cycles.volume_bounces = 6
    try:
        preferences = bpy.context.preferences.addons["cycles"].preferences
        preferences.compute_device_type = "OPTIX"
        preferences.get_devices()
        for device in preferences.devices:
            device.use = device.type == "OPTIX"
        scene.cycles.device = "GPU" if any(d.use for d in preferences.devices) else "CPU"
    except Exception:
        scene.cycles.device = "CPU"
    scene.render.resolution_x = scene.render.resolution_y = size
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "OPEN_EXR"
    scene.render.image_settings.color_mode = "RGBA"
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = 0
    scene.view_settings.gamma = 1
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes.get("Background")
    background.inputs[0].default_value = (0.38, 0.51, 0.72, 1)
    background.inputs[1].default_value = 0.22
    light_data = bpy.data.lights.new("云图集_暖阳", "SUN")
    # 减少烘焙高光被八位图集截白的范围，保留云冠暖光与背光沟谷的区别。
    # 颜色由物理散射烘焙，网页仍只执行一次统一曝光与色调映射。
    light_data.energy = 4.6
    light_data.color = (1, 0.86, 0.70)
    light_data.angle = 0.12
    light = bpy.data.objects.new(light_data.name, light_data)
    scene.collection.objects.link(light)
    light.rotation_euler = Vector((350, 480, -700)).to_track_quat("-Z", "Y").to_euler()
    camera_data = bpy.data.cameras.new("云图集_正交机位")
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = 285
    camera_data.clip_end = 5000
    camera = bpy.data.objects.new(camera_data.name, camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    atlas = np.zeros((size * 2, size * 4, 4), dtype=np.float32)
    for row, elevation in enumerate((8, 48)):
        angle = math.radians(elevation)
        camera.location = (0, -650 * math.cos(angle), 650 * math.sin(angle))
        camera.rotation_euler = (-camera.location).to_track_quat("-Z", "Y").to_euler()
        for column, prototype in enumerate(prototypes):
            for item in prototypes:
                item.hide_render = item != prototype
            path = QA / f"cloud-{row}-{column}.exr"
            scene.render.filepath = str(path)
            bpy.ops.render.render(write_still=True)
            frame = bpy.data.images.load(str(path), check_existing=False)
            pixels = np.empty(size * size * 4, dtype=np.float32)
            frame.pixels.foreach_get(pixels)
            pixels = pixels.reshape(size, size, 4)
            # 文件中的体积边缘先解除预乘，避免网页透明混合产生黑边。
            # 图集最终存为普通非预乘 PNG，零透明度像素继续保持为零。
            alpha = pixels[:, :, 3:4]
            pixels[:, :, :3] = np.divide(pixels[:, :, :3], np.maximum(alpha, 1e-6))
            pixels[:, :, :3][alpha[:, :, 0] < 1e-5] = 0
            atlas[row * size:(row + 1) * size, column * size:(column + 1) * size] = pixels
            bpy.data.images.remove(frame)
            print(f"CLOUD_TILE_READY {row} {column}", flush=True)
    save_atlas_png(OUTPUT / "cloud-atlas.png", atlas)
    return light, camera


def build_layout():
    """
    按距离展开云带，主云海顶面保持在殿内眼高下方，并在远处抬高少量云峰。
    留出主岛与建筑安全区，云海在所有机位下都使用相同世界位置。
    """
    rng = random.Random(20260912)
    clouds = []
    bands = [(1100, 25, -285, 360), (1800, 34, -340, 490), (2800, 42, -370, 680),
             (4100, 48, -415, 860), (5700, 55, -440, 1100), (7800, 60, -470, 1350),
             (10500, 68, -510, 1730), (14000, 72, -560, 2180), (18500, 76, -610, 2800)]
    for band, (radius, count, height, width) in enumerate(bands):
        for index in range(count):
            angle = math.tau * (index + rng.uniform(-0.28, 0.28)) / count
            distance = radius + rng.uniform(-0.14, 0.14) * radius
            thickness = width * rng.uniform(0.28, 0.46)
            y = height + rng.uniform(-65, 45)
            # 近处云冠限制在人物眼高下方；远处云峰可以自然越过低云地平线。
            # 宽度随距离增加，但角尺寸逐渐变小，避免再次出现遮满月门的巨幅云片。
            if band < 4:
                y = min(y, -55 - thickness * 0.5)
            clouds.append({"kind": "cloud_sea", "position": [round(math.cos(angle) * distance, 3), round(y, 3), round(math.sin(angle) * distance, 3)],
                           "dimensions": [round(width * rng.uniform(0.86, 1.3), 3), round(thickness, 3), round(width * rng.uniform(0.62, 0.95), 3)],
                           "variant": rng.randrange(4), "opacity": round(rng.uniform(0.9, 1), 3)})
    # 门外主云浪按角尺寸逐层变小，形成多排交错云冠与山脚之间的遮挡关系。
    # 近景仍位于主岛之外，中远景逐渐抬升，让云海占据门洞下部而非只露一条薄雾。
    for band, (distance, count, spacing, height, width, thickness) in enumerate((
            (1350, 29, 145, 70, 270, 220), (2250, 33, 195, 150, 350, 330),
            (3700, 37, 260, 280, 490, 460), (6100, 41, 380, 455, 700, 680),
            (9800, 47, 540, 780, 970, 1030), (15700, 51, 770, 1220, 1390, 1510))):
        for index in range(count):
            x = (index - (count - 1) / 2) * spacing + rng.uniform(-0.2, 0.2) * spacing
            wave = math.sin(index * 0.82 + band * 1.7) * thickness * 0.14
            clouds.append({"kind": "gate_cloud_wave", "position": [round(x, 3), round(height + wave + rng.uniform(-0.10, 0.12) * thickness, 3), round(distance + rng.uniform(-0.09, 0.09) * distance, 3)],
                           "dimensions": [round(width * rng.uniform(0.82, 1.2), 3), round(thickness * rng.uniform(0.8, 1.25), 3), round(width * 0.72, 3)],
                           "variant": rng.randrange(4), "opacity": 0.98})
    # 原入口遮檐云仍偏向旧相机的横向位置，机位回到中轴后屋顶从月门底部露出。
    # 两排薄云按正式眼点重新居中，放在入口屋面之前，用真实深度自然遮住屋檐。
    eye_x = json.loads((ROOT / "assets" / "cameras.json").read_text(encoding="utf-8"))["cameras"][3]["position"][0]
    for row, z in enumerate((151, 166)):
        for index in range(7):
            clouds.append({"kind": "entrance_roof_occluder", "position": [eye_x + (index - 3) * 24 + row * 9, 42.5 - row, z],
                           "dimensions": [74, 40, 32], "variant": (index + row) % 4, "opacity": 1.0})
    return clouds


def main():
    """
    默认完整生成图集与布局，布局调参可复用已烘焙的图集节省时间。
    保存的独立工程包含全部体积云、远山和导入自原工程的殿内机位。
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-bake", action="store_true")
    parser.add_argument("--tile-size", type=int, default=512)
    parser.add_argument("--samples", type=int, default=48)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    OUTPUT.mkdir(parents=True, exist_ok=True)
    QA.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.world = bpy.data.worlds.new("云海天空")
    prototypes = []
    for index in range(4):
        bpy.ops.mesh.primitive_cube_add(size=2)
        obj = bpy.context.object
        obj.name = f"云形母版_{index + 1}"
        obj.scale = (125, 110, 95)
        obj.data.materials.append(volume_material(index))
        prototypes.append(obj)
    if not args.skip_bake:
        light, camera = bake_atlas(scene, prototypes, args.tile_size, args.samples)
        # 烘焙结束后保留日光供独立工程查看，避免保存成没有太阳的体积场景。
        # 母版相机只在视口隐藏，实际观景机位稍后从原始相机数据恢复。
        light.name = "云海_西南暖阳"
        camera.hide_viewport = True
    else:
        # 仅更新布局时也创建相同日光和天空，确保保存工程仍可用于人工观察。
        # 图集尺寸从实际 PNG 读取，避免复用非默认分辨率图集时写错采样边距。
        scene.world.use_nodes = True
        background = scene.world.node_tree.nodes.get("Background")
        background.inputs[0].default_value = (0.38, 0.51, 0.72, 1)
        background.inputs[1].default_value = 0.22
        light_data = bpy.data.lights.new("云海_西南暖阳", "SUN")
        # 布局重建也使用新图集的同一盏暖阳，人工打开工程时光照方向和强度一致。
        # 此分支只复用正式图集，不重新计算任何像素。
        light_data.energy = 4.6
        light_data.color = (1, 0.86, 0.70)
        light = bpy.data.objects.new(light_data.name, light_data)
        scene.collection.objects.link(light)
        light.rotation_euler = Vector((350, 480, -700)).to_track_quat("-Z", "Y").to_euler()
        args.tile_size = struct.unpack_from(">I", (OUTPUT / "cloud-atlas.png").read_bytes(), 16)[0] // 4
    assert (OUTPUT / "cloud-atlas.png").exists(), "复用烘焙前必须先生成云图集。"
    clouds = build_layout()
    for index, record in enumerate(clouds):
        source = prototypes[record["variant"]]
        obj = bpy.data.objects.new(f"云带_{index:03d}", source.data)
        scene.collection.objects.link(obj)
        x, y, z = record["position"]
        sx, sy, sz = record["dimensions"]
        obj.location = (x, -z, y)
        obj.scale = (sx / 2, sz / 2, sy / 2)
        density_scale = 1 / ((sx / 250 + sz / 220 + sy / 190) / 3)
        obj.color = (density_scale, density_scale, density_scale, 1)
        obj.display_type = "WIRE"
    for obj in prototypes:
        obj.hide_render = True
        obj.hide_set(True)
    # 完整环绕山脊接管旧低模远山，右侧岩壁古松与云浪共享真实空间位置。
    # 标记写入资源布局，使网页只在新环境就绪时停用旧占位山群。
    ridges = build_ridges()
    landmarks = build_gate_landmark()
    data = {"revision": "cloud-sea-v2-moon-gate", "说明": ["世界坐标采用米制 Y 向上；云海位置不跟随相机。", "六排门外云浪、三圈破碎山脊与右侧古松岩壁共同构成门外纵深。"],
            "atlas": "cloud-atlas.png", "tileSize": args.tile_size, "clouds": clouds, "ridges": ridges,
            "landmarks": landmarks, "replacesLegacyMountains": True, "replacesEntranceMist": True,
            "bedHeight": -560, "radius": 28000}
    (OUTPUT / "layout.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    from mathutils import Matrix
    source_camera = json.loads((ROOT / "assets" / "cameras.json").read_text(encoding="utf-8"))["cameras"][3]
    camera_data = bpy.data.cameras.new("殿内望云_原机位")
    camera_data.lens = source_camera["lens_mm"]
    camera_data.shift_x = source_camera["shift_x"]
    # 殿内建筑镜头使用竖向上移，新建云海检查机位时同步全部传感器与偏移参数。
    # 避免重建云海后退回无上移的构图，导致独立工程与网页的观察范围不一致。
    camera_data.shift_y = source_camera["shift_y"]
    camera_data.sensor_width = source_camera["sensor_width_mm"]
    camera_data.sensor_height = source_camera["sensor_height_mm"]
    camera_data.sensor_fit = source_camera["sensor_fit"]
    camera_data.clip_end = 60000
    camera = bpy.data.objects.new(camera_data.name, camera_data)
    scene.collection.objects.link(camera)
    matrix = source_camera["world_matrix"]
    conversion = Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))
    camera.matrix_world = conversion @ Matrix([matrix[i::4] for i in range(4)])
    scene.camera = camera
    # 独立工程保存可直接观察的天空与低位云床，材质图集仍保持透明背景。
    # 云海工程只包含本次环境资产，用户可按相同坐标链接到建筑工程中。
    scene.render.film_transparent = False
    scene.render.engine = "CYCLES"
    scene.cycles.samples = args.samples
    scene.cycles.use_denoising = True
    scene.cycles.volume_bounces = 6
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 960
    bpy.ops.mesh.primitive_plane_add(size=56000, location=(0, 0, -560))
    bed = bpy.context.object
    bed.name = "低位连续云床_网页高度参照"
    bed_material = bpy.data.materials.new("低位云床_暖白")
    bed_material.diffuse_color = (0.72, 0.78, 0.84, 1)
    bed.data.materials.append(bed_material)
    scene["云海说明"] = "独立云海工程；建筑位置及网页四机位保持原有定义。"
    # 完整写出临时工程后再替换正式文件，短暂文件占用不会损坏已有云海工程。
    # 建筑工程保持独立，新环境仍保存到原本的专用云海工程入口。
    save_web_blend(ROOT / "HeavenlyPalace_CloudSea_v01.blend")
    print(f"CLOUD_SEA_READY clouds={len(clouds)} ridges={len(ridges)}", flush=True)


if __name__ == "__main__":
    main()
