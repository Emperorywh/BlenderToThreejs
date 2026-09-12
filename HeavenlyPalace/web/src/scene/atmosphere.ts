/* 云海使用独立的 Blender 体积烘焙和固定空间布局，瀑布继续使用原有实体几何。
 * 本模块统一效果的时间与释放入口，页面控制方式保持一致。 */
import * as THREE from 'three'
import { createCloudSea } from './cloudSea'
import type { CloudRecord } from './cloudSea'

export interface EnvironmentLayout { effects: CloudRecord[] }

/* 等待云图集与布局完整就绪后再交给主场景，避免背景在模型之后突然出现。
 * 下载期间退出时沿用场景取消信号，已生成的资源交由云海模块回收。 */
export async function createAtmosphere(layout: EnvironmentLayout, resourceRoot: string, signal: AbortSignal) {
  const cloudSea = await createCloudSea(resourceRoot, layout.effects, signal)
  const time = { value: 0 }

  /* 水流沿世界竖直方向下落，与云海的烘焙材质和远山几何独立。
   * 保留原有细流、泡沫与时间采样，避免环境更新改变瀑布表现。 */
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
    /* 门外环境完整加载后才传递替换状态，加载失败时仍由场景入口统一报错。
     * 模型可见性由模型加载阶段设置，不在逐帧动画中反复遍历或切换。 */
    clouds: cloudSea.group, water, replacesLegacyMountains: cloudSea.replacesLegacyMountains,
    /* 云海和水流共享前台时间，动态开关同时控制两种效果。
     * 机位操作仍传递强制更新标记，以维持正确的透明排序。 */
    update(elapsed: number, camera: THREE.Camera, force = false) {
      time.value = elapsed; cloudSea.update(elapsed, camera, force)
    },
    dispose() { cloudSea.dispose(); water.dispose() },
  }
}
