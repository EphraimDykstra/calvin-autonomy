"""Aggregate held-out assignment-run evaluations without course content."""

from __future__ import annotations

import copy
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from .common import digest, now
from .runtime import load_run, status_run, validate_run_id
from .verification import validate_verification_report


MANIFEST_SCHEMA_VERSION = "evaluation-manifest-1"
REPORT_SCHEMA_VERSION = "evaluation-report-1"
MIN_CASES = 10
MAX_CASES = 20


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def _boolean(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be true or false")
    return value


def _timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be an ISO-8601 timestamp")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must include a timezone")
    return parsed


def validate_evaluation_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the public test manifest and return a detached copy."""
    if not isinstance(manifest, Mapping):
        raise ValueError("evaluation manifest must be an object")
    if manifest.get("schema_version") != MANIFEST_SCHEMA_VERSION:
        raise ValueError("unsupported evaluation manifest schema")
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not MIN_CASES <= len(cases) <= MAX_CASES:
        raise ValueError(f"evaluation manifest must contain {MIN_CASES}-{MAX_CASES} cases")

    identifiers: list[str] = []
    run_refs: list[str] = []
    for index, case in enumerate(cases):
        label = f"case {index + 1}"
        if not isinstance(case, Mapping):
            raise ValueError(f"{label} must be an object")
        identifier = case.get("id")
        run_ref = case.get("run_ref")
        if not isinstance(identifier, str) or not identifier.strip():
            raise ValueError(f"{label} needs a non-empty id")
        if not isinstance(run_ref, str) or not run_ref.strip():
            raise ValueError(f"{label} needs a non-empty run_ref")
        # Validate run IDs through the same boundary used by the runtime.
        validate_run_id(run_ref)
        identifiers.append(identifier)
        run_refs.append(run_ref)

        expected = case.get("expected")
        if not isinstance(expected, Mapping):
            raise ValueError(f"{label} needs expected outcomes")
        ready = _boolean(expected.get("ready"), f"{label} expected.ready")
        _boolean(
            expected.get("verification_pass"),
            f"{label} expected.verification_pass",
        )
        _boolean(expected.get("stale"), f"{label} expected.stale")
        blockers = expected.get("blockers")
        if (
            not isinstance(blockers, list)
            or any(not isinstance(item, str) or not item.strip() for item in blockers)
        ):
            raise ValueError(f"{label} expected.blockers must be a list of text fragments")
        if not ready and not blockers:
            raise ValueError(f"{label} must name at least one expected blocker")
        minimum_coverage = expected.get("minimum_requirement_coverage")
        if minimum_coverage is not None and (
            isinstance(minimum_coverage, bool)
            or not isinstance(minimum_coverage, (int, float))
            or not 0 <= minimum_coverage <= 1
        ):
            raise ValueError(
                f"{label} expected.minimum_requirement_coverage must be between 0 and 1"
            )

        timestamps = case.get("timestamps")
        if timestamps is not None:
            if not isinstance(timestamps, Mapping):
                raise ValueError(f"{label} timestamps must be an object")
            if set(timestamps) != {"failure_detected_at", "corrected_at"}:
                raise ValueError(
                    f"{label} timestamps require failure_detected_at and corrected_at"
                )
            detected = _timestamp(
                timestamps["failure_detected_at"],
                f"{label} timestamps.failure_detected_at",
            )
            corrected = _timestamp(
                timestamps["corrected_at"], f"{label} timestamps.corrected_at"
            )
            if corrected < detected:
                raise ValueError(f"{label} corrected_at cannot precede failure_detected_at")

    if len(set(identifiers)) != len(identifiers):
        raise ValueError("evaluation case ids must be unique")
    if len(set(run_refs)) != len(run_refs):
        raise ValueError("evaluation run_refs must be unique")
    return copy.deepcopy(dict(manifest))


def _requirement_coverage(state: Mapping[str, Any]) -> dict[str, Any]:
    requirements = state.get("plan", {}).get("requirements", [])
    required = {
        item.get("id")
        for item in requirements
        if isinstance(item, Mapping)
        and isinstance(item.get("id"), str)
        and item.get("id")
    }
    covered: set[str] = set()
    solution = state.get("solution")
    sections = solution.get("sections", []) if isinstance(solution, Mapping) else []
    for section in sections if isinstance(sections, list) else []:
        if not isinstance(section, Mapping):
            continue
        identifiers = section.get("requirement_ids", [])
        if isinstance(identifiers, list):
            covered.update(value for value in identifiers if isinstance(value, str))
    covered_required = required & covered
    return {
        "required": len(required),
        "covered": len(covered_required),
        "coverage_rate": _ratio(len(covered_required), len(required)),
        "missing_requirement_ids": sorted(required - covered),
    }


def _verification_result(state: Mapping[str, Any]) -> dict[str, Any]:
    report = state.get("verification_report")
    if not isinstance(report, Mapping):
        return {"passed": False, "status": "missing"}
    try:
        validate_verification_report(state, report)
    except (KeyError, TypeError, ValueError) as exc:
        return {"passed": False, "status": "invalid", "reason": str(exc)}
    if state.get("verification_sha256") != digest(dict(report)):
        return {
            "passed": False,
            "status": "stale",
            "reason": "verification report hash is stale",
        }
    return {"passed": True, "status": "passed"}


def _matching_blockers(
    expected_fragments: list[str], observed_blockers: list[str]
) -> tuple[list[str], dict[str, str]]:
    matches: dict[str, str] = {}
    missing: list[str] = []
    for fragment in expected_fragments:
        found = next(
            (
                blocker
                for blocker in observed_blockers
                if fragment.casefold() in blocker.casefold()
            ),
            None,
        )
        if found is None:
            missing.append(fragment)
        else:
            matches[fragment] = found
    return missing, matches


def _correction_seconds(case: Mapping[str, Any]) -> float | None:
    timestamps = case.get("timestamps")
    if not isinstance(timestamps, Mapping):
        return None
    detected = _timestamp(timestamps["failure_detected_at"], "failure_detected_at")
    corrected = _timestamp(timestamps["corrected_at"], "corrected_at")
    return (corrected - detected).total_seconds()


def _evaluate_case(
    workspace: Path, case: Mapping[str, Any]
) -> dict[str, Any]:
    run_ref = case["run_ref"]
    state = load_run(workspace, run_ref)
    status = status_run(workspace, run_ref)
    readiness = status["readiness"]
    observed_ready = readiness.get("ready") is True
    observed_blockers = [
        str(value) for value in readiness.get("blockers", []) if str(value).strip()
    ]
    expected = case["expected"]
    missing_blockers, blocker_matches = _matching_blockers(
        expected["blockers"], observed_blockers
    )
    coverage = _requirement_coverage(state)
    verification = _verification_result(state)
    stale_signals = [
        blocker
        for blocker in observed_blockers
        if "stale" in blocker.casefold() or "changed" in blocker.casefold()
    ]
    stale_detected = status.get("effective_stage") == "stale" or bool(stale_signals)
    coverage_target = expected.get("minimum_requirement_coverage")
    coverage_matches = (
        True
        if coverage_target is None
        else coverage["coverage_rate"] is not None
        and coverage["coverage_rate"] >= coverage_target
    )
    readiness_matches = observed_ready == expected["ready"]
    verification_matches = verification["passed"] == expected["verification_pass"]
    stale_matches = stale_detected == expected["stale"]
    correction_seconds = _correction_seconds(case)
    case_passed = (
        readiness_matches
        and not missing_blockers
        and verification_matches
        and stale_matches
        and coverage_matches
    )
    return {
        "id": case["id"],
        "run_ref": run_ref,
        "passed": case_passed,
        "readiness": {
            "expected": expected["ready"],
            "observed": observed_ready,
            "matches": readiness_matches,
            "false_ready": observed_ready and not expected["ready"],
            "false_blocked": not observed_ready and expected["ready"],
        },
        "blockers": {
            "expected_fragments": expected["blockers"],
            "observed": observed_blockers,
            "matches": blocker_matches,
            "missing_expected_fragments": missing_blockers,
        },
        "requirement_coverage": {
            **coverage,
            "minimum_expected": coverage_target,
            "matches": coverage_matches,
        },
        "verification": {
            **verification,
            "expected_pass": expected["verification_pass"],
            "matches": verification_matches,
        },
        "stale_detection": {
            "expected": expected["stale"],
            "detected": stale_detected,
            "matches": stale_matches,
            "signals": stale_signals,
        },
        "correction_time_seconds": correction_seconds,
    }


def evaluate_manifest(workspace: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate 10-20 existing private runs from a content-free manifest."""
    validated = validate_evaluation_manifest(manifest)
    workspace = Path(workspace)
    cases = [_evaluate_case(workspace, case) for case in validated["cases"]]

    total = len(cases)
    expected_blocked = sum(not case["readiness"]["expected"] for case in cases)
    false_ready = sum(case["readiness"]["false_ready"] for case in cases)
    false_blocked = sum(case["readiness"]["false_blocked"] for case in cases)
    readiness_matches = sum(case["readiness"]["matches"] for case in cases)
    expected_blockers = sum(
        len(case["blockers"]["expected_fragments"]) for case in cases
    )
    matched_blockers = sum(
        len(case["blockers"]["matches"]) for case in cases
    )
    required = sum(case["requirement_coverage"]["required"] for case in cases)
    covered = sum(case["requirement_coverage"]["covered"] for case in cases)
    verification_matches = sum(case["verification"]["matches"] for case in cases)
    verification_passes = sum(case["verification"]["passed"] for case in cases)
    stale_matches = sum(case["stale_detection"]["matches"] for case in cases)
    stale_expected = sum(case["stale_detection"]["expected"] for case in cases)
    stale_detected = sum(case["stale_detection"]["detected"] for case in cases)
    correction_times = [
        case["correction_time_seconds"]
        for case in cases
        if case["correction_time_seconds"] is not None
    ]
    correction_summary = {
        "cases_with_timestamps": len(correction_times),
        "mean_seconds": (
            round(statistics.fmean(correction_times), 3) if correction_times else None
        ),
        "median_seconds": (
            round(statistics.median(correction_times), 3) if correction_times else None
        ),
        "max_seconds": round(max(correction_times), 3) if correction_times else None,
    }
    metrics = {
        "case_count": total,
        "case_pass_count": sum(case["passed"] for case in cases),
        "readiness": {
            "accuracy": _ratio(readiness_matches, total),
            "false_ready_count": false_ready,
            "false_ready_rate_among_expected_blocked": _ratio(
                false_ready, expected_blocked
            ),
            "false_blocked_count": false_blocked,
        },
        "blockers": {
            "expected_count": expected_blockers,
            "matched_count": matched_blockers,
            "recall": _ratio(matched_blockers, expected_blockers),
        },
        "requirement_coverage": {
            "required_count": required,
            "covered_count": covered,
            "coverage_rate": _ratio(covered, required),
        },
        "verification": {
            "observed_pass_count": verification_passes,
            "expected_outcome_accuracy": _ratio(verification_matches, total),
        },
        "stale_detection": {
            "expected_count": stale_expected,
            "detected_count": stale_detected,
            "expected_outcome_accuracy": _ratio(stale_matches, total),
        },
        "correction_time": correction_summary,
    }
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "generated_at": now(),
        "manifest_sha256": digest(validated),
        "passed": all(case["passed"] for case in cases),
        "metrics": metrics,
        "cases": cases,
    }
