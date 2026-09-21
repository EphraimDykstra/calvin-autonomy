"""Calculation checks and immutable, structured verification reports."""

from __future__ import annotations

import copy
import re
from collections.abc import Iterable, Mapping
from pathlib import PurePosixPath
from typing import Any

from .calculations import check_calculation
from .common import digest


REPORT_SCHEMA_VERSION = "verification-report-2"
_SHA256 = re.compile(r"[0-9a-f]{64}")
_CHECK_CATEGORIES = ("method", "numerical", "format", "identity")


def verify_solution(solution: dict) -> list[dict]:
    """Preserve the original arithmetic-check interface used by the CLI."""
    return [check_calculation(c) for c in solution.get("calculations", [])]


def _sha256(value: Any, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _artifact_path(value: Any) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("artifact path must be a contained relative POSIX path")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or not path.parts
        or path.as_posix() != value
        or any(part in ("", ".", "..") for part in path.parts)
    ):
        raise ValueError("artifact path must be a contained relative POSIX path")
    return value


def _expected_bindings(state: Mapping[str, Any]) -> dict[str, Any]:
    """Derive bindings and reject a state that is already incomplete or stale."""
    if not isinstance(state, Mapping):
        raise ValueError("state must be an object")

    input_record = state.get("input")
    if not isinstance(input_record, Mapping):
        raise ValueError("state input record is missing")
    input_hash = _sha256(input_record.get("sha256"), "input hash")

    plan = state.get("plan")
    if not isinstance(plan, Mapping):
        raise ValueError("state plan is missing")
    plan_hash = digest(dict(plan))
    if state.get("plan_sha256") != plan_hash:
        raise ValueError("state plan hash is missing or stale")

    requirements = plan.get("requirements")
    if not isinstance(requirements, list) or not requirements:
        raise ValueError("state plan requires a non-empty requirements list")
    requirement_ids = [
        item.get("id") if isinstance(item, Mapping) else None for item in requirements
    ]
    if any(not isinstance(value, str) or not value.strip() for value in requirement_ids):
        raise ValueError("every plan requirement needs a non-empty id")
    if len(set(requirement_ids)) != len(requirement_ids):
        raise ValueError("plan requirement ids must be unique")

    solution = state.get("solution")
    if not isinstance(solution, Mapping):
        raise ValueError("state solution is missing")
    solution_hash = digest(dict(solution))
    if state.get("solution_sha256") != solution_hash:
        raise ValueError("state solution hash is missing or stale")

    if state.get("unresolved") not in (None, []):
        raise ValueError("state contains unresolved findings")
    if solution.get("unresolved") not in (None, []):
        raise ValueError("solution contains unresolved findings")

    calculations = solution.get("calculations", [])
    checks = state.get("checks")
    if not isinstance(calculations, list):
        raise ValueError("solution calculations must be a list")
    if not isinstance(checks, list) or any(not isinstance(item, Mapping) for item in checks):
        raise ValueError("state calculation checks must be a list of objects")
    if state.get("checks_for_solution_sha256") != solution_hash:
        raise ValueError("calculation checks are missing or stale")
    calculation_ids = [
        item.get("id") if isinstance(item, Mapping) else None for item in calculations
    ]
    check_ids = [item.get("id") for item in checks]
    if any(not isinstance(value, str) or not value.strip() for value in calculation_ids):
        raise ValueError("calculation ids must be present")
    if len(set(calculation_ids)) != len(calculation_ids):
        raise ValueError("calculation ids must be unique")
    if any(not isinstance(value, str) or not value.strip() for value in check_ids):
        raise ValueError("calculation check ids must be present")
    if len(set(check_ids)) != len(check_ids):
        raise ValueError("calculation check ids must be unique")
    if sorted(calculation_ids) != sorted(check_ids):
        raise ValueError("calculation checks do not cover every calculation")
    if any(item.get("passed") is not True for item in checks):
        raise ValueError("one or more calculation checks failed")

    artifacts = state.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        raise ValueError("state requires at least one artifact")
    artifact_bindings: list[dict[str, str]] = []
    seen_paths: set[str] = set()
    for item in artifacts:
        if not isinstance(item, Mapping):
            raise ValueError("artifact records must be objects")
        path = _artifact_path(item.get("path"))
        if path in seen_paths:
            raise ValueError("artifact paths must be unique")
        seen_paths.add(path)
        artifact_hash = _sha256(item.get("sha256"), "artifact hash")
        if item.get("source_solution_sha256") != solution_hash:
            raise ValueError("one or more artifacts were rendered from a stale solution")
        artifact_bindings.append(
            {
                "path": path,
                "sha256": artifact_hash,
                "source_solution_sha256": solution_hash,
            }
        )
    artifact_bindings.sort(key=lambda item: item["path"])

    # A declared outstanding input is part of what a report is a report *about*:
    # it says which requirement is waiting on the student.  Binding its digest is
    # what makes withdrawing the declaration invalidate the report, so a run
    # cannot reach ready by deleting the declaration while the work is still
    # undone.  The digest of an empty list is the binding for a run with none.
    outstanding = state.get("outstanding_inputs", [])
    if not isinstance(outstanding, list) or any(not isinstance(item, Mapping) for item in outstanding):
        raise ValueError("state outstanding inputs must be a list of objects")
    outstanding_hash = digest({"outstanding_inputs": [dict(item) for item in outstanding]})
    if state.get("outstanding_inputs_sha256", outstanding_hash) != outstanding_hash:
        raise ValueError("state outstanding inputs hash is missing or stale")

    checks_value = [copy.deepcopy(dict(item)) for item in checks]
    bindings = {
        "input_sha256": input_hash,
        "plan_sha256": plan_hash,
        "solution_sha256": solution_hash,
        "calculation_checks_sha256": digest({"checks": checks_value}),
        "calculation_checks_for_solution_sha256": solution_hash,
        "outstanding_inputs_sha256": outstanding_hash,
        "artifacts": artifact_bindings,
    }
    bindings["artifact_manifest_sha256"] = digest(
        {"artifacts": artifact_bindings}
    )
    return bindings


def _finding_list(value: Any, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} findings must be a non-empty list")
    findings: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise ValueError(f"{label} findings must contain objects")
        findings.append(copy.deepcopy(dict(item)))
    return findings


def _check_requirement_quality(item: Mapping[str, Any], requirement_id: str) -> None:
    """Refuse a requirement finding nobody could act on, passing or not.

    These rules are about the finding rather than about the verdict, so they
    hold for a finding that awaits a student input exactly as they hold for one
    that passes: a verdict with no evidence, with its own unresolved list, or
    with no notes says nothing either way.
    """
    if item.get("unresolved") not in (None, []):
        raise ValueError(f"requirement coverage is unresolved: {requirement_id}")
    if item.get("status") in ("failed", "unresolved"):
        raise ValueError(f"requirement coverage is not passing: {requirement_id}")
    evidence = item.get("evidence")
    if (
        not isinstance(evidence, list)
        or not evidence
        or any(not isinstance(value, str) or not value.strip() for value in evidence)
    ):
        raise ValueError(f"requirement coverage needs evidence: {requirement_id}")
    if not isinstance(item.get("notes"), str) or not item["notes"].strip():
        raise ValueError(f"requirement coverage needs notes: {requirement_id}")


def _awaiting_ids(report: Mapping[str, Any], declared: set[str]) -> list[str]:
    """Return the outstanding-input ids this report records, refusing misuse.

    ``awaiting`` is the one way a report may decline to pass something, and it
    is deliberately narrow.  It belongs only on a requirement finding, because
    only a requirement can be waiting on material the student has not sent; a
    method, numerical, format or identity check is about work already done here
    and must still pass outright.  The id must name an input the run has
    declared, so a verifier cannot invent a reason to be excused, and the
    finding may not also claim to have passed, which would be a contradiction
    rather than a verdict.  It excuses nothing else: the finding still faces
    ``_check_requirement_quality`` like any other.
    """
    findings = report.get("findings")
    if not isinstance(findings, Mapping):
        return []
    for category in _CHECK_CATEGORIES:
        for item in findings.get(category) or []:
            if isinstance(item, Mapping) and item.get("awaiting") is not None:
                raise ValueError(
                    f"{category} checks cannot await a student input; only a requirement can"
                )
    awaiting: list[str] = []
    for item in findings.get("requirements") or []:
        if not isinstance(item, Mapping):
            continue
        value = item.get("awaiting")
        if value is None:
            continue
        requirement_id = item.get("requirement_id")
        if not isinstance(value, str) or value not in declared:
            raise ValueError(
                f"requirement coverage awaits an undeclared input: {requirement_id}"
            )
        if item.get("passed") is True:
            raise ValueError(
                f"requirement coverage cannot both pass and await an input: {requirement_id}"
            )
        awaiting.append(value)
    return awaiting


def validate_verification_report(
    state: Mapping[str, Any], report: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate a report against the current run state and return a safe copy.

    Validation is fail-closed: stale bindings, incomplete requirement coverage,
    failed checks, or unresolved findings raise ``ValueError``.
    """
    expected = _expected_bindings(state)
    if not isinstance(report, Mapping):
        raise ValueError("verification report must be an object")
    if report.get("schema_version") != REPORT_SCHEMA_VERSION:
        raise ValueError("unsupported verification report schema")

    bindings = report.get("bindings")
    if not isinstance(bindings, Mapping):
        raise ValueError("verification report bindings are missing")
    for key in (
        "input_sha256",
        "plan_sha256",
        "solution_sha256",
        "calculation_checks_sha256",
        "calculation_checks_for_solution_sha256",
        "outstanding_inputs_sha256",
        "artifacts",
        "artifact_manifest_sha256",
    ):
        if bindings.get(key) != expected[key]:
            raise ValueError(f"verification report {key} binding is stale")

    declared_inputs = {
        str(item.get("id"))
        for item in state.get("outstanding_inputs", [])
        if isinstance(item, Mapping)
    }
    awaiting = _awaiting_ids(report, declared_inputs)

    unresolved = report.get("unresolved")
    if unresolved != []:
        raise ValueError("verification report has unresolved findings")
    # ``passed`` stays a statement about the findings and is checked in both
    # directions: a report with nothing awaiting must claim True, and one that
    # records a requirement waiting on the student must claim False.  A report
    # cannot call itself passing while something is outstanding, and cannot
    # call itself unpassing to slip past the rule above.
    if report.get("passed") is not (not awaiting):
        raise ValueError(
            "verification report is not passing"
            if not awaiting
            else "a report with an awaiting requirement must record passed as false"
        )

    findings = report.get("findings")
    if not isinstance(findings, Mapping):
        raise ValueError("verification report findings are missing")
    expected_categories = {"requirements", *_CHECK_CATEGORIES}
    if set(findings) != expected_categories:
        raise ValueError("verification report finding categories are incomplete or unexpected")

    requirement_findings = _finding_list(
        findings.get("requirements"), "requirement coverage"
    )
    expected_requirement_ids = {
        item["id"] for item in state["plan"]["requirements"]
    }
    found_requirement_ids: list[str] = []
    for item in requirement_findings:
        requirement_id = item.get("requirement_id")
        if not isinstance(requirement_id, str) or not requirement_id.strip():
            raise ValueError("requirement coverage finding needs a requirement_id")
        found_requirement_ids.append(requirement_id)
        if item.get("awaiting") is not None:
            # Whether the requirement is met and whether the finding is worth
            # reading are separate questions.  An awaiting finding is excused
            # only the first: ``_awaiting_ids`` has already checked that the id
            # is declared and that the finding does not also claim to pass, and
            # everything below still applies to it.
            _check_requirement_quality(item, requirement_id)
            continue
        if item.get("passed") is not True:
            raise ValueError(f"requirement coverage failed: {requirement_id}")
        _check_requirement_quality(item, requirement_id)
    if len(set(found_requirement_ids)) != len(found_requirement_ids):
        raise ValueError("requirement coverage findings must be unique")
    if set(found_requirement_ids) != expected_requirement_ids:
        raise ValueError("requirement coverage findings are incomplete or unexpected")

    for category in _CHECK_CATEGORIES:
        category_findings = _finding_list(findings.get(category), category)
        identifiers: list[str] = []
        for item in category_findings:
            identifier = item.get("id")
            if not isinstance(identifier, str) or not identifier.strip():
                raise ValueError(f"{category} finding needs an id")
            identifiers.append(identifier)
            if item.get("passed") is not True:
                raise ValueError(f"{category} check failed: {identifier}")
            if item.get("unresolved") not in (None, []):
                raise ValueError(f"{category} check is unresolved: {identifier}")
            if item.get("status") in ("failed", "unresolved"):
                raise ValueError(f"{category} check is not passing: {identifier}")
            if not isinstance(item.get("notes"), str) or not item["notes"].strip():
                raise ValueError(f"{category} finding needs notes: {identifier}")
        if len(set(identifiers)) != len(identifiers):
            raise ValueError(f"{category} finding ids must be unique")

    return copy.deepcopy(dict(report))


def build_verification_report(
    state: Mapping[str, Any],
    *,
    requirement_findings: Iterable[Mapping[str, Any]],
    method_checks: Iterable[Mapping[str, Any]],
    numerical_checks: Iterable[Mapping[str, Any]],
    format_checks: Iterable[Mapping[str, Any]],
    identity_checks: Iterable[Mapping[str, Any]],
    unresolved: Iterable[str] = (),
) -> dict[str, Any]:
    """Build and validate a report bound to the supplied run state."""
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "bindings": _expected_bindings(state),
        "findings": {
            "requirements": [copy.deepcopy(dict(item)) for item in requirement_findings],
            "method": [copy.deepcopy(dict(item)) for item in method_checks],
            "numerical": [copy.deepcopy(dict(item)) for item in numerical_checks],
            "format": [copy.deepcopy(dict(item)) for item in format_checks],
            "identity": [copy.deepcopy(dict(item)) for item in identity_checks],
        },
        "unresolved": list(unresolved),
    }
    declared = {
        str(item.get("id"))
        for item in state.get("outstanding_inputs", [])
        if isinstance(item, Mapping)
    }
    report["passed"] = not _awaiting_ids(report, declared)
    return validate_verification_report(state, report)
