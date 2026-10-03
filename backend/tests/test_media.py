from __future__ import annotations

import wave
from types import SimpleNamespace

import pytest
from PIL import Image

from fileora import extraction
from fileora.domain import FileoraError, Unit
from fileora.retrieval import Filters, SearchRequest


def video_fixture(monkeypatch, tmp_path, has_audio=False):
    av = pytest.importorskip("av")
    path = tmp_path / "lecture.mp4"
    path.write_bytes(b"decoder-fixture")
    image = Image.new("RGB", (640, 360), "white")
    frames = [SimpleNamespace(time=t, to_image=lambda: image) for t in (0, 1, 10)]

    class Container:
        duration = 30_000_000
        streams = SimpleNamespace(audio=has_audio, video=True)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def decode(self, **kwargs):
            return iter(frames)

    monkeypatch.setattr(av, "open", lambda *args, **kwargs: Container())
    return path


def test_sampled_frame_ocr_uses_matching_asset_and_coordinates(service, monkeypatch, tmp_path):
    path = video_fixture(monkeypatch, tmp_path)
    service.settings.enable_media = service.settings.enable_ocr = True
    monkeypatch.setattr(
        extraction,
        "ocr_image",
        lambda image, loc, settings: Unit("BCNF determinant", "ocr", dict(loc)),
    )
    result = extraction.extract(path, service.settings)
    frame, text = result.units
    assert frame.kind == "frame" and text.kind == "ocr"
    assert frame.asset == text.asset
    assert text.locator == {"start_ms": 0, "end_ms": 10000, "width": 640, "height": 360}
    # Repeated near-identical frames do not incur repeat OCR work.
    assert "no_audio_stream" in result.warnings


def test_video_preserves_frames_when_speech_setup_is_missing(service, monkeypatch, tmp_path):
    path = video_fixture(monkeypatch, tmp_path, has_audio=True)
    service.settings.enable_media = True
    result = extraction.extract(path, service.settings)
    assert result.units[0].kind == "frame"
    assert result.warnings == ["transcription_unavailable:MODEL_UNAVAILABLE"]


def test_audio_reports_missing_model_instead_of_succeeding_empty(service, monkeypatch, tmp_path):
    path = video_fixture(monkeypatch, tmp_path, has_audio=True).with_suffix(".wav")
    service.settings.enable_media = True
    with pytest.raises(FileoraError, match="Prepare") as exc:
        extraction.extract(path, service.settings)
    assert exc.value.code == "MODEL_UNAVAILABLE"


def test_timestamp_evidence_and_recording_ranges(client, service, corpus, monkeypatch):
    path = corpus / "lecture.wav"
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(b"\0\0" * 16000)
    service.settings.enable_media = True
    monkeypatch.setattr(
        extraction,
        "transcribe_media",
        lambda *args: [
            Unit("translation lookaside buffer", "transcript", {"start_ms": 300, "end_ms": 900})
        ],
    )
    service.indexer.run(service.indexer.create_job())
    result = service.search.run(
        SearchRequest(query="translation lookaside", filters=Filters(modality="audio"))
    )["results"][0]
    assert result["evidence"][0]["locator"]["start_ms"] == 300
    preview = client.get(
        f"/api/v1/files/{result['file_id']}/preview", headers={"Range": "bytes=0-43"}
    )
    assert preview.status_code == 206
    assert preview.headers["content-range"].startswith("bytes 0-43/")
    assert preview.content == path.read_bytes()[:44]
    assert not service.search.run(SearchRequest(query="BCNF", filters=Filters(modality="audio")))[
        "results"
    ]


def test_readiness_requires_enabled_media_tools_and_model(client, service, monkeypatch):
    monkeypatch.setattr("fileora.api.media_capability", lambda: {"decoder": True, "speech": True})
    health = client.get("/api/v1/health").json()
    assert health["speech_model_ready"] and not health["transcription_ready"]
    service.settings.enable_media = True
    assert client.get("/api/v1/health").json()["transcription_ready"]
    monkeypatch.setattr("fileora.api.media_capability", lambda: {"decoder": True, "speech": False})
    health = client.get("/api/v1/health").json()
    assert health["media_ready"] and not health["transcription_ready"]


def test_media_upgrade_does_not_change_unrelated_pipeline(service, corpus):
    assert service.indexer.pipeline_hash(corpus / "lecture.wav") != service.indexer.pipeline_hash()
    assert service.indexer.pipeline_hash(corpus / "notes.md") == service.indexer.pipeline_hash()


def test_transcript_intervals_stay_inside_recording(service, monkeypatch):
    whisper = pytest.importorskip("faster_whisper")
    model_path = service.settings.models_dir / "Systran--faster-whisper-base.en"
    model_path.mkdir()
    (model_path / "fileora-manifest.json").write_text("{}")

    class Speech:
        def __init__(self, *args, **kwargs):
            assert kwargs["local_files_only"] is True

        def transcribe(self, *args, **kwargs):
            return iter(
                [
                    SimpleNamespace(start=-1, end=2, text="first phrase"),
                    SimpleNamespace(start=8, end=15, text="final phrase"),
                    SimpleNamespace(start=12, end=15, text="outside recording"),
                ]
            ), None

    monkeypatch.setattr(whisper, "WhisperModel", Speech)
    units = extraction.transcribe_media(
        model_path / "recording.wav", service.settings, model_path, [], duration=10
    )
    assert [unit.locator for unit in units] == [
        {"start_ms": 0, "end_ms": 2000},
        {"start_ms": 8000, "end_ms": 10000},
    ]


def test_media_preference_survives_restart_and_explicit_override(client, service):
    from fileora.config import Settings
    from fileora.service import Service

    assert not service.settings.enable_media
    response = client.put("/api/v1/index/media", json={"enabled": True})
    assert response.status_code == 200 and response.json()["enabled"]
    assert Service(
        Settings(data_dir=service.settings.data_dir), service.models
    ).settings.enable_media
    assert not Service(
        Settings(data_dir=service.settings.data_dir, enable_media=False), service.models
    ).settings.enable_media
    assert Service(
        Settings(data_dir=service.settings.data_dir), service.models
    ).settings.enable_media
    assert client.put("/api/v1/index/media", json={"enabled": False}).status_code == 200
    assert not Service(
        Settings(data_dir=service.settings.data_dir), service.models
    ).settings.enable_media


def test_media_preference_rejects_mid_scan_change(client, service):
    service.store.execute("INSERT INTO jobs(id,state,verify) VALUES('busy-media-test','running',0)")
    response = client.put("/api/v1/index/media", json={"enabled": True})
    assert response.status_code == 409
    assert not service.settings.enable_media
    assert not service.store.one("SELECT value FROM app_meta WHERE key='media_enabled'")
