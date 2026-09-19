"""Bounded, local source ingestion and catalog search.

The ingestion path deliberately deals in files and extracted text only.  It
does not import user modules, run office macros, or make network requests.
"""

from __future__ import annotations

import codecs
import contextlib
import hashlib
import json
import os
import re
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from xml.etree import ElementTree
from xml.parsers import expat
from . import ocr
from .evidence import evidence_review_status

try:
    # The shared contract helpers are supplied by the root workstream.  The
    # local fallbacks below keep this module usable in isolation during setup.
    from .common import atomic_json as _contract_atomic_json
    from .common import slug as _contract_slug
except ImportError:  # pragma: no cover - only applies before package setup
    _contract_atomic_json = None
    _contract_slug = None

try:  # Dependencies are declared by the project, but keep import errors local.
    from pypdf import PdfReader
except Exception:  # pragma: no cover - exercised when an optional install is absent
    PdfReader = None  # type: ignore[assignment,misc]

try:
    from openpyxl import load_workbook
except Exception:  # pragma: no cover - exercised when an optional install is absent
    load_workbook = None  # type: ignore[assignment,misc]

try:
    from PIL import Image
except Exception:  # pragma: no cover - exercised when an optional install is absent
    Image = None  # type: ignore[assignment,misc]


SCHEMA_VERSION = 1
SUPPORTED_TEXT = {".txt", ".md", ".markdown", ".rst", ".text"}
SUPPORTED_IMAGES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
SUPPORTED = SUPPORTED_TEXT | SUPPORTED_IMAGES | {".pdf", ".docx", ".xlsx", ".xlsm"}
OFFICE_LOCK_PREFIX = "~$"
ALIAS_SUFFIXES = {".alias", ".lnk", ".url"}
MAX_TEXT_BYTES = 8 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
MAX_OCR_IMPORT_BYTES = 2 * 1024 * 1024
MAX_OCR_BLOCK_CHARS = 250_000
MAX_OCR_TOTAL_CHARS = 1_000_000

# Native extraction bounds.  A source inside the byte cap can still yield an
# absurd number of blocks (8MB of newlines is two million) or a single block of
# millions of characters, so every kind is bounded by block count and block
# size as well.  Exceeding either marks the document truncated, which the
# existing contract already treats as incomplete: a truncated source can never
# be accepted as a complete transcription.
MAX_BLOCKS = 50_000
MAX_BLOCK_CHARS = 100_000

# Container bounds.  DOCX and XLSX are zip archives, so a small file on disk
# can decompress to an arbitrarily large member: a 199KB .docx measured at
# 116MB of document.xml, and a 115KB .xlsx at 114MB of sharedStrings.xml.
# The block bounds above cannot help, because they only see text that has
# already been built -- the memory is spent before any of them runs.  These
# bounds are enforced against bytes actually decompressed, never against the
# sizes declared in the zip central directory, which the archive's author
# controls and can understate.
#
# Sized from the largest legitimate documents this project accepts: a .docx
# holding MAX_BLOCKS paragraphs of ordinary prose measures 14.4MB of
# document.xml, and a 60,000-row three-sheet workbook measures 38.7MB across
# all members with a 12.9MB largest member.
MAX_ARCHIVE_MEMBER_BYTES = 32 * 1024 * 1024
MAX_ARCHIVE_TOTAL_BYTES = 128 * 1024 * 1024
_ARCHIVE_CHUNK_BYTES = 256 * 1024

# Bidirectional overrides and isolates reorder how text displays without
# changing what is stored, so the characters a reviewer sees need not be the
# characters that get hashed as evidence.  Benign invisibles (zero-width
# space, soft hyphen) are left alone: they are common in real PDFs and do not
# reorder anything.
_BIDI_OVERRIDES = frozenset(
    "‪‫‬‭‮⁦⁧⁨⁩"
)

# Match names, rather than file contents, before a file is opened.  A secret
# directory is also rejected so a safe-looking child cannot be reached through
# it.
_SECRET_NAME = re.compile(
    r"(?:^\.env(?:\..*)?$|^auth\.json$|^id_[^/]*$|.*\.(?:pem|p8|key)$|.*(?:secret|token|credential).*)",
    re.IGNORECASE,
)
_HEADING_AI = re.compile(
    r"^(?:ai|a\.i\.?|artificial intelligence|generative ai|use of ai|use of artificial intelligence)"
    r"(?:\s+(?:policy|policies|tools|and tools|in this course))?\s*[:\-\u2013\u2014]?\s*$",
    re.IGNORECASE,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _slug(value: str) -> str:
    if _contract_slug is not None:
        return _contract_slug(value)
    if not isinstance(value, str) or not value or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("course must contain only letters, digits, '_' or '-'")
    return value


def _is_secret_component(name: str) -> bool:
    # Hidden metadata and files are excluded too.  The source root itself may
    # be a normal directory whose children include hidden files.
    return name.startswith(".") or bool(_SECRET_NAME.fullmatch(name))


def _path_is_safe_file(path: Path, root: Path) -> bool:
    """Check lstat/lexical containment without following a source symlink."""
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    if any(_is_secret_component(part) for part in relative.parts):
        return False
    try:
        if path.is_symlink():
            return False
        # A parent symlink could otherwise escape the source root.
        cursor = root
        for part in relative.parts[:-1]:
            cursor = cursor / part
            if cursor.is_symlink():
                return False
        return path.is_file()
    except OSError:
        # Dataless cloud placeholders and disappearing files are simply not
        # readable candidates.  The caller records the skipped count.
        return False


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    if _contract_atomic_json is not None:
        _contract_atomic_json(path, value)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _read_catalog(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else {}
    except (FileNotFoundError, OSError, ValueError, TypeError):
        return {}


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{label} is missing or unsafe")
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=lambda constant: (_ for _ in ()).throw(
                ValueError(f"invalid JSON constant: {constant}")
            ),
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is invalid") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _managed_path(root: Path, relative: object, label: str) -> Path:
    if not isinstance(relative, str) or not relative:
        raise ValueError(f"{label} path is missing")
    value = Path(relative)
    if value.is_absolute() or "\\" in relative or any(part in {"", ".", ".."} for part in relative.split("/")):
        raise ValueError(f"{label} path is unsafe")
    target = root / value
    cursor = root
    if cursor.is_symlink():
        raise ValueError(f"{label} path is unsafe")
    for part in value.parts:
        cursor = cursor / part
        if cursor.exists() and cursor.is_symlink():
            raise ValueError(f"{label} path is unsafe")
    return target


def _json_digest(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _relative_source_files(source: Path) -> tuple[list[tuple[Path, str]], dict[str, int], list[str]]:
    """Enumerate regular, non-secret files without following symlinks."""
    counts: dict[str, int] = {}
    notes: list[str] = []
    candidates: list[tuple[Path, str]] = []

    def skipped(reason: str) -> None:
        counts[reason] = counts.get(reason, 0) + 1

    try:
        source_lstat = source.lstat()
    except OSError:
        return [], {"source_unreadable": 1}, notes
    if source.is_symlink():
        return [], {"symlink": 1}, notes
    # Check the basename before any regular-file probe or content open.
    if _is_secret_component(source.name):
        return [], {"secret": 1}, notes
    if source.name.startswith(OFFICE_LOCK_PREFIX) or source.suffix.lower() in ALIAS_SUFFIXES or source.name.casefold().endswith(" alias"):
        return [], {"office_lock_or_alias": 1}, notes
    if source_lstat and source.is_file():
        return [(source, source.name)], counts, notes
    if not source.is_dir():
        return [], {"source_unreadable": 1}, notes

    root = source

    def visit(directory: Path, relative_directory: Path) -> None:
        try:
            entries = sorted(os.scandir(directory), key=lambda item: item.name.casefold())
        except OSError:
            skipped("directory_unreadable")
            return
        for entry in entries:
            name = entry.name
            relative = relative_directory / name
            if _is_secret_component(name):
                skipped("secret_or_hidden")
                continue
            try:
                if entry.is_symlink():
                    skipped("symlink")
                    continue
                if entry.is_dir(follow_symlinks=False):
                    visit(Path(entry.path), relative)
                    continue
                if not entry.is_file(follow_symlinks=False):
                    skipped("not_regular_file")
                    continue
            except OSError:
                skipped("unreadable")
                continue
            path = Path(entry.path)
            if not _path_is_safe_file(path, root):
                skipped("unsafe_path")
                continue
            if name.startswith(OFFICE_LOCK_PREFIX) or path.suffix.lower() in ALIAS_SUFFIXES or name.casefold().endswith(" alias"):
                skipped("office_lock_or_alias")
                continue
            candidates.append((path, relative.as_posix()))

    visit(root, Path("."))
    candidates.sort(key=lambda item: item[1].casefold())
    return candidates, counts, notes


_UTF16_32_BOMS = (
    (codecs.BOM_UTF32_LE, "UTF-32LE"),
    (codecs.BOM_UTF32_BE, "UTF-32BE"),
    (codecs.BOM_UTF16_LE, "UTF-16LE"),
    (codecs.BOM_UTF16_BE, "UTF-16BE"),
)


def _trim_to_character_boundary(raw: bytes) -> bytes:
    """Drop a UTF-8 sequence the byte cap cut in half.

    Without this, truncating mid-character makes the UTF-8 decode fail and the
    cp1252 fallback re-decode *the whole file* as mojibake: every character
    wrong, reported as a success.  At most three trailing bytes can belong to
    an incomplete sequence.
    """
    for back in range(1, 4):
        if len(raw) < back:
            break
        byte = raw[-back]
        if byte < 0x80:  # a complete single-byte character ends the buffer
            break
        if byte >= 0xC0:  # a lead byte: the sequence it starts was cut short
            expected = 2 if byte < 0xE0 else 3 if byte < 0xF0 else 4
            return raw[:-back] if back < expected else raw
    return raw


def _decode_text(path: Path) -> tuple[str, bool]:
    with path.open("rb") as handle:
        raw = handle.read(MAX_TEXT_BYTES + 1)
    truncated = len(raw) > MAX_TEXT_BYTES
    raw = raw[:MAX_TEXT_BYTES]
    # A UTF-16/32 file is full of NUL bytes and would otherwise be reported as
    # "binary content", which sends the reader looking for the wrong problem.
    for bom, label in _UTF16_32_BOMS:
        if raw.startswith(bom):
            raise ValueError(
                f"{label} encoded text is not supported; re-save the source as UTF-8"
            )
    if b"\x00" in raw:
        raise ValueError("binary content is not plain text")
    if truncated:
        raw = _trim_to_character_boundary(raw)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = raw.decode("cp1252")
        except UnicodeDecodeError as exc:
            # Silently substituting replacement characters would misrepresent
            # the page, so an undeterminable encoding fails closed instead.
            raise ValueError(
                "text encoding could not be determined; re-save the source as UTF-8"
            ) from exc
    return text, truncated


def _reject_bidi_overrides(blocks: list[dict[str, str]]) -> None:
    """Refuse text whose displayed order can differ from its stored order.

    A bidirectional override or isolate makes a reader see something other
    than the characters that are actually stored and hashed.  This codebase
    binds reviewed evidence to ``text_sha256`` and asks a human to confirm it
    by looking at the page, so such a block cannot be reviewed honestly: the
    reviewer would attest to one string while another is recorded.  These
    sources fail closed rather than being silently rewritten, which would
    change the hash of text somebody may already have reviewed.
    """
    for block in blocks:
        text = block.get("text", "")
        for index, character in enumerate(text):
            if character in _BIDI_OVERRIDES:
                raise ValueError(
                    f"{block.get('locator', 'block')} contains the bidirectional control "
                    f"U+{ord(character):04X} at character {index + 1}, which can make the "
                    "displayed text differ from the stored text; review the source page "
                    "and re-save it without bidirectional overrides"
                )


def _finalize_blocks(blocks: list[dict[str, str]]) -> tuple[list[dict[str, str]], bool]:
    """Validate and bound extracted blocks for any kind of source.

    Returns the kept blocks and whether anything was dropped.  A dropped block
    marks the document truncated rather than shortening its text, because a
    silently shortened block would misrepresent the page while still looking
    like a complete extraction.  Truncated documents are already treated as
    incomplete everywhere downstream, so the protection needs no second
    mechanism of its own.
    """
    _reject_bidi_overrides(blocks)
    kept: list[dict[str, str]] = []
    truncated = False
    for block in blocks:
        if len(kept) >= MAX_BLOCKS:
            truncated = True
            break
        if len(block.get("text", "")) > MAX_BLOCK_CHARS:
            truncated = True
            continue
        kept.append(block)
    return kept, truncated


def _line_blocks(text: str) -> list[dict[str, str]]:
    lines = text.splitlines()
    if not lines and text:
        lines = [text]
    # Stop one past the cap so the bound can see the overflow without building
    # a dict per line for a file that is mostly newlines.
    return [
        {"locator": f"line:{index}", "text": line}
        for index, line in enumerate(lines[: MAX_BLOCKS + 1], 1)
    ]


def _heading_level(text: str) -> int | None:
    stripped = text.strip()
    markdown = re.match(r"^(#{1,6})\s+\S", stripped)
    if markdown:
        return len(markdown.group(1))
    numbered = re.match(r"^(\d+(?:\.\d+)*)[.)]?\s+\S", stripped)
    if numbered:
        return numbered.group(1).count(".") + 1
    if len(stripped) >= 3 and len(stripped) <= 100 and stripped == stripped.upper():
        letters = re.sub(r"[^A-Z]", "", stripped)
        if len(letters) >= 3:
            return 1
    return None


def _heading_text(text: str) -> str:
    stripped = re.sub(r"^#{1,6}\s+", "", text.strip())
    stripped = re.sub(r"^\d+(?:\.\d+)*[.)]?\s+", "", stripped)
    return stripped.strip().rstrip(":-\u2013\u2014 ")


def _exclude_syllabus_ai(blocks: list[dict[str, str]], enabled: bool) -> tuple[list[dict[str, str]], dict[str, Any]]:
    if not enabled:
        return blocks, {"status": "disabled", "sections": []}
    sections: list[dict[str, Any]] = []
    excluded_indexes: set[int] = set()
    for index, block in enumerate(blocks):
        level = _heading_level(block.get("text", ""))
        if level is None or not _HEADING_AI.fullmatch(_heading_text(block.get("text", ""))):
            continue
        next_index: int | None = None
        for candidate in range(index + 1, len(blocks)):
            candidate_level = _heading_level(blocks[candidate].get("text", ""))
            if candidate_level is not None and candidate_level <= level:
                next_index = candidate
                break
        if next_index is None:
            sections.append(
                {
                    "section": _heading_text(block.get("text", "")),
                    "start_locator": block.get("locator"),
                    "end_locator": None,
                    "action": "ambiguous",
                    "reason": "AI-policy heading has no explicit following section boundary",
                }
            )
        else:
            for excluded in range(index, next_index):
                excluded_indexes.add(excluded)
            sections.append(
                {
                    "section": _heading_text(block.get("text", "")),
                    "start_locator": block.get("locator"),
                    "end_locator": blocks[next_index].get("locator"),
                    "action": "excluded",
                    "reason": "bounded by the next heading at the same or higher level",
                }
            )
    active = [block for index, block in enumerate(blocks) if index not in excluded_indexes]
    if any(item["action"] == "ambiguous" for item in sections):
        status = "ambiguous"
    elif sections:
        status = "applied"
    else:
        status = "none"
    return active, {"status": status, "sections": sections}


def _copy_verified(source: Path, destination: Path, expected_hash: str) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.is_file():
        try:
            if _hash_file(destination) == expected_hash:
                return destination
        except OSError:
            pass
    fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=str(destination.parent))
    os.close(fd)
    temporary_path = Path(temporary)
    try:
        # The caller already performed lstat/symlink checks.  Recheck immediately
        # before opening so a racing replacement is rejected.
        if source.is_symlink() or not source.is_file():
            raise OSError("source is no longer a regular file")
        with source.open("rb") as source_handle, temporary_path.open("wb") as target_handle:
            shutil.copyfileobj(source_handle, target_handle, length=1024 * 1024)
        if _hash_file(temporary_path) != expected_hash or _hash_file(source) != expected_hash:
            raise OSError("source changed while copying")
        os.replace(temporary_path, destination)
        return destination
    finally:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass


def _copy_path(course_root: Path, document_id: str, source: Path, relative: str) -> Path:
    basename = re.sub(r"[^A-Za-z0-9_.-]", "_", Path(relative).name) or "source"
    return course_root / "sources" / f"{document_id}_{basename}"


class _BoundedReader:
    """A stream that refuses to yield more than a decompressed byte budget.

    Wrapping the archive member rather than reading it whole means the bound
    is enforced as the bytes arrive: a member that decompresses to gigabytes
    costs one chunk past the budget, not its expanded size.
    """

    def __init__(self, handle: Any, budget: int, overrun: str) -> None:
        self._handle = handle
        self._remaining = budget
        self._overrun = overrun

    def _take(self, chunk: bytes) -> bytes:
        self._remaining -= len(chunk)
        if self._remaining < 0:
            raise ValueError(self._overrun)
        return chunk

    def read(self, size: int | None = -1) -> bytes:
        if size is None or size < 0:
            chunks = []
            while True:
                chunk = self._handle.read(_ARCHIVE_CHUNK_BYTES)
                if not chunk:
                    return b"".join(chunks)
                chunks.append(self._take(chunk))
        return self._take(self._handle.read(size))

    def close(self) -> None:
        self._handle.close()


def _member_reader(archive: zipfile.ZipFile, name: str) -> Any:
    """Open one archive member under the per-member decompression bound."""
    return _BoundedReader(
        archive.open(name),
        MAX_ARCHIVE_MEMBER_BYTES,
        f"archive member {name!r} decompresses past the "
        f"{MAX_ARCHIVE_MEMBER_BYTES} byte container safety limit",
    )


class _PrologEnded(Exception):
    """Internal signal: the root element began, so no DTD can follow."""


# Leading bytes of a part that some XML parser would read as XML.  Covers
# UTF-8/ASCII, UTF-16 and UCS-4 in either byte order, and EBCDIC "<?xm".
# Exact multi-byte patterns only: a bare zero-byte prefix would also match
# binary parts such as .ico thumbnails and refuse a legitimate workbook.
_XML_SIGNATURES = (
    b"<",
    b"\xef\xbb\xbf",
    b"\xff\xfe",
    b"\xfe\xff",
    b"\x00<",
    b"\x00\x00\x00<",
    b"\x00\x00\xfe\xff",
    b"\x4c\x6f\xa7\x94",
)


class _DocumentTypeScan:
    """Refuse an XML part that declares a document type definition (DTD).

    Entity expansion happens while one text node is parsed, before any block
    or container bound can see the result, and the only limit on it is the
    parser's own amplification check.  That check differs across expat
    versions, and openpyxl hands most workbook parts to lxml, which has a
    different one again.  So this refuses the declaration, not the
    expansion.  Custom entities can only be defined in a DTD, and Office Open
    XML parts never carry one, so a part without a DTD has nothing to expand.

    Only the prolog is read.  The scan stops at the root element, which a DTD
    must come before.  It uses expat instead of a byte search so that the
    encodings the real parser accepts, such as UTF-16, are decoded the same
    way here.  A part that looks like XML but that expat cannot read (UCS-4,
    EBCDIC, or an encoding OOXML forbids) is refused, because lxml might
    still parse it.  Non-XML parts, such as images and vbaProject.bin, pass.
    """

    def __init__(self, name: str) -> None:
        self._name = name
        self._head = b""
        self._parser = expat.ParserCreate()
        self._parser.StartDoctypeDeclHandler = self._refuse
        self._parser.StartElementHandler = self._root
        self.done = False

    def _refuse(self, *_: Any) -> None:
        raise ValueError(
            f"archive member {self._name!r} declares a document type definition; "
            "Office Open XML parts never carry one, so its entity definitions "
            "are refused rather than expanded"
        )

    def _root(self, *_: Any) -> None:
        raise _PrologEnded

    def feed(self, chunk: bytes, final: bool = False) -> None:
        if self.done:
            return
        if len(self._head) < 4:
            self._head += chunk[: 4 - len(self._head)]
        try:
            self._parser.Parse(chunk, final)
        except _PrologEnded:
            self.done = True
        except expat.ExpatError:
            self.done = True
            if self._head.startswith(_XML_SIGNATURES):
                raise ValueError(
                    f"archive member {self._name!r} could not be checked for a "
                    "document type definition, so it is refused"
                )
        if final:
            self.done = True


def _refuse_document_type(archive: zipfile.ZipFile, name: str) -> None:
    """Scan one member's prolog, under the per-member bound, before it is parsed."""
    scan = _DocumentTypeScan(name)
    with contextlib.closing(_member_reader(archive, name)) as reader:
        while not scan.done:
            chunk = reader.read(_ARCHIVE_CHUNK_BYTES)
            scan.feed(chunk, final=not chunk)


def _reject_oversized_archive(path: Path) -> None:
    """Bound a zip container this module hands to another parser.

    openpyxl performs its own reads, so a member cannot be handed to it
    through a bounded reader.  Every member is instead streamed and discarded
    against a per-member and a whole-archive budget before the workbook is
    opened.  Bytes are counted as they decompress; the sizes recorded in the
    central directory are not consulted, because an archive can declare a
    small member and deliver a large one.

    The same pass refuses any member that declares a DTD.  Every member is
    checked, not only the strings table, because openpyxl follows the
    package's relationships to decide which parts it parses, and the
    archive's author controls those.
    """
    total = 0
    with zipfile.ZipFile(path, "r") as archive:
        for name in archive.namelist():
            if name.endswith("/"):
                continue
            member_budget = MAX_ARCHIVE_MEMBER_BYTES
            total_budget = MAX_ARCHIVE_TOTAL_BYTES - total
            if total_budget <= member_budget:
                budget, overrun = total_budget, (
                    f"archive decompresses past the {MAX_ARCHIVE_TOTAL_BYTES} "
                    "byte container safety limit"
                )
            else:
                budget, overrun = member_budget, (
                    f"archive member {name!r} decompresses past the "
                    f"{MAX_ARCHIVE_MEMBER_BYTES} byte container safety limit"
                )
            scan = _DocumentTypeScan(name)
            with archive.open(name) as handle:
                reader = _BoundedReader(handle, budget, overrun)
                while chunk := reader.read(_ARCHIVE_CHUNK_BYTES):
                    total += len(chunk)
                    scan.feed(chunk)
            scan.feed(b"", final=True)


def _extract_text(path: Path, kind: str, max_pdf_pages: int) -> tuple[list[dict[str, str]], dict[str, Any]]:
    if kind == "text":
        text, truncated = _decode_text(path)
        blocks, bounded = _finalize_blocks(_line_blocks(text))
        truncated = truncated or bounded
        return blocks, {
            "pages_total": 1,
            "pages_processed": 1,
            "status": "partial" if truncated else "extracted",
            "truncated": truncated,
        }
    if kind == "pdf":
        if PdfReader is None:
            raise RuntimeError("pypdf is unavailable")
        reader = PdfReader(str(path))
        total = len(reader.pages)
        budget = max(0, max_pdf_pages)
        processed = min(total, budget)
        blocks: list[dict[str, str]] = []
        empty_pages: list[int] = []
        for index in range(processed):
            page_text = reader.pages[index].extract_text() or ""
            page_text = page_text.strip()
            if not page_text:
                empty_pages.append(index + 1)
            else:
                blocks.append({"locator": f"page:{index + 1}", "text": page_text})
        blocks, bounded = _finalize_blocks(blocks)
        truncated = processed < total or bounded
        if empty_pages:
            status = "needs_ocr"
        elif truncated:
            status = "partial"
        else:
            status = "extracted"
        return blocks, {
            "pages_total": total,
            "pages_processed": processed,
            "status": status,
            "needs_ocr_pages": empty_pages,
            "truncated": truncated,
        }
    if kind == "image":
        if Image is None:
            raise RuntimeError("Pillow is unavailable")
        with Image.open(path) as image:
            total = int(getattr(image, "n_frames", 1) or 1)
            budget = max(0, max_pdf_pages)
            processed = min(total, budget)
            dimensions: list[dict[str, int]] = []
            for index in range(processed):
                image.seek(index)
                width, height = (int(value) for value in image.size)
                if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
                    raise ValueError(
                        f"image frame {index + 1} exceeds the {MAX_IMAGE_PIXELS} pixel safety limit"
                    )
                dimensions.append({"frame": index + 1, "width": width, "height": height})
        # Reopen for Pillow's format-level integrity check.  No metadata is
        # copied to the catalog and no embedded payload is executed.
        with Image.open(path) as image:
            image.verify()
        pending = list(range(1, processed + 1))
        return [], {
            "pages_total": total,
            "pages_processed": processed,
            "status": "needs_ocr",
            "needs_ocr_pages": pending,
            "image_dimensions": dimensions,
            "truncated": processed < total,
        }
    if kind == "docx":
        blocks: list[dict[str, str]] = []
        namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        with zipfile.ZipFile(path, "r") as archive:
            try:
                _refuse_document_type(archive, "word/document.xml")
                reader = _member_reader(archive, "word/document.xml")
            except KeyError:
                raise ValueError("DOCX has no document.xml")
            # Parse as the member decompresses, discarding each paragraph once
            # its text is taken.  Building the whole tree first would undo the
            # container bound: 31MB of minimal <w:p> markup sits inside the
            # per-member limit but parses into 1.4 million elements, measured
            # at 355MB.  Streaming holds one paragraph at a time instead, so
            # peak memory follows the blocks kept, not the member size.
            index = 0
            events = ElementTree.iterparse(reader, events=("start", "end"))
            _, root = next(events)
            for event, element in events:
                if event != "end" or element.tag != namespace + "p":
                    continue
                index += 1
                # Stop one past the cap: enough for the bound to detect that
                # the document overflowed, without reading the rest.
                if len(blocks) > MAX_BLOCKS:
                    break
                text = "".join(node.text or "" for node in element.iter(namespace + "t")).strip()
                if text:
                    blocks.append({"locator": f"paragraph:{index}", "text": text})
                element.clear()
                root.clear()
        blocks, truncated = _finalize_blocks(blocks)
        return blocks, {
            "pages_total": None,
            "pages_processed": None,
            "status": "partial" if truncated else "extracted",
            "truncated": truncated,
        }
    if kind == "xlsx":
        if load_workbook is None:
            raise RuntimeError("openpyxl is unavailable")
        # read_only=True streams worksheet rows, but xl/sharedStrings.xml is
        # materialized in full before the first row is yielded, so the block
        # bounds below never see an oversized strings table.  Bound the whole
        # container before openpyxl opens it.
        _reject_oversized_archive(path)
        blocks: list[dict[str, str]] = []
        workbook = load_workbook(path, read_only=True, data_only=False, keep_links=False)
        try:
            for sheet in workbook.worksheets:
                if len(blocks) > MAX_BLOCKS:
                    break
                for row_number, row in enumerate(sheet.iter_rows(values_only=True), 1):
                    # Stop one past the cap rather than materializing a
                    # million-row sheet and discarding it afterwards.
                    if len(blocks) > MAX_BLOCKS:
                        break
                    values = [str(value) for value in row if value is not None and str(value).strip()]
                    if values:
                        blocks.append({"locator": f"sheet:{sheet.title}!row:{row_number}", "text": "\t".join(values)})
        finally:
            workbook.close()
        blocks, truncated = _finalize_blocks(blocks)
        return blocks, {
            "pages_total": None,
            "pages_processed": None,
            "status": "partial" if truncated else "extracted",
            "truncated": truncated,
        }
    raise ValueError("unsupported file kind")


def _kind_for(path: Path) -> str | None:
    suffix = path.suffix.lower()
    if suffix in SUPPORTED_TEXT:
        return "text"
    if suffix == ".pdf":
        return "pdf"
    if suffix == ".docx":
        return "docx"
    if suffix in {".xlsx", ".xlsm"}:
        return "xlsx"
    if suffix in SUPPORTED_IMAGES:
        return "image"
    return None


def extract_source_blocks(path: Path, max_pdf_pages: int = 100) -> dict[str, Any]:
    """Safely extract one assignment/source file without executing its contents.

    Hostile or malformed input is reported, never raised.  Callers treat this
    as a total function returning a ``status``, so an undecodable encoding, a
    malformed document archive or a corrupt page must come back as a
    structured ``error`` with a specific reason rather than escaping as an
    exception the caller never expected to handle.
    """
    path = Path(path)
    kind = _kind_for(path)
    if path.is_symlink() or not path.is_file() or kind is None:
        return {"kind": kind or "unsupported", "status": "unsupported", "blocks": []}
    try:
        blocks, details = _extract_text(path, kind, max_pdf_pages)
    except Exception as exc:
        # Includes an undeterminable text encoding, an unsupported UTF-16/32
        # source, bidirectional overrides, malformed document XML and any
        # parser failure on a corrupt file.
        return {
            "kind": kind,
            "status": "error",
            "blocks": [],
            "reason": f"{type(exc).__name__}: {exc}",
        }
    return {"kind": kind, "blocks": blocks, **details}


def _document_id(relative: str, digest: str) -> str:
    return hashlib.sha256(f"{relative}\0{digest}".encode("utf-8")).hexdigest()[:20]


def _write_extraction(course_root: Path, document_id: str, blocks: list[dict[str, str]]) -> str:
    path = course_root / "extracted" / f"{document_id}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write("\n".join(block["text"] for block in blocks))
            handle.write("\n" if blocks else "")
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
    return path.relative_to(course_root).as_posix()


def _write_ocr_review(
    course_root: Path,
    document_id: str,
    source_sha256: str,
    relative_path: str,
    kind: str,
    details: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Write a deterministic, fail-closed manifest for unresolved visual text."""
    pending = [
        {"locator": f"{'page' if kind == 'pdf' else 'image'}:{page}", "status": "unreviewed"}
        for page in details.get("needs_ocr_pages", [])
    ]
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "document_id": document_id,
        "source_sha256": source_sha256,
        "relative_path": relative_path,
        "kind": kind,
        "status": "ocr_required",
        "execution": "not_performed",
        "pending": pending,
        "pages_total": details.get("pages_total"),
        "pages_processed": details.get("pages_processed"),
        "truncated": bool(details.get("truncated", False)),
        "instructions": (
            "Run OCR only as an explicit local step, then visually compare every transcription "
            "with the source before it can become reviewed evidence."
        ),
    }
    path = course_root / "reviews" / "ocr" / f"{document_id}.json"
    _atomic_json(path, manifest)
    return path.relative_to(course_root).as_posix(), manifest


def _prepare_document(
    source_path: Path,
    relative: str,
    course_root: Path,
    max_pdf_pages: int,
    exclude_syllabus_ai: bool,
) -> dict[str, Any]:
    kind = _kind_for(source_path)
    try:
        digest = _hash_file(source_path)
        size_bytes = source_path.stat().st_size
    except Exception as exc:
        # Keep an error record for a dataless placeholder or a source that
        # disappeared between enumeration and processing.
        return {
            "id": hashlib.sha256(relative.encode()).hexdigest()[:20],
            "relative_path": relative,
            "sha256": None,
            "kind": kind or "unsupported",
            "status": "error",
            "pages_total": None,
            "pages_processed": None,
            "size_bytes": None,
            "blocks": [],
            "active": True,
            "source_copy": None,
            "extraction_path": None,
            "error": f"{type(exc).__name__}: {exc}",
            "exclusion": {"status": "none", "sections": []},
        }
    if kind is None:
        record: dict[str, Any] = {
            "id": _document_id(relative, digest),
            "relative_path": relative,
            "sha256": digest,
            "kind": "unsupported",
            "status": "unsupported",
            "pages_total": None,
            "pages_processed": None,
            "size_bytes": size_bytes,
            "blocks": [],
            "active": True,
            "source_copy": None,
            "extraction_path": None,
            "exclusion": {"status": "none", "sections": []},
            "error": "file type is not supported for native extraction",
        }
        try:
            record["source_copy"] = _copy_verified(
                source_path, _copy_path(course_root, record["id"], source_path, relative), digest
            ).relative_to(course_root).as_posix()
        except Exception as exc:
            record["copy_error"] = f"{type(exc).__name__}: {exc}"
        return record
    document_id = _document_id(relative, digest)
    record: dict[str, Any] = {
        "id": document_id,
        "relative_path": relative,
        "sha256": digest,
        "kind": kind,
        "status": "error",
        "pages_total": None,
        "pages_processed": None,
        "size_bytes": size_bytes,
        "blocks": [],
        "active": True,
        "source_copy": None,
        "extraction_path": None,
        "ingested_at": _now(),
    }
    try:
        destination = _copy_path(course_root, document_id, source_path, relative)
        copied = _copy_verified(source_path, destination, digest)
        record["source_copy"] = copied.relative_to(course_root).as_posix()
        blocks, details = _extract_text(source_path, kind, max_pdf_pages)
        # Syllabus policy exclusion is applied only when the source name marks
        # it as a syllabus; unrelated technical documents mentioning AI stay
        # intact.
        exclusion = {"status": "none", "sections": []}
        source_name = Path(relative).name.casefold()
        appears_syllabus = "syllabus" in source_name or any(
            "syllabus" in block.get("text", "").casefold() for block in blocks[:10]
        )
        if exclude_syllabus_ai and appears_syllabus:
            blocks, exclusion = _exclude_syllabus_ai(blocks, True)
        record["blocks"] = blocks
        record.update({key: details[key] for key in ("pages_total", "pages_processed", "status")})
        record["truncated"] = bool(details.get("truncated", False))
        if details.get("status") == "needs_ocr":
            record["needs_ocr_pages"] = details.get("needs_ocr_pages", [])
            review_path, review = _write_ocr_review(
                course_root, document_id, digest, relative, kind, details
            )
            record["ocr_review_path"] = review_path
            record["ocr_review"] = review
        if details.get("image_dimensions"):
            record["image_dimensions"] = details["image_dimensions"]
        record["exclusion"] = exclusion
        record["extraction_path"] = _write_extraction(course_root, document_id, blocks)
    except Exception as exc:
        # Keep a visible record and let prior good versions remain active.
        record["status"] = "error"
        record["error"] = f"{type(exc).__name__}: {exc}"
        record["exclusion"] = {"status": "none", "sections": []}
    return record


def ingest(
    source: Path,
    workspace: Path,
    course: str,
    max_files: int = 50,
    max_pdf_pages: int = 100,
    exclude_syllabus_ai: bool = True,
) -> dict[str, Any]:
    """Import a bounded source file/directory and write its course catalog."""
    course = _slug(course)
    if max_files < 0 or max_pdf_pages < 0:
        raise ValueError("max_files and max_pdf_pages must be non-negative")
    source = Path(source)
    workspace = Path(workspace)
    # Managed output paths are never allowed to traverse a caller-provided
    # symlink.  This mirrors the shared workspace safety contract.
    if workspace.exists() and workspace.is_symlink():
        raise ValueError("workspace may not be a symlink")
    courses_dir = workspace / "courses"
    if courses_dir.exists() and courses_dir.is_symlink():
        raise ValueError("courses directory may not be a symlink")
    course_root = workspace / "courses" / course
    if course_root.exists() and course_root.is_symlink():
        raise ValueError("course directory may not be a symlink")
    catalog_path = course_root / "catalog.json"
    existing = _read_catalog(catalog_path)
    old_documents = [item for item in existing.get("documents", []) if isinstance(item, dict)]
    candidates, skipped_counts, _ = _relative_source_files(source)
    discovered = len(candidates)
    selected = candidates[:max_files]
    documents = list(old_documents)
    processed = 0
    errors = 0
    for source_path, relative in selected:
        try:
            digest = _hash_file(source_path) if _kind_for(source_path) is not None else None
        except Exception:
            digest = None
        existing_same = next(
            (doc for doc in documents if doc.get("relative_path") == relative and doc.get("sha256") == digest),
            None,
        )
        if existing_same is not None:
            existing_same["active"] = True
            processed += 1
            continue
        record = _prepare_document(source_path, relative, course_root, max_pdf_pages, exclude_syllabus_ai)
        documents.append(record)
        processed += 1
        if record.get("status") == "error":
            errors += 1
            continue
        # A successful newer version supersedes older versions at this path.
        if record.get("status") in {"extracted", "partial", "needs_ocr"}:
            for old in documents:
                if old is not record and old.get("relative_path") == relative and old.get("sha256") != record.get("sha256"):
                    old["active"] = False
                    old["superseded_by"] = record["id"]
    # Keep prior documents from an interrupted or unsupported reimport active;
    # only selected successful replacements above change their active state.
    warnings: list[str] = []
    if discovered > len(selected):
        skipped_counts["max_files"] = discovered - len(selected)
        warnings.append(f"file limit reached: processed {len(selected)} of {discovered}")
    if skipped_counts.get("directory_unreadable") or skipped_counts.get("source_unreadable"):
        warnings.append("one or more source paths could not be read")
    if errors:
        warnings.append(f"{errors} source(s) had extraction errors; prior versions were retained")
    catalog: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "course": course,
        "documents": documents,
        "source": {"path_name": source.name, "is_directory": source.is_dir()},
        "limits": {
            "max_files": max_files,
            "max_pdf_pages": max_pdf_pages,
            "files_discovered": discovered,
            "files_processed": processed,
            "partial": bool(discovered > len(selected) or errors),
        },
        "skipped": skipped_counts,
        "warnings": warnings,
        "updated_at": _now(),
    }
    _atomic_json(catalog_path, catalog)
    return catalog


def ocr_status(workspace: Path, course: str) -> dict[str, Any]:
    """Report pending OCR and local capabilities without running an OCR engine."""
    course = _slug(course)
    catalog = _read_catalog(Path(workspace) / "courses" / course / "catalog.json")
    documents: list[dict[str, Any]] = []
    for document in catalog.get("documents", []):
        if not isinstance(document, dict) or document.get("active", True) is False:
            continue
        if document.get("status") != "needs_ocr":
            continue
        documents.append(
            {
                "document_id": document.get("id"),
                "relative_path": document.get("relative_path"),
                "source_sha256": document.get("sha256"),
                "kind": document.get("kind"),
                "needs_ocr_pages": document.get("needs_ocr_pages", []),
                "truncated": bool(document.get("truncated", False)),
                "ocr_review_path": document.get("ocr_review_path"),
            }
        )
    return {
        "course": course,
        "status": "ocr_required" if documents else "clear",
        "pending_count": len(documents),
        "documents": documents,
        "local_engine": {
            "name": "tesseract",
            "available": shutil.which("tesseract") is not None,
            "execution": "not_performed",
        },
    }


def _normalize_ocr_import(transcription: dict[str, Any]) -> dict[str, Any]:
    expected_keys = {"schema_version", "document_id", "source_sha256", "provenance", "blocks"}
    if set(transcription) != expected_keys or transcription.get("schema_version") != 1:
        raise ValueError("OCR transcription must use schema_version 1 and the documented fields")
    document_id = transcription.get("document_id")
    source_sha256 = transcription.get("source_sha256")
    if not isinstance(document_id, str) or not re.fullmatch(r"[0-9a-f]{20}", document_id):
        raise ValueError("OCR transcription document_id is invalid")
    if not isinstance(source_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", source_sha256):
        raise ValueError("OCR transcription source_sha256 is invalid")
    provenance = transcription.get("provenance")
    if not isinstance(provenance, dict):
        raise ValueError("OCR transcription provenance must be an object")
    allowed_provenance = {"method", "tool", "version", "notes"}
    if not set(provenance).issubset(allowed_provenance) or not {"method", "tool"}.issubset(provenance):
        raise ValueError("OCR provenance requires method and tool and contains unsupported fields")
    normalized_provenance: dict[str, str] = {}
    for key in ("method", "tool", "version", "notes"):
        if key not in provenance:
            continue
        value = provenance[key]
        limit = 2000 if key == "notes" else 200
        if not isinstance(value, str) or not value.strip() or len(value) > limit or "\x00" in value:
            raise ValueError(f"OCR provenance {key} is invalid")
        normalized_provenance[key] = value.strip()
    blocks = transcription.get("blocks")
    if not isinstance(blocks, list):
        raise ValueError("OCR transcription blocks must be a list")
    normalized_blocks: list[dict[str, str]] = []
    total_chars = 0
    seen: set[str] = set()
    for block in blocks:
        if not isinstance(block, dict) or set(block) != {"locator", "text"}:
            raise ValueError("each OCR block must contain only locator and text")
        locator = block.get("locator")
        text = block.get("text")
        if not isinstance(locator, str) or not locator.strip():
            raise ValueError("OCR block locator is invalid")
        locator = locator.strip()
        if locator in seen:
            raise ValueError(f"duplicate OCR locator: {locator}")
        seen.add(locator)
        if not isinstance(text, str):
            raise ValueError(f"OCR text for {locator} is invalid")
        text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not text or "\x00" in text:
            raise ValueError(f"OCR text for {locator} is blank or invalid")
        # Transcribed text becomes citable evidence exactly like extracted
        # text, so it is held to the same standard: a reviewer must not be
        # shown a different string from the one that gets hashed.
        _reject_bidi_overrides([{"locator": locator, "text": text}])
        if len(text) > MAX_OCR_BLOCK_CHARS:
            raise ValueError(f"OCR text for {locator} exceeds the per-block limit")
        total_chars += len(text)
        if total_chars > MAX_OCR_TOTAL_CHARS:
            raise ValueError("OCR transcription exceeds the total text limit")
        normalized_blocks.append(
            {
                "locator": locator,
                "text": text,
                "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            }
        )
    normalized_blocks.sort(
        key=lambda block: (
            0,
            int(block["locator"].split(":", 1)[1]),
            block["locator"],
        )
        if re.fullmatch(r"(?:page|image):\d+", block["locator"])
        else (1, 0, block["locator"])
    )
    return {
        "schema_version": 1,
        "document_id": document_id,
        "source_sha256": source_sha256,
        "provenance": normalized_provenance,
        "blocks": normalized_blocks,
    }


def import_ocr_transcription(workspace: Path, course: str, transcription: dict[str, Any]) -> dict[str, Any]:
    """Import a complete external OCR transcription without treating it as reviewed."""
    course = _slug(course)
    if not isinstance(transcription, dict):
        raise ValueError("OCR transcription must be a JSON object")
    normalized = _normalize_ocr_import(transcription)
    content_sha256 = _json_digest(normalized)
    workspace = Path(workspace)
    for managed in (workspace, workspace / "courses", workspace / "courses" / course):
        if managed.exists() and managed.is_symlink():
            raise ValueError("OCR workspace path is unsafe")
    course_root = workspace / "courses" / course
    catalog_path = course_root / "catalog.json"
    catalog = _read_json_object(catalog_path, "course catalog")
    if catalog.get("course") != course or not isinstance(catalog.get("documents"), list):
        raise ValueError("course catalog is invalid")
    document = next(
        (
            item
            for item in catalog["documents"]
            if isinstance(item, dict)
            and item.get("id") == normalized["document_id"]
            and item.get("active", True) is not False
        ),
        None,
    )
    if document is None:
        raise ValueError("OCR document is missing or inactive")
    if document.get("sha256") != normalized["source_sha256"]:
        raise ValueError("OCR transcription source hash is stale")

    import_path = course_root / "ocr-imports" / f"{normalized['document_id']}.json"
    existing_import = document.get("ocr_import")
    if document.get("status") == "extracted" and isinstance(existing_import, dict):
        if existing_import.get("content_sha256") != content_sha256:
            raise ValueError("OCR transcription already exists and cannot be overwritten")
        if import_path.is_symlink() or not import_path.is_file():
            raise ValueError("stored OCR transcription is missing or unsafe")
        if _hash_file(import_path) != existing_import.get("file_sha256"):
            raise ValueError("stored OCR transcription has changed")
        return {
            "course": course,
            "document_id": document["id"],
            "source_sha256": document["sha256"],
            "status": "extracted",
            "blocks_imported": len(normalized["blocks"]),
            "idempotent": True,
            "ocr_import": existing_import,
        }
    if document.get("status") != "needs_ocr":
        raise ValueError("only a needs_ocr document can accept an OCR transcription")
    if document.get("truncated") is True or document.get("pages_processed") != document.get("pages_total"):
        raise ValueError("partial or truncated sources cannot accept OCR transcription")

    source_copy = _managed_path(course_root, document.get("source_copy"), "source copy")
    if not source_copy.is_file() or _hash_file(source_copy) != document["sha256"]:
        raise ValueError("source copy is missing or does not match the current source hash")
    review_path = _managed_path(course_root, document.get("ocr_review_path"), "OCR review manifest")
    review = _read_json_object(review_path, "OCR review manifest")
    if (
        review.get("document_id") != document["id"]
        or review.get("source_sha256") != document["sha256"]
        or review.get("kind") != document.get("kind")
        or review.get("status") != "ocr_required"
        or review.get("truncated") is True
        or review.get("pages_total") != document.get("pages_total")
        or review.get("pages_processed") != document.get("pages_processed")
    ):
        raise ValueError("OCR review manifest is stale or invalid")
    prefix = "page" if document.get("kind") == "pdf" else "image"
    page_numbers = document.get("needs_ocr_pages")
    if not isinstance(page_numbers, list) or any(not isinstance(value, int) or value < 1 for value in page_numbers):
        raise ValueError("OCR pending page metadata is invalid")
    expected_locators = [f"{prefix}:{value}" for value in page_numbers]
    if len(set(expected_locators)) != len(expected_locators):
        raise ValueError("OCR pending page metadata contains duplicates")
    manifest_pending = review.get("pending")
    if not isinstance(manifest_pending, list) or manifest_pending != [
        {"locator": locator, "status": "unreviewed"} for locator in expected_locators
    ]:
        raise ValueError("OCR review manifest pending coverage is stale or invalid")
    supplied_locators = [block["locator"] for block in normalized["blocks"]]
    if set(supplied_locators) != set(expected_locators) or len(supplied_locators) != len(expected_locators):
        raise ValueError("OCR transcription must cover every pending locator exactly once")

    native_blocks = document.get("blocks")
    if not isinstance(native_blocks, list) or any(not isinstance(block, dict) for block in native_blocks):
        raise ValueError("native extraction blocks are invalid")
    if document.get("kind") not in {"pdf", "image"}:
        raise ValueError("OCR transcription applies only to PDF or image sources")
    fresh_blocks, fresh_details = _extract_text(
        source_copy, str(document.get("kind")), int(document.get("pages_total") or 0)
    )
    source_name = str(document.get("relative_path", "")).casefold()
    appears_syllabus = "syllabus" in Path(source_name).name or any(
        "syllabus" in block.get("text", "").casefold() for block in fresh_blocks[:10]
    )
    if appears_syllabus:
        fresh_blocks, _ = _exclude_syllabus_ai(fresh_blocks, True)
    if (
        fresh_blocks != native_blocks
        or fresh_details.get("status") != "needs_ocr"
        or fresh_details.get("truncated") is True
        or fresh_details.get("needs_ocr_pages") != page_numbers
    ):
        raise ValueError("native extraction or pending OCR metadata is stale")
    native_locators = [block.get("locator") for block in native_blocks]
    if any(not isinstance(locator, str) or not locator for locator in native_locators):
        raise ValueError("native extraction locators are invalid")
    if len(set(native_locators)) != len(native_locators) or set(native_locators).intersection(expected_locators):
        raise ValueError("OCR locators conflict with native extraction")
    imported_blocks = [
        {
            "locator": block["locator"],
            "text": block["text"],
            "origin": "ocr_import",
            "text_sha256": block["text_sha256"],
        }
        for block in normalized["blocks"]
    ]

    def block_order(block: dict[str, Any]) -> tuple[int, int, str]:
        locator = str(block.get("locator", ""))
        match = re.fullmatch(r"(page|image):(\d+)", locator)
        return (0, int(match.group(2)), locator) if match else (1, 0, locator)

    merged_blocks = sorted([*native_blocks, *imported_blocks], key=block_order)
    stored = {
        **normalized,
        "content_sha256": content_sha256,
        "imported_at": _now(),
        "review_status": "unreviewed",
    }
    if import_path.exists():
        prior = _read_json_object(import_path, "stored OCR transcription")
        try:
            prior_payload = {key: prior[key] for key in ("schema_version", "document_id", "source_sha256", "provenance", "blocks")}
        except KeyError as exc:
            raise ValueError("stored OCR transcription is invalid") from exc
        if prior.get("content_sha256") != content_sha256 or _json_digest(prior_payload) != content_sha256:
            raise ValueError("OCR transcription storage already exists and cannot be overwritten")
        stored = prior
    else:
        _atomic_json(import_path, stored)
    file_sha256 = _hash_file(import_path)
    import_record = {
        "path": import_path.relative_to(course_root).as_posix(),
        "source_sha256": document["sha256"],
        "content_sha256": content_sha256,
        "file_sha256": file_sha256,
        "provenance": normalized["provenance"],
        "locators": expected_locators,
        "review_status": "unreviewed",
        "imported_at": stored.get("imported_at"),
    }
    completed_review = dict(review)
    completed_review.update(
        {
            "status": "transcription_imported",
            "execution": "external_import",
            "pending": [
                {
                    "locator": block["locator"],
                    "status": "transcribed_unreviewed",
                    "text_sha256": block["text_sha256"],
                }
                for block in normalized["blocks"]
            ],
            "transcription_path": import_record["path"],
            "transcription_sha256": content_sha256,
        }
    )
    document["blocks"] = merged_blocks
    document["status"] = "extracted"
    document["needs_ocr_pages"] = []
    document["ocr_import"] = import_record
    document["ocr_review"] = completed_review
    document["extraction_path"] = _write_extraction(course_root, document["id"], merged_blocks)
    _atomic_json(review_path, completed_review)
    _atomic_json(catalog_path, catalog)
    return {
        "course": course,
        "document_id": document["id"],
        "source_sha256": document["sha256"],
        "status": "extracted",
        "blocks_imported": len(imported_blocks),
        "native_blocks_preserved": len(native_blocks),
        "idempotent": False,
        "ocr_import": import_record,
    }


def _ocr_blocked(
    course: str,
    document_id: str,
    reason: str,
    warning: str,
    engine: dict[str, Any],
    **extra: Any,
) -> dict[str, Any]:
    """Report a fail-closed automatic OCR attempt.

    Nothing on disk is modified.  The ``ocr_required`` manifest written at
    ingest time is already the queue entry, so leaving it untouched *is* the
    fail-closed state; annotating it would make a byte-stable file carry
    attempt timestamps for no gain.
    """
    return {
        "course": course,
        "document_id": document_id,
        "status": "blocked",
        "imported": False,
        "reason": reason,
        "warning": warning,
        "engine": engine,
        **extra,
    }


def auto_ocr_document(
    workspace: Path,
    course: str,
    document_id: str,
    *,
    probe: Callable[[], "ocr.Engine | str | None"] | None = None,
    runner: Callable[[Path], str] | None = None,
    rasterizer: Any = None,
) -> dict[str, Any]:
    """Transcribe one pending image or PDF source with a local OCR engine, or fail closed.

    This is a convenience over the manual path, never a replacement for it.
    The transcription is handed to :func:`import_ocr_transcription`, so the
    hash binding, exact locator coverage, staleness re-verification and
    ``unreviewed`` review state are inherited rather than reimplemented.
    OCR is not review: imported blocks still require an exact visual evidence
    review before they can be cited.

    When no engine is installed, or the engine fails, times out, or reads a
    page as blank, nothing is imported and the source stays in the review
    queue with an explicit warning.
    """
    course = _slug(course)
    if not isinstance(document_id, str) or not re.fullmatch(r"[0-9a-f]{20}", document_id):
        raise ValueError("document_id is invalid")
    workspace = Path(workspace)
    for managed in (workspace, workspace / "courses", workspace / "courses" / course):
        if managed.exists() and managed.is_symlink():
            raise ValueError("OCR workspace path is unsafe")
    course_root = workspace / "courses" / course
    catalog = _read_json_object(course_root / "catalog.json", "course catalog")
    if catalog.get("course") != course or not isinstance(catalog.get("documents"), list):
        raise ValueError("course catalog is invalid")

    probe = probe if probe is not None else ocr.engine_probe
    selected = ocr.as_engine(probe())
    engine: dict[str, Any] = {
        "name": selected.name if selected is not None else None,
        "available": selected is not None,
        "execution": "not_performed",
    }

    document = next(
        (
            item
            for item in catalog["documents"]
            if isinstance(item, dict)
            and item.get("id") == document_id
            and item.get("active", True) is not False
        ),
        None,
    )
    if document is None:
        return _ocr_blocked(
            course, document_id, "document_missing",
            "no active course document matches this id", engine,
        )
    if document.get("status") == "extracted":
        return _ocr_blocked(
            course, document_id, "already_transcribed",
            "this source already has a complete transcription; nothing was re-run", engine,
        )
    if document.get("status") != "needs_ocr":
        return _ocr_blocked(
            course, document_id, "not_pending_ocr",
            f"only a needs_ocr source can be transcribed; this one is {document.get('status')!r}", engine,
        )
    kind = document.get("kind")
    if kind not in ("image", "pdf"):
        return _ocr_blocked(
            course, document_id, "automatic_ocr_unsupported_kind",
            f"automatic OCR covers image and pdf sources only; a {kind!r} source "
            "stays in the manual transcription queue", engine,
        )
    if kind == "pdf":
        # The page is rendered, never reassembled from its embedded XObjects.
        # Rendering applies the page transform, so a rotated page or a page
        # built from several image streams yields the image a reader would see.
        # Extracting XObjects cannot do that and can produce plausible text that
        # was never on the page.
        engine["rasterizer"] = ocr.RASTERIZER_NAME
        engine["raster_dpi"] = ocr.RASTER_DPI
        if rasterizer is None and not ocr.rasterizer_available():
            return _ocr_blocked(
                course, document_id, "rasterizer_unavailable",
                f"no PDF rasterizer is installed; install the optional {ocr.RASTERIZER_NAME} "
                "dependency or transcribe this source manually", engine,
            )
    if document.get("truncated") is True or document.get("pages_processed") != document.get("pages_total"):
        return _ocr_blocked(
            course, document_id, "source_truncated",
            "this source was truncated at ingest and can never accept a transcription; "
            "re-ingest it with a page budget at least as large as its frame count", engine,
        )
    frames = document.get("needs_ocr_pages")
    if not isinstance(frames, list) or not frames or any(
        not isinstance(value, int) or isinstance(value, bool) or value < 1 for value in frames
    ):
        return _ocr_blocked(
            course, document_id, "pending_metadata_invalid",
            "pending OCR page metadata is missing or invalid", engine,
        )
    if selected is None:
        return _ocr_blocked(
            course, document_id, "engine_unavailable",
            f"no local OCR engine ({ocr.RAPIDOCR} or {ocr.TESSERACT}) is installed; nothing was "
            f"transcribed and {len(frames)} page(s) stay in the review queue", engine,
        )

    try:
        source_copy = _managed_path(course_root, document.get("source_copy"), "source copy")
    except ValueError as exc:
        return _ocr_blocked(course, document_id, "source_copy_unsafe", str(exc), engine)
    if source_copy.is_symlink() or not source_copy.is_file() or _hash_file(source_copy) != document.get("sha256"):
        return _ocr_blocked(
            course, document_id, "source_copy_stale",
            "the stored source copy is missing or no longer matches the recorded source hash", engine,
        )

    active_runner = runner if runner is not None else ocr.engine_runner(selected)
    try:
        if kind == "pdf":
            blocks = ocr.transcribe_pdf_pages(source_copy, frames, active_runner, rasterizer=rasterizer)
        else:
            blocks = ocr.transcribe_frames(source_copy, frames, active_runner)
    except ocr.OcrError as exc:
        engine["execution"] = "attempted"
        return _ocr_blocked(course, document_id, exc.reason, exc.message, engine)

    engine["execution"] = "performed"
    version = ocr.engine_version(selected) if runner is None else None
    transcription = ocr.build_transcription(
        document_id, str(document.get("sha256")), blocks, version=version, tool=selected.name
    )
    result = import_ocr_transcription(workspace, course, transcription)
    return {
        **result,
        "imported": True,
        "automatic": True,
        "engine": engine,
        "locators": [block["locator"] for block in blocks],
    }


def search(workspace: Path, course: str, query: str, limit: int = 8) -> list[dict[str, Any]]:
    """Search active extracted blocks in one course's catalog."""
    course = _slug(course)
    if limit <= 0 or not isinstance(query, str) or not query.strip():
        return []
    catalog = _read_catalog(Path(workspace) / "courses" / course / "catalog.json")
    terms = [term.casefold() for term in query.split() if term.strip()]
    if not terms:
        return []
    results: list[tuple[int, int, dict[str, Any]]] = []
    for document_order, document in enumerate(catalog.get("documents", [])):
        if not isinstance(document, dict) or document.get("active", True) is False:
            continue
        if document.get("status") not in {"extracted", "partial", "needs_ocr"}:
            continue
        for block_order, block in enumerate(document.get("blocks", [])):
            if not isinstance(block, dict) or block.get("active", True) is False:
                continue
            text_value = str(block.get("text", ""))
            text_hash = hashlib.sha256(text_value.encode("utf-8")).hexdigest()
            lowered = text_value.casefold()
            if not all(term in lowered for term in terms):
                continue
            score = sum(lowered.count(term) for term in terms)
            results.append(
                (
                    -score,
                    document_order * 100000 + block_order,
                    {
                        "document_id": document.get("id"),
                        "source_sha256": document.get("sha256"),
                        "relative_path": document.get("relative_path"),
                        "kind": document.get("kind"),
                        "locator": block.get("locator"),
                        "text": text_value,
                        "text_sha256": text_hash,
                        "review_status": evidence_review_status(workspace,course,document.get("id"),document.get("sha256"),block.get("locator"),text_hash),
                        "source_copy": document.get("source_copy"),
                    },
                )
            )
    results.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in results[:limit]]


__all__ = [
    "MAX_OCR_IMPORT_BYTES",
    "extract_source_blocks",
    "import_ocr_transcription",
    "ingest",
    "ocr_status",
    "search",
]
