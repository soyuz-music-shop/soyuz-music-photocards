#!/usr/bin/env python3
"""Run unchanged SOYUZ Media on a fixed local port for a secure web tunnel."""
from __future__ import annotations

import os
import socket
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if not (ROOT / "SOYUZ_Media_v212_132_Ozon_Avito_API.py").is_file():
    raise SystemExit("Положите SOYUZ_Media_WEB.py рядом с основным сервером SOYUZ Media.")

HOST = "127.0.0.1"
try:
    PORT = int(os.environ.get("SOYUZ_MEDIA_WEB_PORT", "8787"))
except ValueError as exc:
    raise SystemExit("Некорректный SOYUZ_MEDIA_WEB_PORT") from exc
if not 1024 <= PORT <= 65535:
    raise SystemExit("SOYUZ_MEDIA_WEB_PORT должен быть в диапазоне 1024..65535")
with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
    try:
        probe.bind((HOST, PORT))
    except OSError as exc:
        raise SystemExit(f"Порт {HOST}:{PORT} занят: {exc}") from exc

import SOYUZ_Media_v212_132_Ozon_Avito_API as app  # noqa: E402

# Only in-memory startup configuration. No application source is modified.
app.base.HOST = HOST
app.base.find_free_port = lambda: PORT
app.base.open_browser_later = lambda _url: None
print("SOYUZ Media WEB: исходная программа без изменений")
print(f"Адрес локального сервера: http://{HOST}:{PORT}/")
print("Для удалённого доступа необходим Cloudflare Tunnel с обязательным Access.")
raise SystemExit(app.main())
