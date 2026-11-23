param(
 [Parameter(Mandatory=$true)][string]$AppDir,
 [string]$ServiceUser = '',
 [string]$TaskName = 'SOYUZ-Media-Cloud'
)
$ErrorActionPreference = 'Stop'
$original = Join-Path $AppDir 'SOYUZ_Media_START.py'
$launcher = Join-Path (Split-Path $PSScriptRoot -Parent) 'SOYUZ_Media_WEB.py'
if (-not (Test-Path -LiteralPath $original -PathType Leaf)) { throw "Отсутствует $original" }
if (-not (Test-Path -LiteralPath $launcher -PathType Leaf)) { throw "Отсутствует $launcher" }
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { throw 'Запустите PowerShell от имени администратора' }
if (-not $ServiceUser) { $ServiceUser = "$env:USERDOMAIN\$env:USERNAME" }
$py = Get-Command py.exe -ErrorAction SilentlyContinue
if ($py) { $python = (& $py.Source -3 -c 'import sys;print(sys.executable)' | Select-Object -First 1) }
else { $python = (Get-Command python.exe -ErrorAction SilentlyContinue).Source }
if (-not $python -or -not (Test-Path -LiteralPath $python -PathType Leaf)) { throw 'Python 3 не найден' }
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) { throw 'Задание уже существует; ничего не перезаписано' }
Write-Host "Программа $AppDir; пользователь $ServiceUser; Python $python"
Write-Warning 'Сначала перенесите историю и ключи в APPDATA указанного Windows пользователя. Нельзя загружать их в GitHub.'
if ((Read-Host 'Для создания задания на автозапуск введите YES') -cne 'YES') { throw 'Отменено' }
$passwordSecure = Read-Host 'Пароль Windows пользователя (не пароль GitHub/Ozon)' -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($passwordSecure)
try {
 $password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
 $action = New-ScheduledTaskAction -Execute $python -Argument ('"' + $launcher + '" "' + $AppDir + '"') -WorkingDirectory (Split-Path $launcher -Parent)
 $trigger = New-ScheduledTaskTrigger -AtStartup
 $settings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Seconds 0) -StartWhenAvailable
 Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -User $ServiceUser -Password $password -Description 'SOYUZ Media original server via local loopback tunnel' | Out-Null
 Write-Host 'Автозапуск зарегистрирован. Публичный доступ НЕ открыт.'
} finally {
 [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
 Remove-Variable password -ErrorAction SilentlyContinue
}
