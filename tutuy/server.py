from __future__ import annotations

import hmac
import io
import json
import os
from pathlib import Path
import secrets
import socket
import threading
import time

from flask import Flask, jsonify, request, send_file, send_from_directory
from itsdangerous import BadSignature, URLSafeTimedSerializer
import qrcode
import qrcode.image.svg

from . import __version__
from .engine import AppError, Engine, resource_dir


def lan_addresses(port):
    addresses = set()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            addresses.add(sock.getsockname()[0])
    except OSError:
        pass
    try:
        addresses.update(socket.gethostbyname_ex(socket.gethostname())[2])
    except OSError:
        pass
    return [f"http://{address}:{port}" for address in sorted(addresses) if not address.startswith(("127.", "169.254."))]


def create_app(data_dir: Path, port=8765, stop_event=None):
    static = resource_dir() / "web"
    app = Flask(__name__, static_folder=str(static), static_url_path="/static")
    app.config["MAX_CONTENT_LENGTH"] = 32 * 1024
    # Explicit allowlist for a frontend deployed behind an external API rewrite.
    # With this option, local desktop actions stay disabled even behind a local proxy.
    public_origin = os.environ.get("TUTUY_PUBLIC_ORIGIN", "").strip().rstrip("/")
    if public_origin:
        from urllib.parse import urlparse
        parsed = urlparse(public_origin)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
            raise ValueError("TUTUY_PUBLIC_ORIGIN debe ser un origen HTTPS, sin ruta ni credenciales.")
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    key_file = data_dir / "conexion.json"
    if key_file.exists():
        configuration = json.loads(key_file.read_text(encoding="utf-8"))
        secret = configuration["key"]
    else:
        secret = secrets.token_urlsafe(32)
        key_file.write_text(json.dumps({"key": secret}), encoding="utf-8")
    serializer = URLSafeTimedSerializer(secret, salt="tutuy-session-v1")
    engine = Engine(data_dir)
    app.extensions.update(engine=engine, pairing_key=secret)
    attempts = {}
    attempt_lock = threading.Lock()

    def is_local():
        return not public_origin and request.remote_addr in {"127.0.0.1", "::1"}

    def local_only():
        if not is_local():
            raise AppError("Esta acción solo está disponible en el computador de la app.", 403)

    @app.before_request
    def protect():
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("Origin")
            if origin and origin not in {request.host_url.rstrip("/"), public_origin}:
                raise AppError("La solicitud procede de un sitio no autorizado.", 403)
            if not request.is_json:
                raise AppError("La solicitud debe usar JSON.", 415)
        if not request.path.startswith("/api/") or request.path in {"/api/health", "/api/connect"}:
            return None
        cookie = request.cookies.get("tutuy_session", "")
        try:
            if serializer.loads(cookie, max_age=30 * 24 * 3600) != "connected":
                raise BadSignature("Invalid session")
        except BadSignature:
            raise AppError("Conecta este dispositivo con el enlace o el código QR de la app.", 401)

    @app.after_request
    def headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' https: data:; media-src 'self' blob:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        if request.path.startswith("/api/") or request.path == "/":
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(AppError)
    def app_error(exc):
        return jsonify(error=str(exc)), exc.status

    @app.errorhandler(400)
    def bad_request(exc):
        return jsonify(error="La solicitud no tiene un formato válido."), 400

    @app.errorhandler(413)
    def large_request(exc):
        return jsonify(error="La selección o el texto son demasiado grandes."), 413

    @app.errorhandler(500)
    def server_error(exc):
        return jsonify(error="Ocurrió un error interno. Revisa data/tutuy.log en la carpeta de la app."), 500

    @app.get("/")
    def index():
        return send_from_directory(static, "index.html")

    @app.get("/manifest.webmanifest")
    def manifest():
        return send_from_directory(static, "manifest.webmanifest", mimetype="application/manifest+json")

    @app.get("/sw.js")
    def worker():
        return send_from_directory(static, "sw.js", mimetype="application/javascript")

    @app.get("/api/health")
    def health():
        return jsonify(app="Tutuy MP3", version=__version__, ready=True)

    @app.get("/deployment.json")
    def deployment():
        return jsonify(mode="local")

    @app.post("/api/connect")
    def connect():
        address = request.remote_addr or "unknown"
        now = time.monotonic()
        with attempt_lock:
            # Discard expired entries, also bounding memory from many LAN clients.
            for key in list(attempts):
                if now - attempts[key][0] > 60:
                    attempts.pop(key)
            since, count = attempts.get(address, (now, 0))
            if count >= 10:
                raise AppError("Demasiados intentos. Espera un minuto antes de conectar.", 429)
            attempts[address] = (since, count + 1)
        data = request.get_json()
        if not isinstance(data, dict):
            raise AppError("Solicitud no válida.")
        if not hmac.compare_digest(str(data.get("key", "")), secret):
            raise AppError("El enlace de conexión no es válido. Escanea de nuevo el QR del computador.", 401)
        with attempt_lock:
            attempts.pop(address, None)
        response = jsonify(connected=True)
        response.set_cookie("tutuy_session", serializer.dumps("connected"), max_age=30 * 24 * 3600,
                            httponly=True, samesite="Strict", secure=request.is_secure or bool(public_origin))
        return response

    def payload():
        data = request.get_json()
        if not isinstance(data, dict):
            raise AppError("Solicitud no válida.")
        return data

    @app.get("/api/status")
    def status():
        return jsonify(online=engine.internet(force=request.args.get("refresh") == "1"),
                       version=__version__, local=is_local(), music_folder=str(engine.music),
                       ffmpeg=bool(engine.ffmpeg), youtube_runtime=bool(engine.node))

    @app.post("/api/search")
    def search():
        data = payload()
        if not engine.search_lock.acquire(blocking=False):
            raise AppError("Ya hay una búsqueda en curso. Espera a que termine.", 429)
        try:
            return jsonify(songs=engine.search(data.get("query", ""), data.get("mode", "artist"), data.get("provider", "youtube"), data.get("limit", 20)))
        finally:
            engine.search_lock.release()

    @app.get("/api/downloads")
    def downloads():
        return jsonify(jobs=engine.jobs())

    @app.post("/api/downloads")
    def enqueue():
        data = payload()
        return jsonify(ids=engine.enqueue(data.get("ids"), data.get("quality", 192))), 202

    @app.post("/api/downloads/<identifier>/cancel")
    def cancel(identifier):
        engine.cancel(identifier)
        return jsonify(ok=True)

    @app.post("/api/downloads/<identifier>/retry")
    def retry(identifier):
        return jsonify(id=engine.retry(identifier)), 202

    @app.get("/api/downloads/<identifier>/file")
    def media(identifier):
        path = engine.file(identifier)
        return send_file(path, mimetype="audio/mpeg", as_attachment=request.args.get("save") == "1", download_name=path.name, conditional=True)

    @app.get("/api/pair")
    def pair():
        local_only()
        addresses = lan_addresses(port)
        return jsonify(urls=[f"{address}/#key={secret}" for address in addresses])

    @app.get("/api/qr")
    def qr():
        local_only()
        addresses = lan_addresses(port)
        selected = request.args.get("address", "")
        if selected not in addresses:
            raise AppError("No se encontró esta dirección de red.")
        image = qrcode.make(f"{selected}/#key={secret}", image_factory=qrcode.image.svg.SvgPathImage, border=3)
        stream = io.BytesIO()
        image.save(stream)
        stream.seek(0)
        return send_file(stream, mimetype="image/svg+xml")

    @app.post("/api/open-folder")
    def open_folder():
        local_only()
        if os.name == "nt":
            os.startfile(engine.music)
        else:
            raise AppError(f"Tus archivos están en: {engine.music}")
        return jsonify(ok=True)

    @app.post("/api/shutdown")
    def shutdown():
        local_only()
        if stop_event:
            timer = threading.Timer(.5, stop_event.set)
            timer.daemon = True
            timer.start()
        return jsonify(ok=True)

    return app
