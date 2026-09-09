<#
统一从用户已有的 web 工程启动验证页，后续开发代码集中在该目录。
资源仍读取独立交付目录，首次依赖安装遵循原项目的 pnpm 锁文件。
#>
param([int]$Port = 5174)
$ErrorActionPreference = 'Stop'
$webPath = Join-Path (Split-Path $PSScriptRoot -Parent) 'web'
Push-Location $webPath
try {
    if (-not (Test-Path -LiteralPath 'node_modules')) {
        pnpm.cmd install --frozen-lockfile
        if ($LASTEXITCODE -ne 0) { throw 'Web 项目依赖安装失败' }
    }
    pnpm.cmd exec vite --host 127.0.0.1 --port $Port --strictPort
} finally { Pop-Location }
