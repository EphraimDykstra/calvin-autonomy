"""Privacy policy for local run identity and reusable public records.

Identity is opt-in and run-scoped.  Shared course packs, examples, skills,
and documentation receive placeholders or redacted metadata instead of a
student's name, identifier, or local path.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Iterable, Mapping
from typing import Any


SCHEMA_VERSION = 1
PLACEHOLDER_DISPLAY_NAME = "[Student Name]"
PLACEHOLDER_STUDENT_ID = "[Student ID]"

# Keys that identify a person or a prior run.  ``id`` is intentionally absent:
# assignment and example IDs are structural identifiers, not student identity.
IDENTITY_KEYS = frozenset(
    {
        "author",
        "author_id",
        "created_by",
        "creator",
        "display_name",
        "email",
        "identity",
        "name",
        "netid",
        "owner",
        "owner_id",
        "run_id",
        "sid",
        "submission_id",
        "studentid",
        "artifact_id",
        "student",
        "student_id",
        "student_name",
        "user",
        "user_id",
        "userid",
        "username",
    }
)
# The same field is spelled several ways in practice.  ``studentName``,
# ``student_name`` and ``studentname`` all name a student's name, so every
# spelling has to resolve to the same key before it is matched.
_IDENTITY_KEY_FORMS = IDENTITY_KEYS | {key.replace("_", "") for key in IDENTITY_KEYS}
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_ABSOLUTE_PERSONAL_PATH = re.compile(r"(?:^|[\s\"'])(?:/Users/[^\s\"']+|/home/[^\s\"']+|[A-Za-z]:[\\/][^\s\"']+)")

# Identity values are redacted by case-insensitive substring match, so a value
# of one or two characters matches inside ordinary words: student_id "S" turns
# "Stress analysis" into "[Redacted]tre[Redacted][Redacted] analy[Redacted]i..."
# and that corruption looks like redaction working.  Such a value also cannot
# identify anyone.  The decision (issue #19) is to refuse it rather than
# redact it, which fails closed: every value at or above the floor is still
# redacted exactly as before, and nothing short is silently stored.
# Real identifiers (netids, 7-9 digit student IDs, full names) are well above
# 3 characters.  The known cost: a genuine 2-character value held alone in an
# identity field, such as a surname "Li", is refused; "Bo Li" is accepted.
MIN_REDACTABLE_LENGTH = 3


def require_redactable(value: str, field: str) -> str:
    """Refuse an identity value too short to redact without corrupting text."""
    text = value.strip()
    if len(text) < MIN_REDACTABLE_LENGTH:
        raise ValueError(
            f"{field} is shorter than {MIN_REDACTABLE_LENGTH} characters; a value this short "
            "cannot identify anyone and cannot be redacted without corrupting surrounding text "
            "(it would match inside ordinary words). Omit it or use the placeholder."
        )
    return text


def _name(value: Any, field: str, placeholder: str) -> tuple[str, bool]:
    if value is None or (isinstance(value, str) and not value.strip()):
        return placeholder, False
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    value = value.strip()
    if _CONTROL.search(value) or len(value) > 200:
        raise ValueError(f"{field} contains unsupported characters or is too long")
    if "/" in value or "\\" in value:
        raise ValueError(f"{field} must be a display value, not a path")
    return require_redactable(value, field), True


def run_identity(
    display_name: str | None = None,
    student_id: str | None = None,
    identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a validated run-local identity, using placeholders by default."""
    if identity is not None:
        if not isinstance(identity, Mapping):
            raise ValueError("identity must be an object")
        if display_name is None:
            display_name = identity.get("display_name", identity.get("student_name", identity.get("name")))
        if student_id is None:
            student_id = identity.get("student_id")
    name, name_given = _name(display_name, "display_name", PLACEHOLDER_DISPLAY_NAME)
    sid, id_given = _name(student_id, "student_id", PLACEHOLDER_STUDENT_ID)
    return {
        "schema_version": SCHEMA_VERSION,
        "display_name": name,
        "student_id": sid,
        "explicit": name_given or id_given,
    }


def deliverable_identity(identity: Mapping[str, Any] | None = None) -> dict[str, str]:
    """Return only safe display fields for generated deliverable metadata."""
    value = run_identity(identity=identity)
    return {"display_name": value["display_name"], "student_id": value["student_id"]}


def _key(value: Any) -> str:
    return str(value).casefold().replace("-", "_").replace(" ", "_")


def _is_identity_key(value: Any) -> bool:
    """Report whether a key names a person or a prior run, in any spelling.

    Matching a single spelling is not enough: ``IDENTITY_KEYS`` already carries
    flattened forms such as ``studentid`` and ``username``, so a key that only
    differs by camel case or a separator names the same field and must be
    treated the same way.
    """
    text = str(value)
    forms = {_key(text), _key(_CAMEL_BOUNDARY.sub("_", text))}
    return bool((forms | {form.replace("_", "") for form in forms}) & _IDENTITY_KEY_FORMS)


def _identity_values(value: Any) -> list[str]:
    """Collect values from identity-labelled fields before removing them."""
    values: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            if _is_identity_key(key) and isinstance(item, str) and item.strip():
                values.append(require_redactable(item, f"identity field {key!r}"))
            values.extend(_identity_values(item))
    elif isinstance(value, list):
        for item in value:
            values.extend(_identity_values(item))
    return values


def _redact_text(value: str, sensitive: Iterable[str]) -> str:
    result = value
    # Longest first prevents a short identifier from partially defeating a
    # longer name replacement.
    for item in sorted({x for x in sensitive if x}, key=len, reverse=True):
        result = re.sub(re.escape(item), "[Redacted]", result, flags=re.IGNORECASE)
    return result


def sanitize_reusable_metadata(
    metadata: Any,
    *,
    identity: Mapping[str, Any] | None = None,
    known_values: Iterable[str] = (),
) -> Any:
    """Remove identity fields and redact their values from reusable metadata."""
    sensitive = [
        require_redactable(value, "known identity value")
        for value in known_values
        if isinstance(value, str) and value.strip()
    ]
    if identity is not None:
        sensitive.extend(_identity_values(identity))
    sensitive.extend(_identity_values(metadata))

    def clean(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {
                str(key): clean(item)
                for key, item in value.items()
                if not _is_identity_key(key)
            }
        if isinstance(value, list):
            return [clean(item) for item in value]
        if isinstance(value, str):
            return _redact_text(value, sensitive)
        return copy.deepcopy(value)

    return clean(metadata)


def sanitize_reusable_example(example: Mapping[str, Any]) -> dict[str, Any]:
    """Return a deep-cleaned example suitable for a shared matching index."""
    if not isinstance(example, Mapping):
        raise ValueError("example must be an object")
    source = copy.deepcopy(dict(example))
    sensitive = _identity_values(source)
    def clean_nested(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {
                str(key): clean_nested(item)
                for key, item in value.items()
                if not _is_identity_key(key)
            }
        if isinstance(value, list):
            return [clean_nested(item) for item in value]
        if isinstance(value, str):
            return _redact_text(value, sensitive)
        return value

    cleaned: dict[str, Any] = {}
    for key, value in source.items():
        if _is_identity_key(key):
            continue
        if _key(key) == "metadata":
            cleaned[str(key)] = sanitize_reusable_metadata(value, known_values=sensitive)
        else:
            cleaned[str(key)] = clean_nested(value)
    return cleaned


def find_identity_leaks(value: Any, forbidden_names: Iterable[str] = ()) -> list[str]:
    """Find likely identity leaks in a public value for distribution checks."""
    names = [name.casefold() for name in forbidden_names if isinstance(name, str) and name.strip()]
    leaks: list[str] = []

    def visit(item: Any, location: str) -> None:
        if isinstance(item, Mapping):
            for key, child in item.items():
                if _is_identity_key(key):
                    if isinstance(child, str) and child in (PLACEHOLDER_DISPLAY_NAME, PLACEHOLDER_STUDENT_ID):
                        continue
                    leaks.append(f"{location}.{key}")
                visit(child, f"{location}.{key}")
        elif isinstance(item, list):
            for index, child in enumerate(item):
                visit(child, f"{location}[{index}]")
        elif isinstance(item, str):
            if _ABSOLUTE_PERSONAL_PATH.search(item):
                leaks.append(location)
            if any(name in item.casefold() for name in names):
                leaks.append(location)

    visit(value, "$" )
    return list(dict.fromkeys(leaks))


def contains_identity_leak(value: Any, forbidden_names: Iterable[str] = ()) -> bool:
    return bool(find_identity_leaks(value, forbidden_names))
