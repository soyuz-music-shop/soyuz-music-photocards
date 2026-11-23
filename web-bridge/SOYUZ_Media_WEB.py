#!/usr/bin/env python3
"""Web launcher for original SOYUZ Media (no changes to source or stored data)."""
from __future__ import annotations

import importlib
import os
import socket
import sys
from pathlib import Path

LAUNCHER_DIR = Path(__file__).resolve().parent
APP_ENTRY = "SOYUZ_Media_START.py"
LOCATION_FILE = LAUNCHER_DIR / "SOYUZ_Media_WEB.path"
HOST = "127.0.0.1"  # The service must NOT listen directly on a public interface.


def _as_app_dir(value: str | Path | None) -> Path | None:
    if not value:
        return None
    try:
        path = Path(str(value).strip().strip('"')).expanduser().resolve()
        if path.is_file():
            path = path.parent
        if (path / APP_ENTRY).is_file():
            return path
        nested = path / "SOYUZ_Media"
        if (nested / APP_ENTRY).is_file():
            return nested
        # Original archive outer directory: 01 СОЮЗ МЕДИА / SOYUZ_Media
        outer = path / "01 СОЮЗ МЕДИА" / "SOYUZ_Media"
        if (outer / APP_ENTRY).is_file():
            return outer
    except (OSError, ValueError):
        return None
    return None


def _select_app_dir() -> Path:
    # An explicit path can be passed by dragging the folder onto START_WEB.bat.
    locations: list[str | Path | None] = [
        sys.argv[1] if len(sys.argv) > 1 else None,
        os.environ.get("SOYUZ_MEDIA_DIR"),
    ]
    if LOCATION_FILE.is_file():
        try:
            locations.append(LOCATION_FILE.read_text(encoding="utf-8-sig").strip())
        except OSError:
            pass
    # Usual layouts, including files extracted in a separate WEB_Bridge folder.
    locations += [LAUNCHER_DIR, LAUNCHER_DIR.parent, LAUNCHER_DIR.parent.parent]
    for candidate in locations:
        directory = _as_app_dir(candidate)
        if directory is not None:
            return directory

    print("Не найдена папка SOYUZ Media. Укажите её один раз.", flush=True)
    print("В открывшемся окне выберите SOYUZ_Media_START.py", flush=True)
    selected = ""
    try:
        from tkinter import Tk, filedialog
        root = Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askopenfilename(
            parent=root,
            title="Укажите SOYUZ_Media_START.py из вашей программы",
            filetypes=[("SOYUZ_Media_START.py", APP_ENTRY), ("Файлы Python", "*.py")],
        )
        root.destroy()
    except (ImportError, RuntimeError, OSError) as exc:
        print(f"Диалог выбора файла недоступен: {exc}", flush=True)

    directory = _as_app_dir(selected)
    if directory is None:
        try:
            print("Можно вставить полный путь к папке SOYUZ_Media (или к SOYUZ_Media_START.py):", flush=True)
            directory = _as_app_dir(input("> "))
        except (EOFError, KeyboardInterrupt):
            pass
    if directory is None:
        raise SystemExit("Папка программы не выбрана. Изменений в программе нет.")

    # Only a local path, never API credentials or history, is cached for next run.
    try:
        LOCATION_FILE.write_text(str(directory) + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"Не удалось запомнить путь ({exc}); в следующий раз выберите папку снова.", flush=True)
    return directory


def main() -> int:
    app_dir = _select_app_dir()
    try:
        port = int(os.environ.get("SOYUZ_MEDIA_WEB_PORT", "8787"))
    except ValueError as exc:
        raise SystemExit("Некорректный SOYUZ_MEDIA_WEB_PORT") from exc
    if not 1024 <= port <= 65535:
        raise SystemExit("SOYUZ_MEDIA_WEB_PORT должен быть в диапазоне 1024..65535")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((HOST, port))
        except OSError as exc:
            raise SystemExit(f"Порт {HOST}:{port} занят: {exc}") from exc

    # Use the existing stable application entry point instead of pinning a
    # release-specific server filename. Runtime and data paths stay original.
    sys.path.insert(0, str(app_dir))
    os.chdir(app_dir)
    launcher = importlib.import_module("SOYUZ_Media_START")
    original_main = launcher.main
    server_module = sys.modules.get(original_main.__module__)
    base = getattr(server_module, "base", None)
    if base is None or not callable(getattr(base, "find_free_port", None)):
        raise SystemExit("Не удалось определить локальный сервер SOYUZ Media. Его файлы не менялись.")

    base.HOST = HOST
    base.find_free_port = lambda: port
    base.open_browser_later = lambda _url: None
    print(f"Найдена программа: {app_dir}", flush=True)
    print("SOYUZ Media WEB: исходная программа и её история не изменяются", flush=True)
    print(f"Открывайте ссылку, которую напечатает сервер (порт {port}).", flush=True)
    print("Для доступа из интернета нужен защищённый Cloudflare Tunnel + Access.", flush=True)
    return original_main()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(0)
