from __future__ import annotations

import shutil

import numpy as np
from PIL import Image
from pypdf import PdfWriter

import fileora.extraction as extraction
from fileora.config import VISION_MODEL
from fileora.domain import FileoraError, Unit
from fileora.retrieval import Filters, SearchRequest


def fake_ocr(image, locator, settings, **kwargs):
    return Unit(
        "BCNF determinant superkey",
        "ocr",
        {
            **locator,
            "boxes": [{"text": "BCNF", "x": 20, "y": 30, "width": 100, "height": 40}],
        },
    )


def test_image_ocr_carries_own_asset_and_dimensions(tmp_path, service, monkeypatch):
    path = tmp_path / "screenshot.png"
    Image.new("RGB", (2400, 1600), "white").save(path)
    service.settings.enable_ocr = True
    monkeypatch.setattr(extraction, "ocr_image", fake_ocr)
    result = extraction.extract(path, service.settings)
    image, ocr = result.units
    assert ocr.asset == image.asset
    assert ocr.locator["width"] == 2400 and ocr.locator["height"] == 1600
    with Image.open(service.settings.data_dir / "assets" / ocr.asset) as preview:
        assert preview.width == 1280
    assert ocr.locator["boxes"][0]["x"] == 20


def test_scanned_pdf_ocr_preview_stays_on_its_page(tmp_path, service, monkeypatch):
    path = tmp_path / "scan.pdf"
    writer = PdfWriter()
    for _ in range(2):
        writer.add_blank_page(width=300, height=200)
    writer.write(path)
    service.settings.enable_ocr = True
    monkeypatch.setattr(extraction, "ocr_image", fake_ocr)
    result = extraction.extract(path, service.settings)
    assert [u.locator["page"] for u in result.units] == [1, 2]
    assert len({u.asset for u in result.units}) == 2
    for unit in result.units:
        assert unit.locator["width"] == 450 and unit.locator["height"] == 300
        assert (service.settings.data_dir / "assets" / unit.asset).is_file()


def test_exact_image_words_and_no_match_filter(service, corpus, client, monkeypatch):
    Image.new("RGB", (400, 300), "white").save(corpus / "screenshot.png")
    service.settings.enable_ocr = True
    monkeypatch.setattr(extraction, "ocr_image", fake_ocr)
    service.indexer.run(service.indexer.create_job())
    found = client.post(
        "/api/v1/search", json={"query": "BCNF", "filters": {"modality": "image"}}
    ).json()
    result = found["results"][0]
    evidence = result["evidence"][0]
    assert result["match_kind"] == "terms"
    assert evidence["asset_url"] and evidence["locator"]["boxes"]
    assert evidence["locator"]["width"] == 400
    assert client.get(evidence["asset_url"]).headers["content-type"] == "image/jpeg"
    assert not service.search.run(
        SearchRequest(query="nonexistentword", filters=Filters(modality="image"))
    )["results"]
    for modality in ("code", "document"):
        assert not service.search.run(
            SearchRequest(query="BCNF", filters=Filters(modality=modality))
        )["results"]


def test_visual_index_survives_ocr_failure_and_obeys_similarity_floor(service, corpus, monkeypatch):
    Image.new("RGB", (400, 300), "white").save(corpus / "screenshot.png")
    service.settings.enable_ocr = service.settings.enable_vision = True

    def failed(*args, **kwargs):
        raise FileoraError("OCR_FAILED", "Unreadable text")

    monkeypatch.setattr(extraction, "ocr_image", failed)
    models = service.models
    available = models.available
    profile = models.profile
    monkeypatch.setattr(
        models, "available", lambda model: model == VISION_MODEL or available(model)
    )
    monkeypatch.setattr(
        models,
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
    vector = np.zeros((1, 32), dtype=np.float32)
    vector[0, 0] = 1
    monkeypatch.setattr(
        models,
        "encode_vision",
        lambda inputs, query=False: np.repeat(vector, len(inputs), axis=0),
        raising=False,
    )
    service.indexer.run(service.indexer.create_job())
    request = SearchRequest(
        query="a diagram without readable words",
        channels="vision",
        mode="semantic",
        filters=Filters(modality="image"),
    )
    result = service.search.run(request)["results"][0]
    assert result["match_kind"] == "visual" and "OCR_FAILED" in result["warnings"]
    # Default keyword searches do not substitute a visually similar image.
    assert not service.search.run(SearchRequest(query="BCNF", filters=Filters(modality="image")))[
        "results"
    ]
    vector[0, 0] = 0
    vector[0, 1] = 1
    assert not service.search.run(request)["results"]


def test_image_capabilities_follow_actual_installed_tools(client, service, monkeypatch):
    service.settings.enable_ocr = True
    monkeypatch.setattr(shutil, "which", lambda name: None)
    monkeypatch.delenv("FILEORA_TESSERACT_CMD", raising=False)
    health = client.get("/api/v1/health").json()
    assert not health["ocr_ready"] and health["ocr_engine"] is None
    assert not health["vision_ready"]
    monkeypatch.setenv("FILEORA_TESSERACT_CMD", str(service.settings.data_dir / "missing.exe"))
    assert not client.get("/api/v1/health").json()["ocr_ready"]


def test_image_provenance_upgrade_keeps_text_pipeline(service, corpus):
    assert service.indexer.pipeline_hash(corpus / "graphs.txt") == service.indexer.pipeline_hash()
    assert (
        service.indexer.pipeline_hash(corpus / "screenshot.png") != service.indexer.pipeline_hash()
    )
