"""Search and durable downloads. All external media is handled by yt-dlp."""
from __future__ import annotations

import contextlib
import ipaddress
import logging
import os
from pathlib import Path
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from uuid import uuid4

import imageio_ffmpeg
from mutagen.mp3 import MP3
from yt_dlp import YoutubeDL

LOG = logging.getLogger("tutuy")
ACTIVE = {"queued", "downloading", "converting"}


class AppError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class Cancelled(Exception):
    pass


def resource_dir() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))


def portable_dir() -> Path:
    return Path(sys.executable).parent if getattr(sys, "frozen", False) else resource_dir()


def validate_url(value: str) -> str:
    """Only public HTTP media URLs; never pass a yt-dlp expression from the client."""
    value = str(value).strip()
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise AppError("Pega un enlace público que empiece por https://.")
    try:
        port = parsed.port
    except ValueError as exc:
        raise AppError("El puerto del enlace no es válido.") from exc
    if len(value) > 3000 or port not in {None, 80, 443}:
        raise AppError("El enlace no es válido o utiliza un puerto no permitido.")
    if parsed.hostname.lower() in {"localhost", "localhost.localdomain"} or parsed.hostname.endswith(".local"):
        raise AppError("Usa un enlace de una plataforma pública.")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise AppError("No se pudo encontrar la plataforma. Revisa la conexión y el enlace.") from exc
    if not addresses or any(not ipaddress.ip_address(item[4][0].split("%")[0]).is_global for item in addresses):
        raise AppError("Solo se admiten enlaces de plataformas públicas.")
    return value


def friendly_error(exc: Exception) -> str:
    message = re.sub(r"\x1b\[[0-9;]*m", "", str(exc)).replace("ERROR: ", "")
    lower = message.lower()
    if any(s in lower for s in ("drm", "protected", "premium", "payment", "purchase")):
        return "Este contenido está protegido o requiere una compra. Prueba con un contenido autorizado y público."
    if any(s in lower for s in ("sign in", "login", "bot", "403", "429", "authentication", "cookies")):
        return "La plataforma ha bloqueado esta solicitud o requiere iniciar sesión. Prueba con otro enlace o más tarde."
    if any(s in lower for s in ("unavailable", "private video", "removed", "not available", "geo")):
        return "Este contenido no está disponible, es privado o tiene una restricción de región."
    if any(s in lower for s in ("timed out", "getaddrinfo", "network", "connection", "resolve")):
        return "Se perdió la conexión con la plataforma. Revisa Internet y vuelve a intentarlo."
    if "unsupported url" in lower:
        return "Esta plataforma o este tipo de enlace todavía no es compatible."
    if "requested format" in lower:
        return "La plataforma no ofrece un formato de audio accesible para este contenido."
    return message[:280] or "No se pudo completar la operación. Prueba con otro enlace."


class QuietLogger:
    def debug(self, message):
        if not message.startswith("[debug]"):
            LOG.debug(message)

    def warning(self, message):
        LOG.info(message)

    def error(self, message):
        LOG.warning(message)


class Engine:
    def __init__(self, directory: Path, workers: int = 2):
        self.directory = Path(directory).resolve()
        self.music = self.directory / "Musica"
        self.temp = self.directory / "temporales"
        self.music.mkdir(parents=True, exist_ok=True)
        self.temp.mkdir(parents=True, exist_ok=True)
        self.db = self.directory / "biblioteca.sqlite3"
        self.lock = threading.RLock()
        self.events: dict[str, threading.Event] = {}
        self.search_cache: dict[str, tuple[float, dict]] = {}
        self.search_lock = threading.Lock()
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="tutuy")
        self.closed = threading.Event()
        self.network_lock = threading.Lock()
        self._online = (0.0, False)
        self.ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        bundled_node = resource_dir() / "tools" / "node.exe"
        self.node = str(bundled_node) if bundled_node.exists() else shutil.which("node")
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, title TEXT, artist TEXT, url TEXT, thumbnail TEXT,
                duration REAL, platform TEXT, status TEXT, progress REAL DEFAULT 0,
                speed REAL DEFAULT 0, eta REAL DEFAULT 0, error TEXT DEFAULT '',
                filename TEXT DEFAULT '', quality INTEGER, created REAL, size INTEGER DEFAULT 0
            )""")
            db.execute("UPDATE jobs SET status='error', error='La app se cerró antes de terminar. Pulsa Reintentar.' WHERE status IN ('queued','downloading','converting')")
        # Temporary source files are never the user's completed MP3s.
        for child in self.temp.iterdir():
            if child.is_dir() and re.fullmatch(r"[a-f0-9]{32}", child.name):
                shutil.rmtree(child, ignore_errors=True)

    def connect(self):
        connection = sqlite3.connect(self.db, timeout=15)
        connection.row_factory = sqlite3.Row
        return _Database(connection)

    def internet(self, force=False) -> bool:
        with self.network_lock:
            checked, online = self._online
            if not force and time.monotonic() - checked < 12:
                return online
            online = False
            for url in ("https://www.gstatic.com/generate_204", "https://www.cloudflare.com/cdn-cgi/trace"):
                try:
                    request = Request(url, headers={"User-Agent": "Tutuy/1.0"})
                    with urlopen(request, timeout=3) as response:
                        if response.status in {200, 204}:
                            online = True
                            break
                except (OSError, ValueError):
                    continue
            self._online = (time.monotonic(), online)
            return online

    def ensure_online(self):
        if not self.internet(force=True):
            raise AppError("No hay conexión a Internet en el computador. Conéctalo e inténtalo de nuevo.", 503)

    def options(self) -> dict:
        options = {
            "quiet": True, "no_warnings": True, "logger": QuietLogger(),
            "socket_timeout": 15, "retries": 2, "fragment_retries": 2,
            "cachedir": False, "noplaylist": True, "nocheckcertificate": False,
            "js_runtimes": {"node": {"path": self.node}} if self.node else {},
            "ffmpeg_location": self.ffmpeg,
        }
        return options

    def search(self, query, mode="artist", provider="youtube", limit=20):
        query = str(query).strip()
        if not 2 <= len(query) <= 500:
            raise AppError("Escribe al menos 2 caracteres y un máximo de 500.")
        if mode not in {"artist", "genre", "url"} or provider not in {"youtube", "soundcloud"}:
            raise AppError("Selecciona un tipo de búsqueda y una plataforma válidos.")
        if limit not in {10, 20, 40}:
            raise AppError("Selecciona 10, 20 o 40 resultados.")
        self.ensure_online()
        expression = validate_url(query) if mode == "url" else f"{'sc' if provider == 'soundcloud' else 'yt'}search{limit}:{query + (' música' if mode == 'genre' else '')}"
        options = self.options() | {"extract_flat": "in_playlist", "playlistend": limit, "noplaylist": mode != "url", "skip_download": True, "ignoreerrors": mode != "url"}
        try:
            with YoutubeDL(options) as ydl:
                info = ydl.extract_info(expression, download=False)
                if not info:
                    raise AppError("No se encontraron resultados. Prueba otra búsqueda o un enlace directo.", 404)
                entries = list(info.get("entries") or [info])[:limit]
                songs = []
                for entry in entries:
                    if not entry or entry.get("is_live") or entry.get("live_status") == "is_live":
                        continue
                    url = entry.get("webpage_url") or entry.get("url")
                    if not url or not str(url).startswith(("http://", "https://")):
                        continue
                    thumbnails = entry.get("thumbnails") or []
                    thumbnail = entry.get("thumbnail") or (thumbnails[-1].get("url", "") if thumbnails else "")
                    if not str(thumbnail).startswith("https://"):
                        thumbnail = ""
                    identifier = uuid4().hex
                    song = {
                        "id": identifier, "title": str(entry.get("title") or "Audio sin título"),
                        "artist": str(entry.get("artist") or entry.get("uploader") or entry.get("channel") or "Artista desconocido"),
                        "url": url, "thumbnail": thumbnail, "duration": entry.get("duration") or 0,
                        "platform": "YouTube" if "youtu" in (urlparse(url).hostname or "").lower() else "SoundCloud" if "soundcloud" in url else str(entry.get("extractor_key") or "Enlace"),
                    }
                    songs.append(song)
                with self.lock:
                    now = time.monotonic()
                    self.search_cache = {k: v for k, v in self.search_cache.items() if now - v[0] < 3600}
                    if len(self.search_cache) > 2000:
                        self.search_cache.clear()
                    self.search_cache.update({song["id"]: (now, song) for song in songs})
                return songs
        except AppError:
            raise
        except Exception as exc:
            LOG.exception("Search failed")
            raise AppError(friendly_error(exc), 502) from exc

    def jobs(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM jobs ORDER BY created DESC LIMIT 500")]

    def get(self, identifier):
        with self.connect() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (identifier,)).fetchone()
        if not row:
            raise AppError("No se encontró esta descarga.", 404)
        return dict(row)

    def update(self, identifier, **values):
        allowed = {"status", "progress", "speed", "eta", "error", "filename", "size", "title", "artist", "duration"}
        if not values or not values.keys() <= allowed:
            raise ValueError("Invalid job update")
        with self.connect() as db:
            db.execute(f"UPDATE jobs SET {','.join(k+'=?' for k in values)} WHERE id=?", (*values.values(), identifier))

    def enqueue(self, ids, quality=192):
        if not isinstance(ids, list) or not 1 <= len(ids) <= 40 or any(not isinstance(i, str) for i in ids):
            raise AppError("Selecciona entre 1 y 40 canciones.")
        if quality not in {128, 192, 320}:
            raise AppError("La calidad debe ser 128, 192 o 320 kbps.")
        self.ensure_online()
        with self.lock:
            if self.closed.is_set():
                raise AppError("La aplicación se está cerrando.", 503)
            if sum(job["status"] in ACTIVE for job in self.jobs()) + len(ids) > 80:
                raise AppError("Hay demasiadas descargas pendientes. Espera a que terminen algunas.")
            songs = []
            for identifier in dict.fromkeys(ids):
                cached = self.search_cache.get(identifier)
                if not cached or time.monotonic() - cached[0] > 3600:
                    raise AppError("Esta búsqueda ha caducado. Busca de nuevo antes de descargar.", 409)
                songs.append(cached[1])
            return [self._submit(song, quality) for song in songs]

    def _submit(self, song, quality):
        identifier = uuid4().hex
        with self.connect() as db:
            db.execute("INSERT INTO jobs (id,title,artist,url,thumbnail,duration,platform,status,quality,created) VALUES (?,?,?,?,?,?,?,?,?,?)",
                       (identifier, song["title"], song["artist"], song["url"], song["thumbnail"], song["duration"], song["platform"], "queued", quality, time.time()))
        event = self.events[identifier] = threading.Event()
        self.pool.submit(self._run, identifier, event)
        return identifier

    def retry(self, identifier):
        job = self.get(identifier)
        if job["status"] not in {"error", "cancelled"}:
            raise AppError("Solo se pueden reintentar descargas fallidas o canceladas.")
        self.ensure_online()
        with self.lock:
            if self.closed.is_set() or sum(j["status"] in ACTIVE for j in self.jobs()) >= 80:
                raise AppError("Espera a que terminen algunas descargas antes de reintentar.")
            return self._submit(job, job["quality"])

    def cancel(self, identifier):
        with self.lock:
            job = self.get(identifier)
            if job["status"] not in ACTIVE:
                raise AppError("Esta descarga ya terminó.")
            event = self.events.get(identifier)
            if event:
                event.set()
            self.update(identifier, status="cancelled", speed=0, eta=0)

    def file(self, identifier):
        job = self.get(identifier)
        if job["status"] != "completed" or not job["filename"]:
            raise AppError("El MP3 todavía no está listo.", 409)
        path = (self.music / job["filename"]).resolve()
        if path.parent != self.music or not path.is_file():
            raise AppError("El archivo se movió o se eliminó de la carpeta Música.", 404)
        return path

    def _run(self, identifier, event):
        job_dir = self.temp / identifier
        process = None
        output = None
        try:
            if event.is_set():
                raise Cancelled()
            job = self.get(identifier)
            self.update(identifier, status="downloading")
            job_dir.mkdir(parents=True, exist_ok=True)
            last_update = [0.0]

            def progress(data):
                if event.is_set() or self.closed.is_set():
                    raise Cancelled()
                now = time.monotonic()
                if now - last_update[0] < .4 and data.get("status") != "finished":
                    return
                last_update[0] = now
                total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
                percent = min(84, data.get("downloaded_bytes", 0) / total * 84) if total else 0
                self.update(identifier, progress=percent, speed=data.get("speed") or 0, eta=data.get("eta") or 0)

            # Revalidate at execution time, including jobs restored from the database.
            validate_url(job["url"])
            options = self.options() | {
                "format": "bestaudio/best", "outtmpl": str(job_dir / "source.%(ext)s"),
                "progress_hooks": [progress], "overwrites": True,
                "max_filesize": 512 * 1024 * 1024, "restrictfilenames": True,
                "match_filter": lambda info, **_: "Las transmisiones en vivo no son compatibles." if info.get("is_live") else None,
            }
            with YoutubeDL(options) as ydl:
                info = ydl.extract_info(job["url"], download=True)
                if not info:
                    raise AppError("No fue posible descargar este contenido.")
                source = Path(ydl.prepare_filename(info))
                if not source.exists():
                    candidates = [p for p in job_dir.glob("source.*") if p.suffix not in {".part", ".ytdl"}]
                    if not candidates:
                        raise AppError("La plataforma no entregó un archivo de audio.")
                    source = candidates[0]
            if event.is_set() or self.closed.is_set():
                raise Cancelled()
            self.update(identifier, status="converting", progress=85, speed=0, eta=0)
            title = str(info.get("track") or info.get("title") or job["title"])
            artist = str(info.get("artist") or info.get("uploader") or job["artist"])
            safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", f"{artist} - {title}").strip(" .")[:130]
            filename = f"{safe_name or 'Audio'} [{identifier[:8]}].mp3"
            output = self.music / filename
            temporary = job_dir / "converted.mp3"
            command = [self.ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", str(source),
                       "-map", "0:a:0", "-vn", "-c:a", "libmp3lame", "-ar", "44100", "-b:a", f"{job['quality']}k",
                       "-id3v2_version", "3", "-metadata", f"title={title}", "-metadata", f"artist={artist}",
                       "-progress", "pipe:1", "-nostats", str(temporary)]
            flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            # Keep stderr on disk: avoids deadlock on a full stderr pipe.
            with (job_dir / "ffmpeg.log").open("wb") as errors:
                process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors, text=True, creationflags=flags)
                def stop_conversion():
                    while process.poll() is None:
                        if event.wait(.2) or self.closed.is_set():
                            with contextlib.suppress(OSError):
                                process.terminate()
                            return
                watcher = threading.Thread(target=stop_conversion, daemon=True)
                watcher.start()
                duration = float(info.get("duration") or job["duration"] or 0)
                for line in process.stdout:
                    if line.startswith("out_time_us=") and duration:
                        with contextlib.suppress(ValueError):
                            seconds = int(line.split("=", 1)[1]) / 1_000_000
                            if time.monotonic() - last_update[0] > .4:
                                self.update(identifier, progress=min(99, 85 + seconds / duration * 14))
                                last_update[0] = time.monotonic()
                process.stdout.close()
                return_code = process.wait()
            if event.is_set() or self.closed.is_set():
                raise Cancelled()
            if return_code != 0 or not temporary.is_file():
                LOG.error("FFmpeg failed: %s", (job_dir / "ffmpeg.log").read_text(errors="replace")[-3000:])
                raise AppError("No se pudo convertir el audio a MP3. Prueba con otro contenido.")
            if not duration:
                duration = MP3(temporary).info.length
            # Cancellation and final commit are serialized so a cancelled job never wins a race.
            with self.lock:
                if event.is_set() or self.closed.is_set():
                    raise Cancelled()
                temporary.replace(output)
                self.update(identifier, status="completed", progress=100, filename=filename,
                            title=title, artist=artist, duration=duration, size=output.stat().st_size, speed=0, eta=0)
        except Exception as exc:
            if event.is_set() or self.closed.is_set() or isinstance(exc, Cancelled):
                self.update(identifier, status="cancelled", speed=0, eta=0)
            else:
                LOG.exception("Download %s failed", identifier)
                self.update(identifier, status="error", error=friendly_error(exc), speed=0, eta=0)
        finally:
            if process and process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            shutil.rmtree(job_dir, ignore_errors=True)
            with self.lock:
                self.events.pop(identifier, None)

    def close(self):
        self.closed.set()
        with self.lock:
            for identifier, event in self.events.items():
                event.set()
                self.update(identifier, status="cancelled", speed=0, eta=0)
        self.pool.shutdown(wait=False, cancel_futures=True)


class _Database:
    """Commit transactions and always close sqlite connections."""
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self.connection

    def __exit__(self, kind, value, traceback):
        try:
            if kind:
                self.connection.rollback()
            else:
                self.connection.commit()
        finally:
            self.connection.close()
