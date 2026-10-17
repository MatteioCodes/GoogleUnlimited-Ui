"""Test data in the native script schema, never a replacement backup engine."""
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS uploads(path TEXT PRIMARY KEY, media_key TEXT, uploaded_at TEXT DEFAULT (datetime('now','localtime')), file_name TEXT, file_size INTEGER, content_hash TEXT);
CREATE TABLE IF NOT EXISTS retry_queue(path TEXT PRIMARY KEY, attempts INTEGER DEFAULT 0, last_attempt TEXT);
CREATE TABLE IF NOT EXISTS logs(id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT DEFAULT (datetime('now','localtime')), level TEXT, message TEXT);
"""

def seed_upload(directory, path):
    directory.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(directory / 'gphotos.db') as db:
        db.executescript(SCHEMA)
        db.execute('INSERT INTO uploads(path,media_key,file_name,file_size) VALUES (?,?,?,?)', (str(path), 'fixture-key', path.name, path.stat().st_size))
