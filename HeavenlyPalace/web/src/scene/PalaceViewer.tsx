/* 固定机位通过导出的完整投影矩阵还原，画面始终保持四比三和 DPR 一。
 * 模型、相机及环境均为同一米制原点，加载后不再居中或旋转模型。 */
import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js'
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js'

/* 为相机文件、加载状态和页面控制提供明确类型，沿用项目的严格类型检查。
 * 页面保留运行所需状态，不包含截图采样、测试记录或诊断开关。 */
interface CameraRecord {
  name: string
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
interface CameraFile { cameras: CameraRecord[] }
interface ManifestFile {
  files: { file: string; bytes: number }[]
  textures: { file: string; bytes: number }[]
  compression: string
}
interface Metrics {
  fps: number
  calls: number
  triangles: number
  instances: number
  instanceGroups: number
  textures: number
  firstRenderedMilliseconds: number
}
interface ViewerAPI {
  selectCamera: (index: number, orbit?: boolean) => void
}

const resourceRoot = import.meta.env.BASE_URL + 'palace-assets/'
const labels = ['整体斜视', '正面结构', '鸟瞰布局', '殿内望云']
const number = (n?: number) => Math.round(n || 0).toLocaleString('zh-CN')
async function readResource<T>(file: string): Promise<T> {
  const response = await fetch(resourceRoot + file)
  if (!response.ok) throw new Error(file + ' 无法读取')
  return response.json()
}

export default function Viewer() {
  const host = useRef<HTMLDivElement>(null)
  const api = useRef<ViewerAPI | null>(null)
  const [active, setActive] = useState(0)
  const [free, setFree] = useState(false)
  const [stats, setStats] = useState(true)
  const [loading, setLoading] = useState('正在读取资源清单')
  const [error, setError] = useState('')
  const [metrics, setMetrics] = useState<Partial<Metrics>>({})

  useEffect(() => {
    if (!host.current) return
    let controls: OrbitControls | undefined, camera: THREE.PerspectiveCamera | THREE.OrthographicCamera | undefined
    let cameraData: CameraFile | undefined
    let cancelled = false, raf = 0, freeMode = false
    const modelRoot = new THREE.Group()
    let counter = 0, lastUi = performance.now()
    let instances = 0, instanceGroups = 0, firstRenderedMilliseconds = 0
    // 使用对数深度保持原相机裁剪面，减轻大尺度屋面与金线的深度冲突。
    // 资源始终采用完整 PBR 材质与环境光照。
    const started = performance.now(), renderer = new THREE.WebGLRenderer({ antialias: true, logarithmicDepthBuffer: true, powerPreference: 'high-performance' })
    renderer.setPixelRatio(1)
    renderer.setSize(1280, 960, false)
    renderer.outputColorSpace = THREE.SRGBColorSpace
    renderer.toneMapping = THREE.ACESFilmicToneMapping
    renderer.toneMappingExposure = .8
    host.current.appendChild(renderer.domElement)
    const scene = new THREE.Scene()
    scene.background = new THREE.Color('#c7d4dc')
    const pmrem = new THREE.PMREMGenerator(renderer)
    const room = new RoomEnvironment()
    const environment = pmrem.fromScene(room, .04)
    scene.environment = environment.texture
    scene.environmentIntensity = .25
    room.dispose(); pmrem.dispose()
    scene.add(new THREE.HemisphereLight(0xe0edff, 0x847360, .55))
    const sunlight = new THREE.DirectionalLight(0xffefd5, 1.8)
    sunlight.position.set(-300, 600, 400); scene.add(sunlight)
    scene.add(modelRoot)
    const manager = new THREE.LoadingManager()
    manager.onError = url => { if (!cancelled) setError(`资源加载失败：${url}`) }
    const loader = new GLTFLoader(manager).setMeshoptDecoder(MeshoptDecoder)

    /* 相机局部前方为负 Z，世界变换已经完成坐标转换。
     * 每次预设切换均恢复完整投影；自由观察使用同样初始光心再开放轨道交互。 */
    function selectCamera(index: number, orbit = false) {
      if (!cameraData) return
      controls?.dispose()
      freeMode = orbit
      const data = cameraData.cameras[index]
      const selectedCamera = data.projection_type === 'ORTHO' ? new THREE.OrthographicCamera(-(data.orthographic_width ?? 1) / 2, (data.orthographic_width ?? 1) / 2, (data.orthographic_height ?? 1) / 2, -(data.orthographic_height ?? 1) / 2, data.near, data.far) : new THREE.PerspectiveCamera(data.vertical_fov_degrees ?? 50, 4 / 3, data.near, data.far)
      new THREE.Matrix4().fromArray(data.world_matrix).decompose(selectedCamera.position, selectedCamera.quaternion, selectedCamera.scale)
      // 固定机位直接使用 Blender 的完整投影，保留光心与镜头偏移。
      // 自由观察切换后由控制器更新，重新选机位即可恢复构图。
      const originalUpdate = selectedCamera.updateProjectionMatrix.bind(selectedCamera)
      selectedCamera.updateProjectionMatrix = () => {
        if (freeMode) { originalUpdate(); return }
        selectedCamera.projectionMatrix.fromArray(data.projection_matrix)
        selectedCamera.projectionMatrixInverse.copy(selectedCamera.projectionMatrix).invert()
      }
      selectedCamera.updateProjectionMatrix()
      selectedCamera.updateMatrixWorld(true)
      if (orbit) {
        controls = new OrbitControls(selectedCamera, renderer.domElement)
        const distance = index === 3 ? 110 : 1500
        controls.target.copy(selectedCamera.position).add(new THREE.Vector3(...data.direction).multiplyScalar(distance))
        controls.enableDamping = true; controls.dampingFactor = .08; controls.minDistance = .2; controls.maxDistance = 15000
      }
      camera = selectedCamera
      counter = 0; lastUi = performance.now()
      setActive(index); setFree(orbit)
    }
    const unique = { geometries: new Set<THREE.BufferGeometry>(), materials: new Set<THREE.Material>(), textures: new Set<THREE.Texture>() }
    function disposeRoot(root: THREE.Object3D) {
      root.traverse(ob => {
        if (!(ob instanceof THREE.Mesh)) return
        if (ob.geometry) unique.geometries.add(ob.geometry)
        for (const mat of (Array.isArray(ob.material) ? ob.material : [ob.material]).filter(Boolean)) {
          unique.materials.add(mat)
          for (const value of Object.values(mat)) if (value instanceof THREE.Texture) unique.textures.add(value)
        }
        if (ob instanceof THREE.InstancedMesh) ob.dispose()
      })
      for (const item of [...unique.geometries, ...unique.materials, ...unique.textures]) item.dispose()
    }

    /* 跨 GLB 用相同材质名称复用材质与纹理，避免同一套贴图重复占用显存。
     * 所有文件仍可被标准 GLTFLoader 单独加载，浏览器缓存会复用相同纹理 URL。 */
    async function load() {
      try {
        const [manifest, cameras] = await Promise.all([readResource<ManifestFile>('manifest.json'), readResource<CameraFile>('cameras.json')])
        if (cancelled) return
        cameraData = cameras
        selectCamera(0)
        const materials = new Map<string, THREE.Material>(), unusedTextures = new Set<THREE.Texture>()
        const results = await Promise.allSettled(manifest.files.map(async file => {
          const gltf = await loader.loadAsync(resourceRoot + file.file)
          return gltf.scene
        }))
        const rejected = results.find(result => result.status === 'rejected')
        if (rejected) {
          for (const result of results) if (result.status === 'fulfilled') disposeRoot(result.value)
          throw rejected.reason
        }
        for (const result of results) {
          if (result.status !== 'fulfilled') continue
          const root = result.value
          if (cancelled) { disposeRoot(root); continue }
          root.traverse(ob => {
            // 静态资源加载完后固定局部矩阵，减少每帧重复计算。
            // 后续需要移动的对象可重新启用 matrixAutoUpdate。
            ob.updateMatrix(); ob.matrixAutoUpdate = false
            if (ob instanceof THREE.InstancedMesh) { instanceGroups++; instances += ob.count; ob.computeBoundingBox(); ob.computeBoundingSphere() }
            if (!(ob instanceof THREE.Mesh)) return
            const reuse = (mat: THREE.Material) => {
              const shared = materials.get(mat.name)
              if (shared) {
                for (const value of Object.values(mat)) if (value instanceof THREE.Texture) unusedTextures.add(value)
                mat.dispose(); return shared
              }
              materials.set(mat.name, mat); return mat
            }
            ob.material = Array.isArray(ob.material) ? ob.material.map(reuse) : reuse(ob.material)
          })
          modelRoot.add(root)
        }
        if (cancelled) return
        const retained = new Set<THREE.Texture>()
        for (const mat of materials.values()) for (const value of Object.values(mat)) if (value instanceof THREE.Texture) retained.add(value)
        for (const texture of unusedTextures) if (!retained.has(texture)) texture.dispose()
        setLoading('全部资源已加载')
      } catch (failure) { if (!cancelled) setError(String(failure)) }
    }

    function frame(now: number) {
      raf = requestAnimationFrame(frame)
      if (!camera) return
      controls?.update()
      /* 固定预设重设导出矩阵，避免轨道控制器和正交缩放重写投影。
       * 自由观察时由控制器更新，但重新切换机位即可回到精确构图。 */
      if (!freeMode) camera.updateProjectionMatrix()
      renderer.render(scene, camera)
      if (!firstRenderedMilliseconds && modelRoot.children.length === 5) firstRenderedMilliseconds = performance.now() - started
      counter++
      if (now - lastUi > 1000) {
        setMetrics({ fps: counter * 1000 / (now - lastUi), calls: renderer.info.render.calls, triangles: renderer.info.render.triangles, textures: renderer.info.memory.textures, instances, instanceGroups, firstRenderedMilliseconds })
        counter = 0; lastUi = now
      }
    }
    api.current = { selectCamera }
    load(); raf = requestAnimationFrame(frame)
    return () => {
      cancelled = true; cancelAnimationFrame(raf); controls?.dispose(); scene.remove(modelRoot); disposeRoot(modelRoot)
      environment.dispose(); scene.environment = null; renderer.renderLists.dispose()
      renderer.dispose(); renderer.forceContextLoss(); renderer.domElement.remove(); api.current = null
    }
  }, [])

  return <main>
    <div className="stage" ref={host} aria-label="天宫三维验证画面" />
    <header><div className="brand"><span className="seal">天</span><div><h1>天宫<span>资源验证</span></h1><p>HEAVENLY PALACE / WEB ASSETS 01</p></div></div><div className="status"><i className={error ? 'bad' : ''}/>{error ? '加载异常' : loading}</div></header>
    <aside className="view-label"><span>0{active + 1} / 04</span><h2>{labels[active]}</h2><p>{free ? '自由观察 · 拖动旋转 / 滚轮缩放 / 右键平移' : active === 3 ? '52 mm · 水平偏移 −0.12 · 精确投影' : '固定 4:3 · 米制坐标'}</p></aside>
    {stats && <aside className="stats"><div><strong>{(metrics.fps || 0).toFixed(1)}</strong><span>FPS</span></div><dl><dt>Draw calls</dt><dd>{number(metrics.calls)}</dd><dt>绘制三角面</dt><dd>{number(metrics.triangles)}</dd><dt>GPU 实例</dt><dd>{number(metrics.instances)}</dd><dt>实例组 / 纹理</dt><dd>{number(metrics.instanceGroups)} / {number(metrics.textures)}</dd><dt>首帧加载</dt><dd>{((metrics.firstRenderedMilliseconds || 0)/1000).toFixed(2)} s</dd><dt>渲染画幅</dt><dd>1280 × 960 · 1×</dd></dl><p>基础场景目标 ≥ 30 FPS</p></aside>}
    {error && <div className="error" role="alert">{error}</div>}
    <footer><nav aria-label="相机选择">{labels.map((label,index) => <button key={label} className={active === index && !free ? 'selected' : ''} onClick={() => api.current?.selectCamera(index)}><span>0{index+1}</span>{label}</button>)}</nav><div className="toolbar"><button aria-pressed={free} onClick={() => api.current?.selectCamera(active,!free)}>自由观察</button><button aria-pressed={stats} onClick={() => setStats(!stats)}>性能统计</button></div><div className="footnote"><span><b>待重建</b> 远景云海 · 近岛云雾 · 入口五团遮檐云 · 瀑布动画</span><span role="status">基础 PBR 灯光 · 性能不代表完整特效场景</span></div></footer>
  </main>
}
