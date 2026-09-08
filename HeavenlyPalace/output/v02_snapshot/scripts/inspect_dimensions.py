"""从已保存工程实际测量白模比例，而非从截图推断米数。
该脚本同时用于冻结 V01 基线和核对 V02 的人尺度与殿堂进深。
"""
import json
from pathlib import Path
import sys

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]


def bounds(objects):
    """使用对象世界变换后的包围盒测量实体范围。
    同时返回绝对边界和尺寸，便于区别模型变大与相机取景变化。
    """
    points = [o.matrix_world @ Vector(v) for o in objects for v in o.bound_box]
    if not points:
        return None
    low = [min(v[i] for v in points) for i in range(3)]
    high = [max(v[i] for v in points) for i in range(3)]
    return {"min": low, "max": high, "size": [high[i] - low[i] for i in range(3)]}


def main():
    """记录主殿、人物、栏杆、台面和实际柱墙间隙。
    工程保持只读，输出文件只能位于当前项目中。
    """
    scene = next(s for s in bpy.data.scenes if s.get("task_tag") == "TIANGONG_PHASE1")
    bpy.context.window.scene = scene
    bpy.context.view_layer.update()
    c = json.loads(scene["scene_config_json"])
    objects = list(scene.objects)
    groups = {"hall_all": [o for o in objects if o.name.startswith("Hall_") and o.type in {'MESH', 'CURVE'}],
              "hall_columns": [o for o in objects if o.get("component_role") == "hall_column"],
              "hall_roofs": [o for o in objects if o.name.startswith("Hall_Roof_Tier_") and o.type == 'MESH'],
              "human_01": [o for o in objects if o.name.startswith("ScaleHuman_01_")],
              "welcome_deck": [o for o in objects if o.get("platform_id") == "Welcome"],
              "relay_deck": [o for o in objects if o.get("platform_id") == "Relay"],
              "main_deck": [o for o in objects if o.get("platform_id") == "Main"]}
    front_columns = sorted([o for o in groups["hall_columns"]], key=lambda o: o.location.y)
    first = front_columns[0]
    wall = next(o for o in objects if o.name == "Hall_MainMoon_Wall")
    wall_bounds = bounds([wall])
    column_bounds = bounds([first])
    report = {"blend": bpy.data.filepath, "blender": bpy.app.version_string, "revision": c["revision"],
              "units": scene.unit_settings.scale_length, "bounds": {k: bounds(v) for k, v in groups.items()},
              "front_column_axis_y": first.location.y, "door_wall_front_y": wall_bounds["min"][1],
              "clear_colonnade_depth": wall_bounds["min"][1] - column_bounds["max"][1],
              "axis_to_main_front": c["platforms"][2]["center"][1] - c["platforms"][2]["size"][1] / 2,
              "rail_post_height": next(o.dimensions.z for o in objects if o.name.startswith("Rail_Welcome") and "_Post_" in o.name),
              "object_count": len(objects)}
    out = (ROOT / (sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv else "output/dimensions_v02.json")).resolve()
    assert out.is_relative_to(ROOT)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True), flush=True)


if __name__ == "__main__":
    main()
