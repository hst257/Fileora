from __future__ import annotations

import hashlib
import json
import multiprocessing as mp
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from fileora.config import (
    AUDIO_EXTENSIONS,
    CODE_EXTENSIONS,
    IMAGE_EXTENSIONS,
    PRESENTATION_EXTENSIONS,
    VIDEO_EXTENSIONS,
    Settings,
)
from fileora.domain import Extraction, FileoraError, Unit


def text_file(path: Path) -> str:
    data = path.read_bytes()
    if b"\x00" in data and not data.startswith((b"\xff\xfe", b"\xfe\xff")):
        raise FileoraError("BINARY_FILE", "File is not a supported text encoding")
    try:
        return data.decode("utf-16" if data.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig")
    except UnicodeDecodeError as exc:
        raise FileoraError("UNSUPPORTED_ENCODING", "Save this file as UTF-8 or UTF-16") from exc


def code_units(path: Path, text: str) -> list[Unit]:
    if path.suffix.lower() not in {".py", ".java"}:
        return [Unit(text, "code", {"line_start": 1, "language": path.suffix[1:]})]
    try:
        from tree_sitter import Language, Parser

        if path.suffix.lower() == ".py":
            import tree_sitter_python

            kinds = {"function_definition", "class_definition"}
            language = tree_sitter_python.language()
        else:
            import tree_sitter_java

            kinds = {
                "method_declaration",
                "constructor_declaration",
                "class_declaration",
                "interface_declaration",
            }
            language = tree_sitter_java.language()
        parser = Parser(Language(language))
        tree = parser.parse(text.encode("utf-8"))
        if tree.root_node.has_error:
            return [
                Unit(
                    text,
                    "code",
                    {"line_start": 1, "language": path.suffix[1:], "parser": "fallback"},
                )
            ]
        nodes = []

        def visit(node):
            if node.type in kinds and node.type not in {
                "class_definition",
                "class_declaration",
                "interface_declaration",
            }:
                nodes.append(node)
                return
            for child in node.children:
                visit(child)

        visit(tree.root_node)
        encoded = text.encode("utf-8")
        result = []
        cursor = 0
        for node in nodes:
            if node.start_byte > cursor:
                gap = encoded[cursor : node.start_byte].decode("utf-8")
                if gap.strip():
                    result.append(
                        Unit(
                            gap,
                            "code",
                            {
                                "line_start": encoded[:cursor].count(b"\n") + 1,
                                "char_start": len(encoded[:cursor].decode("utf-8")),
                                "language": path.suffix[1:],
                            },
                        )
                    )
            name = node.child_by_field_name("name")
            result.append(
                Unit(
                    encoded[node.start_byte : node.end_byte].decode("utf-8"),
                    "code",
                    {
                        "line_start": node.start_point.row + 1,
                        "char_start": len(encoded[: node.start_byte].decode("utf-8")),
                        "language": path.suffix[1:],
                        "parser": "tree-sitter",
                    },
                    name.text.decode("utf-8") if name else "",
                )
            )
            cursor = node.end_byte
        tail = encoded[cursor:].decode("utf-8")
        if tail.strip():
            result.append(
                Unit(
                    tail,
                    "code",
                    {
                        "line_start": encoded[:cursor].count(b"\n") + 1,
                        "char_start": len(encoded[:cursor].decode("utf-8")),
                        "language": path.suffix[1:],
                    },
                )
            )
        return result or [Unit(text, "code", {"line_start": 1})]
    except ImportError:
        return [
            Unit(text, "code", {"line_start": 1, "language": path.suffix[1:], "parser": "fallback"})
        ]


def ocr_image(image, locator: dict, settings: Settings, timeout: float = 30) -> Unit | None:
    if not shutil.which("tesseract") and not os.getenv("FILEORA_TESSERACT_CMD"):
        return portable_ocr(image, locator, settings, timeout=timeout)
    try:
        import pytesseract

        if os.getenv("FILEORA_TESSERACT_CMD"):
            pytesseract.pytesseract.tesseract_cmd = os.environ["FILEORA_TESSERACT_CMD"]

        data = pytesseract.image_to_data(
            image, output_type=pytesseract.Output.DICT, timeout=timeout
        )
    except ImportError as exc:
        raise FileoraError("OCR_UNAVAILABLE", "Install backend[ocr] and Tesseract") from exc
    except Exception as exc:
        raise FileoraError(
            "OCR_FAILED", "Tesseract is unavailable or could not process this image"
        ) from exc
    words, boxes = [], []
    for i, word in enumerate(data["text"]):
        if word.strip():
            words.append(word)
            boxes.append(
                {
                    "text": word,
                    "x": data["left"][i],
                    "y": data["top"][i],
                    "width": data["width"][i],
                    "height": data["height"][i],
                }
            )
    return Unit(" ".join(words), "ocr", {**locator, "boxes": boxes}) if words else None


def portable_ocr(image, locator: dict, settings: Settings, timeout: float = 45) -> Unit | None:
    """Offline WebAssembly Tesseract fallback; no system installer required."""
    script = Path(__file__).resolve().parents[3] / "scripts" / "ocr" / "recognize.cjs"
    node = shutil.which("node")
    if not node or not (script.parent / "node_modules" / "@tesseract.js-data" / "eng").is_dir():
        raise FileoraError(
            "OCR_UNAVAILABLE",
            "Install Tesseract or run npm ci in scripts/ocr for portable local OCR",
        )
    cache = settings.data_dir / "ocr-cache"
    cache.mkdir(exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix="ocr-", suffix=".png", dir=settings.data_dir / "assets", delete=False
    ) as stream:
        temporary = Path(stream.name)
        image.save(stream, "PNG")
    try:
        output = subprocess.run(
            [node, str(script), str(temporary)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            env={**os.environ, "FILEORA_OCR_CACHE": str(cache)},
        )
        if output.returncode:
            raise FileoraError("OCR_FAILED", "Portable Tesseract could not recognize this image")
        result = json.loads(output.stdout)
        words = result["words"]
        return (
            Unit(" ".join(word["text"] for word in words), "ocr", {**locator, "boxes": words})
            if words
            else None
        )
    except (subprocess.TimeoutExpired, ValueError) as exc:
        raise FileoraError(
            "OCR_FAILED", "Portable OCR timed out or returned an invalid result"
        ) from exc
    finally:
        temporary.unlink(missing_ok=True)


def thumbnail(image, settings: Settings, key: str) -> str:
    image = image.convert("RGB")
    image.thumbnail((1280, 1280))
    name = hashlib.sha256(key.encode()).hexdigest() + ".jpg"
    image.save(settings.data_dir / "assets" / name, "JPEG", quality=85)
    return name


def extract(path: Path, settings: Settings) -> Extraction:
    ext = path.suffix.lower()
    if ext in PRESENTATION_EXTENSIONS:
        from fileora.presentations import extract_presentation

        return extract_presentation(path, settings)
    if ext == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(path)
        if reader.is_encrypted:
            raise FileoraError("ENCRYPTED_PDF", "Encrypted PDFs are not indexed")
        units, warnings = [], []
        rendered = None
        for i, page in enumerate(reader.pages, 1):
            content = page.get_contents()
            if content and len(content.get_data()) > 20 * 1024 * 1024:
                warnings.append(f"page_{i}:oversized_content")
                continue
            text = page.extract_text() or ""
            if text.strip():
                units.append(Unit(text, "text", {"page": i}))
            elif settings.enable_ocr:
                try:
                    import pypdfium2

                    if rendered is None:
                        rendered = pypdfium2.PdfDocument(path)
                    image = rendered[i - 1].render(scale=1.5).to_pil()
                    if image.width * image.height > settings.max_image_pixels:
                        raise FileoraError("IMAGE_TOO_LARGE", "Rendered page exceeds pixel limit")
                    unit = ocr_image(image, {"page": i}, settings)
                    if unit:
                        units.append(unit)
                    else:
                        warnings.append(f"page_{i}:empty_ocr")
                except (ImportError, FileoraError) as exc:
                    warnings.append(f"page_{i}:{getattr(exc, 'code', 'OCR_UNAVAILABLE')}")
            else:
                warnings.append(f"page_{i}:needs_ocr")
        return Extraction(units, warnings, "document")
    if ext in IMAGE_EXTENSIONS:
        from PIL import Image, ImageOps

        with Image.open(path) as original:
            if original.width * original.height > settings.max_image_pixels:
                raise FileoraError("IMAGE_TOO_LARGE", "Image exceeds the configured pixel limit")
            image = ImageOps.exif_transpose(original).convert("RGB")
            key = hashlib.sha256(path.read_bytes()).hexdigest()
            asset = thumbnail(image.copy(), settings, key)
            units = [Unit("", "image", {"width": image.width, "height": image.height}, asset=asset)]
            warnings = []
            if settings.enable_ocr:
                try:
                    unit = ocr_image(image, {}, settings)
                    if unit:
                        units.append(unit)
                except FileoraError as exc:
                    warnings.append(exc.code)
        return Extraction(units, warnings, "image")
    if ext in AUDIO_EXTENSIONS | VIDEO_EXTENSIONS:
        if not settings.enable_media:
            raise FileoraError(
                "MEDIA_DISABLED", "Enable media processing and prepare a Whisper model"
            )
        return media(path, settings)
    text = text_file(path)
    units = (
        code_units(path, text)
        if ext in CODE_EXTENSIONS
        else [Unit(text, "text", {"line_start": 1})]
    )
    return Extraction(units, [], "code" if ext in CODE_EXTENSIONS else "text")


def media(path: Path, settings: Settings) -> Extraction:
    try:
        import av
    except ImportError as exc:
        raise FileoraError("MEDIA_UNAVAILABLE", "Install backend[media]") from exc
    model_path = (
        settings.models_dir or settings.data_dir / "models"
    ) / "Systran--faster-whisper-base.en"
    units, warnings = [], []
    with av.open(str(path)) as container:
        duration = float(container.duration or 0) / 1_000_000
        if duration > settings.max_media_seconds:
            raise FileoraError("MEDIA_TOO_LONG", "Media exceeds the duration limit")
        has_audio = bool(container.streams.audio)
        if path.suffix.lower() in VIDEO_EXTENSIONS and container.streams.video:
            from PIL import Image

            next_time = 0.0
            previous = None
            count = 0
            for frame in container.decode(video=0):
                timestamp = float(frame.time or 0)
                if timestamp > settings.max_media_seconds:
                    break
                if timestamp < next_time:
                    continue
                next_time = timestamp + settings.frame_interval
                image = frame.to_image()
                if image.width * image.height > settings.max_image_pixels:
                    raise FileoraError("IMAGE_TOO_LARGE", "Video frame exceeds pixel limit")
                pixels = list(image.convert("L").resize((8, 8), Image.Resampling.LANCZOS).tobytes())
                mean = sum(pixels) / 64
                fingerprint = sum((p >= mean) << i for i, p in enumerate(pixels))
                if previous is not None and (fingerprint ^ previous).bit_count() <= 4:
                    continue
                previous = fingerprint
                key = f"{path}:{path.stat().st_mtime_ns}:{timestamp}"
                asset = thumbnail(image.copy(), settings, key)
                loc = {
                    "start_ms": int(timestamp * 1000),
                    "end_ms": int((timestamp + settings.frame_interval) * 1000),
                }
                units.append(Unit("", "frame", loc, asset=asset))
                if settings.enable_ocr:
                    try:
                        unit = ocr_image(image, loc, settings)
                        if unit:
                            units.append(unit)
                    except FileoraError as exc:
                        warnings.append(exc.code)
                count += 1
                if count >= settings.max_frames:
                    warnings.append("frame_limit_reached")
                    break
    if has_audio:
        if not (model_path / "fileora-manifest.json").exists():
            raise FileoraError("MODEL_UNAVAILABLE", "Prepare Systran/faster-whisper-base.en")
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise FileoraError("MEDIA_UNAVAILABLE", "Install backend[media]") from exc
        try:
            speech = WhisperModel(
                str(model_path),
                device="cuda" if settings.device == "cuda" else "cpu",
                compute_type="int8",
                local_files_only=True,
            )
        except RuntimeError:
            speech = WhisperModel(
                str(model_path), device="cpu", compute_type="int8", local_files_only=True
            )

        def transcribe(model):
            segments, _ = model.transcribe(str(path), language="en", vad_filter=True)
            return [
                Unit(
                    segment.text.strip(),
                    "transcript",
                    {"start_ms": int(segment.start * 1000), "end_ms": int(segment.end * 1000)},
                )
                for segment in segments
                if segment.text.strip()
            ]

        try:
            transcript = transcribe(speech)
        except RuntimeError:
            if settings.device != "cuda":
                raise
            del speech
            speech = WhisperModel(
                str(model_path), device="cpu", compute_type="int8", local_files_only=True
            )
            transcript = transcribe(speech)
            warnings.append("speech_cpu_fallback")
        units.extend(transcript)
    else:
        warnings.append("no_audio_stream")
    return Extraction(
        units, warnings, "video" if path.suffix.lower() in VIDEO_EXTENSIONS else "audio"
    )


def _child(connection, path: Path, settings: Settings) -> None:
    try:
        if sys.platform != "win32":
            os.setsid()  # Keep OCR/converter subprocesses in this extraction's group.
        connection.send((True, extract(path, settings)))
    except Exception as exc:
        connection.send(
            (
                False,
                (
                    getattr(exc, "code", "EXTRACTION_FAILED"),
                    getattr(exc, "message", "Could not extract this file"),
                ),
            )
        )
    finally:
        connection.close()


def supervised_extract(path: Path, settings: Settings, cancelled=None) -> Extraction:
    if cancelled and cancelled():
        raise FileoraError("CANCELLED", "Indexing was cancelled")
    ctx = mp.get_context("spawn")
    parent, child = ctx.Pipe(duplex=False)
    process = ctx.Process(target=_child, args=(child, path, settings), daemon=True)
    process.start()
    child.close()
    timeout = (
        settings.extraction_timeout
        if path.suffix.lower() not in AUDIO_EXTENSIONS | VIDEO_EXTENSIONS
        else settings.max_media_seconds
    )
    try:
        deadline = time.monotonic() + timeout
        while not parent.poll(0.2):
            if cancelled and cancelled():
                raise FileoraError("CANCELLED", "Indexing was cancelled")
            if time.monotonic() >= deadline:
                raise FileoraError("EXTRACTION_TIMEOUT", "Extraction exceeded its time budget")
        success, result = parent.recv()
        if not success:
            raise FileoraError(*result)
        return result
    except EOFError as exc:
        raise FileoraError(
            "EXTRACTOR_CRASHED", "The extractor process exited unexpectedly"
        ) from exc
    finally:
        parent.close()
        if sys.platform != "win32" and process.pid is not None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if process.is_alive():
            if os.name == "nt":
                # Include portable OCR's Node child when terminating the extractor.
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True,
                    timeout=5,
                    check=False,
                )
            process.terminate()
        process.join(timeout=5)
        if path.suffix.lower() == ".ppt" and not process.is_alive():
            # A forcibly stopped extractor cannot run TemporaryDirectory's cleanup.
            for folder in settings.data_dir.glob(f"ppt-convert-{process.pid}-*"):
                if folder.is_dir() and not folder.is_symlink():
                    shutil.rmtree(folder, ignore_errors=True)
