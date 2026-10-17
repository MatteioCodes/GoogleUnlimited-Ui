"""Prepare standalone, checksum-pinned runtimes; nothing is downloaded at app runtime."""

import argparse
import gzip
import io
import os
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import urllib.parse
import urllib.request
import zipfile


ROOT = Path(__file__).resolve().parents[1]
LOCK = json.loads((ROOT / "scripts/runtime-lock.json").read_text())
CACHE = ROOT / "build/downloads"


def download(entry):
    CACHE.mkdir(parents=True, exist_ok=True)
    filename = CACHE / urllib.parse.unquote(entry["url"].rsplit("/", 1)[1])
    if not filename.exists() or hashlib.file_digest(filename.open("rb"), "sha256").hexdigest() != entry["sha256"]:
        print(f"Downloading {filename.name}", flush=True)
        request = urllib.request.Request(entry["url"], headers={"User-Agent": "GoogleUnlimited-build"})
        with urllib.request.urlopen(request, timeout=120) as response, filename.open("wb") as output:
            shutil.copyfileobj(response, output)
    with filename.open("rb") as data:
        actual = hashlib.file_digest(data, "sha256").hexdigest()
    if actual != entry["sha256"]:
        raise RuntimeError(f"Checksum mismatch for {filename.name}; refusing to package it.")
    return filename


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("platform", choices=["linux", "win"])
    args = parser.parse_args()
    target = ROOT / "build/runtime" / args.platform
    target.mkdir(parents=True, exist_ok=True)
    (target / "backup_engine.py").unlink(missing_ok=True)
    archive = download(LOCK[args.platform])
    if args.platform == "linux":
        if not (target / "python/bin/python3").exists():
            with tarfile.open(archive) as package:
                package.extractall(target, filter="data")
        site = target / "python/lib/python3.14/site-packages"
    else:
        if not (target / "python.exe").exists():
            with zipfile.ZipFile(archive) as package:
                package.extractall(target)
        site = target / "Lib/site-packages"
        (target / "python314._pth").write_text("python314.zip\n.\nLib/site-packages\nimport site\n")
    site.mkdir(parents=True, exist_ok=True)
    wheel = download(LOCK["pillowLinux" if args.platform == "linux" else "pillowWin"])
    with zipfile.ZipFile(wheel) as package:
        package.extractall(site)
    for filename in ("dashboard.py", "script_backend.py"):
        shutil.copyfile(ROOT / filename, target / filename)
    backend = target / "backend"
    backend.mkdir(parents=True, exist_ok=True)
    for name in ("google-unlimited.sh", "WatchAndUpload.ps1"):
        shutil.copyfile(ROOT / name, backend / name)
    if args.platform == "win":
        shutil.copytree(ROOT / "Modules/PSSQLite", backend / "Modules/PSSQLite", dirs_exist_ok=True)
    else:
        tools = backend / "tools"
        (tools / "bin").mkdir(parents=True, exist_ok=True)
        (tools / "lib").mkdir(exist_ok=True)
        # dpkg handles Ubuntu's zstd-compressed .deb data members.
        for name, entry in LOCK["linuxBackendTools"].items():
            archive = download(entry)
            payload = subprocess.run(["dpkg-deb", "--fsys-tarfile", str(archive)], capture_output=True, check=True).stdout
            with tarfile.open(fileobj=io.BytesIO(payload)) as package:
                for item in package:
                    path = Path(item.name)
                    if item.isfile() and path.parent == Path('usr/bin') and path.name in ('sqlite3', 'inotifywait'):
                        destination = tools / 'bin' / path.name
                    elif item.isfile() and str(path.parent) in ('usr/lib/x86_64-linux-gnu', 'lib/x86_64-linux-gnu') and '.so' in path.name:
                        destination = tools / 'lib' / path.name
                    elif item.issym() and '.so' in path.name and str(path.parent) in ('usr/lib/x86_64-linux-gnu', 'lib/x86_64-linux-gnu'):
                        destination = tools / 'lib' / path.name
                        destination.unlink(missing_ok=True)
                        destination.symlink_to(Path(item.linkname).name)
                        continue
                    elif item.isfile() and path.name == 'copyright':
                        destination = tools / 'licenses' / (name + '-copyright.txt')
                        destination.parent.mkdir(exist_ok=True)
                    else:
                        continue
                    with package.extractfile(item) as source, destination.open('wb') as output:
                        shutil.copyfileobj(source, output)
                    destination.chmod(0o755 if destination.parent.name == 'bin' else 0o644)
        sources = tools / 'sources'
        sources.mkdir(exist_ok=True)
        for entry in LOCK['linuxBackendSources']:
            archive = download(entry)
            shutil.copyfile(archive, sources / archive.name)
        for license in ('GPL-2', 'GPL-3', 'LGPL-2.1'):
            origin = Path('/usr/share/common-licenses') / license
            if origin.exists():
                shutil.copyfile(origin, tools / 'licenses' / (license + '.txt'))
        env = dict(os.environ, LD_LIBRARY_PATH=str(tools / 'lib'))
        subprocess.run([str(tools / 'bin/sqlite3'), '-version'], env=env, stdout=subprocess.DEVNULL, check=True)
        watcher = subprocess.run([str(tools / 'bin/inotifywait'), '--help'], env=env, capture_output=True)
        if b'inotifywait' not in watcher.stdout or watcher.returncode not in (0, 1):
            raise RuntimeError('Bundled inotifywait could not run.')
    if args.platform == "linux":
        subprocess.run([str(target / "python/bin/python3"), "-c", "import sqlite3; from PIL import Image; import dashboard; print('Standalone Linux runtime verified.')"], cwd=target, check=True)
    print(f"Prepared standalone {args.platform} runtime: {target}", flush=True)


if __name__ == "__main__":
    main()
