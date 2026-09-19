"""Provisional: everything checked except the student's own course evidence.

A new student has supplied no reviewed course material, so a run cannot reach
ready, and that is correct.  What it may reach is provisional: the deliverable
exists and was inspected, the checks passed, the plan cites the student's own
assignment, and the format traces to a named shipped pack.  Every one of those
conditions is required, and each test below removes one to prove it.
"""

import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from engineering_assistant.calculations import check_calculation
from engineering_assistant.cli import main
from engineering_assistant.common import atomic_json, sha256
from engineering_assistant.rendering import render_text_pdf
from engineering_assistant.verification import build_verification_report
from engineering_assistant.runtime import (
    PROFILE_ABSENT,
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


def _plan(source, course_profile_sha256=None):
    plan = {
        "requirements": [{"id": "q1", "text": "answer"}],
        # Only the student's own assignment is cited: a new student has no
        # reviewed course material to cite.
        "evidence": [
            {
                "document_id": "current-assignment",
                "source_sha256": sha256(source),
                "locator": "line:1",
                "text_sha256": hashlib.sha256(source.read_text().encode()).hexdigest(),
            }
        ],
        "deliverables": [{"path": "deliverables/submission.pdf", "format": "pdf"}],
        "verification": {"calculations_required": False, "reason": "prose-only fixture requirement"},
    }
    if course_profile_sha256:
        plan["course_profile_sha256"] = course_profile_sha256
    return plan


def _inspection(path, relative):
    return {
        "artifact_path": relative, "artifact_sha256": sha256(path), "all_pages_reviewed": True,
        "legible": True, "requirements_present": True, "identity_checked": True,
        "no_clipping": True, "unresolved": [],
        "notes": "Reviewed every rendered page, equation, table, and page break.",
    }


def _verifier(workspace, run_id):
    state = load_run(workspace, run_id)
    report = build_verification_report(
        state,
        requirement_findings=[{"requirement_id": "q1", "passed": True, "evidence": ["solution.sections"], "notes": "Requirement is covered."}],
        method_checks=[{"id": "course-method", "passed": True, "notes": "Method follows the course pack."}],
        numerical_checks=[{"id": "calculation-record", "passed": True, "notes": "The plan documents why no calculation is required."}],
        format_checks=[{"id": "declared-format", "passed": True, "notes": "Artifacts match the declared format."}],
        identity_checks=[{"id": "placeholder-identity", "passed": True, "notes": "Only approved identity fields are present."}],
    )
    return record_verification_report(workspace, run_id, report)


class ProvisionalTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.workspace = self.root / "ws"
        self.source = self.root / "assignment.txt"
        self.source.write_text("Report the elastic modulus of the specimen.")

    def _new_student_run(self, course, run_id="r1", *, inspect=True, calculations=()):
        """Drive a run as far as a new student can take it."""
        start_run(self.workspace, run_id, course, self.source)
        set_plan(self.workspace, run_id, _plan(self.source))
        record_solution(self.workspace, run_id, {"sections": [{"requirement_ids": ["q1"]}], "calculations": list(calculations), "unresolved": []})
        record_checks(self.workspace, run_id, [check_calculation(c) for c in calculations])
        artifact = run_dir(self.workspace, run_id) / "deliverables" / "submission.pdf"
        render_text_pdf({"title": "Result", "sections": [{"body": "answer"}]}, artifact)
        record_artifact(self.workspace, run_id, artifact)
        try:
            _verifier(self.workspace, run_id)
        except ValueError:
            # The runtime will not build a verifier report over a failed check.
            # That refusal is correct; the run is then blocked, which is what
            # the failed-check test asserts.
            pass
        if inspect:
            inspect_artifact(self.workspace, run_id, "deliverables/submission.pdf", _inspection(artifact, "deliverables/submission.pdf"))
        return status_run(self.workspace, run_id)

    def test_a_new_student_with_a_shipped_pack_is_provisional_not_ready(self):
        status = self._new_student_run("engr205")
        readiness = status["readiness"]
        self.assertFalse(readiness["ready"])
        self.assertTrue(readiness["provisional"], readiness["blockers"])
        self.assertEqual(status["effective_stage"], "provisional")
        self.assertIn(PROFILE_ABSENT, readiness["provisional_reasons"])
        basis = readiness["provisional_basis"]
        self.assertEqual(basis["source"], "shipped pack engr205")
        self.assertEqual(len(basis["pack_sha256"]), 64)

    def test_the_basis_says_which_values_are_defaults(self):
        # A field the pack does not state is the renderer's default, and the
        # report must say so rather than imply a course rule; a field the pack
        # does state must not be passed off as a default.  The pack is read from
        # disk so this asserts the invariant, not which fields ENGR 205 states
        # today.
        from engineering_assistant.curriculum import DEFAULT_CURRICULUM, RENDERING_FIELDS

        pack = json.loads((DEFAULT_CURRICULUM / "engr205" / "pack.json").read_text(encoding="utf-8"))
        stated = {key for key, value in (pack.get("format", {}).get("rendering") or {}).items() if value is not None}
        fields = self._new_student_run("engr205")["readiness"]["provisional_basis"]["fields"]
        self.assertEqual(set(fields), set(RENDERING_FIELDS))
        for key, label in fields.items():
            with self.subTest(field=key):
                if key in stated:
                    self.assertNotEqual(label, "renderer default")
                else:
                    self.assertEqual(label, "renderer default")

    def test_a_pack_that_states_no_format_is_not_provisional(self):
        # econ222 reports format "none": nothing backs the layout, so the run
        # stays blocked rather than borrowing a pack's authority.
        readiness = self._new_student_run("econ222")["readiness"]
        self.assertFalse(readiness["ready"])
        self.assertFalse(readiness["provisional"])

    def test_a_course_with_no_pack_is_not_provisional(self):
        readiness = self._new_student_run("nosuchcourse")["readiness"]
        self.assertFalse(readiness["provisional"])

    def test_an_uninspected_artifact_keeps_the_run_blocked(self):
        readiness = self._new_student_run("engr205", inspect=False)["readiness"]
        self.assertFalse(readiness["provisional"])

    def test_a_failed_check_keeps_the_run_blocked(self):
        # A wrong answer is not a missing course document.  It must block.
        wrong = {"id": "c1", "expression": "2 + 2", "expected": 5, "unit": "N"}
        readiness = self._new_student_run("engr205", calculations=[wrong])["readiness"]
        self.assertFalse(readiness["provisional"])
        self.assertIn("check failed: c1", readiness["blockers"])

    def test_an_invalid_profile_is_not_softened_to_provisional(self):
        # A profile that exists but fails its own checks is broken, which is a
        # different claim from absent, and must stay a hard blocker.
        atomic_json(self.workspace / "courses" / "engr205" / "profile.json", {"review_status": "draft"})
        readiness = self._new_student_run("engr205")["readiness"]
        self.assertFalse(readiness["provisional"])
        self.assertIn("reviewed course profile is invalid", readiness["blockers"])


class RenderWithoutProfileTests(unittest.TestCase):
    """Deliverables are never withheld, including from a student with no profile."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.workspace = self.root / "ws"
        self.source = self.root / "assignment.txt"
        self.source.write_text("Report the elastic modulus of the specimen.")

    def _cli(self, *args):
        out = io.StringIO()
        # The CLI reports a refusal through argparse, which exits rather than
        # returning, so a refusal arrives here as SystemExit with its code.
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            try:
                code = main(["--workspace", str(self.workspace), *args])
            except SystemExit as exc:
                code = exc.code
        return code, out.getvalue()

    def _render(self, course, **solution_extra):
        start_run(self.workspace, "r1", course, self.source)
        set_plan(self.workspace, "r1", _plan(self.source))
        solution = self.root / "solution.json"
        solution.write_text(json.dumps({
            "title": "Tensile test", "document_type": "technical_report",
            "sections": [{"heading": "Results", "body": "The modulus was computed.", "requirement_ids": ["q1"]}],
            "calculations": [], "unresolved": [], **solution_extra,
        }))
        code, _ = self._cli("render", "r1", str(solution))
        return code, load_run(self.workspace, "r1")

    def test_a_new_student_can_render(self):
        code, state = self._render("engr205")
        self.assertEqual(code, 0)
        self.assertTrue(state["artifacts"])
        self.assertEqual(state["style_basis"]["source"], "shipped pack engr205")

    def test_a_pack_rule_is_enforced_not_just_recorded(self):
        # ENGR 328 requires an abstract.  With no profile, that rule reaches
        # the renderer from the pack and refuses a deliverable without one.
        code, _ = self._render("engr328")
        self.assertNotEqual(code, 0)

    def test_pack_values_are_used_and_attributed(self):
        # ENGR 328 states its layout, so those values reach the renderer and
        # are recorded as course rules, with its one default marked as such.
        code, state = self._render("engr328", abstract="The modulus was measured within five percent.")
        self.assertEqual(code, 0)
        fields = state["style_basis"]["fields"]
        self.assertEqual(fields["abstract"], "course pack rule")
        self.assertEqual(fields["margin_inches"], "pack default, not a course rule")

    def test_a_course_with_no_pack_renders_on_defaults_and_says_so(self):
        code, state = self._render("nosuchcourse")
        self.assertEqual(code, 0)
        self.assertEqual(state["style_basis"]["source"], "renderer defaults")


class PackRenderingBoundsTests(unittest.TestCase):
    """A pack's layout values face the same bounds a course profile's do."""

    def _write(self, rendering):
        from engineering_assistant.curriculum import load_pack
        base = json.loads((Path(__file__).resolve().parents[1] / "curriculum" / "engr205" / "pack.json").read_text())
        base.setdefault("format", {})["rendering"] = rendering
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "pack.json"
            path.write_text(json.dumps(base))
            return load_pack(path)

    def test_bounds_agree_with_the_course_profile_check(self):
        # Every value the profile check accepts at its edges, a pack accepts
        # too, and one step outside is refused by both.  This is what stops the
        # two copies of the bounds drifting apart.
        from engineering_assistant.course_profile import _validate_rendering
        from engineering_assistant.curriculum import CurriculumError
        full = {"title_page": True, "abstract": True, "number_body_pages": True,
                "table_captions_above": True, "figure_captions_below": True,
                "body_font_size": 12, "line_spacing": 1.5, "margin_inches": 1.0}
        for key, good, bad in (("body_font_size", 8, 15), ("body_font_size", 14, 7),
                               ("line_spacing", 2, 2.5), ("margin_inches", 0.5, 1.6)):
            with self.subTest(key=key, good=good, bad=bad):
                _validate_rendering({**full, key: good})
                self._write({key: good})
                with self.assertRaises(ValueError):
                    _validate_rendering({**full, key: bad})
                with self.assertRaises(CurriculumError):
                    self._write({key: bad})

    def test_a_partial_block_is_allowed(self):
        self.assertEqual(self._write({"abstract": True})["format"]["rendering"], {"abstract": True})

    def test_a_non_boolean_switch_is_refused(self):
        from engineering_assistant.curriculum import CurriculumError
        with self.assertRaises(CurriculumError):
            self._write({"abstract": "yes"})


if __name__ == "__main__":
    unittest.main()
