/* 继续使用现有 Web 工程与依赖，开发时直接读取独立资源目录。
 * 构建时将同一批资源复制到产物，避免维护第二份模型与贴图源文件。 */
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import type { Plugin, ResolvedConfig } from 'vite'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const webRoot = path.dirname(fileURLToPath(import.meta.url))
const assetRoot = path.resolve(webRoot, '../web-assets-v01/assets')

function palaceAssets(): Plugin {
  let config: ResolvedConfig
  return {
    name: 'heavenly-palace-assets',
    configResolved(value) { config = value },
    configureServer(server) {
      server.middlewares.use('/palace-assets', (req, res) => {
        try {
          const filename = path.resolve(assetRoot, '.' + decodeURIComponent((req.url || '/').split('?')[0]))
          const relative = path.relative(assetRoot, filename)
          if (relative.startsWith('..') || path.isAbsolute(relative)) { res.statusCode = 403; res.end(); return }
          if (!fs.existsSync(filename) || !fs.statSync(filename).isFile()) { res.statusCode = 404; res.end('Resource not found'); return }
          const mime: Record<string, string> = { '.glb': 'model/gltf-binary', '.json': 'application/json', '.png': 'image/png' }
          res.setHeader('Content-Type', mime[path.extname(filename)] || 'application/octet-stream')
          res.setHeader('Content-Length', fs.statSync(filename).size)
          res.setHeader('Cache-Control', 'no-cache')
          if (req.method === 'HEAD') { res.end(); return }
          fs.createReadStream(filename).on('error', () => res.destroy()).pipe(res)
        } catch { res.statusCode = 400; res.end('Invalid resource path') }
      })
    },
    writeBundle() {
      fs.cpSync(assetRoot, path.resolve(config.root, config.build.outDir, 'palace-assets'), { recursive: true })
    },
  }
}

export default defineConfig({
  plugins: [react(), palaceAssets()],
  server: { host: '127.0.0.1', port: 5174, strictPort: true },
})
