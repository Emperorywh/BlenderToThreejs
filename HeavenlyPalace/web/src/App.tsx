/* 首页直接承载完整天宫游览，交互与场景代码统一维护在本项目中。
 * 构建产物包含页面及其所需文件，可由静态服务器直接提供访问。 */
import PalaceViewer from './scene/PalaceViewer'
import './scene/PalaceViewer.css'

function App() {
  return <PalaceViewer />
}

export default App
