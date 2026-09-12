/* 在 Node 中检查真实机位的镜像投影、主殿阴影覆盖和异常后的绘制状态恢复。
 * 只替换显卡绘制边界，矩阵、材质注入和生命周期均执行网页生产模块。 */
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import * as THREE from '../../web/node_modules/three/build/three.module.js'
import { createHallFloorReflection } from '../../web/src/scene/hallFloor.ts'
import { createSkyRadiance, fitSunShadow } from '../../web/src/scene/palaceLighting.ts'
import { HALL_FLOOR_MATERIAL, HALL_FLOOR_HEIGHT, PALACE_SUN } from '../../web/src/scene/lightingProfile.ts'

const root = new URL('../', import.meta.url), qa = new URL('qa/hall-lighting/', root)
const records = JSON.parse(await fs.readFile(new URL('assets/cameras.json', root), 'utf8')).cameras
const glb = await fs.readFile(new URL('assets/architecture.glb', root))
const doc = JSON.parse(glb.subarray(20, 20 + glb.readUInt32LE(12)).toString())
assert.ok(doc.materials.some(material => material.name === HALL_FLOOR_MATERIAL), '实际建筑必须包含目标地坪材质')
const audit = JSON.parse(await fs.readFile(new URL('sun-audit.json', qa), 'utf8'))
assert.equal(audit.floor_height, HALL_FLOOR_HEIGHT)
assert.ok(new THREE.Vector3(...audit.directions.warm_low.three_direction).distanceTo(new THREE.Vector3(...PALACE_SUN).normalize()) < 1e-6)
/* 门洞和柱网改变后，旧太阳方向也会照进更大的开口，旧版两倍比值不再代表灯光正确性。
 * 检查当前几何下暖阳仍增加受光范围，并同时保留受光与阴影区域用于地坪层次。 */
assert.ok(audit.directions.warm_low.lit_fraction > audit.directions.original.lit_fraction)
assert.ok(audit.directions.warm_low.lit_fraction > 0 && audit.directions.warm_low.lit_fraction < 1)

/* 用主殿完整边界校验阴影投影，检查缩小范围后不会裁掉屋顶或地坪接收面。
 * 外景与殿内使用同一光源位置，两者只改变正交投影覆盖范围。 */
const sun = new THREE.DirectionalLight()
sun.target.position.set(0, 65, -280)
sun.position.copy(sun.target.position).addScaledVector(new THREE.Vector3(...PALACE_SUN).normalize(), 1800)
fitSunShadow(sun, true)
const shadowCamera = sun.shadow.camera
/* 空间调整后的脊饰最高点接近一百四十六米，检查包围整个新屋顶的边界。
 * 地坪下缘保持原标高，确认上抬屋面后接收面与遮挡物同时落在阴影投影内。 */
for (const x of [-140, 140]) for (const y of [24, 148]) for (const z of [-390, -214]) {
  const projected = new THREE.Vector3(x, y, z).project(shadowCamera)
  assert.ok(projected.toArray().every(value => Math.abs(value) < 1), '主殿边界被阴影相机裁掉')
}
const interiorWidth = shadowCamera.right - shadowCamera.left
fitSunShadow(sun, false)
assert.ok(shadowCamera.right - shadowCamera.left > interiorWidth * 3)
const sky = createSkyRadiance()
assert.ok(sky.image.data.every(Number.isFinite))
assert.equal(sky.colorSpace, THREE.LinearSRGBColorSpace)
sky.dispose()

/* 绘制替身检查反射期间隐藏地坪并裁掉地下实体，同时记录真实镜像相机。
 * 模拟异常用于保证主场景不会继承离屏目标、裁剪平面或错误可见性。 */
let renderTarget = null, captures = 0, failCapture = false, mirroredCamera
const scene = new THREE.Scene(), originalClip = []
const renderer = {
  xr: { enabled: false }, shadowMap: { autoUpdate: false }, clippingPlanes: originalClip, autoClear: true,
  getRenderTarget: () => renderTarget,
  setRenderTarget: target => { renderTarget = target },
  state: { buffers: { depth: { setMask() {} } }, viewport() {} },
  render(_scene, camera) {
    captures++; mirroredCamera = camera
    assert.equal(floor.visible, false)
    assert.ok(renderer.clippingPlanes[0].distanceToPoint(new THREE.Vector3(0, 40, 0)) > 0)
    assert.ok(renderer.clippingPlanes[0].distanceToPoint(new THREE.Vector3(0, 32, 0)) < 0)
    if (failCapture) throw new Error('模拟离屏绘制中断')
  },
}
const material = new THREE.MeshStandardMaterial({ name: HALL_FLOOR_MATERIAL })
const floor = new THREE.Mesh(new THREE.BoxGeometry(240, 1.1, 132), material)
floor.position.set(0, 35.45, -300)
scene.add(floor)
const effect = createHallFloorReflection(renderer, scene)
effect.attach(scene)
const shader = { uniforms: {}, vertexShader: THREE.ShaderLib.standard.vertexShader, fragmentShader: THREE.ShaderLib.standard.fragmentShader }
material.onBeforeCompile(shader, renderer)
const camera = new THREE.PerspectiveCamera()
const data = records[3]
new THREE.Matrix4().fromArray(data.world_matrix).decompose(camera.position, camera.quaternion, camera.scale)
camera.projectionMatrix.fromArray(data.projection_matrix)
camera.projectionMatrixInverse.copy(camera.projectionMatrix).invert()
camera.updateMatrixWorld(true)
effect.update(camera, 0, true)
assert.ok(Math.abs(mirroredCamera.position.y - (2 * HALL_FLOOR_HEIGHT - camera.position.y)) < 1e-6)
assert.equal(captures, 1)
assert.equal(floor.visible, true)
assert.equal(renderTarget, null)
assert.equal(renderer.clippingPlanes, originalClip)
assert.equal(shader.uniforms.hallReflectionReady.value, 1)

/* 从观察点连到柱子的虚像，求出地面反射点，再检查其采样位置是否指向实柱。
 * 镜像相机的左右手变换允许纹理横向翻转，物理射线对应关系必须严格吻合。 */
assert.equal(mirroredCamera.projectionMatrix.elements[8], camera.projectionMatrix.elements[8])
for (const point of [new THREE.Vector3(0, 65, -285), new THREE.Vector3(22, 48, -315)]) {
  const image = point.clone(); image.y = 2 * HALL_FLOOR_HEIGHT - point.y
  const t = (HALL_FLOOR_HEIGHT - camera.position.y) / (image.y - camera.position.y)
  const surface = camera.position.clone().lerp(image, t)
  const screen = point.clone().project(mirroredCamera)
  const reflected = new THREE.Vector4(surface.x, surface.y, surface.z, 1).applyMatrix4(shader.uniforms.hallReflectionMatrix.value)
  assert.ok(Math.abs(reflected.x / reflected.w - (screen.x * .5 + .5)) < 1e-5)
  assert.ok(Math.abs(reflected.y / reflected.w - (screen.y * .5 + .5)) < 1e-5)
}
effect.update(camera, 0, false)
assert.equal(captures, 1, '暂停动态时应复用反射')
effect.setQuality('high')
assert.equal(shader.uniforms.hallReflection.value.image.width, 1152)
effect.update(camera, 0, false)
assert.equal(captures, 2)
failCapture = true
assert.throws(() => effect.update(camera, 1, true), /模拟离屏绘制中断/)
assert.equal(floor.visible, true)
assert.equal(renderTarget, null)
assert.equal(renderer.clippingPlanes, originalClip)
camera.position.set(...records[0].position)
effect.update(camera, 2, true)
assert.equal(captures, 3, '外景不绘制反射')
assert.equal(shader.uniforms.hallReflectionReady.value, 0)
effect.dispose(); floor.geometry.dispose(); material.dispose(); sun.shadow.dispose()

/* 按已安装的 Three.js 展开物理材质，覆盖贴图、实例、阴影与对数深度组合。
 * 桌面前缀仅替换语言接口，生产模块注入的石材反射算法保持原样交由驱动编译。 */
function expand(source, clipping) {
  source = source.replace(/#include <([\w]+)>/g, (_match, key) => {
    assert.ok(THREE.ShaderChunk[key], `缺少着色器片段：${key}`)
    return expand(THREE.ShaderChunk[key], clipping)
  })
  source = source.replace(/NUM_[A-Z_]+/g, name => ({ NUM_DIR_LIGHTS: 1, NUM_HEMI_LIGHTS: 1, NUM_DIR_LIGHT_SHADOWS: 1, NUM_CLIPPING_PLANES: clipping }[name] ?? 0))
    .replace(/UNION_CLIPPING_PLANES/g, String(clipping))
  return source.replace(/#pragma unroll_loop_start\s+for\s*\(\s*int i = (\d+);\s*i < (\d+);\s*i\+\+\s*\)\s*{([\s\S]+?)}\s+#pragma unroll_loop_end/g,
    (_match, start, end, body) => Array.from({ length: Number(end) - Number(start) }, (_, n) => body.replace(/\[\s*i\s*\]/g, `[ ${n + Number(start)} ]`).replace(/UNROLLED_LOOP_INDEX/g, String(n + Number(start)))).join(''))
}
const defines = `
#define USE_ENVMAP
#define ENVMAP_TYPE_CUBE_UV
#define ENVMAP_MODE_REFLECTION
#define CUBEUV_TEXEL_WIDTH 0.001302083333
#define CUBEUV_TEXEL_HEIGHT 0.0009765625
#define CUBEUV_MAX_MIP 8.0
#define USE_MAP
#define MAP_UV uv
#define USE_NORMALMAP
#define USE_NORMALMAP_TANGENTSPACE
#define NORMALMAP_UV uv
#define USE_ROUGHNESSMAP
#define ROUGHNESSMAP_UV uv
#define USE_METALNESSMAP
#define METALNESSMAP_UV uv
#define USE_SHADOWMAP
#define SHADOWMAP_TYPE_PCF
#define HAS_NORMAL
#define USE_FOG
#define USE_LOGARITHMIC_DEPTH_BUFFER
`
const vertexPrefix = `#version 330 core
#define attribute in
#define varying out
${defines}
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
#define texture2DLodEXT textureLod
#define textureCube texture
${defines}
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
const shaders = []
for (const instanced of [false, true]) for (const clipping of [0, 1]) {
  const variant = instanced ? '#define USE_INSTANCING\n' : ''
  shaders.push({ name: `地坪_实例${instanced}_裁剪${clipping}`, vertex: vertexPrefix + variant + expand(shader.vertexShader, clipping),
    fragment: fragmentPrefix + '#define TONE_MAPPING\n' + expand(shader.fragmentShader, clipping) })
}
await fs.mkdir(qa, { recursive: true })
await fs.writeFile(new URL('shaders.json', qa), JSON.stringify(shaders))
const report = { passed: true, shadowWidthMeters: interiorWidth, balancedShadowTexelMeters: interiorWidth / 2048,
  mirroredProjection: true, captureStateRestored: true, outsideReflectionSkipped: true, shaderVariants: shaders.length,
  note: '完成数据与生命周期检查，未启动浏览器或执行界面截图。' }
await fs.writeFile(new URL('runtime-verification.json', qa), JSON.stringify(report, null, 2))
console.log(JSON.stringify(report))
