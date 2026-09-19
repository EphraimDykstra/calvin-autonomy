"""Optional local OCR adapter.

This module is the only place that runs an OCR engine.  It performs no
network access and never executes content embedded in a source document: a
page image is handed to the engine as a plain file, in a separate process, and
only that process's standard output is read back.

Two engines are supported.  RapidOCR (``rapidocr-onnxruntime``) is the
default: it installs from a pip wheel with its models bundled, so it needs no
system package manager on macOS, Windows, or Linux.  Tesseract is preferred
whenever its binary is already on PATH.  Both are for bulk archive scans of
printed pages.  Neither reads handwriting reliably, so a photographed or
handwritten worksheet is read by the host's own vision and recorded through
``ocr-import`` instead.

The adapter is deliberately incapable of reporting a success it did not
achieve.  Every helper here either returns engine text it actually received
or raises :class:`OcrError`; the caller converts that into a fail-closed
result and leaves the review queue untouched.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

try:
    from PIL import Image
except Exception:  # pragma: no cover - exercised when an optional install is absent
    Image = None  # type: ignore[assignment,misc]

try:
    import pypdfium2 as _pdfium
except Exception:  # pragma: no cover - exercised when the optional install is absent
    _pdfium = None  # type: ignore[assignment]

TESSERACT = "tesseract"
RAPIDOCR = "rapidocr"
RAPIDOCR_MODULE = "rapidocr_onnxruntime"
RAPIDOCR_DISTRIBUTION = "rapidocr-onnxruntime"
# The preferred engine.  The engine that actually ran is what provenance
# records, never this constant.
ENGINE_NAME = TESSERACT
HANDWRITING_LIMIT = (
    "printed text only: neither engine reads handwriting reliably, so handwritten "
    "pages are read by the host and recorded through ocr-import"
)
RASTERIZER_NAME = "pypdfium2"
RASTER_DPI = 200
OCR_TIMEOUT_SECONDS = 120
MAX_ENGINE_OUTPUT_BYTES = 4 * 1024 * 1024
MAX_FRAME_PIXELS = 40_000_000


@dataclass(frozen=True)
class Engine:
    """The OCR engine selected for this machine.

    ``location`` is the executable path for Tesseract and the Python module
    name for RapidOCR.
    """

    name: str
    location: str


# A probe reports which engine is available, or None when none is.  A runner
# turns one page image into raw engine text.  Both are injectable so that the
# unavailable, blank-output, and failure branches stay testable on a machine
# (or CI runner) with no OCR engine installed.  A probe may also return a bare
# executable path, which names a Tesseract binary.
Probe = Callable[[], "Engine | str | None"]
Runner = Callable[[Path], str]


class OcrError(RuntimeError):
    """An OCR attempt failed. Carries a stable machine-readable reason."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message


def rapidocr_available() -> bool:
    """Whether the RapidOCR wheel is installed, checked without importing it.

    Importing it loads onnxruntime and OpenCV, a cost every CLI call would pay;
    the engine is imported only inside the worker process that uses it.
    """
    try:
        return importlib.util.find_spec(RAPIDOCR_MODULE) is not None
    except (ImportError, ValueError):
        return False


def engine_probe() -> Engine | None:
    """Return the engine to use: Tesseract when present, else RapidOCR, else None."""
    executable = shutil.which(TESSERACT)
    if executable:
        return Engine(TESSERACT, executable)
    if rapidocr_available():
        return Engine(RAPIDOCR, RAPIDOCR_MODULE)
    return None


def as_engine(found: "Engine | str | None") -> Engine | None:
    """Normalize a probe result; a bare string is a Tesseract executable path."""
    if found is None or isinstance(found, Engine):
        return found
    if isinstance(found, str) and found:
        return Engine(TESSERACT, found)
    raise TypeError("an OCR probe must return an Engine, an executable path, or None")


def engine_version(engine: "Engine | str") -> str | None:
    """Best-effort engine version. A failure here never blocks a transcription."""
    engine = as_engine(engine)
    if engine is None:
        return None
    if engine.name == RAPIDOCR:
        try:
            from importlib.metadata import version

            return f"{RAPIDOCR_DISTRIBUTION} {version(RAPIDOCR_DISTRIBUTION)}"[:200]
        except Exception:
            return None
    executable = engine.location
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [executable, "--version"],
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    text = (completed.stdout or b"").decode("utf-8", errors="replace")
    first = text.strip().splitlines()[0].strip() if text.strip() else ""
    return first[:200] or None


def build_runner(executable: str, *, timeout: float = OCR_TIMEOUT_SECONDS) -> Runner:
    """Build a bounded runner that shells out to the engine for one image."""

    def run(image_path: Path) -> str:
        try:
            completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
                [executable, str(image_path), "stdout"],
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise OcrError("engine_timeout", f"OCR engine timed out after {timeout:g}s") from exc
        except OSError as exc:
            raise OcrError("engine_failed", f"OCR engine could not be run: {exc}") from exc
        if completed.returncode != 0:
            detail = (completed.stderr or b"").decode("utf-8", errors="replace").strip()
            raise OcrError(
                "engine_failed",
                f"OCR engine exited with status {completed.returncode}"
                + (f": {detail[:500]}" if detail else ""),
            )
        stdout = completed.stdout or b""
        if len(stdout) > MAX_ENGINE_OUTPUT_BYTES:
            raise OcrError("engine_output_too_large", "OCR engine output exceeded the safety limit")
        return stdout.decode("utf-8", errors="replace")

    return run


def build_rapidocr_runner(*, timeout: float = OCR_TIMEOUT_SECONDS) -> Runner:
    """Build a bounded runner that reads one image with RapidOCR.

    The engine runs in a child interpreter rather than in-process, as Tesseract
    does: the parent enforces the timeout and the output bound, and a native
    crash in onnxruntime cannot take the CLI down with it.
    """

    def run(image_path: Path) -> str:
        try:
            completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
                [sys.executable, "-m", "engineering_assistant.ocr", RAPIDOCR, str(image_path)],
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise OcrError("engine_timeout", f"OCR engine timed out after {timeout:g}s") from exc
        except OSError as exc:
            raise OcrError("engine_failed", f"OCR engine could not be run: {exc}") from exc
        if completed.returncode != 0:
            detail = (completed.stderr or b"").decode("utf-8", errors="replace").strip()
            raise OcrError(
                "engine_failed",
                f"OCR engine exited with status {completed.returncode}"
                + (f": {detail[-500:]}" if detail else ""),
            )
        stdout = completed.stdout or b""
        if len(stdout) > MAX_ENGINE_OUTPUT_BYTES:
            raise OcrError("engine_output_too_large", "OCR engine output exceeded the safety limit")
        return stdout.decode("utf-8", errors="replace")

    return run


def engine_runner(engine: "Engine | str", *, timeout: float = OCR_TIMEOUT_SECONDS) -> Runner:
    """Build the runner for whichever engine the probe selected."""
    engine = as_engine(engine)
    if engine is None:
        raise OcrError("engine_unavailable", "no local OCR engine is installed")
    if engine.name == RAPIDOCR:
        return build_rapidocr_runner(timeout=timeout)
    return build_runner(engine.location, timeout=timeout)


def reading_order(detections: object) -> str:
    """Join RapidOCR detections into page text in reading order.

    RapidOCR returns one ``[box, text, score]`` entry per detected text run,
    and one printed line is often split into several runs.  Runs whose
    vertical centres fall within half a run-height of the line they follow are
    the same line, read left to right; lines are read top to bottom.
    """
    runs: list[tuple[float, float, float, str]] = []
    for item in detections or []:
        try:
            box, text = item[0], item[1]
            ys = [float(point[1]) for point in box]
            xs = [float(point[0]) for point in box]
        except (TypeError, ValueError, IndexError):
            continue
        if not isinstance(text, str) or not text.strip() or not ys:
            continue
        top, bottom = min(ys), max(ys)
        runs.append(((top + bottom) / 2, max(bottom - top, 1.0), min(xs), text.strip()))
    runs.sort(key=lambda run: (run[0], run[2]))
    lines: list[list[tuple[float, float, float, str]]] = []
    for run in runs:
        if lines:
            current = lines[-1]
            centre = sum(item[0] for item in current) / len(current)
            height = max(item[1] for item in current)
            if abs(run[0] - centre) <= height / 2:
                current.append(run)
                continue
        lines.append([run])
    return "\n".join(
        " ".join(item[3] for item in sorted(line, key=lambda item: item[2])) for line in lines
    )


def _rapidocr_worker(image_path: str) -> int:
    """Child-process entry point: print one image's text, or exit non-zero."""
    try:
        from rapidocr_onnxruntime import RapidOCR
    except Exception as exc:  # pragma: no cover - exercised when the wheel is absent
        print(f"rapidocr is unavailable: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 3
    result = RapidOCR()(image_path)
    detections = result[0] if isinstance(result, tuple) else result
    sys.stdout.buffer.write(reading_order(detections).encode("utf-8"))
    return 0


def _normalize(text: object) -> str:
    if not isinstance(text, str):
        raise OcrError("engine_output_invalid", "OCR engine returned a non-text result")
    if "\x00" in text:
        raise OcrError("engine_output_invalid", "OCR engine output contained a NUL byte")
    return text.replace("\r\n", "\n").replace("\r", "\n").strip()


def transcribe_frames(
    source: Path,
    frames: list[int],
    runner: Runner,
) -> list[dict[str, str]]:
    """Transcribe the named 1-based image frames, or fail closed.

    Every requested frame must yield non-blank text.  A frame the engine reads
    as blank raises rather than silently producing an empty or partial
    transcription, because a partial result cannot satisfy the importer's
    all-or-nothing locator coverage and must never look like a success.
    """
    if Image is None:  # pragma: no cover - exercised when an optional install is absent
        raise OcrError("pillow_unavailable", "Pillow is unavailable; page images cannot be prepared")
    source = Path(source)
    blocks: list[dict[str, str]] = []
    with tempfile.TemporaryDirectory(prefix="coursework-ocr-") as scratch:
        scratch_dir = Path(scratch)
        for frame in frames:
            image_path = scratch_dir / f"frame-{frame}.png"
            try:
                with Image.open(source) as image:
                    total = int(getattr(image, "n_frames", 1) or 1)
                    if frame < 1 or frame > total:
                        raise OcrError(
                            "frame_missing",
                            f"image frame {frame} is not present in the stored source copy",
                        )
                    image.seek(frame - 1)
                    width, height = (int(value) for value in image.size)
                    if width <= 0 or height <= 0 or width * height > MAX_FRAME_PIXELS:
                        raise OcrError(
                            "frame_too_large",
                            f"image frame {frame} exceeds the {MAX_FRAME_PIXELS} pixel safety limit",
                        )
                    image.convert("RGB").save(image_path, format="PNG")
            except OcrError:
                raise
            except Exception as exc:
                raise OcrError(
                    "frame_unreadable",
                    f"image frame {frame} could not be prepared: {type(exc).__name__}: {exc}",
                ) from exc
            text = _normalize(runner(image_path))
            if not text:
                raise OcrError(
                    "blank_transcription",
                    f"OCR produced no text for image:{frame}; the source stays in the review queue",
                )
            blocks.append({"locator": f"image:{frame}", "text": text})
            try:
                os.unlink(image_path)
            except OSError:  # pragma: no cover - best-effort scratch cleanup
                pass
    return blocks


def rasterizer_available() -> bool:
    """Whether the optional PDF rasterizer is installed."""
    return _pdfium is not None


def transcribe_pdf_pages(
    source: Path,
    pages: list[int],
    runner: Runner,
    *,
    dpi: int = RASTER_DPI,
    rasterizer: Any = None,
) -> list[dict[str, str]]:
    """Rasterize and transcribe the named 1-based PDF pages, or fail closed.

    Rendering the page rather than extracting its embedded images is what makes
    this safe: the renderer applies the page transform, so a rotated page or a
    page assembled from several image streams produces the image a reader would
    see.  Pulling XObjects out directly cannot do that and can yield plausible
    text that was never on the page.

    Fails closed on every path, exactly as the image adapter does: a page the
    engine reads as blank raises rather than importing a partial transcription.
    """
    engine = rasterizer if rasterizer is not None else _pdfium
    if engine is None:
        raise OcrError(
            "rasterizer_unavailable",
            f"no PDF rasterizer is installed; install the optional {RASTERIZER_NAME} dependency "
            "or transcribe this source manually",
        )
    if not isinstance(dpi, int) or isinstance(dpi, bool) or not 36 <= dpi <= 600:
        raise OcrError("raster_dpi_invalid", "raster dpi must be an integer between 36 and 600")
    source = Path(source)
    blocks: list[dict[str, str]] = []
    with tempfile.TemporaryDirectory(prefix="coursework-ocr-") as scratch:
        scratch_dir = Path(scratch)
        try:
            document = engine.PdfDocument(str(source))
        except Exception as exc:
            raise OcrError(
                "pdf_unreadable",
                f"the stored source copy could not be opened as a PDF: {type(exc).__name__}: {exc}",
            ) from exc
        try:
            total = len(document)
            for page_number in pages:
                image_path = scratch_dir / f"page-{page_number}.png"
                try:
                    if page_number < 1 or page_number > total:
                        raise OcrError(
                            "page_missing",
                            f"page {page_number} is not present in the stored source copy",
                        )
                    image = document[page_number - 1].render(scale=dpi / 72).to_pil()
                    width, height = (int(value) for value in image.size)
                    if width <= 0 or height <= 0 or width * height > MAX_FRAME_PIXELS:
                        raise OcrError(
                            "page_too_large",
                            f"page {page_number} rasterizes to {width}x{height} at {dpi} dpi, which "
                            f"exceeds the {MAX_FRAME_PIXELS} pixel safety limit; re-run at a lower dpi",
                        )
                    image.convert("RGB").save(image_path, format="PNG")
                except OcrError:
                    raise
                except Exception as exc:
                    raise OcrError(
                        "page_unreadable",
                        f"page {page_number} could not be rasterized: {type(exc).__name__}: {exc}",
                    ) from exc
                text = _normalize(runner(image_path))
                if not text:
                    raise OcrError(
                        "blank_transcription",
                        f"OCR produced no text for page:{page_number}; the source stays in the review queue",
                    )
                blocks.append({"locator": f"page:{page_number}", "text": text})
                try:
                    os.unlink(image_path)
                except OSError:  # pragma: no cover - best-effort scratch cleanup
                    pass
        finally:
            close = getattr(document, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:  # pragma: no cover - best-effort handle release
                    pass
    return blocks


def build_transcription(
    document_id: str,
    source_sha256: str,
    blocks: list[dict[str, str]],
    *,
    version: str | None = None,
    tool: str = TESSERACT,
) -> dict[str, Any]:
    """Build the transcription payload the existing hash-bound importer expects.

    ``tool`` must name the engine that actually produced the blocks.
    """
    provenance: dict[str, str] = {"method": "automatic_ocr", "tool": tool}
    if version:
        provenance["version"] = version[:200]
    provenance["notes"] = (
        "Transcribed automatically by a local OCR engine and imported unreviewed. "
        "Every block still requires an exact visual comparison with the source "
        "before it can be cited as reviewed evidence."
    )
    return {
        "schema_version": 1,
        "document_id": document_id,
        "source_sha256": source_sha256,
        "provenance": provenance,
        "blocks": [{"locator": block["locator"], "text": block["text"]} for block in blocks],
    }


__all__ = [
    "ENGINE_NAME",
    "HANDWRITING_LIMIT",
    "OCR_TIMEOUT_SECONDS",
    "RAPIDOCR",
    "TESSERACT",
    "Engine",
    "OcrError",
    "Probe",
    "Runner",
    "as_engine",
    "build_rapidocr_runner",
    "build_runner",
    "build_transcription",
    "engine_probe",
    "engine_runner",
    "engine_version",
    "rapidocr_available",
    "reading_order",
    "transcribe_frames",
]


def _main(argv: list[str]) -> int:
    if len(argv) == 2 and argv[0] == RAPIDOCR:
        return _rapidocr_worker(argv[1])
    if argv == ["--engine"]:
        # One JSON line for the bootstrap scripts, so both platforms learn the
        # active engine from the same code path the CLI uses.
        found = engine_probe()
        print(json.dumps({
            "engine": found.name if found else None,
            "version": engine_version(found) if found else None,
        }))
        return 0
    print("usage: python -m engineering_assistant.ocr (rapidocr IMAGE | --engine)", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
