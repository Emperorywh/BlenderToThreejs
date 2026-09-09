<#
将实际 Blender 渲染图排成对比版面，并汇总最终三个固定机位检查图。
只进行等比例排版，不修补图像内容，不使用参考图替换任何渲染区域。
#>
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$stageRoot = Split-Path $PSScriptRoot -Parent
$deliveryRoot = Join-Path $stageRoot 'v08_1'
$rendersRoot = Join-Path $deliveryRoot 'renders'
foreach ($view in @('01_oblique', '02_front', '03_aerial')) {
    Copy-Item -LiteralPath (Join-Path $deliveryRoot "qa/preview_$view.png") -Destination (Join-Path $rendersRoot "$($view)_check.png") -Force
}
$canvas = [System.Drawing.Bitmap]::new(1840, 760)
$graphics = [System.Drawing.Graphics]::FromImage($canvas)
$graphics.Clear([System.Drawing.Color]::FromArgb(24, 29, 34))
$graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
$graphics.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
$font = [System.Drawing.Font]::new('Microsoft YaHei', 21)
$smallFont = [System.Drawing.Font]::new('Microsoft YaHei', 12)
$brush = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::FromArgb(233, 229, 215))
$before = [System.Drawing.Image]::FromFile((Join-Path $rendersRoot '00_before_v08.png'))
$after = [System.Drawing.Image]::FromFile((Join-Path $rendersRoot '04_interior.png'))
$graphics.DrawString('V8 原机位 · 调整前', $font, $brush, 15, 10)
$graphics.DrawString('V8.1 殿内望云 · 调整后', $font, $brush, 925, 10)
$graphics.DrawImage($before, 15, 52, 900, 675)
$graphics.DrawImage($after, 925, 52, 900, 675)
$graphics.DrawString('均为 Blender 实际渲染；仅等比例排版。月门净径 44 米，人物约 1.8 米。', $smallFont, $brush, 15, 733)
$canvas.Save((Join-Path $rendersRoot '00_before_after_comparison.png'), [System.Drawing.Imaging.ImageFormat]::Png)
$before.Dispose()
$after.Dispose()
$graphics.Dispose()
$canvas.Dispose()
$font.Dispose()
$smallFont.Dispose()
$brush.Dispose()
Get-ChildItem -LiteralPath $rendersRoot -Filter '*.png' | ForEach-Object {
    $picture = [System.Drawing.Image]::FromFile($_.FullName)
    [PSCustomObject]@{ File = $_.Name; Width = $picture.Width; Height = $picture.Height; Bytes = $_.Length }
    $picture.Dispose()
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $deliveryRoot 'qa/delivery_images.json') -Encoding utf8
