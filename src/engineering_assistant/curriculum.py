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
import math
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

# Every top-level block a course pack may carry.  An exam profile shipped
# unvalidated because this set did not exist: an unknown key was silently
# kept, so a new block arrived with no schema, no check and no reviewer
# deciding it was sound.  Closing the set does not validate the blocks
# already in it; it makes the next one a deliberate change.
PACK_TOP_LEVEL_KEYS = frozenset({
    "schema_version", "course", "coverage", "course_policy",
    "assignment_families", "format", "methods", "gaps", "magnitudes",
    "exam_profile", "evidence_tiers", "related_packs", "not_covered",
    "attestation",
})

# A tool pack describes a tool, not a course, so it carries a different set.
# Holding it to the course set would refuse every tool pack that ships.
TOOL_PACK_TOP_LEVEL_KEYS = frozenset({
    "schema_version", "pack", "coverage", "conventions", "methods", "exemplars",
})

# A magnitude entry is a plausibility bound, and every field of it is load
# bearing at review time: review.py finds an entry by `quantity`, converts the
# student's answer into `unit`, and tests it against `typical_range`.
MAGNITUDE_KEYS = frozenset({"quantity", "unit", "typical_range", "basis", "note"})

# The basis has to say which kind of bound this is.  Physics dressed as course
# convention is the specific false claim this field must not make: a student
# told the course requires a value learns a rule that does not exist, and one
# told physics permits a value learns the opposite.
MAGNITUDE_BASIS_KINDS = ("Physical plausibility", "Handout", "Course method")


def _check_top_level_keys(pack: dict[str, Any], allowed: frozenset[str], where: str) -> None:
    unknown = sorted(set(pack) - allowed)
    if unknown:
        listed = ", ".join(repr(key) for key in unknown)
        raise CurriculumError(
            f"{where}: unknown top-level key{'s' * (len(unknown) != 1)} {listed}; "
            "adding a top-level block requires a schema change that declares the "
            "key and checks what it holds, or it ships with nothing validating it"
        )


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
    # A policy with no source or summary is a claim with nothing behind it:
    # "stated" and nothing more reads as a known rule that nobody can check.
    for field in ("source", "summary"):
        if not isinstance(policy.get(field), str) or not policy[field].strip():
            raise CurriculumError(f"{where}: course_policy needs a {field}")
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


def _check_rendering(pack: dict[str, Any], where: str) -> None:
    """Hold a pack's layout values to the same bounds as a course profile's.

    With no profile, these values go straight to the renderer, so a pack must
    not be a way around the checks a profile would have faced.  A pack may
    state only some values; each one it does state is checked.
    """
    fmt = pack.get("format")
    rendering = fmt.get("rendering") if isinstance(fmt, dict) else None
    if rendering is None:
        return
    rendering = _require_mapping(rendering, f"{where}: format.rendering")
    for key in ("title_page", "abstract", "number_body_pages", "table_captions_above", "figure_captions_below"):
        if rendering.get(key) is not None and not isinstance(rendering[key], bool):
            raise CurriculumError(f"{where}: format.rendering.{key} must be true or false")
    for key, low, high in (("body_font_size", 8, 14), ("line_spacing", 1, 2), ("margin_inches", 0.5, 1.5)):
        value = rendering.get(key)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
            raise CurriculumError(f"{where}: format.rendering.{key} must be between {low} and {high}")


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


# ---------------------------------------------------------------------------
# Exam profiles.
#
# A profile describes the SHAPE of a course's assessments: how many problems,
# what each one is about, how points fall, how long, what aids are allowed,
# what the exam's own instructions demand.  It never holds content.  Not a
# problem statement, not a number out of a problem, not an answer, not a
# paraphrase close enough to rebuild one.
#
# The boundary is enforced structurally, by a closed key set at every level.
# That is a real mechanism and a limited one: it makes a field named for
# content impossible to add without a schema change a reviewer sees, and it
# cannot tell that honest prose has been used to smuggle a question in.
# Reading a profile is still a review step; the loader guarantees the shape.

# What the profile's claims rest on.  Parallel to POLICY_CONFIDENCE, and for
# the same reason: a claim that cannot be stated as documented must say so
# rather than read as documented.
EXAM_CONFIDENCE = frozenset({"stated", "inferred", "unverified"})

# The blocks that assert something about a real assessment.  A profile whose
# material has not been established as genuine may not make these claims: a
# file named like a real final turned out to be machine-generated practice,
# and its shape claims would have been false in every particular.
EXAM_SHAPE_CLAIMS = ("assessments", "aids_provided", "question_shape")

EXAM_PROFILE_KEYS = frozenset({
    "basis", "status", "confidence", "not_documented",
    "assessments", "aids_provided", "question_shape", "instructor_remarks",
    "quizzes", "stated_rules", "pre_submission_checklist",
    "practice_generation_note",
})

# ``id`` and ``source`` are required; the rest are checked when stated.
EXAM_ASSESSMENT_KEYS = frozenset({
    "id", "source", "placement", "chapters", "topics",
    "question_count", "points", "time_limit", "note",
})

EXAM_AIDS_KEYS = frozenset({
    "equation_sheet", "calculator", "open_note", "time_limit", "not_documented",
})

EXAM_QUESTION_SHAPE_KEYS = frozenset({"type", "source", "from_exam", "note"})

# Topics and question types are labels, not prose.  A bound on a label is a
# structural limit, unlike a word list, and a label is where "a problem about
# a 2 m bar loaded to 40 kN" would first try to fit.
SHAPE_LABEL_MAX = 160


def _closed_keys(mapping: dict[str, Any], allowed: frozenset[str], where: str) -> None:
    """Refuse a key the schema does not know.

    An unknown key is how an exam profile shipped unvalidated in the first
    place, and for this block it is the exact failure to prevent: an unknown
    key is where a problem statement or an answer would arrive.
    """
    unknown = sorted(set(mapping) - allowed)
    if unknown:
        listed = ", ".join(repr(key) for key in unknown)
        raise CurriculumError(
            f"{where}: unknown key{'s' * (len(unknown) != 1)} {listed}; "
            "an exam profile holds shape, never content"
        )


def _require_text(mapping: dict[str, Any], key: str, where: str) -> None:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise CurriculumError(f"{where}: needs a non-empty {key}")


def _check_stated_text(mapping: dict[str, Any], keys, where: str) -> None:
    """A field that is present must say something.

    An unknown value is omitted, or named in not_documented.  An empty string
    claims neither, and reads downstream as an answered question.
    """
    for key in keys:
        if key in mapping:
            _require_text(mapping, key, f"{where}: {key}")


def _check_label_list(value: Any, where: str) -> None:
    if not isinstance(value, list):
        raise CurriculumError(f"{where} must be a list")
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise CurriculumError(f"{where}: every entry must be a non-empty string")
        if len(item) > SHAPE_LABEL_MAX:
            raise CurriculumError(
                f"{where}: an entry is longer than {SHAPE_LABEL_MAX} characters; "
                "these are labels, and a profile never carries a question"
            )


def _check_exam_assessment(entry: Any, where: str) -> None:
    entry = _require_mapping(entry, where)
    _closed_keys(entry, EXAM_ASSESSMENT_KEYS, where)
    # Every assessment names its own provenance, at the granularity the
    # evidence has.  A profile-level basis cannot say which document placed
    # which test.
    for key in ("id", "source"):
        _require_text(entry, key, f"{where}: {key}")
    _check_stated_text(entry, ("placement", "chapters", "points", "time_limit", "note"), where)
    if "topics" in entry:
        _check_label_list(entry["topics"], f"{where}: topics")
    # A count reads either way in the evidence: "5" on a cover sheet, "five
    # problems, one per chapter" in a slide.  Both are honest; a blank is not.
    if "question_count" in entry:
        count = entry["question_count"]
        counted = isinstance(count, int) and not isinstance(count, bool) and count > 0
        described = isinstance(count, str) and bool(count.strip())
        if not (counted or described):
            raise CurriculumError(
                f"{where}: question_count must be a positive integer or a non-empty string"
            )


def _check_question_shape(entry: Any, where: str) -> None:
    entry = _require_mapping(entry, where)
    _closed_keys(entry, EXAM_QUESTION_SHAPE_KEYS, where)
    for key in ("type", "source"):
        _require_text(entry, key, f"{where}: {key}")
    _check_label_list([entry["type"]], f"{where}: type")
    _check_stated_text(entry, ("note",), where)
    # A shape drawn from a lecture example or a lab sheet is not a shape seen
    # on an exam.  Both are worth recording and they are different claims, so
    # the distinction is a required field rather than a naming convention that
    # erodes the first time someone mines a real test.
    if not isinstance(entry.get("from_exam"), bool):
        raise CurriculumError(
            f"{where}: from_exam must be true or false; a shape seen in course "
            "materials is not a shape seen on an exam"
        )


def _check_exam_profile(pack: dict[str, Any], where: str) -> None:
    """Hold an exam profile to its own claims, or refuse the pack.

    The block is optional: most courses have no exam evidence, and an absent
    profile is an honest absence.  A profile that is present is checked in
    full.  Ignoring it, which is what happened before this existed, leaves
    data claiming to describe an exam with nothing establishing that the
    claim is honest.
    """
    if "exam_profile" not in pack:
        return
    where = f"{where}: exam_profile"
    profile = _require_mapping(pack["exam_profile"], where)
    _closed_keys(profile, EXAM_PROFILE_KEYS, where)

    # An unsourced profile is impossible by construction: basis is required,
    # and must say what the profile rests on.
    for key in ("basis", "status"):
        _require_text(profile, key, f"{where}: {key}")

    confidence = profile.get("confidence")
    if confidence not in EXAM_CONFIDENCE:
        allowed = ", ".join(sorted(EXAM_CONFIDENCE))
        raise CurriculumError(
            f"{where}: confidence is {confidence!r}, expected one of {allowed}"
        )

    # not_documented is required, and required to name something.  A field
    # left absent reads as zero rather than as unknown, which is how a profile
    # quietly overclaims.  An empty list is a claim of completeness with
    # nothing behind it.
    not_documented = profile.get("not_documented")
    _check_label_list(not_documented, f"{where}: not_documented")
    if not not_documented:
        raise CurriculumError(
            f"{where}: not_documented must name at least one thing the evidence "
            "does not establish"
        )

    # The consequence rule.  Unverified material may be recorded, but it may
    # not describe an assessment: that is the whole lesson of a plausible
    # looking exam file that no instructor ever issued.
    if confidence == "unverified":
        for block in EXAM_SHAPE_CLAIMS:
            if profile.get(block):
                raise CurriculumError(
                    f"{where}: confidence is 'unverified' but it carries {block}; "
                    "material that cannot be established as genuine describes no exam"
                )

    _check_stated_text(profile, ("quizzes", "practice_generation_note"), where)
    for key in ("instructor_remarks", "stated_rules", "pre_submission_checklist"):
        if key in profile:
            value = profile[key]
            if not isinstance(value, list):
                raise CurriculumError(f"{where}: {key} must be a list")
            for index, item in enumerate(value):
                if not isinstance(item, str) or not item.strip():
                    raise CurriculumError(
                        f"{where}: {key}[{index}] must be a non-empty string"
                    )

    for index, entry in enumerate(profile.get("assessments", []) or []):
        _check_exam_assessment(entry, f"{where}: assessments[{index}]")

    if "aids_provided" in profile:
        aids = _require_mapping(profile["aids_provided"], f"{where}: aids_provided")
        _closed_keys(aids, EXAM_AIDS_KEYS, f"{where}: aids_provided")
        _check_stated_text(aids, sorted(EXAM_AIDS_KEYS), f"{where}: aids_provided")

    for index, entry in enumerate(profile.get("question_shape", []) or []):
        _check_question_shape(entry, f"{where}: question_shape[{index}]")


def _check_magnitudes(pack: dict[str, Any], where: str) -> None:
    """Hold every plausibility range to what a review will ask of it.

    A range is a magnitude check, not a course rule.  A strain entered as 5
    where 0.05 belongs is a valid dimensionless number that passes every
    arithmetic and unit check, so only magnitude sense catches it.  That is
    what makes the ranges worth shipping, and it is also what makes a bad one
    dangerous: a host would flag a correct answer, and a student taught by
    false alarms learns to ignore the check.

    Checked here rather than only over the packs in this tree, because a pack
    a student or a contributor adds is exactly the one no shipped-pack test
    ever sees.
    """
    if "magnitudes" not in pack:
        return
    entries = pack["magnitudes"]
    if not isinstance(entries, list):
        raise CurriculumError(f"{where}: magnitudes must be a list")

    # Imported here so loading a pack does not depend on the unit engine
    # until there is actually a unit to read.
    from .units import UnitError, parse_unit

    seen: dict[str, int] = {}
    for index, entry in enumerate(entries):
        at = f"{where}: magnitudes[{index}]"
        entry = _require_mapping(entry, at)
        _closed_keys(entry, MAGNITUDE_KEYS, at)
        for key in ("quantity", "unit", "basis", "note"):
            _require_text(entry, key, f"{at}: {key}")

        quantity = entry["quantity"]
        at = f"{where}: magnitudes[{index}] ({quantity})"
        # review.py takes the first entry whose quantity matches, so a second
        # entry of the same name is unreachable: a range someone wrote, and
        # believes is being applied, that never runs.
        if quantity in seen:
            raise CurriculumError(
                f"{at}: quantity repeats magnitudes[{seen[quantity]}]; a review reads "
                "the first match, so the later range would never be applied"
            )
        seen[quantity] = index

        if not entry["basis"].startswith(MAGNITUDE_BASIS_KINDS):
            kinds = ", ".join(repr(kind) for kind in MAGNITUDE_BASIS_KINDS)
            raise CurriculumError(
                f"{at}: basis must open with one of {kinds}; a bound has to say "
                "whether physics or the course is what sets it"
            )

        bounds = entry["typical_range"]
        if not isinstance(bounds, list) or len(bounds) != 2:
            raise CurriculumError(f"{at}: typical_range must be a list of two numbers")
        low, high = bounds
        for bound in bounds:
            if isinstance(bound, bool) or not isinstance(bound, (int, float)) or not math.isfinite(bound):
                raise CurriculumError(f"{at}: typical_range bounds must be finite numbers")
        # An inverted range is the dangerous direction: `low <= value <= high`
        # is then false for every value, so a correct answer is flagged and
        # the check teaches a student to ignore it.
        if low >= high:
            raise CurriculumError(
                f"{at}: typical_range is {low} to {high}; an inverted or empty range "
                "flags every answer, including the right one"
            )

        try:
            parse_unit(entry["unit"])
        except UnitError as exc:
            # The pack may be right and the registry short.  Say so: a real
            # bound deleted to get a pack loading is worse than a missing unit.
            raise CurriculumError(
                f"{at}: unit {entry['unit']!r} is not one the unit engine reads, so a "
                f"review of this quantity would fail for the student instead of "
                f"checking their answer ({exc}). Add the unit to the registry if the "
                "bound is right."
            ) from exc


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

    _check_top_level_keys(pack, PACK_TOP_LEVEL_KEYS, where)

    version = pack["schema_version"]
    if version != SCHEMA_VERSION:
        raise CurriculumError(
            f"{where}: schema_version is {version!r}, this build reads {SCHEMA_VERSION}"
        )

    _check_coverage(pack["coverage"], where)
    _check_policy(pack["course_policy"], where)
    _check_pipeline_support(pack, where)
    _check_rendering(pack, where)
    _check_exam_profile(pack, where)
    _check_magnitudes(pack, where)
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
    _check_top_level_keys(pack, TOOL_PACK_TOP_LEVEL_KEYS, where)
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


# A textbook index is shared reference material: neither a course nor a tool,
# and two courses may use one book.  It sits two levels under _shared with its
# own file name, so neither pack glob can mistake it for a pack.
BOOKS_DIR = "textbooks"
BOOK_FILE = "book.json"

BOOK_TOP_LEVEL_KEYS = frozenset({
    "schema_version", "book", "pointer_policy", "addressing", "chapters", "appendix",
})


def _attached_packs(course: str, root: Path) -> list[str]:
    """The installed packs a book's course entry reaches.

    A book serves a course number, and one number can have a lecture pack and
    a lab pack, so ``engr204`` reaches ``engr204`` and ``engr204-lab``.
    """
    return sorted(
        pack_file.parent.name
        for pack_file in Path(root).glob("*/pack.json")
        if pack_file.parent.name == course or pack_file.parent.name.startswith(f"{course}-")
    )


def load_book(path: Path) -> dict[str, Any]:
    """Return the textbook index at ``path``, or raise ``CurriculumError``.

    The course-to-book edge lives here and nowhere else, so this is where it is
    checked: a course entry that reaches no installed pack is a book that never
    appears on its course's card, and nothing downstream would say so.
    """
    path = Path(path)
    where = f"{path.parent.name}/{path.name}"
    try:
        book = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CurriculumError(f"{where}: cannot be read: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise CurriculumError(f"{where}: is not valid JSON: {exc}") from exc

    book = _require_mapping(book, where)
    _check_top_level_keys(book, BOOK_TOP_LEVEL_KEYS, where)
    if book.get("schema_version") != SCHEMA_VERSION:
        raise CurriculumError(
            f"{where}: schema_version is {book.get('schema_version')!r}, this build reads {SCHEMA_VERSION}"
        )

    record = _require_mapping(book.get("book"), f"{where}: book")
    if record.get("id") != path.parent.name:
        raise CurriculumError(
            f"{where}: book.id is {record.get('id')!r} but its directory is {path.parent.name!r}; "
            "a reference resolves by directory, so the two must not differ"
        )
    # No author is required: a citation may withhold one on purpose.
    if not isinstance(record.get("citation"), str) or not record["citation"].strip():
        raise CurriculumError(f"{where}: book needs a citation")
    # The policy is the book's honesty statement, as coverage.notes is a pack's:
    # an index that does not say it cannot check a value reads as one that can.
    for field in ("pointer_policy", "addressing"):
        if not isinstance(book.get(field), str) or not book[field].strip():
            raise CurriculumError(f"{where}: {field} must say what this index can and cannot tell a student")

    courses = record.get("courses")
    if not isinstance(courses, list) or not courses or not all(isinstance(c, str) and c for c in courses):
        raise CurriculumError(f"{where}: book.courses must name at least one course")
    curriculum_root = path.parents[3]
    for course in courses:
        if not _attached_packs(course, curriculum_root):
            raise CurriculumError(
                f"{where}: book.courses names {course!r}, which matches no installed pack "
                f"({course} or {course}-*); the book would never appear on a course's card"
            )

    for key, items in book.items():
        if not isinstance(items, list):
            continue
        seen: set[str] = set()
        for item in items:
            item = _require_mapping(item, f"{where}: an entry in {key}")
            item_id = item.get("id")
            if not isinstance(item_id, str) or not item_id:
                raise CurriculumError(f"{where}: an entry in {key} has no id")
            if "." in item_id:
                raise CurriculumError(
                    f"{where}: {key} id {item_id!r} contains '.', which separates the parts of an "
                    "address, so the entry could never be fetched"
                )
            if item_id in seen:
                raise CurriculumError(f"{where}: {key} id {item_id!r} appears more than once")
            seen.add(item_id)
            if not isinstance(item.get("title"), str) or not item["title"].strip():
                raise CurriculumError(f"{where}: {key}.{item_id} needs a title")
            if not any(isinstance(item.get(k), str) and item[k].strip() for k in ("basis", "source")):
                raise CurriculumError(f"{where}: {key}.{item_id} needs a basis saying how the pointer was verified")
    return book


def books_for_pack(pack_id: str, root: Path) -> list[str]:
    """The ids of the books whose course entries reach ``pack_id``."""
    found = []
    for book_file in sorted((Path(root) / SHARED_DIR / BOOKS_DIR).glob(f"*/{BOOK_FILE}")):
        courses = load_book(book_file)["book"]["courses"]
        if any(pack_id in _attached_packs(course, root) for course in courses):
            found.append(book_file.parent.name)
    return found


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


# The eight values a renderer needs to lay out a page.  A course profile must
# state all of them; a pack may state some, and the rest fall to the renderer's
# own defaults, which are recorded as defaults rather than passed off as rules.
RENDERING_FIELDS = (
    "title_page", "abstract", "number_body_pages", "table_captions_above",
    "figure_captions_below", "body_font_size", "line_spacing", "margin_inches",
)


def pack_for_course(course: str, root: Path = DEFAULT_CURRICULUM) -> dict[str, Any] | None:
    """Return the shipped pack for ``course`` with its content hash, or None.

    A course id is a pack's directory name.  Only course packs qualify; a tool
    pack describes EES or MATLAB, not the conventions of any one course.
    """
    if not isinstance(course, str) or not course or course.startswith("_"):
        return None
    path = Path(root) / course.lower() / "pack.json"
    if not path.is_file() or path.is_symlink():
        return None
    import hashlib

    pack = load_pack(path)
    return {
        "id": path.parent.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "pack": pack,
    }


def pack_style(entry: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Return the style a pack supplies to the renderer, and where each value came from.

    Only values the pack states are passed on, so the renderer fills the rest
    from its own defaults.  The basis names both, so a default can never be
    presented as a course rule.
    """
    fmt = entry["pack"].get("format") or {}
    rendering = fmt.get("rendering") if isinstance(fmt.get("rendering"), dict) else {}
    stated_basis = fmt.get("rendering_basis") if isinstance(fmt.get("rendering_basis"), dict) else {}
    supplied = {key: rendering[key] for key in RENDERING_FIELDS if rendering.get(key) is not None}
    fields = {}
    for key in RENDERING_FIELDS:
        if key not in supplied:
            fields[key] = "renderer default"
        elif str(stated_basis.get(key, "")).startswith("default"):
            fields[key] = "pack default, not a course rule"
        else:
            fields[key] = "course pack rule"
    basis = {
        "source": f"shipped pack {entry['id']}",
        "pack_sha256": entry["sha256"],
        "format_coverage": entry["pack"]["coverage"]["format"],
        "fields": fields,
        # What each stated value rests on, in the pack's own words.  "Course
        # pack rule" says only that the pack states it; this says whether that
        # is a written rule or the instructor's consistent practice, so a host
        # never reports a value as more certain than its evidence.
        "field_basis": {key: stated_basis.get(key) for key in supplied},
    }
    return ({"rendering": supplied} if supplied else None), basis


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
    "EXAM_CONFIDENCE",
    "BOOKS_DIR",
    "BOOK_FILE",
    "BOOK_TOP_LEVEL_KEYS",
    "books_for_pack",
    "load_book",
    "PACK_TOP_LEVEL_KEYS",
    "TOOL_PACK_TOP_LEVEL_KEYS",
    "MAGNITUDE_KEYS",
    "MAGNITUDE_BASIS_KINDS",
    "SCHEMA_VERSION",
    "CurriculumError",
    "coverage_report",
    "load_pack",
    "load_packs",
    "load_tool_pack",
    "load_tool_packs",
    "pack_for_course",
    "pack_style",
    "RENDERING_FIELDS",
]
