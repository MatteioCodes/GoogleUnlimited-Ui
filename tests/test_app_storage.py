import base64
import contextlib
import http.client
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dashboard import Dashboard, LocalServer, UserError
from backend_fixtures import seed_upload


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.resources = self.root / "installed resources"
        self.resources.mkdir()
        self.app = Dashboard(self.resources, data_dir=self.root / "profile")

    def tearDown(self):
        self.app.engine.stop()
        self.temporary.cleanup()

    def test_install_directory_and_user_data_stay_separate(self):
        photo = self.root / "photos"
        photo.mkdir()
        self.app.save_folders([str(photo)])
        self.app.save_preferences({"theme": "dark", "startup": True})
        self.app.store.bind_account("original@example.test")
        reopened = Dashboard(self.resources, data_dir=self.app.data_dir)
        self.assertEqual(reopened.folders(), [str(photo)])
        self.assertEqual(reopened.preferences()["theme"], "dark")
        self.assertEqual(reopened.store.bound_account(), "original@example.test")
        self.assertEqual(list(self.resources.iterdir()), [])
        with patch.object(self.app, "binary", return_value="bundled-engine"):
            self.assertEqual(self.app.cli(), ["bundled-engine", "--config", str(self.app.data_dir / "gotohp.config")])

    def test_account_switch_is_rolled_back_and_wrong_account_cannot_start(self):
        self.app.store.bind_account("original@example.test")
        self.app.account_cache = {"connected": True, "email": "original@example.test"}
        self.app.account_checked = float("inf")
        def result(args, **kwargs):
            return subprocess.CompletedProcess(args, 0, "* other@example.test\n", "")
        with patch.object(self.app, "cli", return_value=["fake"]), patch.object(self.app, "run", side_effect=result) as run:
            with self.assertRaisesRegex(UserError, "another Google account"):
                self.app.connect("private-test-token")
            self.assertIn(["fake", "creds", "set", "original@example.test"], [call.args[0] for call in run.call_args_list])
        photos = self.root / "photos"
        photos.mkdir()
        self.app.save_folders([str(photos)])
        with patch.object(self.app, "account", return_value={"connected": True, "email": "other@example.test"}):
            with self.assertRaisesRegex(UserError, "associated with this backup history"):
                self.app.start()
        self.assertFalse(self.app.running())

    def test_import_reads_committed_wal_and_preserves_original_database(self):
        source = self.root / "previous app"
        source.mkdir()
        with contextlib.closing(sqlite3.connect(source / "gphotos.db")) as old:
            old.execute("PRAGMA journal_mode=WAL")
            old.execute("CREATE TABLE uploads(path TEXT PRIMARY KEY, media_key TEXT, uploaded_at TEXT)")
            old.execute("INSERT INTO uploads VALUES ('/previous/photo.jpg','confirmed','2026-01-02 10:20:30')")
            old.commit()
            with patch.object(self.app, "account", return_value={"connected": False}):
                self.app.import_setup(str(source))
            self.assertEqual(old.execute("SELECT count(*) FROM uploads").fetchone()[0], 1)
        self.assertEqual(self.app.history()["uploaded"], 1)
        self.assertEqual(self.app.history()["uploads"][0]["path"], "/previous/photo.jpg")
        self.assertEqual(self.app.folders(), [])
        with self.assertRaisesRegex(UserError, "before connecting"):
            self.app.import_setup(str(source))

    def test_appearance_validation_does_not_overwrite_good_preferences(self):
        self.app.save_preferences({"theme": "dark"})
        for invalid in ({"theme": "arbitrary"}, {"startup": "true"}, {"sync_enabled": 1}):
            with self.assertRaises(UserError):
                self.app.save_preferences(invalid)
        self.assertEqual(self.app.preferences()["theme"], "dark")

    def test_media_access_is_limited_to_recorded_supported_files(self):
        photo = self.root / "recorded.jpg"
        photo.write_bytes(b"photo")
        unrecorded = self.root / "private.jpg"
        unrecorded.write_bytes(b"private")
        seed_upload(self.app.data_dir, photo)
        identify = lambda path: base64.urlsafe_b64encode(str(path).encode()).decode().rstrip("=")
        self.assertEqual(self.app.media_path(identify(photo)), photo)
        with self.assertRaises(UserError):
            self.app.media_path(identify(unrecorded))
        photo.unlink()
        with self.assertRaises(UserError):
            self.app.media_path(identify(photo))


class MediaHttpTests(unittest.TestCase):
    def test_media_requires_session_and_supports_bounded_ranges(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app = Dashboard(root)
            clip = root / "video.mp4"
            clip.write_bytes(b"0123456789")
            seed_upload(app.data_dir, clip)
            server = LocalServer(("127.0.0.1", 0), app)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            identifier = app.history()["uploads"][0]["id"]
            try:
                def request(headers):
                    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                    connection.request("GET", "/api/media?id=" + identifier, headers=headers)
                    response = connection.getresponse()
                    value = response.status, dict(response.getheaders()), response.read()
                    connection.close()
                    return value
                self.assertEqual(request({})[0], 403)
                status, headers, body = request({"Cookie": "app_session=" + server.token, "Range": "bytes=2-5"})
                self.assertEqual((status, body), (206, b"2345"))
                self.assertEqual(headers["Content-Range"], "bytes 2-5/10")
                self.assertIn("sandbox", headers["Content-Security-Policy"])
                self.assertIn("default-src 'none'", headers["Content-Security-Policy"])
                self.assertEqual(request({"X-App-Token": server.token, "Range": "bytes=-3"})[2], b"789")
                self.assertEqual(request({"X-App-Token": server.token, "Range": "bytes=50-60"})[0], 416)
                self.assertEqual(request({"X-App-Token": server.token, "Range": "bytes=1-2,4-5"})[0], 416)
            finally:
                server.shutdown()
                server.server_close()
                worker.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
