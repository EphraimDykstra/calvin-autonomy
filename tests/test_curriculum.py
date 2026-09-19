"""The curriculum loader must refuse a pack that cannot describe itself."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from engineering_assistant.cli import main
from engineering_assistant.curriculum import (
    CurriculumError,
    SCHEMA_VERSION,
    coverage_report,
    load_pack,
    load_packs,
)


def _pack(**overrides):
    pack = {
        "schema_version": SCHEMA_VERSION,
        "course": {
            "id": "engr000",
            "code": "ENGR 000",
            "title": "Example Course",
            "professor": "Example",
            "terms_observed": ["Example Term"],
        },
        "coverage": {
            "format": "high",
            "methods": "partial",
            "assignments": "none",
            "notes": "Assignment families are not evidenced.",
        },
        "course_policy": {
            "source": "syllabus (archived)",
            "confidence": "stale",
            "term_observed": "Example Term",
            "summary": "This course has had a stated policy on AI use.",
            "permitted": [],
            "prohibited": [],
            "student_asked": None,
            "professor_answer": None,
        },
        "format": {"body_starts_at_page": 1},
        "methods": [{"id": "m1", "title": "Example method", "steps": ["Example step"]}],
        "assignment_families": [],
    }
    pack.update(overrides)
    return pack


class LoadPackTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _write(self, pack, name="pack.json"):
        path = self.root / name
        path.write_text(json.dumps(pack), encoding="utf-8")
        return path

    def test_valid_pack_loads(self):
        # The benign answer has to be reachable, or the checks measure nothing.
        loaded = load_pack(self._write(_pack()))
        self.assertEqual(loaded["course"]["code"], "ENGR 000")

    def test_pack_covering_nothing_still_loads(self):
        # A pack that honestly reports no coverage is a working pack: the host
        # then asks the student for a handout instead of inventing a format.
        pack = _pack(
            coverage={
                "format": "none",
                "methods": "none",
                "assignments": "none",
                "notes": "No durable evidence for this course.",
            }
        )
        self.assertEqual(load_pack(self._write(pack))["coverage"]["format"], "none")

    def test_missing_course_policy_is_refused(self):
        pack = _pack()
        del pack["course_policy"]
        with self.assertRaises(CurriculumError) as caught:
            load_pack(self._write(pack))
        self.assertIn("course_policy", str(caught.exception))

    def test_unknown_coverage_level_is_refused(self):
        # Degrading an unrecognised level to a default would convert "we do not
        # know" into a claim about the course.
        pack = _pack()
        pack["coverage"]["format"] = "probably fine"
        with self.assertRaises(CurriculumError) as caught:
            load_pack(self._write(pack))
        self.assertIn("probably fine", str(caught.exception))

    def test_missing_coverage_dimension_is_refused(self):
        pack = _pack()
        del pack["coverage"]["methods"]
        with self.assertRaises(CurriculumError):
            load_pack(self._write(pack))

    def test_stale_policy_may_not_carry_terms(self):
        # An archived syllabus proves a policy existed, not what it is now.
        pack = _pack()
        pack["course_policy"]["prohibited"] = ["writing drafts"]
        with self.assertRaises(CurriculumError) as caught:
            load_pack(self._write(pack))
        self.assertIn("prohibited", str(caught.exception))

    def test_unknown_policy_may_not_carry_terms(self):
        pack = _pack()
        pack["course_policy"]["confidence"] = "unknown"
        pack["course_policy"]["permitted"] = ["brainstorming"]
        with self.assertRaises(CurriculumError):
            load_pack(self._write(pack))

    def test_stated_policy_may_carry_terms(self):
        pack = _pack()
        pack["course_policy"]["confidence"] = "stated"
        pack["course_policy"]["prohibited"] = ["writing drafts"]
        self.assertEqual(
            load_pack(self._write(pack))["course_policy"]["confidence"], "stated"
        )

    def test_unknown_policy_confidence_is_refused(self):
        pack = _pack()
        pack["course_policy"]["confidence"] = "probably stale"
        with self.assertRaises(CurriculumError):
            load_pack(self._write(pack))

    def test_future_schema_version_is_refused(self):
        with self.assertRaises(CurriculumError) as caught:
            load_pack(self._write(_pack(schema_version=SCHEMA_VERSION + 1)))
        self.assertIn("schema_version", str(caught.exception))

    def test_malformed_json_is_refused(self):
        path = self.root / "pack.json"
        path.write_text("{not json", encoding="utf-8")
        with self.assertRaises(CurriculumError):
            load_pack(path)


class PipelineSupportTests(unittest.TestCase):
    """A pack must not claim more of the pipeline than exists."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _load(self, support, artifacts=None):
        fmt = {"pipeline_support": support}
        if artifacts is not None:
            fmt["artifacts"] = artifacts
        path = self.root / "pack.json"
        path.write_text(json.dumps(_pack(format=fmt)), encoding="utf-8")
        return load_pack(path)

    def _support(self, **overrides):
        support = {
            "render": False,
            "execute": False,
            "verify_rendered_output": False,
            "note": "The student renders it in Quarto and returns the PDF.",
        }
        support.update(overrides)
        return support

    def test_an_honest_unrenderable_course_loads(self):
        # The benign answer: a Quarto course that says it cannot be rendered.
        pack = self._load(
            self._support(),
            [{"role": "source", "extension": "qmd", "submitted": True}],
        )
        self.assertFalse(pack["format"]["pipeline_support"]["render"])

    def test_a_renderable_submitted_report_loads(self):
        # The MATLAB lab shape: the report renders even though the script is
        # run by the student.
        self._load(
            self._support(render=True, verify_rendered_output=True),
            [
                {"role": "report", "extension": "docx", "submitted": True},
                {"role": "script", "extension": "m", "submitted": True},
            ],
        )

    def test_pipeline_support_is_optional(self):
        path = self.root / "pack.json"
        path.write_text(json.dumps(_pack()), encoding="utf-8")
        self.assertIsNotNone(load_pack(path))

    def test_claiming_to_execute_code_is_refused(self):
        with self.assertRaises(CurriculumError) as caught:
            self._load(self._support(execute=True))
        self.assertIn("runs", str(caught.exception))

    def test_claiming_to_render_nothing_renderable_is_refused(self):
        # A pack saying it renders a course whose only submission is a .qmd
        # is how a host comes to call an unrun notebook finished.
        with self.assertRaises(CurriculumError) as caught:
            self._load(
                self._support(render=True),
                [{"role": "source", "extension": "qmd", "submitted": True}],
            )
        self.assertIn("renderer", str(caught.exception))

    def test_a_flag_must_be_a_boolean(self):
        with self.assertRaises(CurriculumError):
            self._load(self._support(render="yes"))

    def test_the_note_is_required(self):
        # Without it the host knows the pipeline stops but not what the
        # student must do next.
        with self.assertRaises(CurriculumError):
            self._load(self._support(note=""))

    def test_the_report_carries_the_pipeline(self):
        path = self.root / "engr000"
        path.mkdir()
        (path / "pack.json").write_text(
            json.dumps(_pack(format={"pipeline_support": self._support()})), encoding="utf-8"
        )
        course = coverage_report(load_packs(self.root))["courses"][0]
        self.assertFalse(course["pipeline"]["render"])
        self.assertIn("Quarto", course["pipeline"]["note"])


class PackStyleTests(unittest.TestCase):
    def test_each_stated_value_carries_its_own_evidence(self):
        # "Course pack rule" says only that the pack states a value.  The pack's
        # own basis says whether that is a written rule or observed practice,
        # and status must carry it so a host never overstates the evidence.
        from engineering_assistant.curriculum import pack_for_course, pack_style
        _, basis = pack_style(pack_for_course("engr328"))
        self.assertEqual(basis["field_basis"]["abstract"], "spec")
        self.assertTrue(str(basis["field_basis"]["margin_inches"]).startswith("default"))
        for key in basis["field_basis"]:
            self.assertNotEqual(basis["fields"][key], "renderer default")


class LoadPacksTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _write(self, pack_id, pack):
        directory = self.root / pack_id
        directory.mkdir()
        (directory / "pack.json").write_text(json.dumps(pack), encoding="utf-8")

    def test_missing_root_is_empty(self):
        self.assertEqual(load_packs(self.root / "absent"), {})

    def test_packs_are_keyed_by_directory(self):
        self._write("engr319", _pack())
        self._write("engr328", _pack())
        self.assertEqual(sorted(load_packs(self.root)), ["engr319", "engr328"])

    def test_one_bad_pack_refuses_the_whole_load(self):
        # Skipping it would leave the host reporting coverage for a course
        # whose rules never loaded, which is the false-ready result again.
        self._write("engr319", _pack())
        bad = _pack()
        del bad["course_policy"]
        self._write("engr328", bad)
        with self.assertRaises(CurriculumError):
            load_packs(self.root)

    def test_coverage_report_summarises_every_pack(self):
        self._write("engr319", _pack())
        report = coverage_report(load_packs(self.root))
        self.assertEqual(report["course_count"], 1)
        course = report["courses"][0]
        self.assertEqual(course["coverage"]["assignments"], "none")
        self.assertEqual(course["policy_confidence"], "stale")
        self.assertFalse(course["policy_answered"])

    def test_report_marks_a_policy_the_student_resolved(self):
        pack = _pack()
        pack["course_policy"]["confidence"] = "stated"
        pack["course_policy"]["professor_answer"] = "Example answer."
        self._write("engr319", pack)
        report = coverage_report(load_packs(self.root))
        self.assertTrue(report["courses"][0]["policy_answered"])


class CoursesCommandTests(unittest.TestCase):
    """The report has to be reachable from the CLI, not just importable."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _run(self, curriculum):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = main(["courses", "--curriculum", str(curriculum)])
        return code, json.loads(buffer.getvalue())

    def test_reports_a_shipped_pack(self):
        directory = self.root / "engr319"
        directory.mkdir()
        (directory / "pack.json").write_text(json.dumps(_pack()), encoding="utf-8")
        code, report = self._run(self.root)
        self.assertEqual(code, 0)
        self.assertEqual(report["course_count"], 1)
        self.assertEqual(report["courses"][0]["id"], "engr319")

    def test_absent_curriculum_reports_nothing_rather_than_failing(self):
        # A fresh clone has no packs.  That is an honest empty answer, not an
        # error: the host should say it covers nothing, not crash on startup.
        code, report = self._run(self.root / "absent")
        self.assertEqual(code, 0)
        self.assertEqual(report["course_count"], 0)


if __name__ == "__main__":
    unittest.main()
