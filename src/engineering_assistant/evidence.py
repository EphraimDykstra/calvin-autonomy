"""Resolve structured citations against one course catalog."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .common import atomic_json,now,slug


def _reviews_path(workspace: Path, course: str) -> Path:
    return Path(workspace) / "courses" / slug(course) / "reviews.json"


def _reviews(workspace: Path, course: str) -> dict:
    path = _reviews_path(workspace, course)
    if not path.exists():
        return {"schema_version": 1, "course": slug(course), "reviews": []}
    if path.is_symlink() or not path.is_file():
        raise ValueError("course evidence review registry is unsafe")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict) or value.get("schema_version")!=1 or value.get("course")!=slug(course) or not isinstance(value.get("reviews"),list):
        raise ValueError("course evidence review registry is invalid")
    return value


def evidence_review_status(workspace:Path,course:str,document_id:str,source_sha256:str,locator:str,text_sha256:str)->str:
    try: records=_reviews(workspace,course)["reviews"]
    except (OSError,ValueError,TypeError,json.JSONDecodeError): return "unreviewed"
    match=next((item for item in records if isinstance(item,dict) and item.get("document_id")==document_id and item.get("source_sha256")==source_sha256 and item.get("locator")==locator and item.get("text_sha256")==text_sha256),None)
    return "reviewed" if match and match.get("status")=="reviewed" else "unreviewed"


def review_evidence(workspace:Path,course:str,document_id:str,locator:str,notes:str)->dict:
    course=slug(course)
    if not isinstance(notes,str) or not notes.strip(): raise ValueError("evidence review needs substantive notes")
    catalog_path=Path(workspace)/"courses"/course/"catalog.json"
    if catalog_path.is_symlink() or not catalog_path.is_file(): raise ValueError("course catalog is missing or unsafe")
    catalog=json.loads(catalog_path.read_text(encoding="utf-8"))
    document=next((item for item in catalog.get("documents",[]) if isinstance(item,dict) and item.get("id")==document_id and item.get("active",True) is not False),None)
    if not document or document.get("status")!="extracted": raise ValueError("only a fully extracted active course source can be reviewed")
    block=next((item for item in document.get("blocks",[]) if isinstance(item,dict) and item.get("locator")==locator and item.get("active",True) is not False),None)
    if block is None: raise ValueError("review locator does not resolve")
    text_hash=hashlib.sha256(str(block.get("text","")).encode("utf-8")).hexdigest()
    record={"document_id":document_id,"source_sha256":document.get("sha256"),"locator":locator,"text_sha256":text_hash,"status":"reviewed","notes":notes.strip(),"reviewed_at":now()}
    registry=_reviews(workspace,course)
    existing=next((item for item in registry["reviews"] if all(item.get(key)==record[key] for key in ("document_id","source_sha256","locator","text_sha256"))),None)
    if existing is not None: return existing
    registry["reviews"].append(record); registry["reviews"].sort(key=lambda item:(item["document_id"],item["locator"],item["source_sha256"]))
    atomic_json(_reviews_path(workspace,course),registry); return record


def resolve_evidence(
    workspace: Path,
    course: str,
    evidence: object,
    *,
    current_input_sha256: str | None = None,
    current_input_extraction: object = None,
    require_current_assignment: bool = False,
) -> list[str]:
    if not isinstance(evidence, list) or not evidence:
        return ["reviewed evidence is missing"]
    course = slug(course)
    catalog_path = Path(workspace) / "courses" / course / "catalog.json"
    try:
        if catalog_path.is_symlink() or not catalog_path.is_file():
            catalog = {}
        else:
            catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        catalog = {}
    documents = {
        item.get("id"): item
        for item in catalog.get("documents", [])
        if isinstance(item, dict) and item.get("active", True) is not False
    }
    blockers: list[str] = []
    current_found = False
    course_found = False
    for index, item in enumerate(evidence):
        label = f"evidence {index + 1}"
        if not isinstance(item, dict):
            blockers.append(f"{label} is invalid")
            continue
        locator = item.get("locator")
        document_id = item.get("document_id")
        source_hash = item.get("source_sha256")
        if not isinstance(locator, str) or not locator.strip():
            blockers.append(f"{label} has no locator")
            continue
        if document_id == "current-assignment":
            if current_input_sha256 is None or source_hash != current_input_sha256:
                blockers.append(f"{label} does not match the current assignment")
                continue
            if not isinstance(current_input_extraction,dict) or current_input_extraction.get("status")!="extracted":
                blockers.append(f"{label} current assignment extraction is incomplete or unresolved")
                continue
            block=next((value for value in current_input_extraction.get("blocks",[]) if isinstance(value,dict) and value.get("locator")==locator),None)
            text_hash=hashlib.sha256(str(block.get("text","")).encode("utf-8")).hexdigest() if block else None
            if block is None or item.get("text_sha256")!=text_hash:
                blockers.append(f"{label} current-assignment locator or text hash is stale")
                continue
            current_found = True
            continue
        document = documents.get(document_id)
        if not document or document.get("sha256") != source_hash:
            blockers.append(f"{label} does not resolve to an active same-course source")
            continue
        if document.get("status") != "extracted":
            blockers.append(f"{label} source extraction is incomplete or unresolved")
            continue
        block = next(
            (
                value
                for value in document.get("blocks", [])
                if isinstance(value, dict)
                and value.get("locator") == locator
                and value.get("active", True) is not False
            ),
            None,
        )
        text_hash = hashlib.sha256(str(block.get("text", "")).encode("utf-8")).hexdigest() if block else None
        if block is None or item.get("text_sha256") != text_hash:
            blockers.append(f"{label} locator or text hash is stale")
            continue
        if evidence_review_status(Path(workspace),course,document_id,source_hash,locator,text_hash) != "reviewed":
            blockers.append(f"{label} is not reviewed for method or format use")
            continue
        course_found = True
    if require_current_assignment and not current_found:
        blockers.append("evidence does not cite the current assignment")
    if not course_found:
        blockers.append("no resolved reviewed same-course evidence")
    return blockers


REVIEW_QUEUE_SCHEMA_VERSION = 1


def _catalog(workspace: Path, course: str) -> dict:
    """Read one course catalog, treating any unreadable catalog as empty."""
    path = Path(workspace) / "courses" / slug(course) / "catalog.json"
    try:
        if path.is_symlink() or not path.is_file():
            return {}
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _active_documents(catalog: dict) -> dict:
    return {
        item.get("id"): item
        for item in catalog.get("documents", [])
        if isinstance(item, dict) and item.get("active", True) is not False
    }


def _reviewed_keys(workspace: Path, course: str) -> set:
    """Read the review registry once; an unreadable registry reviews nothing."""
    try:
        records = _reviews(Path(workspace), course)["reviews"]
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return set()
    return {
        (item.get("document_id"), item.get("source_sha256"), item.get("locator"), item.get("text_sha256"))
        for item in records
        if isinstance(item, dict) and item.get("status") == "reviewed"
    }


def _block_text_sha256(block: dict) -> str:
    return hashlib.sha256(str(block.get("text", "")).encode("utf-8")).hexdigest()


def _citation_state(documents: dict, reviewed: set, item: dict) -> str:
    """Classify one citation. Never returns or derives any source text."""
    document = documents.get(item.get("document_id"))
    if not document or document.get("sha256") != item.get("source_sha256"):
        return "unresolved"
    if document.get("status") != "extracted":
        return "unextracted"
    block = next(
        (
            value
            for value in document.get("blocks", [])
            if isinstance(value, dict)
            and value.get("locator") == item.get("locator")
            and value.get("active", True) is not False
        ),
        None,
    )
    if block is None or item.get("text_sha256") != _block_text_sha256(block):
        return "stale"
    key = (item.get("document_id"), item.get("source_sha256"), item.get("locator"), item.get("text_sha256"))
    return "reviewed" if key in reviewed else "unreviewed"


def _used_by(item: dict) -> list[str]:
    value = item.get("used_by")
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [entry for entry in value if isinstance(entry, str) and entry.strip()]
    return []


def evidence_review_queue(workspace: Path, course: str, citations: object = None) -> dict:
    """Report what is pending exact visual review and what that review blocks.

    Citations are evidence dicts, each optionally tagged with ``used_by`` naming
    the downstream consumers a pending review is holding up.  The report carries
    identifiers, hashes and states only: never block text and never reviewer
    notes.  A pending review is an exact *visual* review of the rendered source,
    so triage must send a reader to that page rather than to extracted text.
    """
    course = slug(course)
    documents = _active_documents(_catalog(workspace, course))
    reviewed = _reviewed_keys(Path(workspace), course)

    entries: dict = {}
    for item in citations if isinstance(citations, list) else []:
        if not isinstance(item, dict):
            continue
        document_id, locator = item.get("document_id"), item.get("locator")
        if not isinstance(document_id, str) or not isinstance(locator, str) or not locator.strip():
            continue
        if document_id == "current-assignment":
            continue
        key = (document_id, item.get("source_sha256"), locator, item.get("text_sha256"))
        entry = entries.get(key)
        if entry is None:
            entry = {
                "document_id": document_id,
                "source_sha256": item.get("source_sha256"),
                "locator": locator,
                "text_sha256": item.get("text_sha256"),
                "state": _citation_state(documents, reviewed, item),
                "blocks": [],
            }
            entries[key] = entry
        for label in _used_by(item):
            if label not in entry["blocks"]:
                entry["blocks"].append(label)

    for entry in entries.values():
        entry["blocks"].sort()
    pending = sorted(
        (entry for entry in entries.values() if entry["state"] != "reviewed"),
        key=lambda entry: (entry["document_id"], entry["locator"], entry["state"]),
    )

    blocks_total = 0
    blocks_reviewed = 0
    awaiting_extraction = 0
    for document in documents.values():
        if document.get("status") != "extracted":
            awaiting_extraction += 1
            continue
        for block in document.get("blocks", []):
            if not isinstance(block, dict) or block.get("active", True) is False:
                continue
            if not isinstance(block.get("locator"), str):
                continue
            blocks_total += 1
            key = (document.get("id"), document.get("sha256"), block.get("locator"), _block_text_sha256(block))
            if key in reviewed:
                blocks_reviewed += 1

    return {
        "schema_version": REVIEW_QUEUE_SCHEMA_VERSION,
        "course": course,
        "status": "review_required" if pending else "clear",
        "pending_count": len(pending),
        "pending": pending,
        "documents_total": len(documents),
        "blocks_total": blocks_total,
        "blocks_reviewed": blocks_reviewed,
        "blocks_awaiting_review": blocks_total - blocks_reviewed,
        "documents_awaiting_extraction": awaiting_extraction,
    }


__all__ = ["evidence_review_queue","evidence_review_status","resolve_evidence","review_evidence"]
