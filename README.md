# GoogleUnlimited

> **Zero-Quota, Unlimited Google Photos Auto-Sync for Windows, macOS & Linux**  
> Native background watcher that automatically uploads photos and videos with **Google Pixel original quality unlimited backup** — without WSL, WSA, Android emulators, or Morphe crashes.

<p align="center">
  <img src="reddit_showcase.jpg" alt="GoogleUnlimited Showcase" width="100%" />
</p>

---

## Features

- **Unlimited Google Photos Backup**: Spoofs Google Pixel mobile upload API ([`xob0t/gotohp`](https://github.com/xob0t/gotohp)) so all uploaded photos and videos consume **0 bytes of Google Drive / Google One storage**.
- **Cross-Platform (Windows, macOS & Linux)**:
  - **Windows**: Native PowerShell engine with bundled portable `PSSQLite`.
  - **macOS**: Native Bash + `fswatch` engine supporting both Apple Silicon (M1-M4) and Intel Macs via universal binary.
  - **Linux**: Native POSIX Bash + `inotify-tools` engine for all major distributions (Ubuntu, Debian, Fedora, Arch).
- **Multi-OS Interoperability**: Windows, macOS, and Linux scripts share the exact same SQLite database schema (`gphotos.db`), with dual-key lookups (`path` + `filename|filesize`) to seamlessly prevent duplicate uploads on shared or external partitions.
- **Unified Clean Architecture (Zero Clutter)**:
  - **Windows**: `GoogleUnlimited.bat` provides an interactive menu or CLI commands (`watch`, `silent`, `status`, `logs`, `enable`, `disable`, `stop`).
  - **macOS & Linux**: `google-unlimited.sh` unified runner (`watch`, `status`, `logs`, `setup`, `enable`, `disable`, `stop`). Zero separate script clutter.
- **Real-Time Auto-Sync**: Monitors standard user folders instantly when files are downloaded or saved, with debounce protection for active downloads.
- **Embedded SQLite Tracking**: Tracks every upload in `gphotos.db` — zero duplicate re-uploads, crash-resilient with automatic retry queues.
- **Live Terminal Progress Bar**: Real-time dynamic progress bar, elapsed timer, and file size indicator.
- **Background Auto-Start**: 
  - **Windows**: 1-click startup installer or silent VBScript launcher (`StartPhotosWatcher.vbs`).
  - **macOS**: Native `launchd` LaunchAgent (`./google-unlimited.sh enable`).
  - **Linux**: Native user `systemd` service (`./google-unlimited.sh enable`).
- **Security Hardened**: Automatically locks credentials (`gotohp.config`) and database (`gphotos.db`) to `chmod 600` (owner-only), sanitizes all database queries, and handles macOS Gatekeeper quarantine flags.

---

## Directory Structure

```text
GoogleUnlimited/
│
├── Modules/
│   └── PSSQLite/             # Bundled portable SQLite engine for Windows PowerShell
│
├── gotohp-cli-x64.exe        # Windows 64-bit CLI uploader with Pixel spoofing
├── gotohp-x64.exe            # Windows desktop GUI for one-click Google OAuth sign-in
├── gotohp-cli_amd64          # Native Linux x86_64 ELF binary
│
│   # --- Windows ---
├── GoogleUnlimited.bat       # Unified Windows Manager (interactive menu + CLI commands)
├── StartPhotosWatcher.vbs    # Windows silent background launcher (zero window)
├── WatchAndUpload.ps1        # Core Windows PowerShell orchestrator
│
│   # --- macOS & Linux ---
├── google-unlimited.sh       # Unified Unix Manager (macOS & Linux runner, setup, status, startup)
│
├── .gitattributes            # Line ending preservation (LF on shell scripts & plists, CRLF on bat/ps1)
├── .gitignore                # Protects credentials, tokens, and personal databases
├── README.md                 # Documentation
└── reddit_showcase.jpg       # Showcase graphic
```

---

## Windows Setup & Usage

### 1. Download or Clone
```cmd
git clone https://github.com/shishir0x/GoogleUnlimited.git
```

### 2. Sign In to Google Photos (One-Time)
1. Double-click **`gotohp-x64.exe`** and click **Add Google account**.
2. Click **Open Google sign-in** and sign in with your Google account.
3. Sign in on the Google Embedded Setup page and click **I agree**.  
   *(Note: The page buffering indefinitely is completely normal and expected).*
4. Open browser Developer Tools (**F12**):
   - Go to **Application** tab (Chrome/Edge/Brave) or **Storage** tab (Firefox).
   - Under **Cookies**, click `https://accounts.google.com`.
   - Copy the value of the **`oauth_token`** cookie.
5. In `gotohp`, paste the token and click **Connect account**.
6. Once connected, your credentials are saved locally. Close the GUI.

### 3. Run on Windows
Double-click **`GoogleUnlimited.bat`** to open the interactive manager:
```text
==========================================================
  *  Google Unlimited Photos Auto-Sync (Windows)
==========================================================
  [1] Start Live Watcher (Interactive progress)
  [2] Start Background Watcher (Silent, zero window)
  [3] Check Backup Status
  [4] View Activity Logs
  [5] Enable Auto-Start on Windows Boot
  [6] Disable Auto-Start on Windows Boot
  [7] Stop Background Watcher
  [8] Manage Watched Folders (Custom dirs / watch_dirs.txt)
  [9] Manage Google Accounts (Switch or add accounts)
  [10] Force Re-scan & Sync All Media (Safety sweep)
  [0] Exit
==========================================================
```

You can also run any action directly from the terminal or shortcuts:
```cmd
GoogleUnlimited.bat watch                 # Live terminal watcher with progress bar
GoogleUnlimited.bat silent                # Silent background run (zero window)
GoogleUnlimited.bat status                # Check total uploads and retry queue
GoogleUnlimited.bat logs                  # View last 30 sync activity logs
GoogleUnlimited.bat dirs                  # Open and manage custom watch folders
GoogleUnlimited.bat account               # View or switch active Google account
GoogleUnlimited.bat resync                # Force re-scan and sync all existing media
GoogleUnlimited.bat enable                # Enable auto-start on Windows boot
GoogleUnlimited.bat disable               # Disable auto-start on Windows boot
GoogleUnlimited.bat stop                  # Stop any running background watcher
```

---

## macOS Setup & Usage

GoogleUnlimited runs natively on macOS (Apple Silicon M1/M2/M3/M4 & Intel) using `fswatch`, `sqlite3`, and the official universal Mach-O binary.

### 1. Clone the Repository
```bash
git clone https://github.com/shishir0x/GoogleUnlimited.git
cd GoogleUnlimited
```

### 2. One-Command Setup
Make executable and run setup (auto-installs `fswatch` via Homebrew and downloads the universal binary):
```bash
chmod +x google-unlimited.sh
./google-unlimited.sh setup
```
*(If Homebrew is not installed, install it with: `/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"`)*

### 3. Sign In (One-Time)
1. Open the Google Embedded Setup sign-in page:  
   👉 **[https://accounts.google.com/embedded/setup/v2/android](https://accounts.google.com/embedded/setup/v2/android)**
2. Sign in with your Google account and click **I agree** *(buffering indefinitely is normal)*.
3. Press **Option + Command + I** (or right-click → **Inspect**) to open Developer Tools:
   - Go to **Application** tab → **Cookies** → `https://accounts.google.com`.
   - Copy the value of the **`oauth_token`** cookie.
4. In your terminal, run:
   ```bash
   ./google-unlimited.sh creds add
   ```
   *(When prompted, paste your `oauth_token`. Input is hidden for security so your token is never exposed in shell history or process listings).*

*(Alternatively: If you already signed in on Windows or Linux, simply copy `gotohp.config` into this directory).*

### 4. Run on macOS
Run `./google-unlimited.sh` to launch the interactive manager or pass commands directly:
```bash
./google-unlimited.sh watch      # Live interactive watcher with progress
./google-unlimited.sh enable     # Auto-start on macOS login via launchd
./google-unlimited.sh disable    # Disable macOS launchd auto-start
./google-unlimited.sh status     # View total uploads and pending retries
./google-unlimited.sh logs       # View recent activity logs
./google-unlimited.sh stop       # Stop background watcher instances
```

---

## Linux Setup & Usage

GoogleUnlimited runs natively on any Linux distribution (Ubuntu, Debian, Fedora, Arch Linux, openSUSE, etc.) using `inotify-tools`, `sqlite3`, and the native Linux `gotohp` binary.

### 1. Clone the Repository
```bash
git clone https://github.com/shishir0x/GoogleUnlimited.git
cd GoogleUnlimited
```

### 2. One-Command Setup
Run setup to auto-install dependencies (`inotify-tools`, `sqlite3`, `curl`):
```bash
chmod +x google-unlimited.sh
./google-unlimited.sh setup
```

### 3. Sign In (One-Time)

#### Option A: Retrieve `oauth_token` via Browser
1. In any web browser, open the Google Embedded Setup sign-in page:  
   👉 **[https://accounts.google.com/embedded/setup/v2/android](https://accounts.google.com/embedded/setup/v2/android)**
2. Sign in with your Google account and click **I agree**.  
   *(The screen may stay loading/buffering indefinitely; this is expected).*
3. Press **F12** (or right-click → **Inspect**) to open browser Developer Tools:
   - Click the **Application** tab (Chrome / Brave / Edge) or **Storage** tab (Firefox).
   - In the left sidebar, expand **Cookies** → click `https://accounts.google.com`.
   - Find the cookie named **`oauth_token`** and copy its full value.
4. In your Linux terminal, run:
   ```bash
   ./google-unlimited.sh creds add "<oauth_token>"
   ```
5. Verify your active account:
   ```bash
   ./google-unlimited.sh creds list
   ```

#### Option B: Copy from Windows / macOS (Fastest for Dual-Boot / Shared Drives)
If you already signed in on another OS:
Simply copy the generated `gotohp.config` file into your Linux project directory:
```bash
cp /path/to/GoogleUnlimited/gotohp.config ~/GoogleUnlimited/
```
The Linux watcher will detect `gotohp.config` and authenticate automatically.

### 4. Run on Linux
Run `./google-unlimited.sh` in your terminal to open the interactive manager:
```text
==========================================================
  *  GoogleUnlimited - Unix Manager (Linux)
==========================================================
  [1] Start Live Watcher (Foreground)
  [2] Check Backup Status
  [3] View Activity Logs
  [4] Run Setup & Dependency Installer
  [5] Enable Auto-Start on Boot (Linux systemd)
  [6] Disable Auto-Start on Boot
  [7] Stop Background Watcher
  [0] Exit
==========================================================
```

Or pass any command directly:
```bash
./google-unlimited.sh watch      # Interactive terminal with live progress
./google-unlimited.sh enable     # Auto-start on boot via systemd user service
./google-unlimited.sh disable    # Disable systemd startup service
./google-unlimited.sh status     # View upload statistics and retry queue
./google-unlimited.sh logs       # View recent activity logs with colors
./google-unlimited.sh stop       # Terminate background watcher
```

---

## Monitored Folders & Cloud Storage

The watcher automatically detects standard user media folders, cloud sync folders, and custom user-specified directories across all operating systems:
- `Pictures` / `Photos`
- `Videos` / `Movies`
- `Downloads`
- `Desktop`
- `Documents`
- `Music`
- **Cloud Folders**:
  - **Google Drive**: `G:\`, `G:\My Drive`, `~/Google Drive`, `~/Google Photos`
  - **OneDrive**: `Pictures`, `Camera Roll`
  - **iCloud Photos**: `iCloud Photos\Photos`

### Custom Directories (`watch_dirs.txt`)
Need to watch external SSDs, SD cards, or custom folders?
1. Open or create `watch_dirs.txt` in the root repository folder (or select `[8] Manage Watched Folders` in `GoogleUnlimited.bat`).
2. Add one folder path per line (environment variables like `%USERPROFILE%` or `$HOME` are fully supported):
   ```text
   # Custom storage drives
   D:\CameraRoll
   E:\SonyA7IV_Raw
   %USERPROFILE%\Pictures\Lightroom
   ```
3. You can also specify directories directly on launch:
   ```cmd
   GoogleUnlimited.bat watch "D:\Photos" "E:\Videos"
   ```
   ```bash
   ./google-unlimited.sh watch /Volumes/ExternalSSD/Photos
   ```

### Supported Media Formats (37 Formats)
- **Standard Images**: `.jpg`, `.jpeg`, `.png`, `.heic`, `.heif`, `.webp`, `.gif`, `.bmp`, `.tiff`, `.tif`, `.jfif`, `.avif`
- **Camera RAW (DSLR & Mirrorless)**: `.dng`, `.cr2`, `.cr3` (Canon), `.nef` (Nikon), `.arw` (Sony), `.raw`, `.orf` (Olympus), `.rw2` (Panasonic), `.pef` (Pentax), `.srw` (Samsung), `.raf` (Fujifilm)
- **Videos**: `.mp4`, `.mov` (Apple QuickTime/iPhone), `.mkv`, `.avi`, `.m4v`, `.3gp`, `.3g2`, `.wmv`, `.webm`, `.flv`, `.mts`, `.m2ts`, `.ts`, `.mpg`

---

## Real-Time Detection & Safety Sweeps

- **Instant Real-Time Monitoring**:
  - **Windows**: Uses .NET `FileSystemWatcher` listening to `Created`, `Renamed`, and `Changed` events with buffer expansion (64 KB) and debouncing (1.5s window).
  - **macOS / Linux**: Uses `fswatch` or `inotifywait` with low-latency streaming event loops.
- **Full Historical Scan & Safety Sweep**:
  - Upon startup (Phase 1), every monitored folder is traversed to sync any previously existing media files.
  - Background safety sweeps run every 30 seconds to catch any files transferred while the watcher was paused or during offline camera imports.
- **Accurate Content-Hash Deduplication**:
  - Unlike naive filename/size matching, GoogleUnlimited verifies the SHA-256 hash against `gphotos.db`, ensuring no duplicate uploads while never discarding different photos that happen to share standard filenames (e.g., `IMG_0001.JPG`) and byte sizes.

---

## Privacy & Security

- **Strict Permission Hardening**:
  - `gotohp.config` (OAuth token) is strictly locked down to `chmod 600` (readable/writable only by the owner).
  - `gphotos.db` (upload history) is locked to `chmod 600`.
  - Binaries are locked to `chmod 700`.
  - macOS Gatekeeper quarantine attributes (`com.apple.quarantine`) are stripped during setup to ensure clean execution.
- **Input Sanitization**: All SQLite queries escape single quotes and validate numeric bounds to prevent SQL injection across all platforms.
- **Direct Connections Only**: Every API request and media upload connects directly from your machine to official Google Photos endpoints (`photoslibrary.googleapis.com`). No intermediate or third-party servers are involved.
- **Local Credentials**: Authentication tokens and config files stay strictly on your local machine.
- **Git Protection**: The `.gitignore` file excludes:
  - Database files (`gphotos.db`, `*.db`, `*.db-wal`, `*.db-shm`)
  - Personal config files and tokens (`gotohp.config`, `*.config`, `*.token`)
  - Log files and temporary cache
  Your personal file history and login tokens are **never** committed or pushed to Git.
- **Zero Telemetry**: No tracking, analytics, or external telemetry of any kind.

---

## Troubleshooting & Issues

If you encounter any bugs, unexpected behavior, or need help:
- Run `./google-unlimited.sh status` (macOS/Linux) or `GoogleUnlimited.bat status` (Windows) to check queue and database status.
- Run `./google-unlimited.sh logs` (macOS/Linux) or `GoogleUnlimited.bat logs` (Windows) to inspect error details.
- Please submit an issue on the GitHub repository:  
  👉 **[Report an Issue on GitHub](https://github.com/shishir0x/GoogleUnlimited/issues)**

---

## License & Credits

- Core Pixel upload engine powered by [`xob0t/gotohp`](https://github.com/xob0t/gotohp).
- Windows SQLite integration powered by `PSSQLite`.

