"""
只重建殿内藻井梁架，保留当前柱网、月门、构图、地形和已经完成的光照资源。
执行前保存本轮独立备份，核验通过后才写回网页工程；导出由统一阶段入口负责。
"""
import hashlib
import json
import shutil
import sys
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import refine_main_hall as hall
from hall_ceiling import build_ceiling, PREFIX, REVISION
from blend_io import save_web_blend
# 藻井重建复用基准几何，完成后恢复当前空间版本，避免重复加高或重复扩展中央开间。
# 验收采样使用同一柱网映射与上抬量，继续检查真实背衬而非更高处的屋面。
from hall_space import UPPER_LIFT, apply_space, column_x, restore_space, space_active


def untouched_digest():
    """
    摘要覆盖本轮藻井以外的全部对象、几何、材质槽和变换，核对局部修改边界。
    使用连续数值数组计算，不生成海量顶点文本，也不改变当前场景数据。
    """
    digest=hashlib.sha256()
    for ob in sorted(bpy.context.scene.objects,key=lambda item:item.name):
        if ob.name.startswith(PREFIX) or ob.name=='H01_井字梁架与分层藻井':
            continue
        digest.update(ob.name.encode())
        digest.update(np.asarray(ob.matrix_world,dtype='<f8').tobytes())
        if ob.type=='MESH':
            coords=np.empty(len(ob.data.vertices)*3,dtype=np.float32)
            ob.data.vertices.foreach_get('co',coords)
            digest.update(coords.tobytes())
            digest.update(str([m.name if m else None for m in ob.data.materials]).encode())
    return digest.hexdigest()


def verify():
    """
    检查共享开间数量、真实分层范围、有效面面积和所有物理贴图的实际文件。
    门洞射线与整体主殿结构继续由已有核验器检查，不以导出成功替代几何核验。
    """
    objects=[ob for ob in bpy.context.scene.objects if ob.name.startswith(PREFIX)]
    meshes={ob.data for ob in objects}
    issues=[]
    triangles=0
    for mesh in meshes:
        mesh.calc_loop_triangles()
        triangles+=len(mesh.loop_triangles)
        if not mesh.uv_layers or any(t.area<1e-8 for t in mesh.loop_triangles):
            issues.append(mesh.name+': 缺失纹理坐标或存在退化面')
        for mat in mesh.materials:
            spec=json.loads(mat['web_spec'])
            for filename in spec['files'].values():
                if not (ROOT/'assets'/'textures'/filename).is_file():
                    issues.append('缺失贴图：'+filename)
    report=dict(revision=REVISION,objects=len(objects),unique_meshes=len(meshes),
                unique_triangles=triangles,side_bays=12,central_bays=3,issues=issues)
    # 井字梁侧和两开间之间是最容易漏到屋架的部位，用向上射线检查实际封口。
    # 射线只查本轮构件且限制十米，命中更高处的屋面不能冒充藻井封闭成功。
    seam_samples=[(0,279.9),(0,313.23),(-45,279.9),(45,313.23),
                  (31.4,295),(-31.4,295),(61.4,261.67),(-61.4,328.33)]
    sealed=[]
    active=space_active()
    lift=UPPER_LIFT if active else 0
    for x,y in seam_samples:
        origin=Vector((column_x(x) if active else x,y,78+lift))
        hits=[]
        for ob in objects:
            inverse=ob.matrix_world.inverted()
            hit,point,normal,face=ob.ray_cast(inverse@origin,Vector((0,0,1)),distance=10)
            if hit:
                hits.append((ob.matrix_world@point).z)
        sealed.append(bool(hits) and min(hits)<85.3+lift)
    report['seams_closed']=sealed
    assert len(objects)==46 and len(meshes)==7, '藻井实例结构不符合设计。'
    assert all(sealed), '藻井安装缝未被实体背衬封闭。'
    assert not issues, str(issues)
    return report


def main():
    """
    备份按本轮版本单独保存，绝不覆盖已有阶段备份；检查模式仅验证不写工程。
    正式模式复用当前主殿集合及公共网格构建器，完成后原子保存可编辑工程。
    """
    qa=ROOT/'qa'
    qa.mkdir(exist_ok=True)
    if '--verify' in sys.argv:
        # 最终工程的检查报告单独保存，记录导出后实体接缝是否仍然封闭。
        # 只写检查目录，不改工程、相机或正式网页资源。
        report=verify()
        (qa/'hall-ceiling-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False),flush=True)
        return
    backup=qa/'before-ceiling-c02'
    if not backup.exists():
        backup.mkdir()
        shutil.copy2(bpy.data.filepath,backup/'HeavenlyPalace_WebAssets_v01.blend')
        shutil.copytree(ROOT/'assets',backup/'assets')
    # 在基准空间比较重建前后摘要，避免可逆浮点变换引入无关的末位差异。
    # 最终保存前再恢复空间比例，局部天花更新不会退回旧层高和旧中央开间。
    active=space_active()
    if active:
        restore_space()
    before=untouched_digest()
    hall.COLS['frame']=bpy.data.collections['04H_主殿样板_梁架斗拱彩画']
    build_ceiling(hall)
    assert untouched_digest()==before, '本轮藻井以外的场景数据发生变化。'
    if active:
        apply_space()
    report=verify()
    report['other_objects_unchanged']=True
    (qa/'hall-ceiling-build.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    save_web_blend(ROOT/'HeavenlyPalace_WebAssets_v01.blend')
    print('CEILING_BUILD_COMPLETE',json.dumps(report,ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()
