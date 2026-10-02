from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any

from PIL import Image

from fileora.config import Settings
from fileora.domain import Extraction, FileoraError, Unit


def libreoffice_command() -> str | None:
    configured = os.getenv("FILEORA_LIBREOFFICE_CMD")
    if configured:
        return configured if Path(configured).is_file() else None
    for command in ("soffice.com", "soffice", "libreoffice"):
        found = shutil.which(command)
        if found:
            return found
    for name in ("ProgramFiles", "ProgramFiles(x86)"):
        folder = os.getenv(name)
        if folder:
            candidate = Path(folder) / "LibreOffice" / "program" / "soffice.com"
            if candidate.is_file():
                return str(candidate)
    return None


def convert_legacy(path: Path, directory: Path, settings: Settings) -> Path:
    command = libreoffice_command()
    if not command:
        raise FileoraError(
            "LEGACY_PPT_UNAVAILABLE",
            "Save this .ppt as .pptx in PowerPoint, or install local LibreOffice for automatic conversion",
        )
    profile = directory / "profile"
    (profile / "user").mkdir(parents=True)
    # A private profile avoids interfering with an open LibreOffice session.
    # No trusted locations; macros, active content, and external links disabled.
    (profile / "user" / "registrymodifications.xcu").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<oor:items xmlns:oor="http://openoffice.org/2001/registry">'
        '<item oor:path="/org.openoffice.Office.Common/Security/Scripting">'
        '<prop oor:name="DisableMacrosExecution" oor:op="fuse"><value>true</value></prop>'
        '<prop oor:name="DisableActiveContent" oor:op="fuse"><value>true</value></prop>'
        '<prop oor:name="BlockUntrustedRefererLinks" oor:op="fuse"><value>true</value></prop>'
        "</item></oor:items>",
        encoding="utf-8",
    )
    output = directory / "converted"
    output.mkdir()
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.CREATE_NO_WINDOW
    try:
        process = subprocess.Popen(
            [
                command,
                f"-env:UserInstallation={profile.resolve().as_uri()}",
                "--headless",
                "--nologo",
                "--nodefault",
                "--norestore",
                "--convert-to",
                "pptx:Impress MS PowerPoint 2007 XML",
                "--outdir",
                str(output),
                str(path.resolve()),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
    except OSError as exc:
        raise FileoraError(
            "PPT_CONVERSION_FAILED", "Could not start local LibreOffice; save as .pptx instead"
        ) from exc
    try:
        process.wait(timeout=min(45, settings.extraction_timeout))
    except subprocess.TimeoutExpired as exc:
        try:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True,
                    timeout=5,
                    check=False,
                )
        except (OSError, subprocess.TimeoutExpired):
            pass
        finally:
            process.kill()
            process.wait(timeout=5)
        raise FileoraError(
            "PPT_CONVERSION_TIMEOUT",
            "Legacy PowerPoint conversion timed out; save as .pptx instead",
        ) from exc
    target = output / (path.stem + ".pptx")
    if process.returncode or not target.is_file():
        raise FileoraError(
            "PPT_CONVERSION_FAILED",
            "Could not convert this .ppt; open it locally and save as .pptx",
        )
    if target.stat().st_size > settings.max_file_bytes:
        raise FileoraError(
            "FILE_TOO_LARGE", "Converted presentation exceeds the configured size limit"
        )
    return target


def validate_package(path: Path, settings: Settings) -> None:
    try:
        with zipfile.ZipFile(path) as package:
            parts = package.infolist()
            if (
                len(parts) > 10000
                or sum(part.file_size for part in parts) > settings.max_file_bytes * 4
            ):
                raise FileoraError(
                    "PRESENTATION_TOO_LARGE", "Expanded presentation exceeds package limits"
                )
            if any(part.file_size > 20 * 1024 * 1024 for part in parts):
                raise FileoraError("PRESENTATION_TOO_LARGE", "A presentation part exceeds 20 MiB")
            if any(part.flag_bits & 1 for part in parts):
                raise FileoraError(
                    "ENCRYPTED_PRESENTATION", "Save an unencrypted copy of this presentation"
                )
            if "ppt/presentation.xml" not in package.namelist():
                raise FileoraError(
                    "PRESENTATION_UNREADABLE", "File is not a PowerPoint presentation"
                )
    except (zipfile.BadZipFile, OSError) as exc:
        raise FileoraError(
            "PRESENTATION_UNREADABLE",
            "Could not read this presentation; save an unencrypted .pptx copy",
        ) from exc


def extract_pptx(path: Path, settings: Settings, started: float | None = None) -> Extraction:
    try:
        from pptx import Presentation
        from pptx.enum.shapes import MSO_SHAPE_TYPE
    except ImportError as exc:
        raise FileoraError(
            "PRESENTATION_UNAVAILABLE",
            "Install the updated Fileora dependencies for PowerPoint support",
        ) from exc
    from fileora.presentation_ocr import PresentationOCR

    started = time.monotonic() if started is None else started
    validate_package(path, settings)
    try:
        deck = Presentation(str(path))
        if len(deck.slides) > 1000:
            raise FileoraError(
                "PRESENTATION_TOO_LARGE", "Presentation exceeds the 1,000-slide limit"
            )
        units, warnings = [], []
        image_tasks: list[tuple[int, Any, bool]] = []
        for number, slide in enumerate(deck.slides, 1):
            text: list[str] = []
            pictures: list[Any] = []

            def collect(shapes, text, pictures, depth=0):
                if depth > 32:
                    raise FileoraError(
                        "PRESENTATION_TOO_LARGE", "Slide shape nesting exceeds the limit"
                    )
                for shape in shapes:
                    if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
                        collect(shape.shapes, text, pictures, depth + 1)
                    elif shape.has_text_frame:
                        if shape.text_frame.text.strip():
                            text.append(shape.text_frame.text)
                    elif shape.has_table:
                        for row in shape.table.rows:
                            text.append(
                                " | ".join(cell.text for cell in row.cells if not cell.is_spanned)
                            )
                    elif shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                        pictures.append(shape)
                    elif shape.has_chart:
                        chart = shape.chart
                        if chart.has_title and chart.chart_title.has_text_frame:
                            text.append(chart.chart_title.text_frame.text)
                        for series in chart.series:
                            text.append(str(series.name))
                        for plot in chart.plots:
                            # Scatter/bubble plots have no categorical axis.
                            if hasattr(plot, "categories"):
                                text.extend(str(category.label) for category in plot.categories)

            collect(slide.shapes, text, pictures)
            if text:
                units.append(Unit("\n".join(text), locator={"slide": number, "section": "slide"}))
            if slide.has_notes_slide:
                notes = slide.notes_slide.notes_text_frame
                if notes is not None and notes.text.strip():
                    units.append(Unit(notes.text, locator={"slide": number, "section": "notes"}))
            if pictures and not settings.enable_ocr:
                warnings.append(f"slide_{number}:image_text_requires_ocr")
            elif pictures:
                image_tasks.extend(
                    (number, picture, len(" ".join(text)) >= 40) for picture in pictures
                )
            if not text and not pictures:
                warnings.append(f"slide_{number}:no_slide_text")
        # Publish native text even when optional image OCR exhausts its budget.
        budget = min(
            settings.ppt_ocr_seconds,
            max(0, settings.extraction_timeout - (time.monotonic() - started) - 5),
        )
        deadline = time.monotonic() + budget
        image_tasks.sort(key=lambda task: (task[2], -(task[1].width * task[1].height)))
        recognized: dict[str, Unit | None] = {}
        engine = PresentationOCR(settings) if image_tasks else None
        deferred = 0
        try:
            for index, (number, picture, _) in enumerate(image_tasks):
                try:
                    blob = picture.image.blob
                    digest = hashlib.sha256(blob).hexdigest()
                    locator = {"slide": number, "section": "image", "shape": picture.name}
                    if digest in recognized:
                        cached = recognized[digest]
                        if cached:
                            units.append(
                                Unit(
                                    cached.text,
                                    "ocr",
                                    {**cached.locator, **locator},
                                    asset=cached.asset,
                                )
                            )
                        continue
                    if (
                        time.monotonic() >= deadline
                        or len(recognized) >= settings.ppt_ocr_max_images
                    ):
                        deferred += 1
                        continue
                    assert engine is not None
                    unit = engine.recognize(
                        blob, locator, timeout=min(10, deadline - time.monotonic())
                    )
                    recognized[digest] = unit
                    if unit:
                        units.append(unit)
                except (
                    FileoraError,
                    OSError,
                    ValueError,
                    AttributeError,
                    KeyError,
                    TypeError,
                    Image.DecompressionBombError,
                ) as exc:
                    code = getattr(exc, "code", "IMAGE_UNREADABLE")
                    warnings.append(f"slide_{number}:{code}")
                    if code == "OCR_UNAVAILABLE":
                        deferred += len(image_tasks) - index - 1
                        break
            if deferred:
                warnings.append(
                    f"presentation_ocr_partial:{deferred}_images_not_processed;native_text_indexed"
                )
        finally:
            if engine:
                engine.close()
        return Extraction(units, warnings, "presentation")
    except FileoraError:
        raise
    except Exception as exc:
        raise FileoraError(
            "PRESENTATION_UNREADABLE", "Could not parse this presentation; resave it as .pptx"
        ) from exc


def extract_presentation(path: Path, settings: Settings) -> Extraction:
    if path.suffix.lower() != ".ppt":
        return extract_pptx(path, settings)
    started = time.monotonic()
    with tempfile.TemporaryDirectory(
        prefix=f"ppt-convert-{os.getpid()}-", dir=settings.data_dir
    ) as folder:
        result = extract_pptx(
            convert_legacy(path, Path(folder), settings), settings, started=started
        )
        result.warnings.append("legacy_ppt_converted_locally")
        return result
