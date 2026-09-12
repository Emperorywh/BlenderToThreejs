<#
按固定次序重建网页资源，原始 V9 始终只读；所有日志保存在独立交付目录。
默认导出未压缩资源供首次浏览器验收，显式选择压缩阶段后生成最终 Meshopt 版本。
#>
param(
    [string]$Blender = '',
    # 构图阶段只更新殿内机位和人物站位，可独立于建筑重建运行。
    # 其余阶段继续沿用既有名称，已有导出命令保持可用。
    # 藻井阶段独立替换殿内天花构件，直接沿用当前主殿工程。
    # 不触发屋面、柱网、构图与人物的重新生成。
    # 空间阶段调整主殿比例并同步机位和人物，可在当前网页副本上独立重复执行。
    # 主殿重建阶段也同步构图，确保导出的建筑和人物来自同一版空间。
    [ValidateSet('All','Quality','Hall','Space','Ceiling','View','Export','Compress','Verify')][string]$Stage = 'All',
    [switch]$Rebake
)
$ErrorActionPreference = 'Stop'
# 优先查找当前电脑的 Blender，仍可通过参数指定其他版本。
# 不依赖原作者的安装盘符，确保本地重建入口可以直接使用。
if (-not $Blender) {
    $blenderCommand = Get-Command blender -ErrorAction SilentlyContinue
    $candidates = @('D:\app\blender\blender.exe', 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe')
    if ($blenderCommand) { $Blender = $blenderCommand.Source }
    else { $Blender = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1 }
    if (-not $Blender) { throw '没有找到 Blender，请使用 -Blender 指定 blender.exe 路径。' }
}
$sourcePath = Join-Path (Split-Path $PSScriptRoot -Parent) 'stage1\HeavenlyPalace_Detail_v09.blend'
$copyPath = Join-Path $PSScriptRoot 'HeavenlyPalace_WebAssets_v01.blend'
# 仅在执行导出时建立中间记录目录，该目录已从版本控制排除。
# 清理工作区后仍可按需重建导出与核验所需数据。
$qaPath = Join-Path $PSScriptRoot 'qa'
New-Item -ItemType Directory -Path $qaPath -Force | Out-Null
# 可选脚本参数用于同一构图脚本的只读核验，避免另建一套不一致的检查入口。
# 参数直接作为进程参数传递，不拼接可执行命令字符串。
function Invoke-BlenderStep([string]$InputBlend,[string]$ScriptName,[string[]]$ScriptArguments = @()) {
    $scriptPath = Join-Path $PSScriptRoot ('scripts\' + $ScriptName + '.py')
    $logPath = Join-Path $PSScriptRoot ($ScriptName + '.log')
    # 程序材质发生变化时通过显式开关更新贴图缓存。
    # 其他阶段仍使用同一份已验证资源，避免无意重新烘焙。
    $extraArgs = $ScriptArguments
    if ($Rebake -and $ScriptName -eq 'adapt_scene') { $extraArgs = @('--','--rebake') }
    # 藻井专用阶段只更新建筑文件，其他资源沿用已核对的摘要。
    # 主殿和空间阶段在后面显式顺序导出建筑及人物，不能覆盖调用方传入的资源类别。
    if ($Stage -eq 'Ceiling' -and $ScriptName -eq 'export_glb') { $extraArgs = @('--','--only','architecture') }
    # 构图修改包含第一位人物的平移，因此只重导人物资源即可。
    # 建筑、地形、植被与瀑布按现有摘要继承，不触发几何重建。
    if ($Stage -eq 'View' -and $ScriptName -eq 'export_glb') { $extraArgs = @('--','--only','characters') }
    & $Blender --background $InputBlend --python-exit-code 1 --python $scriptPath @extraArgs *> $logPath
    if ($LASTEXITCODE -ne 0) { throw "步骤失败：$ScriptName，请查看 $logPath" }
    Write-Host "完成：$ScriptName"
}
if ($Stage -eq 'All') {
    Invoke-BlenderStep $sourcePath 'audit_scene'
    Invoke-BlenderStep $sourcePath 'adapt_scene'
    Invoke-BlenderStep $copyPath 'fix_material_slots'
    Invoke-BlenderStep $copyPath 'refine_geometry'
}
# 质量升级放在基础适配后、区域合并前；再次执行会识别版本并跳过。
# 单独升级已有网页副本时选择 Quality，完成后继续压缩和核验。
if ($Stage -in @('All','Quality')) {
    Invoke-BlenderStep $copyPath 'upgrade_quality'
    Invoke-BlenderStep $copyPath 'review_quality'
}
# 主殿样板具有独立的可重复重建入口，修改参数后可直接运行 Hall。
# 完整重建也执行相同步骤，避免下一次从原件导出时丢失本轮主殿精修。
if ($Stage -in @('All','Quality','Hall')) {
    Invoke-BlenderStep $copyPath 'refine_main_hall'
    Invoke-BlenderStep $copyPath 'review_main_hall'
}
# 独立空间阶段保留现有材质与装饰，只应用可重复的层高、柱网和月门调整。
# 同时执行建筑实体核验，未通过检查时不进入正式资源导出。
if ($Stage -eq 'Space') {
    Invoke-BlenderStep $copyPath 'refine_hall_space'
    Invoke-BlenderStep $copyPath 'review_main_hall'
}
# 藻井局部更新使用独立脚本，避免覆盖用户已经调整的其他主殿构件。
# 完成后仍核验主殿净空、有效网格和网页材质，再进入建筑资源导出。
if ($Stage -eq 'Ceiling') {
    Invoke-BlenderStep $copyPath 'refine_hall_ceiling'
    Invoke-BlenderStep $copyPath 'review_main_hall'
}
# 完整重建与构图更新使用同一参数源，确保下次从原始工程生成时不会退回旧机位。
# 主殿与空间调整会影响月门取景，因此这两个阶段同步相机及人物的绝对站位。
if ($Stage -in @('All','Quality','Hall','Space','View')) {
    Invoke-BlenderStep $copyPath 'compose_hall_view'
}
if ($Stage -in @('All','Quality','Hall','Space','Ceiling','View','Export')) {
    # 建筑和人物按顺序写入，共用最新清单继承其余资源，避免并行写文件互相覆盖。
    # 第二次导出只更新人物；相机 JSON 已由构图阶段完整保存。
    if ($Stage -in @('Hall','Space')) {
        Invoke-BlenderStep $copyPath 'export_glb' @('--','--only','architecture')
        Invoke-BlenderStep $copyPath 'export_glb' @('--','--only','characters')
    } else {
        Invoke-BlenderStep $copyPath 'export_glb'
    }
    Invoke-BlenderStep $copyPath 'finalize_blend'
}
if ($Stage -in @('All','Verify')) {
    if (-not (Test-Path -LiteralPath (Join-Path $qaPath 'source-audit.json'))) { Invoke-BlenderStep $sourcePath 'audit_scene' }
    Invoke-BlenderStep $copyPath 'verify_scene'
    # 最终工程再次检查实际开孔与贴图引用，覆盖导出合并后的对象状态。
    # 该阶段只核验数据，不自动打开浏览器或生成网页截图。
    Invoke-BlenderStep $copyPath 'review_quality'
    # 最终工程同时核验主殿柱网、门洞和斗拱净空。
    # 检查不生成渲染，也不自动操作浏览器。
    Invoke-BlenderStep $copyPath 'review_main_hall'
    # 空间核验检查实际层高、柱网和月门净口，覆盖最终保存及区域合并后的状态。
    # 此入口只输出数据报告，不修改工程或进行界面截图测试。
    Invoke-BlenderStep $copyPath 'refine_hall_space' @('--','--verify')
    # 藻井核验补充内部安装缝、共享网格与物理贴图检查。
    # 从最终保存文件读回验证，避免只在重建过程的内存场景中通过检查。
    Invoke-BlenderStep $copyPath 'refine_hall_ceiling' @('--','--verify')
    # 读回已保存的工程，核对构图比例、门洞视线和网页完整相机矩阵。
    # 只核验资源数据，不调用预览渲染或启动浏览器。
    Invoke-BlenderStep $copyPath 'compose_hall_view' @('--','--verify')
}
if ($Stage -in @('Compress','Verify')) {
    Push-Location (Join-Path $PSScriptRoot 'tooling')
    try {
        if (-not (Test-Path -LiteralPath 'node_modules')) { npm.cmd ci; if ($LASTEXITCODE -ne 0) { throw '工具依赖安装失败' } }
        if ($Stage -eq 'Compress') { node compress.mjs; if ($LASTEXITCODE -ne 0) { throw '压缩失败' } }
        node validate.mjs
        if ($LASTEXITCODE -ne 0) { throw 'GLB 验证失败' }
        # 保留基础导出后，逐三角形和逐实例核验压缩结果。
        # 检查位置、法线、纹理坐标与实例变换，不把导出成功视作验证通过。
        if (Test-Path -LiteralPath '../qa/baseline-glb/architecture.glb') {
            node verify-compression.mjs
            if ($LASTEXITCODE -ne 0) { throw '压缩前后数据不一致' }
        }
    } finally { Pop-Location }
}
Write-Host '资源处理完成。请在 web 目录运行 pnpm dev 查看场景。'
