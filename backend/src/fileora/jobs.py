from __future__ import annotations

import fnmatch
import json
import logging
import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from fileora.config import EXCLUDED
from fileora.indexing import SUPPORTED, is_link

logger = logging.getLogger(__name__)


class Worker:
    def __init__(self, indexer):
        self.indexer = indexer
        self.store = indexer.store
        self.stop_event = threading.Event()
        self.wake = threading.Event()
        self.thread = None
        self.observer = None
        self.dirty = set()
        self.dirty_lock = threading.Lock()
        self.changed_at = 0.0
        self.watch_lock = threading.RLock()
        self.event_roots: tuple = ()
        self.watched_roots = 0
        self.watch_errors: list[dict] = []

    def start(self):
        # A restarted job is retried as a full reconciliation, not resumed at a directory cursor.
        self.store.execute(
            "UPDATE jobs SET state='queued',processed=0,indexed=0,skipped=0,failed=0,deleted=0,total=0 WHERE state='running' AND cancel=0"
        )
        self.store.execute(
            "UPDATE jobs SET state='cancelled',finished_at=CURRENT_TIMESTAMP WHERE cancel=1 AND state IN ('queued','running')"
        )
        self.thread = threading.Thread(target=self._loop, name="fileora-indexer", daemon=True)
        self.thread.start()
        if self.indexer.settings.watch:
            self.restart_watch()

    def set_watch(self, enabled: bool):
        with self.watch_lock:
            if bool(self.indexer.settings.watch) == enabled:
                return
            self.indexer.settings.watch = enabled
            if enabled:
                self.restart_watch()
            else:
                self._stop_observer()
                self.event_roots = ()
                self.watched_roots = 0
                self.watch_errors = []
                with self.dirty_lock:
                    self.dirty.clear()
            self.wake.set()

    def _stop_observer(self):
        if self.observer:
            self.observer.stop()
            if self.observer.is_alive():
                self.observer.join()
            self.observer = None

    def watch_status(self) -> dict:
        with self.watch_lock:
            enabled = bool(self.indexer.settings.watch)
            active = bool(self.observer and self.observer.is_alive())
            errors = {item["path"]: item for item in self.watch_errors}
            if enabled:
                for folder, _ in self.event_roots:
                    if not folder.is_dir():
                        errors.setdefault(
                            str(folder), {"path": str(folder), "code": "WATCH_UNAVAILABLE"}
                        )
                if active and self.observer is not None:
                    for emitter in self.observer.emitters:
                        if not emitter.is_alive():
                            errors.setdefault(
                                emitter.watch.path,
                                {"path": emitter.watch.path, "code": "WATCH_STOPPED"},
                            )
            state = (
                "off"
                if not enabled
                else "waiting"
                if not self.event_roots
                else "watching"
                if active and not errors
                else "polling"
            )
            if enabled and self.thread is not None and not self.thread.is_alive():
                state = "stopped"
            return {
                "enabled": enabled,
                "state": state,
                "observer_active": active,
                "watched_roots": self.watched_roots,
                "reconcile_seconds": self.indexer.settings.reconcile_seconds,
                "worker_active": bool(self.thread and self.thread.is_alive()),
                "errors": list(errors.values()),
            }

    def _event_relevant(self, path: str, directory: bool) -> bool:
        candidate = Path(path).absolute()
        for folder, exclusions in self.event_roots:
            try:
                relative = candidate.relative_to(folder)
            except ValueError:
                continue
            if any(part.startswith(".") or part.lower() in EXCLUDED for part in relative.parts):
                return False
            prefixes = [
                Path(*relative.parts[:i]).as_posix() for i in range(1, len(relative.parts) + 1)
            ]
            if any(
                fnmatch.fnmatch(prefix, pattern) for prefix in prefixes for pattern in exclusions
            ):
                return False
            return directory or candidate.suffix.lower() in SUPPORTED
        return False

    def _record_event(self, event):
        if not self.indexer.settings.watch or event.event_type not in {
            "created",
            "modified",
            "deleted",
            "moved",
        }:
            return
        # Parent directory mtime notifications accompany file events and would
        # otherwise cause ignored dependency/build changes to trigger full scans.
        if event.is_directory and event.event_type == "modified":
            return
        paths = [event.src_path, getattr(event, "dest_path", "")]
        relevant = {
            path for path in paths if path and self._event_relevant(path, event.is_directory)
        }
        if not relevant:
            return
        with self.dirty_lock:
            if not self.indexer.settings.watch:
                return
            self.dirty.update(relevant)
            self.changed_at = time.monotonic()
        self.wake.set()

    def restart_watch(self, reconcile: bool = True):
        with self.watch_lock:
            if not self.indexer.settings.watch or self.stop_event.is_set():
                return
            self._restart_watch(reconcile)

    def _restart_watch(self, reconcile: bool):
        self._stop_observer()
        worker = self

        class Events(FileSystemEventHandler):
            def on_any_event(self, event):
                worker._record_event(event)

        self.observer = Observer()
        roots = self.store.rows("SELECT path,exclusions FROM roots WHERE enabled=1")
        self.event_roots = tuple(
            (Path(root["path"]), json.loads(root["exclusions"])) for root in roots
        )
        self.watched_roots = 0
        self.watch_errors = []
        for root in roots:
            try:
                folder = Path(root["path"])
                if not folder.is_dir() or any(
                    is_link(parent)
                    for parent in [folder, *folder.parents]
                    if parent != parent.parent
                ):
                    raise OSError("Folder unavailable")
                self.observer.schedule(Events(), root["path"], recursive=True)
                self.watched_roots += 1
            except OSError:
                self.watch_errors.append({"path": root["path"], "code": "WATCH_UNAVAILABLE"})
                logger.warning(
                    "A selected folder cannot be watched; periodic reconciliation remains enabled"
                )
        try:
            if self.watched_roots:
                self.observer.start()
            else:
                self.observer = None
        except OSError:
            self._stop_observer()
            self.watch_errors = [
                {"path": root["path"], "code": "WATCH_START_FAILED"} for root in roots
            ]
            self.watched_roots = 0
            self.observer = None  # Periodic reconciliation still runs.
        if (
            reconcile
            and roots
            and not self.store.one("SELECT id FROM jobs WHERE state IN ('queued','running')")
        ):
            self.indexer.create_job(verify=True)
        self.wake.set()

    def submit(self, verify=False):
        job_id = self.indexer.create_job(verify)
        self.wake.set()
        return job_id

    def _loop(self):
        last_reconcile = time.monotonic()
        while not self.stop_event.is_set():
            job = self.store.one(
                "SELECT * FROM jobs WHERE state='queued' ORDER BY created_at,id LIMIT 1"
            )
            forced = set()
            if job is None:
                # Serialize automatic job creation with disabling watching. If a
                # scan was already queued it may finish, but no new one appears
                # after the disable request returns.
                with self.watch_lock:
                    with self.dirty_lock:
                        if (
                            self.indexer.settings.watch
                            and self.dirty
                            and time.monotonic() - self.changed_at >= 1
                        ):
                            forced, self.dirty = self.dirty, set()
                    if forced or (
                        self.indexer.settings.watch
                        and time.monotonic() - last_reconcile
                        >= self.indexer.settings.reconcile_seconds
                    ):
                        job_id = self.indexer.create_job(verify=not bool(forced))
                        job = self.store.one("SELECT * FROM jobs WHERE id=?", (job_id,))
                        last_reconcile = time.monotonic()
                        if not forced:
                            # Reattach folders restored after being unavailable.
                            self.restart_watch(reconcile=False)
            if job:
                if job["cancel"]:
                    self.store.execute(
                        "UPDATE jobs SET state='cancelled',finished_at=CURRENT_TIMESTAMP WHERE id=?",
                        (job["id"],),
                    )
                else:
                    self.indexer.run(job["id"], forced)
            else:
                self.wake.wait(timeout=0.5)
                self.wake.clear()

    def stop(self):
        self.stop_event.set()
        active = self.store.rows("SELECT id FROM jobs WHERE state='running'")
        for job in active:
            self.store.execute("UPDATE jobs SET cancel=1 WHERE id=?", (job["id"],))
        self.wake.set()
        with self.watch_lock:
            self._stop_observer()
        if self.thread:
            # Keep ownership of the catalog until the current atomic operation stops.
            # Supervised extraction polls cancellation every 200ms.
            self.thread.join()
