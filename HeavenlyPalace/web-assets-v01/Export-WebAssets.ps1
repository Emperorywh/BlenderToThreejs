<#
按固定次序重建网页资源，原始 V9 始终只读；所有日志保存在独立交付目录。
默认导出未压缩资源供首次浏览器验收，显式选择压缩阶段后生成最终 Meshopt 版本。
#>
param(
    [string]$Blender = 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe',
    [ValidateSet('All','Export','Compress','Verify')][string]$Stage = 'All',
    [switch]$Rebake
)
$ErrorActionPreference = 'Stop'
$sourcePath = Join-Path (Split-Path $PSScriptRoot -Parent) 'stage1\HeavenlyPalace_Detail_v09.blend'
$copyPath = Join-Path $PSScriptRoot 'HeavenlyPalace_WebAssets_v01.blend'
# 仅在执行导出时建立中间记录目录，该目录已从版本控制排除。
# 清理工作区后仍可按需重建导出与核验所需数据。
$qaPath = Join-Path $PSScriptRoot 'qa'
New-Item -ItemType Directory -Path $qaPath -Force | Out-Null
function Invoke-BlenderStep([string]$InputBlend,[string]$ScriptName) {
    $scriptPath = Join-Path $PSScriptRoot ('scripts\' + $ScriptName + '.py')
    $logPath = Join-Path $PSScriptRoot ($ScriptName + '.log')
    # 程序材质发生变化时通过显式开关更新贴图缓存。
    # 其他阶段仍使用同一份已验证资源，避免无意重新烘焙。
    $extraArgs = @()
    if ($Rebake -and $ScriptName -eq 'adapt_scene') { $extraArgs = @('--','--rebake') }
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
if ($Stage -in @('All','Export')) {
    Invoke-BlenderStep $copyPath 'export_glb'
    Invoke-BlenderStep $copyPath 'finalize_blend'
}
if ($Stage -in @('All','Verify')) {
    if (-not (Test-Path -LiteralPath (Join-Path $qaPath 'source-audit.json'))) { Invoke-BlenderStep $sourcePath 'audit_scene' }
    Invoke-BlenderStep $copyPath 'verify_scene'
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
