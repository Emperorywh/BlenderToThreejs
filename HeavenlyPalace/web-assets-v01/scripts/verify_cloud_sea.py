"""
离线核验云海图集、远山网格和穿过月洞门的视线，所有判断基于实际交付数据。
不启动浏览器，不截图界面；报告仅说明资源和几何关系，不能替代网页人工验收。
"""
import json
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parents[1]
# 有建筑工程时优先读取月门实体的最新元数据，独立云海工程则使用当前空间参数。
# 云海坐标为网页的纵轴向上坐标，门前平面的 Blender 正纵轴需要转换为负深度。
sys.path.insert(0, str(ROOT / 'scripts'))
from hall_space import FLOOR_Z, GATE_CENTER_Z, GATE_FRONT_Y, GATE_RADIUS, space_active
moon = bpy.data.objects.get('V05_月门通厚石圈_净径44米')
gate_center = float(moon.get('门洞中心标高_米', GATE_CENTER_Z if space_active() else 56.0)) if moon else GATE_CENTER_Z
gate_radius = float(moon.get('净开口直径_米', (GATE_RADIUS if space_active() else 22.0) * 2)) / 2 if moon else GATE_RADIUS
gate_floor = float(moon.get('完成面标高_米', FLOOR_Z)) if moon else FLOOR_Z
gate_depth = -max((moon.matrix_world @ vertex.co).y for vertex in moon.data.vertices) if moon else -GATE_FRONT_Y
ASSETS = ROOT / "assets" / "cloud-sea"
data = json.loads((ASSETS / "layout.json").read_text(encoding="utf-8"))
camera = json.loads((ROOT / "assets" / "cameras.json").read_text(encoding="utf-8"))["cameras"][3]
world = np.array(camera["world_matrix"]).reshape(4, 4).T
view = np.linalg.inv(world)
eye = world[:3, 3]
atlas = bpy.data.images.load(str(ASSETS / data["atlas"]))
pixels = np.array(atlas.pixels[:]).reshape(atlas.size[1], atlas.size[0], 4)
size = data["tileSize"]
assert list(atlas.size) == [size * 4, size * 2], "图集实际尺寸不符合双视角四形布局。"
tiles = []
for row in range(2):
    for column in range(4):
        tile = pixels[row * size:(row + 1) * size, column * size:(column + 1) * size]
        alpha = tile[:, :, 3]
        opaque = tile[:, :, :3][alpha > 0.8]
        assert len(opaque) > size * size * 0.08, "云团缺少具有实体感的核心。"
        assert np.max(alpha[:5]) < 0.005 and np.max(alpha[-5:]) < 0.005, "云团触及上下图集边界。"
        assert np.max(alpha[:, :5]) < 0.005 and np.max(alpha[:, -5:]) < 0.005, "云团触及左右图集边界。"
        contrast = float(np.percentile(opaque.mean(axis=1), 90) - np.percentile(opaque.mean(axis=1), 10))
        assert contrast > 0.06, "云图集明暗过平，无法提供可读的体积。"
        tiles.append({"row": row, "variant": column, "core_contrast": round(contrast, 4)})


def through_gate(points):
    """
    从当前正式相机 JSON 的殿内眼点连接世界点，检查连线是否穿过实际月门。
    门平面、净径和完成面共同限定可见开口，地坪以下的圆弧不计入云海覆盖。
    """
    delta = points - eye
    t = (gate_depth - eye[2]) / delta[:, 2]
    gate = eye + delta * t[:, None]
    inside = ((gate[:, 0] ** 2 + (gate[:, 1] - gate_center) ** 2) < gate_radius ** 2) & (gate[:, 1] >= gate_floor) & (t > 0) & (t < 1)
    return inside


# 网格核验同时检查索引、法线长度与三角形面积，防止导出有效但实际出现破面。
# 各层至少要有部分山峰位于月门视线内，避免把远景错误生成到宫殿背面。
ridges, landmarks = [], []
for ridge in data["ridges"] + data.get("landmarks", []):
    positions, normals = np.array(ridge["positions"]), np.array(ridge["normals"])
    indices = np.array(ridge["indices"]).reshape(-1, 3)
    assert np.isfinite(positions).all() and np.isfinite(normals).all()
    assert indices.min() >= 0 and indices.max() < len(positions)
    assert np.max(np.abs(np.linalg.norm(normals, axis=1) - 1)) < 0.001
    triangles = positions[indices]
    areas = np.linalg.norm(np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]), axis=1) / 2
    assert areas.min() > 0.001, "远山含退化三角形。"
    visible = int(np.sum(through_gate(positions) & (positions[:, 1] > 300)))
    assert visible > 10, "该层远山没有进入殿内月门视线。"
    # 近景也核对顶点与法线，并记录它投射到月门平面的左右位置。
    # 相机面向正 Z，负 X 对应画面右侧，古松必须实际进入右半门洞。
    record = {"layer": ridge["layer"], "triangles": len(indices), "vertices_through_gate": visible}
    if ridge["layer"] >= 0:
        ridges.append(record)
    else:
        inside = through_gate(positions)
        assert np.all(positions[inside, 0] < 0), "岩松应位于月门画面右侧。"
        record.update(name=ridge["name"], kind=ridge["kind"])
        landmarks.append(record)

# 用实际图集透明度采样云片投影，统计云海在门洞中的覆盖，而非只检查锚点。
# 采样不绘制图像，也不对外宣称网页表现已通过视觉验收。
# 使用扣除半米门圈边缘的实际可见区域采样，宽门和截圆落地造型采用一致规则。
# 上方蓝天分区相对可见净高确定，避免沿用旧中心标高把新门中部误当作天空。
sample_radius = gate_radius - 0.5
sample_bottom = max(gate_floor + 0.5, gate_center - sample_radius)
sample_top = gate_center + sample_radius
upper_boundary = sample_bottom + (sample_top - sample_bottom) * 0.62
gate_samples = np.array([(x, y, gate_depth) for y in np.linspace(sample_bottom, sample_top, 110) for x in np.linspace(-sample_radius, sample_radius, 110)
                         if x * x + (y - gate_center) ** 2 < sample_radius ** 2])
sample_view = (view @ np.column_stack((gate_samples, np.ones(len(gate_samples)))).T).T[:, :3]
rays = sample_view[:, :2] / -sample_view[:, 2:3]
coverage = np.zeros(len(rays))
for cloud in data["clouds"]:
    center, extent = np.array(cloud["position"]), np.array(cloud["dimensions"])
    assert np.isfinite(center).all() and np.all(extent > 0)
    distance = np.linalg.norm(center[[0, 2]])
    # 入口薄云是明确指定的局部遮檐效果，其余新云海仍必须位于主岛之外。
    # 薄云不能前移到主殿，也不能进入入口屋面的深度范围。
    if cloud["kind"] == "entrance_roof_occluder":
        assert 140 <= center[2] <= 170 and 25 <= center[1] <= 46, "局部遮檐云离开入口安全带。"
    else:
        assert distance > 800, "新云海侵入主岛安全区。"
    if distance < 4700 and cloud["kind"] == "cloud_sea":
        assert center[1] + extent[1] * 0.5 < eye[1], "近处主云海高于殿内眼点。"
    center_view = (view @ np.append(center, 1))[:3]
    if center_view[2] >= -150:
        continue
    dimensions = np.array([np.linalg.norm(world[:3, 0] * extent), np.linalg.norm(world[:3, 1] * extent)]) * 1.35
    uv = (rays * -center_view[2] - center_view[:2]) / dimensions + 0.5
    visible = np.all((uv >= 0) & (uv <= 1), axis=1)
    if not np.any(visible):
        continue
    local = np.clip((uv[visible] * (size - 1)).astype(int), 0, size - 1)
    column = cloud["variant"] * size
    alpha = pixels[local[:, 1], local[:, 0] + column, 3] * cloud["opacity"]
    coverage[visible] = 1 - (1 - coverage[visible]) * (1 - alpha)
covered = float(np.mean(coverage > 0.35))
# 门外主云冠应成为可读的面，同时保持门洞上半部的蓝天空间。
# 分区统计避免靠一张遮满门洞的大云片获得看似合格的总体覆盖率。
upper_coverage = float(np.mean(coverage[gate_samples[:, 1] > upper_boundary] > 0.35))
assert 0.30 < covered < 0.55, f"门洞内云海覆盖异常：{covered:.1%}，需要同时保留蓝天与云冠。"
assert upper_coverage < 0.05, "高处云冠遮挡过多蓝天。"

# 用真实近景三角形测试门洞射线，确认岩松只占画面一侧而不堵住云海。
# 该过程仅统计几何交点，不创建相机图像或调用界面截图工具。
landmark_hits = np.zeros(len(gate_samples), dtype=bool)
trees = {}
for landmark in data.get("landmarks", []):
    indices = np.array(landmark["indices"]).reshape(-1, 3).tolist()
    tree = BVHTree.FromPolygons(landmark["positions"], indices, all_triangles=True)
    trees[landmark["kind"]] = tree
    hits = np.array([tree.ray_cast(Vector(eye), Vector(point - eye).normalized(), 4000)[0] is not None for point in gate_samples])
    landmark_hits |= hits
    assert float(np.mean(hits)) > 0.0005, "该近景材质未进入月门实际视线。"
landmark_coverage = float(np.mean(landmark_hits))
assert 0.04 < landmark_coverage < 0.32, "岩壁古松占比异常，需保留中央云谷。"
assert not np.any(landmark_hits[gate_samples[:, 0] > 0]), "近景岩松越过门洞中线。"
# 根部落点必须贴住真实三角形表面，避免近景构图正确但树干实际悬空。
# 容许少量根部嵌入岩面，符合生成脚本用于遮住接缝的深度设置。
pine = next(item for item in data["landmarks"] if item["kind"] == "bark")
root_distance = trees["rock"].find_nearest(Vector(pine["anchor"]))[3]
assert root_distance is not None and root_distance < 2, "古松根部没有连接到岩壁。"

# 可在只读建筑工程中运行，按真实入口屋面的三角形采样检查前方薄云遮挡。
# 深度条件排除屋面后方的远云，避免仅凭相同屏幕位置误判遮檐已经完成。
roof_report = None
roof = bpy.data.objects.get("V06_入口中央门厅_连续曲面")
if roof is not None:
    roof.data.calc_loop_triangles()
    roof_points = []
    for triangle in roof.data.loop_triangles:
        point = roof.matrix_world @ (sum((roof.data.vertices[i].co for i in triangle.vertices), Vector()) / 3)
        roof_points.append((point.x, point.z, -point.y))
    roof_points = np.array(roof_points)
    roof_points = roof_points[through_gate(roof_points)]
    assert len(roof_points) > 10, "入口屋面采样不足。"
    projected = (view @ np.column_stack((roof_points, np.ones(len(roof_points)))).T).T[:, :3]
    roof_rays = projected[:, :2] / -projected[:, 2:3]
    opacity = np.zeros(len(roof_points))
    for cloud in data["clouds"]:
        if cloud["kind"] != "entrance_roof_occluder":
            continue
        center, extent = np.array(cloud["position"]), np.array(cloud["dimensions"])
        center_view = (view @ np.append(center, 1))[:3]
        dimensions = np.array([np.linalg.norm(world[:3, 0] * extent), np.linalg.norm(world[:3, 1] * extent)]) * 1.35
        uv = (roof_rays * -center_view[2] - center_view[:2]) / dimensions + 0.5
        visible = np.all((uv >= 0) & (uv <= 1), axis=1) & (center_view[2] > projected[:, 2])
        local = np.clip((uv[visible] * (size - 1)).astype(int), 0, size - 1)
        alpha = pixels[local[:, 1], local[:, 0] + cloud["variant"] * size, 3] * cloud["opacity"]
        opacity[visible] = 1 - (1 - opacity[visible]) * (1 - alpha)
    obscured = float(np.mean(opacity > 0.92))
    assert obscured > 0.97, f"入口屋檐仍可能从云海露出：遮挡率 {obscured:.1%}。"
    roof_report = {"samples": len(roof_points), "obscured_fraction": round(obscured, 4), "minimum_opacity": round(float(opacity.min()), 4)}
report = {"passed": True, "clouds": len(data["clouds"]), "ridges": ridges, "tiles": tiles,
          "gate_diameter_m": gate_radius * 2, "gate_center_z": gate_center, "gate_floor_z": gate_floor,
          "gate_cloud_coverage": round(covered, 4), "eye_height_m": round(float(eye[1]), 3),
          "upper_cloud_coverage": round(upper_coverage, 4), "landmarks": landmarks,
          "gate_landmark_coverage": round(landmark_coverage, 4), "entrance_roof": roof_report,
          "pine_root_surface_distance": round(root_distance, 4),
          "note": "离线资源与几何核验；网页视觉和交互由用户手动验收。"}
destination = ROOT / "qa" / "cloud-sea" / "verification.json"
destination.parent.mkdir(parents=True, exist_ok=True)
destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=False), flush=True)
