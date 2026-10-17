"""Lifecycle adapter for the native backend. No scanning, uploads or dedupe here."""
import base64
import contextlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import sqlite3
import subprocess
import threading
import time

ROOT = Path(__file__).resolve().parent
VIDEOS = {'.mp4', '.mov', '.mkv', '.avi', '.m4v', '.3gp', '.3g2', '.wmv', '.webm', '.mpg', '.mpeg', '.mts', '.m2ts', '.ts', '.flv', '.vob'}
BACKEND_ROOT = ROOT / 'backend' if (ROOT / 'backend').is_dir() else ROOT
# Presentation and preview filtering follow the backend's extension list.
_format_source = (BACKEND_ROOT / 'google-unlimited.sh').read_text(encoding='utf-8')
SUPPORTED = {'.' + ext for ext in re.search(r"MEDIA_EXT_REGEX='\^\(([^)]+)\)", _format_source)[1].split('|')}


class BackupError(Exception):
    pass


class Store:
    """UI account binding is separate from the script-owned backup database."""
    def __init__(self, directory):
        self.directory = Path(directory)
        self.path = self.directory / 'gphotos.db'
        self.metadata = self.directory / 'app-account.json'

    def bound_account(self):
        if self.metadata.exists():
            try:
                return json.loads(self.metadata.read_text(encoding='utf-8')).get('account')
            except (ValueError, OSError):
                raise BackupError('The saved account setting could not be read. Restore your app data or use another profile.') from None
        # Preserve account binding when upgrading a development build.
        if self.path.exists():
            with contextlib.suppress(sqlite3.Error):
                with contextlib.closing(sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True)) as db:
                    row = db.execute("SELECT value FROM app_metadata WHERE key='account'").fetchone()
                    if row:
                        return row[0]
        return None

    def bind_account(self, email):
        bound = self.bound_account()
        if bound and bound != email.casefold():
            raise BackupError('This backup history belongs to a different Google account. Reconnect the original account.')
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = self.metadata.with_suffix('.tmp')
        temporary.write_text(json.dumps({'account': email.casefold()}), encoding='utf-8')
        temporary.chmod(0o600)
        os.replace(temporary, self.metadata)


class ScriptBackend:
    def __init__(self, store, folders, command, account, backend_root=BACKEND_ROOT):
        self.store, self.folders, self.command, self.account = store, folders, command, account
        self.root = Path(backend_root)
        self.process = None
        self.thread = None
        self.phase = 'paused'
        self.current = None
        self.last_error = None
        self.scanned = 0
        self._lock = threading.RLock()
        self._ready = threading.Event()
        self._stopping = False

    @property
    def unavailable(self):
        return {folder for folder in self.folders() if not Path(folder).is_dir()}

    @property
    def running(self):
        return self.process is not None and self.process.poll() is None and not self._stopping

    def launch(self, action='watch'):
        command = self.command()
        # The app uses the backend's own portable config, folder list and DB.
        env = os.environ.copy()
        env.update(GOOGLE_UNLIMITED_DATA_DIR=str(self.store.directory), GOOGLE_UNLIMITED_ENGINE=command[0],
                   GOOGLE_UNLIMITED_ACCOUNT=self.account() or '', GOOGLE_UNLIMITED_APP_MODE='1')
        if os.name == 'nt':
            powershell = shutil.which('powershell.exe') or shutil.which('pwsh.exe')
            if not powershell:
                raise BackupError('Windows PowerShell is unavailable. Restore it before starting backup.')
            args = [powershell, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File',
                    str(self.root / 'WatchAndUpload.ps1'), '-AppMode', '-DataDir', str(self.store.directory),
                    '-EnginePath', command[0], '-Account', env['GOOGLE_UNLIMITED_ACCOUNT']]
            if action == 'retry':
                args.append('-RetryFailed')
        else:
            args = [shutil.which('bash') or '/bin/bash', str(self.root / 'google-unlimited.sh'), action]
            tools = self.root / 'tools'
            if tools.is_dir():
                env['PATH'] = str(tools / 'bin') + os.pathsep + env.get('PATH', '')
                env['LD_LIBRARY_PATH'] = str(tools / 'lib') + (os.pathsep + env['LD_LIBRARY_PATH'] if env.get('LD_LIBRARY_PATH') else '')
        return args, env

    def requirements(self):
        if os.name == 'nt':
            ready = bool((shutil.which('powershell.exe') or shutil.which('pwsh.exe')) and (self.root / 'WatchAndUpload.ps1').is_file() and (self.root / 'Modules/PSSQLite/PSSQLite.psd1').is_file())
        else:
            tools = self.root / 'tools'
            search = str(tools / 'bin') + os.pathsep + os.environ.get('PATH', '')
            ready = (self.root / 'google-unlimited.sh').is_file() and all(shutil.which(name, path=search) for name in ('bash', 'sqlite3', 'inotifywait', 'flock'))
        return {'name': 'Native backup script', 'ready': bool(ready), 'help': 'The backup script or its dependencies are missing. Reinstall the app; source users can run the backend setup command.'}

    def _read_events(self, child):
        for line in child.stdout:
            if not line.startswith('@@GoogleUnlimited:'):
                continue  # Terminal diagnostics never become frontend messages.
            try:
                _, phase, encoded = line.strip().split(':', 2)
                path = base64.b64decode(encoded, validate=True).decode('utf-8') if encoded else None
            except (ValueError, UnicodeError):
                continue
            if phase in {'scanning', 'settling', 'uploading', 'watching', 'paused'}:
                self.phase = phase
                self.current = {'path': path, 'name': Path(path).name, 'started_at': time.time()} if path else None
                if path:
                    self.scanned += 1
                if phase != 'paused':
                    self._ready.set()
            elif phase in {'locked', 'unavailable', 'error'}:
                self.last_error = {'locked': 'Backup is already running for this profile.',
                                   'unavailable': 'None of your selected folders are available. Reconnect the drive and try again.',
                                   'error': 'The file watcher stopped. Start backup again to resume.'}[phase]
        child.wait()
        if not self._stopping:
            self.phase = 'error'
            self.current = None
            self.last_error = self.last_error or 'The backup script stopped. Check your account and selected folders, then start backup again.'
        self._ready.set()

    def start(self):
        with self._lock:
            if self.running:
                return
            if self.thread:
                self.thread.join(timeout=1)
            self.store.bind_account(self.account())
            stop = self.store.directory / '.app-stop'
            stop.unlink(missing_ok=True)
            self.phase, self.current, self.last_error, self.scanned = 'starting', None, None, 0
            self._stopping = False
            self._ready.clear()
            args, env = self.launch()
            try:
                self.process = subprocess.Popen(args, env=env, cwd=self.store.directory, stdin=subprocess.DEVNULL,
                                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding='utf-8', errors='replace',
                                                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
                                                start_new_session=os.name != 'nt')
            except OSError:
                raise BackupError('The native backup script could not be started. Reinstall the app or check its dependencies.') from None
            self.thread = threading.Thread(target=self._read_events, args=(self.process,), daemon=True)
            self.thread.start()
            if not self._ready.wait(timeout=18) or not self.running or self.phase in {'error', 'paused'}:
                error = self.last_error or 'The backup script did not become ready. Check your account and backup folders.'
                self.stop()
                self.last_error = error
                raise BackupError(error)

    def stop(self):
        with self._lock:
            self._stopping = True
            child = self.process
            if child and child.poll() is None:
                if os.name == 'nt':
                    (self.store.directory / '.app-stop').touch()
                else:
                    with contextlib.suppress(ProcessLookupError):
                        os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=7)
                except subprocess.TimeoutExpired:
                    if os.name == 'nt':
                        subprocess.run(['taskkill', '/PID', str(child.pid), '/T', '/F'], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=10)
                    else:
                        with contextlib.suppress(ProcessLookupError):
                            os.killpg(child.pid, signal.SIGKILL)
                    child.wait(timeout=3)
            if self.thread:
                self.thread.join(timeout=2)
            if child and child.stdout:
                child.stdout.close()
            self.process = None
            self.phase, self.current = 'paused', None

    def retry(self):
        if not self.store.path.exists():
            return
        args, env = self.launch('retry')
        try:
            result = subprocess.run(args, env=env, cwd=self.store.directory, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL, timeout=30,
                                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        except (OSError, subprocess.TimeoutExpired):
            raise BackupError('The backend could not reset retries. Try again after pausing backup.') from None
        if result.returncode:
            raise BackupError('The backend could not reset retries. Check your account and try again.')
