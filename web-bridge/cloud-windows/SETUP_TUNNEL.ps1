# Hardened remote-managed tunnel setup. Cloudflare Access MUST protect the hostname first.
#Requires -Version 5.1
param([Parameter(Mandatory=$true)][string]$Hostname)
$ErrorActionPreference='Stop'
$principal=New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
  throw 'Нужен PowerShell от имени администратора.'
}
if ($Hostname -notmatch '^[A-Za-z0-9][A-Za-z0-9.-]*\.[A-Za-z]{2,}$') {
  throw 'Некорректный домен.'
}
$cf=Get-Command cloudflared.exe -ErrorAction SilentlyContinue
if (-not $cf) { throw 'Сначала установите официальный Cloudflare cloudflared.' }
if (Get-Service cloudflared -ErrorAction SilentlyContinue) {
  throw 'Служба cloudflared уже есть. Не меняем действующую конфигурацию.'
}
# Fail closed. Access commonly redirects to /cdn-cgi/access/login.
try {
  $res=Invoke-WebRequest -Uri ('https://'+$Hostname+'/') -UseBasicParsing -MaximumRedirection 0 -ErrorAction Stop
  $status=[int]$res.StatusCode; $loc=$res.Headers['Location']
} catch [System.Net.WebException] {
  if (-not $_.Exception.Response) { throw 'Hostname не отвечает. Сначала настройте DNS, Tunnel и Access.' }
  $status=[int]$_.Exception.Response.StatusCode
  $loc=$_.Exception.Response.Headers['Location']
}
if ($status -notin @(302,303,307,308) -or $loc -notmatch '(?i)(/cdn-cgi/access/|\.cloudflareaccess\.com)') {
  throw "Защита Cloudflare Access не подтверждена (HTTP $status). Служба НЕ устанавливается."
}
Write-Host 'Проверка Access пройдена. Токен нужен только в этой Windows VM.'
$secure=Read-Host 'Cloudflare Tunnel token' -AsSecureString
$bstr=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
  $token=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
  if ($token.Length -lt 30) { throw 'Некорректный токен.' }
  & $cf.Source service install $token | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "Cloudflared завершился с кодом $LASTEXITCODE" }
} finally {
  [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
  Remove-Variable token -ErrorAction SilentlyContinue
}
Write-Host 'Туннель установлен как Windows service. Проверьте вход и отказ без авторизации.'
