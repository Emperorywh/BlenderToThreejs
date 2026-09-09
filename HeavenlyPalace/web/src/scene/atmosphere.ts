/* 云海沿用场景导出的空间布局，通过共享纹理和实例绘制形成柔和云层。
 * 水流保留原有瀑布几何，只为表面增加沿世界竖直方向下落的细流与泡沫。 */
import * as THREE from 'three'

interface CloudRecord {
  kind: string
  position: [number, number, number]
  dimensions: [number, number, number]
}
export interface EnvironmentLayout { effects: CloudRecord[] }

/* 使用确定性的云团笔触生成本地纹理，不依赖远程图片或额外下载。
 * 上部暖白、下部青灰的层次让云海在浅色天空中仍能呈现体积感。 */
function cloudTexture() {
  const canvas = document.createElement('canvas')
  canvas.width = 256; canvas.height = 256
  const context = canvas.getContext('2d')!
  let seed = 97
  const random = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647 }
  for (let i = 0; i < 48; i++) {
    const angle = random() * Math.PI * 2, radius = Math.sqrt(random()) * 68
    const x = 128 + Math.cos(angle) * radius, y = 128 + Math.sin(angle) * radius * .68
    const size = 30 + random() * 45
    const gradient = context.createRadialGradient(x, y, size * .12, x, y, size)
    gradient.addColorStop(0, 'rgba(255,255,255,.36)')
    gradient.addColorStop(.5, 'rgba(255,255,255,.2)')
    gradient.addColorStop(1, 'rgba(255,255,255,0)')
    context.fillStyle = gradient
    context.fillRect(x - size, y - size, size * 2, size * 2)
  }
  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.NoColorSpace
  return texture
}

export function createAtmosphere(layout: EnvironmentLayout) {
  const texture = cloudTexture()
  const time = { value: 0 }
  const material = new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, side: THREE.DoubleSide,
    uniforms: { cloudMap: { value: texture }, elapsed: time },
    vertexShader: `
      /* 按相机方向计算椭球的投影大小，俯视时仍能看到完整云面。
       * 每个实例保持原始锚点，风动仅在局部轻微往复。 */
      attribute float density;
      uniform float elapsed;
      varying vec2 cloudUv;
      varying float cloudDensity;
      #include <common>
      #include <logdepthbuf_pars_vertex>
      void main() {
        cloudUv = uv;
        cloudDensity = density;
        vec3 center = instanceMatrix[3].xyz;
        vec3 extent = vec3(instanceMatrix[0].x, instanceMatrix[1].y, instanceMatrix[2].z);
        float phase = center.x * .003 + center.z * .002;
        center.x += sin(elapsed * .035 + phase) * min(extent.x * .018, 12.0);
        vec3 right = vec3(viewMatrix[0][0], viewMatrix[1][0], viewMatrix[2][0]);
        vec3 up = vec3(viewMatrix[0][1], viewMatrix[1][1], viewMatrix[2][1]);
        vec2 size = vec2(length(right * extent), length(up * extent));
        vec4 mvPosition = viewMatrix * vec4(center, 1.0);
        mvPosition.xy += position.xy * size * 1.55;
        gl_Position = projectionMatrix * mvPosition;
        #include <logdepthbuf_vertex>
      }
    `,
    fragmentShader: `
      /* 透明边缘与深度测试保留建筑遮挡关系，避免云层浮在建筑表面。
       * 云团下侧略带青灰，亮部与天空自然衔接。 */
      uniform sampler2D cloudMap;
      varying vec2 cloudUv;
      varying float cloudDensity;
      #include <common>
      #include <logdepthbuf_pars_fragment>
      void main() {
        float alpha = texture2D(cloudMap, cloudUv).a * cloudDensity;
        if (alpha < .008) discard;
        #include <logdepthbuf_fragment>
        vec3 color = mix(vec3(.53, .64, .64), vec3(.93, .94, .88), smoothstep(.12, .85, cloudUv.y));
        gl_FragColor = vec4(color, alpha);
        #include <tonemapping_fragment>
        #include <colorspace_fragment>
      }
    `,
  })
  const geometry = new THREE.PlaneGeometry(1, 1)
  const density = new THREE.InstancedBufferAttribute(new Float32Array(layout.effects.length), 1)
  geometry.setAttribute('density', density)
  const clouds = new THREE.InstancedMesh(geometry, material, layout.effects.length)
  clouds.frustumCulled = false
  const matrix = new THREE.Matrix4()
  const entries = layout.effects.map(effect => ({ ...effect, depth: 0 }))
  let lastSort = -1

  /* 实例按视线深度排序，自动环游和手动旋转时透明云层仍正确叠加。
   * 排序按低频更新，动画时间使用前台帧差，切回页面时不会突然跳动。 */
  function update(elapsed: number, camera: THREE.Camera, force = false) {
    time.value = elapsed
    if (!force && elapsed - lastSort < .12 && lastSort >= 0) return
    lastSort = elapsed
    const view = camera.matrixWorldInverse.elements
    for (const item of entries) item.depth = view[2] * item.position[0] + view[6] * item.position[1] + view[10] * item.position[2]
    entries.sort((a, b) => a.depth - b.depth)
    entries.forEach((item, index) => {
      matrix.makeScale(...item.dimensions)
      matrix.setPosition(...item.position)
      clouds.setMatrixAt(index, matrix)
      density.setX(index, item.kind === 'waterfall_mist' ? .45 : item.kind === 'entrance_roof_occluder' ? 1 : .88)
    })
    clouds.instanceMatrix.needsUpdate = true
    density.needsUpdate = true
  }

  const water = new THREE.MeshStandardMaterial({ color: '#b5d8d2', roughness: .27, metalness: .08, side: THREE.DoubleSide })
  water.onBeforeCompile = shader => {
    shader.uniforms.flowTime = time
    shader.vertexShader = shader.vertexShader.replace('#include <common>', '#include <common>\nvarying vec3 flowPosition;')
      .replace('#include <project_vertex>', `
        #include <project_vertex>
        vec4 flowWorld = vec4(transformed, 1.0);
        #ifdef USE_INSTANCING
          flowWorld = instanceMatrix * flowWorld;
        #endif
        flowPosition = (modelMatrix * flowWorld).xyz;
      `)
    shader.fragmentShader = shader.fragmentShader.replace('#include <common>', '#include <common>\nuniform float flowTime;\nvarying vec3 flowPosition;')
      .replace('#include <color_fragment>', `
        #include <color_fragment>
        float fall = flowPosition.y * .16 + flowTime * 3.8;
        float strands = sin(flowPosition.x * 3.7 + flowPosition.z * 2.9 + sin(fall) * .35);
        float foam = smoothstep(.2, 1.0, strands * sin(fall + flowPosition.x * .8));
        float ripple = sin(fall * 2.3 + flowPosition.z * 1.7) * .07;
        diffuseColor.rgb = mix(diffuseColor.rgb * (.76 + ripple), vec3(.94, .98, .95), foam * .8);
      `)
  }
  water.customProgramCacheKey = () => 'palace-flow-v1'

  return {
    clouds, water, update,
    dispose() { clouds.dispose(); geometry.dispose(); material.dispose(); texture.dispose(); water.dispose() },
  }
}
