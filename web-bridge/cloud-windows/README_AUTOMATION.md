# SOYUZ Media: облачный установщик через GitHub

Всё, что возможно без облачного аккаунта, автоматизировано: GitHub Actions проверяет Python/PowerShell и собирает отдельный установочный ZIP. Это **не работающий облачный сайт**: обычный GitHub-hosted Actions runner временный и не является постоянным сервером.

## Осталось сделать один раз

1. Получить отдельную постоянно работающую **Windows VM** (не Linux Docker сервер). Нужны Python 3, постоянный диск, Windows GUI. Для Microsoft Photos и Windows AI нужна совместимая Windows 11 и аппаратная среда; полноценная поддержка в облаке не гарантируется.
2. Перенести на VM **непублично** оригинальный ZIP `01 СОЮЗ МЕДИА(1).zip`. Для полной истории дополнительно перенести содержимое `%APPDATA%\SOYUZ_Media\` с исходного компьютера в профиль той Windows-учётной записи, под которой будет работать сервер.
3. Самый короткий путь: открыть **PowerShell от администратора на Windows VM** и выполнить две команды (файлы установщика скачиваются из нашего GitHub автоматически):

```powershell
$u='https://raw.githubusercontent.com/soyuz-music-shop/soyuz-music-photocards/main/web-bridge/cloud-windows/BOOTSTRAP.ps1'; $p=Join-Path $env:TEMP 'SOYUZ_Bootstrap.ps1'; Invoke-WebRequest $u -OutFile $p -UseBasicParsing
powershell -NoProfile -ExecutionPolicy Bypass -File $p -SourceZip 'C:\Users\Administrator\Downloads\01 СОЮЗ МЕДИА(1).zip'
```

Можно также использовать ZIP из GitHub Actions, распаковав его на VM. В таком случае выполнить:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\web-bridge\cloud-windows\INSTALL_ONE_CLICK.ps1 -SourceZip 'C:\Users\Administrator\Downloads\01 СОЮЗ МЕДИА(1).zip'
```

Установщик автоматически проверяет и распаковывает исходную программу, сохраняет SQLite без изменений, копирует веб-запускатель в постоянную папку и предлагает настроить автозапуск. **Существующие папки/задачи он не перезаписывает**.

4. Создать в Cloudflare Zero Trust **remotely-managed Tunnel** с hostname к `http://127.0.0.1:8787`, а также **Cloudflare Access** с персональным allowlist. Установить официальный cloudflared. После настройки DNS и Access выполнить на VM:

```powershell
.\web-bridge\cloud-windows\SETUP_TUNNEL.ps1 -Hostname 'media.example.com'
```

Он проверит редирект Access до установки службы, затем запросит token **локально** на VM. Никогда не присылайте его в чат или GitHub.

## Неизменность и ограничения

Редактор, HTML/JS, API Ozon/Avito, SQLite и история не редактируются. GitHub не содержит оригинальный ZIP, базу данных, историю, токены и ключи. Публичный self-hosted runner не используется.

Microsoft Photos запускается на самом Windows-сервере, а не на клиентском компьютере. Её полноценную работу нельзя автоматически превратить в веб-функцию без изменения редактора. Браузерные `localStorage` и `IndexedDB` также требуют штатного экспорта/импорта при смене адреса.

Если облачной Windows VM пока нет, установка не завершена: GitHub сам VM не предоставляет.

Официальные материалы: https://developers.cloudflare.com/tunnel/get-started/ , https://docs.github.com/en/actions/reference/security/secure-use
