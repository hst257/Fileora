from __future__ import annotations

import fnmatch
import hashlib
import heapq
import json
import os
import re
import threading
import uuid
from collections.abc import Callable
from pathlib import Path

import faiss
import numpy as np

from fileora.chunking import chunk_units
from fileora.config import (
    AUDIO_EXTENSIONS,
    CODE_EXTENSIONS,
    EXCLUDED,
    IMAGE_EXTENSIONS,
    PRESENTATION_EXTENSIONS,
    TEXT_EXTENSIONS,
    VIDEO_EXTENSIONS,
    VISION_MODEL,
    Settings,
)
from fileora.domain import FileoraError
from fileora.extraction import supervised_extract
from fileora.models import Models
from fileora.storage import Store, json_dump

SUPPORTED = (
    TEXT_EXTENSIONS
    | CODE_EXTENSIONS
    | IMAGE_EXTENSIONS
    | AUDIO_EXTENSIONS
    | VIDEO_EXTENSIONS
    | PRESENTATION_EXTENSIONS
    | {".pdf"}
)


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def is_link(path: Path) -> bool:
    return path.is_symlink() or bool(getattr(path.lstat(), "st_file_attributes", 0) & 0x400)


def is_hidden(path: Path) -> bool:
    return path.name.startswith(".") or bool(getattr(path.lstat(), "st_file_attributes", 0) & 0x2)


def split_identifiers(value: str) -> str:
    return re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value).replace("_", " ")


class VectorIndexes:
    def __init__(self, store: Store, settings: Settings, lock: threading.RLock):
        self.store, self.settings, self.lock = store, settings, lock
        self.loaded: dict = {}

    def rows(self, profile_id: str) -> list[dict]:
        return self.store.rows(
            """SELECT e.id,e.vector,e.chunk_id FROM embeddings e
            JOIN chunks c ON c.id=e.chunk_id JOIN files f ON f.active_revision_id=c.revision_id
            JOIN roots r ON r.id=f.root_id WHERE e.profile_id=? AND f.status='ready'
            AND r.enabled=1 AND r.status='ready' ORDER BY e.id""",
            (profile_id,),
        )

    def get(self, profile: dict):
        with self.lock:
            state = self.store.one("SELECT * FROM index_state WHERE profile_id=?", (profile["id"],))
            generation = state["generation"] if state else 0
            cached = self.loaded.get(profile["id"])
            if cached and cached[0] == generation:
                return cached[1]
            index = None
            if state and state["snapshot_generation"] == generation and state["snapshot"]:
                path = self.settings.data_dir / "indexes" / state["snapshot"]
                if path.is_file() and digest(path) == state["checksum"]:
                    try:
                        candidate = faiss.read_index(str(path))
                        if candidate.d == profile["dimension"]:
                            index = candidate
                    except Exception:
                        index = None
            if index is None:
                index = faiss.IndexIDMap2(faiss.IndexFlatIP(profile["dimension"]))
                rows = self.rows(profile["id"])
                if rows:
                    vectors = np.stack(
                        [np.frombuffer(row["vector"], dtype=np.float32) for row in rows]
                    )
                    index.add_with_ids(
                        vectors, np.array([row["id"] for row in rows], dtype=np.int64)
                    )
                filename = f"{profile['id']}-{generation}-{uuid.uuid4().hex[:8]}.faiss"
                path = self.settings.data_dir / "indexes" / filename
                faiss.write_index(index, str(path))
                self.store.execute(
                    "UPDATE index_state SET snapshot_generation=?,snapshot=?,checksum=? WHERE profile_id=?",
                    (generation, filename, digest(path), profile["id"]),
                )
                for previous in (self.settings.data_dir / "indexes").glob(
                    f"{profile['id']}-*.faiss"
                ):
                    if previous != path:
                        try:
                            previous.unlink()
                        except OSError:
                            pass
            self.loaded[profile["id"]] = (generation, index)
            return index

    def search(
        self, profile: dict, query: np.ndarray, allowed: set[int] | None, limit: int = 50
    ) -> list[tuple[int, float]]:
        with self.lock:
            if allowed is not None:
                heap: list[tuple[float, int]] = []
                chunk_ids = sorted(allowed)
                for start in range(0, len(chunk_ids), 2048):
                    ids = chunk_ids[start : start + 2048]
                    batch = self.store.rows(
                        f"""SELECT e.chunk_id,e.vector FROM embeddings e
                        JOIN chunks c ON c.id=e.chunk_id JOIN files f ON f.active_revision_id=c.revision_id
                        WHERE e.profile_id=? AND f.status='ready' AND e.chunk_id IN ({",".join("?" for _ in ids)})""",
                        (profile["id"], *ids),
                    )
                    if not batch:
                        continue
                    vectors = np.stack(
                        [np.frombuffer(r["vector"], dtype=np.float32) for r in batch]
                    )
                    scores = vectors @ query
                    for row, score in zip(batch, scores, strict=True):
                        item = (float(score), -row["chunk_id"])
                        if len(heap) < limit:
                            heapq.heappush(heap, item)
                        elif item > heap[0]:
                            heapq.heapreplace(heap, item)
                return [(-chunk_id, score) for score, chunk_id in sorted(heap, reverse=True)]
            index = self.get(profile)
            distances, ids = index.search(query.reshape(1, -1), min(limit, max(1, index.ntotal)))
            hits = [
                (int(i), float(s)) for i, s in zip(ids[0], distances[0], strict=True) if i != -1
            ]
            if not hits:
                return []
            mapping = {
                r["id"]: r["chunk_id"]
                for r in self.store.rows(
                    f"SELECT id,chunk_id FROM embeddings WHERE id IN ({','.join('?' for _ in hits)})",
                    tuple(i for i, _ in hits),
                )
            }
            return [(mapping[i], score) for i, score in hits if i in mapping]


class Indexer:
    def __init__(
        self,
        store: Store,
        settings: Settings,
        models: Models,
        lock: threading.RLock,
        extractor=supervised_extract,
    ):
        self.store, self.settings, self.models, self.lock = store, settings, models, lock
        self.extractor = extractor
        self.on_forget: Callable[[], None] | None = None

    def add_root(self, path: str, exclusions: list[str] | None = None) -> dict:
        folder = Path(path).expanduser()
        if str(folder).startswith("\\\\"):
            raise FileoraError(
                "NETWORK_ROOT_DISABLED", "Use a local folder rather than a network share"
            )
        if not folder.is_dir() or any(
            is_link(parent) for parent in [folder, *folder.parents] if parent != parent.parent
        ):
            raise FileoraError(
                "INVALID_ROOT", "Choose an existing local directory without a symlink or junction"
            )
        folder = folder.resolve()
        for root in self.store.rows("SELECT * FROM roots"):
            existing = Path(root["path"])
            if existing == folder:
                return root
            if folder.is_relative_to(existing) or existing.is_relative_to(folder):
                raise FileoraError("OVERLAPPING_ROOT", "Choose non-overlapping indexed folders")
        if (
            folder == self.settings.data_dir
            or folder.is_relative_to(self.settings.data_dir)
            or (self.settings.models_dir and folder.is_relative_to(self.settings.models_dir))
        ):
            raise FileoraError("INVALID_ROOT", "The runtime data directory cannot be indexed")
        with self.lock, self.store.connect() as db:
            cursor = db.execute(
                "INSERT INTO roots(path,exclusions) VALUES(?,?)",
                (str(folder), json_dump(exclusions or [])),
            )
            return dict(
                db.execute("SELECT * FROM roots WHERE id=?", (cursor.lastrowid,)).fetchone()
            )

    def forget_root(self, root_id: int) -> None:
        with self.lock, self.store.connect() as db:
            db.execute(
                "DELETE FROM job_errors WHERE file_id IN (SELECT id FROM files WHERE root_id=?)",
                (root_id,),
            )
            db.execute(
                "DELETE FROM chunks_fts WHERE rowid IN (SELECT c.id FROM chunks c JOIN file_revisions v ON v.id=c.revision_id JOIN files f ON f.id=v.file_id WHERE f.root_id=?)",
                (root_id,),
            )
            db.execute("DELETE FROM roots WHERE id=?", (root_id,))
            Store.changed(db)
            db.execute("UPDATE index_state SET snapshot=NULL,checksum=NULL,snapshot_generation=-1")
        for snapshot in (self.settings.data_dir / "indexes").glob("*.faiss"):
            snapshot.unlink(missing_ok=True)
        if self.on_forget:
            self.on_forget()
        self.cleanup_assets()

    def cleanup_assets(self) -> None:
        used = {
            r["asset"]
            for r in self.store.rows("SELECT DISTINCT asset FROM chunks WHERE asset IS NOT NULL")
        }
        for path in (self.settings.data_dir / "assets").glob("*.jpg"):
            if path.name not in used:
                try:
                    path.unlink()
                except OSError:
                    pass
        for temporary in (self.settings.data_dir / "assets").glob("ocr-*.png"):
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        cache_keys = {
            json.loads(r["locator"]).get("ocr_cache_key")
            for r in self.store.rows("SELECT locator FROM chunks WHERE kind='ocr'")
        }
        for cached in (self.settings.data_dir / "ocr-cache").glob("ppt-*.*"):
            if cached.suffix == ".tmp" or cached.stem not in cache_keys:
                try:
                    cached.unlink(missing_ok=True)
                except OSError:
                    pass

    def create_job(self, verify: bool = False) -> str:
        job_id = uuid.uuid4().hex
        self.store.execute(
            "INSERT INTO jobs(id,state,verify) VALUES(?,'queued',?)", (job_id, int(verify))
        )
        return job_id

    def _cancelled(self, job_id: str) -> bool:
        row = self.store.one("SELECT cancel FROM jobs WHERE id=?", (job_id,))
        return bool(row and row["cancel"])

    def _error(
        self, job_id: str, relative: str, exc: Exception, file_id: int | None = None
    ) -> None:
        code = getattr(exc, "code", "PROCESSING_FAILED")
        message = getattr(
            exc, "message", "Could not process this file; check permissions and format"
        )
        self.store.execute(
            "INSERT INTO job_errors(job_id,file_id,relative_path,code,message) VALUES(?,?,?,?,?)",
            (job_id, file_id, relative, code, message),
        )

    def pipeline_hash(self, path: Path | None = None) -> str:
        identity: dict = {
            "extractor": 1,
            "chunker": 1,
            "budget": self.settings.chunk_tokens,
            "overlap": self.settings.overlap_tokens,
            "ocr": self.settings.enable_ocr,
            "vision": self.settings.enable_vision,
            "media": self.settings.enable_media,
            "frames": self.settings.frame_interval,
        }
        if path and path.suffix.lower() in PRESENTATION_EXTENSIONS:
            from fileora.presentation_ocr import engine_identity

            identity["presentation"] = {
                "version": 2,
                "ocr_seconds": self.settings.ppt_ocr_seconds,
                "ocr_max_images": self.settings.ppt_ocr_max_images,
                "ocr_engine": engine_identity() if self.settings.enable_ocr else "disabled",
            }
        if path and path.suffix.lower() in IMAGE_EXTENSIONS | {".pdf"}:
            identity["image_provenance"] = 1
        for kind, model in (
            ("text", self.settings.text_model),
            ("vision", "openai/clip-vit-base-patch32"),
        ):
            identity[kind] = (
                self.models.manifest(model) if self.models.available(model) else "not-prepared"
            )
        if self.settings.enable_media:
            speech = "Systran/faster-whisper-base.en"
            identity["speech"] = (
                self.models.manifest(speech) if self.models.available(speech) else "not-prepared"
            )
        return hashlib.sha256(json_dump(identity).encode()).hexdigest()

    def refresh_metadata(self, current: dict, path: Path, relative: str, stat) -> None:
        if (
            current["path"],
            current["relative_path"],
            current["name"],
            current["size"],
            current["mtime_ns"],
        ) == (str(path), relative, path.name, stat.st_size, stat.st_mtime_ns):
            return
        with self.lock, self.store.connect() as db:
            db.execute(
                "UPDATE files SET path=?,relative_path=?,name=?,size=?,mtime_ns=? WHERE id=?",
                (str(path), relative, path.name, stat.st_size, stat.st_mtime_ns, current["id"]),
            )
            if current["relative_path"] != relative:
                db.execute(
                    "UPDATE chunks_fts SET name=?,path=? WHERE rowid IN (SELECT id FROM chunks WHERE revision_id=?)",
                    (path.name, relative, current["active_revision_id"]),
                )
                Store.changed(db)

    def process(
        self, path: Path, root: dict, job_id: str, verify: bool, forced: bool = False
    ) -> str:
        relative = path.relative_to(Path(root["path"])).as_posix()
        if not path.resolve().is_relative_to(Path(root["path"]).resolve()) or any(
            is_link(parent) for parent in [path, *path.parents] if parent != parent.parent
        ):
            raise FileoraError("SOURCE_BLOCKED", "Source escaped the allowed folder")
        stat = path.stat()
        key = os.path.normcase(str(path.resolve()))
        current = self.store.one(
            "SELECT f.*,v.sha256,v.pipeline_hash FROM files f LEFT JOIN file_revisions v ON v.id=f.active_revision_id WHERE path_key=?",
            (key,),
        )
        # Optional media is intentionally skipped, not reported as a parser failure.
        if (
            path.suffix.lower() in AUDIO_EXTENSIONS | VIDEO_EXTENSIONS
            and not self.settings.enable_media
        ):
            return "skipped"
        pipeline = self.pipeline_hash(path)
        unchanged = (
            current and current["status"] == "ready" and current["pipeline_hash"] == pipeline
        )
        if (
            current is not None
            and unchanged
            and current["size"] == stat.st_size
            and current["mtime_ns"] == stat.st_mtime_ns
            and not verify
            and not forced
        ):
            self.refresh_metadata(current, path, relative, stat)
            return "skipped"
        if (
            stat.st_size > self.settings.max_file_bytes
            and path.suffix.lower() not in AUDIO_EXTENSIONS | VIDEO_EXTENSIONS
        ):
            raise FileoraError("FILE_TOO_LARGE", "File exceeds the configured size limit")
        sha = digest(path)
        if current is not None and unchanged and current["sha256"] == sha:
            self.refresh_metadata(current, path, relative, stat)
            return "skipped"
        if current:
            with self.lock, self.store.connect() as db:
                db.execute("UPDATE files SET status='stale' WHERE id=?", (current["id"],))
                Store.changed(db)
        extraction = (
            supervised_extract(path, self.settings, lambda: self._cancelled(job_id))
            if self.extractor is supervised_extract
            else self.extractor(path, self.settings)
        )
        tokenizer = self.models.tokenizer()
        units = chunk_units(
            extraction.units, self.settings.chunk_tokens, self.settings.overlap_tokens, tokenizer
        )
        warnings = extraction.warnings[:]
        if not units:
            warnings.append("no_searchable_content")
        embeddings: dict[int, list[tuple[dict, np.ndarray, str]]] = {}
        text_units = [(i, u) for i, u in enumerate(units) if u.text.strip()]
        if self.models.available(self.settings.text_model) and text_units:
            profile = self.models.profile()
            missing = []
            for i, unit in text_units:
                input_hash = hashlib.sha256(unit.text.encode()).hexdigest()
                cached = self.store.one(
                    "SELECT vector FROM embeddings WHERE profile_id=? AND input_hash=? LIMIT 1",
                    (profile["id"], input_hash),
                )
                if cached:
                    embeddings.setdefault(i, []).append(
                        (
                            profile,
                            np.frombuffer(cached["vector"], dtype=np.float32).copy(),
                            input_hash,
                        )
                    )
                else:
                    missing.append((i, unit, input_hash))
            if missing:
                unique = {input_hash: unit.text for _, unit, input_hash in missing}
                vectors = self.models.encode_text(list(unique.values()))
                by_hash = dict(zip(unique, vectors, strict=True))
                for i, _, input_hash in missing:
                    vector = by_hash[input_hash]
                    embeddings.setdefault(i, []).append((profile, vector, input_hash))
        elif text_units:
            warnings.append("semantic_not_indexed:model_not_prepared")
        if self.settings.enable_vision and self.models.available(VISION_MODEL):
            visual = [(i, u) for i, u in enumerate(units) if u.kind in {"image", "frame"}]
            if visual:
                from PIL import Image

                profile = self.models.profile("vision")
                for start in range(0, len(visual), 8):
                    batch = visual[start : start + 8]
                    images = []
                    for _, unit in batch:
                        if not unit.asset:
                            raise FileoraError(
                                "ASSET_UNAVAILABLE", "Visual unit has no preview asset"
                            )
                        with Image.open(self.settings.data_dir / "assets" / unit.asset) as image:
                            images.append(image.convert("RGB"))
                    vectors = self.models.encode_vision(images)
                    for (i, unit), vector in zip(batch, vectors, strict=True):
                        embeddings.setdefault(i, []).append((profile, vector, unit.asset or sha))
        elif self.settings.enable_vision and any(u.kind in {"image", "frame"} for u in units):
            warnings.append("vision_not_indexed:model_not_prepared")
        after = path.stat()
        if (
            stat.st_size != after.st_size
            or stat.st_mtime_ns != after.st_mtime_ns
            or digest(path) != sha
        ):
            raise FileoraError(
                "SOURCE_CHANGED", "File changed while processing; retry after it settles"
            )
        if self._cancelled(job_id):
            return "cancelled"
        with self.lock, self.store.connect() as db:
            if current:
                file_id = current["id"]
            else:
                cursor = db.execute(
                    "INSERT INTO files(root_id,path,path_key,relative_path,name,extension,modality,size,mtime_ns) VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        root["id"],
                        str(path),
                        key,
                        relative,
                        path.name,
                        path.suffix.lower(),
                        extraction.modality,
                        stat.st_size,
                        stat.st_mtime_ns,
                    ),
                )
                file_id = cursor.lastrowid
            cursor = db.execute(
                "INSERT INTO file_revisions(file_id,sha256,pipeline_hash,warnings) VALUES(?,?,?,?)",
                (file_id, sha, pipeline, json_dump(warnings)),
            )
            revision_id = cursor.lastrowid
            for i, unit in enumerate(units):
                cursor = db.execute(
                    "INSERT INTO chunks(revision_id,ordinal,kind,text,text_hash,locator,symbol,asset) VALUES(?,?,?,?,?,?,?,?)",
                    (
                        revision_id,
                        i,
                        unit.kind,
                        unit.text,
                        hashlib.sha256(unit.text.encode()).hexdigest(),
                        json_dump(unit.locator),
                        unit.symbol,
                        unit.asset,
                    ),
                )
                chunk_id = cursor.lastrowid
                db.execute(
                    "INSERT INTO chunks_fts(rowid,text,name,path,symbol) VALUES(?,?,?,?,?)",
                    (
                        chunk_id,
                        unit.text + " " + split_identifiers(unit.text)
                        if unit.kind == "code"
                        else unit.text,
                        path.name,
                        relative,
                        split_identifiers(unit.symbol),
                    ),
                )
                for profile, vector, input_hash in embeddings.get(i, []):
                    vector = np.asarray(vector, dtype=np.float32)
                    if (
                        vector.shape != (profile["dimension"],)
                        or not np.isfinite(vector).all()
                        or not np.isclose(np.linalg.norm(vector), 1, atol=1e-3)
                    ):
                        raise FileoraError(
                            "INVALID_EMBEDDING", "Model returned an invalid or unnormalized vector"
                        )
                    db.execute(
                        "INSERT OR IGNORE INTO embedding_profiles(id,model,revision,dimension,config,modality) VALUES(?,?,?,?,?,?)",
                        (
                            profile["id"],
                            profile["model"],
                            profile["revision"],
                            profile["dimension"],
                            json_dump(profile["config"]),
                            profile["modality"],
                        ),
                    )
                    db.execute(
                        "INSERT OR IGNORE INTO index_state(profile_id) VALUES(?)", (profile["id"],)
                    )
                    db.execute(
                        "INSERT INTO embeddings(chunk_id,profile_id,input_hash,vector) VALUES(?,?,?,?)",
                        (chunk_id, profile["id"], input_hash, vector.tobytes()),
                    )
            db.execute(
                "UPDATE files SET size=?,mtime_ns=?,status='ready',error_code=NULL,active_revision_id=?,modality=? WHERE id=?",
                (stat.st_size, stat.st_mtime_ns, revision_id, extraction.modality, file_id),
            )
            db.execute(
                "DELETE FROM chunks_fts WHERE rowid IN (SELECT c.id FROM chunks c JOIN file_revisions v ON v.id=c.revision_id WHERE v.file_id=? AND v.id!=?)",
                (file_id, revision_id),
            )
            db.execute(
                "DELETE FROM file_revisions WHERE file_id=? AND id!=?", (file_id, revision_id)
            )
            Store.changed(db)
        return "indexed"

    def run(self, job_id: str, forced_paths: set[str] | None = None) -> dict:
        forced = {os.path.normcase(os.path.abspath(path)) for path in (forced_paths or set())}
        job = self.store.one("SELECT * FROM jobs WHERE id=?", (job_id,))
        if not job:
            raise FileoraError("NOT_FOUND", "Indexing job not found", 404)
        self.store.execute(
            "UPDATE jobs SET state='running',started_at=CURRENT_TIMESTAMP WHERE id=?", (job_id,)
        )
        try:
            for root in self.store.rows("SELECT * FROM roots WHERE enabled=1"):
                folder = Path(root["path"])
                if not folder.is_dir() or any(
                    is_link(parent)
                    for parent in [folder, *folder.parents]
                    if parent != parent.parent
                ):
                    with self.lock, self.store.connect() as db:
                        db.execute(
                            "UPDATE roots SET status='unavailable' WHERE id=?", (root["id"],)
                        )
                        Store.changed(db)
                    self._error(
                        job_id,
                        "",
                        FileoraError("ROOT_UNAVAILABLE", "An indexed folder is unavailable"),
                    )
                    continue
                with self.lock, self.store.connect() as db:
                    if root["status"] != "ready":
                        db.execute("UPDATE roots SET status='ready' WHERE id=?", (root["id"],))
                        Store.changed(db)
                complete = True
                seen = set()
                exclusions = json.loads(root["exclusions"])

                def onerror(error):
                    nonlocal complete
                    complete = False
                    self._error(
                        job_id,
                        "",
                        FileoraError("SCAN_INCOMPLETE", "A folder could not be traversed"),
                    )

                for directory, dirs, names in os.walk(folder, followlinks=False, onerror=onerror):
                    safe_dirs = []
                    for name in dirs:
                        candidate = Path(directory) / name
                        relative = candidate.relative_to(folder).as_posix()
                        try:
                            if (
                                name not in EXCLUDED
                                and not name.startswith(".")
                                and not is_hidden(candidate)
                                and not is_link(candidate)
                                and candidate.resolve() != self.settings.data_dir
                                and candidate.resolve() != self.settings.models_dir
                                and not any(
                                    fnmatch.fnmatch(relative, pattern) for pattern in exclusions
                                )
                            ):
                                safe_dirs.append(name)
                        except OSError as exc:
                            onerror(exc)
                    dirs[:] = safe_dirs
                    for name in sorted(names):
                        if self._cancelled(job_id):
                            self.store.execute(
                                "UPDATE jobs SET state='cancelled',finished_at=CURRENT_TIMESTAMP WHERE id=?",
                                (job_id,),
                            )
                            return self.store.one("SELECT * FROM jobs WHERE id=?", (job_id,)) or {}
                        path = Path(directory) / name
                        relative = path.relative_to(folder).as_posix()
                        if (
                            path.suffix.lower() not in SUPPORTED
                            or name.startswith(".")
                            or any(fnmatch.fnmatch(relative, pattern) for pattern in exclusions)
                        ):
                            continue
                        try:
                            if is_link(path) or is_hidden(path):
                                continue
                            seen.add(os.path.normcase(str(path.absolute())))
                            self.store.execute(
                                "UPDATE jobs SET total=total+1 WHERE id=?", (job_id,)
                            )
                            result = self.process(
                                path,
                                root,
                                job_id,
                                bool(job["verify"]),
                                bool(forced)
                                and any(
                                    os.path.normcase(str(parent.absolute())) in forced
                                    for parent in (path, *path.parents)
                                ),
                            )
                            if result == "cancelled":
                                self.store.execute(
                                    "UPDATE jobs SET state='cancelled',finished_at=CURRENT_TIMESTAMP WHERE id=?",
                                    (job_id,),
                                )
                                return (
                                    self.store.one("SELECT * FROM jobs WHERE id=?", (job_id,)) or {}
                                )
                        except Exception as exc:
                            if getattr(exc, "code", None) == "CANCELLED":
                                self.store.execute(
                                    "UPDATE jobs SET state='cancelled',finished_at=CURRENT_TIMESTAMP WHERE id=?",
                                    (job_id,),
                                )
                                return (
                                    self.store.one("SELECT * FROM jobs WHERE id=?", (job_id,)) or {}
                                )
                            result = "failed"
                            current = self.store.one(
                                "SELECT id FROM files WHERE root_id=? AND relative_path=?",
                                (root["id"], relative),
                            )
                            if current:
                                with self.lock, self.store.connect() as db:
                                    db.execute(
                                        "UPDATE files SET status='failed',error_code=? WHERE id=?",
                                        (getattr(exc, "code", "PROCESSING_FAILED"), current["id"]),
                                    )
                                    Store.changed(db)
                            self._error(job_id, relative, exc, current["id"] if current else None)
                        self.store.execute(
                            f"UPDATE jobs SET processed=processed+1,{result}={result}+1 WHERE id=?",
                            (job_id,),
                        )
                if complete:
                    with self.lock, self.store.connect() as db:
                        for old in db.execute(
                            "SELECT id,path_key FROM files WHERE root_id=?", (root["id"],)
                        ).fetchall():
                            if old["path_key"] not in seen:
                                db.execute(
                                    "DELETE FROM chunks_fts WHERE rowid IN (SELECT c.id FROM chunks c JOIN file_revisions v ON v.id=c.revision_id WHERE v.file_id=?)",
                                    (old["id"],),
                                )
                                db.execute("DELETE FROM files WHERE id=?", (old["id"],))
                                db.execute(
                                    "UPDATE jobs SET deleted=deleted+1 WHERE id=?", (job_id,)
                                )
                                Store.changed(db)
                        db.execute(
                            "UPDATE roots SET last_scan=CURRENT_TIMESTAMP WHERE id=?", (root["id"],)
                        )
            self.store.execute(
                "UPDATE jobs SET state='completed',finished_at=CURRENT_TIMESTAMP WHERE id=?",
                (job_id,),
            )
        except Exception as exc:
            self._error(job_id, "", exc)
            self.store.execute(
                "UPDATE jobs SET state='failed',finished_at=CURRENT_TIMESTAMP WHERE id=?", (job_id,)
            )
        finally:
            self.cleanup_assets()
        return self.store.one("SELECT * FROM jobs WHERE id=?", (job_id,)) or {}
