/* 将柱列、藻井与天空的实时平面反射融入现有石材物理材质。
 * 地坪仍使用原网格、砖缝和法线，反射按粗糙度柔化并按掠射角增强。 */
import * as THREE from 'three'
import { Reflector } from 'three/addons/objects/Reflector.js'
import { HALL_FLOOR_HEIGHT, HALL_FLOOR_MATERIAL } from './lightingProfile.ts'

/* 在光照合成前替换地坪的间接镜面项，保持日光、阴影和原来的石纹采样。
 * 反射使用线性颜色，最终只经过主场景的一次色调映射与显示空间转换。 */
export function createHallFloorReflection(renderer: THREE.WebGLRenderer, scene: THREE.Scene) {
  const reflector = new Reflector(new THREE.PlaneGeometry(1, 1), { textureWidth: 768, textureHeight: 512, multisample: 0 })
  const reflectionRoot = new THREE.Group()
  reflectionRoot.add(reflector)
  /* 反射辅助对象内部固定使用着色器材质，公开类型仍继承通用网格的联合类型。
   * 在入口明确类型，后续只读取辅助对象实际持有的投影矩阵统一变量。 */
  const reflectorMaterial = reflector.material as THREE.ShaderMaterial
  reflector.rotation.x = -Math.PI / 2
  reflector.position.y = HALL_FLOOR_HEIGHT
  reflector.updateMatrixWorld(true)
  const target = reflector.getRenderTarget()
  target.texture.name = '主殿石坪线性反射'
  const inverseFloor = reflector.matrixWorld.clone().invert()
  const uniforms = {
    hallReflection: { value: target.texture },
    hallReflectionMatrix: { value: new THREE.Matrix4() },
    hallReflectionTexel: { value: new THREE.Vector2(1 / 768, 1 / 512) },
    hallReflectionReady: { value: 0 },
  }
  const floors: THREE.Mesh[] = [], patched = new Set<THREE.MeshStandardMaterial>()
  const clipPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), -HALL_FLOOR_HEIGHT - .025)
  let lastUpdate = -Infinity, invalidated = true, highQuality = false

  return {
    attach(root: THREE.Object3D) {
      root.traverse(object => {
        if (!(object instanceof THREE.Mesh)) return
        const materials = Array.isArray(object.material) ? object.material : [object.material]
        for (const material of materials) {
          if (!(material instanceof THREE.MeshStandardMaterial) || material.name !== HALL_FLOOR_MATERIAL) continue
          if (!floors.includes(object)) floors.push(object)
          if (patched.has(material)) continue
          patched.add(material)
          /* 室内抛光石板共用了室外铺地贴图，单独调节材质系数以保留贴图细节。
           * 非金属石材保持零金属度，较低粗糙度只用于形成柔和的柱列倒影。 */
          material.roughness = .67
          material.metalness = 0
          material.onBeforeCompile = shader => {
            Object.assign(shader.uniforms, uniforms)
            shader.vertexShader = shader.vertexShader.replace('#include <common>', `
              #include <common>
              varying vec3 hallWorldPosition;
            `).replace('#include <project_vertex>', `
              #include <project_vertex>
              /* 先应用实例和模型变换，使原网格与未来的实例地坪使用相同世界坐标。
               * 投影反射与砖块纹理坐标独立，不会因砖缝平铺而重复倒影。 */
              vec4 hallWorld = vec4(transformed, 1.0);
              #ifdef USE_INSTANCING
                hallWorld = instanceMatrix * hallWorld;
              #endif
              hallWorldPosition = (modelMatrix * hallWorld).xyz;
            `)
            shader.fragmentShader = shader.fragmentShader.replace('#include <common>', `
              #include <common>
              varying vec3 hallWorldPosition;
              uniform sampler2D hallReflection;
              uniform mat4 hallReflectionMatrix;
              uniform vec2 hallReflectionTexel;
              uniform float hallReflectionReady;
            `).replace('#include <aomap_fragment>', `
              #include <aomap_fragment>
              /* 顶面高度与法线同时限制反射，台基侧面仍按普通石材着色。
               * 投影边缘平滑回退到天空环境，避免镜像纹理在画幅外拉成长条。 */
              vec4 reflectedCoord = hallReflectionMatrix * vec4(hallWorldPosition, 1.0);
              vec2 reflectedUv = reflectedCoord.xy / max(reflectedCoord.w, 0.0001);
              vec3 hallWorldNormal = transformDirectionByInverseViewMatrix(normal, viewMatrix);
              float floorMask = (1.0 - smoothstep(0.03, 0.10, abs(hallWorldPosition.y - ${HALL_FLOOR_HEIGHT.toFixed(1)})));
              floorMask *= smoothstep(0.90, 0.99, hallWorldNormal.y) * hallReflectionReady;
              float border = min(min(reflectedUv.x, reflectedUv.y), min(1.0 - reflectedUv.x, 1.0 - reflectedUv.y));
              floorMask *= smoothstep(0.0, 0.025, border) * step(0.0, reflectedCoord.w);
              if (floorMask > 0.0) {
                /* 九点采样让远处柱影柔化，微法线只产生轻微扰动而不制造水面波纹。
                 * 菲涅耳项同时衰减底色和环境镜面，避免把反射直接加亮成发白的地面。 */
                vec2 center = clamp(reflectedUv + hallWorldNormal.xz * 0.008, vec2(0.005), vec2(0.995));
                vec2 spread = hallReflectionTexel * (0.75 + roughnessFactor * roughnessFactor * 18.0);
                vec3 reflection = texture2D(hallReflection, center).rgb * 0.25;
                reflection += texture2D(hallReflection, center + vec2(spread.x, 0.0)).rgb * 0.125;
                reflection += texture2D(hallReflection, center - vec2(spread.x, 0.0)).rgb * 0.125;
                reflection += texture2D(hallReflection, center + vec2(0.0, spread.y)).rgb * 0.125;
                reflection += texture2D(hallReflection, center - vec2(0.0, spread.y)).rgb * 0.125;
                reflection += texture2D(hallReflection, center + spread).rgb * 0.0625;
                reflection += texture2D(hallReflection, center - spread).rgb * 0.0625;
                reflection += texture2D(hallReflection, center + vec2(spread.x, -spread.y)).rgb * 0.0625;
                reflection += texture2D(hallReflection, center + vec2(-spread.x, spread.y)).rgb * 0.0625;
                float grazing = pow(1.0 - max(dot(normal, normalize(vViewPosition)), 0.0), 5.0);
                float fresnel = (0.04 + 0.96 * grazing) * (1.0 - roughnessFactor * 0.65);
                reflectedLight.directDiffuse *= 1.0 - fresnel * floorMask;
                reflectedLight.indirectDiffuse *= 1.0 - fresnel * floorMask;
                reflectedLight.indirectSpecular = mix(reflectedLight.indirectSpecular, reflection * fresnel, floorMask);
              }
            `)
          }
          material.customProgramCacheKey = () => 'palace-hall-stone-reflection-v1'
          material.needsUpdate = true
        }
      })
    },
    /* 镜像相机只在殿内近景绘制，静止时以较低频率更新流云倒影。
     * 镜头变化立即刷新；暂停动态后仍能拖动观察，外景不承担额外一遍全场绘制。 */
    update(camera: THREE.Camera, elapsed: number, changed: boolean) {
      const p = camera.position
      const active = floors.length > 0 && p.y > HALL_FLOOR_HEIGHT + .08 && p.y < 105 && Math.abs(p.x) < 145 && p.z > -415 && p.z < -205
      if (!active) { uniforms.hallReflectionReady.value = 0; invalidated = true; return }
      if (!changed && !invalidated && elapsed - lastUpdate < (highQuality ? 1 / 15 : 1 / 10)) return
      const visibility = floors.map(floor => floor.visible), previousClip = renderer.clippingPlanes
      const previousTarget = renderer.getRenderTarget(), previousXr = renderer.xr.enabled
      const previousShadowUpdate = renderer.shadowMap.autoUpdate
      uniforms.hallReflectionReady.value = 0
      try {
        for (const floor of floors) floor.visible = false
        /* 对数深度会重写深度值，因此额外启用世界裁剪平面隔离台基下方的实体。
         * 反射辅助面不加入场景，不产生重复地面、深度闪烁或递归镜像。 */
        renderer.clippingPlanes = [...previousClip, clipPlane]
        reflector.onBeforeRender(renderer, scene, camera, reflector.geometry, reflectorMaterial, reflectionRoot)
        uniforms.hallReflectionMatrix.value.copy(reflectorMaterial.uniforms.textureMatrix.value).multiply(inverseFloor)
        uniforms.hallReflectionReady.value = 1
        lastUpdate = elapsed; invalidated = false
      } finally {
        floors.forEach((floor, index) => { floor.visible = visibility[index] })
        renderer.clippingPlanes = previousClip
        renderer.xr.enabled = previousXr; renderer.shadowMap.autoUpdate = previousShadowUpdate
        renderer.setRenderTarget(previousTarget)
      }
    },
    /* 质量切换复用目标对象并重新分配其存储，所有材质继续引用同一张反射纹理。
     * 高画质增加采样分辨率与动态刷新频率，不改变石材颜色或反射强度。 */
    setQuality(quality: 'balanced' | 'high') {
      highQuality = quality === 'high'
      const width = highQuality ? 1152 : 768, height = highQuality ? 768 : 512
      target.setSize(width, height)
      uniforms.hallReflectionTexel.value.set(1 / width, 1 / height)
      invalidated = true
    },
    dispose() { reflector.geometry.dispose(); reflector.dispose(); floors.length = 0; patched.clear() },
  }
}
