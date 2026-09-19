import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from engineering_assistant.common import atomic_json
from engineering_assistant.evidence import evidence_review_queue,resolve_evidence,review_evidence


class EvidenceTests(unittest.TestCase):
    def catalog(self, workspace, course="demo", status="extracted"):
        text = "Reviewed method statement."
        atomic_json(Path(workspace) / "courses" / course / "catalog.json", {
            "course": course,
            "documents": [{"id": "method", "sha256": "source-hash", "status": status, "active": True, "blocks": [{"locator": "page:1", "text": text}]}],
        })
        return {"document_id": "method", "source_sha256": "source-hash", "locator": "page:1", "text_sha256": hashlib.sha256(text.encode()).hexdigest(), "review_status": "reviewed"}

    def test_resolves_reviewed_same_course_source(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence = self.catalog(directory)
            self.assertTrue(any("not reviewed" in item for item in resolve_evidence(Path(directory), "demo", [evidence])))
            review_evidence(Path(directory),"demo","method","page:1","Method and units were checked against the rendered source.")
            self.assertEqual(resolve_evidence(Path(directory), "demo", [evidence]), [])

    def test_rejects_wrong_course_unreviewed_stale_and_unresolved_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory); evidence = self.catalog(workspace)
            self.assertTrue(resolve_evidence(workspace, "other", [evidence]))
            self.assertTrue(any("not reviewed" in item for item in resolve_evidence(workspace, "demo", [evidence])))
            review_evidence(workspace,"demo","method","page:1","Reviewed source text and method context.")
            stale = dict(evidence); stale["text_sha256"] = "stale"
            self.assertTrue(any("stale" in item for item in resolve_evidence(workspace, "demo", [stale])))
            unresolved = self.catalog(workspace, status="needs_ocr")
            self.assertTrue(any("incomplete or unresolved" in item for item in resolve_evidence(workspace, "demo", [unresolved])))

    def test_current_assignment_locator_and_text_hash_must_resolve(self):
        text="Answer both parts."; text_hash=hashlib.sha256(text.encode()).hexdigest()
        evidence={"document_id":"current-assignment","source_sha256":"input-hash","locator":"line:1","text_sha256":text_hash}
        extraction={"status":"extracted","blocks":[{"locator":"line:1","text":text}]}
        errors=resolve_evidence(Path("."),"demo",[evidence],current_input_sha256="input-hash",current_input_extraction=extraction,require_current_assignment=True)
        self.assertIn("no resolved reviewed same-course evidence",errors)
        stale=dict(evidence); stale["locator"]="line:99"
        self.assertTrue(any("current-assignment locator" in item for item in resolve_evidence(Path("."),"demo",[stale],current_input_sha256="input-hash",current_input_extraction=extraction,require_current_assignment=True)))

    def test_review_queue_reports_pending_citations_and_what_they_block(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            evidence = self.catalog(workspace)
            citation = dict(evidence, used_by="course-profile")
            queue = evidence_review_queue(workspace, "demo", [citation])
            self.assertEqual(queue["status"], "review_required")
            self.assertEqual(queue["pending_count"], 1)
            self.assertEqual(queue["pending"][0]["state"], "unreviewed")
            self.assertEqual(queue["pending"][0]["blocks"], ["course-profile"])
            self.assertEqual((queue["documents_total"], queue["blocks_total"], queue["blocks_awaiting_review"]), (1, 1, 1))
            review_evidence(workspace, "demo", "method", "page:1", "Checked the rendered page in context.")
            cleared = evidence_review_queue(workspace, "demo", [citation])
            self.assertEqual((cleared["status"], cleared["pending"]), ("clear", []))
            self.assertEqual((cleared["blocks_reviewed"], cleared["blocks_awaiting_review"]), (1, 0))

    def test_review_queue_merges_downstream_consumers_of_one_pending_review(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            evidence = self.catalog(workspace)
            queue = evidence_review_queue(workspace, "demo", [
                dict(evidence, used_by="example:hx-1"),
                dict(evidence, used_by=["course-profile", "example:hx-1"]),
            ])
            self.assertEqual(queue["pending_count"], 1)
            self.assertEqual(queue["pending"][0]["blocks"], ["course-profile", "example:hx-1"])

    def test_review_queue_classifies_stale_unextracted_and_unresolved_citations(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            evidence = self.catalog(workspace)
            stale = evidence_review_queue(workspace, "demo", [dict(evidence, text_sha256="stale")])
            self.assertEqual(stale["pending"][0]["state"], "stale")
            missing = evidence_review_queue(workspace, "demo", [dict(evidence, document_id="absent-source")])
            self.assertEqual(missing["pending"][0]["state"], "unresolved")
            self.catalog(workspace, status="needs_ocr")
            pending_ocr = evidence_review_queue(workspace, "demo", [dict(evidence)])
            self.assertEqual(pending_ocr["pending"][0]["state"], "unextracted")
            self.assertEqual(pending_ocr["documents_awaiting_extraction"], 1)
            self.assertEqual(pending_ocr["blocks_total"], 0)

    def test_review_queue_never_exposes_source_text_or_reviewer_notes(self):
        # A pending review is an exact VISUAL review of the rendered source.
        # Handing the reviewer extracted text would let them approve evidence
        # they never actually looked at, turning the review gate into a
        # formality, so triage carries identifiers and hashes only.
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            reviewed_text, pending_text = "Reviewed guidance page.", "Unreviewed guidance page."
            atomic_json(workspace / "courses" / "demo" / "catalog.json", {
                "course": "demo",
                "documents": [{"id": "method", "sha256": "source-hash", "status": "extracted", "active": True, "blocks": [
                    {"locator": "page:1", "text": reviewed_text},
                    {"locator": "page:2", "text": pending_text},
                ]}],
            })
            review_evidence(workspace, "demo", "method", "page:1", "Distinctive reviewer note about the page.")
            citation = {
                "document_id": "method", "source_sha256": "source-hash", "locator": "page:2",
                "text_sha256": hashlib.sha256(pending_text.encode()).hexdigest(), "used_by": "course-profile",
            }
            queue = evidence_review_queue(workspace, "demo", [citation])
            self.assertEqual(queue["pending"][0]["state"], "unreviewed")
            serialized = json.dumps(queue)
            self.assertNotIn(pending_text, serialized)
            self.assertNotIn(reviewed_text, serialized)
            self.assertNotIn("Distinctive reviewer note", serialized)
            self.assertNotIn("notes", serialized)

    def test_review_queue_survives_a_missing_or_unusable_course(self):
        with tempfile.TemporaryDirectory() as directory:
            queue = evidence_review_queue(Path(directory), "demo", None)
            self.assertEqual(queue["status"], "clear")
            self.assertEqual((queue["documents_total"], queue["blocks_total"], queue["pending_count"]), (0, 0, 0))


if __name__ == "__main__":
    unittest.main()
