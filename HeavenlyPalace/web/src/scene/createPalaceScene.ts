/* 场景模块负责加载、相机和绘制，页面组件只管理访客可见的交互状态。
 * 保留统一米制坐标和实例化模型，所有请求都相对于静态站点的部署目录。 */
import * as THREE from 'three'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js'
import { createAtmosphere } from './atmosphere'
import type { EnvironmentLayout } from './atmosphere'
/* 新云海包含完整环绕山群，旧 GLB 中的专用远山占位材质用于精确识别。
 * 只在新资产加载完成后关闭旧山群绘制，主岛岩壁与桥台继续使用原模型。 */
import { retireLegacyMountains } from './cloudSea'
/* 光照与石坪反射独立管理，场景入口只负责加载后的接入与逐帧调度。
 * 两者共享原建筑和相机，不需要重新导出或移动已经完成的模型资产。 */
import { createPalaceLighting } from './palaceLighting'
import { createHallFloorReflection } from './hallFloor'

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
  /* 殿内构图由 Blender 导出宽屏倍率和门口地坪锚点，网页直接使用同一份参数。
   * 字段可选，旧相机资源及三个外景机位继续采用原有的等比扩幅规则。 */
  composition_framing?: {
    reference_aspect: number
    wide_aspect: number
    wide_scale: number
    floor_anchor_ndc: number
  }
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
  /* 暖阳照亮柱面，阴影保留冷色天空补光，并以统一曝光保住白玉高光。
   * 使用当前版本的软化阴影采样，静态阴影只在覆盖范围或画质变化时重绘。 */
  renderer.toneMappingExposure = .92
  renderer.shadowMap.enabled = true
  renderer.shadowMap.type = THREE.PCFShadowMap
  renderer.shadowMap.autoUpdate = false
  renderer.domElement.tabIndex = 0
  renderer.domElement.setAttribute('aria-label', '天宫三维场景，可拖动旋转，使用方向键观察，加减键缩放')
  renderer.domElement.setAttribute('aria-describedby', 'scene-instructions')
  host.appendChild(renderer.domElement)
  const scene = new THREE.Scene()
  /* 雾色与云海地平线一致，保留近岛对比，同时让旧地形自然融入新远景。
   * 正式天空由云海模块绘制，底色仅用于资源尚未完成时的背景。 */
  scene.background = new THREE.Color('#d2e0e6')
  scene.fog = new THREE.Fog('#d2e0e6', 3800, 24000)
  /* 户外环境提供天空与云海的反弹光，殿内近景另取实际建筑的平面反射。
   * 反射目标保持线性空间，避免倒影与正常场景产生不同的曝光。 */
  const lighting = createPalaceLighting(renderer, scene)
  const floorReflection = createHallFloorReflection(renderer, scene)
  const modelRoot = new THREE.Group()
  scene.add(modelRoot)
  const abort = new AbortController()
  let disposed = false, failed = false, ready = false, raf = 0, cameraIndex = 0
  let cameraData: CameraRecord[] = [], camera: THREE.PerspectiveCamera | THREE.OrthographicCamera | undefined
  /* 环境需等待体积图集下载，因此保存异步创建后的效果对象类型。
   * 后续相机更新与退出释放仍通过同一对象完成。 */
  let controls: OrbitControls | undefined, atmosphere: Awaited<ReturnType<typeof createAtmosphere>> | undefined
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

  /* 以导出的投影矩阵为基准按视口扩展画幅，保留殿内建筑镜头的竖向上移。
   * 窄屏扩展纵向视野而非裁掉建筑，缩放时只改变投影尺度，不丢失偏移。 */
  function updateProjection() {
    if (!camera) return
    const data = cameraData[cameraIndex], aspect = width / height, originalAspect = 4 / 3
    camera.projectionMatrix.fromArray(data.projection_matrix)
    const matrix = camera.projectionMatrix.elements
    /* 新云海延伸到二十八公里，扩展深度范围以免外景机位截掉远云与远山。
     * 仅调整投影深度项，焦距和镜头偏移始终读取当前正式相机数据。 */
    const far = camera.far, near = camera.near
    matrix[10] = camera instanceof THREE.PerspectiveCamera ? -(far + near) / (far - near) : -2 / (far - near)
    matrix[14] = camera instanceof THREE.PerspectiveCamera ? -2 * far * near / (far - near) : -(far + near) / (far - near)
    const horizontal = aspect > originalAspect ? originalAspect / aspect : 1
    const vertical = aspect < originalAspect ? aspect / originalAspect : 1
    matrix[0] *= horizontal * camera.zoom
    matrix[5] *= vertical * camera.zoom
    if (camera instanceof THREE.PerspectiveCamera) { matrix[8] *= horizontal; matrix[9] *= vertical }
    else { matrix[12] *= horizontal; matrix[13] *= vertical }
    /* 殿内从三比二到超宽画幅逐步收紧视野，防止月门随横向扩幅不断缩小。
     * 横纵使用相同倍率保持圆弧比例，并绕门口地坪收紧，保留地面反射的前景。 */
    const framing = data.composition_framing
    if (cameraIndex === 3 && camera instanceof THREE.PerspectiveCamera && framing) {
      const progress = THREE.MathUtils.clamp((aspect - framing.reference_aspect) / (framing.wide_aspect - framing.reference_aspect), 0, 1)
      const scale = THREE.MathUtils.lerp(1, framing.wide_scale, progress)
      matrix[0] *= scale; matrix[5] *= scale; matrix[8] *= scale
      matrix[9] = matrix[9] * scale + (scale - 1) * framing.floor_anchor_ndc
    }
    /* 外景以主体建筑为构图重点，适当留出导航空间。
     * 保持原始镜头投影，让屋檐、月门和山崖在宽屏中具有可辨认的尺寸。 */
    if (cameraIndex !== 3 && (width > 760 || width / height > 1.3)) {
      matrix[0] *= .98; matrix[5] *= .98
      if (camera instanceof THREE.PerspectiveCamera) matrix[9] -= .08
      else matrix[13] += .08
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
    /* 全部观景机位共享完整远景范围，旋转时不会突然露出云海的裁剪边界。
     * 对数深度继续承担近柱与远山之间的大尺度深度精度。 */
    selected.far = Math.max(data.far, 60000)
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
      /* 烘焙云团、连续云床和远山完整就绪后，再开始首次场景编译。
       * 异步返回时复查生命周期，避免退出页面后把迟到的效果挂回场景。 */
      atmosphere = await createAtmosphere(layout, resourceRoot, abort.signal)
      if (disposed || failed) { atmosphere.dispose(); atmosphere = undefined; return }
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
      /* 阴影只收录近岛实体，远山和动态瀑布不进入静态阴影缓存。
       * 根据世界边界识别实例批次，避免把远景山群计入投影范围。 */
      const shadowBounds = new THREE.Box3(), shadowCenter = new THREE.Vector3(), shadowSize = new THREE.Vector3()
      const anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy())
      for (const root of roots) {
        /* 原低模远山距离更近，会挡住新云冠并在月门中露出明显尖锥。
         * 新山群覆盖所有方位后统一替换，四机位和环游共享相同真实场景。 */
        if (atmosphere.replacesLegacyMountains) retireLegacyMountains(root)
        root.updateMatrixWorld(true)
        root.traverse(object => {
          object.updateMatrix(); object.matrixAutoUpdate = false
          if (object instanceof THREE.InstancedMesh) { object.computeBoundingBox(); object.computeBoundingSphere() }
          if (!(object instanceof THREE.Mesh)) return
          shadowBounds.setFromObject(object)
          shadowBounds.getCenter(shadowCenter); shadowBounds.getSize(shadowSize)
          const sourceMaterials = Array.isArray(object.material) ? object.material : [object.material]
          const isWater = sourceMaterials.some(material => material.name === 'WEB_Waterfall_Static_Preview')
          object.castShadow = !isWater && Math.abs(shadowCenter.x) < 650 && Math.abs(shadowCenter.z) < 850 && Math.max(...shadowSize.toArray()) < 1400
          object.receiveShadow = !isWater
          const reuse = (material: THREE.Material) => {
            const water = material.name === 'WEB_Waterfall_Static_Preview'
            const shared = water ? atmosphere!.water : material.name ? materials.get(material.name) : undefined
            if (shared && shared !== material) {
              replaced.add(material)
              for (const value of Object.values(material)) if (value instanceof THREE.Texture) unusedTextures.add(value)
              return shared
            }
            /* 斜视瓦面与铺地使用各向异性采样，远处的细密纹理保持连续。
             * 共享材质只保留一份纹理，提升清晰度不会重复加载图片。 */
            for (const value of Object.values(material)) {
              if (value instanceof THREE.Texture) value.anisotropy = anisotropy
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
      /* 共享材质确定后再接入地面反射，避免重复替换贴图和着色器。
       * 初次编译已经包含反射分支，切入殿内时无需重新生成地面材质。 */
      floorReflection.attach(modelRoot)
      renderer.shadowMap.needsUpdate = true
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
      /* 先更新阴影覆盖与镜像目标，再统一绘制正常机位，保证柱影和倒影同步。
       * 镜像只在殿内启用；移动相机即时刷新，流云静止时复用已有反射。 */
      try {
        lighting.update(camera)
        floorReflection.update(camera, elapsed, Boolean(changed) || dirty)
        renderer.render(scene, camera)
      }
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
    /* 质量切换统一调整阴影与镜像分辨率，各模块负责回收旧显存。
     * 相机和材质外观保持一致，仅改变采样精度与反射刷新频率。 */
    setQuality(value) {
      quality = value
      lighting.setQuality(value)
      floorReflection.setQuality(value)
      resize()
    },
    dispose() {
      disposed = true; abort.abort(); clearTimeout(loadDeadline); cancelAnimationFrame(raf)
      observer.disconnect(); controls?.dispose()
      document.removeEventListener('visibilitychange', visibilityChanged)
      renderer.domElement.removeEventListener('webglcontextlost', contextLost)
      renderer.domElement.removeEventListener('keydown', keyboard)
      /* 环境预过滤、阴影与平面反射目标均由效果模块持有，需要显式释放。
       * 重试或退出场景后不保留上一次创建的离屏纹理。 */
      disposeModels([modelRoot]); atmosphere?.dispose(); floorReflection.dispose(); lighting.dispose()
      scene.environment = null; scene.clear(); renderer.renderLists.dispose()
      renderer.dispose(); renderer.forceContextLoss(); renderer.domElement.remove()
    },
  }
}
