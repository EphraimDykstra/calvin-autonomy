"""Small, explicit, project-scoped student memory records."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .common import atomic_json, now, read_json, slug


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


# Observations: slips caught while checking the student's own work.
#
# These record EVENTS, never TRAITS.  "A percentage was used as a fraction in
# a modulus calculation" is an observation bound to a piece of work; "weak at
# units" is a judgement about a person, which this memory refuses outright.
# The difference matters most to the student, who can read this file.  The
# cause comes from a closed vocabulary, the classifier's own, so it cannot be
# widened into an assessment; the topic names the work, not the student; and
# no number the student wrote is kept, because that would be their work.
OBSERVATION_CAUSES = frozenset({
    "sign", "inverted", "unit prefix", "percent", "decimal",
    "temperature scale", "dimension", "method", "arithmetic", "reading",
})
MAX_OBSERVATIONS = 50
_TRAIT_WORDS = (
    "ability", "iq", "weak", "bad at", "poor", "struggle", "smart", "stupid",
    "slow", "lazy", "careless", "sloppy", "always", "never", "talent",
)


def _observations_path(workspace: Path) -> Path:
    return Path(workspace) / "student" / "memory" / "observations.json"


def _load_observations(workspace: Path) -> dict[str, Any]:
    path = _observations_path(workspace)
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "observations": []}
    value = read_json(path)
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("observations have an unsupported schema_version")
    if not isinstance(value.get("observations"), list):
        raise ValueError("observations must be a list")
    return value


def record_observation(workspace: Path, course: str, topic: str, cause: str) -> dict[str, Any]:
    """Record one slip, confirmed with the student, against the work it was in."""
    course = slug(course)
    if cause not in OBSERVATION_CAUSES:
        allowed = ", ".join(sorted(OBSERVATION_CAUSES))
        raise ValueError(f"cause must be one of: {allowed}")
    if not isinstance(topic, str) or not topic.strip() or len(topic) > 120:
        raise ValueError("topic must name the work in 1-120 characters, such as 'tensile modulus, lab 3'")
    lowered = topic.casefold()
    for word in _TRAIT_WORDS:
        if word in lowered:
            raise ValueError(
                f"topic names the work, not the student: {word!r} reads as a judgement about a person"
            )
    state = _load_observations(workspace)
    entry = {
        "course": course,
        "topic": topic.strip(),
        "cause": cause,
        "recorded_at": now(),
        "authority": "observation",
    }
    # A bounded window, so this stays a record of recent work rather than
    # growing into a dossier.
    state["observations"] = (state["observations"] + [entry])[-MAX_OBSERVATIONS:]
    atomic_json(_observations_path(workspace), state)
    return entry


def list_observations(workspace: Path, course: str | None = None, limit: int = 20) -> dict[str, Any]:
    """Return recent observations, newest first, as events and nothing more.

    There is deliberately no summary: counting causes into "this student
    tends to" is exactly the aggregation into a trait this store refuses.
    """
    items = _load_observations(workspace)["observations"]
    if course is not None:
        course = slug(course)
        items = [item for item in items if item.get("course") == course]
    return {"schema_version": SCHEMA_VERSION, "observations": list(reversed(items))[:max(0, limit)]}


def forget_observations(workspace: Path, course: str | None = None) -> dict[str, Any]:
    """Delete observations, all of them or one course's.  The student's call."""
    state = _load_observations(workspace)
    before = len(state["observations"])
    if course is None:
        state["observations"] = []
    else:
        course = slug(course)
        state["observations"] = [i for i in state["observations"] if i.get("course") != course]
    atomic_json(_observations_path(workspace), state)
    return {"forgotten": before - len(state["observations"])}
