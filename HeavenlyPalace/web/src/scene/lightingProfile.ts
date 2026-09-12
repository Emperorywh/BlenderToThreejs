/* 建筑、天空和远山共用一个世界空间太阳方向，避免亮边与实际投影相反。
 * 坐标为网页的右手米制坐标；低角度日光从殿内画面左前方进入柱廊。 */
export const PALACE_SUN = [650, 430, 650] as const

/* 地坪来自 Blender 实体压顶板的顶面，反射只作用于该材质的向上表面。
 * 保留材质的完整名称，避免把台阶、室外广场和立面误判为抛光地坪。 */
export const HALL_FLOOR_HEIGHT = 36
export const HALL_FLOOR_MATERIAL = 'WEB_V09_白玉地坪_四米大板与柔和反射'
