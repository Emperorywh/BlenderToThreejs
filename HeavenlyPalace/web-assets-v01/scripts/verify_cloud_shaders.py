"""
使用本机 OpenGL 驱动编译从生产模块提取的云海着色器，不创建浏览器或截取界面。
可选依赖 moderngl 安装到忽略的 qa 目录，编译检查不会改变项目运行依赖。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QA = ROOT / "qa" / "cloud-sea"
sys.path.insert(0, str(QA / "python"))
import moderngl

# 独立上下文由驱动在后台建立，仅执行编译和链接，不创建任何可见窗口。
# 每个程序完成后立即释放，测试结束时销毁上下文。
context = moderngl.create_standalone_context(require=330)
records = json.loads((QA / "shaders.json").read_text(encoding="utf-8"))
for record in records:
    program = context.program(vertex_shader=record["vertex"], fragment_shader=record["fragment"])
    program.release()
report = {"passed": True, "programs": len(records), "renderer": context.info["GL_RENDERER"],
          "note": "原生驱动离线编译与链接通过；未启动浏览器，未执行网页截图测试。"}
(QA / "shader-verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
context.release()
print(json.dumps(report, ensure_ascii=False))
