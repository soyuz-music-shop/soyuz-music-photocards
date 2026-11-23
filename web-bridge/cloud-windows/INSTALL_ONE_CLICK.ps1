# Installs original ZIP on a DEDICATED Windows VM. Never upload it to public GitHub.
#Requires -Version 5.1
param(
  [string]$SourceZip = '',
  [string]$InstallRoot = 'C:\SOYUZMedia',
  [switch]$NoAutostart
)
$ErrorActionPreference = 'Stop'
$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  throw 'Запустите PowerShell от имени администратора на Windows VM.'
}
if (-not (Get-Command py.exe -ErrorAction SilentlyContinue) -and -not (Get-Command python.exe -ErrorAction SilentlyContinue)) {
  throw 'Требуется Python 3 на облачной Windows VM.'
}
if (-not $SourceZip) {
  try {
    Add-Type -AssemblyName System.Windows.Forms
    $picker = New-Object System.Windows.Forms.OpenFileDialog
    $picker.Title = 'Выберите исходный архив SOYUZ Media с SQLite'
    $picker.Filter = 'ZIP (*.zip)|*.zip'
    if ($picker.ShowDialog() -eq 'OK') { $SourceZip = $picker.FileName }
  } catch {}
  if (-not $SourceZip) { $SourceZip = Read-Host 'Путь к оригинальному ZIP на этой VM' }
}
if (-not (Test-Path -LiteralPath $SourceZip -PathType Leaf)) { throw 'Исходный ZIP не найден.' }
$app = Join-Path $InstallRoot 'app'
$kit = Join-Path $InstallRoot 'cloud-kit'
$entry = Join-Path $app 'SOYUZ_Media_START.py'
if (-not (Test-Path -LiteralPath $entry -PathType Leaf)) {
  if (Test-Path -LiteralPath $app) { throw 'Папка app уже существует: автоматическая замена запрещена.' }
  Add-Type -AssemblyName System.IO.Compression.FileSystem
  $zip = [System.IO.Compression.ZipFile]::OpenRead($SourceZip)
  try {
    foreach ($item in $zip.Entries) {
      $path = $item.FullName.Replace('\','/')
      if ($path.StartsWith('/') -or $path -match '(^|/)\.\.(/|$)' -or $path -match '^[A-Za-z]:' -or $path.Contains(':')) {
        throw "Небезопасный путь в ZIP: $path"
      }
    }
  } finally { $zip.Dispose() }
  $stage = Join-Path $env:TEMP ('soyuz-stage-' + [guid]::NewGuid().ToString('N'))
  try {
    Expand-Archive -LiteralPath $SourceZip -DestinationPath $stage
    $entries = @(Get-ChildItem -LiteralPath $stage -Filter SOYUZ_Media_START.py -File -Recurse)
    if ($entries.Count -ne 1) { throw 'Найдено не ровно одно приложение SOYUZ Media.' }
    $source = $entries[0].Directory.FullName
    foreach ($file in @('SOYUZ_Media_v212_132_Ozon_Avito_API.py','SOYUZ_Media_v212_41_Ozon_API.py','SOYUZ_Media_v212_2_Dewatermark_working.html')) {
      if (-not (Test-Path -LiteralPath (Join-Path $source $file) -PathType Leaf)) { throw "В архиве отсутствует $file" }
    }
    New-Item -ItemType Directory -Path $InstallRoot -Force | Out-Null
    Move-Item -LiteralPath $source -Destination $app
    Write-Host 'Исходный редактор и SQLite скопированы в отдельную облачную VM без изменений.'
  } finally { Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue }
} else { Write-Host 'Существующая программа найдена. Программа и история не перезаписаны.' }
$bundleRoot = Split-Path $PSScriptRoot -Parent
if (-not (Test-Path -LiteralPath (Join-Path $bundleRoot 'SOYUZ_Media_WEB.py') -PathType Leaf)) {
  throw 'Нет файла SOYUZ_Media_WEB.py в комплекте. Распакуйте ZIP установщика целиком.'
}
if (-not (Test-Path -LiteralPath $kit)) {
  New-Item -ItemType Directory -Path (Join-Path $kit 'cloud-windows') -Force | Out-Null
  Copy-Item -LiteralPath (Join-Path $bundleRoot 'SOYUZ_Media_WEB.py') -Destination (Join-Path $kit 'SOYUZ_Media_WEB.py')
  foreach ($script in @('INSTALL_CLOUD_TASK.ps1','CHECK_CLOUD.ps1')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $script) -Destination (Join-Path $kit 'cloud-windows' $script)
  }
}
$state = Join-Path $env:APPDATA 'SOYUZ_Media'
if (-not (Test-Path -LiteralPath (Join-Path $state 'completed_items_v3.json') -PathType Leaf)) {
  Write-Warning "Отметки 'Сделано' из APPDATA отсутствуют на VM. Перенесите %APPDATA%\SOYUZ_Media исходного ПК перед работой."
}
if (-not (Test-Path -LiteralPath (Join-Path $state 'ozon_send_status_v1.json') -PathType Leaf)) {
  Write-Warning 'История отправок Ozon из APPDATA отсутствует на VM. Перенесите её отдельно.'
}
Write-Warning 'Microsoft Photos/Windows AI могут требовать активный графический Windows-сеанс.'
if (-not $NoAutostart) {
  $task = Get-ScheduledTask -TaskName 'SOYUZ-Media-Cloud' -ErrorAction SilentlyContinue
  if (-not $task) {
    & (Join-Path $kit 'cloud-windows' 'INSTALL_CLOUD_TASK.ps1') -AppDir $app
  } else { Write-Host 'Автозапуск уже есть; оставлен без изменений.' }
}
Write-Host 'Веб-сервер слушает только 127.0.0.1:8787. Публикация требует Cloudflare Access.'
Write-Host "Проверка: & '$kit\cloud-windows\CHECK_CLOUD.ps1' -AppDir '$app'"
