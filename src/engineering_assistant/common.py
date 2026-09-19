"""Small shared primitives; no provider APIs or credential access."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def slug(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}", value):
        raise ValueError("Identifier must contain only letters, digits, underscores and hyphens (1-96 characters).")
    return value


def permitted_source(path: Path) -> bool:
    path = Path(path)
    parts = [part for part in path.parts if part not in (path.anchor, "")]
    for index, part in enumerate(parts):
        lower = part.lower()
        # A hidden *target* is a real signal that a file was never meant to be
        # read.  A hidden *ancestor* is not: an ordinary project can sit under
        # any hidden directory, and rejecting on that made every absolute path
        # unusable from, for example, a git worktree under `.claude/`.  This
        # matches the containment-relative rule ingestion already applies,
        # which checks components below the supplied root rather than the
        # absolute ancestors above it.  Every other rule below still applies
        # to every component.
        if index == len(parts) - 1 and lower.startswith("."):
            return False
        if (lower.startswith(("~$", "id_")) or lower == "auth.json"
                or any(word in lower for word in ("secret", "token", "credential"))
                or Path(lower).suffix in (".pem", ".p8", ".key")
                or lower.endswith(" alias")):
            return False
    # Parent aliases such as macOS /tmp -> /private/tmp are normal. The file
    # itself must be regular; ingestion additionally validates containment.
    return not path.is_symlink()


def safe_relative(root: Path, relative: str) -> Path:
    root = Path(root)
    p = Path(relative)
    if not relative or p.is_absolute() or "\\" in relative or any(x in ("..", ".") for x in relative.split("/")):
        raise ValueError("Expected a contained relative path without traversal.")
    candidate = root / p
    if any(x.is_symlink() for x in [root, candidate, *candidate.parents] if x == root or root in x.parents):
        raise ValueError("Symlinks are not permitted in managed paths.")
    if not candidate.resolve().is_relative_to(root.resolve()):
        raise ValueError("Path escapes its workspace.")
    return candidate


def atomic_json(path: Path, value: dict) -> None:
    path = Path(path)
    if path.is_symlink():
        raise ValueError("Refusing to overwrite a symlink.")
    content = json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def read_json(path: Path) -> dict:
    value = json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=lambda v: (_ for _ in ()).throw(ValueError("Non-finite JSON number")))
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object.")
    return value


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()
