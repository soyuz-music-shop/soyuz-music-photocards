# SOYUZ Media — облачный Windows-хост

**Статус: подготовка, не публичный работающий сайт.** Сохраняет все исходные Python/HTML/JS файлы без изменений. Для независимости от домашнего ПК требуется постоянно работающая Windows VM с Python, локальным диском и Cloudflare Access + Tunnel. GitHub Actions и Cloudflare Workers/D1 сами по себе не запускают неизменённый Windows редактор.

## Обязательные шаги

1. Подготовить отдельную Windows VM (без вмешательства в production Docker-хост geomercury); проверить, поддерживает ли она Microsoft Photos, NPU, Vulkan GPU и фоновые процессы. Даже Windows Server не гарантирует функциональность Photos и Windows AI.
2. В приватном канале перенести исходную папку SOYUZ Media вместе с SQLite, предварительно остановив локальную копию и сделав резервную копию. Приватные файлы, в том числе историю, **не загружать в публичный GitHub**.
3. Перенести конфигурацию и историю из `%APPDATA%\SOYUZ_Media\` в профиль **того же Windows пользователя**, под которым будет работать сервер (включая `completed_items_v3.json` и `ozon_send_status_v1.json`).
4. Скопировать рядом из `web-bridge/` неизменяемый запускатель `SOYUZ_Media_WEB.py`. Скопировать из этой папки скрипты CHECK_CLOUD и INSTALL_CLOUD_TASK. Запускать PowerShell с правами администратора:

```powershell
.\CHECK_CLOUD.ps1 -AppDir 'C:\SOYUZMedia\app'
.\INSTALL_CLOUD_TASK.ps1 -AppDir 'C:\SOYUZMedia\app' -ServiceUser 'VMNAME\soyuzmedia'
Start-ScheduledTask -TaskName 'SOYUZ-Media-Cloud'
```

5. Проверить на VM локально `http://127.0.0.1:8787/SOYUZ_Media_v212_2_Dewatermark_working.html`. Не открывать порт 8787 в Internet/Firewall. Создать Cloudflare Tunnel из VM к `127.0.0.1:8787`, обязательно защитить Cloudflare Access с разрешением только своего аккаунта. Настроить tunnel как автозапускаемую службу.
6. Протестировать экспорт/импорт сохранённого в браузере прогресса: IndexedDB/localStorage с прежнего `localhost` не переезжают при смене доменного имени.

**Без Windows VM и доступа к её настройкам этот GitHub-код сам по себе не разворачивает веб-сайт.** Если VM не поддерживает Microsoft Photos/NPU/Vulkan, полный функционал будет недоступен; исходный редактор при этом не меняется.
