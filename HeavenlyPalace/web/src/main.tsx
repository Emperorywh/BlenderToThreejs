/* 渲染器由页面组件管理完整的创建和释放生命周期。
 * 开发入口保持单次挂载，避免大型 GLB 在严格模式预演中重复下载解码。 */
import { createRoot } from 'react-dom/client'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <App />,
)
