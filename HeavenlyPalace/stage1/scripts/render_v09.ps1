<#
从已保存的第九版工程输出固定机位与细节实渲，默认交付六张正式图。
各机位仅切换时间线相机；独立目录保存图片、设置与耗时记录。
#>
param([string]$Frames = '1,2,3,4,17,18', [switch]$Preview, [switch]$Baseline)
$ErrorActionPreference = 'Stop'
$stageRoot = Split-Path $PSScriptRoot -Parent
$blenderPath = 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe'
$scenePath = Join-Path $stageRoot 'HeavenlyPalace_Detail_v09.blend'
$renderArgs = @('--frames', $Frames)
if ($Preview) { $renderArgs += '--preview' }
if ($Baseline) {
    $scenePath = Join-Path $stageRoot 'HeavenlyPalace_Lookdev_v08_1.blend'
    $renderArgs = @('--frames', '4', '--baseline')
}
& $blenderPath -b $scenePath -t 16 --python-exit-code 1 --python (Join-Path $PSScriptRoot 'render_detail_v09.py') -- @renderArgs
if ($LASTEXITCODE -ne 0) { throw "Blender 渲染未成功完成，退出码：$LASTEXITCODE" }
