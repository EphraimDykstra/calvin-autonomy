"""A run waiting on the student is blocked, and says one true thing about why.

A deliverable can be complete in every way this project can check and still be
waiting on something only the student has: a chart drawn from property data the
tool may not ship, a photograph of the rig, a reading nobody wrote down. Before
`outstanding_inputs` existed, both honest ways of recording that were refused by
`verify-report`, so the run reported the real gap AND "structured verifier report
is missing", and the student could not tell which to act on.

Declaring an input must never soften a verdict. These tests take a run that
genuinely reaches `ready` and prove that no combination of declarations and
awaiting findings can keep it there, that a withdrawn declaration cannot smuggle
it back, and that `awaiting` is refused everywhere it does not belong.
"""

import hashlib
import itertools
import json
import tempfile
import unittest
from pathlib import Path

from engineering_assistant.calculations import check_calculation
from engineering_assistant.common import atomic_json, sha256
from engineering_assistant.evidence import review_evidence
from engineering_assistant.course_profile import set_course_profile
from engineering_assistant.rendering import render_text_pdf
from engineering_assistant.runtime import (
    OUTSTANDING_INPUTS_FILE,
    declare_outstanding_inputs,
    inspect_artifact,
    load_run,
    record_artifact,
    record_checks,
    record_solution,
    record_verification_report,
    run_dir,
    set_plan,
    start_run,
    status_run,
)
from engineering_assistant.verification import (
    build_verification_report,
    validate_verification_report,
)

COURSE = "engr328"
CHART = {
    "id": "ph-chart-summer",
    "need": "Send the R134a P-h diagram for the summer run, as an image file.",
    "requirement_ids": ["q1"],
}


def _findings(**overrides):
    findings = {
        "requirement_findings": [
            {"requirement_id": "q1", "passed": True, "evidence": ["solution.sections"], "notes": "Covered."}
        ],
        "method_checks": [{"id": "m", "passed": True, "notes": "Follows the reviewed method."}],
        "numerical_checks": [{"id": "n", "passed": True, "notes": "Recomputed independently."}],
        "format_checks": [{"id": "f", "passed": True, "notes": "Artifact matches the declared format."}],
        "identity_checks": [{"id": "i", "passed": True, "notes": "Only approved identity fields."}],
    }
    findings.update(overrides)
    return findings


AWAITING_FINDING = [
    {
        "requirement_id": "q1",
        "awaiting": CHART["id"],
        "evidence": ["solution.sections"],
        "notes": "The cycle chart this requirement asks for is waiting on the student.",
    }
]


class OutstandingInputTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.ws = self.root / "ws"
        self.source = self.root / "assignment.txt"
        self.source.write_text("Report the coefficient of performance for each season.")

    def _run(self, run_id="r1"):
        """Everything a student can supply: the run below reaches ready."""
        text = "Reviewed course method."
        atomic_json(self.ws / "courses" / COURSE / "catalog.json", {
            "course": COURSE,
            "documents": [{"id": "guide-1", "sha256": "guide-hash", "active": True, "status": "extracted",
                           "blocks": [{"locator": "page:1", "text": text}]}]})
        evidence = {"document_id": "guide-1", "source_sha256": "guide-hash", "locator": "page:1",
                    "text_sha256": hashlib.sha256(text.encode()).hexdigest(), "review_status": "reviewed"}
        review_evidence(self.ws, COURSE, "guide-1", "page:1", "Reviewed the stated method and its context.")
        profile = set_course_profile(self.ws, COURSE, {
            "schema_version": 1, "review_status": "reviewed",
            "precedence": ["current_assignment", "reviewed_course_guidance"],
            "rules": {"reporting": "concise"},
            "rendering": {"body_font_size": 11, "line_spacing": 1.2, "margin_inches": 1, "title_page": True,
                          "abstract": True, "number_body_pages": True, "table_captions_above": True,
                          "figure_captions_below": True},
            "evidence": [evidence]})
        start_run(self.ws, run_id, COURSE, self.source)
        set_plan(self.ws, run_id, {
            "requirements": [{"id": "q1", "text": "report the coefficient of performance"}],
            "evidence": [{"document_id": "current-assignment", "source_sha256": sha256(self.source),
                          "locator": "line:1",
                          "text_sha256": hashlib.sha256(self.source.read_text().encode()).hexdigest()},
                         evidence],
            "course_profile_sha256": profile["sha256"],
            "deliverables": [{"path": "deliverables/submission.pdf", "format": "pdf"}],
            "verification": {"calculations_required": True, "reason": "the student returns the computed values"}})
        calculation = {"id": "c1", "expression": "2 + 2", "expected": 4, "unit": "dimensionless"}
        record_solution(self.ws, run_id, {"sections": [{"requirement_ids": ["q1"]}], "calculations": [calculation], "unresolved": []})
        record_checks(self.ws, run_id, [check_calculation(calculation)])
        artifact = run_dir(self.ws, run_id) / "deliverables" / "submission.pdf"
        render_text_pdf({"title": "Result", "sections": [{"body": "COP = 3.33"}]}, artifact)
        record_artifact(self.ws, run_id, artifact)
        self.artifact = artifact
        return run_id

    def _report(self, run_id, **overrides):
        return build_verification_report(load_run(self.ws, run_id), **_findings(**overrides))

    def _inspect(self, run_id):
        inspect_artifact(self.ws, run_id, "deliverables/submission.pdf", {
            "artifact_path": "deliverables/submission.pdf", "artifact_sha256": sha256(self.artifact),
            "all_pages_reviewed": True, "legible": True, "requirements_present": True,
            "identity_checked": True, "no_clipping": True, "unresolved": [],
            "notes": "Reviewed every rendered page, equation, table, and page break."})
        return status_run(self.ws, run_id)

    # -- the baseline this whole file is measured against -----------------
    def test_the_same_run_without_a_declaration_reaches_ready(self):
        """Without this, every assertion below would pass for the wrong reason."""
        run_id = self._run()
        record_verification_report(self.ws, run_id, self._report(run_id))
        status = self._inspect(run_id)
        self.assertTrue(status["readiness"]["ready"], status["readiness"]["blockers"])

    # -- what the state is for --------------------------------------------
    def test_a_declared_input_lets_the_report_bind_and_keeps_the_run_blocked(self):
        run_id = self._run()
        declare_outstanding_inputs(self.ws, run_id, [CHART])
        record_verification_report(self.ws, run_id, self._report(run_id, requirement_findings=AWAITING_FINDING))
        status = self._inspect(run_id)
        readiness = status["readiness"]
        self.assertFalse(readiness["ready"])
        self.assertFalse(readiness["provisional"])
        self.assertEqual(status["effective_stage"], "blocked")
        self.assertIn(f"waiting on you: {CHART['need']}", readiness["blockers"])
        # The point of the state: the real reason stands alone, with no second
        # blocker saying the verifier report is missing.
        self.assertNotIn("structured verifier report is missing", readiness["blockers"])

    def test_the_blocker_says_what_to_do(self):
        """A student reads this sentence in status and must be able to act on it."""
        run_id = self._run()
        declare_outstanding_inputs(self.ws, run_id, [CHART])
        record_verification_report(self.ws, run_id, self._report(run_id, requirement_findings=AWAITING_FINDING))
        waiting = [b for b in self._inspect(run_id)["readiness"]["blockers"] if b.startswith("waiting on you:")]
        self.assertEqual(len(waiting), 1)
        self.assertIn("Send", waiting[0])
        self.assertGreater(len(waiting[0].split()), 6)

    def test_a_declaration_nothing_awaits_still_blocks(self):
        """Declared and unmentioned must not be quieter than declared and cited."""
        run_id = self._run()
        declare_outstanding_inputs(self.ws, run_id, [CHART])
        record_verification_report(self.ws, run_id, self._report(run_id))
        readiness = self._inspect(run_id)["readiness"]
        self.assertFalse(readiness["ready"])
        self.assertFalse(readiness["provisional"])
        self.assertIn(f"waiting on you: {CHART['need']}", readiness["blockers"])

    # -- the invariant, by mutation ---------------------------------------
    def test_no_combination_of_declarations_and_awaiting_findings_is_ready(self):
        """Every reachable shape of the new state, against an otherwise ready run."""
        declarations = ([CHART], [CHART, {"id": "psychrometric-chart", "need": "Send the summer psychrometric chart, as an image file.", "requirement_ids": ["q1"]}])
        for index, (declared, awaiting) in enumerate(itertools.product(declarations, (True, False))):
            with self.subTest(declared=len(declared), awaiting=awaiting):
                run_id = self._run(run_id=f"m{index}")
                declare_outstanding_inputs(self.ws, run_id, declared)
                overrides = {"requirement_findings": AWAITING_FINDING} if awaiting else {}
                record_verification_report(self.ws, run_id, self._report(run_id, **overrides))
                readiness = self._inspect(run_id)["readiness"]
                self.assertFalse(readiness["ready"])
                self.assertFalse(readiness["provisional"])
                self.assertEqual(len([b for b in readiness["blockers"] if b.startswith("waiting on you:")]), len(declared))

    def test_withdrawing_the_declaration_cannot_buy_ready(self):
        """Resolution is as strict as declaration: the old report goes stale."""
        run_id = self._run()
        declare_outstanding_inputs(self.ws, run_id, [CHART])
        record_verification_report(self.ws, run_id, self._report(run_id, requirement_findings=AWAITING_FINDING))
        self._inspect(run_id)
        # The student has not sent anything; the declaration is simply removed.
        declare_outstanding_inputs(self.ws, run_id, [])
        readiness = status_run(self.ws, run_id)["readiness"]
        self.assertFalse(readiness["ready"])
        self.assertIn("structured verifier report is missing", readiness["blockers"])
        # Re-binding now demands a genuinely passing requirement, which is the
        # verifier's statement that the work is actually done.
        with self.assertRaises(ValueError):
            self._report(run_id, requirement_findings=AWAITING_FINDING)

    # -- where awaiting is refused ----------------------------------------
    def test_awaiting_an_undeclared_input_is_refused(self):
        run_id = self._run()
        with self.assertRaises(ValueError) as caught:
            self._report(run_id, requirement_findings=AWAITING_FINDING)
        self.assertIn("undeclared", str(caught.exception))

    def test_awaiting_on_any_other_finding_class_is_refused(self):
        run_id = self._run()
        declare_outstanding_inputs(self.ws, run_id, [CHART])
        for key, identifier in (("method_checks", "m"), ("numerical_checks", "n"),
                                ("format_checks", "f"), ("identity_checks", "i")):
            with self.subTest(category=key):
                finding = [{"id": identifier, "awaiting": CHART["id"], "notes": "Waiting."}]
                with self.assertRaises(ValueError) as caught:
                    self._report(run_id, **{key: finding})
                self.assertIn("only a requirement", str(caught.exception))

    def test_an_awaiting_finding_is_excused_nothing_but_passing(self):
        """Waiting on the student is a verdict; a verdict still has to be readable."""
        run_id = self._run()
        declare_outstanding_inputs(self.ws, run_id, [CHART])
        base = AWAITING_FINDING[0]
        for bad, expected in (
            ({k: v for k, v in base.items() if k != "evidence"}, "needs evidence"),
            ({k: v for k, v in base.items() if k != "notes"}, "needs notes"),
            ({**base, "unresolved": ["the chart never arrived"]}, "is unresolved"),
            ({**base, "status": "failed"}, "is not passing"),
        ):
            with self.subTest(expected=expected):
                with self.assertRaises(ValueError) as caught:
                    self._report(run_id, requirement_findings=[bad])
                self.assertIn(expected, str(caught.exception))

    def test_editing_the_declaration_on_disk_is_caught(self):
        """The file is the record; readiness re-reads it rather than trusting state."""
        run_id = self._run()
        declare_outstanding_inputs(self.ws, run_id, [CHART])
        record_verification_report(self.ws, run_id, self._report(run_id, requirement_findings=AWAITING_FINDING))
        self._inspect(run_id)
        path = run_dir(self.ws, run_id) / OUTSTANDING_INPUTS_FILE
        path.write_text(json.dumps({"outstanding_inputs": []}))
        readiness = status_run(self.ws, run_id)["readiness"]
        self.assertFalse(readiness["ready"])
        self.assertIn("declared outstanding inputs record is missing or changed", readiness["blockers"])

    def test_a_finding_cannot_both_pass_and_await(self):
        run_id = self._run()
        declare_outstanding_inputs(self.ws, run_id, [CHART])
        finding = [{**AWAITING_FINDING[0], "passed": True}]
        with self.assertRaises(ValueError) as caught:
            self._report(run_id, requirement_findings=finding)
        self.assertIn("cannot both pass and await", str(caught.exception))

    def test_passed_is_checked_in_both_directions(self):
        run_id = self._run()
        declare_outstanding_inputs(self.ws, run_id, [CHART])
        state = load_run(self.ws, run_id)
        awaiting_report = self._report(run_id, requirement_findings=AWAITING_FINDING)
        self.assertIs(awaiting_report["passed"], False)
        with self.assertRaises(ValueError):
            validate_verification_report(state, {**awaiting_report, "passed": True})
        clean = self._report(run_id)
        self.assertIs(clean["passed"], True)
        with self.assertRaises(ValueError):
            validate_verification_report(state, {**clean, "passed": False})

    # -- what may be declared ---------------------------------------------
    def test_two_inputs_may_not_ask_in_the_same_words(self):
        """Readiness drops duplicate sentences, so identical needs would tell
        the student once about two things and invite them to send one."""
        run_id = self._run()
        with self.assertRaises(ValueError) as caught:
            declare_outstanding_inputs(self.ws, run_id, [CHART, {**CHART, "id": "second"}])
        self.assertIn("word for word", str(caught.exception))

    def test_a_declaration_must_say_what_to_supply_and_what_it_holds_up(self):
        run_id = self._run()
        for bad in ({"id": "x", "requirement_ids": ["q1"]},
                    {"id": "x", "need": "   ", "requirement_ids": ["q1"]},
                    {"id": "", "need": "Send it.", "requirement_ids": ["q1"]},
                    {"id": "x", "need": "Send it.", "requirement_ids": []},
                    {"id": "x", "need": "Send it.", "requirement_ids": ["nosuch"]}):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    declare_outstanding_inputs(self.ws, run_id, [bad])

    def test_declaring_again_discards_the_report_that_bound_the_old_one(self):
        run_id = self._run()
        declare_outstanding_inputs(self.ws, run_id, [CHART])
        record_verification_report(self.ws, run_id, self._report(run_id, requirement_findings=AWAITING_FINDING))
        state = declare_outstanding_inputs(self.ws, run_id, [{**CHART, "need": "Send the summer P-h diagram."}])
        self.assertNotIn("verification_report", state)


if __name__ == "__main__":
    unittest.main()
