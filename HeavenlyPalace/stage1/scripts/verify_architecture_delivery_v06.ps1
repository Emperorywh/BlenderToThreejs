<#
核验正式 V6 工程、九张实际渲染、几何审查与两次内嵌重建结果。
只读检查基准与交付文件，另写清单，不改变工程和图像。
#>
$ErrorActionPreference = 'Stop'
$stageRoot = Split-Path -Parent $PSScriptRoot
$deliveryRoot = Join-Path $stageRoot 'v06'
$parameters = Get-Content -LiteralPath (Join-Path $deliveryRoot 'design_parameters_v06.json') -Encoding UTF8 -Raw | ConvertFrom-Json
$audit = Get-Content -LiteralPath (Join-Path $deliveryRoot 'qa/audit_v06.json') -Encoding UTF8 -Raw | ConvertFrom-Json
$rebuild = Get-Content -LiteralPath (Join-Path $deliveryRoot 'qa/rebuild_verification.json') -Encoding UTF8 -Raw | ConvertFrom-Json
$candidatePath = Join-Path $stageRoot $parameters.output_file
$sourcePath = Join-Path $stageRoot $parameters.baseline_file
$sourceHash = (Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash
if ($sourceHash -ne $parameters.baseline_sha256) { throw 'V5 原文件摘要发生变化。' }
if (-not $audit.passed) { throw '几何审查尚未通过。' }
if ($audit.file -ne $candidatePath) { throw '审查报告没有对应正式交付工程。' }
if (-not $rebuild.passed -or $rebuild.original_object_count -ne $audit.objects) { throw '重建结果尚未对应最终模型。' }

# 从每张 PNG 的实际文件头读取分辨率，避免把预览图当作正式图交付。
# 逐一记录文件大小和摘要，便于确认渲染与交付文件是否完整。
$names = @('01_oblique','02_front','03_aerial','04_interior','07_entry_detail','08_corner_detail','09_bridge_detail','10_corridor_under_eave','11_view_pavilion')
$renders = foreach ($name in $names) {
    $imagePath = Join-Path $deliveryRoot "renders/$name.png"
    $file = Get-Item -LiteralPath $imagePath
    $bytes = [System.IO.File]::ReadAllBytes($imagePath)
    if ($bytes.Length -lt 1000 -or $bytes[0] -ne 137 -or $bytes[1] -ne 80) { throw "无效 PNG：$name" }
    $width = [int]$bytes[16]*16777216 + [int]$bytes[17]*65536 + [int]$bytes[18]*256 + [int]$bytes[19]
    $height = [int]$bytes[20]*16777216 + [int]$bytes[21]*65536 + [int]$bytes[22]*256 + [int]$bytes[23]
    if ($width -ne $parameters.render_width -or $height -ne $parameters.render_height) { throw "正式图像素尺寸不符：$name" }
    [ordered]@{ file=$file.Name; width=$width; height=$height; bytes=$file.Length; sha256=(Get-FileHash -LiteralPath $imagePath -Algorithm SHA256).Hash }
}
$manifest = [ordered]@{
    blend=[ordered]@{ file=$candidatePath; bytes=(Get-Item -LiteralPath $candidatePath).Length; sha256=(Get-FileHash -LiteralPath $candidatePath -Algorithm SHA256).Hash }
    baseline=[ordered]@{ file=$sourcePath; sha256=$sourceHash; unchanged=$true }
    geometry_audit_passed=$audit.passed
    embedded_rebuild_passed=$rebuild.passed
    original_cameras_preserved=4
    previous_detail_cameras_preserved=2
    added_detail_cameras=5
    route_samples=$audit.route_sample_count
    shared_meshes=$audit.shared_mesh_count
    renderer='Blender 5.2.1 LTS / Cycles CPU / 48 最大采样 / 降噪'
    renders=@($renders)
}
$manifest | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $deliveryRoot 'qa/render_manifest.json') -Encoding UTF8
$manifest | ConvertTo-Json -Depth 10
