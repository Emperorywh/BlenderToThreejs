/* 场景模块负责加载、相机和绘制，页面组件只管理访客可见的交互状态。
 * 保留统一米制坐标和实例化模型，所有请求都相对于静态站点的部署目录。 */
import * as THREE from 'three'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js'
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js'
import { createAtmosphere } from './atmosphere'
import type { EnvironmentLayout } from './atmosphere'

interface CameraRecord {
  projection_type: 'ORTHO' | 'PERSP'
  orthographic_width: number | null
  orthographic_height: number | null
  near: number
  far: number
  vertical_fov_degrees: number | null
  world_matrix: number[]
  projection_matrix: number[]
  direction: [number, number, number]
}
interface ManifestFile { files: { file: string; bytes: number }[] }
interface SceneCallbacks {
  onProgress: (value: number, message: string) => void
  onReady: () => void
  onError: (message: string) => void
  onInteract: () => void
  onCamera: (index: number) => void
}
export interface PalaceScene {
  selectCamera: (index: number) => void
  setTour: (enabled: boolean) => void
  setMotion: (enabled: boolean) => void
  setQuality: (quality: 'balanced' | 'high') => void
  zoom: (direction: number) => void
  dispose: () => void
}

const resourceRoot = import.meta.env.BASE_URL + 'palace-assets/'

/* 释放时按对象去重，保留跨模型共享材质与纹理的引用关系。
 * 异步下载在退出页面后完成时，同样释放其结果，避免重试积累显存。 */
function disposeModels(roots: THREE.Object3D[]) {
  const geometries = new Set<THREE.BufferGeometry>(), materials = new Set<THREE.Material>(), textures = new Set<THREE.Texture>()
  for (const root of roots) root.traverse(object => {
    if (!(object instanceof THREE.Mesh)) return
    geometries.add(object.geometry)
    for (const material of Array.isArray(object.material) ? object.material : [object.material]) {
      materials.add(material)
      for (const value of Object.values(material)) if (value instanceof THREE.Texture) textures.add(value)
    }
    if (object instanceof THREE.InstancedMesh) object.dispose()
  })
  for (const item of [...geometries, ...materials, ...textures]) item.dispose()
}

export function createPalaceScene(host: HTMLDivElement, callbacks: SceneCallbacks): PalaceScene {
  const renderer = new THREE.WebGLRenderer({ antialias: true, logarithmicDepthBuffer: true, powerPreference: 'high-performance' })
  renderer.outputColorSpace = THREE.SRGBColorSpace
  renderer.toneMapping = THREE.ACESFilmicToneMapping
  renderer.toneMappingExposure = .94
  renderer.domElement.tabIndex = 0
  renderer.domElement.setAttribute('aria-label', '天宫三维场景，可拖动旋转，使用方向键观察，加减键缩放')
  renderer.domElement.setAttribute('aria-describedby', 'scene-instructions')
  host.appendChild(renderer.domElement)
  const scene = new THREE.Scene()
  scene.background = new THREE.Color('#d3dfdf')
  scene.fog = new THREE.Fog('#d3dfdf', 2800, 14500)
  const pmrem = new THREE.PMREMGenerator(renderer), room = new RoomEnvironment()
  const environment = pmrem.fromScene(room, .04)
  scene.environment = environment.texture
  scene.environmentIntensity = .36
  room.dispose(); pmrem.dispose()
  scene.add(new THREE.HemisphereLight(0xe2f0ff, 0x847360, .75))
  const sunlight = new THREE.DirectionalLight(0xffefd5, 2.15)
  sunlight.position.set(-300, 600, 400); scene.add(sunlight)
  const modelRoot = new THREE.Group()
  scene.add(modelRoot)
  const abort = new AbortController()
  let disposed = false, failed = false, ready = false, raf = 0, cameraIndex = 0
  let cameraData: CameraRecord[] = [], camera: THREE.PerspectiveCamera | THREE.OrthographicCamera | undefined
  let controls: OrbitControls | undefined, atmosphere: ReturnType<typeof createAtmosphere> | undefined
  let freeMode = false, tour = false, motion = !matchMedia('(prefers-reduced-motion: reduce)').matches
  let quality: 'balanced' | 'high' = 'balanced', width = 1, height = 1, elapsed = 0, lastFrame = 0, dirty = true

  function fail(message: string) {
    if (disposed || failed) return
    failed = true
    abort.abort()
    clearTimeout(loadDeadline)
    callbacks.onError(message)
  }
  const loadDeadline = window.setTimeout(() => fail('这次加载花费了较长时间，请检查网络后重试。'), 180000)
  /* 着色器编译失败也进入统一重试界面，避免把空白画面当作加载完成。
   * 对访客只显示可采取的操作，不暴露内部图形程序信息。 */
  renderer.debug.onShaderError = () => fail('当前浏览器未能绘制完整画面，请重新载入或更新浏览器后尝试。')

  /* 以导出的投影矩阵为基准按视口扩展画幅，保留殿内镜头的水平偏移。
   * 窄屏扩展纵向视野而非裁掉建筑，缩放时只改变投影尺度，不丢失偏移。 */
  function updateProjection() {
    if (!camera) return
    const data = cameraData[cameraIndex], aspect = width / height, originalAspect = 4 / 3
    camera.projectionMatrix.fromArray(data.projection_matrix)
    const matrix = camera.projectionMatrix.elements
    const horizontal = aspect > originalAspect ? originalAspect / aspect : 1
    const vertical = aspect < originalAspect ? aspect / originalAspect : 1
    matrix[0] *= horizontal * camera.zoom
    matrix[5] *= vertical * camera.zoom
    if (camera instanceof THREE.PerspectiveCamera) { matrix[8] *= horizontal; matrix[9] *= vertical }
    else { matrix[12] *= horizontal; matrix[13] *= vertical }
    /* 外景构图为顶部品牌与底部导航留出空间，完整呈现悬岛轮廓。
     * 殿内保持原镜头取景，沉浸与普通模式共享相机，切换时不会跳动。 */
    if (cameraIndex !== 3 && (width > 760 || width / height > 1.3)) {
      matrix[0] *= .78; matrix[5] *= .78
      if (camera instanceof THREE.PerspectiveCamera) matrix[9] -= .19
      else matrix[13] += .19
    }
    camera.projectionMatrixInverse.copy(camera.projectionMatrix).invert()
    dirty = true
  }

  function resize() {
    width = Math.max(1, host.clientWidth); height = Math.max(1, host.clientHeight)
    const pixelBudget = quality === 'high' ? 3600000 : 1900000
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, quality === 'high' ? 2 : 1.5, Math.sqrt(pixelBudget / (width * height))))
    renderer.setSize(width, height, false)
    updateProjection()
  }

  function interact() {
    if (!ready) return
    tour = false; freeMode = true
    if (controls) controls.autoRotate = false
    dirty = true
    callbacks.onInteract()
  }

  function selectCamera(index: number) {
    const data = cameraData[index]
    if (!data || disposed || failed) return
    controls?.dispose()
    cameraIndex = index; freeMode = false; tour = false
    const selected = data.projection_type === 'ORTHO'
      ? new THREE.OrthographicCamera(-(data.orthographic_width ?? 840) / 2, (data.orthographic_width ?? 840) / 2, (data.orthographic_height ?? 630) / 2, -(data.orthographic_height ?? 630) / 2, data.near, data.far)
      : new THREE.PerspectiveCamera(data.vertical_fov_degrees ?? 50, width / height, data.near, data.far)
    camera = selected
    selected.updateProjectionMatrix = updateProjection
    const matrix = new THREE.Matrix4().fromArray(data.world_matrix)
    matrix.decompose(selected.position, selected.quaternion, selected.scale)
    controls = new OrbitControls(selected, renderer.domElement)
    matrix.decompose(selected.position, selected.quaternion, selected.scale)
    controls.target.copy(selected.position).add(new THREE.Vector3(...data.direction).multiplyScalar(index === 3 ? 110 : 1500))
    controls.enableDamping = true; controls.dampingFactor = .075
    controls.rotateSpeed = .55; controls.zoomSpeed = .75; controls.panSpeed = .65
    controls.minDistance = index === 3 ? 3 : 80; controls.maxDistance = 6500
    controls.minZoom = .35; controls.maxZoom = 8
    controls.maxPolarAngle = Math.PI * .88
    controls.autoRotateSpeed = .32
    controls.enabled = ready
    controls.addEventListener('start', interact)
    selected.updateMatrixWorld(true)
    updateProjection()
    callbacks.onCamera(index)
  }

  /* 整体进度由实际模型下载量推进，解码及首次绘制留出独立阶段。
   * 只有完整场景首次成功绘制后才开放操作，避免看到分批弹出的建筑。 */
  async function load() {
    try {
      const read = async <T,>(file: string): Promise<T> => {
        const response = await fetch(resourceRoot + file, { signal: abort.signal })
        if (!response.ok) throw new Error('Scene request failed')
        return response.json()
      }
      const [manifest, cameras, layout] = await Promise.all([
        read<ManifestFile>('manifest.json'), read<{ cameras: CameraRecord[] }>('cameras.json'), read<EnvironmentLayout>('environment-layout.json'),
      ])
      if (disposed || failed) return
      cameraData = cameras.cameras
      selectCamera(0)
      atmosphere = createAtmosphere(layout)
      scene.add(atmosphere.clouds)
      const manager = new THREE.LoadingManager()
      manager.onError = () => fail('未能载入完整的天宫，请检查网络后重新尝试。')
      const loader = new GLTFLoader(manager).setMeshoptDecoder(MeshoptDecoder)
      const total = manifest.files.reduce((sum, file) => sum + file.bytes, 0), received = new Map<string, number>()
      callbacks.onProgress(5, '正在迎来云间宫阙')
      const results = await Promise.allSettled(manifest.files.map(async file => {
        const gltf = await loader.loadAsync(resourceRoot + file.file, event => {
          if (disposed || failed) return
          received.set(file.file, Math.min(event.loaded, file.bytes))
          const loaded = [...received.values()].reduce((sum, value) => sum + value, 0)
          callbacks.onProgress(5 + Math.round(loaded / total * 79), '正在迎来云间宫阙')
        })
        return gltf.scene
      }))
      const roots = results.flatMap(result => result.status === 'fulfilled' ? [result.value] : [])
      if (disposed || failed || results.some(result => result.status === 'rejected')) {
        disposeModels(roots)
        if (!disposed && !failed) fail('天宫暂时未能载入，请检查网络后重试。')
        return
      }
      const materials = new Map<string, THREE.Material>(), replaced = new Set<THREE.Material>(), unusedTextures = new Set<THREE.Texture>()
      for (const root of roots) {
        root.traverse(object => {
          object.updateMatrix(); object.matrixAutoUpdate = false
          if (object instanceof THREE.InstancedMesh) { object.computeBoundingBox(); object.computeBoundingSphere() }
          if (!(object instanceof THREE.Mesh)) return
          const reuse = (material: THREE.Material) => {
            const water = material.name === 'WEB_Waterfall_Static_Preview'
            const shared = water ? atmosphere!.water : material.name ? materials.get(material.name) : undefined
            if (shared && shared !== material) {
              replaced.add(material)
              for (const value of Object.values(material)) if (value instanceof THREE.Texture) unusedTextures.add(value)
              return shared
            }
            if (material.name) materials.set(material.name, material)
            return material
          }
          object.material = Array.isArray(object.material) ? object.material.map(reuse) : reuse(object.material)
        })
        modelRoot.add(root)
      }
      const retained = new Set<THREE.Texture>()
      modelRoot.traverse(object => {
        if (!(object instanceof THREE.Mesh)) return
        for (const material of Array.isArray(object.material) ? object.material : [object.material]) {
          for (const value of Object.values(material)) if (value instanceof THREE.Texture) retained.add(value)
        }
      })
      for (const material of replaced) material.dispose()
      for (const texture of unusedTextures) if (!retained.has(texture)) texture.dispose()
      callbacks.onProgress(92, '云海就绪，即将入境')
      if (camera) {
        atmosphere.update(0, camera)
        await renderer.compileAsync(scene, camera)
      }
      if (disposed || failed) return
      ready = true; dirty = true
      if (controls) controls.enabled = true
    } catch {
      fail('天宫暂时未能载入，请检查网络后重试。')
    }
  }

  let presented = false
  function frame(now: number) {
    if (disposed || failed || document.hidden) { raf = 0; return }
    raf = requestAnimationFrame(frame)
    const delta = lastFrame ? Math.min((now - lastFrame) / 1000, .05) : 0
    lastFrame = now
    if (!camera || !ready) return
    if (motion) elapsed += delta
    const changed = (freeMode || tour) && controls?.update(delta)
    if (motion || changed || dirty || tour) {
      camera.updateMatrixWorld(true)
      atmosphere?.update(elapsed, camera, Boolean(changed) || dirty)
      try { renderer.render(scene, camera) }
      catch { fail('画面暂时中断，请重新载入以继续游览。'); return }
      if (failed) return
      dirty = false
    }
    if (!presented) {
      presented = true
      clearTimeout(loadDeadline)
      callbacks.onProgress(100, '天宫已至')
      callbacks.onReady()
    }
  }

  /* 页面进入后台时停止绘制，恢复后重置帧差，避免额外耗电和镜头跳动。
   * 显卡上下文丢失时给出可重试界面，不让访客停留在黑屏上。 */
  function visibilityChanged() {
    cancelAnimationFrame(raf); raf = 0; lastFrame = 0
    if (!document.hidden && !disposed && !failed) { dirty = true; raf = requestAnimationFrame(frame) }
  }
  function contextLost(event: Event) {
    event.preventDefault()
    fail('画面暂时中断，请重新载入以继续游览。')
  }
  function zoom(direction: number) {
    if (!camera || !controls || !ready || failed) return
    interact()
    if (direction > 0) controls.dollyIn(.84)
    else controls.dollyOut(.84)
    dirty = true
  }
  function keyboard(event: KeyboardEvent) {
    if (!ready || !controls || event.altKey || event.ctrlKey || event.metaKey) return
    if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', '+', '=', '-'].includes(event.key)) return
    event.preventDefault(); interact()
    if (event.key === '+' || event.key === '=') zoom(1)
    else if (event.key === '-') zoom(-1)
    else if (event.key === 'ArrowLeft') controls.rotateLeft(.06)
    else if (event.key === 'ArrowRight') controls.rotateLeft(-.06)
    else if (event.key === 'ArrowUp') controls.rotateUp(.06)
    else controls.rotateUp(-.06)
  }
  const observer = new ResizeObserver(resize)
  observer.observe(host)
  document.addEventListener('visibilitychange', visibilityChanged)
  renderer.domElement.addEventListener('webglcontextlost', contextLost)
  renderer.domElement.addEventListener('keydown', keyboard)
  resize(); void load(); raf = requestAnimationFrame(frame)

  return {
    selectCamera, zoom,
    setTour(enabled) {
      if (!ready || !controls || failed) return
      /* 殿内空间不适合绕目标环行，启动自动环游时回到云端全景。
       * 暂停保留当前观察角度，手动输入也会自然接管控制。 */
      if (enabled && cameraIndex === 3) selectCamera(0)
      tour = enabled; freeMode = true
      controls.autoRotate = enabled
      dirty = true
    },
    setMotion(enabled) { motion = enabled; dirty = true },
    setQuality(value) { quality = value; resize() },
    dispose() {
      disposed = true; abort.abort(); clearTimeout(loadDeadline); cancelAnimationFrame(raf)
      observer.disconnect(); controls?.dispose()
      document.removeEventListener('visibilitychange', visibilityChanged)
      renderer.domElement.removeEventListener('webglcontextlost', contextLost)
      renderer.domElement.removeEventListener('keydown', keyboard)
      disposeModels([modelRoot]); atmosphere?.dispose(); environment.dispose()
      scene.environment = null; scene.clear(); renderer.renderLists.dispose()
      renderer.dispose(); renderer.forceContextLoss(); renderer.domElement.remove()
    },
  }
}
