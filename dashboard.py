#!/usr/bin/env python3
"""A dependency-free, loopback-only interface for the existing sync scripts."""

import argparse
import contextlib
import io
import json
import mimetypes
import os
import platform
import re
import secrets
import shutil
import signal
import sqlite3
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from script_backend import ScriptBackend, BackupError, Store, SUPPORTED, VIDEOS


ROOT = Path(__file__).resolve().parent
WINDOWS = os.name == "nt"
EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}")


class UserError(Exception):
    """An actionable error that can be shown without exposing credentials."""


class Dashboard:
    def __init__(self, root=ROOT, data_dir=None, engine_path=None, asset_dir=None, desktop=False):
        self.root = Path(root).resolve()
        self.data_dir = Path(data_dir).resolve() if data_dir else self.root
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.folders_file = self.data_dir / "watch_dirs.txt"
        self.db = self.data_dir / "gphotos.db"
        self.engine_path = engine_path
        self.asset_dir = Path(asset_dir) if asset_dir else ROOT / "ui"
        self.isolated_config = True
        self.desktop = desktop
        self.settings_file = self.data_dir / "app-settings.json"
        self.process = None
        self.lock = threading.RLock()
        self.account_cache = None
        self.account_checked = 0
        self.store = Store(self.data_dir)
        self.engine = ScriptBackend(self.store, self.folders, self.cli, lambda: self.account().get("email"))

    def preferences(self):
        defaults = {"theme": "system", "startup": False, "sync_enabled": False}
        if self.settings_file.exists():
            try:
                saved = json.loads(self.settings_file.read_text(encoding="utf-8"))
                if isinstance(saved, dict):
                    defaults.update({key: saved[key] for key in defaults if key in saved})
            except (OSError, ValueError):
                pass
        return defaults

    def save_preferences(self, changes):
        if not isinstance(changes, dict):
            raise UserError("Choose valid app settings.")
        values = self.preferences()
        if "theme" in changes:
            if changes["theme"] not in ("light", "dark", "system"):
                raise UserError("Choose light, dark, or system appearance.")
            values["theme"] = changes["theme"]
        for key in ("startup", "sync_enabled"):
            if key in changes:
                if type(changes[key]) is not bool:
                    raise UserError("Choose a valid setting.")
                values[key] = changes[key]
        temporary = self.settings_file.with_suffix(".tmp")
        temporary.write_text(json.dumps(values), encoding="utf-8")
        temporary.chmod(0o600)
        os.replace(temporary, self.settings_file)
        return {"message": "Settings saved.", "preferences": values}

    def binary(self):
        if self.engine_path:
            return str(self.engine_path) if Path(self.engine_path).is_file() else None
        if WINDOWS:
            names = ["gotohp-cli-x64.exe", "gotohp-cli.exe"]
        else:
            arch = "arm64" if platform.machine().lower() in ("arm64", "aarch64") else "amd64"
            names = ["gotohp-cli", "gotohp-cli_" + arch]
        for name in names:
            path = self.root / name
            if path.is_file():
                if not WINDOWS and not os.access(path, os.X_OK):
                    try:
                        path.chmod(path.stat().st_mode | 0o100)
                    except OSError:
                        continue
                return str(path)
        return shutil.which("gotohp-cli")

    def cli(self):
        binary = self.binary()
        if not binary:
            raise UserError("The upload engine is missing. Reinstall the app or run the backend setup command.")
        args = [binary]
        config = self.data_dir / "gotohp.config"
        if config.is_file() or self.isolated_config:
            args += ["--config", str(config)]
        return args

    def run(self, args, timeout=12, **kwargs):
        try:
            return subprocess.run(
                args, cwd=self.data_dir, text=True, encoding="utf-8", errors="replace",
                capture_output=True, timeout=timeout,
                creationflags=subprocess.CREATE_NO_WINDOW if WINDOWS else 0, **kwargs,
            )
        except subprocess.TimeoutExpired:
            raise UserError("That took too long. Check your connection and try again.") from None
        except OSError:
            raise UserError("Could not launch the required program. Check that the upload engine matches your operating system.") from None

    def account(self, refresh=False):
        with self.lock:
            if not refresh and self.account_cache is not None and time.monotonic() - self.account_checked < 15:
                return self.account_cache
            try:
                result = self.run(self.cli() + ["creds", "list"])
                active = next((line for line in result.stdout.splitlines() if "*" in line and EMAIL.search(line)), "")
                match = EMAIL.search(active)
                value = {"connected": bool(result.returncode == 0 and match), "email": match.group(0) if match else None,
                         "accounts_present": bool(EMAIL.search(result.stdout))}
                if result.returncode:
                    value["error"] = "Could not read your account. Open account setup and try connecting again."
            except UserError as exc:
                value = {"connected": False, "email": None, "error": str(exc)}
            self.account_cache = value
            self.account_checked = time.monotonic()
            return value

    def connect(self, token):
        if not isinstance(token, str) or not token.strip() or len(token) > 16000:
            raise UserError("Paste the oauth_token value from Google sign-in first.")
        if self.running():
            raise UserError("Stop syncing before connecting or changing your Google account.")
        previous = self.account()
        bound = self.store.bound_account()
        # stdin keeps the secret out of shell history, process arguments, and logs.
        result = self.run(self.cli() + ["creds", "add", "-"], input=token.strip() + "\n", timeout=90)
        if result.returncode:
            raise UserError("Google could not connect this account. Copy a fresh oauth_token after signing in, then try again.")
        account = self.account(refresh=True)
        if not account["connected"]:
            raise UserError("No active account was found after sign-in. Try connecting again.")
        if bound and account["email"].casefold() != bound:
            if previous.get("email"):
                self.run(self.cli() + ["creds", "set", previous["email"]])
            self.account_cache = None
            raise UserError("This backup history belongs to another Google account. Reconnect the original account to keep its history.")
        self.store.bind_account(account["email"])
        config = self.data_dir / "gotohp.config"
        if config.exists():
            config.chmod(0o600)
        return {"message": "Google Photos connected.", "account": account}

    def folders(self):
        if not self.folders_file.exists():
            return []
        try:
            return list(dict.fromkeys(line for line in self.folders_file.read_text(encoding="utf-8-sig").splitlines() if line))
        except OSError:
            raise UserError("Could not read your folder settings. Check permissions in the app folder.") from None

    def save_folders(self, folders):
        if not isinstance(folders, list) or len(folders) > 64:
            raise UserError("Choose up to 64 folders to back up.")
        paths = []
        for folder in folders:
            if not isinstance(folder, str) or not folder.strip() or any(c in folder for c in "\r\n\0"):
                raise UserError("Choose a valid folder path.")
            path = Path(folder).expanduser()
            if not path.is_absolute():
                raise UserError("Enter a full folder path, or use Browse folders.")
            path = path.resolve()
            if not path.is_dir() or not os.access(path, os.R_OK | os.X_OK):
                raise UserError("That folder is unavailable or cannot be read. Check the path and permissions.")
            if str(path) not in paths:
                paths.append(str(path))
        # Avoid duplicate scans when a selected folder already includes another.
        selected = [p for p in paths if not any(p != other and Path(p).is_relative_to(Path(other)) for other in paths)]
        was_running = self.running()
        if was_running:
            self.engine.stop()
        try:
            temporary = self.folders_file.with_suffix(".tmp")
            temporary.write_text("".join(p + "\n" for p in selected), encoding="utf-8")
            temporary.chmod(0o600)
            os.replace(temporary, self.folders_file)
        finally:
            if was_running and self.folders():
                self.engine.start()
            elif was_running:
                self.save_preferences({"sync_enabled": False})
        return {"message": "Backup folders updated.", "folders": selected}

    def browse(self, requested=None):
        path = Path(requested).expanduser() if requested else Path.home()
        if not path.is_absolute():
            raise UserError("Enter a full folder path.")
        try:
            path = path.resolve(strict=True)
            children = sorted(
                ({"name": item.name, "path": str(item)} for item in path.iterdir()
                 if not item.name.startswith(".") and item.is_dir()),
                key=lambda item: item["name"].casefold(),
            )
        except (OSError, ValueError):
            raise UserError("This folder is unavailable. Choose another folder or check its permissions.") from None
        return {"path": str(path), "parent": str(path.parent), "home": str(Path.home()), "folders": children[:500], "truncated": len(children) > 500}

    def suggestions(self):
        paths = [Path.home() / name for name in ("Pictures", "Videos", "Downloads", "Desktop", "Documents")]
        if WINDOWS:
            with contextlib.suppress(OSError, ImportError):
                import winreg
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as key:
                    for name in ("My Pictures", "My Video", "{374DE290-123F-4565-9164-39C4925E467B}", "Desktop", "Personal"):
                        with contextlib.suppress(OSError):
                            paths.append(Path(os.path.expandvars(winreg.QueryValueEx(key, name)[0])))
        else:
            xdg = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "user-dirs.dirs"
            if xdg.is_file():
                for match in re.finditer(r'^XDG_(?:PICTURES|VIDEOS|DOWNLOAD|DESKTOP|DOCUMENTS)_DIR="([^"\n]+)"', xdg.read_text(), re.M):
                    paths.append(Path(match.group(1).replace("$HOME", str(Path.home()))))
        return [{"name": Path(p).name, "path": p} for p in dict.fromkeys(str(p) for p in paths if p.is_dir())]

    def running(self):
        return self.engine.running

    def requirements(self):
        return [
            {"name": "Upload engine", "ready": bool(self.binary()), "help": "The upload engine is missing. Reinstall the app to restore it."},
            {"name": "Backup database", "ready": os.access(self.data_dir, os.W_OK), "help": "The app data folder is not writable. Check its permissions."},
            self.engine.requirements(),
        ]

    def ready(self):
        account = self.account(refresh=True)
        if not account["connected"]:
            raise UserError("Connect your Google Photos account first.")
        if not self.folders():
            raise UserError("Choose at least one folder to back up first.")
        bound = self.store.bound_account()
        if bound and account["email"].casefold() != bound:
            raise UserError("Reconnect the Google account associated with this backup history.")
        missing = [item for item in self.requirements() if not item["ready"]]
        if missing:
            raise UserError(missing[0]["help"])

    def start(self):
        if self.running():
            return {"message": "Backup is already running."}
        self.ready()
        self.engine.start()
        self.save_preferences({"sync_enabled": True})
        return {"message": "Backup started. Checking your selected folders."}

    def stop(self):
        self.engine.stop()
        self.save_preferences({"sync_enabled": False})
        return {"message": "Backup paused. Your progress is saved."}

    def startup(self, enabled):
        if not self.desktop:
            raise UserError("Open the installed desktop app to manage automatic startup.")
        return self.save_preferences({"startup": enabled})

    def retry(self):
        if self.running():
            self.engine.stop()
        self.engine.retry()
        self.start()
        return {"message": "Waiting and failed files will be retried."}

    def history(self, search="", page=1, kind="all"):
        empty = {"uploaded": 0, "verified": 0, "legacy": 0, "today": 0, "pending": 0, "uploads": [], "retries": [], "logs": [], "total": 0, "page": page}
        if not self.db.exists():
            return empty
        try:
            # Read-only: the dashboard never creates or rewrites upload history.
            with contextlib.closing(sqlite3.connect(self.db.as_uri() + "?mode=ro", uri=True, timeout=3)) as conn:
                conn.row_factory = sqlite3.Row
                tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if "uploads" in tables:
                    empty["uploaded"] = conn.execute("SELECT count(*) FROM uploads").fetchone()[0]
                    columns = {row[1] for row in conn.execute("PRAGMA table_info(uploads)")}
                    confirmed = "media_key IS NOT NULL AND media_key != ''"
                    empty["verified"] = conn.execute("SELECT count(*) FROM uploads WHERE " + confirmed).fetchone()[0]
                    empty["legacy"] = empty["uploaded"] - empty["verified"]
                    empty["today"] = conn.execute("SELECT count(*) FROM uploads WHERE " + confirmed + " AND uploaded_at >= date('now','localtime')").fetchone()[0]
                    clauses, params = [], []
                    if search:
                        clauses.append("instr(lower(path), lower(?)) > 0")
                        params.append(search[:300])
                    videos = " OR ".join("lower(path) GLOB '*" + ext + "'" for ext in sorted(VIDEOS))
                    if kind in ("photos", "videos"):
                        clauses.append(("NOT " if kind == "photos" else "") + "(" + videos + ")")
                    where = " WHERE " + " AND ".join(clauses) if clauses else ""
                    empty["total"] = conn.execute("SELECT count(*) FROM uploads" + where, params).fetchone()[0]
                    size = "file_size" if "file_size" in columns else "size" if "size" in columns else "NULL"
                    empty["uploads"] = [dict(row) for row in conn.execute("SELECT path, uploaded_at, " + size + " AS size, CASE WHEN " + confirmed + " THEN 'native-script' END AS confirmation FROM uploads" + where + " ORDER BY uploaded_at DESC, path LIMIT 25 OFFSET ?", params + [(page - 1) * 25])]
                    import base64
                    for row in empty["uploads"]:
                        row["id"] = base64.urlsafe_b64encode(row["path"].encode()).decode().rstrip("=")
                if "retry_queue" in tables:
                    empty["pending"] = conn.execute("SELECT count(*) FROM retry_queue").fetchone()[0]
                    empty["retries"] = [dict(row) for row in conn.execute("SELECT path, attempts, last_attempt, CASE WHEN attempts >= 3 THEN 'failed' WHEN attempts > 0 THEN 'retrying' ELSE 'waiting' END AS state, NULL AS error, NULL AS size FROM retry_queue ORDER BY last_attempt DESC LIMIT 100")]
                if "logs" in tables:
                    empty["logs"] = [dict(row) for row in conn.execute("SELECT timestamp, level, message FROM logs ORDER BY id DESC LIMIT 100")]
        except sqlite3.Error:
            empty["error"] = "Upload history is temporarily unavailable. If syncing is running, try refreshing in a moment."
        return empty

    def status(self):
        history = self.history()
        folders = self.folders()
        return {
            "formats": sorted(ext[1:].upper() for ext in SUPPORTED),
            "account": self.account(), "running": self.running(), "desktop": self.desktop,
            "folders": [{"path": p, "name": Path(p).name or p, "available": Path(p).is_dir() and p not in self.engine.unavailable} for p in folders],
            "requirements": self.requirements(), "suggestions": self.suggestions(),
            "startup": {"available": self.desktop, "enabled": self.preferences()["startup"]},
            "preferences": self.preferences(),
            "platform": "Windows" if WINDOWS else "Linux" if sys.platform.startswith("linux") else platform.system(),
            "stats": {k: history[k] for k in ("uploaded", "verified", "legacy", "today", "pending")},
            "recent": history["uploads"][:8], "retries": history["retries"], "logs": history["logs"],
            "history_error": history.get("error"),
            "backup": {"phase": self.engine.phase, "current": self.engine.current, "error": self.engine.last_error,
                       "scanned": self.engine.scanned, "unavailable": list(self.engine.unavailable)},
        }

    def media_path(self, identifier):
        import base64
        try:
            if len(identifier) > 12000:
                raise ValueError()
            path = base64.urlsafe_b64decode(identifier + "=" * (-len(identifier) % 4)).decode("utf-8")
        except (ValueError, UnicodeError):
            raise UserError("This preview is unavailable.") from None
        if not self.db.exists():
            raise UserError("This preview is unavailable.")
        with contextlib.closing(sqlite3.connect(self.db.as_uri() + "?mode=ro", uri=True)) as db:
            known = db.execute("SELECT path FROM uploads WHERE path=? UNION SELECT path FROM retry_queue WHERE path=?", (path, path)).fetchone()
        resolved = Path(path)
        if not known or resolved.suffix.casefold() not in SUPPORTED or not resolved.is_file() or resolved.resolve() != resolved:
            raise UserError("The original file is unavailable on this computer.")
        return resolved

    def import_setup(self, folder):
        if self.running():
            raise UserError("Pause backup before importing a previous setup.")
        if not isinstance(folder, str):
            raise UserError("Choose your previous GoogleUnlimited folder.")
        source = Path(folder).resolve()
        incoming = source / "gphotos.db"
        if not incoming.is_file() or source == self.data_dir:
            raise UserError("Choose a different app folder containing gphotos.db.")
        if self.history()["uploaded"] or self.store.bound_account() or self.account().get("accounts_present"):
            raise UserError("Import is available before connecting an account or backing up files in this installation.")
        temporary = self.data_dir / "import.db.tmp"
        try:
            with contextlib.closing(sqlite3.connect(incoming.as_uri() + "?mode=ro", uri=True)) as old:
                columns = {row[1] for row in old.execute("PRAGMA table_info(uploads)")}
                if not {"path", "uploaded_at", "media_key"} <= columns:
                    raise UserError("That database is not a compatible GoogleUnlimited backup history.")
                with contextlib.closing(sqlite3.connect(temporary)) as new:
                    old.backup(new)
            if (source / "gotohp.config").is_file():
                shutil.copyfile(source / "gotohp.config", self.data_dir / "gotohp.config")
                (self.data_dir / "gotohp.config").chmod(0o600)
            # No worker or writer is active; remove empty destination WAL sidecars.
            for suffix in ("-wal", "-shm"):
                with contextlib.suppress(FileNotFoundError):
                    Path(str(self.db) + suffix).unlink()
            os.replace(temporary, self.db)
            self.store = Store(self.data_dir)
            self.engine.store = self.store
            self.account_cache = None
            return {"message": "Backup history imported. Choose the folders to watch on this computer."}
        except sqlite3.Error:
            raise UserError("Could not import that history. The original setup has been left in place.") from None
        finally:
            with contextlib.suppress(FileNotFoundError):
                temporary.unlink()


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, app):
        self.app = app
        self.token = secrets.token_urlsafe(32)
        super().__init__(address, Handler)
        port = self.server_port
        self.hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        self.origins = {"http://" + host for host in self.hosts}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass  # No URLs, account information, tokens, or request bodies in logs.

    def respond(self, status, body, content_type="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if content_type.startswith("text/html"):
            self.send_header("Set-Cookie", f"app_session={self.server.token}; HttpOnly; SameSite=Strict; Path=/")
        self.end_headers()
        with contextlib.suppress(BrokenPipeError, ConnectionResetError):
            self.wfile.write(body)

    def guard(self, api=False):
        if self.headers.get("Host") not in self.server.hosts:
            self.respond(403, {"error": "Open the dashboard using its localhost address."})
            return False
        origin = self.headers.get("Origin")
        if origin and origin not in self.server.origins:
            self.respond(403, {"error": "This request must come from the local dashboard."})
            return False
        from http.cookies import SimpleCookie
        cookies = SimpleCookie()
        with contextlib.suppress(Exception):
            cookies.load(self.headers.get("Cookie", ""))
        supplied = self.headers.get("X-App-Token", "") or (cookies["app_session"].value if "app_session" in cookies else "")
        if api and not secrets.compare_digest(supplied.encode(), self.server.token.encode()):
            self.respond(403, {"error": "Refresh the dashboard to reconnect."})
            return False
        return True

    def do_GET(self):
        url = urlsplit(self.path)
        if not self.guard(api=url.path.startswith("/api/")):
            return
        query = parse_qs(url.query)
        try:
            if url.path == "/api/status":
                return self.respond(200, self.server.app.status())
            if url.path == "/api/browse":
                return self.respond(200, self.server.app.browse(query.get("path", [None])[0]))
            if url.path == "/api/media-check":
                self.server.app.media_path(query.get("id", [""])[0])
                return self.respond(200, {"available": True})
            if url.path == "/api/media":
                path = self.server.app.media_path(query.get("id", [""])[0])
                if query.get("thumbnail", [""])[0] == "1":
                    try:
                        from PIL import Image, ImageOps, UnidentifiedImageError
                    except ImportError:
                        return self.respond(404, {"error": "Image previews are unavailable in this runtime."})
                    try:
                        import warnings
                        with warnings.catch_warnings():
                            warnings.simplefilter("error", Image.DecompressionBombWarning)
                            with Image.open(path) as image:
                                image = ImageOps.exif_transpose(image)
                                image.thumbnail((520, 520))
                                output = io.BytesIO()
                                image.convert("RGB").save(output, "JPEG", quality=82)
                        return self.respond(200, output.getvalue(), "image/jpeg")
                    except (OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
                        return self.respond(404, {"error": "Preview unavailable for this file format."})
                return self.stream_media(path)
            if url.path == "/api/history":
                try:
                    page = max(1, min(1000000, int(query.get("page", ["1"])[0])))
                except ValueError:
                    raise UserError("Choose a valid history page.") from None
                return self.respond(200, self.server.app.history(query.get("search", [""])[0], page, query.get("kind", ["all"])[0]))
            assets = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"), "/styles.css": ("styles.css", "text/css; charset=utf-8"), "/favicon.svg": ("favicon.svg", "image/svg+xml")}
            if url.path not in assets:
                return self.respond(404, {"error": "Page not found."})
            name, content_type = assets[url.path]
            body = (self.server.app.asset_dir / name).read_bytes()
            if name == "index.html":
                body = body.replace(b"__APP_TOKEN__", self.server.token.encode())
            self.respond(200, body, content_type)
        except (UserError, BackupError) as exc:
            self.respond(400, {"error": str(exc)})
        except (OSError, ValueError, sqlite3.Error):
            self.respond(500, {"error": "Could not read the local app data. Check the app folder permissions."})

    def do_POST(self):
        if not self.guard(api=True):
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > 65536:
                return self.respond(413, {"error": "This request is too large."})
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                return self.respond(415, {"error": "Send a JSON request."})
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise UserError("Send a valid request.")
            with self.server.app.lock:
                actions = {
                    "/api/account": lambda: self.server.app.connect(body.get("token")),
                    "/api/folders": lambda: self.server.app.save_folders(body.get("folders")),
                    "/api/sync/start": self.server.app.start,
                    "/api/sync/stop": self.server.app.stop,
                    "/api/startup": lambda: self.server.app.startup(body.get("enabled")),
                    "/api/preferences": lambda: self.server.app.save_preferences(body),
                    "/api/retry": self.server.app.retry,
                    "/api/import": lambda: self.server.app.import_setup(body.get("folder")),
                }
                action = actions.get(urlsplit(self.path).path)
                if not action:
                    return self.respond(404, {"error": "Action not found."})
                self.respond(200, action())
        except (ValueError, UnicodeError):
            self.respond(400, {"error": "The request could not be read. Refresh and try again."})
        except (UserError, BackupError) as exc:
            self.respond(400, {"error": str(exc)})
        except (OSError, sqlite3.Error):
            self.respond(500, {"error": "Could not save the change. Check the app folder permissions."})

    def stream_media(self, path):
        size = path.stat().st_size
        start, end, status = 0, size - 1, 200
        requested = self.headers.get("Range")
        if requested:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", requested)
            if not match or not any(match.groups()):
                return self.respond(416, {"error": "Invalid media range."})
            first, last = match.groups()
            if first:
                start, end = int(first), min(int(last), end) if last else end
            else:
                start = max(0, size - int(last))
            if start > end or start >= size:
                return self.respond(416, {"error": "Media range unavailable."})
            status = 206
        self.send_response(status)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(max(0, end - start + 1)))
        self.send_header("Content-Security-Policy", "default-src 'none'; sandbox")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with path.open("rb") as source, contextlib.suppress(BrokenPipeError, ConnectionResetError):
            source.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                chunk = source.read(min(65536, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)


def main():
    if sys.version_info < (3, 11):
        print("Source mode needs Python 3.11 or newer. The desktop installer includes its own runtime.", flush=True)
        return 1
    parser = argparse.ArgumentParser(description="GoogleUnlimited backup service")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--desktop", action="store_true")
    parser.add_argument("--data-dir")
    parser.add_argument("--engine")
    parser.add_argument("--asset-dir")
    args = parser.parse_args()
    app = Dashboard(data_dir=args.data_dir, engine_path=args.engine, asset_dir=args.asset_dir, desktop=args.desktop)
    try:
        server = LocalServer(("127.0.0.1", args.port), app)
    except OSError:
        print(f"Port {args.port} is in use. Reopen the existing app or choose --port 8766.", flush=True)
        return 1
    stopped = threading.Event()
    for name in ("SIGINT", "SIGTERM"):
        signal.signal(getattr(signal, name), lambda *_: stopped.set())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    address = f"http://127.0.0.1:{server.server_port}"
    if args.desktop:
        print(json.dumps({"ready": True, "port": server.server_port}), flush=True)
        def watch_parent():
            # Electron owns this pipe. EOF means it quit or crashed, on either OS.
            sys.stdin.buffer.read()
            stopped.set()
        threading.Thread(target=watch_parent, daemon=True).start()
        if app.preferences()["sync_enabled"]:
            try:
                app.start()
            except (UserError, BackupError, OSError, sqlite3.Error):
                app.engine.last_error = "Automatic backup could not resume. Check your account and backup folders."
    else:
        print(f"GoogleUnlimited is ready: {address}", flush=True)
        print("Keep this service running to back up files. The desktop app manages it automatically.", flush=True)
        if not args.no_browser:
            threading.Timer(0.3, webbrowser.open, args=(address,)).start()
    try:
        stopped.wait()
    finally:
        app.engine.stop()
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
    return 0


if __name__ == "__main__":
    sys.exit(main())
