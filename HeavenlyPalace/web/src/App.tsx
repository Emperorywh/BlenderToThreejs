/* 现有 Web 项目首页直接承载天宫资源验证与后续场景开发。
 * 模型文件由 Vite 读取独立交付目录，页面源码统一维护在本项目中。 */
import PalaceViewer from './scene/PalaceViewer'
import './scene/PalaceViewer.css'

function App() {
  return <PalaceViewer />
}

export default App
