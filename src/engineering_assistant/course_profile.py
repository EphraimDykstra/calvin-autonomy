"""Reviewed, course-scoped method and presentation profiles."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .common import atomic_json, digest, slug
from .evidence import evidence_review_queue, resolve_evidence


def profile_path(workspace: Path, course: str) -> Path:
    return Path(workspace) / "courses" / slug(course) / "profile.json"


def _validate_rendering(value: Any) -> None:
    if not isinstance(value, dict):
        raise ValueError("course profile requires normalized rendering settings")
    font_size = value.get("body_font_size")
    spacing = value.get("line_spacing")
    margin = value.get("margin_inches")
    if isinstance(font_size, bool) or not isinstance(font_size, (int, float)) or not 8 <= font_size <= 14:
        raise ValueError("body_font_size must be between 8 and 14 points")
    if isinstance(spacing, bool) or not isinstance(spacing, (int, float)) or not 1 <= spacing <= 2:
        raise ValueError("line_spacing must be between 1 and 2")
    if isinstance(margin, bool) or not isinstance(margin, (int, float)) or not 0.5 <= margin <= 1.5:
        raise ValueError("margin_inches must be between 0.5 and 1.5")
    for key in ("title_page", "abstract", "number_body_pages", "table_captions_above", "figure_captions_below"):
        if not isinstance(value.get(key), bool):
            raise ValueError(f"rendering setting {key} must be true or false")


def validate_profile(profile: dict) -> None:
    if not isinstance(profile, dict):
        raise ValueError("course profile must be an object")
    if profile.get("review_status") != "reviewed":
        raise ValueError("course profile must be explicitly reviewed")
    precedence = profile.get("precedence")
    if not isinstance(precedence, list) or not precedence or any(not isinstance(item, str) or not item for item in precedence):
        raise ValueError("course profile requires a source precedence list")
    if not isinstance(profile.get("rules"), dict) or not profile["rules"]:
        raise ValueError("course profile requires style rules")
    evidence = profile.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError("course profile requires reviewed source evidence")
    _validate_rendering(profile.get("rendering"))


def set_course_profile(workspace: Path, course: str, profile: dict) -> dict:
    course = slug(course)
    validate_profile(profile)
    evidence_errors = resolve_evidence(workspace, course, profile.get("evidence"))
    if evidence_errors:
        raise ValueError("course profile evidence failed: " + "; ".join(evidence_errors))
    value = dict(profile)
    value["course"] = course
    path = profile_path(workspace, course)
    atomic_json(path, value)
    return {"course": course, "path": path.relative_to(Path(workspace)).as_posix(), "sha256": digest(value), "profile": value}


def load_course_profile(workspace: Path, course: str) -> dict:
    path = profile_path(workspace, course)
    if path.is_symlink() or not path.is_file():
        raise FileNotFoundError(path)
    value = json.loads(path.read_text(encoding="utf-8"))
    validate_profile(value)
    if value.get("course") != slug(course):
        raise ValueError("course profile belongs to a different course")
    evidence_errors = resolve_evidence(workspace, course, value.get("evidence"))
    if evidence_errors:
        raise ValueError("course profile evidence failed: " + "; ".join(evidence_errors))
    return value


COVERAGE_SCHEMA_VERSION = 1
COVERAGE_STATES = ("reviewed", "provisional", "absent")
# Coverage item kind -> the key callers use in ``expected``.
COVERAGE_KINDS = {
    "assignment_family": "assignment_families",
    "method": "methods",
    "formatting_rule": "formatting_rules",
}
ONBOARDING_SCHEMA_VERSION = 1


def _read_json_object(path: Path) -> dict | None:
    """Read one managed JSON object, or None when it is missing or unusable."""
    path = Path(path)
    try:
        if path.is_symlink() or not path.is_file():
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _examples(workspace: Path, course: str) -> list[dict]:
    """Read registered examples read-only; an unusable registry registers none."""
    value = _read_json_object(Path(workspace) / "courses" / slug(course) / "examples.json")
    examples = (value or {}).get("examples")
    if not isinstance(examples, list):
        return []
    return [item for item in examples if isinstance(item, dict)]


def _profile_coverage(workspace: Path, course: str) -> tuple[str, str, list[str], list[dict]]:
    """Classify the stored profile as reviewed, provisional or absent.

    Returns the state, the reason for it, the formatting rule names it covers,
    and its citations tagged with the downstream consumer a pending review
    blocks.  Never raises for a degraded workspace: the states this reports are
    exactly the ones load_course_profile refuses.
    """
    path = profile_path(workspace, course)
    if path.is_symlink() or not path.is_file():
        return "absent", "no course profile is registered for this course", [], []
    value = _read_json_object(path)
    if value is None:
        return "absent", "the stored course profile is unreadable", [], []
    if value.get("course") != slug(course):
        return "absent", "the stored course profile belongs to a different course", [], []
    try:
        validate_profile(value)
    except ValueError as exc:
        return "absent", f"the stored course profile is not usable: {exc}", [], []
    names = sorted({str(key) for key in value.get("rules", {})} | {"rendering"})
    evidence = value.get("evidence")
    citations = [
        dict(item, used_by="course-profile")
        for item in (evidence if isinstance(evidence, list) else [])
        if isinstance(item, dict)
    ]
    # Deliberately NOT reading profile["review_status"].  validate_profile above
    # already forces that field to "reviewed", so every profile that parses
    # self-asserts a review.  Trusting it would launder that self-assertion into
    # a coverage claim, which is the exact dishonesty this report exists to
    # prevent.  "reviewed" here means the cited evidence still resolves and has
    # passed exact visual review.  Do not "simplify" this to read the field.
    blockers = resolve_evidence(workspace, course, evidence)
    if blockers:
        return "provisional", "cited evidence does not resolve as reviewed: " + "; ".join(blockers), names, citations
    return "reviewed", "backed by resolved, reviewed course evidence", names, citations


def _example_items(examples: list[dict]) -> list[dict]:
    """Group registered examples into assignment family and method coverage."""
    groups: dict[tuple[str, str], dict[str, list[str]]] = {}
    for example in examples:
        assignment = example.get("assignment")
        if not isinstance(assignment, dict):
            continue
        example_id = example.get("id")
        bucket = "reviewed" if example.get("review_status") == "reviewed" else "provisional"
        for kind, field in (("assignment_family", "family"), ("method", "method")):
            name = assignment.get(field)
            if not isinstance(name, str) or not name.strip():
                continue
            group = groups.setdefault((kind, name.strip()), {"reviewed": [], "provisional": []})
            if isinstance(example_id, str) and example_id and example_id not in group[bucket]:
                group[bucket].append(example_id)
    items = []
    for (kind, name), group in groups.items():
        reviewed, provisional = sorted(group["reviewed"]), sorted(group["provisional"])
        if reviewed:
            state, reason = "reviewed", f"{len(reviewed)} reviewed example(s) registered"
        else:
            state, reason = "provisional", f"{len(provisional)} registered example(s), none marked reviewed"
        items.append({"kind": kind, "name": name, "state": state, "reason": reason, "sources": reviewed + provisional})
    return items


def _expected_names(expected: object, key: str) -> list[str]:
    values = expected.get(key) if isinstance(expected, dict) else None
    if not isinstance(values, list):
        return []
    return [item.strip() for item in values if isinstance(item, str) and item.strip()]


def course_coverage(workspace: Path, course: str, expected: object = None) -> dict:
    """Report what one course can actually back, in three honest states.

    Every formatting rule, assignment family and method is reported as reviewed
    (resolved, reviewed evidence stands behind it), provisional (registered but
    not backed by a reviewed source) or absent (nothing covers it at all).  The
    report must never imply support the course cannot back, so ``ready`` is
    false whenever the profile is missing or degraded, however many reviewed
    examples exist: without a loading profile nothing renders.

    ``expected`` optionally names what the caller needs, as
    ``{"assignment_families": [...], "methods": [...], "formatting_rules": [...]}``;
    anything asked for that nothing covers is reported absent.  Absence is
    reported without it too -- a course with no usable profile has no formatting
    coverage at all -- so the three states never collapse to two.  Nothing is
    written to disk.
    """
    course = slug(course)
    profile_state, profile_reason, rule_names, _ = _profile_coverage(workspace, course)
    # "rendering" is a structurally known dimension every course must cover, so
    # it is always reported. Without it a course that has no profile would emit
    # no formatting items at all and the bare call could never reach "absent".
    rule_names = sorted(set(rule_names) | {"rendering"})
    items = [
        {
            "kind": "formatting_rule",
            "name": name,
            "state": profile_state,
            "reason": profile_reason,
            "sources": [] if profile_state == "absent" else ["course-profile"],
        }
        for name in rule_names
    ]
    items.extend(_example_items(_examples(workspace, course)))

    known = {(item["kind"], item["name"]) for item in items}
    for kind, key in COVERAGE_KINDS.items():
        for name in _expected_names(expected, key):
            if (kind, name) in known:
                continue
            known.add((kind, name))
            items.append({
                "kind": kind,
                "name": name,
                "state": "absent",
                "reason": "nothing registered for this course covers it",
                "sources": [],
            })

    items.sort(key=lambda item: (item["kind"], item["name"]))
    blockers = []
    if profile_state != "reviewed":
        blockers.append(f"course profile is {profile_state}: {profile_reason}")
    if not any(item["kind"] == "assignment_family" and item["state"] == "reviewed" for item in items):
        blockers.append("no assignment family has a reviewed example behind it")
    # An unextracted source is guidance nobody has read, and it may carry a
    # method or formatting constraint that contradicts everything above, so the
    # report must not clear a course while one is outstanding.
    unextracted = evidence_review_queue(workspace, course, None)["documents_awaiting_extraction"]
    if unextracted:
        blockers.append(f"{unextracted} course source(s) are not yet extracted, so their guidance is unread")
    return {
        "schema_version": COVERAGE_SCHEMA_VERSION,
        "course": course,
        "ready": not blockers,
        "summary": {state: sum(1 for item in items if item["state"] == state) for state in COVERAGE_STATES},
        "items": items,
        "blockers": blockers,
    }


def course_onboarding_status(workspace: Path, course: str) -> dict:
    """Report the guided path for adding one course, as data rather than lore.

    The steps are strictly ordered, so the first unfinished step is the one to
    work on next and every later unfinished step is blocked behind it.  The
    embedded review queue names what is pending exact visual review and what
    that pending review is holding up downstream.  Nothing is written to disk.
    """
    course = slug(course)
    profile_state, profile_reason, _, citations = _profile_coverage(workspace, course)
    examples = _examples(workspace, course)
    reviewed_examples = [item for item in examples if item.get("review_status") == "reviewed"]
    queue = evidence_review_queue(workspace, course, citations)

    plan = [
        (
            "ingest_sources",
            queue["documents_total"] > 0,
            f"{queue['documents_total']} active course source(s) in the catalog",
        ),
        (
            "resolve_extraction",
            queue["documents_total"] > 0 and queue["documents_awaiting_extraction"] == 0,
            f"{queue['documents_awaiting_extraction']} source(s) awaiting extraction or OCR"
            if queue["documents_total"]
            else "no ingested sources to extract yet",
        ),
        (
            "review_evidence",
            queue["blocks_reviewed"] > 0 and queue["status"] == "clear",
            f"{queue['blocks_reviewed']} of {queue['blocks_total']} extracted passage(s) reviewed; "
            f"{queue['pending_count']} cited passage(s) pending exact visual review",
        ),
        ("register_profile", profile_state == "reviewed", profile_reason),
        (
            "register_examples",
            bool(reviewed_examples),
            f"{len(reviewed_examples)} reviewed and {len(examples) - len(reviewed_examples)} "
            "provisional example(s) registered",
        ),
    ]

    first_unfinished = next((step_id for step_id, done, _ in plan if not done), None)
    steps = []
    for index, (step_id, done, detail) in enumerate(plan):
        if done:
            state = "done"
        elif step_id == first_unfinished:
            state = "pending"
        else:
            state = "blocked"
        steps.append({
            "id": step_id,
            "state": state,
            "detail": detail,
            # A finished step holds nothing up. Only unfinished work blocks.
            "blocks": [] if done else [other for other, other_done, _ in plan[index + 1:] if not other_done],
        })
    return {
        "schema_version": ONBOARDING_SCHEMA_VERSION,
        "course": course,
        "ready": first_unfinished is None,
        "next_step": first_unfinished,
        "steps": steps,
        "blockers": [f"{step['id']}: {step['detail']}" for step in steps if step["state"] != "done"],
        "review_queue": queue,
    }


__all__ = [
    "course_coverage",
    "course_onboarding_status",
    "load_course_profile",
    "profile_path",
    "set_course_profile",
    "validate_profile",
]
