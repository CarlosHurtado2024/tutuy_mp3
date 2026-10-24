"""Portable launcher: embedded server + desktop browser app window."""
from __future__ import annotations

import argparse
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import subprocess
import sys
import threading
from urllib.request import urlopen
import webbrowser

from waitress import create_server

from tutuy.engine import portable_dir
from tutuy.server import create_app


def open_window(url):
    if os.name == "nt":
        candidates = [
            Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe",
            Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Microsoft/Edge/Application/msedge.exe",
            Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Google/Chrome/Application/chrome.exe",
        ]
        for browser in candidates:
            if browser.is_file():
                subprocess.Popen([str(browser), f"--app={url}", "--window-size=1380,920"], creationflags=subprocess.CREATE_NO_WINDOW)
                return
    webbrowser.open(url)


def run():
    parser = argparse.ArgumentParser(description="Tutuy MP3 · escritorio, web y móvil")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="0.0.0.0", choices=["0.0.0.0", "127.0.0.1"])
    parser.add_argument("--data-dir", type=Path, default=portable_dir() / "data")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("El puerto debe estar entre 1024 y 65535.")
    args.data_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(args.data_dir / "tutuy.log", maxBytes=2_000_000, backupCount=2, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, handlers=[handler], format="%(asctime)s %(levelname)s %(message)s")
    stop = threading.Event()
    server = None
    app = None
    try:
        # A port already serving Tutuy is reused; another application is never terminated.
        url = f"http://127.0.0.1:{args.port}"
        key_file = args.data_dir / "conexion.json"
        try:
            with urlopen(f"{url}/api/health", timeout=1) as response:
                existing = json.load(response)
            if existing.get("app") == "Tutuy MP3" and key_file.exists():
                key = json.loads(key_file.read_text(encoding="utf-8"))["key"]
                if not args.no_browser:
                    open_window(f"{url}/#key={key}")
                return
        except (OSError, ValueError):
            pass
        app = create_app(args.data_dir, args.port, stop)
        server = create_server(app, host=args.host, port=args.port, threads=10, ident="Tutuy MP3",
                               channel_timeout=120, clear_untrusted_proxy_headers=True)
        thread = threading.Thread(target=server.run, daemon=True, name="tutuy-web")
        thread.start()
        if not args.no_browser:
            open_window(f"{url}/#key={app.extensions['pairing_key']}")
        if sys.stdout:
            print(f"Tutuy MP3 listo en {url}", flush=True)
        stop.wait()
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        logging.exception("Startup failed")
        if getattr(sys, "frozen", False) and os.name == "nt":
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, f"No se pudo abrir Tutuy MP3.\n\n{exc}\n\nRevisa si el puerto {args.port} está ocupado o si la carpeta tiene permiso de escritura.", "Tutuy MP3", 0x10)
        elif sys.stderr:
            print(str(exc), file=sys.stderr)
        return 1
    finally:
        if app:
            app.extensions["engine"].close()
        if server:
            server.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
