import copy
import unittest

from engineering_assistant.common import digest
from engineering_assistant.verification import (
    build_verification_report,
    validate_verification_report,
    verify_solution,
)


class StructuredVerificationTests(unittest.TestCase):
    def _state(self):
        plan = {
            "requirements": [
                {"id": "q1", "text": "Calculate the heat rate."},
                {"id": "q2", "text": "Present the requested table."},
            ]
        }
        solution = {
            "sections": [
                {"heading": "Results", "requirement_ids": ["q1", "q2"]}
            ],
            "calculations": [
                {
                    "id": "heat-rate",
                    "expression": "m*cp*dT",
                    "variables": {"m": 2.0, "cp": 4.0, "dT": 3.0},
                    "expected": 24.0,
                    "unit": "kW",
                }
            ],
            "unresolved": [],
        }
        solution_hash = digest(solution)
        checks = verify_solution(solution)
        return {
            "input": {"sha256": "a" * 64},
            "plan": plan,
            "plan_sha256": digest(plan),
            "solution": solution,
            "solution_sha256": solution_hash,
            "checks": checks,
            "checks_for_solution_sha256": solution_hash,
            "artifacts": [
                {
                    "path": "deliverables/submission.pdf",
                    "sha256": "b" * 64,
                    "source_solution_sha256": solution_hash,
                }
            ],
            "unresolved": [],
        }

    def _findings(self):
        return {
            "requirement_findings": [
                {
                    "requirement_id": "q1",
                    "passed": True,
                    "evidence": ["solution.sections[0]", "checks.heat-rate"],
                    "notes": "The heat-rate calculation and units are present.",
                },
                {
                    "requirement_id": "q2",
                    "passed": True,
                    "evidence": ["solution.sections[0].tables[0]"],
                    "notes": "The requested results table is present.",
                },
            ],
            "method_checks": [
                {
                    "id": "course-method",
                    "passed": True,
                    "notes": "Method matches the reviewed course source.",
                }
            ],
            "numerical_checks": [
                {
                    "id": "recalculated",
                    "passed": True,
                    "notes": "The independent arithmetic check passed.",
                }
            ],
            "format_checks": [
                {
                    "id": "rendered-pages",
                    "passed": True,
                    "notes": "Every rendered page was inspected.",
                }
            ],
            "identity_checks": [
                {
                    "id": "identity",
                    "passed": True,
                    "notes": "Only the current run identity is present.",
                }
            ],
        }

    def test_builder_binds_all_current_hashes_and_validates(self):
        state = self._state()
        report = build_verification_report(state, **self._findings())
        self.assertEqual(report["bindings"]["input_sha256"], "a" * 64)
        self.assertEqual(report["bindings"]["plan_sha256"], state["plan_sha256"])
        self.assertEqual(report["bindings"]["solution_sha256"], state["solution_sha256"])
        self.assertEqual(report["bindings"]["artifacts"][0]["sha256"], "b" * 64)
        self.assertTrue(report["passed"])
        self.assertEqual(validate_verification_report(state, report), report)

    def test_validator_rejects_stale_plan_checks_and_artifacts(self):
        state = self._state()
        report = build_verification_report(state, **self._findings())

        changed_input = copy.deepcopy(state)
        changed_input["input"]["sha256"] = "d" * 64
        with self.assertRaisesRegex(ValueError, "input_sha256.*stale"):
            validate_verification_report(changed_input, report)

        changed_plan = copy.deepcopy(state)
        changed_plan["plan"]["requirements"][0]["text"] = "Changed"
        with self.assertRaisesRegex(ValueError, "plan hash.*stale"):
            validate_verification_report(changed_plan, report)

        changed_solution = copy.deepcopy(state)
        changed_solution["solution"]["sections"][0]["heading"] = "Changed"
        with self.assertRaisesRegex(ValueError, "solution hash.*stale"):
            validate_verification_report(changed_solution, report)

        changed_checks = copy.deepcopy(state)
        changed_checks["checks"][0]["actual"] = 25.0
        with self.assertRaisesRegex(ValueError, "calculation_checks_sha256.*stale"):
            validate_verification_report(changed_checks, report)

        changed_artifact = copy.deepcopy(state)
        changed_artifact["artifacts"][0]["sha256"] = "c" * 64
        with self.assertRaisesRegex(ValueError, "artifacts binding is stale"):
            validate_verification_report(changed_artifact, report)

        for unsafe in ("../submission.pdf", "a/../../submission.pdf", "/etc/passwd",
                       "deliverables/../../escape.pdf", "./submission.pdf",
                       "a/./submission.pdf", "deliverables\\submission.pdf", ""):
            unsafe_artifact = self._state()
            unsafe_artifact["artifacts"][0]["path"] = unsafe
            with self.assertRaisesRegex(ValueError, "contained relative", msg=unsafe):
                build_verification_report(unsafe_artifact, **self._findings())

    def test_builder_rejects_failed_or_unresolved_findings(self):
        failed = self._findings()
        failed["method_checks"][0]["passed"] = False
        with self.assertRaisesRegex(ValueError, "method check failed"):
            build_verification_report(self._state(), **failed)

        with self.assertRaisesRegex(ValueError, "unresolved"):
            build_verification_report(
                self._state(), **self._findings(), unresolved=["Equation needs review"]
            )

        state = self._state()
        state["checks"][0]["passed"] = False
        with self.assertRaisesRegex(ValueError, "calculation checks failed"):
            build_verification_report(state, **self._findings())

    def test_requirement_findings_must_cover_plan_exactly(self):
        findings = self._findings()
        findings["requirement_findings"].pop()
        with self.assertRaisesRegex(ValueError, "incomplete or unexpected"):
            build_verification_report(self._state(), **findings)

    def test_validator_rejects_hidden_or_malformed_findings(self):
        state = self._state()
        report = build_verification_report(state, **self._findings())
        report["findings"]["method"][0]["unresolved"] = ["Source not reviewed"]
        with self.assertRaisesRegex(ValueError, "method check is unresolved"):
            validate_verification_report(state, report)

        report = build_verification_report(state, **self._findings())
        report["findings"]["other"] = [
            {"id": "hidden", "passed": False, "notes": "Must not be ignored."}
        ]
        with self.assertRaisesRegex(ValueError, "categories.*unexpected"):
            validate_verification_report(state, report)

    def test_existing_verify_solution_behavior_is_preserved(self):
        checks = verify_solution(self._state()["solution"])
        self.assertEqual([item["id"] for item in checks], ["heat-rate"])
        self.assertTrue(checks[0]["passed"])


if __name__ == "__main__":
    unittest.main()
