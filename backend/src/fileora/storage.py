from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version(version INTEGER NOT NULL);
INSERT INTO schema_version SELECT 1 WHERE NOT EXISTS(SELECT 1 FROM schema_version);
CREATE TABLE IF NOT EXISTS roots(
 id INTEGER PRIMARY KEY, path TEXT NOT NULL UNIQUE, exclusions TEXT NOT NULL DEFAULT '[]',
 enabled INTEGER NOT NULL DEFAULT 1, status TEXT NOT NULL DEFAULT 'ready', last_scan TEXT);
CREATE TABLE IF NOT EXISTS files(
 id INTEGER PRIMARY KEY AUTOINCREMENT, root_id INTEGER NOT NULL REFERENCES roots(id) ON DELETE CASCADE,
 path TEXT NOT NULL, path_key TEXT NOT NULL UNIQUE, relative_path TEXT NOT NULL,
 name TEXT NOT NULL, extension TEXT NOT NULL, modality TEXT NOT NULL,
 size INTEGER NOT NULL, mtime_ns INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
 active_revision_id INTEGER, error_code TEXT, UNIQUE(root_id,relative_path));
CREATE TABLE IF NOT EXISTS file_revisions(
 id INTEGER PRIMARY KEY AUTOINCREMENT, file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
 sha256 TEXT NOT NULL, pipeline_hash TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 state TEXT NOT NULL DEFAULT 'ready', warnings TEXT NOT NULL DEFAULT '[]');
CREATE TABLE IF NOT EXISTS chunks(
 id INTEGER PRIMARY KEY AUTOINCREMENT, revision_id INTEGER NOT NULL REFERENCES file_revisions(id) ON DELETE CASCADE,
 ordinal INTEGER NOT NULL, kind TEXT NOT NULL, text TEXT NOT NULL, text_hash TEXT NOT NULL,
 locator TEXT NOT NULL, symbol TEXT NOT NULL DEFAULT '', asset TEXT,
 UNIQUE(revision_id,ordinal));
CREATE TABLE IF NOT EXISTS embedding_profiles(
 id TEXT PRIMARY KEY, model TEXT NOT NULL, revision TEXT NOT NULL, dimension INTEGER NOT NULL,
 config TEXT NOT NULL, modality TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS embeddings(
 id INTEGER PRIMARY KEY AUTOINCREMENT, chunk_id INTEGER NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
 profile_id TEXT NOT NULL REFERENCES embedding_profiles(id), input_hash TEXT NOT NULL,
 vector BLOB NOT NULL, UNIQUE(chunk_id,profile_id));
CREATE INDEX IF NOT EXISTS embedding_cache ON embeddings(profile_id,input_hash);
CREATE TABLE IF NOT EXISTS index_state(
 profile_id TEXT PRIMARY KEY REFERENCES embedding_profiles(id), generation INTEGER NOT NULL DEFAULT 0,
 snapshot_generation INTEGER NOT NULL DEFAULT -1, snapshot TEXT, checksum TEXT);
CREATE TABLE IF NOT EXISTS jobs(
 id TEXT PRIMARY KEY, state TEXT NOT NULL, verify INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, started_at TEXT, finished_at TEXT,
 processed INTEGER NOT NULL DEFAULT 0, indexed INTEGER NOT NULL DEFAULT 0,
 skipped INTEGER NOT NULL DEFAULT 0, failed INTEGER NOT NULL DEFAULT 0,
 deleted INTEGER NOT NULL DEFAULT 0, cancel INTEGER NOT NULL DEFAULT 0, total INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS job_errors(
 id INTEGER PRIMARY KEY, job_id TEXT REFERENCES jobs(id) ON DELETE CASCADE,
 file_id INTEGER REFERENCES files(id) ON DELETE SET NULL, relative_path TEXT NOT NULL,
 code TEXT NOT NULL, message TEXT NOT NULL);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(text,name,path,symbol, tokenize='unicode61');
CREATE INDEX IF NOT EXISTS file_root_status ON files(root_id,status);
CREATE INDEX IF NOT EXISTS chunk_revision ON chunks(revision_id);
CREATE INDEX IF NOT EXISTS revision_content ON file_revisions(sha256,pipeline_hash);
CREATE TABLE IF NOT EXISTS app_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
INSERT OR IGNORE INTO app_meta VALUES('generation','0');
"""


class Store:
    def __init__(self, directory: Path):
        self.path = directory / "catalog.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript(SCHEMA)
            version = db.execute("SELECT version FROM schema_version").fetchone()[0]
            if version != 1:
                raise RuntimeError("Unsupported catalog schema; use a compatible Fileora release")

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA journal_mode=WAL")
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def rows(self, sql: str, args: tuple = ()) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute(sql, args)]

    def one(self, sql: str, args: tuple = ()) -> dict | None:
        rows = self.rows(sql, args)
        return rows[0] if rows else None

    def execute(self, sql: str, args: tuple = ()) -> None:
        with self.connect() as db:
            db.execute(sql, args)

    @staticmethod
    def changed(db: sqlite3.Connection) -> None:
        db.execute("UPDATE app_meta SET value=CAST(value AS INTEGER)+1 WHERE key='generation'")
        db.execute("UPDATE index_state SET generation=generation+1")

    def status(self) -> dict:
        with self.connect() as db:
            return {
                "files": db.execute("SELECT count(*) FROM files WHERE status='ready'").fetchone()[
                    0
                ],
                "chunks": db.execute(
                    "SELECT count(*) FROM chunks c JOIN files f ON c.revision_id=f.active_revision_id WHERE f.status='ready'"
                ).fetchone()[0],
                "embeddings": db.execute("SELECT count(*) FROM embeddings").fetchone()[0],
                "generation": int(
                    db.execute("SELECT value FROM app_meta WHERE key='generation'").fetchone()[0]
                ),
                "roots": [dict(r) for r in db.execute("SELECT * FROM roots")],
                "failures": [
                    dict(r)
                    for r in db.execute(
                        "SELECT id,name,status,error_code FROM files WHERE status IN ('failed','stale')"
                    )
                ],
                "modalities": [
                    dict(r)
                    for r in db.execute(
                        "SELECT modality,count(*) AS count FROM files WHERE status='ready' GROUP BY modality"
                    )
                ],
                "profiles": [
                    dict(r)
                    for r in db.execute(
                        "SELECT id,model,revision,dimension,modality FROM embedding_profiles"
                    )
                ],
            }


def json_dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
