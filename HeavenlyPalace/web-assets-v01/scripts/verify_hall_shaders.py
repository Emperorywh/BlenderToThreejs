"""
在本机显卡的独立 OpenGL 上下文编译并链接网页地坪的物理材质着色器。
使用已存在的离线驱动核验依赖，不创建浏览器、窗口或截图。
"""
import json
import sys
from pathlib import Path


def main():
    """
    所有变体均由生产材质与已安装的 Three.js 片段展开，编译失败立即退出。
    核验包含普通网格和实例网格，以及镜像绘制所需的全局裁剪分支。
    """
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / 'qa' / 'cloud-sea' / 'python'))
    import moderngl

    context = moderngl.create_standalone_context(require=330)
    records = json.loads((root / 'qa' / 'hall-lighting' / 'shaders.json').read_text(encoding='utf-8'))
    try:
        for record in records:
            program = context.program(vertex_shader=record['vertex'], fragment_shader=record['fragment'])
            program.release()
        report = {'passed': True, 'programs': len(records), 'renderer': context.info['GL_RENDERER'],
                  'note': '原生驱动编译与链接通过；浏览器视觉效果仍由用户验收。'}
        (root / 'qa' / 'hall-lighting' / 'shader-verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False))
    finally:
        context.release()


if __name__ == '__main__':
    main()
