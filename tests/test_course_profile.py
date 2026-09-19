import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from engineering_assistant import cli
from engineering_assistant.common import atomic_json
from engineering_assistant.course_profile import (
    course_coverage,
    course_onboarding_status,
    load_course_profile,
    set_course_profile,
)
from engineering_assistant.matching import register_example
from engineering_assistant.rendering import render_text_pdf
from engineering_assistant.evidence import review_evidence


class CourseProfileTests(unittest.TestCase):
    def profile(self, evidence):
        return {
            "schema_version": 1,
            "review_status": "reviewed",
            "precedence": ["current_assignment", "reviewed_course_guidance"],
            "rules": {"reporting": "concise technical prose"},
            "rendering": {
                "body_font_size": 12,
                "line_spacing": 1.5,
                "margin_inches": 1,
                "title_page": True,
                "abstract": True,
                "number_body_pages": True,
                "table_captions_above": True,
                "figure_captions_below": True,
            },
            "evidence": [evidence],
        }

    def test_profile_requires_resolved_reviewed_course_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            text = "Use a concise technical report."
            evidence = {
                "document_id": "style-guide",
                "source_sha256": "source-hash",
                "locator": "page:1",
                "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "review_status": "reviewed",
            }
            atomic_json(
                workspace / "courses" / "demo" / "catalog.json",
                {"course": "demo", "documents": [{"id": "style-guide", "sha256": "source-hash", "status": "extracted", "blocks": [{"locator": "page:1", "text": text}]}]},
            )
            review_evidence(workspace,"demo","style-guide","page:1","Reviewed the report guidance and formatting requirements.")
            result = set_course_profile(workspace, "demo", self.profile(evidence))
            self.assertEqual(load_course_profile(workspace, "demo"), result["profile"])
            stale = dict(evidence); stale["locator"] = "page:99"
            with self.assertRaisesRegex(ValueError, "locator or text hash is stale"):
                set_course_profile(workspace, "demo", self.profile(stale))

    def test_renderer_enforces_profile_abstract_requirement(self):
        rendering = self.profile({})["rendering"]
        with tempfile.TemporaryDirectory() as directory:
            solution = {"document_type": "technical_report", "title": "Report", "sections": [{"heading": "Results", "body": "Result."}]}
            with self.assertRaisesRegex(ValueError, "requires an abstract"):
                render_text_pdf(solution, Path(directory) / "report.pdf", style_profile={"rendering": rendering})


COURSE = "course-101"


class _CourseFixture:
    """Shared workspace fixtures for the coverage and onboarding reports."""

    def source(self, workspace, text="Use a concise technical report."):
        """Register one extracted course source and return a citation for it."""
        atomic_json(
            Path(workspace) / "courses" / COURSE / "catalog.json",
            {"course": COURSE, "documents": [{"id": "style-guide", "sha256": "source-hash", "status": "extracted", "active": True, "blocks": [{"locator": "page:1", "text": text}]}]},
        )
        return {
            "document_id": "style-guide",
            "source_sha256": "source-hash",
            "locator": "page:1",
            "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
        }

    def profile(self, evidence):
        return CourseProfileTests().profile(evidence)

    def reviewed_course(self, workspace):
        """Bring one course all the way to a reviewed, resolving profile."""
        evidence = self.source(workspace)
        review_evidence(workspace, COURSE, "style-guide", "page:1", "Reviewed the rendered guidance page in context.")
        set_course_profile(workspace, COURSE, self.profile(evidence))
        return evidence

    def example(self, workspace, example_id, family, method, reviewed):
        register_example(workspace, COURSE, {
            "id": example_id,
            "review_status": "reviewed" if reviewed else "provisional",
            "assignment": {"title": "Prior work", "family": family, "method": method},
        })

    def states(self, report, kind):
        return {item["name"]: item["state"] for item in report["items"] if item["kind"] == kind}


class CourseCoverageTests(_CourseFixture, unittest.TestCase):
    """Coverage must report what a course can actually back, never more."""

    def test_absent_is_reported_without_the_caller_naming_expectations(self):
        # A three-state report that only reaches "absent" when the caller passes
        # expected= would be a two-state report with extra steps.  With no
        # profile there is genuinely no formatting coverage, so absent must
        # appear on the bare call.
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            self.source(workspace)
            report = course_coverage(workspace, COURSE)
            self.assertEqual(self.states(report, "formatting_rule"), {"rendering": "absent"})
            self.assertEqual(report["summary"]["absent"], 1)
            self.assertFalse(report["ready"])

    def test_bare_report_shows_reviewed_provisional_and_absent_together(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            self.reviewed_course(workspace)
            self.example(workspace, "hx-1", "heat-exchanger-homework", "lmtd", reviewed=True)
            self.example(workspace, "lab-1", "lab-report", "uncertainty", reviewed=False)
            report = course_coverage(workspace, COURSE)
            families = self.states(report, "assignment_family")
            self.assertEqual(families["heat-exchanger-homework"], "reviewed")
            self.assertEqual(families["lab-report"], "provisional")
            self.assertEqual(self.states(report, "formatting_rule")["reporting"], "reviewed")
            expected = course_coverage(workspace, COURSE, {"assignment_families": ["design-project"]})
            self.assertEqual(self.states(expected, "assignment_family")["design-project"], "absent")
            self.assertEqual(set(expected["summary"]), {"reviewed", "provisional", "absent"})
            self.assertTrue(all(count > 0 for count in expected["summary"].values()))

    def test_coverage_reports_a_degraded_profile_instead_of_raising(self):
        # load_course_profile raises in exactly the states coverage exists to
        # report, so coverage must catch and translate rather than propagate.
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            self.reviewed_course(workspace)
            self.assertEqual(self.states(course_coverage(workspace, COURSE), "formatting_rule")["rendering"], "reviewed")
            # The source is re-ingested and the cited passage no longer matches.
            self.source(workspace, text="Different guidance entirely.")
            with self.assertRaises(ValueError):
                load_course_profile(workspace, COURSE)
            degraded = course_coverage(workspace, COURSE)
            self.assertEqual(self.states(degraded, "formatting_rule")["rendering"], "provisional")
            self.assertFalse(degraded["ready"])
            self.assertTrue(any("course profile is provisional" in item for item in degraded["blockers"]))

    def test_a_self_asserted_review_status_does_not_make_a_rule_reviewed(self):
        # validate_profile forces review_status to "reviewed", so a profile that
        # merely parses self-asserts one.  State must come from whether the
        # cited evidence resolves and was actually reviewed.
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            evidence = self.source(workspace)
            stored = dict(self.profile(evidence), course=COURSE)
            self.assertEqual(stored["review_status"], "reviewed")
            atomic_json(Path(workspace) / "courses" / COURSE / "profile.json", stored)
            report = course_coverage(workspace, COURSE)
            self.assertEqual(self.states(report, "formatting_rule")["reporting"], "provisional")
            self.assertFalse(report["ready"])

    def test_reviewed_families_never_imply_readiness_without_a_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            self.source(workspace)
            self.example(workspace, "hx-1", "heat-exchanger-homework", "lmtd", reviewed=True)
            report = course_coverage(workspace, COURSE)
            self.assertEqual(self.states(report, "assignment_family")["heat-exchanger-homework"], "reviewed")
            self.assertFalse(report["ready"])
            self.assertTrue(any("course profile is absent" in item for item in report["blockers"]))

    def test_coverage_is_deterministic_and_ready_only_when_fully_backed(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            self.reviewed_course(workspace)
            self.example(workspace, "hx-1", "heat-exchanger-homework", "lmtd", reviewed=True)
            report = course_coverage(workspace, COURSE)
            self.assertTrue(report["ready"])
            self.assertEqual(report["blockers"], [])
            self.assertEqual(report, course_coverage(workspace, COURSE))
            self.assertEqual(report["items"], sorted(report["items"], key=lambda item: (item["kind"], item["name"])))

    def test_an_unread_source_stops_the_report_clearing_the_course(self):
        # An unextracted source is guidance nobody has read, and it may contain
        # a rule that contradicts everything the report just claimed.
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            self.reviewed_course(workspace)
            self.example(workspace, "hx-1", "heat-exchanger-homework", "lmtd", reviewed=True)
            self.assertTrue(course_coverage(workspace, COURSE)["ready"])
            catalog_path = workspace / "courses" / COURSE / "catalog.json"
            catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
            catalog["documents"].append({"id": "scan", "sha256": "scan-hash", "status": "needs_ocr", "active": True, "blocks": []})
            atomic_json(catalog_path, catalog)
            report = course_coverage(workspace, COURSE)
            self.assertFalse(report["ready"])
            self.assertTrue(any("not yet extracted" in item for item in report["blockers"]))

    def test_the_cli_returns_the_same_reports_it_prints(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            self.reviewed_course(workspace)
            self.example(workspace, "hx-1", "heat-exchanger-homework", "lmtd", reviewed=True)
            for command, expected in (
                ("coverage", course_coverage(workspace, COURSE)),
                ("onboarding-status", course_onboarding_status(workspace, COURSE)),
                ("evidence-queue", course_onboarding_status(workspace, COURSE)["review_queue"]),
            ):
                stream = io.StringIO()
                with contextlib.redirect_stdout(stream):
                    self.assertEqual(cli.main(["--workspace", str(workspace), command, "--course", COURSE]), 0)
                self.assertEqual(json.loads(stream.getvalue()), expected)

    def test_the_cli_reports_coverage_against_named_expectations(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            self.reviewed_course(workspace)
            expected_path = workspace / "expected.json"
            atomic_json(expected_path, {"assignment_families": ["design-project"]})
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                cli.main(["--workspace", str(workspace), "coverage", "--course", COURSE, "--expected", str(expected_path)])
            report = json.loads(stream.getvalue())
            self.assertEqual(self.states(report, "assignment_family"), {"design-project": "absent"})

    def test_coverage_survives_a_workspace_with_nothing_in_it(self):
        with tempfile.TemporaryDirectory() as directory:
            report = course_coverage(Path(directory), COURSE)
            self.assertFalse(report["ready"])
            self.assertEqual(self.states(report, "formatting_rule"), {"rendering": "absent"})
            self.assertEqual(self.states(report, "assignment_family"), {})


class CourseOnboardingTests(_CourseFixture, unittest.TestCase):
    """The guided path is data, so it stays true as the workspace changes."""

    def test_an_empty_course_starts_at_ingest_with_everything_behind_it(self):
        with tempfile.TemporaryDirectory() as directory:
            status = course_onboarding_status(Path(directory), COURSE)
            self.assertFalse(status["ready"])
            self.assertEqual(status["next_step"], "ingest_sources")
            self.assertEqual([step["state"] for step in status["steps"]], ["pending", "blocked", "blocked", "blocked", "blocked"])
            self.assertEqual(status["steps"][0]["blocks"], ["resolve_extraction", "review_evidence", "register_profile", "register_examples"])
            self.assertEqual(status["steps"][-1]["blocks"], [])

    def test_unresolved_extraction_is_what_blocks_the_review_step(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            atomic_json(
                workspace / "courses" / COURSE / "catalog.json",
                {"course": COURSE, "documents": [{"id": "scan", "sha256": "source-hash", "status": "needs_ocr", "active": True, "blocks": []}]},
            )
            status = course_onboarding_status(workspace, COURSE)
            self.assertEqual(status["next_step"], "resolve_extraction")
            by_id = {step["id"]: step for step in status["steps"]}
            self.assertEqual(by_id["ingest_sources"]["state"], "done")
            # A finished step holds nothing up, so it must claim to block nothing.
            self.assertEqual(by_id["ingest_sources"]["blocks"], [])
            self.assertIn("review_evidence", by_id["resolve_extraction"]["blocks"])
            self.assertEqual(status["review_queue"]["documents_awaiting_extraction"], 1)

    def test_a_pending_review_names_the_downstream_work_it_holds_up(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            self.reviewed_course(workspace)
            # The cited passage changes, so its review no longer stands.
            self.source(workspace, text="Different guidance entirely.")
            status = course_onboarding_status(workspace, COURSE)
            self.assertEqual(status["next_step"], "review_evidence")
            self.assertEqual(status["review_queue"]["pending_count"], 1)
            self.assertEqual(status["review_queue"]["pending"][0]["blocks"], ["course-profile"])
            self.assertEqual(status["review_queue"]["pending"][0]["state"], "stale")

    def test_a_fully_onboarded_course_reports_ready_with_no_next_step(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            self.reviewed_course(workspace)
            self.example(workspace, "hx-1", "heat-exchanger-homework", "lmtd", reviewed=True)
            status = course_onboarding_status(workspace, COURSE)
            self.assertTrue(status["ready"])
            self.assertIsNone(status["next_step"])
            self.assertEqual(status["blockers"], [])
            self.assertEqual({step["state"] for step in status["steps"]}, {"done"})

    def test_provisional_examples_leave_the_last_step_unfinished(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            self.reviewed_course(workspace)
            self.example(workspace, "hx-1", "heat-exchanger-homework", "lmtd", reviewed=False)
            status = course_onboarding_status(workspace, COURSE)
            self.assertEqual(status["next_step"], "register_examples")
            self.assertFalse(status["ready"])


if __name__ == "__main__":
    unittest.main()
