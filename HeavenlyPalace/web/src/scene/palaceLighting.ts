/* 以低角度暖阳和户外天空反射建立殿内外的明暗关系。
 * 阴影随观察位置切换覆盖范围，太阳方向和色温始终保持一致。 */
import * as THREE from 'three'
import { PALACE_SUN } from './lightingProfile.ts'

/* 用线性高动态范围颜色生成户外环境，避免通用展厅的白色灯箱映入玉柱。
 * 不加入尖锐太阳圆盘，以免与方向光重复产生高光；下半球代表云海反弹光。 */
export function createSkyRadiance() {
  const width = 256, height = 128, pixels = new Float32Array(width * height * 4)
  const direction = new THREE.Vector3(...PALACE_SUN).normalize()
  for (let y = 0; y < height; y++) {
    const latitude = (y + .5) / height * Math.PI
    const elevation = -Math.cos(latitude), ring = Math.sin(latitude)
    for (let x = 0; x < width; x++) {
      const longitude = ((x + .5) / width - .5) * Math.PI * 2
      const alignment = ring * Math.cos(longitude) * direction.x + elevation * direction.y + ring * Math.sin(longitude) * direction.z
      const glow = Math.pow(Math.max(alignment, 0), 12) * .6
      const blend = Math.pow(Math.abs(elevation), .55)
      const horizon = [.64, .74, .80], pole = elevation >= 0 ? [.12, .29, .48] : [.38, .35, .29]
      const index = (y * width + x) * 4
      for (let channel = 0; channel < 3; channel++) pixels[index + channel] = THREE.MathUtils.lerp(horizon[channel], pole[channel], blend) + glow * [1, .65, .28][channel]
      pixels[index + 3] = 1
    }
  }
  const texture = new THREE.DataTexture(pixels, width, height, THREE.RGBAFormat, THREE.FloatType)
  texture.mapping = THREE.EquirectangularReflectionMapping
  texture.colorSpace = THREE.LinearSRGBColorSpace
  texture.needsUpdate = true
  return texture
}

/* 将真实主殿边界投到灯光空间，集中有限的阴影像素用于柱脚、月门与梁架。
 * 外景重新覆盖近岛；切换只重建静态阴影，不叠加第二盏太阳或双重投影。 */
export function fitSunShadow(sun: THREE.DirectionalLight, interior: boolean) {
  /* 主殿空间调整后屋脊最高点约为一百四十六米，阴影范围同步覆盖新的屋面。
   * 保留地坪和柱脚接收面，避免抬高后的屋顶超出殿内阴影相机边界。 */
  const bounds = interior
    ? new THREE.Box3(new THREE.Vector3(-140, 24, -390), new THREE.Vector3(140, 148, -214))
    : new THREE.Box3(new THREE.Vector3(-650, -500, -850), new THREE.Vector3(650, 210, 850))
  sun.updateMatrixWorld(true); sun.target.updateMatrixWorld(true)
  sun.shadow.updateMatrices(sun)
  const lightBounds = new THREE.Box3(), point = new THREE.Vector3()
  for (const x of [bounds.min.x, bounds.max.x]) for (const y of [bounds.min.y, bounds.max.y]) for (const z of [bounds.min.z, bounds.max.z]) {
    lightBounds.expandByPoint(point.set(x, y, z).applyMatrix4(sun.shadow.camera.matrixWorldInverse))
  }
  const camera = sun.shadow.camera, padding = interior ? 8 : 24
  camera.left = lightBounds.min.x - padding; camera.right = lightBounds.max.x + padding
  camera.bottom = lightBounds.min.y - padding; camera.top = lightBounds.max.y + padding
  camera.near = 1; camera.far = 3600
  sun.shadow.bias = interior ? -.000008 : -.00004
  sun.shadow.normalBias = interior ? .025 : .12
  sun.shadow.radius = 1.5
  camera.updateProjectionMatrix()
}

/* 环境纹理只预过滤一次，日光阴影只在机位覆盖范围和画质变化时更新。
 * 所有离屏资源统一释放，重复加载场景不会累积环境贴图或阴影贴图。 */
export function createPalaceLighting(renderer: THREE.WebGLRenderer, scene: THREE.Scene) {
  const source = createSkyRadiance(), pmrem = new THREE.PMREMGenerator(renderer)
  const environment = pmrem.fromEquirectangular(source)
  source.dispose(); pmrem.dispose()
  scene.environment = environment.texture
  scene.environmentIntensity = .48
  const fill = new THREE.HemisphereLight('#b9d7f4', '#b49a77', .16)
  const sun = new THREE.DirectionalLight('#ffe0ad', 3.6)
  sun.target.position.set(0, 65, -280)
  sun.position.copy(sun.target.position).addScaledVector(new THREE.Vector3(...PALACE_SUN).normalize(), 1800)
  sun.castShadow = true
  sun.shadow.mapSize.set(2048, 2048)
  scene.add(fill, sun, sun.target)
  let interior = false
  fitSunShadow(sun, interior)
  return {
    /* 按实际观察位置启用殿内精度，拖动到外景后自动恢复近岛覆盖。
     * 留出边界缓冲，防止柱廊附近的微小移动反复切换阴影贴图。 */
    update(camera: THREE.Camera) {
      const p = camera.position, margin = interior ? 30 : 0
      const next = Math.abs(p.x) < 145 + margin && p.y > 30 - margin && p.y < 120 + margin && p.z > -415 - margin && p.z < -205 + margin
      if (next === interior) return
      interior = next; fitSunShadow(sun, interior)
      renderer.shadowMap.needsUpdate = true
    },
    setQuality(quality: 'balanced' | 'high') {
      const size = Math.min(renderer.capabilities.maxTextureSize, quality === 'high' ? 4096 : 2048)
      if (sun.shadow.mapSize.x === size) return
      sun.shadow.map?.dispose(); sun.shadow.map = null
      sun.shadow.mapSize.set(size, size)
      renderer.shadowMap.needsUpdate = true
    },
    dispose() {
      scene.environment = null
      scene.remove(fill, sun, sun.target)
      environment.dispose(); sun.shadow.dispose()
    },
  }
}
