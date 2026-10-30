# ASCII-only. Render mermaid HTML to tight-cropped hi-res PNG.
# Usage: powershell -ExecutionPolicy Bypass -File render.ps1
# Output: arch1.png..arch4.png in this folder (scripts/render-arch/),
#         then copy+rename to docs/系统架构图/*.png.
# Re-render after editing arch*.html.
$edge = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
$tmp = $PSScriptRoot

foreach ($n in 'arch1','arch2','arch3','arch4') {
  $html = Join-Path $tmp ($n + '.html')
  $url = 'file:///' + ($html -replace '\\','/')

  $dom = (& $edge --headless --disable-gpu --user-data-dir=$tmp\m-prof --dump-dom --virtual-time-budget=6000 $url 2>$null | Out-String)
  if ($dom -match 'SIZE:(\d+)x(\d+)') {
    $w = [int]$Matches[1]; $h = [int]$Matches[2]
  } else {
    Write-Host ($n + ': MEASURE FAILED')
    continue
  }
  Start-Sleep -Milliseconds 300

  $pad = 16
  $winW = $w + $pad; $winH = $h + $pad
  $png = Join-Path $tmp ($n + '.png')
  & $edge --headless --disable-gpu --no-first-run --no-default-browser-check --user-data-dir=$tmp\s-prof --force-device-scale-factor=3 --window-size="$winW,$winH" --virtual-time-budget=6000 --screenshot=$png $url 2>$null
  if (Test-Path $png) {
    Write-Host ($n + ': content ' + $w + 'x' + $h + ' -> PNG ' + ($winW*3) + 'x' + ($winH*3))
  } else {
    Write-Host ($n + ': content ' + $w + 'x' + $h + ' : SCREENSHOT FAILED')
  }
  Start-Sleep -Milliseconds 300
}
Remove-Item -Recurse -Force "$tmp\m-prof", "$tmp\s-prof" -ErrorAction SilentlyContinue
Write-Host 'DONE'
