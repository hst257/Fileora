from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from typing import Any, cast

import numpy as np

from fileora.config import RERANK_MODEL, VISION_MODEL, Settings
from fileora.domain import FileoraError


def model_directory(settings: Settings, model: str) -> Path:
    return (settings.models_dir or settings.data_dir / "models") / model.replace("/", "--")


def prepare_model(settings: Settings, model: str, revision: str | None = None) -> dict:
    """The only download path. Normal inference only uses local artifacts."""
    try:
        from huggingface_hub import HfApi, snapshot_download
    except ImportError as exc:
        raise FileoraError("ML_NOT_INSTALLED", "Install backend[ml] to download models") from exc
    info = HfApi().model_info(model, revision=revision)
    sha = info.sha
    directory = model_directory(settings, model)
    manifest_path = directory / "fileora-manifest.json"
    if manifest_path.exists() and Models(settings).available(model):
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing.get("revision") == sha:
            return existing
        raise FileoraError(
            "MODEL_REVISION_CONFLICT",
            "This cache already contains a different revision. Use a new --models-dir for comparison",
            409,
        )
    directory.mkdir(parents=True, exist_ok=True)
    siblings = {item.rfilename for item in (info.siblings or [])}
    legacy_clip = model == VISION_MODEL and "model.safetensors" not in siblings
    snapshot_download(
        model,
        revision=sha,
        local_dir=directory,
        allow_patterns=[
            "*.json",
            "*.txt",
            "*.safetensors",
            "*.model",
            "*.bin"
            if model.startswith("Systran/")
            else ("pytorch_model.bin" if legacy_clip else "*.safetensors"),
        ],
    )
    if legacy_clip:
        # This official, pinned CLIP checkpoint predates safetensors. Convert once using
        # PyTorch's restricted weights-only loader; inference never loads pickle files.
        import torch
        from safetensors.torch import save_file

        weights = torch.load(directory / "pytorch_model.bin", map_location="cpu", weights_only=True)
        save_file(
            {key: value.contiguous() for key, value in weights.items()},
            str(directory / "model.safetensors"),
        )
        (directory / "pytorch_model.bin").unlink()
    if not model.startswith("Systran/") and not list(directory.glob("*.safetensors")):
        raise FileoraError(
            "MODEL_ARTIFACT_MISSING", "Download did not produce safe model weights", 503
        )
    manifest = {"model": model, "revision": sha}
    (directory / "fileora-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return manifest


class Models:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.lock = threading.RLock()
        self.loaded: dict = {}
        self.device = "cpu"

    def manifest(self, model: str) -> dict:
        path = model_directory(self.settings, model) / "fileora-manifest.json"
        if not path.exists():
            raise FileoraError(
                "MODEL_UNAVAILABLE",
                f"Prepare the local model with: fileora models download {model}",
                503,
            )
        return json.loads(path.read_text(encoding="utf-8"))

    def available(self, model: str) -> bool:
        directory = model_directory(self.settings, model)
        weights = list(directory.glob("*.safetensors"))
        if model.startswith("Systran/"):
            weights = list(directory.glob("model.bin"))
        return (directory / "fileora-manifest.json").is_file() and bool(weights)

    def profile(self, modality: str = "text") -> dict:
        model = self.settings.text_model if modality == "text" else VISION_MODEL
        manifest = self.manifest(model)
        config = {
            "normalized": True,
            "dtype": "float32",
            "instructions": "Represent this sentence for searching relevant passages: "
            if model == "BAAI/bge-small-en-v1.5"
            else "",
            "preprocessing": "fileora-1",
        }
        identity = {**manifest, "config": config, "modality": modality}
        pid = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:24]
        return {
            "id": pid,
            **manifest,
            "dimension": 384 if modality == "text" else 512,
            "config": config,
            "modality": modality,
        }

    def _device(self) -> str:
        import torch

        requested = self.settings.device
        return "cuda" if requested != "cpu" and torch.cuda.is_available() else "cpu"

    def text(self):
        model = self.settings.text_model
        self.manifest(model)
        if model not in self.loaded:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise FileoraError(
                    "ML_NOT_INSTALLED", "Install backend[ml] for semantic search", 503
                ) from exc
            self.device = self._device()
            self.loaded[model] = SentenceTransformer(
                str(model_directory(self.settings, model)),
                device=self.device,
                local_files_only=True,
                trust_remote_code=False,
                model_kwargs={"use_safetensors": True},
            )
        return self.loaded[model]

    def tokenizer(self):
        if not self.available(self.settings.text_model):
            return None
        with self.lock:
            model = self.text()
            model.tokenizer.model_max_length = min(
                model.tokenizer.model_max_length, model.max_seq_length
            )
            return model.tokenizer

    def encode_text(self, texts: list[str], query: bool = False) -> np.ndarray:
        if not texts:
            return np.empty((0, self.profile()["dimension"]), dtype=np.float32)
        with self.lock:
            model = self.text()
            if query:
                prefix = self.profile()["config"]["instructions"]
                texts = [prefix + text for text in texts]
            batch = 32 if self.device == "cuda" else 16
            while True:
                try:
                    return np.asarray(
                        model.encode(
                            texts,
                            batch_size=batch,
                            normalize_embeddings=True,
                            show_progress_bar=False,
                        ),
                        dtype=np.float32,
                    )
                except RuntimeError as exc:
                    if "out of memory" not in str(exc).lower():
                        raise
                    if batch > 1:
                        batch = max(1, batch // 2)
                    elif self.device == "cuda":
                        model.to("cpu")
                        self.device = "cpu"
                    else:
                        raise FileoraError(
                            "INFERENCE_OOM", "Insufficient RAM for embedding inference", 503
                        ) from exc

    def _vision(self):
        self.manifest(VISION_MODEL)
        if VISION_MODEL not in self.loaded:
            try:
                from transformers import CLIPModel, CLIPProcessor
            except ImportError as exc:
                raise FileoraError(
                    "ML_NOT_INSTALLED", "Install backend[ml] for visual search", 503
                ) from exc
            device = self._device()
            path = str(model_directory(self.settings, VISION_MODEL))
            self.loaded[VISION_MODEL] = (
                cast(Any, CLIPModel)
                .from_pretrained(path, local_files_only=True, use_safetensors=True)
                .to(device)
                .eval(),
                cast(Any, CLIPProcessor).from_pretrained(path, local_files_only=True),
                device,
            )
        return self.loaded[VISION_MODEL]

    def encode_vision(self, items: list, query: bool = False) -> np.ndarray:
        import torch

        with self.lock:
            model, processor, device = self._vision()
            outputs = []
            for start in range(0, len(items), 8):
                batch = items[start : start + 8]
                if query and any(
                    len(processor.tokenizer(text)["input_ids"]) > 77 for text in batch
                ):
                    raise FileoraError(
                        "VISUAL_QUERY_TOO_LONG", "CLIP queries may contain at most 77 model tokens"
                    )
                inputs = (
                    processor(text=batch, return_tensors="pt", padding=True, truncation=False)
                    if query
                    else processor(images=batch, return_tensors="pt")
                )
                try:
                    with torch.inference_mode():
                        features = (
                            model.get_text_features(**inputs.to(device))
                            if query
                            else model.get_image_features(**inputs.to(device))
                        )
                except RuntimeError as exc:
                    if "out of memory" not in str(exc).lower() or device == "cpu":
                        raise
                    model.to("cpu")
                    device = "cpu"
                    self.loaded[VISION_MODEL] = (model, processor, device)
                    with torch.inference_mode():
                        features = (
                            model.get_text_features(**inputs.to(device))
                            if query
                            else model.get_image_features(**inputs.to(device))
                        )
                if not isinstance(features, torch.Tensor):
                    features = features.pooler_output
                outputs.append(
                    torch.nn.functional.normalize(features, dim=-1).cpu().numpy().astype(np.float32)
                )
            return np.concatenate(outputs) if outputs else np.empty((0, 512), dtype=np.float32)

    def rerank(self, query: str, passages: list[str]) -> list[float]:
        with self.lock:
            self.manifest(RERANK_MODEL)
            if RERANK_MODEL not in self.loaded:
                from sentence_transformers import CrossEncoder

                self.loaded[RERANK_MODEL] = CrossEncoder(
                    str(model_directory(self.settings, RERANK_MODEL)),
                    device="cpu",
                    local_files_only=True,
                    trust_remote_code=False,
                )
            return [
                float(x)
                for x in self.loaded[RERANK_MODEL].predict([(query, text) for text in passages])
            ]

    def unload(self) -> None:
        with self.lock:
            self.loaded.clear()
            try:
                import torch

                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except ImportError:
                pass
