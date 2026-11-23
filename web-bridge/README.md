# SOYUZ Media — web bridge (без изменения редактора)

Отдельный запуск **исходной Windows-программы** с фиксированным портом `127.0.0.1:8787`. Исходный Python-сервер, HTML/JS-интерфейс, API-маршруты и логика Ozon/Avito не модифицируются. GitHub содержит только веб-запуск и пример конфигурации, не сам архив редактора.

## Установка

1. Сделайте резервные копии папки программы и `%APPDATA%/SOYUZ_Media/`.
2. Скопируйте `SOYUZ_Media_WEB.py` и `START_WEB.bat` рядом с `SOYUZ_Media_START.py`.
3. Запустите `START_WEB.bat`. Откройте локально `http://127.0.0.1:8787/SOYUZ_Media_v212_2_Dewatermark_working.html`.
4. Для веб-доступа извне создайте **named Cloudflare Tunnel** и защищённое приложение **Cloudflare Access** с доступом только для вашего аккаунта. Заполните личный `config.yml` по образцу, указав `teamName` и `audTag` приложения Access.
5. Проверьте `cloudflared tunnel --config config.yml ingress validate` и запускайте `cloudflared tunnel --config config.yml run`. Проверьте, что вход без авторизации Cloudflare Access отклонён.

**Не публикуйте Quick Tunnel или публичный tunnel без обязательного Access.** Это рабочий редактор с доступом к API Ozon/Avito.

## История и данные

- Завершённые карточки: `%APPDATA%/SOYUZ_Media/completed_items_v3.json`.
- Статусы отправок: `%APPDATA%/SOYUZ_Media/ozon_send_status_v1.json`.
- Правки каталога: `SOYUZ_Media_local_state.sqlite3` рядом с исходным сервером.
- Дополнительное состояние: `%APPDATA%/SOYUZ_Media/`.
- Отдельные браузерные данные в `localStorage` и `IndexedDB` не копируются при смене адреса: используйте штатные **Экспорт прогресса / Импорт прогресса** и проверьте результаты.

GitHub хранит только код, а не историю и не ключи API. Веб-доступ работает только пока включён Windows-компьютер с сервером и запущен tunnel. GitHub Pages сам по себе этот Python-сервер не запускает.

Документация Cloudflare: https://developers.cloudflare.com/tunnel/features/locally-managed-tunnels/configuration-file/ и https://developers.cloudflare.com/reference-architecture/design-guides/identity-gated-edge/
