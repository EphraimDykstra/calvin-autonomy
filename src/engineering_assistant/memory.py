"""Small, explicit, project-scoped student memory records."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .common import atomic_json, now, read_json


SCHEMA_VERSION = 1
_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}")
_PROHIBITED = {"password", "secret", "token", "credential", "api_key", "ability", "iq"}


def _path(workspace: Path) -> Path:
    return Path(workspace) / "student" / "memory" / "entries.json"


def _load(workspace: Path) -> dict[str, Any]:
    path = _path(workspace)
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "entries": {}}
    value = read_json(path)
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("student memory has unsupported schema_version")
    if not isinstance(value.get("entries"), dict):
        raise ValueError("student memory entries must be an object")
    return value


def list_memory(workspace: Path) -> dict[str, Any]:
    """Return inspectable memory state without interpreting it."""
    return _load(workspace)


def set_memory(workspace: Path, key: str, value: str, *, scope: str, source: str) -> dict[str, Any]:
    """Create or replace an explicit preference or handoff pointer."""
    if not isinstance(key, str) or not _KEY.fullmatch(key):
        raise ValueError("memory key must be 1-80 safe characters")
    if key.casefold() in _PROHIBITED or any(word in key.casefold() for word in ("secret", "token", "credential")):
        raise ValueError("memory may not store secrets, credentials, or inferred ability assessments")
    for name, item in (("value", value), ("scope", scope), ("source", source)):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"memory {name} must be a non-empty string")
        if len(item) > 2000:
            raise ValueError(f"memory {name} is too long")
    state = _load(workspace)
    entry = {
        "value": value.strip(),
        "scope": scope.strip(),
        "source": source.strip(),
        "updated_at": now(),
        "authority": "preference_only",
    }
    state["entries"][key] = entry
    atomic_json(_path(workspace), state)
    return {"key": key, **entry}


def forget_memory(workspace: Path, key: str) -> dict[str, Any]:
    """Remove an entry and report whether it existed."""
    if not isinstance(key, str) or not _KEY.fullmatch(key):
        raise ValueError("memory key must be 1-80 safe characters")
    state = _load(workspace)
    existed = key in state["entries"]
    state["entries"].pop(key, None)
    atomic_json(_path(workspace), state)
    return {"key": key, "forgotten": existed}
