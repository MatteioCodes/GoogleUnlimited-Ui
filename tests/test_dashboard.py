import contextlib
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dashboard import Dashboard, LocalServer, ROOT, UserError


SCHEMA = """
CREATE TABLE uploads (path TEXT PRIMARY KEY, media_key TEXT, uploaded_at TEXT DEFAULT (datetime('now','localtime')));
CREATE TABLE retry_queue (path TEXT PRIMARY KEY, attempts INTEGER DEFAULT 0, last_attempt TEXT);
CREATE TABLE logs (id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT DEFAULT (datetime('now','localtime')), level TEXT, message TEXT);
"""


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="googleunlimited-test-")
        self.root = Path(self.temp.name)
        self.app = Dashboard(self.root)

    def tearDown(self):
        self.temp.cleanup()

    def test_first_launch_is_empty_and_does_not_create_database(self):
        self.assertEqual(self.app.history()["uploaded"], 0)
        self.assertEqual(self.app.folders(), [])
        self.assertFalse(self.app.db.exists())
        self.assertFalse(self.app.account()["connected"])
        with self.assertRaisesRegex(UserError, "Connect your Google"):
            self.app.start()

    def test_folder_selection_roundtrips_unicode_and_normalizes_nested_folders(self):
        folder = self.root / "Family's photos 📷"
        nested = folder / "summer"
        nested.mkdir(parents=True)
        result = self.app.save_folders([str(nested), str(folder), str(folder)])
        self.assertEqual(result["folders"], [str(folder)])
        self.assertEqual(Dashboard(self.root).folders(), [str(folder)])
        self.app.save_folders([])
        self.assertTrue(self.app.folders_file.exists())
        self.assertEqual(self.app.folders_file.read_text(), "")

    def test_invalid_folder_preserves_choices_and_live_changes_pause_safely(self):
        folder = self.root / "Photos"
        folder.mkdir()
        self.app.save_folders([str(folder)])
        for invalid in ["relative/folder", str(self.root / "missing"), str(folder) + "\n/other"]:
            with self.assertRaises(UserError):
                self.app.save_folders([invalid])
        self.assertEqual(self.app.folders(), [str(folder)])
        with patch.object(self.app, "running", return_value=True), patch.object(self.app.engine, "stop") as stop:
            self.app.save_folders([])
            stop.assert_called_once()
        self.assertEqual(self.app.folders(), [])

    def test_browser_lists_directories_without_reading_files(self):
        (self.root / "Photos").mkdir()
        (self.root / ".hidden").mkdir()
        (self.root / "private.txt").write_text("not served")
        listing = self.app.browse(str(self.root))
        self.assertEqual([row["name"] for row in listing["folders"]], ["Photos"])
        with self.assertRaises(UserError):
            self.app.browse(str(self.root / "private.txt"))

    def test_real_sqlite_history_supports_literal_search_filters_and_pagination(self):
        with sqlite3.connect(self.app.db) as conn:
            conn.executescript(SCHEMA)
            conn.executemany("INSERT INTO uploads(path) VALUES (?)", [(f"/photos/photo-{i:02}.jpg",) for i in range(30)])
            conn.executemany("INSERT INTO uploads(path) VALUES (?)", [("/photos/film.MP4",), ("/photos/100%_sun's.jpg",)])
            conn.execute("INSERT INTO retry_queue(path,attempts) VALUES('/photos/retry.mov',2)")
            conn.execute("INSERT INTO logs(level,message) VALUES('WARN','Network unavailable')")
        history = self.app.history()
        self.assertEqual((history["uploaded"], history["pending"], len(history["uploads"])), (32, 1, 25))
        self.assertEqual(len(self.app.history(page=2)["uploads"]), 7)
        self.assertEqual(self.app.history(kind="videos")["total"], 1)
        self.assertEqual(self.app.history(kind="photos")["total"], 31)
        self.assertEqual(self.app.history(search="100%_sun's")["total"], 1)
        self.assertEqual(self.app.history(search="' OR 1=1 --")["total"], 0)
        self.assertEqual(history["logs"][0]["message"], "Network unavailable")

    def test_corrupt_database_is_reported_without_overwriting_it(self):
        self.app.db.write_bytes(b"not a database")
        self.assertIn("error", self.app.history())
        self.assertEqual(self.app.db.read_bytes(), b"not a database")

    def test_account_secret_uses_stdin_and_is_never_returned_in_errors(self):
        secret = "private-token-never-in-argv"
        calls = []

        def fake_run(args, **kwargs):
            calls.append((args, kwargs))
            return subprocess.CompletedProcess(args, 0, "* person@example.test\n", "")

        with patch.object(self.app, "cli", return_value=["fake-gotohp"]), patch.object(self.app, "run", side_effect=fake_run):
            self.assertEqual(self.app.connect(secret)["account"]["email"], "person@example.test")
        addition = next(call for call in calls if call[0][-2:] == ["add", "-"])
        self.assertEqual(addition[0], ["fake-gotohp", "creds", "add", "-"])
        self.assertEqual(addition[1]["input"], secret + "\n")
        with patch.object(self.app, "cli", return_value=["fake-gotohp"]), patch.object(self.app, "run", return_value=subprocess.CompletedProcess([], 1, secret, secret)):
            with self.assertRaises(UserError) as error:
                self.app.connect(secret)
        self.assertNotIn(secret, str(error.exception))


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = Dashboard(Path(self.temp.name))
        self.server = LocalServer(("127.0.0.1", 0), self.app)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.temp.cleanup()

    def request(self, path, method="GET", body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        conn.request(method, path, body=body, headers=headers or {})
        response = conn.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        conn.close()
        return result

    def test_page_bootstrap_csp_and_protected_api(self):
        status, headers, html = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn(self.server.token.encode(), html)
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(self.request("/api/status")[0], 403)
        headers = {"X-App-Token": self.server.token}
        status, _, body = self.request("/api/status", headers=headers)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["stats"]["uploaded"], 0)

    def test_cross_origin_and_dns_rebinding_requests_are_rejected(self):
        self.assertEqual(self.request("/", headers={"Host": "attacker.example"})[0], 403)
        self.assertEqual(self.request("/api/status", headers={"Origin": "https://attacker.example", "X-App-Token": self.server.token})[0], 403)
        self.assertEqual(self.request("/api/folders", "POST", '{"folders":[]}', {"Content-Type": "application/json"})[0], 403)

    def test_http_folder_save_and_errors(self):
        folder = Path(self.temp.name) / "Personal photos"
        folder.mkdir()
        headers = {"X-App-Token": self.server.token, "Content-Type": "application/json"}
        status, _, _ = self.request("/api/folders", "POST", json.dumps({"folders": [str(folder)]}), headers)
        self.assertEqual(status, 200)
        self.assertEqual(self.app.folders(), [str(folder)])
        self.assertEqual(self.request("/api/folders", "POST", "not json", headers)[0], 400)
        self.assertEqual(self.request("/api/history?page=invalid", headers={"X-App-Token": self.server.token})[0], 400)
        self.assertEqual(self.request("/../dashboard.py")[0], 404)
        self.assertEqual(self.request("/gotohp.config")[0], 404)
