# Build server release zip.
# Contents: backend/ (excl. venv, caches, local db, .env) + deploy/
# Usage: powershell -ExecutionPolicy Bypass -File deploy\build.ps1
# NOTE: keep this file ASCII-only. PS 5.1 reads non-BOM files as ANSI,
#       non-ASCII comments can corrupt the line after them.
$root = Split-Path -Parent $PSScriptRoot
$stamp = Get-Date -Format 'yyyyMMdd'
$outDir = Join-Path $root 'release'
$zip = Join-Path $outDir "dc2-release-$stamp.zip"
New-Item -ItemType Directory -Force $outDir | Out-Null

$stage = Join-Path $env:TEMP "dc2-stage-$stamp"
if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
New-Item -ItemType Directory -Force $stage | Out-Null

$backend = Join-Path $root 'backend'
New-Item -ItemType Directory -Force (Join-Path $stage 'backend') | Out-Null

$exclude = @('.venv', '__pycache__', '.pytest_cache', 'uploads', '.env', '.git')
Get-ChildItem $backend -Force | Where-Object {
  $exclude -notcontains $_.Name -and $_.Name -notmatch '\.(db|pyc)$'
} | ForEach-Object {
  Copy-Item $_.FullName (Join-Path $stage 'backend') -Recurse -Force
}
# Nested __pycache__ dirs and local SQLite DBs are useless on the server.
Get-ChildItem (Join-Path $stage 'backend') -Recurse -Directory -Filter '__pycache__' |
  Remove-Item -Recurse -Force
Get-ChildItem (Join-Path $stage 'backend') -Recurse -File |
  Where-Object { $_.Extension -in '.db', '.pyc' } | Remove-Item -Force
# 大数据栅格（WorldClim 11MB）不进发布包：服务器一次性 scp 部署到 data/spatial/
$spatial = Join-Path $stage 'backend\data\spatial'
if (Test-Path $spatial) { Remove-Item -Recurse -Force $spatial }
# 识别原图（服务器运行时数据，/opt/dc2/data/recognitions）不进发布包
$recog = Join-Path $stage 'backend\data\recognitions'
if (Test-Path $recog) { Remove-Item -Recurse -Force $recog }

Copy-Item (Join-Path $root 'deploy') (Join-Path $stage 'deploy') -Recurse -Force

# Web 管理平台构建产物（web/dist，存在才打进去）
$webDist = Join-Path $root 'web\dist'
if (Test-Path $webDist) {
  Copy-Item $webDist (Join-Path $stage 'web') -Recurse -Force
}

Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $zip -Force
Remove-Item -Recurse -Force $stage

$sizeMB = [math]::Round((Get-Item $zip).Length / 1MB, 1)
Write-Host "Release package: $zip ($sizeMB MB)"
Write-Host "Upload to server, extract, then run deploy/provision.sh (see deploy/README.md)"
