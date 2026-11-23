# One command on a dedicated Windows VM: downloads only public installer files,
# then installs the UNCHANGED original program from a ZIP located on that VM.
#Requires -Version 5.1
param([string]$SourceZip='')
$ErrorActionPreference = 'Stop'
$uriRoot = 'https://raw.githubusercontent.com/soyuz-music-shop/soyuz-music-photocards/main/web-bridge/'
$root = Join-Path $env:TEMP ('SOYUZ_Media_Install_' + [guid]::NewGuid().ToString('N'))
$files = @(
  'SOYUZ_Media_WEB.py',
  'cloud-windows/INSTALL_ONE_CLICK.ps1',
  'cloud-windows/INSTALL_CLOUD_TASK.ps1',
  'cloud-windows/CHECK_CLOUD.ps1',
  'cloud-windows/SETUP_TUNNEL.ps1'
)
try {
  foreach ($file in $files) {
    $dest=Join-Path $root ($file.Replace('/','\'))
    New-Item -ItemType Directory -Path (Split-Path $dest -Parent) -Force | Out-Null
    Invoke-WebRequest -Uri ($uriRoot + $file) -OutFile $dest -UseBasicParsing
    if (-not (Test-Path $dest -PathType Leaf)) { throw "Не скачан установщик: $file" }
  }
  $installer = Join-Path (Join-Path $root 'cloud-windows') 'INSTALL_ONE_CLICK.ps1'
  & $installer -SourceZip $SourceZip
} finally {
  # Running scheduled task points to C:\SOYUZMedia\cloud-kit, not this temporary dir.
  Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
}
