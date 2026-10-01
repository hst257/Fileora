from __future__ import annotations

import json
import sys
import threading
from io import BufferedRandom
from pathlib import Path

from fileora.config import Settings
from fileora.domain import FileoraError
from fileora.indexing import Indexer, VectorIndexes, is_link
from fileora.jobs import Worker
from fileora.models import Models
from fileora.retrieval import Search
from fileora.storage import Store


class InstanceLock:
    """One catalog owner across CLI/server processes, including Windows."""

    def __init__(self, path: Path):
        self.path = path
        self.stream: BufferedRandom | None = None

    def acquire(self):
        try:
            self.stream = self.path.open("a+b")
            self.stream.seek(0)
            if self.stream.read(1) == b"":
                self.stream.write(b"0")
                self.stream.flush()
            self.stream.seek(0)
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if self.stream:
                self.stream.close()
            self.stream = None
            raise FileoraError(
                "INSTANCE_RUNNING",
                "This catalog is in use. Use the running UI or stop the other Fileora process",
                409,
            ) from exc

    def release(self):
        if self.stream:
            if sys.platform == "win32":
                import msvcrt

                self.stream.seek(0)
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.stream.fileno(), fcntl.LOCK_UN)
            self.stream.close()
            self.stream = None


class Service:
    def __init__(self, settings: Settings, models=None, extractor=None):
        self.settings = settings
        settings.prepare()
        self.store = Store(settings.data_dir)
        self.models = models or Models(settings)
        self.lock = threading.RLock()
        self.indexes = VectorIndexes(self.store, settings, self.lock)
        kwargs = {"extractor": extractor} if extractor else {}
        self.indexer = Indexer(self.store, settings, self.models, self.lock, **kwargs)
        self.indexer.on_forget = self.indexes.loaded.clear
        self.search = Search(self.store, settings, self.models, self.indexes, self.lock)
        self.worker = Worker(self.indexer)
        self.instance = InstanceLock(settings.data_dir / "instance.lock")

    def source(self, file_id: int) -> tuple[Path, dict]:
        row = self.store.one(
            "SELECT f.*,r.path AS root_path FROM files f JOIN roots r ON r.id=f.root_id WHERE f.id=? AND r.enabled=1",
            (file_id,),
        )
        if not row:
            raise FileoraError("NOT_FOUND", "Indexed file not found", 404)
        path = Path(row["path"])
        root = Path(row["root_path"])
        try:
            if not path.resolve().is_relative_to(root.resolve()) or any(
                is_link(parent) for parent in [path, *path.parents] if parent != parent.parent
            ):
                raise FileoraError(
                    "SOURCE_BLOCKED", "Source path is no longer inside its allowed folder", 403
                )
            stat = path.stat()
        except OSError as exc:
            raise FileoraError(
                "SOURCE_UNAVAILABLE", "Source file is no longer available", 404
            ) from exc
        if stat.st_size != row["size"] or stat.st_mtime_ns != row["mtime_ns"]:
            raise FileoraError(
                "SOURCE_CHANGED", "Source changed since indexing. Rescan before previewing", 409
            )
        return path, row

    def asset(self, chunk_id: int) -> Path:
        row = self.store.one(
            "SELECT c.asset,f.id AS file_id FROM chunks c JOIN files f ON f.active_revision_id=c.revision_id WHERE c.id=? AND f.status='ready'",
            (chunk_id,),
        )
        if not row or not row["asset"]:
            raise FileoraError("NOT_FOUND", "Preview image not found", 404)
        self.source(row["file_id"])
        path = self.settings.data_dir / "assets" / row["asset"]
        if (
            not path.is_file()
            or path.resolve().parent != (self.settings.data_dir / "assets").resolve()
        ):
            raise FileoraError("NOT_FOUND", "Preview image unavailable", 404)
        return path

    def file(self, file_id: int) -> dict:
        row = self.store.one(
            "SELECT f.*,v.warnings FROM files f LEFT JOIN file_revisions v ON v.id=f.active_revision_id WHERE f.id=?",
            (file_id,),
        )
        if not row:
            raise FileoraError("NOT_FOUND", "File not found", 404)
        row["warnings"] = json.loads(row["warnings"] or "[]")
        row["chunks"] = self.store.rows(
            "SELECT id,kind,text,locator,symbol,asset FROM chunks WHERE revision_id=? ORDER BY ordinal LIMIT 100",
            (row["active_revision_id"],),
        )
        for chunk in row["chunks"]:
            chunk["locator"] = json.loads(chunk["locator"])
        try:
            self.source(file_id)
            row["source_available"] = True
        except FileoraError as exc:
            row["source_available"] = False
            row["source_error"] = exc.code
        return row
