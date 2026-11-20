# Ozon Seller API — параметры подключения

Источник: действующий репозиторий `soyuz-music-shop/soyuz-music-store`, файлы `OZON-API-SETUP.md`, `.github/workflows/sync-ozon.yml` и `scripts/sync_ozon.py`.

| Параметр | Значение |
|---|---|
| API endpoint | `https://api-seller.ozon.ru` |
| Заголовок Client ID | `Client-Id` |
| Заголовок API Key | `Api-Key` |
| Имя секрета Actions | `OZON_CLIENT_ID` |
| Имя секрета Actions | `OZON_API_KEY` |

## Настройка только в новом репозитории

Секреты старого сайта не копируются автоматически и не могут быть прочитаны из этого проекта.

1. Откройте `Settings → Secrets and variables → Actions` репозитория `soyuz-music-photocards`.
2. Добавьте `OZON_CLIENT_ID` и `OZON_API_KEY` как repository secrets.
3. Запустите вручную workflow `Проверить Ozon API (без изменений)` в разделе `Actions`.
4. Проверяйте лог: скрипт делает только запрос чтения `/v3/product/list`.

Никогда не публикуйте значения ключей в файлах репозитория, issues или переписке.
