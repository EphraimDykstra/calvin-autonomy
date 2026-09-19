"""Issue #19: an identity value too short to redact safely is refused.

Redaction is a case-insensitive substring match, so a one- or two-character
value shreds ordinary words ("Euler 1st order" -> "Euler [Redacted]st order")
and the result looks like redaction working.  The fix refuses such values; it
never stops redacting a value it redacts today.
"""
import json
import tempfile
import unittest
from pathlib import Path

from engineering_assistant.identity import (
    run_identity,
    sanitize_reusable_example,
    sanitize_reusable_metadata,
)
from engineering_assistant.matching import register_example


def _example(**identity):
    return {
        "id": "beam-03", **identity,
        "assignment": {
            "id": "beam-03", "title": "Stress analysis", "family": "beam",
            "method": "Euler 1st order", "requirements": [{"id": "r1", "text": "Calculate stress"}],
            "deliverables": ["report"], "text": "Size a beam.",
        },
        "artifacts": [],
    }


class ShortIdentityValueTests(unittest.TestCase):
    def test_issue_repro_one_character_author_id_is_refused_not_shredded(self):
        with self.assertRaisesRegex(ValueError, "cannot identify anyone"):
            sanitize_reusable_example(_example(authorId="1"))

    def test_issue_repro_one_character_student_id_in_metadata_is_refused(self):
        with self.assertRaisesRegex(ValueError, "cannot be redacted without corrupting"):
            sanitize_reusable_metadata({"student_id": "S", "method": "Stress analysis"})

    def test_two_characters_is_refused_and_the_message_does_not_echo_it(self):
        with self.assertRaises(ValueError) as caught:
            sanitize_reusable_example(_example(studentName=" Qx "))
        self.assertNotIn("Qx", str(caught.exception))
        self.assertIn("studentName", str(caught.exception))

    def test_short_known_value_is_refused(self):
        with self.assertRaises(ValueError):
            sanitize_reusable_metadata({"method": "Euler 1st order"}, known_values=["1"])

    def test_register_example_rejects_rather_than_storing_shredded_text(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(ValueError):
                register_example(root, "demo", _example(authorId="1"))
            self.assertFalse((root / "courses/demo/examples.json").exists())

    def test_run_identity_refuses_a_short_explicit_value(self):
        with self.assertRaisesRegex(ValueError, "student_id"):
            run_identity(student_id="7")
        with self.assertRaisesRegex(ValueError, "display_name"):
            run_identity(display_name="Q")

    def test_values_at_the_floor_are_still_redacted_as_before(self):
        # Refusal is a tightening only: a three-character value keeps the
        # existing substring redaction, including inside other words.
        clean = sanitize_reusable_metadata({"author": "Zq9", "file": "Zq9-report.pdf", "note": "xZq9y"})
        self.assertEqual(clean, {"file": "[Redacted]-report.pdf", "note": "x[Redacted]y"})

    def test_real_identity_still_redacted_and_ordinary_text_intact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            clean = register_example(root, "demo", _example(authorId="S-4417", studentName="Bo Li"))
            serialized = json.dumps(json.loads((root / "courses/demo/examples.json").read_text()))
            self.assertNotIn("S-4417", serialized)
            self.assertNotIn("Bo Li", serialized)
            self.assertEqual(clean["assignment"]["method"], "Euler 1st order")
            self.assertEqual(clean["assignment"]["title"], "Stress analysis")


if __name__ == "__main__":
    unittest.main()
