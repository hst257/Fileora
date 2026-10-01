from __future__ import annotations

import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


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

    def restart_watch(self):
        if self.observer:
            self.observer.stop()
            self.observer.join(timeout=5)
        worker = self

        class Events(FileSystemEventHandler):
            def on_any_event(self, event):
                if event.event_type not in {"created", "modified", "deleted", "moved"}:
                    return
                with worker.dirty_lock:
                    worker.dirty.add(event.src_path)
                    destination = getattr(event, "dest_path", None)
                    if destination:
                        worker.dirty.add(destination)
                    worker.changed_at = time.monotonic()
                worker.wake.set()

        self.observer = Observer()
        for root in self.store.rows("SELECT path FROM roots WHERE enabled=1"):
            if Path(root["path"]).is_dir():
                try:
                    self.observer.schedule(Events(), root["path"], recursive=True)
                except OSError:
                    pass  # Reconciliation still checks inaccessible roots.
        try:
            self.observer.start()
        except OSError:
            self.observer = None  # Periodic reconciliation still runs.
        if not self.store.one("SELECT id FROM jobs WHERE state IN ('queued','running')"):
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
                with self.dirty_lock:
                    if self.dirty and time.monotonic() - self.changed_at >= 1:
                        forced, self.dirty = self.dirty, set()
                if forced or (
                    self.indexer.settings.watch
                    and time.monotonic() - last_reconcile >= self.indexer.settings.reconcile_seconds
                ):
                    job_id = self.indexer.create_job(verify=not bool(forced))
                    job = self.store.one("SELECT * FROM jobs WHERE id=?", (job_id,))
                    last_reconcile = time.monotonic()
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
        if self.observer:
            self.observer.stop()
            self.observer.join(timeout=5)
        if self.thread:
            # Keep ownership of the catalog until the current atomic operation stops.
            # Supervised extraction polls cancellation every 200ms.
            self.thread.join()
