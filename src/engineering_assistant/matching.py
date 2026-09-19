"""Course-scoped matching of prior assignment examples.

The matcher deliberately treats a prior example as evidence about an assignment,
not as a solution to copy.  It returns a classification and an explanation of
the changes a host should account for before using any example.
"""

from __future__ import annotations

import copy
import json
import math
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from .identity import sanitize_reusable_example


SCHEMA_VERSION = 1
CLASSIFICATIONS = (
    "exact_repeat",
    "input_variant",
    "method_changing_variant",
    "presentation_only",
    "no_useful_match",
)
_VALID_REVIEW_STATUS = {"provisional", "reviewed"}
_BAD_STATUS_WORDS = {"incorrect", "rejected", "invalid", "wrong", "stale", "deprecated"}
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in",
    "into", "is", "of", "on", "or", "that", "the", "their", "this", "to",
    "use", "with", "must", "should", "shall", "will",
}

# Mutually exclusive physical regimes.  Each group lists alternatives that
# cannot both describe one problem; the first phrase of an alternative is its
# display label.
#
# This vocabulary is a REASON ENRICHER ONLY and is deliberately non-exhaustive.
# Correctness never depends on a term appearing here: any change to the problem
# statement already forces a method-changing classification (see
# ``_forces_fresh_method``).  These groups only let the matcher say "prior
# states parallel-flow, current states counterflow" instead of "text changed".
_REGIME_GROUPS: tuple[tuple[str, tuple[tuple[str, ...], ...]], ...] = (
    ("time dependence", (
        ("steady state", "steady flow", "steady"),
        ("transient", "unsteady", "time dependent", "time varying", "started from cold", "startup", "shutdown"),
    )),
    ("flow arrangement", (
        ("parallel flow", "cocurrent", "co current"),
        ("counterflow", "counter flow", "countercurrent", "counter current"),
        ("crossflow", "cross flow"),
    )),
    ("flow regime", (("laminar",), ("turbulent",))),
    ("compressibility", (("incompressible",), ("compressible",))),
    ("process path", (("isothermal",), ("adiabatic",), ("isentropic",), ("isobaric",), ("isochoric",))),
    ("reversibility", (("reversible",), ("irreversible",))),
    ("system boundary", (("closed system", "control mass"), ("open system", "control volume"))),
    ("thermal model", (("lumped capacitance", "lumped"), ("distributed",))),
    ("dissipation", (
        ("frictionless", "neglect friction", "neglecting friction", "neglect the friction"),
        ("account for friction", "including friction", "with friction"),
    )),
    ("thermal boundary", (
        ("insulated", "perfectly insulated", "no heat loss"),
        ("loses heat", "heat loss to the surroundings", "not insulated"),
    )),
)

# Quantity-basis markers.  A basis change redefines the quantity itself and so
# changes the method, unlike a same-dimension unit rescale (m -> ft), which is
# an ordinary input variant.
_BASIS_GROUPS: tuple[tuple[str, tuple[tuple[str, ...], ...]], ...] = (
    ("quantity basis", (
        ("kg", "lbm", "gram", "kilogram", "mass basis", "per mass"),
        ("kmol", "mol", "lbmol", "kgmol", "molar basis", "per mole"),
    )),
    ("pressure reference", (("gauge", "gage"), ("absolute", "abs"))),
    ("moisture basis", (("dry basis", "dry"), ("wet basis", "wet"))),
)


def _phrase_present(haystack: str, phrase: str) -> bool:
    """Whole-token phrase search, so 'reversible' never matches 'irreversible'."""
    padded = f" {haystack} "
    needle = f" {phrase} "
    start = padded.find(needle)
    while start != -1:
        # "non adiabatic" and "not insulated" assert the opposite of the term.
        prefix = padded[:start + 1].rstrip().rsplit(" ", 1)
        if not prefix or prefix[-1] not in {"non", "not"}:
            return True
        start = padded.find(needle, start + 1)
    return False


def _alternatives_present(text: str, groups) -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for label, alternatives in groups:
        present = {
            alternative[0]
            for alternative in alternatives
            if any(_phrase_present(text, phrase) for phrase in alternative)
        }
        if present:
            found[label] = present
    return found


def _group_conflicts(previous: str, current: str, groups) -> list[str]:
    """Report only genuine A-vs-B disagreements.

    A term present on both sides is agreement and reports nothing; a term
    present on only one side is silence, not conflict, and also reports nothing.
    """
    old_found = _alternatives_present(previous, groups)
    new_found = _alternatives_present(current, groups)
    conflicts = []
    for label in sorted(set(old_found) & set(new_found)):
        old_alternatives, new_alternatives = old_found[label], new_found[label]
        if old_alternatives != new_alternatives:
            conflicts.append(
                f"{label} changed: prior states {', '.join(sorted(old_alternatives))}; "
                f"current states {', '.join(sorted(new_alternatives))}"
            )
    return conflicts


def _slug(value: str) -> str:
    """Use common.slug when available, while keeping this module usable alone."""
    if not isinstance(value, str) or not value or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("course and record IDs may contain only letters, digits, '_' and '-'")
    try:
        from .common import slug
    except ImportError:
        return value
    return slug(value)


def _jsonable(value: Any, where: str = "value") -> Any:
    """Validate JSON-like values and reject non-finite numbers."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{where} must be finite")
        return value
    if isinstance(value, list):
        return [_jsonable(item, f"{where}[{i}]") for i, item in enumerate(value)]
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{where} keys must be strings")
            result[key] = _jsonable(item, f"{where}.{key}")
        return result
    raise ValueError(f"{where} must be JSON-compatible")


def _norm(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        value = json.dumps(value, sort_keys=True, separators=(",", ":"))
    value = str(value).casefold()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", value)).strip()


def _tokens(value: Any) -> set[str]:
    return {token for token in _norm(value).split() if token and token not in _STOPWORDS}


def _similarity(left: Any, right: Any) -> float:
    a, b = _tokens(left), _tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _deep_equal(left: Any, right: Any) -> bool:
    return _jsonable(left) == _jsonable(right)


def _bad_secret_ref(path: str) -> bool:
    pieces = Path(path).parts
    for piece in pieces:
        low = piece.casefold()
        if piece in (".", "..") or piece.startswith("."):
            return True
        if any(word in low for word in ("secret", "credential", "token")):
            return True
        if low in {".env", ".env.local", ".env.production", "auth.json"}:
            return True
        if low.endswith((".pem", ".p8", ".key")) or low.startswith("id_"):
            return True
    return False


def _artifact_path(course_root: Path, workspace: Path, value: Any) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("artifact paths must be non-empty strings")
    raw = Path(value)
    if raw.is_absolute() or _bad_secret_ref(value) or ".." in raw.parts:
        raise ValueError(f"unsafe artifact path: {value!r}")
    # Artifacts are recorded relative to the course root.  A path explicitly
    # prefixed with courses/<course> is accepted for CLI callers that already
    # work relative to workspace.
    if raw.parts[:2] == ("courses", course_root.name):
        candidate = workspace.joinpath(*raw.parts)
    else:
        candidate = course_root.joinpath(raw)
    root = workspace.resolve()
    course = course_root.resolve()
    try:
        candidate.resolve().relative_to(course)
    except ValueError:
        try:
            candidate.resolve().relative_to(root)
        except ValueError as exc:
            raise ValueError(f"artifact must remain inside workspace/course: {value!r}") from exc
    # A symlink anywhere in an artifact reference is rejected, even when its
    # final resolution happens to remain in the allowed root.
    check_from = workspace if candidate.parts[: len(workspace.parts)] == workspace.parts else course_root
    try:
        relative = candidate.relative_to(check_from)
    except ValueError:
        relative = candidate.relative_to(course_root)
    current = check_from
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"artifact may not traverse symlinks: {value!r}")
    return candidate


def _course_root(workspace: Path, course: str) -> Path:
    course_id = _slug(course)
    workspace = Path(workspace)
    if workspace.exists() and workspace.is_symlink():
        raise ValueError("workspace may not be a symlink")
    courses = workspace / "courses"
    if courses.exists() and courses.is_symlink():
        raise ValueError("courses directory may not be a symlink")
    root = courses / course_id
    if root.exists() and root.is_symlink():
        raise ValueError("course directory may not be a symlink")
    return root


def _read_examples(root: Path, course: str) -> dict[str, Any]:
    path = root / "examples.json"
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "course": course, "examples": []}
    if path.is_symlink():
        raise ValueError("examples.json may not be a symlink")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read examples.json: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("examples.json has unsupported schema_version")
    if value.get("course") != course or not isinstance(value.get("examples"), list):
        raise ValueError("examples.json course or examples is invalid")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Prefer the shared atomic helper when root has supplied it.
    try:
        from .common import atomic_json
    except ImportError:
        atomic_json = None
    if atomic_json is not None:
        atomic_json(path, value)
        return
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _validate_assignment(assignment: Any, *, where: str = "assignment") -> dict[str, Any]:
    if not isinstance(assignment, dict):
        raise ValueError(f"{where} must be an object")
    assignment = _jsonable(assignment, where)
    for field in ("title", "family", "method", "text"):
        if field in assignment and assignment[field] is not None and not isinstance(assignment[field], str):
            raise ValueError(f"{where}.{field} must be a string")
    if "assumptions" in assignment and not isinstance(assignment["assumptions"], dict):
        raise ValueError(f"{where}.assumptions must be an object")
    inputs = assignment.get("inputs", {})
    if inputs is None:
        inputs = {}
    if not isinstance(inputs, dict):
        raise ValueError(f"{where}.inputs must be an object")
    clean_inputs: dict[str, dict[str, Any]] = {}
    for name, spec in inputs.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{where}.inputs names must be non-empty strings")
        if not isinstance(spec, dict):
            raise ValueError(f"{where}.inputs.{name} must be an object")
        if "value" not in spec:
            raise ValueError(f"{where}.inputs.{name} requires value")
        if "unit" in spec and spec["unit"] is not None and not isinstance(spec["unit"], str):
            raise ValueError(f"{where}.inputs.{name}.unit must be a string")
        clean_inputs[name] = dict(spec)
    assignment["inputs"] = clean_inputs
    requirements = assignment.get("requirements", [])
    if requirements is None:
        requirements = []
    if not isinstance(requirements, list):
        raise ValueError(f"{where}.requirements must be a list")
    clean_requirements = []
    seen_requirement_ids: set[str] = set()
    for index, requirement in enumerate(requirements):
        if not isinstance(requirement, dict) or not isinstance(requirement.get("text"), str):
            raise ValueError(f"{where}.requirements[{index}] requires text")
        item = dict(requirement)
        if "id" in item and item["id"] is not None and not isinstance(item["id"], str):
            raise ValueError(f"{where}.requirements[{index}].id must be a string")
        requirement_id = item.get("id")
        if requirement_id is not None:
            if requirement_id in seen_requirement_ids:
                raise ValueError(f"{where}.requirements contains duplicate id {requirement_id!r}")
            seen_requirement_ids.add(requirement_id)
        clean_requirements.append(item)
    assignment["requirements"] = clean_requirements
    deliverables = assignment.get("deliverables", [])
    if deliverables is None:
        deliverables = []
    if not isinstance(deliverables, list) or not all(isinstance(item, str) for item in deliverables):
        raise ValueError(f"{where}.deliverables must be a list of strings")
    assignment["deliverables"] = deliverables
    return assignment


def _validate_example(workspace: Path, course: str, example: Any) -> dict[str, Any]:
    if not isinstance(example, dict):
        raise ValueError("example must be an object")
    # Examples become reusable course evidence.  Strip any identity metadata
    # before validation and persistence, including legacy input fields.
    example = _jsonable(sanitize_reusable_example(example), "example")
    if not isinstance(example.get("id"), str) or not example["id"]:
        raise ValueError("example.id is required")
    _slug(example["id"])
    if "assignment" not in example:
        raise ValueError("example.assignment is required")
    example["assignment"] = _validate_assignment(example["assignment"], where="example.assignment")
    status = example.get("review_status", "provisional")
    if status not in _VALID_REVIEW_STATUS:
        raise ValueError("example.review_status must be 'provisional' or 'reviewed'")
    artifacts = example.get("artifacts", [])
    if not isinstance(artifacts, list):
        raise ValueError("example.artifacts must be a list")
    root = _course_root(workspace, course)
    for artifact in artifacts:
        _artifact_path(root, Path(workspace), artifact)
    example["artifacts"] = list(artifacts)
    example["review_status"] = status
    return example


def register_example(workspace: Path, course: str, example: dict) -> dict:
    """Validate and durably register one example, idempotently by example ID."""
    course_id = _slug(course)
    root = _course_root(Path(workspace), course_id)
    clean = _validate_example(Path(workspace), course_id, copy.deepcopy(example))
    records = _read_examples(root, course_id)
    for existing in records["examples"]:
        if existing.get("id") == clean["id"]:
            _validate_example(Path(workspace), course_id, existing)
            if _canonical(existing) != _canonical(clean):
                raise ValueError(f"example ID already exists with different content: {clean['id']}")
            return copy.deepcopy(existing)
    records["examples"].append(clean)
    records["examples"].sort(key=lambda item: item["id"])
    _write_json(root / "examples.json", records)
    return copy.deepcopy(clean)


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _structure_present(assignment: dict[str, Any]) -> tuple[bool, list[str]]:
    missing = []
    # Family and method are the reliable assignment identity gates.  A title or
    # body/requirements is required to make the identity meaningful.
    for key in ("family", "method"):
        if not isinstance(assignment.get(key), str) or not assignment.get(key).strip():
            missing.append(key)
    if not (assignment.get("title") or assignment.get("text") or assignment.get("requirements")):
        missing.append("title/text/requirements")
    return not missing, missing


def _req_differences(previous: list[dict[str, Any]], current: list[dict[str, Any]]) -> list[dict[str, Any]]:
    diffs: list[dict[str, Any]] = []
    old_by_id = {r.get("id"): r for r in previous if r.get("id") is not None}
    new_by_id = {r.get("id"): r for r in current if r.get("id") is not None}
    old_unmatched = [r for r in previous if r.get("id") is None or r.get("id") not in new_by_id]
    new_unmatched = [r for r in current if r.get("id") is None or r.get("id") not in old_by_id]
    for rid in sorted(set(old_by_id) & set(new_by_id), key=str):
        if not _deep_equal(old_by_id[rid], new_by_id[rid]):
            diffs.append({"field": f"requirements[{rid}]", "kind": "changed", "before": old_by_id[rid], "after": new_by_id[rid]})
    # IDs are retained unless text provides strong evidence that a requirement
    # was renamed/re-keyed.  This avoids turning ordinary ID revisions into a
    # misleading remove/add pair.
    used_new: set[int] = set()
    for old in old_unmatched:
        best_index, best_score = None, 0.0
        for index, new in enumerate(new_unmatched):
            if index in used_new:
                continue
            score = _similarity(old.get("text", ""), new.get("text", ""))
            if score > best_score:
                best_index, best_score = index, score
        if best_index is not None and best_score >= 0.78:
            new = new_unmatched[best_index]
            used_new.add(best_index)
            diffs.append({"field": "requirements", "kind": "changed", "before": old, "after": new, "reason": "strong textual alignment despite requirement ID change"})
        else:
            diffs.append({"field": "requirements", "kind": "removed", "before": old})
    for index, new in enumerate(new_unmatched):
        if index not in used_new:
            diffs.append({"field": "requirements", "kind": "added", "after": new})
    return diffs


def _input_differences(previous: dict[str, Any], current: dict[str, Any]) -> list[dict[str, Any]]:
    diffs: list[dict[str, Any]] = []
    old_names, new_names = set(previous), set(current)
    removed, added = set(old_names - new_names), set(new_names - old_names)
    # A unique equal value/unit descriptor is useful evidence of a stale name.
    # It does not silently make two otherwise unrelated assignments match.
    used_added: set[str] = set()
    for old_name in sorted(removed):
        old_spec = previous[old_name]
        match = None
        for new_name in sorted(added):
            if new_name in used_added:
                continue
            new_spec = current[new_name]
            if _deep_equal(old_spec, new_spec):
                match = new_name
                break
        if match:
            used_added.add(match)
            diffs.append({"field": f"inputs.{old_name}", "kind": "renamed", "before_name": old_name, "after_name": match, "before": old_spec, "after": current[match], "reason": "same input descriptor under a changed name"})
        else:
            diffs.append({"field": f"inputs.{old_name}", "kind": "removed", "before": old_spec})
    for name in sorted(added - used_added):
        diffs.append({"field": f"inputs.{name}", "kind": "added", "after": current[name]})
    for name in sorted(old_names & new_names):
        if not _deep_equal(previous[name], current[name]):
            old, new = previous[name], current[name]
            reason = "input value changed"
            if old.get("unit") != new.get("unit"):
                reason = "input unit changed"
            elif old.get("value") != new.get("value"):
                reason = "input value changed"
            diff = {"field": f"inputs.{name}", "kind": "changed", "before": old, "after": new, "reason": reason}
            basis_conflicts = _basis_conflicts(old, new)
            if basis_conflicts:
                # A basis change redefines the quantity rather than rescaling
                # it, so the prior method cannot be carried over unchanged.
                diff["basis_change"] = True
                diff["reason"] = "input basis changed: " + "; ".join(basis_conflicts)
            diffs.append(diff)
    return diffs


def _basis_segments(spec: Any) -> list[str]:
    """Split a unit into its compound parts, numerator first.

    A basis marker only means something in the position it occupies: in
    ``kJ/kg`` the mass marker is the denominator (the quantity is *per* unit
    mass), while in ``kg/s`` it is the numerator (the quantity *is* a mass).
    Comparing markers position by position is what distinguishes a real basis
    change from an equivalent compound unit written differently.
    """
    if not isinstance(spec, dict):
        return [""]
    unit = str(spec.get("unit", "") or "")
    segments = [_norm(part) for part in unit.split("/")] or [""]
    # A qualifier such as "gauge" or "dry basis" describes the whole quantity,
    # so it belongs with the leading segment.
    qualifier = _norm(spec.get("basis", "") or "")
    if qualifier:
        segments[0] = f"{segments[0]} {qualifier}".strip()
    return segments


def _basis_conflicts(previous: Any, current: Any) -> list[str]:
    """Report basis disagreements, ignoring equivalent compound units.

    ``kg/kmol`` and ``g/mol`` are the same quantity written at different scales:
    both are a mass per mole.  Comparing the markers as one unordered set made
    them look like a mass-to-mole basis change, which wrongly forced a
    method-changing classification onto a pure unit rescale.  Comparing
    position by position keeps ``kJ/kg`` -> ``kJ/kmol`` a real basis change
    while leaving an equivalent rescale an ordinary input variant.
    """
    old_segments = _basis_segments(previous)
    new_segments = _basis_segments(current)
    conflicts: list[str] = []
    for position in range(min(len(old_segments), len(new_segments))):
        conflicts.extend(_group_conflicts(old_segments[position], new_segments[position], _BASIS_GROUPS))
    return conflicts


def compare_assignments(previous: dict, current: dict) -> dict:
    """Compare two structured assignments and explain every material delta."""
    old = _validate_assignment(previous, where="previous")
    new = _validate_assignment(current, where="current")
    old_ok, old_missing = _structure_present(old)
    new_ok, new_missing = _structure_present(new)
    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "classification": "no_useful_match",
        "match": False,
        "differences": [],
        "reasons": [],
        "evidence": [],
    }
    if not old_ok or not new_ok:
        result["reasons"].append("missing structural fields: " + ", ".join(sorted(set(old_missing + new_missing))))
        return result

    if _norm(old.get("family")) != _norm(new.get("family")):
        result["reasons"].append("assignment families differ")
        return result
    result["evidence"].append("same assignment family")
    if _norm(old.get("method")) != _norm(new.get("method")):
        result["classification"] = "method_changing_variant"
        result["match"] = True
        result["reasons"].append("method changed")
        result["differences"].append({"field": "method", "kind": "changed", "before": old.get("method"), "after": new.get("method")})
    else:
        result["evidence"].append("same method")

    # Include all field-level changes regardless of classification so a host can
    # adapt the prior method without accidentally carrying stale values.
    result["differences"].extend(_input_differences(old.get("inputs", {}), new.get("inputs", {})))
    if not _deep_equal(old.get("assumptions", {}), new.get("assumptions", {})):
        result["differences"].append({"field": "assumptions", "kind": "changed", "before": old.get("assumptions", {}), "after": new.get("assumptions", {}), "reason": "boundary conditions or assumptions changed"})
    result["differences"].extend(_req_differences(old.get("requirements", []), new.get("requirements", [])))
    if _norm(old.get("title")) != _norm(new.get("title")) and old.get("title") and new.get("title"):
        result["differences"].append({"field": "title", "kind": "changed", "before": old.get("title"), "after": new.get("title")})
    if _norm(old.get("text")) != _norm(new.get("text")) and old.get("text") and new.get("text"):
        result["differences"].append({"field": "text", "kind": "changed", "before": old.get("text"), "after": new.get("text")})
    if not _deep_equal(old.get("deliverables", []), new.get("deliverables", [])):
        result["differences"].append({"field": "deliverables", "kind": "changed", "before": old.get("deliverables", []), "after": new.get("deliverables", []), "reason": "required presentation or output changed"})

    # Name any mutually exclusive regime disagreement before classifying, so the
    # explanation points at the physics rather than at "the text changed".
    conflicts = _group_conflicts(_regime_text(old), _regime_text(new), _REGIME_GROUPS)

    if result["classification"] == "method_changing_variant":
        result["reasons"].extend(conflicts)
        result["reasons"].append("reuse requires re-deriving the method and checking all changed inputs and requirements")
    elif not result["differences"]:
        result["classification"] = "exact_repeat"
        result["match"] = True
        result["reasons"].append("normalized assignment structure and content are unchanged")
    else:
        # ``text`` is the problem statement: it is where the physics that
        # selects a method actually lives (steady vs transient, parallel-flow vs
        # counterflow, an added constraint, a different requested quantity).
        # Only ``title`` (a label) and ``deliverables`` (an output format) are
        # genuinely non-substantive.
        substantive = [d for d in result["differences"] if d["field"] not in {"title", "deliverables"}]
        forcing = [d for d in substantive if _forces_fresh_method(d)]
        if not substantive:
            result["classification"] = "presentation_only"
            result["match"] = True
            result["reasons"].append("only title, wording, or deliverables changed")
        elif forcing:
            result["classification"] = "method_changing_variant"
            result["match"] = True
            result["reasons"].extend(conflicts)
            result["reasons"].extend(sorted({_forcing_reason(d) for d in forcing}))
            result["reasons"].append("reuse requires re-deriving the method and checking all changed inputs and requirements")
        elif all(d["field"].startswith("inputs.") for d in substantive):
            result["classification"] = "input_variant"
            result["match"] = True
            result["reasons"].append("assignment method is retained while input data changed")
        else:
            result["classification"] = "method_changing_variant"
            result["match"] = True
            result["reasons"].extend(conflicts)
            result["reasons"].append("requirements or assumptions changed and require fresh reasoning")
    return result


def _regime_text(assignment: dict[str, Any]) -> str:
    """Every surface where a problem states the regime it is posed in."""
    parts = [
        str(assignment.get("title") or ""),
        str(assignment.get("text") or ""),
        _norm(assignment.get("assumptions") or {}),
    ]
    parts.extend(str(r.get("text", "")) for r in assignment.get("requirements", []))
    return _norm(" ".join(parts))


def _forces_fresh_method(difference: dict[str, Any]) -> bool:
    """Whether one difference on its own invalidates reuse of the prior method."""
    field = str(difference.get("field", ""))
    if difference.get("basis_change"):
        return True
    if field == "text" or field == "assumptions" or field.startswith("requirements"):
        return True
    # A datum the prior method consumed is gone, so that method cannot be run as
    # written.  An *added* input is ambiguous and stays an input variant.
    return field.startswith("inputs.") and difference.get("kind") == "removed"


def _forcing_reason(difference: dict[str, Any]) -> str:
    field = str(difference.get("field", ""))
    if difference.get("basis_change"):
        return "an input basis changed, which redefines the quantity rather than rescaling it"
    if field == "text":
        return "the problem statement changed; re-derive the method from the current statement"
    if field == "assumptions":
        return "assumptions or boundary conditions changed"
    if field.startswith("requirements"):
        return "requirements changed and require fresh reasoning"
    return "an input the prior method required was removed"


def _candidate_relevance(assignment: dict[str, Any], prior: dict[str, Any]) -> tuple[float, list[str]]:
    old = prior.get("assignment", {})
    if not isinstance(old, dict):
        return 0.0, []
    if not _structure_present(assignment)[0] or not _structure_present(old)[0]:
        return 0.0, []
    if _norm(assignment.get("family")) != _norm(old.get("family")):
        return 0.0, []
    evidence = ["same assignment family"]
    score = 0.4
    if _norm(assignment.get("method")) == _norm(old.get("method")):
        score += 0.25
        evidence.append("same method")
    else:
        score += 0.08
        evidence.append("family matches but method differs")
    current_text = " ".join([assignment.get("title", ""), assignment.get("text", "")] + [r.get("text", "") for r in assignment.get("requirements", [])])
    prior_text = " ".join([old.get("title", ""), old.get("text", "")] + [r.get("text", "") for r in old.get("requirements", [])])
    overlap = _similarity(current_text, prior_text)
    title_overlap = _similarity(assignment.get("title", ""), old.get("title", ""))
    requirement_overlap = _similarity(
        " ".join(r.get("text", "") for r in assignment.get("requirements", [])),
        " ".join(r.get("text", "") for r in old.get("requirements", [])),
    )
    input_name_overlap = len(set(assignment.get("inputs", {})) & set(old.get("inputs", {}))) / max(
        1, len(set(assignment.get("inputs", {})) | set(old.get("inputs", {})))
    )
    # Family/method labels alone are too broad to establish a useful match.
    # Require some textual or input identity evidence before ranking a record.
    if max(overlap, title_overlap, requirement_overlap, input_name_overlap) < 0.25:
        return 0.0, []
    score += min(0.3, overlap * 0.3)
    if overlap >= 0.45:
        evidence.append(f"normalized text overlap {overlap:.2f}")
    if assignment.get("inputs") and old.get("inputs"):
        common = set(assignment["inputs"]) & set(old["inputs"])
        if common:
            score += min(0.05, 0.05 * len(common) / max(len(assignment["inputs"]), len(old["inputs"])))
            evidence.append(f"shared input names: {', '.join(sorted(common))}")
    return score, evidence


def match_examples(workspace: Path, course: str, assignment: dict, limit: int = 3) -> list[dict]:
    """Return ranked, same-course prior examples with comparison evidence."""
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
        raise ValueError("limit must be a non-negative integer")
    course_id = _slug(course)
    current = _validate_assignment(assignment, where="assignment")
    root = _course_root(Path(workspace), course_id)
    records = _read_examples(root, course_id)
    if not _structure_present(current)[0]:
        return []
    ranked = []
    for example in records["examples"]:
        status = str(example.get("status", "")).casefold()
        if status in _BAD_STATUS_WORDS or any(word in status for word in _BAD_STATUS_WORDS):
            continue
        # Provisional records stay cataloged for review, but they cannot drive
        # assignment adaptation or professor-style decisions.
        if example.get("review_status") != "reviewed":
            continue
        try:
            prior = _validate_example(Path(workspace), course_id, example)
        except ValueError:
            continue
        score, retrieval_evidence = _candidate_relevance(current, prior)
        if score <= 0:
            continue
        comparison = compare_assignments(prior["assignment"], current)
        if comparison["classification"] == "no_useful_match":
            continue
        # The numeric value is private ranking machinery and is intentionally
        # omitted from the public result; callers receive evidence, not a
        # misleading confidence percentage.
        ranked.append((score, prior["id"], {
            "schema_version": SCHEMA_VERSION,
            "id": prior["id"],
            "example_id": prior["id"],
            "course": course_id,
            "classification": comparison["classification"],
            "review_status": prior["review_status"],
            "artifacts": list(prior.get("artifacts", [])),
            "evidence": retrieval_evidence + comparison["evidence"],
            "reasons": comparison["reasons"],
            "differences": comparison["differences"],
            "assignment": copy.deepcopy(prior["assignment"]),
            "example": copy.deepcopy(prior),
            "comparison": comparison,
        }))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [item[2] for item in ranked[:limit]]
