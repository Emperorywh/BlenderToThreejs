# 天宫 · 云上漫游

基于现有 React + TypeScript + Vite + Three.js 工程的全屏三维游览页。
在 `HeavenlyPalace/web` 目录运行：

```powershell
pnpm install
pnpm run dev
```

开发地址：<http://127.0.0.1:5174/>。

## 游览交互

- 四处观景视角：云端全景、正殿揽胜、凌空俯瞰、殿内望云。点击当前视角或恢复按钮，可回到初始构图。
- 鼠标：左键拖动旋转、滚轮缩放、右键拖动平移。触屏：单指旋转、双指缩放与平移。
- 自动环游可随时暂停；手动拖动或缩放会接管镜头。从殿内启动环游时回到云端全景。
- 沉浸观景隐藏界面并保留返回和环游按钮；浏览器支持时另有全屏按钮。
- 观景设置提供均衡／精细画质，以及流云与飞瀑动态效果开关。首次进入遵循系统的减少动态效果偏好。
- 键盘：`1`–`4` 换景，`R` 复位，空格切换环游，`I` 切换沉浸，`H` 打开指南，`Esc` 关闭面板或退出沉浸。聚焦三维画面后可用方向键转动、`+`／`-` 缩放。
- 加载期间显示真实下载进度，完整场景首次绘制后开放操作；网络异常或画面中断可重新载入。切入后台暂停绘制。

## 构建并部署到 NGINX

```powershell
pnpm run build
```

产物为 `web/dist/`。将其中的全部内容复制到 NGINX 站点目录即可，不需要 Node.js 服务、接口服务或 Vite 代理。

```text
dist/
  index.html
  favicon.svg
  assets/          页面脚本与样式
  palace-assets/   模型、贴图与场景配置
```

站点根目录部署可参考 [deploy/nginx.conf](deploy/nginx.conf)，按实际路径修改 `root` 与 `server_name`，将示例的 `server` 部分合入站点配置即可。

构建使用相对路径，也支持子目录：例如将整个产物放到站点的 `palace/` 目录，通过 `https://你的域名/palace/` 访问。子目录地址应带尾斜杠，NGINX 的静态目录处理会自动跳转；如果已有自定义规则，应保留这一跳转。页面没有客户端路径路由，文件不存在时直接返回 404。

`assets/` 内文件名带构建摘要，可长期缓存。`index.html` 与 `palace-assets/` 中的固定文件名应使用协商缓存，避免更新后继续使用旧场景；示例已配置。发布时上传完整产物，保持模型与其外部贴图的相对目录结构。

本地查看构建结果：

```powershell
pnpm run preview --host 127.0.0.1 --port 4174
```

## 代码位置

- `src/scene/PalaceViewer.tsx`、`PalaceViewer.css`：导航、加载、帮助、设置与响应式布局。
- `src/scene/createPalaceScene.ts`：场景加载、相机适配、轨道控制、绘制与生命周期。
- `src/scene/atmosphere.ts`：实例云海、局部云雾与瀑布动态材质。
- `src/scene/views.ts`：四景文案。
- `vite.config.ts`：开发时读取 `../web-assets-v01/assets/`，构建时复制到 `dist/palace-assets/`。不增加模型导出或资源核验步骤。

云层采用实时实例云片，瀑布使用原几何上的动态表面材质；不会改动 Blender 原件，也不依赖远程图片、字体或 CDN。构建目录和依赖目录均不提交 Git。
