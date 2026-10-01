from __future__ import annotations

import hashlib
import re

import numpy as np
import pytest

from fileora.config import Settings
from fileora.extraction import extract
from fileora.service import Service


class TestModels:
    """Deterministic test encoder, never exposed in the application."""

    __test__ = False

    def __init__(self, enabled=True):
        self.enabled = enabled
        self.device = "test"
        self.calls = 0

    def available(self, model):
        return self.enabled and model != "openai/clip-vit-base-patch32"

    def manifest(self, model):
        return {"model": model, "revision": "test-only"}

    def profile(self, modality="text"):
        if not self.enabled:
            from fileora.domain import FileoraError

            raise FileoraError("MODEL_UNAVAILABLE", "Test model unavailable", 503)
        return {
            "id": "test-profile",
            "model": "test-only",
            "revision": "test-only",
            "dimension": 32,
            "config": {"normalized": True},
            "modality": modality,
        }

    def tokenizer(self):
        return None

    def encode_text(self, texts, query=False):
        self.calls += len(texts)
        result = []
        for text in texts:
            vector = np.zeros(32, dtype=np.float32)
            for token in re.findall(r"\w+", text.lower()):
                vector[int(hashlib.sha256(token.encode()).hexdigest(), 16) % 32] += 1
            if not vector.any():
                vector[0] = 1
            result.append(vector / np.linalg.norm(vector))
        return np.stack(result)

    def unload(self):
        pass


@pytest.fixture
def service(tmp_path):
    settings = Settings(data_dir=tmp_path / "runtime", chunk_tokens=16, overlap_tokens=3)
    return Service(settings, TestModels(), extractor=extract)


@pytest.fixture
def corpus(tmp_path, service):
    folder = tmp_path / "notes"
    folder.mkdir()
    (folder / "semaphores.md").write_text(
        "# Semaphores\nSemaphores protect critical sections.\nThreads coordinate using wait and signal.\n",
        encoding="utf-8",
    )
    (folder / "graphs.txt").write_text(
        "Dijkstra shortest path uses a priority queue and nonnegative edge weights.",
        encoding="utf-8",
    )
    service.indexer.add_root(str(folder))
    service.indexer.run(service.indexer.create_job())
    return folder
