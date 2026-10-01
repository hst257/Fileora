from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

TEXT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
VISION_MODEL = "openai/clip-vit-base-patch32"
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L6-v2"
TEXT_EXTENSIONS = {".txt", ".md", ".markdown"}
CODE_EXTENSIONS = {
    ".py",
    ".java",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".go",
    ".rs",
    ".sql",
}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}
AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac"}
VIDEO_EXTENSIONS = {".mp4", ".mkv"}
EXCLUDED = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    ".fileora",
    ".aws",
    ".ssh",
    ".codex",
    ".agents",
}


def default_data_dir() -> Path:
    configured = os.getenv("FILEORA_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    base = Path(os.getenv("LOCALAPPDATA", str(Path.home() / ".local" / "share")))
    return base / "Fileora"


@dataclass
class Settings:
    data_dir: Path = field(default_factory=default_data_dir)
    models_dir: Path | None = None
    text_model: str = TEXT_MODEL
    min_text_similarity: float | None = None
    min_vision_similarity: float = 0.28
    device: str = "auto"
    chunk_tokens: int = 192
    overlap_tokens: int = 32
    max_file_bytes: int = 50 * 1024 * 1024
    extraction_timeout: float = 60
    max_image_pixels: int = 40_000_000
    max_media_seconds: int = 4 * 60 * 60
    frame_interval: int = 10
    max_frames: int = 1500
    enable_ocr: bool = False
    enable_media: bool = False
    enable_vision: bool = False
    watch: bool | None = None
    reconcile_seconds: int = 900
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:4b"
    frontend_dir: Path = field(
        default_factory=lambda: Path(__file__).resolve().parents[3] / "frontend" / "dist"
    )

    def __post_init__(self) -> None:
        self.data_dir = Path(self.data_dir).resolve()
        self.models_dir = (
            Path(self.models_dir).resolve() if self.models_dir else self.data_dir / "models"
        )
        if not 0 <= self.overlap_tokens < self.chunk_tokens:
            raise ValueError("Overlap must be smaller than the chunk token budget")
        if self.device not in {"auto", "cpu", "cuda"}:
            raise ValueError("Device must be auto, cpu, or cuda")
        if self.frame_interval < 1:
            raise ValueError("Frame interval must be positive")
        if not all(
            0 <= value <= 1 for value in (self.text_similarity_floor, self.min_vision_similarity)
        ):
            raise ValueError("Minimum similarity must be between zero and one")

    @property
    def text_similarity_floor(self) -> float:
        if self.min_text_similarity is not None:
            return self.min_text_similarity
        return 0.55 if self.text_model == "BAAI/bge-small-en-v1.5" else 0.35

    def prepare(self) -> None:
        for name in ("indexes", "assets", "models"):
            (self.data_dir / name).mkdir(parents=True, exist_ok=True)
        if self.models_dir:
            self.models_dir.mkdir(parents=True, exist_ok=True)
