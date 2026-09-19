import json
import tempfile
import unittest
from pathlib import Path

from scripts.validate_course_pack import validate


class CoursePackValidationTests(unittest.TestCase):
    def test_bounded_pack_locators_and_precedence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "course-pack"; root.mkdir()
            source_root = Path(directory) / "workspace" / "courses" / "DEMO"; source_root.mkdir(parents=True)
            (root / "course.yaml").write_text(
                "course_id: demo\nsource_root: ../workspace/courses/DEMO\nhistorical_syllabus_ai_content: excluded_by_owner\n",
                encoding="utf-8",
            )
            (root / "style-profile.yaml").write_text("status: reviewed\n", encoding="utf-8")
            (root / "style-profile.json").write_text(json.dumps({
                "precedence": ["instructor_assignment", "instructor_template", "reviewed_course_guidance", "anonymous_student_example", "unresolved_or_image_only_evidence"],
                "review_status": "reviewed",
                "rendering": {"body_font_size": 12},
                "evidence": [{"document_id": "guide"}],
            }), encoding="utf-8")
            self.assertEqual(validate(root), [])

    def test_missing_pack_returns_an_error(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(validate(Path(directory) / "missing"), ["course-pack root is missing"])

    def test_rejects_dangling_family_sources_and_invalid_ledgers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "course-pack"
            (root / "assignment-families").mkdir(parents=True)
            (root / "ledgers").mkdir()
            (root / "course.yaml").write_text(
                "course_id: demo\n"
                "historical_syllabus_ai_content: excluded_by_owner\n"
                "sources:\n  - id: known-source\n"
                "source_ledgers:\n  - family: homework\n    path: ledgers/homework.json\n",
                encoding="utf-8",
            )
            (root / "style-profile.yaml").write_text("status: reviewed\n", encoding="utf-8")
            (root / "style-profile.json").write_text(json.dumps({
                "precedence": ["instructor_assignment", "instructor_template", "reviewed_course_guidance", "anonymous_student_example", "unresolved_or_image_only_evidence"],
                "review_status": "reviewed",
                "rendering": {"body_font_size": 12},
                "evidence": [{"document_id": "guide"}],
            }), encoding="utf-8")
            (root / "assignment-families" / "demo.yaml").write_text(
                "family_id: demo\nsource_artifacts:\n  - retired-queue-id\n",
                encoding="utf-8",
            )
            (root / "ledgers" / "homework.json").write_text(json.dumps({
                "course_id": "wrong-course",
                "sources": [],
                "source": "/Users/example/private/course.pdf",
            }), encoding="utf-8")

            errors = validate(root)
            self.assertIn(
                "unresolved source_artifact in assignment-families/demo.yaml: retired-queue-id",
                errors,
            )
            self.assertIn("source ledger course_id mismatch: ledgers/homework.json", errors)
            self.assertIn("source ledger lacks sources: ledgers/homework.json", errors)
            self.assertIn("source ledger contains an absolute user path: ledgers/homework.json", errors)


if __name__ == "__main__":
    unittest.main()
