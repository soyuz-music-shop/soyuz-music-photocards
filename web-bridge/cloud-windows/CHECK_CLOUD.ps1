param([string]$AppDir = '')
$ErrorActionPreference = 'Stop'
Write-Host 'SOYUZ Media cloud: проверка без изменений данных'
$os = Get-CimInstance Win32_OperatingSystem
Write-Host ('Windows: ' + $os.Caption)
$py = Get-Command py.exe -ErrorAction SilentlyContinue
if ($py) { $pythonPath = (& $py.Source -3 -c 'import sys;print(sys.executable)' | Select-Object -First 1) }
else { $pythonPath = (Get-Command python.exe -ErrorAction SilentlyContinue).Source }
if (-not $pythonPath -or -not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) { throw 'Python 3 не найден' }
Write-Host ('Python: ' + $pythonPath)
if ($AppDir) {
  foreach ($f in @('SOYUZ_Media_START.py','SOYUZ_Media_v212_132_Ozon_Avito_API.py','SOYUZ_Media_v212_41_Ozon_API.py','SOYUZ_Media_v212_2_Dewatermark_working.html')) {
    if (-not (Test-Path -LiteralPath (Join-Path $AppDir $f) -PathType Leaf)) { throw "Не найден файл $f" }
  }
  Write-Host ('SQLite: ' + (Test-Path -LiteralPath (Join-Path $AppDir 'SOYUZ_Media_local_state.sqlite3')))
}
$state = Join-Path $env:APPDATA 'SOYUZ_Media'
Write-Host ('APPDATA: ' + $state)
Write-Host ('Completed state: ' + (Test-Path -LiteralPath (Join-Path $state 'completed_items_v3.json')))
Write-Host ('Ozon send state: ' + (Test-Path -LiteralPath (Join-Path $state 'ozon_send_status_v1.json')))
Write-Host ('Microsoft Photos package: ' + [bool](Get-AppxPackage Microsoft.Windows.Photos -ErrorAction SilentlyContinue))
Write-Host ('GPU: ' + ((Get-CimInstance Win32_VideoController | ForEach-Object Name) -join ', '))
Write-Host ('cloudflared installed: ' + [bool](Get-Command cloudflared.exe -ErrorAction SilentlyContinue))
Write-Warning 'Photos, NPU, Vulkan/Real-ESRGAN нельзя считать рабочими без отдельного теста на VM.'
