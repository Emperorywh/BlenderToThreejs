/* 在 Node 中核验云海场景的机位更新、透明排序、异步取消和资源释放。
 * 不创建浏览器或画布，同时导出展开后的着色器供本机驱动离线编译。 */
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import * as THREE from '../../web/node_modules/three/build/three.module.js'
/* 远山替换直接调用生产函数，并使用实际 GLB 材质清单核对分类边界。
 * 测试既覆盖被替换的占位山群，也检查主岛及混合材质网格不会误隐藏。 */
import { createCloudSea, retireLegacyMountains } from '../../web/src/scene/cloudSea.ts'

const root = new URL('../', import.meta.url)
const layout = JSON.parse(await fs.readFile(new URL('assets/environment-layout.json', root), 'utf8'))
const cameras = JSON.parse(await fs.readFile(new URL('assets/cameras.json', root), 'utf8')).cameras
const cloudLayout = JSON.parse(await fs.readFile(new URL('assets/cloud-sea/layout.json', root), 'utf8'))
const originalFetch = globalThis.fetch, originalLoad = THREE.TextureLoader.prototype.loadAsync
let atlasDisposed = 0

/* 只替换下载边界，实际场景构建、矩阵计算和资源释放均执行生产模块。
 * 云图集的像素内容由 Blender 核验脚本检查，此处不伪装浏览器绘制结果。 */
globalThis.fetch = async (_url, options) => {
  options.signal.throwIfAborted()
  return new Response(JSON.stringify(cloudLayout))
}
THREE.TextureLoader.prototype.loadAsync = async () => {
  const texture = new THREE.Texture()
  texture.addEventListener('dispose', () => { atlasDisposed++ })
  return texture
}

/* 复用当前安装版本的 Three.js 着色器片段，递归展开所有引用。
 * 原生编译前缀只适配桌面 GLSL 接口，效果算法仍直接来自生产材质。 */
function expand(source) {
  return source.replace(/#include <([\w]+)>/g, (_match, key) => {
    assert.ok(THREE.ShaderChunk[key], `缺少着色器片段：${key}`)
    return expand(THREE.ShaderChunk[key])
  })
}
const vertexPrefix = `#version 330 core
#define attribute in
#define varying out
#define USE_LOGDEPTHBUF
uniform mat4 modelMatrix, modelViewMatrix, projectionMatrix, viewMatrix;
uniform mat3 normalMatrix;
uniform vec3 cameraPosition;
uniform bool isOrthographic;
in vec3 position, normal;
in vec2 uv;
in mat4 instanceMatrix;
`
const fragmentPrefix = `#version 330 core
#define varying in
#define texture2D texture
#define USE_LOGDEPTHBUF
#define TONE_MAPPING
out vec4 outputColor;
#define gl_FragColor outputColor
uniform mat4 viewMatrix;
uniform vec3 cameraPosition;
uniform bool isOrthographic;
${THREE.ShaderChunk.tonemapping_pars_fragment}
vec3 toneMapping(vec3 color) { return ACESFilmicToneMapping(color); }
${THREE.ShaderChunk.colorspace_pars_fragment}
vec4 linearToOutputTexel(vec4 value) { return sRGBTransferOETF(value); }
`

try {
  /* 从交付地形文件读回网格与材质对应关系，不靠手写对象名模拟旧场景。
   * 无需解码顶点或创建画布即可确认所有原远山批次均被新环境接管。 */
  const terrainBytes = await fs.readFile(new URL('assets/terrain.glb', root))
  const terrain = JSON.parse(terrainBytes.subarray(20, 20 + terrainBytes.readUInt32LE(12)).toString())
  const legacyRoot = new THREE.Group(), dummyGeometry = new THREE.BufferGeometry()
  const sourceMaterials = terrain.materials.map(record => new THREE.MeshBasicMaterial({ name: record.name }))
  for (const node of terrain.nodes) {
    if (node.mesh === undefined) continue
    const mesh = new THREE.Mesh(dummyGeometry, terrain.meshes[node.mesh].primitives.map(primitive => sourceMaterials[primitive.material]))
    mesh.name = node.name
    legacyRoot.add(mesh)
  }
  const mixed = new THREE.Mesh(dummyGeometry, [sourceMaterials.find(material => material.name.includes('远山_空气透视')), sourceMaterials[0]])
  legacyRoot.add(mixed)
  assert.equal(retireLegacyMountains(legacyRoot), 92, '实际地形中的旧远山应完整停用')
  assert.ok(mixed.visible, '混合材质网格不得被整体隐藏')
  assert.ok(legacyRoot.children.filter(mesh => !mesh.name.includes('远山')).every(mesh => mesh.visible), '主岛岩体必须保留')
  dummyGeometry.dispose()
  for (const material of sourceMaterials) material.dispose()
  const effect = await createCloudSea('local/', layout.effects, new AbortController().signal)
  assert.equal(effect.replacesLegacyMountains, true)
  const clouds = effect.group.children.find(item => item.isInstancedMesh)
  /* 入口薄云已按正式中轴机位重建，旧的五团偏置遮檐云应从实例中剔除。
   * 岛边云与瀑布水雾仍保留，核对数量可发现漏接或重复挂载的局部效果。 */
  assert.equal(clouds.count, cloudLayout.clouds.length + layout.effects.filter(item => item.kind !== 'distant_cloud_sea'
    && !(cloudLayout.replacesEntranceMist && item.kind === 'entrance_roof_occluder')).length)
  for (const [index, record] of cameras.entries()) {
    const camera = record.projection_type === 'ORTHO' ? new THREE.OrthographicCamera() : new THREE.PerspectiveCamera()
    new THREE.Matrix4().fromArray(record.world_matrix).decompose(camera.position, camera.quaternion, camera.scale)
    camera.updateMatrixWorld(true)
    effect.update(0, camera, true)
    const matrix = new THREE.Matrix4(), center = new THREE.Vector3()
    let previous = -Infinity
    for (let i = 0; i < clouds.count; i++) {
      clouds.getMatrixAt(i, matrix)
      center.setFromMatrixPosition(matrix).applyMatrix4(camera.matrixWorldInverse)
      assert.ok(center.z >= previous - 0.1, `机位 ${index + 1} 的透明云片排序错误`)
      previous = center.z
    }
    assert.ok(effect.group.children[0].position.equals(camera.position))
  }
  const shaders = [], released = new Set()
  effect.group.traverse(object => {
    if (!object.isMesh) return
    assert.equal(object.material.depthWrite, !object.material.transparent && object.name !== '蓝天与高空薄云')
    object.geometry.addEventListener('dispose', () => released.add(object.geometry))
    object.material.addEventListener('dispose', () => released.add(object.material))
    shaders.push({ name: object.name, vertex: vertexPrefix + expand(object.material.vertexShader), fragment: fragmentPrefix + expand(object.material.fragmentShader) })
  })
  /* 三圈山群与三种岩松材质分别独立绘制，图集实例仍维持单一批次。
   * 确认正式布局包含近景参照，防止只更新渲染代码而漏交付 Blender 几何。 */
  assert.equal(cloudLayout.landmarks.length, 3)
  assert.equal(shaders.length, 9)
  await fs.mkdir(new URL('qa/cloud-sea/', root), { recursive: true })
  await fs.writeFile(new URL('qa/cloud-sea/shaders.json', root), JSON.stringify(shaders))
  effect.dispose()
  assert.equal(released.size, shaders.length * 2)
  assert.equal(atlasDisposed, 1)
  assert.equal(effect.group.children.length, 0)

  /* 下载完成与用户退出可能发生在同一事件循环，单独核验迟到纹理的回收。
   * 使用真正的取消信号触发拒绝，确保资源不会挂回已销毁的场景。 */
  const controller = new AbortController()
  THREE.TextureLoader.prototype.loadAsync = async () => {
    const texture = new THREE.Texture()
    texture.addEventListener('dispose', () => { atlasDisposed++ })
    controller.abort()
    return texture
  }
  await assert.rejects(createCloudSea('local/', [], controller.signal), { name: 'AbortError' })
  assert.equal(atlasDisposed, 2)
  console.log(JSON.stringify({ passed: true, cameras: 4, cloudInstances: clouds.count, materials: shaders.length, lateTextureReleased: true,
    shaderFile: fileURLToPath(new URL('qa/cloud-sea/shaders.json', root)) }))
} finally {
  globalThis.fetch = originalFetch
  THREE.TextureLoader.prototype.loadAsync = originalLoad
}
