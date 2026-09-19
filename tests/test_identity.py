import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from engineering_assistant.identity import (
    PLACEHOLDER_DISPLAY_NAME,
    PLACEHOLDER_STUDENT_ID,
    find_identity_leaks,
    run_identity,
    sanitize_reusable_metadata,
)
from engineering_assistant.matching import register_example
from engineering_assistant.runtime import start_run
from scripts import check_distribution


class IdentityPolicyTests(unittest.TestCase):
    def _assignment(self):
        return {
            "id": "beam-01", "title": "Beam sizing", "family": "beam",
            "method": "Euler", "requirements": [{"id": "r1", "text": "Calculate stress"}],
            "deliverables": ["report"], "text": "Size a beam.",
        }

    def test_default_identity_is_placeholder(self):
        self.assertEqual(run_identity(), {
            "schema_version": 1,
            "display_name": PLACEHOLDER_DISPLAY_NAME,
            "student_id": PLACEHOLDER_STUDENT_ID,
            "explicit": False,
        })

    def test_explicit_identity_is_private_run_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "assignment.txt"
            source.write_text("requirements", encoding="utf-8")
            state = start_run(root / "workspace", "run-1", "demo", source, display_name="Alice Example", student_id="S-123")
            self.assertEqual(state["identity"]["display_name"], "Alice Example")
            self.assertEqual(json.loads((root / "workspace/assignments/run-1/run.json").read_text())["identity"]["student_id"], "S-123")

    def test_reusable_metadata_removes_names_and_ids(self):
        metadata = {"author": "Alice Example", "student_id": "S-123", "file": "Alice Example-report.pdf", "safe": "reviewed"}
        clean = sanitize_reusable_metadata(metadata)
        self.assertEqual(clean, {"file": "[Redacted]-report.pdf", "safe": "reviewed"})
        self.assertFalse(find_identity_leaks(clean, ["Alice Example", "S-123"]))

    def test_matching_example_drops_identity_and_nested_prior_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            example = {
                "id": "alice-example", "student_name": "Alice Example", "student_id": "S-123",
                "assignment": {**self._assignment(), "notes": "Prepared by Alice Example"},
                "metadata": {"author": "Alice Example", "submission_id": "S-123", "reviewed": True},
                "artifacts": [],
            }
            clean = register_example(root, "demo", example)
            stored = json.loads((root / "courses/demo/examples.json").read_text())
            serialized = json.dumps(stored)
            self.assertNotIn("Alice Example", serialized)
            self.assertNotIn("S-123", serialized)
            self.assertNotIn("student_name", clean)
            self.assertNotIn("author", clean.get("metadata", {}))

    def test_identity_keys_are_matched_in_every_spelling(self):
        """camelCase spellings name the same field and must be treated alike."""
        metadata = {
            "studentName": "Dana Fictional", "displayName": "Dana Fictional",
            "authorId": "S-999", "createdBy": "Dana Fictional",
            "ownerId": "S-999", "submissionId": "S-999", "safe": "reviewed",
        }
        clean = sanitize_reusable_metadata(metadata)
        self.assertEqual(clean, {"safe": "reviewed"})
        # The detector must not share the sanitizer's blind spot, or the
        # distribution audit passes a file the sanitizer failed to strip.
        for key in ("studentName", "displayName", "authorId", "createdBy", "ownerId", "submissionId"):
            self.assertEqual(find_identity_leaks({key: "Dana Fictional"}), [f"$.{key}"], key)
        self.assertFalse(find_identity_leaks({"displayName": PLACEHOLDER_DISPLAY_NAME}))

    def test_camel_case_identity_never_reaches_a_shared_example(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            example = {
                "id": "beam-02", "studentName": "Dana Fictional", "authorId": "S-999",
                "assignment": {**self._assignment(), "notes": "Prepared by Dana Fictional"},
                "metadata": {"createdBy": "Dana Fictional", "submissionId": "S-999", "reviewed": True},
                "artifacts": [],
            }
            clean = register_example(root, "demo", example)
            serialized = json.dumps(json.loads((root / "courses/demo/examples.json").read_text()))
            self.assertNotIn("Dana Fictional", serialized)
            self.assertNotIn("S-999", serialized)
            self.assertNotIn("studentName", clean)
            self.assertNotIn("createdBy", clean.get("metadata", {}))
            self.assertFalse(find_identity_leaks(clean, ["Dana Fictional", "S-999"]))
            # A structural example id is not identity and must survive the
            # broader key matching; see the IDENTITY_KEYS note on ``id``.
            self.assertEqual(clean["id"], "beam-02")

    def test_distribution_name_scan_and_secret_file_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "public.txt").write_text("Alice Example", encoding="utf-8")
            self.assertTrue(any("forbidden name" in item for item in check_distribution.audit(root, ["Alice Example"])))
            (root / "private-token.txt").write_text("Alice Example", encoding="utf-8")
            original_read_text = Path.read_text
            def guarded_read_text(path, *args, **kwargs):
                if path.name == "private-token.txt":
                    raise AssertionError("secret file opened")
                return original_read_text(path, *args, **kwargs)
            with patch.object(Path, "read_text", guarded_read_text):
                errors = check_distribution.audit(root)
            self.assertTrue(any("secret-like name" in item for item in errors))


if __name__ == "__main__":
    unittest.main()
