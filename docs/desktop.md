# GoogleUnlimited desktop

[Download installers](https://github.com/MatteioCodes/GoogleUnlimited-Ui/releases/latest).
The installer contains the app, CLI, and runtime; no developer tools are needed.
Windows 10/11 x64 uses Windows PowerShell 5.1. Linux x64 requires a desktop and
glibc 2.35+ (Ubuntu 22.04+ or Debian 12+). AppImage normally needs FUSE; alternatively
run it with `--appimage-extract-and-run`. The Windows installer is unsigned.

## First backup

1. Connect Google Photos with **Continue with Google**. A temporary sign-in window
   passes the `oauth_token` cookie directly to the upload CLI over standard input.
   Google may require the manual browser connection option offered in the dialog.
2. Choose your backup folders with the native folder picker. The installed app
   selects no personal folders by default.
3. Start backup. The backend scans those folders and watches for changes. Open
   Activity for the current file, retries, and the backend's saved events.

The library reads upload records from the backend's `gphotos.db` and previews
local originals. It does not fetch your entire remote Google Photos library.
Some RAW, HEIC, and video formats can upload without displaying a preview.
Use Google Photos to inspect remote copies.

Closing the window keeps the app in the tray where a tray is available. Quit
stops the script and its active upload. An active backup resumes on the next
launch; pausing keeps it paused. The computer must be awake for backup to run.
Reconnect a missing external drive and restart backup to restore its watcher.

Settings can import an existing `gphotos.db` and portable `gotohp.config` before
connecting an account in an empty profile. Stop the old watcher before importing.
The import uses SQLite's backup API, including committed WAL data, and retains
all original source files. Choose folders on the current computer after import.
The backend retains its existing history and duplicate-detection semantics.

## One backend

Electron owns the local HTTP/UI service in `dashboard.py`. `script_backend.py`
only manages the native script process, account binding, and status events.
Scanning, file readiness, SHA-256 hashing, duplicate detection, uploads, and retry
policy remain in the current repository backend scripts:

- Windows: `WatchAndUpload.ps1 -AppMode -DataDir <profile> -EnginePath <bundled CLI> -Account <email>`.
- Linux: `google-unlimited.sh watch`, with `GOOGLE_UNLIMITED_DATA_DIR`,
  `GOOGLE_UNLIMITED_ENGINE`, `GOOGLE_UNLIMITED_ACCOUNT`, and
  `GOOGLE_UNLIMITED_APP_MODE=1` supplied to the child process.

The backend writes `uploads`, `retry_queue`, and `logs` in `gphotos.db`.
The frontend reads those tables without migrating them or writing upload records.
Folder choices use the backend's `watch_dirs.txt`. App preferences and account
binding use separate JSON files. Installed profiles live in:

- Windows: `%APPDATA%\GoogleUnlimited`
- Linux: `$XDG_CONFIG_HOME/GoogleUnlimited`, normally `~/.config/GoogleUnlimited`

Backend status uses `@@GoogleUnlimited:<phase>:<base64 UTF-8 path>` on standard
output in app mode. Regular terminal output is discarded by the adapter. Windows
stops cooperatively through `.app-stop`; Linux owns a process group and signals
only that group. The native watcher owns the single-instance lock. Failed files
stay in the native retry table after three attempts so Activity can show them.
Retry now invokes the backend's `retry` / `-RetryFailed` action. The Linux event
loop serializes uploads with periodic retries and sweeps. Both scripts prevent
queued files outside selected folders from uploading.

The renderer has no Node access. The loopback service validates Host and Origin,
requires a session token, uses a strict CSP, and serves only known media paths.
Account cookies are not put in renderer storage, command arguments, or logs.
App resources contain no external UI assets or analytics. The UI uses original
code and artwork; Ente was used as a design reference. See
[third-party references](../third-party/README.md).

## Development and installers

Development uses Node.js 22+ and Python 3.11+. Linux source mode also needs Bash,
sqlite3, inotify-tools, and util-linux; the backend's `setup` command can install
its native dependencies. Windows source mode uses the repository PSSQLite module.

```sh
npm ci
python3 -m pip install -r requirements-dev.txt
npm start
# Browser-only development:
python3 dashboard.py --no-browser --port 8765
```

The standalone installers bundle checksum-pinned CPython, Pillow, the current
repository CLI binaries, both native script resources, and the platform's backend
dependencies. Linux build hosts need `dpkg-deb` to extract the pinned Ubuntu tools.
Their licenses and corresponding GPL source archives accompany the binary tools.
No dependencies are downloaded when using the installed app.

```sh
npm run dist:linux
npm run dist:win
python3 scripts/check_artifacts.py
```

Outputs are in `dist/`; SHA-256 checksums are in `dist/SHA256SUMS.txt`. On Linux,
the pinned electron-builder NSIS reader builds the Windows uninstaller without
Wine. Native Windows builds use the standard NSIS build path. Uninstalling keeps
the user-profile data and original photos.

## Verification

```sh
python3 -m unittest discover -s tests -v
bash tests/run_all_tests.sh
python3 tests/browser_smoke.py
xvfb-run -a npm run test:desktop
```

The adapter tests launch the actual native script, with a simulated CLI that
never contacts Google. They cover folder selection, broader formats, confirmed
history, real filesystem events, retries, resume, cancellation, schema ownership,
and native single-instance protection. Equivalent PowerShell integration runs on
Windows. The existing backend regression tests remain in place.

GitHub Actions checks both platforms, browser/native UI behavior on Linux, bundled
runtimes, and a real silent install/uninstall on Windows. Live Google sign-in and
uploads need a real account and are not exercised by automated fixture tests.
