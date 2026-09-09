/* 对照基础 GLB 和最终 GLB 的每个三角形，确认压缩没有改变位置、法线或 UV。
 * 同时核验实例变换数值，补足通用验证器尚不支持实例扩展的检查范围。 */
import fs from 'node:fs/promises'
import path from 'node:path'
import crypto from 'node:crypto'
import { fileURLToPath } from 'node:url'
import { NodeIO } from '@gltf-transform/core'
import { ALL_EXTENSIONS } from '@gltf-transform/extensions'
import { MeshoptDecoder } from 'meshoptimizer'

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..')
await MeshoptDecoder.ready
const io=new NodeIO().registerExtensions(ALL_EXTENSIONS).registerDependencies({'meshopt.decoder':MeshoptDecoder})
const manifest=JSON.parse(await fs.readFile(path.join(root,'assets/manifest.json'),'utf8'))
const reports=[]
function digest(primitive) {
  const attributes=['POSITION','NORMAL','TEXCOORD_0','TEXCOORD_1'].map(name=>primitive.getAttribute(name)).filter(Boolean)
  const index=primitive.getIndices()?.getArray() || Array.from({length:attributes[0].getCount()},(_,i)=>i)
  const hashes=[]
  for(let i=0;i<index.length;i+=3) {
    const vertices=[]
    for(let j=0;j<3;j++) {
      const values=attributes.flatMap(attribute=>Array.from(attribute.getArray().slice(index[i+j]*attribute.getElementSize(),(index[i+j]+1)*attribute.getElementSize())))
      vertices.push(Buffer.from(new Float32Array(values).buffer).toString('hex'))
    }
    const rotations=[vertices.join(''),[vertices[1],vertices[2],vertices[0]].join(''),[vertices[2],vertices[0],vertices[1]].join('')]
    hashes.push(crypto.createHash('sha256').update(rotations.sort()[0]).digest('hex'))
  }
  return crypto.createHash('sha256').update(hashes.sort().join('')).digest('hex')
}
for(const file of manifest.files) {
  // 基础 GLB 的外部图像仍从正式纹理目录解析，校验过程只在内存内补足资源路径。
  // 不复制纹理到基线目录，避免交付包出现多份相同图片。
  const baselineBytes=await fs.readFile(path.join(root,'qa/baseline-glb',file.file))
  const jsonLength=baselineBytes.readUInt32LE(12)
  const json=JSON.parse(baselineBytes.subarray(20,20+jsonLength).toString())
  const resources={}
  for(const image of json.images||[]) resources[image.uri]=new Uint8Array(await fs.readFile(path.join(root,'assets',image.uri)))
  json.buffers[0].uri='baseline.bin';resources['baseline.bin']=new Uint8Array(baselineBytes.subarray(28+jsonLength))
  const baseline=await io.readJSON({json,resources})
  const final=await io.read(path.join(root,'assets',file.file))
  const before=baseline.getRoot().listMeshes().flatMap(m=>m.listPrimitives()).map(digest).sort()
  const after=final.getRoot().listMeshes().flatMap(m=>m.listPrimitives()).map(digest).sort()
  const instanceAttributes=doc=>doc.getRoot().listNodes().filter(n=>n.getExtension('EXT_mesh_gpu_instancing')).map(n=>{
    const extension=n.getExtension('EXT_mesh_gpu_instancing')
    return JSON.stringify(['TRANSLATION','ROTATION','SCALE'].map(key=>Array.from(extension.getAttribute(key).getArray())))
  }).sort()
  const row={file:file.file,trianglesAttributesIdentical:JSON.stringify(before)===JSON.stringify(after),instanceAttributesIdentical:JSON.stringify(instanceAttributes(baseline))===JSON.stringify(instanceAttributes(final))}
  reports.push(row);console.log(row)
}
await fs.writeFile(path.join(root,'qa/compression-integrity.json'),JSON.stringify(reports,null,2))
if(reports.some(r=>!r.trianglesAttributesIdentical||!r.instanceAttributesIdentical))process.exitCode=1
