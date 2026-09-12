"""
在 Windows 下通过同目录临时文件保存 Blender 工程，避免短暂文件占用导致原地保存失败。
只有完整写出后才替换正式文件；替换失败时保留临时工程供恢复，不删除用户文件。
"""
import bpy
import os
import time
import uuid
from pathlib import Path


def save_web_blend(destination):
    """
    每次保存使用独立临时路径，并以有限重试处理索引器和开发服务的短暂占用。
    使用副本保存保持当前工程路径，确保相对贴图引用仍以原目录为基准。
    """
    destination=Path(destination).resolve()
    temporary=destination.with_name(destination.stem+'.'+uuid.uuid4().hex[:10]+'.blend')
    bpy.context.preferences.filepaths.save_version=0
    bpy.ops.wm.save_as_mainfile(filepath=str(temporary),compress=True,copy=True)
    for attempt in range(8):
        try:
            os.replace(temporary,destination)
            return
        except PermissionError:
            if attempt==7:
                raise RuntimeError('正式工程暂时被占用，完整副本保存在：'+str(temporary))
            time.sleep(min(2,.3*(attempt+1)))
