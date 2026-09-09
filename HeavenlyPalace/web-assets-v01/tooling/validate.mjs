/* 使用 Khronos 验证器读取最终二进制及其外部纹理，输出可审阅的问题清单。
 * 不只检查文件是否存在，同时检查 glTF 结构、访问器范围和扩展声明。 */
import fs from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import validator from 'gltf-validator'
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const manifest = JSON.parse(await fs.readFile(path.join(root, 'assets/manifest.json'), 'utf8'))
const reports = []
for (const file of manifest.files) {
  const data = new Uint8Array(await fs.readFile(path.join(root, 'assets', file.file)))
  const report = await validator.validateBytes(data, { uri: file.file, maxIssues: 100, externalResourceFunction: async uri => new Uint8Array(await fs.readFile(path.join(root, 'assets', decodeURIComponent(uri)))) })
  reports.push({ file: file.file, ...report })
  console.log(file.file, JSON.stringify(report.issues))
}
await fs.writeFile(path.join(root, 'qa/gltf-validation.json'), JSON.stringify(reports, null, 2))
if (reports.some(r => r.issues.numErrors)) process.exitCode = 1
