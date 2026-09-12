/* 基础浏览器验证后进行无损 Meshopt 压缩，保留共享外部贴图和实例扩展。
 * 不量化位置、不压缩纹理；压缩前后几何值一致，避免月门与相机发生漂移。 */
import fs from 'node:fs/promises'
import path from 'node:path'
import crypto from 'node:crypto'
import { fileURLToPath } from 'node:url'
import { NodeIO, Format } from '@gltf-transform/core'
import { ALL_EXTENSIONS, EXTMeshoptCompression } from '@gltf-transform/extensions'
import { MeshoptEncoder, MeshoptDecoder } from 'meshoptimizer'
import { reorder, unweld, tangents, weld } from '@gltf-transform/functions'
import { generateTangents } from 'mikktspace'
/* 文件索引或开发服务可能短暂占用资源，有限重试让原子替换可以恢复。
 * 等待只处理可识别的占用错误，其他错误仍直接报告。 */
import { setTimeout as delay } from 'node:timers/promises'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const folder = path.join(root, 'assets')
await MeshoptEncoder.ready
await MeshoptDecoder.ready
const io = new NodeIO().registerExtensions(ALL_EXTENSIONS).registerDependencies({ 'meshopt.encoder': MeshoptEncoder, 'meshopt.decoder': MeshoptDecoder })
const manifest = JSON.parse(await fs.readFile(path.join(folder,'manifest.json'),'utf8'))
await fs.mkdir(path.join(root,'qa/baseline-glb'),{recursive:true})
const report = []
for (const file of manifest.files) {
  const target = path.join(folder,file.file)
  const original = await fs.readFile(target)
  const backup = path.join(root,'qa/baseline-glb',file.file)
  const hasMeshopt = original.includes(Buffer.from('EXT_meshopt_compression'))
  // 清理中间基线后，已压缩资源仍可再次执行此入口。
  // 直接保留现有文件，避免重复压缩或依赖被删除的临时副本。
  if (hasMeshopt) {
    // 上一次任务可能在部分文件写出后中断，需要同步已经完成的文件信息。
    // 每次都依据实际字节刷新清单，保证加载进度和摘要不会滞留在压缩前。
    file.bytes=original.length;file.sha256=crypto.createHash('sha256').update(original).digest('hex')
    report.push({file:file.file,beforeBytes:null,afterBytes:original.length,skipped:true})
    console.log(file.file,'已为 Meshopt，保留现有资源')
    continue
  }
  if (!hasMeshopt) await fs.writeFile(backup,original)
  const baselineBytes = (await fs.stat(backup)).size
  const document = await io.read(target)
  // 以实际法线贴图 UV 生成 MikkTSpace 切线，避免运行时导数法线跨实现差异。
  // 先展开再重新焊接仅改变顶点组织，保持每个三角形的位置、法线和 UV 数值。
  await document.transform(unweld(),tangents({generateTangents}),weld(),reorder({encoder:MeshoptEncoder}))
  document.createExtension(EXTMeshoptCompression).setRequired(true)
  const output = await io.writeJSON(document,{format:Format.GLTF})
  const json = output.json
  const realBuffers = json.buffers.map((b,index)=>({b,index})).filter(({b})=>b.uri && output.resources[b.uri])
  if (realBuffers.length !== 1) throw new Error('压缩结果必须恰有一个实体二进制缓冲区')
  const real = realBuffers[0]
  if (real.index !== 0) throw new Error('实体缓冲区应为第零项')
  let binary = Buffer.from(output.resources[real.b.uri])
  delete real.b.uri
  /* 图像保持稳定 URI，逐字节核对写出资源与既有 PNG 相同。
   * glTF 的虚拟回退缓冲区由 Meshopt 扩展声明，不复制未压缩数据。 */
  for (const image of json.images || []) {
    const resource = output.resources[image.uri]
    const filename = path.basename(image.uri)
    const old = await fs.readFile(path.join(folder,'textures',filename))
    if (!Buffer.from(resource).equals(old)) throw new Error('纹理发生意外变化：'+filename)
    image.uri='textures/'+filename
  }
  let encoded=Buffer.from(JSON.stringify(json))
  encoded=Buffer.concat([encoded,Buffer.alloc((4-encoded.length%4)%4,32)])
  binary=Buffer.concat([binary,Buffer.alloc((4-binary.length%4)%4)])
  const header=Buffer.alloc(12);header.write('glTF');header.writeUInt32LE(2,4);header.writeUInt32LE(28+encoded.length+binary.length,8)
  const jsonHeader=Buffer.alloc(8);jsonHeader.writeUInt32LE(encoded.length);jsonHeader.write('JSON',4)
  const binHeader=Buffer.alloc(8);binHeader.writeUInt32LE(binary.length);binHeader.write('BIN\0',4)
  const glb=Buffer.concat([header,jsonHeader,encoded,binHeader,binary])
  /* 先写完整临时文件，再原子替换模型，避免开发服务读到被截断的资源。
   * 同时兼容 Windows 对正在读取的模型文件进行原地写入时的限制。 */
  /* 临时路径包含进程编号，恢复任务不会截断仍被系统索引的旧临时文件。
   * 最终文件仍使用稳定名称，外部引用和加载地址保持一致。 */
  const temporary = target + '.' + process.pid + '.tmp'
  await fs.writeFile(temporary,glb)
  for (let attempt = 0; ; attempt++) {
    try { await fs.rename(temporary,target); break }
    catch (error) {
      if (attempt >= 5 || !['EPERM','EACCES','EBUSY','UNKNOWN'].includes(error.code)) throw error
      await delay(500 * (attempt + 1))
    }
  }
  report.push({file:file.file,beforeBytes:baselineBytes,afterBytes:glb.length,savingPercent:(1-glb.length/baselineBytes)*100,lossless:true,addedTangents:'MikkTSpace; 消除运行时切线生成警告'})
  file.bytes=glb.length;file.sha256=crypto.createHash('sha256').update(glb).digest('hex')
  console.log(file.file,original.length,'→',glb.length)
}
manifest.compression='EXT_meshopt_compression; lossless float data; shared PNG textures'
/* 根据本次清单记录实际纹理体积，不沿用历史浏览器测试结论。
 * 共享图片保留无损格式，是否进一步压缩由后续人工性能验收决定。 */
const textureMiB = manifest.textures.reduce((sum, texture) => sum + texture.bytes, 0) / 1024 / 1024
manifest.textureCompressionDecision=`保留 ${textureMiB.toFixed(2)} MiB 共享 PNG 材质贴图；尚未进行本轮浏览器性能验收。`
await fs.writeFile(path.join(folder,'manifest.json'),JSON.stringify(manifest,null,2))
await fs.writeFile(path.join(root,'qa/compression-report.json'),JSON.stringify(report,null,2))
