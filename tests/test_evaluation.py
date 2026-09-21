import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from engineering_assistant.common import digest
from engineering_assistant.evaluation import (
    evaluate_manifest,
    validate_evaluation_manifest,
)
from engineering_assistant.verification import build_verification_report


class EvaluationTests(unittest.TestCase):
    def state(self, *, verified=True):
        plan = {"requirements": [{"id": "r1", "text": "Synthetic requirement"}]}
        solution = {
            "sections": [{"heading": "Result", "requirement_ids": ["r1"]}],
            "calculations": [],
            "unresolved": [],
        }
        state = {
            "input": {"sha256": "1" * 64},
            "plan": plan,
            "plan_sha256": digest(plan),
            "solution": solution,
            "solution_sha256": digest(solution),
            "unresolved": [],
            "checks": [],
            "checks_for_solution_sha256": digest(solution),
            "artifacts": [
                {
                    "path": "deliverables/submission.pdf",
                    "sha256": "2" * 64,
                    "source_solution_sha256": digest(solution),
                }
            ],
        }
        if verified:
            report = build_verification_report(
                state,
                requirement_findings=[
                    {
                        "requirement_id": "r1",
                        "passed": True,
                        "evidence": ["solution.sections"],
                        "notes": "Synthetic requirement is covered.",
                    }
                ],
                method_checks=[
                    {"id": "method", "passed": True, "notes": "Method checked."}
                ],
                numerical_checks=[
                    {
                        "id": "numerical",
                        "passed": True,
                        "notes": "Numerical scope checked.",
                    }
                ],
                format_checks=[
                    {"id": "format", "passed": True, "notes": "Format checked."}
                ],
                identity_checks=[
                    {
                        "id": "identity",
                        "passed": True,
                        "notes": "Identity checked.",
                    }
                ],
            )
            state["verification_report"] = report
            state["verification_sha256"] = digest(report)
        return state

    def manifest(self):
        blocker_fragments = [
            "missing input",
            "changed",
            "requirements",
            "calculation",
            "evidence",
            "artifact",
            "inspection",
            "format",
            "unresolved",
        ]
        cases = [
            {
                "id": "case-01",
                "run_ref": "run-01",
                "expected": {
                    "ready": True,
                    "verification_pass": True,
                    "stale": False,
                    "blockers": [],
                    "minimum_requirement_coverage": 1.0,
                },
            }
        ]
        for index, fragment in enumerate(blocker_fragments, start=2):
            case = {
                "id": f"case-{index:02d}",
                "run_ref": f"run-{index:02d}",
                "expected": {
                    "ready": False,
                    "verification_pass": index in (2, 3),
                    "stale": index == 3,
                    "blockers": [fragment],
                },
            }
            if index == 3:
                case["timestamps"] = {
                    "failure_detected_at": "2026-01-01T12:00:00Z",
                    "corrected_at": "2026-01-01T12:30:00Z",
                }
            cases.append(case)
        return {"schema_version": "evaluation-manifest-1", "cases": cases}

    def test_ten_case_report_exposes_false_ready_and_all_metrics(self):
        manifest = self.manifest()
        states = {}
        statuses = {}
        for index in range(1, 11):
            verified = index in (1, 2, 3)
            states[f"run-{index:02d}"] = self.state(verified=verified)
        statuses["run-01"] = {
            "effective_stage": "ready",
            "readiness": {"ready": True, "blockers": []},
        }
        # Deliberate false-ready case: a known missing-input case is marked ready.
        statuses["run-02"] = {
            "effective_stage": "ready",
            "readiness": {"ready": True, "blockers": []},
        }
        statuses["run-03"] = {
            "effective_stage": "stale",
            "readiness": {
                "ready": False,
                "blockers": ["deliverable artifact changed after inspection"],
            },
        }
        observed = [
            "requirements without solution coverage",
            "calculation checks are missing",
            "reviewed course evidence is missing",
            "deliverable artifact is missing",
            "inspection report is missing",
            "artifact format is invalid",
            "unresolved measurement input",
        ]
        for index, blocker in enumerate(observed, start=4):
            statuses[f"run-{index:02d}"] = {
                "effective_stage": "blocked",
                "readiness": {"ready": False, "blockers": [blocker]},
            }

        with patch(
            "engineering_assistant.evaluation.load_run",
            side_effect=lambda workspace, run_id: copy.deepcopy(states[run_id]),
        ), patch(
            "engineering_assistant.evaluation.status_run",
            side_effect=lambda workspace, run_id: copy.deepcopy(statuses[run_id]),
        ):
            report = evaluate_manifest(Path("workspace"), manifest)

        self.assertFalse(report["passed"])
        self.assertEqual(report["metrics"]["case_count"], 10)
        self.assertEqual(report["metrics"]["case_pass_count"], 9)
        self.assertEqual(report["metrics"]["readiness"]["accuracy"], 0.9)
        self.assertEqual(report["metrics"]["readiness"]["false_ready_count"], 1)
        self.assertEqual(
            report["metrics"]["readiness"][
                "false_ready_rate_among_expected_blocked"
            ],
            0.111111,
        )
        self.assertEqual(report["metrics"]["blockers"]["recall"], 0.888889)
        self.assertEqual(
            report["metrics"]["requirement_coverage"]["coverage_rate"], 1.0
        )
        self.assertEqual(
            report["metrics"]["verification"]["expected_outcome_accuracy"], 1.0
        )
        self.assertEqual(
            report["metrics"]["stale_detection"]["expected_outcome_accuracy"],
            1.0,
        )
        self.assertEqual(
            report["metrics"]["correction_time"]["median_seconds"], 1800.0
        )
        self.assertTrue(report["cases"][1]["readiness"]["false_ready"])
        self.assertEqual(
            report["cases"][1]["blockers"]["missing_expected_fragments"],
            ["missing input"],
        )

    def test_manifest_rejects_wrong_case_count_duplicate_runs_and_bad_time(self):
        manifest = self.manifest()
        too_short = copy.deepcopy(manifest)
        too_short["cases"] = too_short["cases"][:9]
        with self.assertRaisesRegex(ValueError, "10-20 cases"):
            validate_evaluation_manifest(too_short)

        duplicate = copy.deepcopy(manifest)
        duplicate["cases"][1]["run_ref"] = duplicate["cases"][0]["run_ref"]
        with self.assertRaisesRegex(ValueError, "run_refs must be unique"):
            validate_evaluation_manifest(duplicate)

        reversed_time = copy.deepcopy(manifest)
        reversed_time["cases"][2]["timestamps"]["corrected_at"] = (
            "2026-01-01T11:59:59Z"
        )
        with self.assertRaisesRegex(ValueError, "cannot precede"):
            validate_evaluation_manifest(reversed_time)

        timezone_free = copy.deepcopy(manifest)
        timezone_free["cases"][2]["timestamps"]["corrected_at"] = (
            "2026-01-01T12:30:00"
        )
        with self.assertRaisesRegex(ValueError, "include a timezone"):
            validate_evaluation_manifest(timezone_free)

    def test_requirement_coverage_threshold_can_fail_a_case(self):
        manifest = self.manifest()
        state = self.state(verified=True)
        state["solution"]["sections"][0]["requirement_ids"] = []
        # Keep the stale solution hash intentionally visible to verification as a failure.
        statuses = {
            case["run_ref"]: {
                "effective_stage": "ready" if index == 0 else "blocked",
                "readiness": {
                    "ready": index == 0,
                    "blockers": [] if index == 0 else [case["expected"]["blockers"][0]],
                },
            }
            for index, case in enumerate(manifest["cases"])
        }
        with patch(
            "engineering_assistant.evaluation.load_run", return_value=state
        ), patch(
            "engineering_assistant.evaluation.status_run",
            side_effect=lambda workspace, run_id: statuses[run_id],
        ):
            report = evaluate_manifest(Path("workspace"), manifest)
        first = report["cases"][0]
        self.assertEqual(first["requirement_coverage"]["coverage_rate"], 0.0)
        self.assertFalse(first["requirement_coverage"]["matches"])
        self.assertFalse(first["passed"])


if __name__ == "__main__":
    unittest.main()
