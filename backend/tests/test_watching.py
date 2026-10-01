from __future__ import annotations

import json
import os
import time

from watchdog.events import DirModifiedEvent, FileCreatedEvent, FileMovedEvent

from fileora.config import Settings
from fileora.retrieval import SearchRequest
from fileora.service import Service


def wait_until(predicate, seconds=12):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    assert predicate(), "Automatic indexing did not reach the expected state"


def matches(service, query):
    return service.search.run(SearchRequest(query=query))["results"]


def test_real_watcher_create_rename_same_metadata_edit_and_delete(service, corpus):
    service.worker.start()
    try:
        status = service.configure_watch(True)
        assert status["state"] == "watching"
        assert status["watched_roots"] == 1
        wait_until(
            lambda: not service.store.one("SELECT id FROM jobs WHERE state IN ('queued','running')")
        )
        path = corpus / "lecture.txt"
        path.write_text("quasar waiting research", encoding="utf-8")
        wait_until(lambda: bool(matches(service, "quasar")))
        renamed = corpus / "revision.txt"
        path.rename(renamed)
        wait_until(lambda: matches(service, "quasar")[0]["name"] == "revision.txt")
        stat = renamed.stat()
        renamed.write_text("nebula waiting research", encoding="utf-8")
        os.utime(renamed, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        assert renamed.stat().st_size == stat.st_size
        wait_until(lambda: bool(matches(service, "nebula")))
        assert not matches(service, "quasar")
        renamed.unlink()
        wait_until(lambda: not matches(service, "nebula"))
        assert not service.store.one("SELECT id FROM files WHERE name='revision.txt'")
    finally:
        service.worker.stop()
    assert not service.worker.watch_status()["observer_active"]


def test_watch_preference_survives_restart_and_explicit_override(service):
    assert service.settings.watch is False
    assert service.configure_watch(True)["state"] == "waiting"
    saved = service.store.one("SELECT value FROM app_meta WHERE key='watch_enabled'")
    assert saved["value"] == "true"
    restored = Service(Settings(data_dir=service.settings.data_dir), models=service.models)
    assert restored.settings.watch is True
    override = Service(
        Settings(data_dir=service.settings.data_dir, watch=False), models=service.models
    )
    assert override.settings.watch is False
    assert restored.configure_watch(False)["state"] == "off"
    assert (
        Service(Settings(data_dir=service.settings.data_dir), models=service.models).settings.watch
        is False
    )


def test_turning_watch_off_stops_new_automatic_jobs(service, corpus):
    service.worker.start()
    try:
        service.configure_watch(True)
        wait_until(
            lambda: not service.store.one("SELECT id FROM jobs WHERE state IN ('queued','running')")
        )
        service.configure_watch(False)
        before = service.store.one("SELECT count(*) AS n FROM jobs")["n"]
        (corpus / "new.txt").write_text("unwatched constellations", encoding="utf-8")
        time.sleep(1.5)
        assert not matches(service, "constellations")
        assert service.store.one("SELECT count(*) AS n FROM jobs")["n"] == before
        assert service.worker.watch_status()["state"] == "off"
        assert not service.worker.dirty
    finally:
        service.worker.stop()


def test_ignored_events_do_not_dirty_library_but_moves_keep_both_paths(service, corpus):
    service.settings.watch = True
    service.worker.event_roots = ((corpus, ["private/*"]),)
    for path in (
        corpus / "node_modules" / "library.js",
        corpus / ".hidden" / "note.md",
        corpus / "private" / "secret.md",
        corpus / "unknown.zip",
        corpus.parent / "outside.md",
    ):
        service.worker._record_event(FileCreatedEvent(str(path)))
    service.worker._record_event(DirModifiedEvent(str(corpus)))
    assert not service.worker.dirty
    source, destination = corpus / "before.md", corpus / "after.md"
    service.worker._record_event(FileMovedEvent(str(source), str(destination)))
    assert service.worker.dirty == {str(source), str(destination)}


def test_unavailable_watcher_is_visible_and_periodic_scan_reattaches_restored_root(service, corpus):
    moved = corpus.with_name("temporarily-moved")
    corpus.rename(moved)
    service.settings.reconcile_seconds = 1
    service.worker.start()
    try:
        status = service.configure_watch(True)
        assert status["state"] == "polling"
        assert status["errors"][0]["code"] == "WATCH_UNAVAILABLE"
        wait_until(lambda: service.store.one("SELECT status FROM roots")["status"] == "unavailable")
        moved.rename(corpus)
        wait_until(lambda: service.worker.watch_status()["state"] == "watching")
        wait_until(lambda: bool(matches(service, "semaphores")))
    finally:
        service.worker.stop()
        if moved.exists():
            moved.rename(corpus)


def test_observer_start_failure_preserves_polling_fallback(service, corpus, monkeypatch):
    from fileora.jobs import Observer

    def unavailable(self):
        raise OSError("Unavailable watcher")

    monkeypatch.setattr(Observer, "start", unavailable)
    service.worker.start()
    try:
        status = service.configure_watch(True)
        assert status["state"] == "polling"
        assert status["errors"][0]["code"] == "WATCH_START_FAILED"
        assert status["worker_active"]
        assert not status["observer_active"]
        assert service.settings.watch
    finally:
        service.worker.stop()


def test_directory_events_force_hashing_descendants(service, corpus):
    path = corpus / "graphs.txt"
    stat = path.stat()
    text = path.read_text(encoding="utf-8").replace("Dijkstra", "Astarway")
    path.write_text(text, encoding="utf-8")
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    service.indexer.run(service.indexer.create_job(), forced_paths={str(corpus)})
    assert matches(service, "Astarway")
    assert not matches(service, "Dijkstra")


def test_dead_emitter_is_reported_even_when_observer_thread_is_alive(service, corpus):
    service.worker.start()
    try:
        assert service.configure_watch(True)["state"] == "watching"
        emitter = next(iter(service.worker.observer.emitters))
        emitter.stop()
        emitter.join(timeout=5)
        status = service.worker.watch_status()
        assert status["observer_active"]
        assert status["state"] == "polling"
        assert status["errors"][0]["code"] == "WATCH_STOPPED"
    finally:
        service.worker.stop()


def test_watch_api_persists_preference_and_is_session_protected(client, service):
    assert client.get("/api/v1/index/watch").json()["state"] == "off"
    denied = client.put(
        "/api/v1/index/watch", json={"enabled": True}, headers={"x-fileora-token": "wrong"}
    )
    assert denied.status_code == 403
    assert service.settings.watch is False
    enabled = client.put("/api/v1/index/watch", json={"enabled": True})
    assert enabled.status_code == 200
    assert enabled.json()["state"] == "watching"
    assert client.get("/api/v1/health").json()["watch"]["enabled"]
    wait_until(
        lambda: not service.store.one("SELECT id FROM jobs WHERE state IN ('queued','running')")
    )
    before = service.store.one("SELECT count(*) AS n FROM jobs")["n"]
    assert client.put("/api/v1/index/watch", json={"enabled": True}).status_code == 200
    assert service.store.one("SELECT count(*) AS n FROM jobs")["n"] == before
    assert client.put("/api/v1/index/watch", json={"enabled": False}).json()["state"] == "off"
    assert (
        json.loads(
            service.store.one("SELECT value FROM app_meta WHERE key='watch_enabled'")["value"]
        )
        is False
    )
