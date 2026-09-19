"""Build a privacy-safe manifest for adapting a prior assignment example.

This module is intentionally a planning aid.  It carries forward evidence about
methods and presentation patterns while forcing current inputs and requirements
to be considered again.  It never copies a prior answer, calculation, or
student identity into the manifest.
"""

from __future__ import annotations

import copy
import math
import re
from typing import Any

from .matching import compare_assignments


SCHEMA_VERSION = 1
_IDENTITY_KEYS = {
    "name", "student", "student_name", "student_id", "studentid", "sid",
    "author", "owner", "email", "netid", "user", "user_id", "userid",
}
_RESULT_KEYS = {
    "answer", "answers", "calculation", "calculations", "result", "results",
    "solution", "output", "outputs", "final", "work", "derivation",
}
# Classifications under which nothing substantive moved, so a fresh derivation
# is not forced by the comparison itself.  Current inputs are still recomputed
# and prior results are still never reused.
_NO_FRESH_DERIVATION = {"presentation_only", "exact_repeat"}
_PRESENTATION_WORDS = {
    "artifact", "artifacts", "chart", "figure", "format", "graph", "image",
    "plot", "report", "slide", "table", "presentation", "deliverable",
}


def _norm(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(value).casefold())).strip()


def _tokens(value: Any) -> set[str]:
    return set(_norm(value).split())


def _similarity(left: Any, right: Any) -> float:
    a, b = _tokens(left), _tokens(right)
    return len(a & b) / len(a | b) if a and b else 0.0


def _safe_copy(value: Any, *, key: str = "") -> Any:
    """Copy metadata while dropping identity-bearing keys and non-finite values."""
    if key.casefold() in _IDENTITY_KEYS:
        return "<redacted>"
    if isinstance(value, dict):
        return {
            str(k): _safe_copy(v, key=str(k))
            for k, v in value.items()
            if str(k).casefold() not in _IDENTITY_KEYS
        }
    if isinstance(value, list):
        return [_safe_copy(v) for v in value]
    if isinstance(value, float) and not math.isfinite(value):
        return "<non-finite>"
    if isinstance(value, (str, int, float, bool)) or value is None:
        return copy.deepcopy(value)
    return str(value)


def _identity(identity: dict[str, Any] | None) -> dict[str, str]:
    """Return only explicit per-run identity, otherwise stable placeholders."""
    if identity is None:
        identity = {}
    if not isinstance(identity, dict):
        raise ValueError("identity must be an object when supplied")
    output: dict[str, str] = {}
    for field, placeholder in (("name", "<student-name>"), ("student_id", "<student-id>")):
        value = identity.get(field)
        if value is None or value == "":
            output[field] = placeholder
        elif not isinstance(value, str):
            raise ValueError(f"identity.{field} must be a string")
        else:
            output[field] = value
    return output


def _prior_assignment(prior_example: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(prior_example, dict):
        raise ValueError("prior example must be an object")
    prior = prior_example.get("assignment", prior_example)
    if not isinstance(prior, dict):
        raise ValueError("prior example assignment must be an object")
    return prior


def _difference_field(diff: dict[str, Any]) -> str:
    field = str(diff.get("field", "unknown"))
    if field.startswith("requirements["):
        return "requirements"
    if field.startswith("inputs."):
        return "inputs"
    return field


def _public_difference(difference: dict[str, Any]) -> dict[str, Any]:
    """Expose change metadata without copying prior-side values.

    Prior inputs and requirement text can contain arbitrary student-entered
    material.  The manifest only needs the field, change kind, current value,
    and an explanation; omitting ``before`` prevents accidental identity/result
    propagation even for unconventional field names.
    """
    output = {
        "field": _difference_field(difference),
        "kind": difference.get("kind", "changed"),
        "reason": difference.get("reason", "current assignment differs from prior example"),
    }
    if "after" in difference:
        output["current"] = _safe_copy(difference["after"])
    if "after_name" in difference:
        output["current_name"] = _safe_copy(difference["after_name"])
    return output


def _result_field_names(prior_example: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for key in prior_example:
        low = str(key).casefold()
        if low in _RESULT_KEYS or any(word in low for word in ("answer", "result", "solution", "calculation")):
            names.append(str(key))
    # An artifact is evidence of an old rendered result, but its path is never
    # copied into the output.
    if prior_example.get("artifacts"):
        names.append("artifacts")
    return sorted(set(names))


def _reuse_blockers(comparison: dict[str, Any], previous: dict[str, Any], current: dict[str, Any]) -> list[str]:
    """Reasons the prior approach cannot be carried into ANY current requirement.

    These are assignment-wide: a requirement whose wording never changed is
    still not reusable once the method, the stated regime, or the assumptions
    underneath it have moved.
    """
    blockers: list[str] = []
    if _norm(previous.get("method")) != _norm(current.get("method")):
        blockers.append("method")
    changed_fields = {_difference_field(item) for item in comparison.get("differences", [])}
    if "assumptions" in changed_fields:
        blockers.append("assumptions")
    if "text" in changed_fields:
        blockers.append("problem_statement")
    if "requirements" in changed_fields:
        blockers.append("requirements")
    if comparison.get("classification") in {"method_changing_variant", "no_useful_match"} and not blockers:
        # method_changing_variant reached via a removed input or a changed
        # quantity basis; no_useful_match established nothing at all, so it must
        # not read permissively just because the two method labels happen to
        # agree.
        blockers.append("method")
    return blockers


def _requirement_coverage(
    previous: dict[str, Any],
    current: dict[str, Any],
    blockers: list[str] | None = None,
) -> list[dict[str, Any]]:
    blockers = list(blockers or [])
    old_reqs = previous.get("requirements", []) or []
    current_reqs = current.get("requirements", []) or []
    old_by_id = {
        r.get("id"): (index, r)
        for index, r in enumerate(old_reqs)
        if isinstance(r, dict) and r.get("id") is not None
    }
    used_old: set[int] = set()
    prior_matches: dict[int, dict[str, Any]] = {}

    # Pass 1 reserves exact ID matches.  Resolving these first is what keeps the
    # result independent of the order requirements happen to appear in: a fuzzy
    # text match must never consume a prior requirement that an exact ID was
    # entitled to, which is possible whenever the ID-bearing requirement comes
    # later in the list than a similarly worded one.
    for index, req in enumerate(current_reqs):
        rid = req.get("id") if isinstance(req, dict) else None
        if rid is None or rid not in old_by_id:
            continue
        old_index, prior = old_by_id[rid]
        if old_index in used_old:
            continue
        used_old.add(old_index)
        prior_matches[index] = prior

    # Pass 2 aligns whatever is left on text similarity.
    for index, req in enumerate(current_reqs):
        if index in prior_matches:
            continue
        text = req.get("text", "") if isinstance(req, dict) else str(req)
        best_score, best_index, best_req = 0.0, None, None
        for old_index, old_req in enumerate(old_reqs):
            if old_index in used_old or not isinstance(old_req, dict):
                continue
            score = _similarity(old_req.get("text", ""), text)
            if score > best_score:
                best_score, best_index, best_req = score, old_index, old_req
        if best_index is not None and best_score >= 0.78:
            used_old.add(best_index)
            prior_matches[index] = best_req

    coverage: list[dict[str, Any]] = []
    for index, req in enumerate(current_reqs):
        rid = req.get("id") if isinstance(req, dict) else None
        text = req.get("text", "") if isinstance(req, dict) else str(req)
        prior_match = prior_matches.get(index)
        if prior_match is None:
            status = "new_requirement"
        elif _norm(prior_match.get("text")) == _norm(text):
            status = "unchanged_requirement"
        else:
            status = "changed_requirement"
        entry_blockers = list(blockers)
        if status != "unchanged_requirement" and "requirements" not in entry_blockers:
            entry_blockers.append("requirements")
        coverage.append({
            "index": index,
            "id": rid if rid is not None else f"requirement-{index + 1}",
            "text": str(text),
            "status": status,
            "prior_alignment": bool(prior_match),
            "current_work_required": True,
            # Empty means the prior approach may inform this requirement; it
            # never means the prior numbers may be reused.
            "reuse_blocked_by": entry_blockers,
        })
    return coverage


def _method_validity(comparison: dict[str, Any], previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    classification = comparison.get("classification")
    if classification == "no_useful_match":
        return {"status": "unknown", "direct_reuse": False, "reasons": ["prior assignment is not structurally comparable"]}
    if _norm(previous.get("method")) != _norm(current.get("method")):
        return {
            "status": "changed",
            "direct_reuse": False,
            "reasons": ["current method differs; prior method can provide context only"],
            "current_method": current.get("method", ""),
        }
    changed_fields = {_difference_field(item) for item in comparison.get("differences", [])}
    if "assumptions" in changed_fields or "requirements" in changed_fields:
        return {
            "status": "conditional",
            "direct_reuse": False,
            "reasons": ["method name is retained, but assumptions or requirements changed"],
            "method": current.get("method", ""),
        }
    if classification == "method_changing_variant":
        # The method *label* survived, but the comparison established that the
        # method itself must be re-derived: the problem statement, an input
        # basis, or a required input moved underneath it.  Never report this as
        # valid for adaptation.
        return {
            "status": "conditional",
            "direct_reuse": False,
            "reasons": [
                "method name is retained, but the current assignment requires re-deriving it",
                *[str(reason) for reason in comparison.get("reasons", [])],
            ],
            "method": current.get("method", ""),
        }
    return {
        "status": "valid_for_adaptation",
        "direct_reuse": False,
        "reasons": ["prior method may be reused as a starting structure after current checks"],
        "method": current.get("method", ""),
    }


def build_adaptation_manifest(
    current_assignment: dict[str, Any],
    prior_example: dict[str, Any],
    identity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a difference manifest for one current assignment and prior example.

    ``identity`` is deliberately a separate per-run argument.  Values found in
    either assignment or prior example are never used to populate it.
    """
    if not isinstance(current_assignment, dict):
        raise ValueError("current assignment must be an object")
    current = copy.deepcopy(current_assignment)
    previous = _prior_assignment(prior_example)
    comparison = compare_assignments(previous, current)
    differences = comparison.get("differences", [])
    result_fields = _result_field_names(prior_example)

    stale_fields: list[dict[str, Any]] = []
    for difference in differences:
        stale_fields.append(_public_difference(difference))
    for field in result_fields:
        stale_fields.append({
            "field": f"prior.{field}",
            "kind": "stale_prior_result",
            "reason": "prior result/artifact must not be copied; recompute from current inputs",
        })

    changed_fields = {_difference_field(item) for item in differences}
    classification = comparison.get("classification", "no_useful_match")
    # Key recalculation off the classification rather than off which field drove
    # it.  Keying it off a field set let a changed problem statement (the one
    # place the physics is usually stated) report that no recalculation was
    # needed while the classification already said the method had changed.
    # This answers "is there prior numeric work whose reuse must be blocked",
    # NOT "must the current run do its own work".  The second question is
    # answered per requirement by current_requirement_coverage, which is True
    # for every requirement regardless of what this flag says, and by
    # reusable_parts, where nothing is ever safe_to_reuse.  So a False here
    # cannot let a host skip work: it means there was no prior result to copy
    # in the first place.  Do not "fix" this to a constant True; that makes
    # the field carry no information and tempts a later reader to weaken the
    # per-requirement flags that are actually load-bearing.
    recalculation = bool(result_fields) or classification not in _NO_FRESH_DERIVATION

    blockers = _reuse_blockers(comparison, previous, current)

    reusable_parts: list[dict[str, Any]] = []
    if comparison.get("classification") != "no_useful_match":
        if _norm(previous.get("method")) == _norm(current.get("method")) and current.get("method"):
            reusable_parts.append({"part": "method_structure", "method": str(current.get("method")), "safe_to_reuse": False, "reason": "method structure is evidence only; validate it against current requirements"})
        if _norm(previous.get("family")) == _norm(current.get("family")) and current.get("family"):
            reusable_parts.append({"part": "assignment_family", "family": str(current.get("family")), "safe_to_reuse": False, "reason": "same family supports retrieval and review"})
        if "deliverables" not in changed_fields:
            reusable_parts.append({"part": "presentation_pattern", "safe_to_reuse": False, "reason": "deliverable shape is unchanged, but current content still requires review"})
    if not reusable_parts:
        reusable_parts.append({"part": "none", "safe_to_reuse": False, "reason": "no structurally useful prior part established"})

    deliverable_changes = [
        _public_difference(difference)
        for difference in differences
        if _difference_field(difference) == "deliverables"
    ]
    if result_fields:
        deliverable_changes.append({
            "field": "prior_results",
            "kind": "discarded",
            "reason": "prior rendered/solution result is stale for this run",
        })

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "identity": _identity(identity),
        "classification": comparison.get("classification", "no_useful_match"),
        "reusable_parts": reusable_parts,
        "stale_fields": stale_fields,
        "recalculation_required": recalculation,
        "method_validity": _method_validity(comparison, previous, current),
        "deliverable_changes": deliverable_changes,
        "current_requirement_coverage": _requirement_coverage(previous, current, blockers),
        "reuse_blocked_by": blockers,
        "reasons": [str(reason) for reason in comparison.get("reasons", [])],
    }
    # Defensive final scrub catches identity-bearing metadata nested in unusual
    # input fields while preserving the explicitly supplied per-run identity.
    supplied_identity = manifest["identity"]
    manifest = _safe_copy(manifest)
    manifest["identity"] = supplied_identity
    return manifest


def adapt_assignment(current_assignment: dict[str, Any], prior_example: dict[str, Any], identity: dict[str, Any] | None = None) -> dict[str, Any]:
    """Alias with a concise name for host/CLI integrations."""
    return build_adaptation_manifest(current_assignment, prior_example, identity)


def adapt_example(current_assignment: dict[str, Any], prior_example: dict[str, Any], identity: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compatibility alias for integrations that call the reference an example."""
    return build_adaptation_manifest(current_assignment, prior_example, identity)


def difference_manifest(current_assignment: dict[str, Any], prior_example: dict[str, Any], identity: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compatibility alias emphasizing the emitted manifest shape."""
    return build_adaptation_manifest(current_assignment, prior_example, identity)


__all__ = ["adapt_assignment", "adapt_example", "build_adaptation_manifest", "difference_manifest"]
