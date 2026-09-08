<#
核验 V05 交付工程、六张正式渲染及 V4 源文件摘要。
只读取工程和图片，生成可供复核的交付清单，不改动模型或渲染内容。
#>
$ErrorActionPreference = 'Stop'
$stageRoot = Split-Path -Parent $PSScriptRoot
$deliveryRoot = Join-Path $stageRoot 'v05'
$parameters = Get-Content -LiteralPath (Join-Path $deliveryRoot 'design_parameters_v05.json') -Encoding UTF8 -Raw | ConvertFrom-Json
$audit = Get-Content -LiteralPath (Join-Path $deliveryRoot 'qa/audit_v05.json') -Encoding UTF8 -Raw | ConvertFrom-Json
$sourcePath = Join-Path $stageRoot $parameters.baseline_file
$candidatePath = Join-Path $stageRoot 'HeavenlyPalace_Structure_v05.blend'
$sourceHash = (Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash
if ($sourceHash -ne $parameters.baseline_sha256) { throw 'V4 原文件摘要变化。' }
if (-not $audit.passed) { throw '模型审查尚未通过。' }
if ($audit.file -ne $candidatePath) { throw '审查报告对应的不是正式交付工程。' }

# PNG 文件头记录实际像素尺寸，不能仅凭场景渲染设置判断输出成功。
# 六个名称逐个核对，防止漏图、低分辨率预览混入正式交付。
$names = @('01_oblique','02_front','03_aerial','04_interior','05_roof_detail','06_moon_detail')
$renders = foreach ($name in $names) {
    $imagePath = Join-Path $deliveryRoot "renders/$name.png"
    $imageFile = Get-Item -LiteralPath $imagePath
    $pngBytes = [System.IO.File]::ReadAllBytes($imagePath)
    if ($pngBytes.Length -lt 1000 -or $pngBytes[0] -ne 137 -or $pngBytes[1] -ne 80) { throw "图片无效：$name" }
    $width = [int]$pngBytes[16]*16777216 + [int]$pngBytes[17]*65536 + [int]$pngBytes[18]*256 + [int]$pngBytes[19]
    $height = [int]$pngBytes[20]*16777216 + [int]$pngBytes[21]*65536 + [int]$pngBytes[22]*256 + [int]$pngBytes[23]
    if ($width -ne $parameters.render_width -or $height -ne $parameters.render_height) { throw "图片尺寸不符：$name" }
    [ordered]@{ file=$imageFile.Name; width=$width; height=$height; bytes=$imageFile.Length; sha256=(Get-FileHash -LiteralPath $imagePath -Algorithm SHA256).Hash }
}
$manifest = [ordered]@{
    blend=[ordered]@{ file=$candidatePath; bytes=(Get-Item -LiteralPath $candidatePath).Length; sha256=(Get-FileHash -LiteralPath $candidatePath -Algorithm SHA256).Hash }
    baseline=[ordered]@{ file=$sourcePath; sha256=$sourceHash; unchanged=$true }
    geometry_audit_passed=$audit.passed
    original_camera_count=4
    added_camera_count=2
    renderer='Blender 5.2.1 / Cycles CPU / 48 最大采样 / 降噪'
    renders=@($renders)
}
$manifest | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $deliveryRoot 'qa/render_manifest.json') -Encoding UTF8
$manifest | ConvertTo-Json -Depth 10
