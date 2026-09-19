"""Load shipped curriculum packs and report honestly on what they cover.

A pack holds rules derived from a course's own materials: how deliverables are
formatted, how the professor teaches a method, what an assignment family looks
like.  It never holds the source documents or a student's work.

Every check here fails closed.  A student cannot tell the difference between a
pack that knows a course and a host that is merely fluent about it, so the
honesty has to be structural: a pack that cannot state its own coverage is
refused rather than loaded with a permissive default.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1

# What a pack is allowed to claim about a dimension of itself.  "none" is a
# first-class, shippable answer: a pack that says it has no format rules is
# working correctly, and the host can then ask the student for a handout.
COVERAGE_LEVELS = frozenset({"high", "partial", "none"})

# How much weight a policy statement carries.  "stale" exists because archived
# syllabi describe a term that has passed: they prove a policy existed, not
# what it is now, and shipping the old terms as current would be a false claim
# about the present.
POLICY_CONFIDENCE = frozenset({"stated", "inferred", "stale", "unknown"})

COVERAGE_DIMENSIONS = ("format", "methods", "assignments")

# A tool pack describes a tool used across courses rather than a course, so it
# answers different questions and lives under _shared/.  It carries no
# course_policy: a policy belongs to a course, not to EES.
TOOL_COVERAGE_DIMENSIONS = ("conventions", "methods", "pitfalls")

SHARED_DIR = "_shared"

# Packs ship with the install, so they are found relative to it rather than to
# wherever the student happened to run the command.  The launcher does not
# change directory, so a bare relative default would report no coverage at all
# from a subdirectory: the honesty layer inverted, telling a student the system
# knows nothing about a course it knows a great deal about.
DEFAULT_CURRICULUM = Path(__file__).resolve().parents[2] / "curriculum"

_REQUIRED_TOP_LEVEL = ("schema_version", "coverage", "course_policy")


class CurriculumError(Exception):
    """A pack cannot be trusted to describe itself, so it is not loaded."""


def _require_mapping(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CurriculumError(f"{where} must be an object")
    return value


def _check_coverage(coverage: Any, where: str) -> None:
    coverage = _require_mapping(coverage, f"{where}: coverage")
    for dimension in COVERAGE_DIMENSIONS:
        if dimension not in coverage:
            raise CurriculumError(f"{where}: coverage is missing '{dimension}'")
        level = coverage[dimension]
        # An unrecognised level must refuse rather than degrade to a default.
        # Degrading would silently convert "we do not know" into a claim.
        if level not in COVERAGE_LEVELS:
            allowed = ", ".join(sorted(COVERAGE_LEVELS))
            raise CurriculumError(
                f"{where}: coverage '{dimension}' is {level!r}, expected one of {allowed}"
            )


def _check_policy(policy: Any, where: str) -> None:
    policy = _require_mapping(policy, f"{where}: course_policy")
    confidence = policy.get("confidence")
    if confidence not in POLICY_CONFIDENCE:
        allowed = ", ".join(sorted(POLICY_CONFIDENCE))
        raise CurriculumError(
            f"{where}: course_policy confidence is {confidence!r}, expected one of {allowed}"
        )
    # A stale or unknown policy must not carry terms.  Archived syllabus text
    # read as current is the failure this separation exists to prevent.
    if confidence in {"stale", "unknown"}:
        for field in ("permitted", "prohibited"):
            if policy.get(field):
                raise CurriculumError(
                    f"{where}: course_policy is {confidence!r} but lists {field}; "
                    "terms that cannot be stated as current must be omitted"
                )


def _extension_tokens(extension: Any) -> set[str]:
    """Read the formats an artifact's extension names.

    Real packs describe extensions the way the evidence reads, not as a bare
    token: ".docx or .pdf", ".docx (submitted as PDF)".  That honesty is worth
    keeping, so this reads the words out of it instead of demanding a format
    the evidence cannot always support.
    """
    if not isinstance(extension, str):
        return set()
    return set(re.findall(r"[a-z0-9]+", extension.lower()))


def _check_pipeline_support(pack: dict[str, Any], where: str) -> None:
    """Refuse a pack that claims more of the pipeline than exists.

    A course whose deliverable is a Quarto file, a MATLAB script or a bare
    Python file cannot be rendered or run here, so a host must not call it
    ready.  The pack is where that truth is stated, which makes it the place
    a false claim would enter.  Two claims are checkable: nothing here ever
    executes a student's code, and a pack that says it renders must name a
    submitted artifact the renderer can actually produce.
    """
    fmt = pack.get("format")
    if not isinstance(fmt, dict) or "pipeline_support" not in fmt:
        return
    support = _require_mapping(fmt["pipeline_support"], f"{where}: pipeline_support")
    for flag in ("render", "execute", "verify_rendered_output"):
        if not isinstance(support.get(flag), bool):
            raise CurriculumError(f"{where}: pipeline_support.{flag} must be true or false")
    if support["execute"]:
        raise CurriculumError(
            f"{where}: pipeline_support.execute is true, but nothing in this project runs "
            "a student's code; the student runs it and brings the results back"
        )
    note = support.get("note")
    if not isinstance(note, str) or not note.strip():
        raise CurriculumError(
            f"{where}: pipeline_support.note must say what the student runs and brings back"
        )
    if support["render"]:
        # Imported here so loading a pack does not pull in the PDF stack.
        from .artifact_rendering import SUPPORTED_RENDER_FORMATS

        artifacts = fmt.get("artifacts") or []
        renderable = [
            a for a in artifacts
            if isinstance(a, dict) and _extension_tokens(a.get("extension")) & SUPPORTED_RENDER_FORMATS
        ]
        if artifacts and not renderable:
            raise CurriculumError(
                f"{where}: pipeline_support.render is true, but no submitted artifact is one "
                f"the renderer produces ({', '.join(sorted(SUPPORTED_RENDER_FORMATS))})"
            )


def load_pack(path: Path) -> dict[str, Any]:
    """Return the pack at ``path``, or raise ``CurriculumError``."""
    path = Path(path)
    where = path.name
    try:
        pack = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CurriculumError(f"{where}: cannot be read: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise CurriculumError(f"{where}: is not valid JSON: {exc}") from exc

    pack = _require_mapping(pack, where)
    for key in _REQUIRED_TOP_LEVEL:
        # course_policy is required even when empty of terms.  A missing key
        # reads as "this course has no policy"; an explicit unknown reads as
        # "we did not find one".  Those are different claims.
        if key not in pack:
            raise CurriculumError(f"{where}: is missing required key '{key}'")

    version = pack["schema_version"]
    if version != SCHEMA_VERSION:
        raise CurriculumError(
            f"{where}: schema_version is {version!r}, this build reads {SCHEMA_VERSION}"
        )

    _check_coverage(pack["coverage"], where)
    _check_policy(pack["course_policy"], where)
    _check_pipeline_support(pack, where)
    return pack


def load_tool_pack(path: Path) -> dict[str, Any]:
    """Return the tool pack at ``path``, or raise ``CurriculumError``.

    Checked separately from course packs because it answers different
    questions.  Leaving it unchecked would put the pack with the most
    exemplars behind no validation at all.
    """
    path = Path(path)
    where = f"{path.parent.name}/{path.name}"
    try:
        pack = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CurriculumError(f"{where}: cannot be read: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise CurriculumError(f"{where}: is not valid JSON: {exc}") from exc

    pack = _require_mapping(pack, where)
    if pack.get("schema_version") != SCHEMA_VERSION:
        raise CurriculumError(
            f"{where}: schema_version is {pack.get('schema_version')!r}, "
            f"this build reads {SCHEMA_VERSION}"
        )

    coverage = _require_mapping(pack.get("coverage"), f"{where}: coverage")
    for dimension in TOOL_COVERAGE_DIMENSIONS:
        if dimension not in coverage:
            raise CurriculumError(f"{where}: coverage is missing '{dimension}'")
        if coverage[dimension] not in COVERAGE_LEVELS:
            allowed = ", ".join(sorted(COVERAGE_LEVELS))
            raise CurriculumError(
                f"{where}: coverage '{dimension}' is {coverage[dimension]!r}, "
                f"expected one of {allowed}"
            )

    # An exemplar naming a file that is not there degrades to "no exemplar" at
    # the point of use, which reads as a tool with nothing to show.
    for exemplar in pack.get("exemplars", []) or []:
        exemplar = _require_mapping(exemplar, f"{where}: an exemplar")
        name = exemplar.get("file")
        if not name:
            raise CurriculumError(f"{where}: exemplar {exemplar.get('id')!r} names no file")
        if not (path.parent / name).is_file():
            raise CurriculumError(f"{where}: exemplar file is missing: {name}")
    return pack


def load_tool_packs(root: Path) -> dict[str, dict[str, Any]]:
    """Return every tool pack under ``root/_shared``, keyed by directory name."""
    shared = Path(root) / SHARED_DIR
    if not shared.is_dir():
        return {}
    return {
        pack_file.parent.name: load_tool_pack(pack_file)
        for pack_file in sorted(shared.glob("*/pack.json"))
    }


def load_packs(root: Path) -> dict[str, dict[str, Any]]:
    """Return every pack under ``root``, keyed by its directory name.

    A malformed pack raises rather than being skipped.  Skipping would leave
    the host reporting coverage for a course whose rules never loaded.
    """
    root = Path(root)
    if not root.is_dir():
        return {}
    packs: dict[str, dict[str, Any]] = {}
    for pack_file in sorted(root.glob("*/pack.json")):
        # _shared holds tool packs, which answer different questions and are
        # loaded by load_tool_packs.
        if pack_file.parent.name == SHARED_DIR:
            continue
        packs[pack_file.parent.name] = load_pack(pack_file)
    return packs


def _pipeline_summary(pack: dict[str, Any]) -> dict[str, Any] | None:
    fmt = pack.get("format")
    support = fmt.get("pipeline_support") if isinstance(fmt, dict) else None
    if not isinstance(support, dict):
        return None
    return {
        "render": support.get("render"),
        "execute": support.get("execute"),
        "verify_rendered_output": support.get("verify_rendered_output"),
        "note": support.get("note"),
    }


def coverage_report(
    packs: dict[str, dict[str, Any]],
    tool_packs: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Summarise what is and is not covered, for the host to say out loud."""
    courses = []
    for pack_id, pack in sorted(packs.items()):
        coverage = pack["coverage"]
        course = pack.get("course", {})
        policy = pack["course_policy"]
        courses.append(
            {
                "id": pack_id,
                "code": course.get("code"),
                "title": course.get("title"),
                "professor": course.get("professor"),
                "coverage": {d: coverage[d] for d in COVERAGE_DIMENSIONS},
                "notes": coverage.get("notes"),
                # The host surfaces this once and leaves the decision with the
                # student; it never gates a deliverable on it.
                "policy_confidence": policy.get("confidence"),
                "policy_answered": policy.get("professor_answer") is not None,
                # Where the pipeline cannot render or run a deliverable, the
                # host must say so and must not call the work ready.
                "pipeline": _pipeline_summary(pack),
            }
        )
    tools = [
        {
            "id": tool_id,
            "title": pack.get("pack", {}).get("title"),
            "coverage": {d: pack["coverage"][d] for d in TOOL_COVERAGE_DIMENSIONS},
            "notes": pack["coverage"].get("notes"),
        }
        for tool_id, pack in sorted((tool_packs or {}).items())
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "course_count": len(courses),
        "courses": courses,
        "tools": tools,
    }


__all__ = [
    "COVERAGE_DIMENSIONS",
    "DEFAULT_CURRICULUM",
    "SHARED_DIR",
    "TOOL_COVERAGE_DIMENSIONS",
    "COVERAGE_LEVELS",
    "POLICY_CONFIDENCE",
    "SCHEMA_VERSION",
    "CurriculumError",
    "coverage_report",
    "load_pack",
    "load_packs",
    "load_tool_pack",
    "load_tool_packs",
]
