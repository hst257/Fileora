from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from pypdf import PdfWriter

from fileora.chunking import chunk_units, offsets
from fileora.domain import FileoraError, Unit
from fileora.evaluation import metrics, ndcg, span_matches
from fileora.extraction import code_units, extract, supervised_extract, text_file
from fileora.retrieval import Filters, SearchRequest, rrf
from fileora.service import InstanceLock, Service


def test_chunk_budget_overlap_and_lines():
    text = "\n".join(f"word{i} another" for i in range(20))
    chunks = chunk_units([Unit(text, locator={"line_start": 1})], 8, 2)
    assert all(len(offsets(c.text)) <= 8 for c in chunks)
    assert chunks[0].locator["line_start"] == 1
    assert chunks[-1].locator["line_end"] == 20
    assert chunks[0].text.split()[-2:] == chunks[1].text.split()[:2]
    for c in chunks:
        assert text[c.locator["char_start"] : c.locator["char_end"]] == c.text


def test_pages_never_merge():
    result = chunk_units(
        [Unit("first page", locator={"page": 1}), Unit("second page", locator={"page": 2})], 8, 1
    )
    assert [c.locator["page"] for c in result] == [1, 2]


def test_unicode_code_provenance():
    text = '# café\ndef solve():\n    return "graph"\n'
    units = code_units(Path("test.py"), text)
    function = next(u for u in units if u.symbol == "solve")
    assert function.locator["line_start"] == 2
    assert text[function.locator["char_start"] :].startswith("def solve")


def test_bad_encoding(tmp_path):
    path = tmp_path / "bad.txt"
    path.write_bytes(b"\xffnot unicode")
    with pytest.raises(FileoraError, match="UTF-8"):
        text_file(path)


def test_utf16(tmp_path):
    path = tmp_path / "note.txt"
    path.write_text("paging", encoding="utf-16")
    assert text_file(path) == "paging"


def test_blank_pdf_and_encryption(tmp_path, service):
    path = tmp_path / "blank.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)
    writer.write(path)
    result = extract(path, service.settings)
    assert result.warnings == ["page_1:needs_ocr"]
    writer.encrypt("secret")
    writer.write(path)
    with pytest.raises(FileoraError) as exc:
        extract(path, service.settings)
    assert exc.value.code == "ENCRYPTED_PDF"


def test_supervised_spawn(tmp_path, service):
    path = tmp_path / "spawn.txt"
    path.write_text("hello", encoding="utf-8")
    assert supervised_extract(path, service.settings).units[0].text == "hello"


def test_image_thumbnail(tmp_path, service):
    path = tmp_path / "diagram.png"
    Image.new("RGB", (1600, 900), "white").save(path)
    result = extract(path, service.settings)
    assert result.modality == "image"
    asset = service.settings.data_dir / "assets" / result.units[0].asset
    with Image.open(asset) as image:
        assert max(image.size) <= 1280


def test_image_pixel_limit(tmp_path, service):
    path = tmp_path / "diagram.png"
    Image.new("RGB", (30, 30)).save(path)
    service.settings.max_image_pixels = 100
    with pytest.raises(FileoraError) as exc:
        extract(path, service.settings)
    assert exc.value.code == "IMAGE_TOO_LARGE"


def test_lexical_semantic_hybrid(service, corpus):
    for mode in ("lexical", "semantic", "hybrid"):
        result = service.search.run(SearchRequest(query="semaphores critical", mode=mode))
        assert result["results"][0]["name"] == "semaphores.md"
        assert result["results"][0]["evidence"][0]["locator"]["line_start"] == 1


def test_incremental_reuses_unchanged(service, corpus):
    calls = service.models.calls
    result = service.indexer.run(service.indexer.create_job())
    assert result["skipped"] == 2 and result["indexed"] == 0
    assert service.models.calls == calls


def test_modified_deleted_rename(service, corpus):
    (corpus / "semaphores.md").write_text(
        "mutexes prevent concurrent modification", encoding="utf-8"
    )
    (corpus / "graphs.txt").rename(corpus / "renamed.txt")
    job = service.indexer.run(service.indexer.create_job())
    assert job["deleted"] == 1 and job["indexed"] == 2
    matches = service.search.run(SearchRequest(query="semaphores", mode="lexical"))["results"]
    assert all(
        "critical sections" not in evidence["snippet"]
        for result in matches
        for evidence in result["evidence"]
    )
    assert (
        service.search.run(SearchRequest(query="Dijkstra", mode="lexical"))["results"][0]["name"]
        == "renamed.txt"
    )
    with service.store.connect() as db:
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    (corpus / "renamed.txt").unlink()
    service.indexer.run(service.indexer.create_job())
    assert not service.search.run(SearchRequest(query="Dijkstra", mode="lexical"))["results"]


def test_verify_same_mtime_size(service, corpus):
    path = corpus / "graphs.txt"
    original = path.stat()
    path.write_text(path.read_text().replace("Dijkstra", "KruskalX"), encoding="utf-8")
    os.utime(path, ns=(original.st_atime_ns, original.st_mtime_ns))
    result = service.indexer.run(service.indexer.create_job(verify=True))
    assert result["indexed"] == 1
    assert service.search.run(SearchRequest(query="KruskalX", mode="lexical"))["results"]


def test_duplicate_locations_and_cache(service, corpus):
    calls = service.models.calls
    (corpus / "copy.md").write_bytes((corpus / "semaphores.md").read_bytes())
    service.indexer.run(service.indexer.create_job())
    assert service.models.calls == calls
    result = service.search.run(SearchRequest(query="semaphores", mode="lexical"))
    assert len(result["results"]) == 1
    assert len(result["results"][0]["aliases"]) == 1


def test_filter_before_vector_limit(service, corpus):
    result = service.search.run(
        SearchRequest(
            query="Dijkstra shortest path", mode="semantic", filters=Filters(extension=".txt")
        )
    )
    assert len(result["results"]) == 1
    assert result["results"][0]["name"] == "graphs.txt"


def test_literal_fts_and_path_filter(service, corpus):
    result = service.search.run(
        SearchRequest(
            query='" OR * NEAR semaphores', mode="lexical", filters=Filters(path_prefix="sema")
        )
    )
    assert result["results"][0]["name"] == "semaphores.md"
    assert not service.search.run(
        SearchRequest(query="semaphores", mode="lexical", filters=Filters(path_prefix="%"))
    )["results"]


def test_index_recovery(service, corpus):
    profile = service.models.profile()
    index = service.indexes.get(profile)
    rows = service.indexes.rows(profile["id"])
    query = service.models.encode_text(["Dijkstra"], query=True)[0]
    vectors = np.stack([np.frombuffer(r["vector"], dtype=np.float32) for r in rows])
    expected = sorted(
        zip([r["chunk_id"] for r in rows], vectors @ query, strict=True), key=lambda p: -p[1]
    )
    assert [i for i, _ in service.indexes.search(profile, query, None)] == [i for i, _ in expected]
    state = service.store.one("SELECT * FROM index_state WHERE profile_id=?", (profile["id"],))
    (service.settings.data_dir / "indexes" / state["snapshot"]).write_bytes(b"corrupt")
    service.indexes.loaded.clear()
    calls = service.models.calls
    assert service.indexes.get(profile).ntotal == index.ntotal
    assert service.models.calls == calls
    restarted = Service(service.settings, service.models)
    assert restarted.indexes.get(profile).ntotal == index.ntotal


def test_unavailable_root_preserves_catalog(service, corpus):
    moved = corpus.with_name("offline")
    corpus.rename(moved)
    job = service.indexer.run(service.indexer.create_job())
    assert job["deleted"] == 0
    assert service.store.status()["files"] == 2
    assert not service.search.run(SearchRequest(query="Dijkstra", mode="lexical"))["results"]
    moved.rename(corpus)
    service.indexer.run(service.indexer.create_job())
    assert service.search.run(SearchRequest(query="Dijkstra", mode="lexical"))["results"]


def test_incomplete_scan_does_not_delete(service, corpus, monkeypatch):
    import fileora.indexing

    def broken_walk(folder, **kwargs):
        kwargs["onerror"](PermissionError())
        return iter([])

    monkeypatch.setattr(fileora.indexing.os, "walk", broken_walk)
    assert service.indexer.run(service.indexer.create_job())["deleted"] == 0
    assert service.store.status()["files"] == 2


def test_cancellation_before_processing(service, corpus):
    job_id = service.indexer.create_job()
    service.store.execute("UPDATE jobs SET cancel=1 WHERE id=?", (job_id,))
    assert service.indexer.run(job_id)["state"] == "cancelled"


def test_failure_keeps_old_content_hidden(service, corpus):
    path = corpus / "semaphores.md"
    path.write_bytes(b"\xffbroken")
    result = service.indexer.run(service.indexer.create_job())
    assert result["failed"] == 1
    assert not service.search.run(SearchRequest(query="semaphores", mode="lexical"))["results"]
    assert service.store.status()["failures"][0]["error_code"] == "UNSUPPORTED_ENCODING"


def test_changed_during_extraction(service, corpus):
    path = corpus / "semaphores.md"
    path.write_text("semaphore changed", encoding="utf-8")
    original = service.indexer.extractor

    def mutate(path, settings):
        result = original(path, settings)
        path.write_text("another revision", encoding="utf-8")
        return result

    service.indexer.extractor = mutate
    job = service.indexer.run(service.indexer.create_job())
    assert job["failed"] == 1
    assert not service.search.run(SearchRequest(query="semaphore", mode="lexical"))["results"]


def test_forget_removes_fts_and_vectors(service, corpus):
    service.indexes.get(service.models.profile())
    assert list((service.settings.data_dir / "indexes").glob("*.faiss"))
    root = service.store.status()["roots"][0]
    service.indexer.forget_root(root["id"])
    assert (corpus / "semaphores.md").exists()
    assert service.store.status()["files"] == 0
    assert not service.store.rows("SELECT * FROM embeddings")
    assert not service.store.rows("SELECT rowid FROM chunks_fts")
    assert not list((service.settings.data_dir / "indexes").glob("*.faiss"))
    assert not service.indexes.loaded


def test_overlap_and_hidden_exclusions(service, corpus):
    with pytest.raises(FileoraError) as exc:
        service.indexer.add_root(str(corpus.parent))
    assert exc.value.code == "OVERLAPPING_ROOT"
    (corpus / ".env.txt").write_text("secret")
    (corpus / "node_modules").mkdir()
    (corpus / "node_modules" / "secret.md").write_text("secret")
    service.indexer.run(service.indexer.create_job())
    assert service.store.status()["files"] == 2


def test_source_changed_and_escape(service, corpus):
    row = service.store.one("SELECT id FROM files WHERE name='graphs.txt'")
    path, _ = service.source(row["id"])
    path.write_text("changed", encoding="utf-8")
    with pytest.raises(FileoraError) as exc:
        service.source(row["id"])
    assert exc.value.code == "SOURCE_CHANGED"
    service.store.execute(
        "UPDATE files SET path=? WHERE id=?", (str(corpus.parent / "outside.txt"), row["id"])
    )
    with pytest.raises(FileoraError) as exc:
        service.source(row["id"])
    assert exc.value.code == "SOURCE_BLOCKED"


def test_instance_lock(service):
    lock = InstanceLock(service.settings.data_dir / "test.lock")
    other = InstanceLock(service.settings.data_dir / "test.lock")
    lock.acquire()
    try:
        with pytest.raises(FileoraError):
            other.acquire()
    finally:
        lock.release()
    other.acquire()
    other.release()


def test_lexical_fallback(service, corpus):
    service.models.enabled = False
    result = service.search.run(SearchRequest(query="Dijkstra priority queue", mode="hybrid"))
    assert result["results"] and result["warnings"]


def test_metrics_no_duplicate_credit():
    result = metrics(["a", "a", "b"], {"a", "c"}, 5)
    assert result == {"precision": 0.2, "recall": 0.5, "hit_rate": 1.0, "mrr": 1.0}
    assert metrics(["x", "a"], {"a"}, 5)["mrr"] == 0.5
    assert metrics([], set(), 5)["mrr"] == 0
    assert ndcg(["a", "b"], {"a": 2, "b": 1}, 5) == 1


def test_rank_fusion_and_locations():
    assert rrf([[(1, 10), (2, 1)], [(2, -100), (3, 900)]])[0][0] == 2
    assert span_matches({"page": 2}, {"page": 2})
    assert not span_matches({"page": 1}, {"page": 2})
    assert span_matches({"line_start": 5, "line_end": 10}, {"line_start": 9, "line_end": 15})


def test_no_query_truncation(service, corpus):
    with pytest.raises(FileoraError) as exc:
        service.search.run(SearchRequest(query="word " * 129))
    assert exc.value.code == "QUERY_TOO_LONG"


def test_cancel_before_extraction_does_not_read_source(service):
    with pytest.raises(FileoraError) as exc:
        supervised_extract(Path("nonexistent.pdf"), service.settings, cancelled=lambda: True)
    assert exc.value.code == "CANCELLED"


def test_visual_only_requires_enabled_vision(service, corpus):
    with pytest.raises(FileoraError) as exc:
        service.search.run(SearchRequest(query="semaphore", channels="vision"))
    assert exc.value.code == "VISION_DISABLED"


def test_silent_video_does_not_require_speech_model(service, tmp_path):
    av = pytest.importorskip("av")
    path = tmp_path / "silent.mp4"
    with av.open(str(path), "w") as output:
        stream = output.add_stream("libx264", rate=1)
        stream.width, stream.height, stream.pix_fmt = 64, 64, "yuv420p"
        frame = av.VideoFrame.from_ndarray(
            np.full((64, 64, 3), 127, dtype=np.uint8), format="rgb24"
        )
        for packet in stream.encode(frame):
            output.mux(packet)
        for packet in stream.encode():
            output.mux(packet)
    service.settings.enable_media = True
    service.settings.max_frames = 1
    result = extract(path, service.settings)
    assert result.modality == "video"
    assert result.units[0].kind == "frame"
    assert result.units[0].locator["start_ms"] == 0
    assert "no_audio_stream" in result.warnings
    assert (service.settings.data_dir / "assets" / result.units[0].asset).is_file()


def test_worker_recovers_interrupted_job(service, corpus):
    import time

    job_id = service.indexer.create_job()
    service.store.execute("UPDATE jobs SET state='running' WHERE id=?", (job_id,))
    service.worker.start()
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            job = service.store.one("SELECT * FROM jobs WHERE id=?", (job_id,))
            if job["state"] == "completed":
                break
            time.sleep(0.02)
        assert job["state"] == "completed"
        assert job["skipped"] == 2
    finally:
        service.worker.stop()


@pytest.mark.skipif(os.name != "nt", reason="Windows case-insensitive path identity")
def test_windows_case_only_rename_updates_display_without_reembedding(service, corpus):
    before = service.models.calls
    (corpus / "graphs.txt").rename(corpus / "Graphs.txt")
    service.indexer.run(service.indexer.create_job())
    result = service.search.run(SearchRequest(query="Dijkstra", mode="lexical"))["results"][0]
    assert result["name"] == "Graphs.txt"
    assert result["relative_path"] == "Graphs.txt"
    assert service.models.calls == before


@pytest.mark.skipif(os.name != "nt", reason="Windows hidden attribute")
def test_windows_hiding_an_indexed_file_removes_it_from_search(service, corpus):
    import ctypes

    path = corpus / "graphs.txt"
    kernel = ctypes.windll.kernel32
    kernel.GetFileAttributesW.argtypes = [ctypes.c_wchar_p]
    kernel.GetFileAttributesW.restype = ctypes.c_uint32
    kernel.SetFileAttributesW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32]
    original = kernel.GetFileAttributesW(str(path))
    assert kernel.SetFileAttributesW(str(path), original | 2)
    try:
        service.indexer.run(service.indexer.create_job())
        assert not service.search.run(SearchRequest(query="Dijkstra", mode="lexical"))["results"]
    finally:
        kernel.SetFileAttributesW(str(path), original)


def test_filename_only_image_does_not_require_text_reranking(service, corpus):
    Image.new("RGB", (64, 64), "white").save(corpus / "holiday.png")
    service.indexer.run(service.indexer.create_job())
    output = service.search.run(SearchRequest(query="holiday", mode="lexical", rerank=True))
    assert output["results"][0]["name"] == "holiday.png"
    assert output["results"][0]["ranking"] == "lexical"
