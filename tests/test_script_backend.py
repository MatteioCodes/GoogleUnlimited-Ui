"""Exercise the UI adapter against the real Bash backend and SQLite tools."""
import contextlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dashboard import Dashboard
from script_backend import BackupError, SUPPORTED
from backend_fixtures import seed_upload

TOOLS = Path(__file__).resolve().parents[1] / 'build/runtime/linux/backend/tools'

@unittest.skipIf(os.name == 'nt', 'Real Bash integration; native PowerShell regression tests run on Windows')
class NativeBackendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='native-backend-')
        self.root = Path(self.temp.name)
        self.profile = self.root / 'profile with spaces'
        self.profile.mkdir()
        self.photos = self.root / "Family's photos 📷"
        self.photos.mkdir()
        self.other = self.root / 'private'
        self.other.mkdir()
        self.uploader = self.root / 'gotohp-cli'
        self.uploader.write_text(f'#!{sys.executable}\n' + '''import json,sys,time
from pathlib import Path
args=sys.argv[1:]
if args[0]=='--config': args=args[2:]
if args[:2]==['creds','list']: print('* local@example.test')
elif args[0]=='upload':
 with Path('calls.jsonl').open('a') as f: f.write(json.dumps(args)+'\\n')
 if Path('slow').exists(): time.sleep(120)
 if Path('fail').exists(): print(json.dumps({'results':[{'success':False,'error':'simulated connection failure'}]}))
 else: print(json.dumps({'results':[{'path':args[-1],'success':True,'mediaKey':'test-key'}]}))
else: sys.exit(1)
''')
        self.uploader.chmod(0o700)
        self.environment = patch.dict(os.environ, {'PATH': str(TOOLS / 'bin') + os.pathsep + os.environ['PATH'], 'LD_LIBRARY_PATH': str(TOOLS / 'lib')})
        self.environment.start()
        if not all(shutil.which(name) for name in ('sqlite3','inotifywait','flock')):
            self.environment.stop()
            self.temp.cleanup()
            self.skipTest('Install sqlite3, inotify-tools and util-linux, or run npm run prepare:linux')
        self.app = Dashboard(data_dir=self.profile, engine_path=self.uploader)
        self.app.save_folders([str(self.photos)])

    def tearDown(self):
        self.app.engine.stop()
        self.environment.stop()
        self.temp.cleanup()

    def wait_for(self, predicate, timeout=12):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            if predicate(): return
            time.sleep(.05)
        self.fail('Timed out: ' + str(self.app.engine.last_error))

    def calls(self):
        file=self.profile/'calls.jsonl'
        return [json.loads(line) for line in file.read_text().splitlines()] if file.exists() else []

    def test_real_script_uploads_then_watches_new_files_and_resumes_without_duplicates(self):
        photo=self.photos/'a memory.AVIF'; photo.write_bytes(b'first photo')
        (self.other/'private.jpg').write_bytes(b'not selected')
        self.app.start()
        process=self.app.engine.process
        self.app.start()
        self.assertIs(self.app.engine.process,process)
        self.wait_for(lambda:self.app.history()['uploaded']==1 and self.app.engine.phase=='watching')
        (self.photos/'a new clip.webm').write_bytes(b'new video')
        self.wait_for(lambda:self.app.history()['uploaded']==2)
        self.app.stop()
        self.assertFalse(self.app.running())
        self.app.start()
        self.wait_for(lambda:self.app.engine.phase=='watching')
        self.assertEqual(len(self.calls()),2)
        self.assertEqual(self.app.history(kind='videos')['total'],1)
        self.assertIn('.avif',SUPPORTED)
        self.assertIn('watch_dirs.txt',str(self.app.folders_file))
        for args in self.calls():
            self.assertIn('--account',args)
            self.assertIn('local@example.test',args)
            self.assertNotIn('--force',args)
        with sqlite3.connect(self.app.db) as db:
            columns={row[1] for row in db.execute('PRAGMA table_info(uploads)')}
            self.assertIn('content_hash',columns)
            self.assertNotIn('confirmation',columns)  # No parallel Python engine schema.

    def test_retry_control_is_executed_by_backend_and_removed_folders_cannot_upload(self):
        photo=self.photos/'retry.jpg';photo.write_bytes(b'photo')
        (self.profile/'fail').touch()
        self.app.start()
        self.wait_for(lambda:self.app.engine.phase=='watching' and self.app.history()['pending']==1)
        self.assertEqual(self.app.history()['uploaded'],0)
        self.app.stop()
        (self.profile/'fail').unlink()
        self.app.retry()
        self.wait_for(lambda:self.app.history()['uploaded']==1)
        self.app.stop()
        self.app.save_folders([str(self.other)])
        missing=self.photos/'not selected.jpg';missing.write_bytes(b'private')
        with sqlite3.connect(self.app.db) as db:
            db.execute('INSERT INTO retry_queue(path,attempts) VALUES (?,1)',(str(missing),))
        self.app.start()
        self.wait_for(lambda:self.app.engine.phase=='watching')
        self.assertNotIn(str(missing),[row[-1] for row in self.calls()])

    def test_pausing_active_upload_terminates_entire_child_process_group(self):
        (self.photos/'long upload.mp4').write_bytes(b'video')
        (self.profile/'slow').touch()
        self.app.start()
        self.wait_for(lambda:len(self.calls())==1)
        child=self.app.engine.process
        start=time.monotonic()
        self.app.stop()
        self.assertLess(time.monotonic()-start,9)
        self.assertIsNotNone(child.poll())
        self.assertEqual(self.app.history()['uploaded'],0)
        # The native startup scan rediscovers the interrupted original.
        (self.profile/'slow').unlink()
        self.app.start()
        self.wait_for(lambda:self.app.history()['uploaded']==1)

    def test_native_single_instance_lock_blocks_a_second_adapter(self):
        self.app.start()
        second=Dashboard(data_dir=self.profile,engine_path=self.uploader)
        try:
            with self.assertRaisesRegex(BackupError,'already running'):
                second.start()
            self.assertTrue(self.app.running())
        finally:
            second.engine.stop()

    def test_history_reads_do_not_migrate_the_native_database(self):
        photo=self.photos/'saved.jpg';photo.write_bytes(b'photo')
        seed_upload(self.profile,photo)
        with sqlite3.connect(self.app.db) as db:
            original=list(db.execute('SELECT sql FROM sqlite_master ORDER BY name'))
        self.assertEqual(self.app.history()['verified'],1)
        with sqlite3.connect(self.app.db) as db:
            self.assertEqual(original,list(db.execute('SELECT sql FROM sqlite_master ORDER BY name')))

    def test_unavailable_selection_does_not_fall_back_to_home_folders(self):
        self.photos.rmdir()
        with self.assertRaisesRegex(BackupError,'selected folders'):
            self.app.start()
        self.assertEqual(self.calls(),[])


class WindowsBackendTests(NativeBackendTests):
    __unittest_skip__ = os.name != 'nt'
    __unittest_skip_why__ = 'Requires native Windows PowerShell and bundled PSSQLite'

    def setUp(self):
        import subprocess
        self.temp = tempfile.TemporaryDirectory(prefix='native-backend-')
        self.root = Path(self.temp.name)
        self.profile = self.root / 'profile with spaces'
        self.profile.mkdir()
        self.photos = self.root / "Family's photos 📷"
        self.photos.mkdir()
        self.other = self.root / 'private'
        self.other.mkdir()
        source = self.root / 'uploader.cs'
        source.write_text(r'''
using System;
using System.IO;
using System.Text;
using System.Threading;
using System.Web.Script.Serialization;
class FixtureUploader {
    static int Main(string[] args) {
        int index = args.Length > 0 && args[0] == "--config" ? 2 : 0;
        if (args[index] == "creds") {
            if (args[index + 1] == "list") Console.WriteLine("* local@example.test");
            return 0;
        }
        if (args[index] == "upload") {
            File.AppendAllText("calls.jsonl", new JavaScriptSerializer().Serialize(args) + "\n", new UTF8Encoding(false));
            if (File.Exists("slow")) Thread.Sleep(120000);
            Console.WriteLine(File.Exists("fail") ? "{\"success\":false,\"error\":\"simulated connection failure\"}" : "{\"success\":true,\"mediaKey\":\"test-key\"}");
            return 0;
        }
        return 1;
    }
}
''', encoding='utf-8')
        self.uploader = self.root / 'gotohp-cli.exe'
        self.environment = patch.dict(os.environ, {'GU_FIXTURE_SOURCE': str(source), 'GU_FIXTURE_EXE': str(self.uploader)})
        self.environment.start()
        try:
            subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
                'Add-Type -TypeDefinition ([IO.File]::ReadAllText($env:GU_FIXTURE_SOURCE)) -ReferencedAssemblies System.Web.Extensions -OutputAssembly $env:GU_FIXTURE_EXE -OutputType ConsoleApplication'], check=True, capture_output=True)
            self.app = Dashboard(data_dir=self.profile, engine_path=self.uploader)
            self.app.save_folders([str(self.photos)])
        except BaseException:
            self.environment.stop()
            self.temp.cleanup()
            raise
