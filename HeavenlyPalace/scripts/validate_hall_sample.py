"""重新打开已保存的样板，检查冻结对象及中尺度构件的实际接触。
射线针对真实网格，不用配置里的预期端点代替几何验证。
"""
import hashlib
import json
from pathlib import Path
import sys

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from build_hall_sample import object_map, bbox


def height_interval(obj, x, y):
    """分别从上方和下方射线取实体边界，返回世界空间高度区间。
    对象可有非单位缩放；射线和命中点均通过实际变换换算。
    """
    inverse = obj.matrix_world.inverted()
    heights = []
    for z, direction in ((1000,-1),(-1000,1)):
        local_direction = (inverse.to_3x3() @ Vector((0,0,direction))).normalized()
        hit, co, _, _ = obj.ray_cast(inverse @ Vector((x,y,z)),local_direction,distance=100000)
        assert hit, (obj.name,x,y)
        heights.append((obj.matrix_world @ co).z)
    return sorted(heights)


def overlap(a, b):
    """计算两个实际高度区间的交叠量，正值表示接触或嵌接。
    只检查选定的结构接头，不宣称已经完成建筑工程受力计算。
    """
    return min(a[1],b[1])-max(a[0],b[0])


def main():
    """核验保存后的工程、局部接头和冻结范围，输出可追溯的检查结果。
    此检查不修改或重存 V02 与样板文件。
    """
    cfg = json.loads((ROOT/"hall_sample_config.json").read_text(encoding="utf-8"))
    report = json.loads((ROOT/"output/sample_v03_build_report.json").read_text(encoding="utf-8"))
    path = ROOT/cfg["output_blend"]
    assert hashlib.sha256(path.read_bytes()).hexdigest()==report["output_sha256"]
    bpy.ops.wm.open_mainfile(filepath=str(path))
    scene = bpy.data.scenes["Tiangong_Whitebox"]
    bpy.context.window.scene = scene
    bpy.context.view_layer.update()
    actual = object_map(scene)
    assert actual == report["sample_models"]
    checks = dict(report["checks"])
    checks["saved_model_matches_build"] = True
    checks["baseline_blend_and_config_unchanged"] = (
        hashlib.sha256((ROOT/cfg["base_blend"]).read_bytes()).hexdigest()==cfg["base_blend_sha256"] and
        hashlib.sha256((ROOT/cfg["base_config"]).read_bytes()).hexdigest()==cfg["base_config_sha256"])
    contacts = []
    for p in report["connection_probes"]:
        x,y = p["probe"]
        if p["type"] == "through_roof_transfer":
            beam = height_interval(bpy.data.objects[p["beam"]],x,y)
            block = height_interval(bpy.data.objects[p["object"]],x,y)
            post = height_interval(bpy.data.objects[p["post"]],x,y)
            contacts.append({"type":p["type"],"object":p["object"],"lower_overlap":overlap(beam,block),"upper_overlap":overlap(block,post)})
        elif p["type"] == "rafter_to_roof":
            roof = height_interval(bpy.data.objects[p["roof"]],x,y)
            rafter = height_interval(bpy.data.objects[p["object"]],x,y)
            contacts.append({"type":p["type"],"object":p["object"],"overlap":overlap(roof,rafter)})
        elif p["type"] == "outboard_support":
            arm = height_interval(bpy.data.objects["S03_T%d_Outrigger_%g"%(p["tier"],x)],x,y)
            purlin = height_interval(bpy.data.objects["S03_T%d_Purlin_0"%p["tier"]],x,y)
            contacts.append({"type":p["type"],"probe":[x,y],"overlap":overlap(arm,purlin)})
    checks["actual_sample_contacts_overlap"] = all(min(c[k] for k in c if "overlap" in k) > .005 for c in contacts)
    front_wall = bbox([o for o in scene.objects if o.get("sample_component")=="Wall"])[0][1]
    checks["door_wall_and_colonnade_depth_preserved"] = front_wall >= cfg["sample"]["wall_plane_front_y"]-.001
    # 中央月门通过位置仍使用行人高度检查，不受新增门扇或短柱遮挡。
    # 从前廊进入殿内的轴线通道必须在真实场景射线中保持畅通。
    hit, _, _, _, obj, _ = scene.ray_cast(bpy.context.evaluated_depsgraph_get(),Vector((0,151,29)),Vector((0,1,0)),distance=35)
    checks["central_moon_passage_clear"] = not hit
    checks["four_sample_cameras_saved"] = sum(o.type=='CAMERA' and o.get("sample_view_id") is not None for o in scene.objects)==4
    result = {"checks":checks,"contact_count":len(contacts),"contacts":contacts,
              "front_wall_plane_actual":front_wall,"central_passage_hit":obj.name if hit else None,
              "source_blend_sha256":report["output_sha256"]}
    (ROOT/"output/sample_v03_validation.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print("SAMPLE_VALIDATION "+json.dumps({"checks":checks,"contacts":len(contacts)},ensure_ascii=False),flush=True)
    assert all(checks.values()), result


if __name__ == "__main__":
    main()
