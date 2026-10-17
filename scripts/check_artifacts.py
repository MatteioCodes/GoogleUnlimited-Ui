"""Validate installer payloads and write checksums without uploading a release."""
import hashlib
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
files = sorted(path for path in (root / "dist").iterdir() if path.suffix in {".exe", ".deb", ".AppImage"} and "uninstaller" not in path.name)
if not files:
    raise SystemExit("No installer artifacts found. Run npm run dist first.")
lines = []
for path in files:
    if path.stat().st_size < 30 * 1024 * 1024:
        raise SystemExit(f"{path.name} is too small to contain the app and runtime.")
    if path.suffix == ".exe":
        with path.open("rb") as source:
            if source.read(2) != b"MZ":
                raise SystemExit(f"{path.name} is not a Windows executable.")
    if path.suffix == ".deb" and sys.platform.startswith("linux"):
        result = subprocess.run(["dpkg-deb", "--contents", str(path)], capture_output=True, text=True, check=True)
        if "resources/service/python/bin/python3" not in result.stdout or "resources/upload/gotohp-cli" not in result.stdout:
            raise SystemExit("The Debian package is missing a required runtime component.")
    with path.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    lines.append(f"{digest}  {path.name}")
    print(f"Verified {path.name} ({path.stat().st_size / 1048576:.1f} MB)")
(root / "dist/SHA256SUMS.txt").write_text("\n".join(lines) + "\n")
