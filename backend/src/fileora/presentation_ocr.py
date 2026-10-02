"""Bounded PowerPoint OCR with one offline worker and content-addressed results."""

from __future__ import annotations

import hashlib
import io
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from PIL import Image, ImageOps

from fileora.config import Settings
from fileora.domain import FileoraError, Unit

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "ocr" / "recognize.cjs"


def engine_identity() -> str:
    native = os.getenv("FILEORA_TESSERACT_CMD") or shutil.which("tesseract")
    identity = ["ppt-ocr-v2", native or "portable", os.getenv("TESSDATA_PREFIX", "")]
    for path in (Path(native) if native else SCRIPT, SCRIPT.parent / "package-lock.json"):
        if path.is_file():
            stat = path.stat()
            identity.append(f"{stat.st_size}:{stat.st_mtime_ns}")
    return hashlib.sha256("|".join(identity).encode()).hexdigest()


class PresentationOCR:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.identity = engine_identity()
        self.cache = settings.data_dir / "ocr-cache"
        self.cache.mkdir(exist_ok=True)
        self.process: subprocess.Popen | None = None
        self.responses: queue.Queue = queue.Queue()

    def _start(self):
        node = shutil.which("node")
        if not node or not (SCRIPT.parent / "node_modules" / "@tesseract.js-data" / "eng").is_dir():
            raise FileoraError("OCR_UNAVAILABLE", "Prepare portable OCR or install local Tesseract")
        flags = 0
        if sys.platform == "win32":
            flags = subprocess.CREATE_NO_WINDOW
        self.process = subprocess.Popen(
            [node, str(SCRIPT), "--stream"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            bufsize=1,
            creationflags=flags,
            env={**os.environ, "FILEORA_OCR_CACHE": str(self.cache)},
        )
        process = self.process
        responses: queue.Queue = queue.Queue()
        self.responses = responses

        def receive():
            assert process.stdout is not None
            for line in process.stdout:
                responses.put(line)
            responses.put(None)

        threading.Thread(target=receive, daemon=True).start()

    def _portable(self, image, timeout: float) -> Unit | None:
        if self.process is None:
            self._start()
        process = self.process
        assert process is not None and process.stdin is not None
        with tempfile.NamedTemporaryFile(
            prefix="ocr-", suffix=".png", dir=self.settings.data_dir / "assets", delete=False
        ) as stream:
            temporary = Path(stream.name)
            image.save(stream, "PNG")
        try:
            process.stdin.write(json.dumps({"path": str(temporary)}) + "\n")
            process.stdin.flush()
            line = self.responses.get(timeout=max(0.01, timeout))
            if line is None:
                raise FileoraError("OCR_FAILED", "The local OCR worker exited")
            result = json.loads(line)
            if result.get("error"):
                raise FileoraError("OCR_FAILED", "An embedded image could not be recognized")
            words = result["words"]
            return (
                Unit(" ".join(w["text"] for w in words), "ocr", {"boxes": words}) if words else None
            )
        except queue.Empty as exc:
            self.close()
            raise FileoraError(
                "OCR_TIMEOUT", "Presentation image OCR reached its time budget"
            ) from exc
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise FileoraError(
                "OCR_FAILED", "The local OCR worker could not process this image"
            ) from exc
        finally:
            temporary.unlink(missing_ok=True)

    def recognize(self, blob: bytes, locator: dict, timeout: float) -> Unit | None:
        from fileora.extraction import ocr_image, thumbnail

        key = (
            "ppt-"
            + hashlib.sha256(
                (self.identity + hashlib.sha256(blob).hexdigest()).encode()
            ).hexdigest()
        )
        target = self.cache / (key + ".json")
        with Image.open(io.BytesIO(blob)) as source:
            if source.width * source.height > self.settings.max_image_pixels:
                raise FileoraError("IMAGE_TOO_LARGE", "Embedded slide image exceeds pixel limit")
            cached = None
            try:
                if target.stat().st_size <= 4 * 1024 * 1024:
                    cached = json.loads(target.read_text(encoding="utf-8"))
                    if (
                        not isinstance(cached, dict)
                        or not isinstance(cached.get("text"), str)
                        or not isinstance(cached.get("boxes"), list)
                        or (
                            cached["text"]
                            and (
                                not isinstance(cached.get("asset"), str)
                                or Path(cached["asset"]).name != cached["asset"]
                                or not cached["asset"].endswith(".jpg")
                            )
                        )
                    ):
                        cached = None
            except (OSError, ValueError):
                pass
            if cached is not None and (
                not cached["text"]
                or (self.settings.data_dir / "assets" / cached.get("asset", "missing")).is_file()
            ):
                return (
                    Unit(
                        cached["text"],
                        "ocr",
                        {**locator, "boxes": cached["boxes"], "ocr_cache_key": key},
                        asset=cached.get("asset"),
                    )
                    if cached["text"]
                    else None
                )
            rgb = ImageOps.exif_transpose(source).convert("RGB")
            rgb.thumbnail((1600, 1600))
            if os.getenv("FILEORA_TESSERACT_CMD") or shutil.which("tesseract"):
                unit = ocr_image(rgb, {}, self.settings, timeout=timeout)
            else:
                unit = self._portable(rgb, timeout)
            asset = thumbnail(rgb, self.settings, key) if unit else None
            payload = {
                "text": unit.text if unit else "",
                "boxes": unit.locator.get("boxes", []) if unit else [],
                "asset": asset,
            }
            # Atomic publication avoids accepting half-written OCR after cancellation.
            temp = target.with_suffix(".tmp")
            try:
                encoded = json.dumps(payload)
                if len(encoded.encode("utf-8")) <= 4 * 1024 * 1024:
                    temp.write_text(encoded, encoding="utf-8")
                    temp.replace(target)
            except OSError:
                temp.unlink(missing_ok=True)
            return (
                Unit(
                    payload["text"],
                    "ocr",
                    {**locator, "boxes": payload["boxes"], "ocr_cache_key": key},
                    asset=asset,
                )
                if unit
                else None
            )

    def close(self):
        process, self.process = self.process, None
        if process is not None:
            if process.stdin:
                try:
                    process.stdin.close()
                except OSError:
                    pass
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
