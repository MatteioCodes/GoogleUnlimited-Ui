"""Run an installed backend with its bundled Python; no account or uploads."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import tempfile
import urllib.request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("resources", type=Path)
    args = parser.parse_args()
    resources = args.resources.resolve()
    windows = (resources / "service/python.exe").exists()
    python = resources / ("service/python.exe" if windows else "service/python/bin/python3")
    engine = resources / ("upload/gotohp-cli.exe" if windows else "upload/gotohp-cli")
    subprocess.run([str(python), "-c", "import sqlite3; from PIL import Image; print('Bundled Python, SQLite and Pillow ready.')"], check=True)
    subprocess.run([str(engine), "version"], check=True)
    with tempfile.TemporaryDirectory(prefix="googleunlimited-installed-") as directory:
        process = subprocess.Popen([str(python), "-u", str(resources / "service/dashboard.py"), "--desktop", "--no-browser", "--port", "0", "--data-dir", directory, "--asset-dir", str(resources / "ui"), "--engine", str(engine)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            line = process.stdout.readline()
            if not line:
                raise RuntimeError("Installed backup service did not start: " + process.stderr.read()[-1500:])
            ready = json.loads(line)
            url = f"http://127.0.0.1:{ready['port']}"
            page = urllib.request.urlopen(url, timeout=10).read().decode()
            token = re.search(r'name="app-token"\s+content="([^"]+)"', page).group(1)
            request = urllib.request.Request(url + "/api/status", headers={"X-App-Token": token})
            status = json.load(urllib.request.urlopen(request, timeout=15))
            assert status["account"]["connected"] is False
            assert all(item["ready"] for item in status["requirements"]), status["requirements"]
            assert status["desktop"] is True
            print("Installed service, assets, isolated profile and bundled upload engine verified.")
        finally:
            process.stdin.close()
            try:
                process.wait(timeout=12)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            assert process.returncode == 0, "Installed service did not shut down cleanly."


if __name__ == "__main__":
    main()
