"""A course this pipeline cannot render can never be reported ready.

Found by an independent persona test of the shipped plugin. For STAT 241 the
student submits a Quarto file they render themselves, and the pack says so with
pipeline_support.render false. A host could render a substitute PDF, inspect
that, and reach ready for R code that had never been run and whose answer was
wrong. Everything the gate checked was true of the substitute, and nothing was
true of what the student would hand in.
"""

import hashlib
import tempfile
import unittest
from pathlib import Path

from engineering_assistant.common import atomic_json, sha256
from engineering_assistant.course_profile import set_course_profile
from engineering_assistant.evidence import review_evidence
from engineering_assistant.rendering import render_text_pdf
from engineering_assistant.runtime import (
    PIPELINE_NOT_RENDERED,
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
from engineering_assistant.verification import build_verification_report


class PipelineReadinessTests(unittest.TestCase):
    """The worker's Variant B: fully evidenced, and still not ready."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.ws = self.root / "ws"
        self.source = self.root / "assignment.txt"
        self.source.write_text("Run a one sided t test and report the p value.")

    def _fully_evidenced_run(self, course, run_id="r1"):
        """Everything a student can supply: own material ingested and reviewed."""
        text = "Reviewed course method."
        atomic_json(self.ws / "courses" / course / "catalog.json", {
            "course": course,
            "documents": [{"id": "guide-1", "sha256": "guide-hash", "active": True, "status": "extracted",
                           "blocks": [{"locator": "page:1", "text": text}]}]})
        evidence = {"document_id": "guide-1", "source_sha256": "guide-hash", "locator": "page:1",
                    "text_sha256": hashlib.sha256(text.encode()).hexdigest(), "review_status": "reviewed"}
        review_evidence(self.ws, course, "guide-1", "page:1", "Reviewed the stated method and its context.")
        profile = set_course_profile(self.ws, course, {
            "schema_version": 1, "review_status": "reviewed",
            "precedence": ["current_assignment", "reviewed_course_guidance"],
            "rules": {"reporting": "concise"},
            "rendering": {"body_font_size": 11, "line_spacing": 1.2, "margin_inches": 1, "title_page": True,
                          "abstract": True, "number_body_pages": True, "table_captions_above": True,
                          "figure_captions_below": True},
            "evidence": [evidence]})
        start_run(self.ws, run_id, course, self.source)
        set_plan(self.ws, run_id, {
            "requirements": [{"id": "q1", "text": "report the p value"}],
            "evidence": [{"document_id": "current-assignment", "source_sha256": sha256(self.source),
                          "locator": "line:1",
                          "text_sha256": hashlib.sha256(self.source.read_text().encode()).hexdigest()},
                         evidence],
            "course_profile_sha256": profile["sha256"],
            "deliverables": [{"path": "deliverables/submission.pdf", "format": "pdf"}],
            "verification": {"calculations_required": False, "reason": "prose-only fixture requirement"}})
        record_solution(self.ws, run_id, {"sections": [{"requirement_ids": ["q1"]}], "calculations": [], "unresolved": []})
        record_checks(self.ws, run_id, [])
        artifact = run_dir(self.ws, run_id) / "deliverables" / "submission.pdf"
        render_text_pdf({"title": "Result", "sections": [{"body": "p = 0.049"}]}, artifact)
        record_artifact(self.ws, run_id, artifact)
        state = load_run(self.ws, run_id)
        record_verification_report(self.ws, run_id, build_verification_report(
            state,
            requirement_findings=[{"requirement_id": "q1", "passed": True, "evidence": ["solution.sections"], "notes": "Covered."}],
            method_checks=[{"id": "m", "passed": True, "notes": "Follows the reviewed method."}],
            numerical_checks=[{"id": "n", "passed": True, "notes": "The plan documents why none are required."}],
            format_checks=[{"id": "f", "passed": True, "notes": "Artifact matches the declared format."}],
            identity_checks=[{"id": "i", "passed": True, "notes": "Only approved identity fields."}]))
        inspect_artifact(self.ws, run_id, "deliverables/submission.pdf", {
            "artifact_path": "deliverables/submission.pdf", "artifact_sha256": sha256(artifact),
            "all_pages_reviewed": True, "legible": True, "requirements_present": True,
            "identity_checked": True, "no_clipping": True, "unresolved": [],
            "notes": "Reviewed every rendered page, equation, table, and page break."})
        return status_run(self.ws, run_id)

    def test_a_course_this_pipeline_cannot_render_is_never_ready(self):
        status = self._fully_evidenced_run("stats241")
        readiness = status["readiness"]
        self.assertFalse(readiness["ready"], "a render:false course reached ready")
        self.assertIn(PIPELINE_NOT_RENDERED, readiness["blockers"])
        self.assertTrue(readiness["provisional"])
        self.assertEqual(status["effective_stage"], "provisional")
        self.assertTrue(readiness["provisional_basis"]["deliverable_produced_outside_pipeline"])

    def test_cs104_is_covered_too(self):
        self.assertFalse(self._fully_evidenced_run("cs104")["readiness"]["ready"])

    def test_a_course_this_pipeline_does_render_still_reaches_ready(self):
        # The benign answer must stay reachable, or this check would simply
        # have broken readiness for every course.
        status = self._fully_evidenced_run("engr328")
        self.assertTrue(status["readiness"]["ready"], status["readiness"]["blockers"])


if __name__ == "__main__":
    unittest.main()
