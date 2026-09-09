<#
核验正式 V7 文件、九张实际渲染与几何和重建报告的一致性。
只读访问 V6 基准及最终工程，逐一记录文件摘要，防止交付混入旧预览。
#>
$ErrorActionPreference = 'Stop'
$stageRoot = Split-Path -Parent $PSScriptRoot
$deliveryRoot = Join-Path $stageRoot 'v07'
$parameters = Get-Content -LiteralPath (Join-Path $deliveryRoot 'design_parameters_v07.json') -Raw | ConvertFrom-Json
$audit = Get-Content -LiteralPath (Join-Path $deliveryRoot 'qa/audit_v07.json') -Raw | ConvertFrom-Json
$rebuild = Get-Content -LiteralPath (Join-Path $deliveryRoot 'qa/rebuild_verification.json') -Raw | ConvertFrom-Json
$candidatePath = Join-Path $stageRoot $parameters.output_file
$baselinePath = Join-Path $stageRoot $parameters.baseline_file
$baselineHash = (Get-FileHash -LiteralPath $baselinePath -Algorithm SHA256).Hash
if ($baselineHash -ne $parameters.baseline_sha256) { throw 'V6 基准摘要发生变化。' }
if (-not $audit.passed -or $audit.file -ne $candidatePath) { throw '几何审查没有通过或不对应正式 V7。' }
if (-not $rebuild.passed -or $rebuild.original_objects -ne $audit.objects) { throw '内嵌重建核验没有对应最终工程。' }

# 从 PNG 文件头核对正式像素尺寸，不使用扩展名或文件名代替实际验证。
# 图像和工程摘要一起写入交付清单，方便后续验收与版本留档。
$names = @('01_oblique','02_front','03_aerial','04_interior','12_main_cliff','13_hero_pine','14_bridge_environment','15_waterfall_detail','16_bridge_clearance')
$renders = foreach ($name in $names) {
    $imagePath = Join-Path $deliveryRoot "renders/$name.png"
    $bytes = [System.IO.File]::ReadAllBytes($imagePath)
    if ($bytes.Length -lt 1000 -or $bytes[0] -ne 137 -or $bytes[1] -ne 80) { throw "无效 PNG：$name" }
    $width = [int]$bytes[16]*16777216 + [int]$bytes[17]*65536 + [int]$bytes[18]*256 + [int]$bytes[19]
    $height = [int]$bytes[20]*16777216 + [int]$bytes[21]*65536 + [int]$bytes[22]*256 + [int]$bytes[23]
    if ($width -ne $parameters.render_width -or $height -ne $parameters.render_height) { throw "正式分辨率不符：$name" }
    [ordered]@{ file=$imagePath; width=$width; height=$height; bytes=$bytes.Length; sha256=(Get-FileHash -LiteralPath $imagePath -Algorithm SHA256).Hash }
}
$manifest = [ordered]@{
    blend=[ordered]@{ file=$candidatePath; bytes=(Get-Item -LiteralPath $candidatePath).Length; sha256=(Get-FileHash -LiteralPath $candidatePath -Algorithm SHA256).Hash }
    baseline=[ordered]@{ file=$baselinePath; sha256=$baselineHash; unchanged=$true }
    geometry_audit_passed=$audit.passed
    embedded_rebuild_passed=$rebuild.passed
    preserved_objects=$audit.protected_objects
    original_fixed_cameras=4
    preserved_total_cameras=$audit.preserved_cameras
    added_environment_cameras=5
    renderer='Blender 5.2.1 LTS / Cycles CPU / 48 最大采样 / 降噪'
    renders=@($renders)
}
$manifest | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $deliveryRoot 'qa/render_manifest.json') -Encoding UTF8
$manifest | ConvertTo-Json -Depth 10
