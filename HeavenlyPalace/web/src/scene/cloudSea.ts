/* 云海使用 Blender 烘焙的体积云图集、固定米制布局和真实远山网格。
 * 天空、低位连续云床与起伏云团共同提供纵深，不随观景机位替换背景。 */
import * as THREE from 'three'
/* 云团亮边、山体受光和天空光晕与建筑日光采用同一方向。
 * 烘焙云图集通过既有朝向翻转适配光源，远景不会与柱列阴影左右相反。 */
import { PALACE_SUN } from './lightingProfile.ts'

export interface CloudRecord {
  kind: string
  position: [number, number, number]
  dimensions: [number, number, number]
  variant?: number
  opacity?: number
}

interface RidgeRecord {
  name: string
  layer: number
  /* 同一几何格式兼容远山、近岩与古松，材质按明确的资产类别选择。
   * 未提供类别的旧布局仍作为山岩加载，允许资源与代码逐步更新。 */
  kind?: 'rock' | 'bark' | 'needles'
  positions: [number, number, number][]
  normals: [number, number, number][]
  indices: number[]
}

interface CloudSeaLayout {
  revision: string
  atlas: string
  tileSize: number
  clouds: CloudRecord[]
  ridges: RidgeRecord[]
  /* 右侧岩壁古松与远山使用同一世界坐标，不随镜头切换显隐或改变位置。
   * 只有完整新山群声明接管时才停用原地形中的远山占位对象。 */
  landmarks?: RidgeRecord[]
  replacesLegacyMountains?: boolean
  /* 中轴机位对应新的入口薄云位置，替换旧偏置云团以免叠加成过厚雾墙。
   * 近岛云雾和瀑布水雾继续从原有环境布局读取。 */
  replacesEntranceMist?: boolean
  bedHeight: number
  radius: number
}

/* 根据旧资源的专用材质识别远山，避开主岛岩体、桥台和原有植被。
 * 合并网格必须全部使用旧远山材质才停用，防止误隐藏混合用途的网格。 */
export function retireLegacyMountains(root: THREE.Object3D) {
  let retired = 0
  root.traverse(object => {
    if (!(object instanceof THREE.Mesh)) return
    const slots = Array.isArray(object.material) ? object.material : [object.material]
    if (slots.length > 0 && slots.every(material => /^WEB_V08_远山_空气透视_\d/.test(material.name))) {
      object.visible = false
      retired++
    }
  })
  return retired
}

/* 天空与云床共用连续噪声，纹理锚定世界坐标，旋转和缩放不会使纹理滑动。
 * 四个频率形成大范围云浪与细小起伏，计算量不随云团数量增加。 */
const noiseShader = `
  float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
  float noise2(vec2 p) {
    vec2 i = floor(p), f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash(i), hash(i + vec2(1, 0)), f.x),
               mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), f.x), f.y);
  }
  float fbm(vec2 p) {
    float value = 0.0, amplitude = 0.55;
    for (int i = 0; i < 4; i++) {
      value += noise2(p) * amplitude;
      p = mat2(1.6, -1.2, 1.2, 1.6) * p + 8.7;
      amplitude *= 0.48;
    }
    return value;
  }
`

/* 图集通过加载器等待解码完成，任何资源失败都交由上层加载界面处理。
 * 即使用户在下载时离开，也释放迟到的纹理，避免重试积累显存。 */
export async function createCloudSea(resourceRoot: string, existing: CloudRecord[], signal: AbortSignal) {
  const root = resourceRoot + 'cloud-sea/'
  const response = await fetch(root + 'layout.json', { signal })
  if (!response.ok) throw new Error('Cloud sea layout unavailable')
  const layout: CloudSeaLayout = await response.json()
  signal.throwIfAborted()
  const atlas = await new THREE.TextureLoader().loadAsync(root + layout.atlas)
  if (signal.aborted) { atlas.dispose(); signal.throwIfAborted() }
  atlas.colorSpace = THREE.SRGBColorSpace
  atlas.generateMipmaps = false
  atlas.minFilter = THREE.LinearFilter
  atlas.magFilter = THREE.LinearFilter

  const group = new THREE.Group()
  group.name = '殿外云海与远山'
  const geometries: THREE.BufferGeometry[] = [], materials: THREE.Material[] = []
  /* 统一太阳方向由殿内实际遮挡射线检查确定，保持全场光线连续。
   * 时间只影响云的漂移，不改变昼夜或随相机转动太阳。 */
  const time = { value: 0 }, sun = new THREE.Vector3(...PALACE_SUN).normalize()
  /* 远处空气透视保留青蓝色，云峰以暖白迎光，避免外景整体混成相同灰度。
   * 近景岩松使用较低雾量，使它在门缘提供可读的尺度和深度参照。 */
  const hazeColor = new THREE.Color('#c6d6df')

  /* 天空只在背景绘制，水平线附近偏暖灰蓝，高处逐渐转为清晰的蓝色。
   * 远裁剪面由投影深度单独处理，四个机位都能看到完整天空。 */
  const skyGeometry = new THREE.SphereGeometry(45000, 32, 20)
  const skyMaterial = new THREE.ShaderMaterial({
    side: THREE.BackSide, depthWrite: false, depthTest: false,
    uniforms: { sunDirection: { value: sun } },
    vertexShader: `
      varying vec3 skyDirection;
      void main() {
        skyDirection = normalize(position);
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        gl_Position.z = gl_Position.w * 0.999999;
      }
    `,
    fragmentShader: `
      /* 薄高云保留蓝天间隙，太阳方向只产生宽柔光晕，不增加遮挡建筑的光片。
       * 颜色在线性空间合成，最终跟随场景统一色调映射。 */
      varying vec3 skyDirection;
      uniform vec3 sunDirection;
      ${noiseShader}
      void main() {
        vec3 ray = normalize(skyDirection);
        float elevation = max(ray.y, 0.0);
        /* 门洞上方保留通透蓝天，低处浅蓝雾带连接暖白云冠。
         * 高空云丝降低对比，视觉主体留给真实空间中的云浪与峰群。 */
        vec3 color = mix(vec3(0.50, 0.65, 0.77), vec3(0.065, 0.19, 0.36), pow(clamp(elevation * 2.1, 0.0, 1.0), 0.48));
        float glow = pow(max(dot(ray, sunDirection), 0.0), 9.0);
        color += vec3(0.27, 0.16, 0.055) * glow;
        vec2 skyUv = ray.xz / max(ray.y + 0.28, 0.15);
        float wisps = smoothstep(0.59, 0.79, fbm(skyUv * vec2(5.0, 24.0)));
        wisps *= smoothstep(0.07, 0.19, ray.y) * (1.0 - smoothstep(0.42, 0.7, ray.y));
        color = mix(color, vec3(0.88, 0.88, 0.83), wisps * 0.22);
        gl_FragColor = vec4(color, 1.0);
        #include <tonemapping_fragment>
        #include <colorspace_fragment>
      }
    `,
  })
  const sky = new THREE.Mesh(skyGeometry, skyMaterial)
  sky.name = '蓝天与高空薄云'; sky.frustumCulled = false; sky.renderOrder = -1000
  geometries.push(skyGeometry); materials.push(skyMaterial); group.add(sky)

  /* 低位云床填满云团之间的缝隙，固定在主岛下方，提供连续的俯瞰云面。
   * 云床写入深度，远山山根在真实交界处入云，岛顶建筑仍正常遮挡它。 */
  const bedGeometry = new THREE.PlaneGeometry(layout.radius * 2, layout.radius * 2)
  bedGeometry.rotateX(-Math.PI / 2)
  const bedMaterial = new THREE.ShaderMaterial({
    side: THREE.DoubleSide,
    uniforms: { elapsed: time, bedRadius: { value: layout.radius }, hazeColor: { value: hazeColor } },
    vertexShader: `
      varying vec3 cloudWorld;
      #include <common>
      #include <logdepthbuf_pars_vertex>
      void main() {
        cloudWorld = (modelMatrix * vec4(position, 1.0)).xyz;
        vec4 mvPosition = viewMatrix * vec4(cloudWorld, 1.0);
        gl_Position = projectionMatrix * mvPosition;
        #include <logdepthbuf_vertex>
      }
    `,
    fragmentShader: `
      /* 云浪采用暖白峰顶和冷灰谷部，远处逐渐减小对比以融入地平线。
       * 运动只改变很小的采样偏移，暂停动态时保持当前云海位置。 */
      varying vec3 cloudWorld;
      uniform float elapsed;
      uniform float bedRadius;
      uniform vec3 hazeColor;
      ${noiseShader}
      #include <common>
      #include <logdepthbuf_pars_fragment>
      void main() {
        if (length(cloudWorld.xz) > bedRadius) discard;
        vec2 p = cloudWorld.xz * 0.0028 + vec2(elapsed * 0.0015, 0.0);
        float height = fbm(p);
        float slope = fbm(p + vec2(-0.12, 0.16)) - height;
        vec3 color = mix(vec3(0.32, 0.43, 0.54), vec3(1.05, 1.02, 0.91), smoothstep(0.21, 0.72, height));
        color += slope * 0.8;
        float distanceToEye = length(cloudWorld - cameraPosition);
        color = mix(color, hazeColor, smoothstep(3500.0, 26000.0, distanceToEye) * 0.90);
        #include <logdepthbuf_fragment>
        gl_FragColor = vec4(color, 1.0);
        #include <tonemapping_fragment>
        #include <colorspace_fragment>
      }
    `,
  })
  const bed = new THREE.Mesh(bedGeometry, bedMaterial)
  bed.name = '宫殿下方连续云床'; bed.position.y = layout.bedHeight
  geometries.push(bedGeometry); materials.push(bedMaterial); group.add(bed)

  /* 远山以几何轮廓和表面法线表现沟壑，颜色按距离逐层变浅。
   * 山脚在低云中柔和消失，避免截平底座或悬浮锥体破坏云海尺度。 */
  for (const ridge of [...layout.ridges, ...(layout.landmarks ?? [])]) {
    const geometry = new THREE.BufferGeometry()
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(ridge.positions.flat(), 3))
    geometry.setAttribute('normal', new THREE.Float32BufferAttribute(ridge.normals.flat(), 3))
    geometry.setIndex(ridge.indices)
    geometry.computeBoundingSphere()
    const material = new THREE.ShaderMaterial({
      /* 几何共享岩壁受光与空气透视，枝干和针叶增加独立色彩与细节尺度。
       * 使用材质类别常量，不依赖物体名称推测新资产的表现。 */
      uniforms: { sunDirection: { value: sun }, hazeColor: { value: hazeColor }, layer: { value: ridge.layer },
        surfaceKind: { value: ridge.kind === 'needles' ? 2 : ridge.kind === 'bark' ? 1 : 0 } },
      vertexShader: `
        varying vec3 ridgeWorld;
        varying vec3 ridgeNormal;
        #include <common>
        #include <logdepthbuf_pars_vertex>
        void main() {
          ridgeWorld = (modelMatrix * vec4(position, 1.0)).xyz;
          ridgeNormal = normalize(mat3(modelMatrix) * normal);
          vec4 mvPosition = viewMatrix * vec4(ridgeWorld, 1.0);
          gl_Position = projectionMatrix * mvPosition;
          #include <logdepthbuf_vertex>
        }
      `,
      fragmentShader: `
        varying vec3 ridgeWorld;
        varying vec3 ridgeNormal;
        uniform vec3 sunDirection;
        uniform vec3 hazeColor;
        uniform float layer;
        /* 近岩的竖向裂隙、松皮条纹和针叶斑驳均锚定世界坐标。
         * 细节只改变表面明暗，真实轮廓和门洞遮挡由 Blender 网格提供。 */
        uniform float surfaceKind;
        ${noiseShader}
        #include <common>
        #include <logdepthbuf_pars_fragment>
        void main() {
          vec3 normalDirection = normalize(ridgeNormal);
          float light = max(dot(normalDirection, sunDirection), 0.0);
          float nearField = 1.0 - step(0.0, layer);
          float detail = fbm(ridgeWorld.xz * 0.027 + ridgeWorld.y * 0.003);
          float clefts = fbm(vec2(ridgeWorld.x + ridgeWorld.z * 0.63, ridgeWorld.y * 0.13) * 0.07);
          vec3 stone = mix(vec3(0.10, 0.155, 0.19), vec3(0.43, 0.40, 0.30), light);
          stone *= 0.64 + clefts * 0.72;
          float moss = smoothstep(0.50, 0.68, detail) * smoothstep(-0.10, 0.6, normalDirection.y);
          stone = mix(stone, vec3(0.09, 0.15, 0.055) * (0.50 + light), moss * nearField * 0.75);
          vec3 color = stone;
          if (surfaceKind > 0.5 && surfaceKind < 1.5) {
            color = mix(vec3(0.055, 0.043, 0.031), vec3(0.28, 0.20, 0.105), light) * (0.65 + clefts * 0.7);
          } else if (surfaceKind > 1.5) {
            float needles = fbm(ridgeWorld.xz * 0.43 + ridgeWorld.y * 0.11);
            color = mix(vec3(0.028, 0.055, 0.035), vec3(0.23, 0.285, 0.075), light);
            color *= 0.64 + needles * 0.80;
          }
          float distanceToEye = length(ridgeWorld - cameraPosition);
          float haze = clamp(0.06 + distanceToEye / 38000.0 + max(layer, 0.0) * 0.075, 0.0, 0.86);
          haze *= mix(1.0, 0.48, nearField);
          color = mix(color, hazeColor, haze);
          float foot = 1.0 - smoothstep(-420.0, 260.0 + max(layer, 0.0) * 130.0, ridgeWorld.y);
          color = mix(color, hazeColor, foot * mix(0.88, 0.38, nearField));
          #include <logdepthbuf_fragment>
          gl_FragColor = vec4(color, 1.0);
          #include <tonemapping_fragment>
          #include <colorspace_fragment>
        }
      `,
    })
    const mountain = new THREE.Mesh(geometry, material)
    mountain.name = ridge.name
    geometries.push(geometry); materials.push(material); group.add(mountain)
  }

  /* 保留岛边与瀑布雾气，新云浪与居中的入口薄云接管相应旧布局。
   * 每个实例记录形状和透明度，按视线排序后同步更新，防止纹理在云团间跳换。 */
  const entries = [
    ...existing.filter(item => item.kind !== 'distant_cloud_sea'
      && !(layout.replacesEntranceMist && item.kind === 'entrance_roof_occluder')).map((item, index) => ({
      ...item, variant: index % 4,
      opacity: item.kind === 'waterfall_mist' ? 0.42 : 0.96,
    })),
    ...layout.clouds,
  ].map(item => ({ ...item, depth: 0 }))
  const geometry = new THREE.PlaneGeometry(1, 1)
  const traits = new THREE.InstancedBufferAttribute(new Float32Array(entries.length * 2), 2)
  geometry.setAttribute('cloudTraits', traits)
  const material = new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, side: THREE.DoubleSide,
    uniforms: { cloudAtlas: { value: atlas }, elapsed: time, hazeColor: { value: hazeColor }, sunDirection: { value: sun }, tileSize: { value: layout.tileSize } },
    vertexShader: `
      /* 云片按椭球在视线中的投影展开，并按俯视角度选择相应烘焙图层。
       * 世界位置参与深度测试，云层不会覆盖站在殿内的柱子和人物。 */
      attribute vec2 cloudTraits;
      uniform float elapsed;
      uniform vec3 sunDirection;
      varying vec2 cloudUv;
      varying vec2 traits;
      varying float overhead;
      varying float distanceToEye;
      #include <common>
      #include <logdepthbuf_pars_vertex>
      void main() {
        traits = cloudTraits;
        vec3 center = instanceMatrix[3].xyz;
        vec3 extent = vec3(instanceMatrix[0].x, instanceMatrix[1].y, instanceMatrix[2].z);
        center.x += sin(elapsed * 0.025 + center.z * 0.001) * min(extent.x * 0.009, 9.0);
        vec3 right = vec3(viewMatrix[0][0], viewMatrix[1][0], viewMatrix[2][0]);
        vec3 up = vec3(viewMatrix[0][1], viewMatrix[1][1], viewMatrix[2][1]);
        vec2 size = vec2(length(right * extent), length(up * extent));
        cloudUv = vec2(dot(right, sunDirection) > 0.0 ? 1.0 - uv.x : uv.x, uv.y);
        vec3 toEye = cameraPosition - center;
        distanceToEye = length(toEye);
        overhead = smoothstep(0.20, 0.72, max(toEye.y, 0.0) / max(distanceToEye, 1.0));
        vec4 mvPosition = viewMatrix * vec4(center, 1.0);
        mvPosition.xy += position.xy * size * 1.35;
        gl_Position = projectionMatrix * mvPosition;
        #include <logdepthbuf_vertex>
      }
    `,
    fragmentShader: `
      /* 采样限制在每格图集内部，避免线性插值串入相邻云形。
       * 两个视角先按透明度加权混合颜色，再做普通透明合成，保留柔软亮沿。 */
      uniform sampler2D cloudAtlas;
      uniform float tileSize;
      uniform vec3 hazeColor;
      varying vec2 cloudUv;
      varying vec2 traits;
      varying float overhead;
      varying float distanceToEye;
      #include <common>
      #include <logdepthbuf_pars_fragment>
      void main() {
        vec2 local = clamp(cloudUv, vec2(0.5 / tileSize), vec2(1.0 - 0.5 / tileSize));
        vec4 low = texture2D(cloudAtlas, (local + vec2(traits.x, 0.0)) / vec2(4.0, 2.0));
        vec4 high = texture2D(cloudAtlas, (local + vec2(traits.x, 1.0)) / vec2(4.0, 2.0));
        float alpha = mix(low.a, high.a, overhead);
        if (alpha * traits.y < 0.012) discard;
        vec3 color = mix(low.rgb * low.a, high.rgb * high.a, overhead) / max(alpha, 0.001);
        /* 暖光云冠与冷灰沟谷保持烘焙明暗关系，远云逐渐降低对比但不漂白。
         * 六排不同角尺寸的云浪因此仍可分辨前后遮挡与中间的暗部沟谷。 */
        float brightness = dot(color, vec3(0.2126, 0.7152, 0.0722));
        color *= mix(vec3(0.80, 0.90, 1.06), vec3(1.08, 1.035, 0.96), smoothstep(0.20, 0.76, brightness));
        color = mix(color, hazeColor, smoothstep(3200.0, 27000.0, distanceToEye) * 0.54);
        #include <logdepthbuf_fragment>
        gl_FragColor = vec4(color, alpha * traits.y);
        #include <tonemapping_fragment>
        #include <colorspace_fragment>
      }
    `,
  })
  const clouds = new THREE.InstancedMesh(geometry, material, entries.length)
  clouds.name = '分层体积云图集实例'; clouds.frustumCulled = false
  clouds.instanceMatrix.setUsage(THREE.DynamicDrawUsage)
  traits.setUsage(THREE.DynamicDrawUsage)
  geometries.push(geometry); materials.push(material); group.add(clouds)
  const matrix = new THREE.Matrix4()
  let lastSort = -1

  /* 背景天空跟随观察点以消除球壳边界，实体云海与远山始终固定在世界中。
   * 关闭动画后仍允许相机操作触发透明排序，减少动态效果不会冻结场景更新。 */
  function update(elapsed: number, camera: THREE.Camera, force = false) {
    time.value = elapsed
    sky.position.copy(camera.position)
    if (!force && lastSort >= 0 && elapsed - lastSort < 0.12) return
    lastSort = elapsed
    const view = camera.matrixWorldInverse.elements
    for (const entry of entries) entry.depth = view[2] * entry.position[0] + view[6] * entry.position[1] + view[10] * entry.position[2]
    entries.sort((a, b) => a.depth - b.depth)
    entries.forEach((entry, index) => {
      matrix.makeScale(...entry.dimensions); matrix.setPosition(...entry.position)
      clouds.setMatrixAt(index, matrix)
      traits.setXY(index, entry.variant ?? 0, entry.opacity ?? 0.96)
    })
    clouds.instanceMatrix.needsUpdate = true; traits.needsUpdate = true
  }

  return {
    /* 将接管标记传到模型加载入口，确保旧山群只在新环境成功加载后退出绘制。
     * 保留原 GLB 数据，退出与重载仍沿用模型原有资源释放逻辑。 */
    group, update, replacesLegacyMountains: layout.replacesLegacyMountains === true,
    /* 图集和所有效果网格均属于本模块，退出时统一释放且只释放一次。
     * 建筑材质不引用这些资源，因此更新云海不会改变建筑资产的生命周期。 */
    dispose() {
      clouds.dispose(); atlas.dispose()
      for (const item of [...geometries, ...materials]) item.dispose()
      group.clear()
    },
  }
}
