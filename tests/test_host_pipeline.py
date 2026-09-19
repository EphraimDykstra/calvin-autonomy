"""A host with only the documented commands must be able to finish a run.

A persona following SKILL.md could not reach provisional at all. The verifier
report required bindings that are canonical digests of run state, which no
command prints and the template marked REPLACE_FROM_CURRENT_RUN. The only way
through was importing a private function.
"""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from engineering_assistant.cli import main
from engineering_assistant.common import sha256
from engineering_assistant.rendering import render_text_docx, render_text_pdf


class HostCanFinishTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.ws = self.root / "ws"
        self.source = self.root / "assignment.txt"
        self.source.write_text("Report the elastic modulus.")

    def _cli(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            try:
                code = main(["--workspace", str(self.ws), *args])
            except SystemExit as exc:
                code = exc.code
        return code, out.getvalue()

    def _write(self, name, value):
        path = self.root / name
        path.write_text(json.dumps(value))
        return str(path)

    def test_findings_alone_are_enough_to_record_a_verifier_report(self):
        self._cli("start", str(self.source), "--course", "engr205", "--run-id", "r1")
        plan = self._write("plan.json", {
            "requirements": [{"id": "q1", "text": "modulus"}],
            "evidence": [{"document_id": "current-assignment", "source_sha256": sha256(self.source),
                          "locator": "line:1",
                          "text_sha256": __import__("hashlib").sha256(self.source.read_text().encode()).hexdigest()}],
            "deliverables": [{"path": "deliverables/submission.pdf", "format": "pdf"}],
            "verification": {"calculations_required": False, "reason": "prose-only fixture"}})
        self._cli("accept-plan", "r1", plan)
        solution = self._write("solution.json", {
            "title": "Tensile test", "document_type": "technical_report",
            "abstract": "The modulus was measured.",
            "sections": [{"heading": "Results", "body": "It was measured.", "requirement_ids": ["q1"]}],
            "calculations": [], "unresolved": []})
        self.assertEqual(self._cli("render", "r1", solution)[0], 0)
        # verify must run before verify-report even with no calculations: it
        # records the checks the report's bindings are computed from.
        self.assertEqual(self._cli("verify", "r1")[0], 0)

        # Findings only: no bindings, which a host cannot compute.
        findings = self._write("findings.json", {
            "requirements": [{"requirement_id": "q1", "passed": True, "evidence": ["solution.sections"],
                              "notes": "The requirement is covered by the solution."}],
            "method": [{"id": "method", "passed": True, "notes": "Follows the course pack's method."}],
            "numerical": [{"id": "numerical", "passed": True, "notes": "The plan documents why none are required."}],
            "format": [{"id": "format", "passed": True, "notes": "The artifact matches the declared format."}],
            "identity": [{"id": "identity", "passed": True, "notes": "Only approved identity fields appear."}]})
        code, _ = self._cli("verify-report", "r1", findings)
        self.assertEqual(code, 0, "a verifier that supplies findings must be able to record a report")

        from engineering_assistant.runtime import run_dir

        artifact = run_dir(self.ws, "r1") / "deliverables" / "submission.pdf"
        inspection = self._write("inspection.json", {
            "artifact_path": "deliverables/submission.pdf", "artifact_sha256": sha256(artifact),
            "all_pages_reviewed": True, "legible": True, "requirements_present": True,
            "identity_checked": True, "no_clipping": True, "unresolved": [],
            "notes": "Reviewed every rendered page, equation, table and page break."})
        self.assertEqual(self._cli("inspect", "r1", "--artifact", "deliverables/submission.pdf",
                                   "--report", inspection)[0], 0)
        code, out = self._cli("status", "r1")
        status = json.loads(out)
        self.assertEqual(status["effective_stage"], "provisional", status["readiness"]["blockers"])

    def test_a_failed_finding_is_still_refused(self):
        # Building the bindings here loosens nothing.
        self._cli("start", str(self.source), "--course", "engr205", "--run-id", "r2")
        findings = self._write("bad.json", {
            "requirements": [{"requirement_id": "q1", "passed": False, "evidence": ["x"], "notes": "Not covered."}],
            "method": [], "numerical": [], "format": [], "identity": []})
        self.assertNotEqual(self._cli("verify-report", "r2", findings)[0], 0)


class AbstractIsNeverDroppedTests(unittest.TestCase):
    """An abstract that a layout cannot carry must say so, not vanish."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _solution(self, document_type):
        base = {"title": "Pitot lab", "document_type": document_type,
                "abstract": "The velocity profile was measured.",
                "sections": [{"heading": "Results", "body": "It was measured."}]}
        if document_type == "memo":
            base["memo_header"] = {"to": "[Instructor]", "date": "19 September 2026", "re": "Pitot lab"}
        return base

    def test_a_layout_without_a_title_page_refuses_an_abstract(self):
        for document_type in ("memo", "worked_problem", "technical_memo"):
            for render in (render_text_pdf, render_text_docx):
                with self.subTest(document_type=document_type, render=render.__name__):
                    with self.assertRaises(ValueError) as caught:
                        render(self._solution(document_type), self.root / "out")
                    self.assertIn("technical_report", str(caught.exception))

    def test_a_technical_report_still_carries_its_abstract(self):
        for render, suffix in ((render_text_pdf, "pdf"), (render_text_docx, "docx")):
            with self.subTest(render=render.__name__):
                render(self._solution("technical_report"), self.root / f"ok.{suffix}")


if __name__ == "__main__":
    unittest.main()
