"""为 V02 与主殿样板使用同一组固定机位，渲染前后对照。
渲染时不移动模型，不按机位隐藏对象，基线仅临时添加相机且不保存。
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from render_whitebox import material_signature


def apply_cameras(scene, config):
    """从唯一的样板机位参数创建四个相机，两个版本使用同一函数。
    保留原来的 V02 相机与照明，不修改模型或白模材质。
    """
    col = bpy.data.collections.get("TG_S03_样板验收相机")
    if col is None:
        col = bpy.data.collections.new("TG_S03_样板验收相机")
        scene.collection.children.link(col)
    for name, p in config["cameras"].items():
        obj = bpy.data.objects.get("S03_Camera_"+name)
        if obj is None:
            data = bpy.data.cameras.new("S03_Camera_"+name)
            obj = bpy.data.objects.new("S03_Camera_"+name,data)
            col.objects.link(obj)
        obj.location = p["location"]
        obj.rotation_euler = (Vector(p["target"])-obj.location).to_track_quat('-Z','Y').to_euler()
        obj.data.type = 'PERSP'
        obj.data.lens = p["lens"]
        obj.data.sensor_width = 36
        obj.data.sensor_fit = 'HORIZONTAL'
        obj.data.clip_start, obj.data.clip_end = .1,2000
        obj.data.dof.use_dof = False
        obj["sample_view_id"] = name
    scene.camera = bpy.data.objects["S03_Camera_sample_close"]
    bpy.context.view_layer.update()


def camera_record(obj):
    """记录 Blender 中的实际相机参数，不能只记录预期配置。
    包括偏移、感光元件及裁剪范围，使固定机位对照能够复核。
    """
    return {"matrix_world":[list(row) for row in obj.matrix_world],"type":obj.data.type,
            "lens":obj.data.lens,"sensor_width":obj.data.sensor_width,"sensor_height":obj.data.sensor_height,
            "sensor_fit":obj.data.sensor_fit,"shift":[obj.data.shift_x,obj.data.shift_y],
            "clip":[obj.data.clip_start,obj.data.clip_end],"dof":obj.data.dof.use_dof}


def main():
    """从磁盘重新打开基线或样板，保存原始 PNG 与渲染记录。
    最终统一清单由独立收尾脚本在全部图片保存后重新生成并逐张校验哈希。
    """
    from build_hall_sample import object_map
    parser = argparse.ArgumentParser()
    parser.add_argument("--before",action="store_true")
    parser.add_argument("--draft",action="store_true")
    parser.add_argument("--views",nargs="+")
    parser.add_argument("--output")
    args = parser.parse_args(sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else [])
    config_text = (ROOT/"hall_sample_config.json").read_text(encoding="utf-8")
    config = json.loads(config_text)
    source = (ROOT/config["base_blend" if args.before else "output_blend"]).resolve()
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    if args.before:
        assert source_hash == config["base_blend_sha256"]
    bpy.ops.wm.open_mainfile(filepath=str(source))
    scene = bpy.data.scenes["Tiangong_Whitebox"]
    bpy.context.window.scene = scene
    bpy.context.view_layer.update()
    if not args.before:
        assert scene["sample_config_json"] == config_text
    model_before = object_map(scene)
    apply_cameras(scene,config)
    assert object_map(scene) == model_before
    scene.render.engine = config["render"]["engine"]
    scene.cycles.device = 'CPU'
    scene.cycles.samples = config["render"]["draft_samples" if args.draft else "samples"]
    scene.cycles.use_denoising = True
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGB'
    scene.render.image_settings.color_depth = '8'
    scene.render.film_transparent = False
    variant = "before" if args.before else "after"
    out = (ROOT/(args.output or config["output_images"])/variant).resolve()
    assert out.is_relative_to(ROOT)
    out.mkdir(parents=True,exist_ok=True)
    record = {"variant":variant,"source_blend":str(source),"source_sha256":source_hash,
              "sample_config_sha256":hashlib.sha256(config_text.encode()).hexdigest(),
              "base_config_sha256":scene["config_sha256"],"draft":args.draft,"blender":bpy.app.version_string,
              "materials":material_signature(scene),"lights":[{"name":o.name,"matrix":[list(r) for r in o.matrix_world],
                "energy":o.data.energy,"size":o.data.size,"shape":o.data.shape,"color":list(o.data.color),"hide_render":o.hide_render}
                for o in sorted(scene.objects,key=lambda o:o.name) if o.type=='LIGHT'],
              "world":{"color":list(scene.world.node_tree.nodes['Background'].inputs[0].default_value),
                       "strength":scene.world.node_tree.nodes['Background'].inputs[1].default_value},
              "render_settings":{"engine":scene.render.engine,"samples":scene.cycles.samples,"denoise":scene.cycles.use_denoising,
                "view_transform":scene.view_settings.view_transform,"look":scene.view_settings.look,
                "exposure":scene.view_settings.exposure,"gamma":scene.view_settings.gamma,"transparent":scene.render.film_transparent},
              "models_sha256":hashlib.sha256(json.dumps(model_before,sort_keys=True).encode()).hexdigest(),"views":[]}
    for name in args.views or config["cameras"]:
        scene.camera = bpy.data.objects["S03_Camera_"+name]
        res = config["cameras"][name]["resolution"]
        scale = config["render"]["draft_scale"] if args.draft else 1
        scene.render.resolution_x,scene.render.resolution_y = [round(v*scale) for v in res]
        scene.render.resolution_percentage = 100
        path = out/(name+".png")
        scene.render.filepath = str(path)
        assert object_map(scene) == model_before
        start = time.time()
        bpy.ops.render.render(write_still=True)
        assert object_map(scene) == model_before
        record["views"].append({"name":name,"file":str(path),"camera":camera_record(scene.camera),
                                "resolution":[scene.render.resolution_x,scene.render.resolution_y],
                                "sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"seconds":round(time.time()-start,2)})
        print("SAMPLE_RENDER "+variant+" "+name,flush=True)
    record["same_models_and_visibility_for_all_views"] = object_map(scene) == model_before
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
    (out/"render_receipt.json").write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding="utf-8")
    print("SAMPLE_RENDER_COMPLETE "+variant,flush=True)


if __name__ == "__main__":
    main()
