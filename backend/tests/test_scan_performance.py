from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from fileora.config import VISION_MODEL
from fileora.domain import Unit
from fileora.retrieval import SearchRequest
from fileora.storage import json_dump


def forbid_extraction(*args):
    raise AssertionError("Unexpected extraction")


@pytest.mark.parametrize("extension", [".md", ".pdf", ".pptx", ".png", ".wav", ".mp4"])
@pytest.mark.parametrize("media", [False, True])
def test_original_revision_hashes_remain_compatible(service, extension, media):
    settings = service.settings
    settings.enable_media = media
    settings.enable_ocr = True
    settings.enable_vision = True
    # Reproduce the original insertion order independently of the new helper.
    legacy = {
        "extractor": 1,
        "chunker": 1,
        "budget": settings.chunk_tokens,
        "overlap": settings.overlap_tokens,
        "ocr": True,
        "vision": True,
        "media": media,
        "frames": settings.frame_interval,
    }
    if extension == ".pptx":
        from fileora.presentation_ocr import engine_identity

        legacy["presentation"] = {
            "version": 2,
            "ocr_seconds": settings.ppt_ocr_seconds,
            "ocr_max_images": settings.ppt_ocr_max_images,
            "ocr_engine": engine_identity(),
        }
    if extension in {".pdf", ".png"}:
        legacy["image_provenance"] = 1
    if extension in {".wav", ".mp4"}:
        legacy["media_provenance"] = 2
    for key, model in (("text", settings.text_model), ("vision", VISION_MODEL)):
        legacy[key] = (
            service.models.manifest(model) if service.models.available(model) else "not-prepared"
        )
    if media:
        legacy["speech"] = service.models.manifest("Systran/faster-whisper-base.en")
    expected = hashlib.sha256(json_dump(legacy).encode()).hexdigest()
    path = Path("original" + extension)
    assert expected in service.indexer.compatible_pipelines(path, for_extraction=True)
    if extension in {".md", ".pdf", ".pptx", ".png"}:
        settings.enable_media = not media
        assert expected in service.indexer.compatible_pipelines(path, for_extraction=True)


def test_unrelated_feature_changes_do_not_reextract_notes(service, corpus):
    service.settings.enable_ocr = service.settings.enable_media = service.settings.enable_vision = (
        True
    )
    service.indexer.extractor = forbid_extraction
    job = service.indexer.run(service.indexer.create_job())
    assert job["skipped"] == 2 and job["failed"] == job["indexed"] == 0


def test_copy_and_rename_reuse_complete_extraction_without_rechunking(service, corpus):
    before = service.store.rows(
        "SELECT text,locator FROM chunks WHERE revision_id=(SELECT active_revision_id FROM files WHERE name='semaphores.md') ORDER BY ordinal"
    )
    service.indexer.extractor = forbid_extraction
    shutil.copyfile(corpus / "semaphores.md", corpus / "copy.md")
    (corpus / "graphs.txt").rename(corpus / "renamed.txt")
    job = service.indexer.run(service.indexer.create_job())
    assert job["indexed"] == 2 and job["deleted"] == 1 and job["failed"] == 0
    after = service.store.rows(
        "SELECT text,locator FROM chunks WHERE revision_id=(SELECT active_revision_id FROM files WHERE name='copy.md') ORDER BY ordinal"
    )
    assert after == before
    assert (
        service.search.run(SearchRequest(query="Dijkstra", mode="lexical"))["results"][0]["name"]
        == "renamed.txt"
    )


def test_visual_enable_adds_vectors_using_existing_extraction(service, corpus, monkeypatch):
    path = corpus / "diagram.png"
    Image.new("RGB", (120, 80), "white").save(path)
    available = service.models.available
    profile = service.models.profile
    monkeypatch.setattr(
        service.models, "available", lambda model: model == VISION_MODEL or available(model)
    )
    monkeypatch.setattr(
        service.models,
        "profile",
        lambda modality="text": (
            {
                "id": "test-vision",
                "model": VISION_MODEL,
                "revision": "test",
                "dimension": 32,
                "config": {},
                "modality": "vision",
            }
            if modality == "vision"
            else profile(modality)
        ),
    )
    calls = []

    def encode(images):
        calls.extend(images)
        vector = np.zeros((len(images), 32), dtype=np.float32)
        vector[:, 0] = 1
        return vector

    monkeypatch.setattr(service.models, "encode_vision", encode, raising=False)
    service.indexer.run(service.indexer.create_job())
    # Simulate an old manifest-based pipeline lacking the explicit visual flag.
    # Availability is unchanged for extraction identity; model metadata remains exact.
    identity = service.indexer._pipeline_identity(path)
    identity.pop("visual_enabled")
    legacy = hashlib.sha256(json_dump(identity).encode()).hexdigest()
    service.store.execute(
        "UPDATE file_revisions SET pipeline_hash=? WHERE file_id=(SELECT id FROM files WHERE name='diagram.png')",
        (legacy,),
    )
    service.settings.enable_vision = True
    service.indexer.extractor = forbid_extraction
    job = service.indexer.run(service.indexer.create_job())
    assert job["failed"] == 0 and job["indexed"] == 1 and len(calls) == 1
    shutil.copyfile(path, corpus / "copy.png")
    job = service.indexer.run(service.indexer.create_job())
    assert job["failed"] == 0 and job["indexed"] == 1 and len(calls) == 1


def test_progress_is_complete_when_job_becomes_terminal(service, corpus):
    for i in range(80):
        (corpus / f"note-{i}.md").write_text(f"Example {i}")
    first = service.indexer.run(service.indexer.create_job())
    assert first["state"] == "completed" and first["processed"] == first["total"] == 82
    second = service.indexer.run(service.indexer.create_job())
    assert second["state"] == "completed" and second["skipped"] == second["total"] == 82


def test_missing_cached_preview_forces_real_extraction(service, corpus, monkeypatch):
    path = corpus / "original.png"
    Image.new("RGB", (120, 80), "white").save(path)
    service.indexer.run(service.indexer.create_job())
    asset = service.store.one("SELECT asset FROM chunks WHERE kind='image'")["asset"]
    (service.settings.data_dir / "assets" / asset).unlink()
    shutil.copyfile(path, corpus / "copy.png")
    calls = []
    original = service.indexer.extractor

    def extract(path, settings):
        calls.append(path.name)
        return original(path, settings)

    service.indexer.extractor = extract
    job = service.indexer.run(service.indexer.create_job())
    assert job["failed"] == 0 and calls == ["copy.png"]


def test_portable_ocr_worker_is_shared_and_closed_for_scanned_pdf(service, tmp_path, monkeypatch):
    from pypdf import PdfWriter

    from fileora import extraction, presentation_ocr

    pdf = tmp_path / "scanned.pdf"
    writer = PdfWriter()
    for _ in range(3):
        writer.add_blank_page(width=100, height=100)
    writer.write(pdf)
    service.settings.enable_ocr = True
    monkeypatch.delenv("FILEORA_TESSERACT_CMD", raising=False)
    monkeypatch.setattr(extraction.shutil, "which", lambda name: None)
    instances = []

    class Worker:
        def __init__(self, settings):
            self.calls = 0
            self.closed = False
            instances.append(self)

        def _portable(self, image, timeout):
            self.calls += 1
            return Unit("recognized word", "ocr", {"boxes": []})

        def close(self):
            self.closed = True

    monkeypatch.setattr(presentation_ocr, "PresentationOCR", Worker)
    result = extraction.extract(pdf, service.settings)
    assert len(result.units) == 3
    assert len(instances) == 1 and instances[0].calls == 3 and instances[0].closed
    assert extraction._portable_session.get() is None
