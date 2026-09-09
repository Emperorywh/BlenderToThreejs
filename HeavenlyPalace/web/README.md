# 天宫 Web 场景

使用现有 React + TypeScript + Vite + Three.js 环境。
在本目录运行：

```powershell
pnpm install
pnpm dev
```

已安装依赖时只需 `pnpm dev`。地址：http://127.0.0.1:5174/ 。
页面保留模型加载、四机位切换、自由观察和可开关的性能统计。

源码只有 `src/App.tsx`、`src/main.tsx`、`src/scene/PalaceViewer.tsx` 和对应 CSS。
资源唯一来源是 `../web-assets-v01/assets/`；`vite.config.ts` 提供开发资源路径并在构建时复制必要文件。

```powershell
pnpm lint
pnpm build
pnpm preview --host 127.0.0.1 --port 4174
```

部署整个 `dist/`，其中包含网页和 `palace-assets/`。构建目录和依赖目录均不提交 Git。
资源导出方法见 `../web-assets-v01/资源接入与复现.md`。
云海、水雾和瀑布动画仍待实现，稳定 30 FPS 尚未完成验收。
