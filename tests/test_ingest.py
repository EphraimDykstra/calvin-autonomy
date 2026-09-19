import hashlib
import json
import os
import shutil
import struct
import tempfile
import tracemalloc
import unittest
import zipfile
from unittest import mock
from contextlib import redirect_stdout
from io import BytesIO
from io import StringIO
from pathlib import Path

from engineering_assistant.cli import _json_input, main
from engineering_assistant.ingest import (
    MAX_ARCHIVE_MEMBER_BYTES,
    MAX_ARCHIVE_TOTAL_BYTES,
    MAX_BLOCKS,
    MAX_BLOCK_CHARS,
    MAX_TEXT_BYTES,
    _decode_text,
    auto_ocr_document,
    extract_source_blocks,
    import_ocr_transcription,
    ingest,
    ocr_status,
    search,
)
from engineering_assistant.ocr import OcrError, build_runner
from engineering_assistant.evidence import evidence_review_status, review_evidence


class IngestTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.source = self.root / "sources"
        self.workspace = self.root / "workspace"
        self.source.mkdir()

    def tearDown(self):
        self.tempdir.cleanup()

    def _catalog(self):
        with (self.workspace / "courses" / "demo" / "catalog.json").open(encoding="utf-8") as handle:
            return json.load(handle)

    def _transcription(self, document, blocks):
        return {
            "schema_version": 1,
            "document_id": document["id"],
            "source_sha256": document["sha256"],
            "provenance": {"method": "manual_transcription", "tool": "visual review"},
            "blocks": blocks,
        }

    def test_hash_preservation_and_non_destructive_copy(self):
        original = b"A technical beam requirement.\n"
        path = self.source / "notes.md"
        path.write_bytes(original)
        catalog = ingest(self.source, self.workspace, "demo")
        document = catalog["documents"][0]
        self.assertEqual(document["sha256"], hashlib.sha256(original).hexdigest())
        self.assertEqual(Path(document["source_copy"]).is_absolute(), False)
        self.assertEqual((self.workspace / "courses" / "demo" / document["source_copy"]).read_bytes(), original)
        self.assertEqual(path.read_bytes(), original)

    def test_duplicate_reimport_is_idempotent(self):
        (self.source / "notes.txt").write_text("same content", encoding="utf-8")
        first = ingest(self.source, self.workspace, "demo")
        second = ingest(self.source, self.workspace, "demo")
        self.assertEqual(len(first["documents"]), 1)
        self.assertEqual(len(second["documents"]), 1)
        self.assertEqual(second["documents"][0]["id"], first["documents"][0]["id"])

    def test_changed_source_is_versioned_and_search_uses_active_text(self):
        path = self.source / "notes.md"
        path.write_text("old design detail", encoding="utf-8")
        ingest(self.source, self.workspace, "demo")
        path.write_text("new design detail", encoding="utf-8")
        catalog = ingest(self.source, self.workspace, "demo")
        self.assertEqual(len(catalog["documents"]), 2)
        active = [doc for doc in catalog["documents"] if doc.get("active", True)]
        self.assertEqual(len(active), 1)
        self.assertEqual(search(self.workspace, "demo", "new design")[0]["text"], "new design detail")
        self.assertEqual(search(self.workspace, "demo", "old design"), [])
        course_root = self.workspace / "courses" / "demo"
        self.assertTrue(all((course_root / doc["source_copy"]).exists() for doc in catalog["documents"] if doc.get("source_copy")))

    def test_pdf_page_budget_and_image_only_status(self):
        from pypdf import PdfWriter

        pdf = self.source / "scanned.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=300, height=300)
        writer.add_blank_page(width=300, height=300)
        with pdf.open("wb") as handle:
            writer.write(handle)
        catalog = ingest(self.source, self.workspace, "demo", max_pdf_pages=1)
        document = catalog["documents"][0]
        self.assertEqual(document["pages_total"], 2)
        self.assertEqual(document["pages_processed"], 1)
        self.assertEqual(document["status"], "needs_ocr")
        self.assertEqual(document["needs_ocr_pages"], [1])
        self.assertTrue(document["truncated"])
        manifest_path = self.workspace / "courses" / "demo" / document["ocr_review_path"]
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["source_sha256"], document["sha256"])
        self.assertEqual(manifest["pending"], [{"locator": "page:1", "status": "unreviewed"}])
        self.assertEqual(manifest["execution"], "not_performed")

    def test_image_ingestion_is_bounded_and_fails_closed_for_ocr(self):
        from PIL import Image

        image_path = self.source / "assignment.png"
        Image.new("RGB", (40, 20), "white").save(image_path)
        original_hash = hashlib.sha256(image_path.read_bytes()).hexdigest()

        catalog = ingest(self.source, self.workspace, "demo")
        document = catalog["documents"][0]
        self.assertEqual(document["kind"], "image")
        self.assertEqual(document["status"], "needs_ocr")
        self.assertEqual(document["sha256"], original_hash)
        self.assertEqual(document["blocks"], [])
        self.assertEqual(document["image_dimensions"], [{"frame": 1, "width": 40, "height": 20}])
        self.assertEqual(document["needs_ocr_pages"], [1])
        self.assertEqual(image_path.read_bytes(), (self.workspace / "courses" / "demo" / document["source_copy"]).read_bytes())

        pending = ocr_status(self.workspace, "demo")
        self.assertEqual(pending["status"], "ocr_required")
        self.assertEqual(pending["pending_count"], 1)
        self.assertEqual(pending["documents"][0]["document_id"], document["id"])
        self.assertEqual(pending["local_engine"]["execution"], "not_performed")

        direct = extract_source_blocks(image_path)
        self.assertEqual(direct["status"], "needs_ocr")
        self.assertEqual(direct["blocks"], [])

    def test_pdf_with_native_text_and_blank_page_remains_unresolved(self):
        from pypdf import PdfReader, PdfWriter
        from reportlab.pdfgen.canvas import Canvas

        buffer = BytesIO()
        canvas = Canvas(buffer, pagesize=(300, 300))
        canvas.drawString(20, 280, "Native assignment instructions")
        canvas.save()
        writer = PdfWriter()
        writer.add_page(PdfReader(buffer).pages[0])
        writer.add_blank_page(width=300, height=300)
        pdf = self.source / "mixed.pdf"
        with pdf.open("wb") as handle:
            writer.write(handle)

        document = ingest(self.source, self.workspace, "demo")["documents"][0]
        self.assertEqual(document["status"], "needs_ocr")
        self.assertEqual(document["needs_ocr_pages"], [2])
        self.assertEqual(document["blocks"][0]["locator"], "page:1")
        self.assertEqual(search(self.workspace, "demo", "Native assignment")[0]["locator"], "page:1")
        manifest = json.loads(
            (self.workspace / "courses" / "demo" / document["ocr_review_path"]).read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["pending"], [{"locator": "page:2", "status": "unreviewed"}])

    def test_complete_ocr_import_preserves_native_blocks_and_requires_separate_review(self):
        from pypdf import PdfReader, PdfWriter
        from reportlab.pdfgen.canvas import Canvas

        buffer = BytesIO()
        canvas = Canvas(buffer, pagesize=(300, 300))
        canvas.drawString(20, 280, "Native heat transfer instructions")
        canvas.save()
        writer = PdfWriter()
        writer.add_page(PdfReader(buffer).pages[0])
        writer.add_blank_page(width=300, height=300)
        pdf = self.source / "mixed.pdf"
        with pdf.open("wb") as handle:
            writer.write(handle)
        document = ingest(self.source, self.workspace, "demo")["documents"][0]
        native_block = dict(document["blocks"][0])
        transcription = self._transcription(
            document,
            [{"locator": "page:2", "text": "Calculate the convection coefficient."}],
        )

        result = import_ocr_transcription(self.workspace, "demo", transcription)
        self.assertEqual(result["status"], "extracted")
        self.assertEqual(result["native_blocks_preserved"], 1)
        self.assertFalse(result["idempotent"])
        completed = self._catalog()["documents"][0]
        self.assertEqual(completed["status"], "extracted")
        self.assertEqual(completed["blocks"][0], native_block)
        self.assertEqual(completed["blocks"][1]["locator"], "page:2")
        self.assertEqual(completed["blocks"][1]["origin"], "ocr_import")
        self.assertEqual(completed["ocr_import"]["review_status"], "unreviewed")
        stored_path = self.workspace / "courses" / "demo" / completed["ocr_import"]["path"]
        self.assertTrue(stored_path.is_file())
        self.assertEqual(hashlib.sha256(stored_path.read_bytes()).hexdigest(), completed["ocr_import"]["file_sha256"])
        result = search(self.workspace, "demo", "convection coefficient")[0]
        self.assertEqual(result["review_status"], "unreviewed")
        review_evidence(
            self.workspace,
            "demo",
            result["document_id"],
            result["locator"],
            "Compared the imported text against page 2 of the source PDF.",
        )
        self.assertEqual(search(self.workspace, "demo", "convection coefficient")[0]["review_status"], "reviewed")
        self.assertEqual(ocr_status(self.workspace, "demo")["status"], "clear")

    def test_ocr_import_rejects_bad_coverage_stale_hash_blank_text_and_truncation(self):
        from PIL import Image
        from pypdf import PdfWriter

        image_path = self.source / "assignment.png"
        Image.new("RGB", (40, 20), "white").save(image_path)
        document = ingest(self.source, self.workspace, "demo")["documents"][0]
        valid = self._transcription(document, [{"locator": "image:1", "text": "Solve part A."}])

        stale = dict(valid)
        stale["source_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "source hash is stale"):
            import_ocr_transcription(self.workspace, "demo", stale)
        missing = dict(valid)
        missing["blocks"] = []
        with self.assertRaisesRegex(ValueError, "cover every pending locator"):
            import_ocr_transcription(self.workspace, "demo", missing)
        extra = dict(valid)
        extra["blocks"] = [*valid["blocks"], {"locator": "image:2", "text": "Extra"}]
        with self.assertRaisesRegex(ValueError, "cover every pending locator"):
            import_ocr_transcription(self.workspace, "demo", extra)
        duplicate = dict(valid)
        duplicate["blocks"] = [valid["blocks"][0], dict(valid["blocks"][0])]
        with self.assertRaisesRegex(ValueError, "duplicate OCR locator"):
            import_ocr_transcription(self.workspace, "demo", duplicate)
        blank = dict(valid)
        blank["blocks"] = [{"locator": "image:1", "text": "  "}]
        with self.assertRaisesRegex(ValueError, "blank or invalid"):
            import_ocr_transcription(self.workspace, "demo", blank)

        truncated_source = self.root / "truncated"
        truncated_source.mkdir()
        pdf = truncated_source / "two-pages.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=300, height=300)
        writer.add_blank_page(width=300, height=300)
        with pdf.open("wb") as handle:
            writer.write(handle)
        truncated_document = ingest(pdf, self.workspace, "truncated", max_pdf_pages=1)["documents"][0]
        truncated_import = self._transcription(
            truncated_document,
            [{"locator": "page:1", "text": "Only one processed page."}],
        )
        with self.assertRaisesRegex(ValueError, "partial or truncated"):
            import_ocr_transcription(self.workspace, "truncated", truncated_import)

    def test_ocr_import_is_idempotent_and_rejects_overwrite_or_unsafe_input_file(self):
        from PIL import Image

        image_path = self.source / "assignment.png"
        Image.new("RGB", (40, 20), "white").save(image_path)
        document = ingest(self.source, self.workspace, "demo")["documents"][0]
        transcription = self._transcription(
            document,
            [{"locator": "image:1", "text": "Determine the required area."}],
        )
        first = import_ocr_transcription(self.workspace, "demo", transcription)
        second = import_ocr_transcription(self.workspace, "demo", transcription)
        self.assertFalse(first["idempotent"])
        self.assertTrue(second["idempotent"])
        changed = self._transcription(
            document,
            [{"locator": "image:1", "text": "Changed transcription."}],
        )
        with self.assertRaisesRegex(ValueError, "cannot be overwritten"):
            import_ocr_transcription(self.workspace, "demo", changed)

        json_path = self.root / "transcription.json"
        json_path.write_text(json.dumps(transcription), encoding="utf-8")
        symlink_path = self.root / "linked.json"
        try:
            os.symlink(json_path, symlink_path)
        except OSError as exc:
            self.skipTest(f"symlink unavailable: {exc}")
        with self.assertRaisesRegex(ValueError, "permitted regular file"):
            _json_input(symlink_path)

    def test_ocr_import_cli_accepts_bounded_json_file(self):
        from PIL import Image

        image_path = self.source / "assignment.png"
        Image.new("RGB", (40, 20), "white").save(image_path)
        document = ingest(self.source, self.workspace, "demo")["documents"][0]
        transcription_path = self.root / "transcription.json"
        transcription_path.write_text(
            json.dumps(
                self._transcription(
                    document,
                    [{"locator": "image:1", "text": "State the energy balance."}],
                )
            ),
            encoding="utf-8",
        )
        output = StringIO()
        with redirect_stdout(output):
            result = main(
                [
                    "--workspace",
                    str(self.workspace),
                    "ocr-import",
                    str(transcription_path),
                    "--course",
                    "demo",
                ]
            )
        self.assertEqual(result, 0)
        self.assertEqual(json.loads(output.getvalue())["status"], "extracted")

    def test_secret_symlink_and_alias_files_are_never_cataloged(self):
        (self.source / ".env.local").write_text("private", encoding="utf-8")
        (self.source / "api-token.txt").write_text("private", encoding="utf-8")
        (self.source / "~$locked.docx").write_text("lock", encoding="utf-8")
        (self.source / "shortcut.alias").write_text("alias", encoding="utf-8")
        outside = self.root / "outside.txt"
        outside.write_text("outside", encoding="utf-8")
        try:
            os.symlink(outside, self.source / "link.txt")
        except OSError as exc:
            self.skipTest(f"symlink unavailable: {exc}")
        (self.source / "good.txt").write_text("safe", encoding="utf-8")
        catalog = ingest(self.source, self.workspace, "demo")
        self.assertEqual([doc["relative_path"] for doc in catalog["documents"]], ["good.txt"])
        self.assertGreaterEqual(catalog["skipped"].get("secret_or_hidden", 0), 2)
        self.assertEqual(catalog["skipped"].get("symlink"), 1)

    def test_unsupported_files_are_visible_without_execution(self):
        executable = self.source / "program.py"
        executable.write_text("raise RuntimeError('must not run')", encoding="utf-8")
        catalog = ingest(self.source, self.workspace, "demo")
        self.assertEqual(len(catalog["documents"]), 1)
        document = catalog["documents"][0]
        self.assertEqual(document["status"], "unsupported")
        self.assertEqual(document["kind"], "unsupported")
        self.assertEqual(document["size_bytes"], executable.stat().st_size)
        self.assertEqual(document["sha256"], hashlib.sha256(executable.read_bytes()).hexdigest())

    def test_syllabus_ai_section_requires_explicit_boundary(self):
        bounded = self.source / "course-syllabus.md"
        bounded.write_text(
            "# Course\n\n## AI Policy\nDo not include this policy.\n\n## Grading\nTechnical grading details.\n",
            encoding="utf-8",
        )
        catalog = ingest(self.source, self.workspace, "demo")
        document = catalog["documents"][0]
        text = "\n".join(block["text"] for block in document["blocks"])
        self.assertNotIn("Do not include this policy", text)
        self.assertIn("Technical grading details", text)
        self.assertEqual(document["exclusion"]["status"], "applied")

        ambiguous_source = self.root / "ambiguous"
        ambiguous_source.mkdir()
        (ambiguous_source / "syllabus.md").write_text("# AI Policy\nPolicy text\n", encoding="utf-8")
        ambiguous = ingest(ambiguous_source, self.workspace, "ambiguous")
        ambiguous_document = ambiguous["documents"][0]
        self.assertEqual(ambiguous_document["exclusion"]["status"], "ambiguous")
        self.assertIn("Policy text", "\n".join(block["text"] for block in ambiguous_document["blocks"]))

    def test_search_is_course_scoped_and_returns_locators(self):
        (self.source / "one.md").write_text("shared term", encoding="utf-8")
        ingest(self.source, self.workspace, "demo")
        other = self.root / "other"
        other.mkdir()
        (other / "two.md").write_text("shared term", encoding="utf-8")
        ingest(other, self.workspace, "other")
        result = search(self.workspace, "demo", "shared")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["relative_path"], "one.md")
        self.assertEqual(result[0]["locator"], "line:1")
        self.assertEqual(result[0]["review_status"], "unreviewed")
        review_evidence(self.workspace,"demo",result[0]["document_id"],result[0]["locator"],"Reviewed the exact source line in context.")
        self.assertEqual(search(self.workspace,"demo","shared")[0]["review_status"],"reviewed")
        self.assertEqual(search(self.workspace, "demo", "missing"), [])


class AutomaticOcrTests(unittest.TestCase):
    """The optional Tesseract adapter.

    Every branch below runs with an injected probe and runner, so the whole
    class passes on a machine (and a CI runner) with no OCR engine installed.
    The one test that needs a real engine is skipped when it is absent.
    """

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.source = self.root / "sources"
        self.workspace = self.root / "workspace"
        self.source.mkdir()

    def tearDown(self):
        self.tempdir.cleanup()

    def _catalog_bytes(self):
        return (self.workspace / "courses" / "demo" / "catalog.json").read_bytes()

    def _catalog(self):
        return json.loads(self._catalog_bytes().decode("utf-8"))

    def _png(self, name="assignment.png"):
        """A synthetic image. Never a scan of real coursework."""
        from PIL import Image

        path = self.source / name
        Image.new("RGB", (40, 20), "white").save(path)
        return path

    def _two_frame_tiff(self, name="pages.tif"):
        from PIL import Image

        path = self.source / name
        first = Image.new("RGB", (40, 20), "white")
        second = Image.new("RGB", (40, 20), "white")
        first.save(path, save_all=True, append_images=[second])
        return path

    def _runner(self, mapping):
        """A fake engine. `mapping` is frame number -> text, or an exception."""
        calls = []

        def run(image_path):
            frame = int(Path(image_path).stem.rsplit("-", 1)[1])
            calls.append(frame)
            value = mapping[frame]
            if isinstance(value, BaseException):
                raise value
            return value

        run.calls = calls
        return run

    @staticmethod
    def _present():
        return "/usr/bin/tesseract"

    @staticmethod
    def _absent():
        return None

    # -- no engine installed -------------------------------------------------

    def test_automatic_ocr_without_an_engine_fails_closed_and_changes_nothing(self):
        self._png()
        document = ingest(self.source, self.workspace, "demo")["documents"][0]
        manifest_path = self.workspace / "courses" / "demo" / document["ocr_review_path"]
        catalog_before = self._catalog_bytes()
        manifest_before = manifest_path.read_bytes()
        runner = self._runner({})

        result = auto_ocr_document(
            self.workspace, "demo", document["id"], probe=self._absent, runner=runner
        )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "engine_unavailable")
        self.assertFalse(result["imported"])
        self.assertFalse(result["engine"]["available"])
        self.assertEqual(result["engine"]["execution"], "not_performed")
        self.assertIn("tesseract", result["warning"])
        self.assertEqual(runner.calls, [])
        # Fail closed means the queue entry is left exactly as ingest wrote it.
        self.assertEqual(self._catalog_bytes(), catalog_before)
        self.assertEqual(manifest_path.read_bytes(), manifest_before)
        self.assertEqual(self._catalog()["documents"][0]["status"], "needs_ocr")
        self.assertEqual(ocr_status(self.workspace, "demo")["status"], "ocr_required")
        self.assertFalse((self.workspace / "courses" / "demo" / "ocr-imports").exists())

    # -- the engine succeeds -------------------------------------------------

    def test_automatic_ocr_imports_unreviewed_and_preserves_source_hash_and_locators(self):
        image_path = self._png()
        original_hash = hashlib.sha256(image_path.read_bytes()).hexdigest()
        document = ingest(self.source, self.workspace, "demo")["documents"][0]
        source_copy = self.workspace / "courses" / "demo" / document["source_copy"]
        runner = self._runner({1: "Determine the steady-state heat flux.\n"})

        result = auto_ocr_document(
            self.workspace, "demo", document["id"], probe=self._present, runner=runner
        )

        self.assertTrue(result["imported"])
        self.assertTrue(result["automatic"])
        self.assertEqual(result["status"], "extracted")
        self.assertEqual(result["locators"], ["image:1"])
        self.assertEqual(result["engine"]["execution"], "performed")
        self.assertEqual(runner.calls, [1])

        completed = self._catalog()["documents"][0]
        # Hashes and locators are preserved exactly as the manual import does.
        self.assertEqual(completed["sha256"], original_hash)
        self.assertEqual(completed["status"], "extracted")
        self.assertEqual(completed["needs_ocr_pages"], [])
        self.assertEqual(len(completed["blocks"]), 1)
        block = completed["blocks"][0]
        self.assertEqual(block["locator"], "image:1")
        self.assertEqual(block["origin"], "ocr_import")
        self.assertEqual(block["text"], "Determine the steady-state heat flux.")
        self.assertEqual(
            block["text_sha256"], hashlib.sha256(block["text"].encode("utf-8")).hexdigest()
        )
        # The source itself is never rewritten by an OCR pass.
        self.assertEqual(source_copy.read_bytes(), image_path.read_bytes())
        self.assertEqual(hashlib.sha256(source_copy.read_bytes()).hexdigest(), original_hash)

        import_record = completed["ocr_import"]
        self.assertEqual(import_record["review_status"], "unreviewed")
        self.assertEqual(import_record["source_sha256"], original_hash)
        self.assertEqual(import_record["provenance"]["method"], "automatic_ocr")
        self.assertEqual(import_record["provenance"]["tool"], "tesseract")
        self.assertEqual(completed["ocr_review"]["status"], "transcription_imported")
        self.assertEqual(completed["ocr_review"]["execution"], "external_import")
        self.assertEqual(
            completed["ocr_review"]["pending"][0]["status"], "transcribed_unreviewed"
        )
        self.assertEqual(ocr_status(self.workspace, "demo")["status"], "clear")

    def test_automatic_ocr_output_is_never_treated_as_reviewed_evidence(self):
        """OCR is not review.

        This is the load-bearing guarantee of the whole adapter: text a machine
        read off an image must stay unreviewed until a person records an exact
        visual comparison against the source.  If a change ever lets automatic
        OCR produce reviewed evidence on its own, this test is what must stop it.
        """
        self._png()
        document = ingest(self.source, self.workspace, "demo")["documents"][0]
        runner = self._runner({1: "Determine the steady-state heat flux."})

        auto_ocr_document(
            self.workspace, "demo", document["id"], probe=self._present, runner=runner
        )

        completed = self._catalog()["documents"][0]
        block = completed["blocks"][0]
        self.assertEqual(
            evidence_review_status(
                self.workspace,
                "demo",
                completed["id"],
                completed["sha256"],
                block["locator"],
                block["text_sha256"],
            ),
            "unreviewed",
        )
        # The adapter must not have written into the evidence review registry.
        self.assertFalse((self.workspace / "courses" / "demo" / "reviews.json").exists())
        self.assertEqual(completed["ocr_import"]["review_status"], "unreviewed")
        hit = search(self.workspace, "demo", "steady-state heat flux")[0]
        self.assertEqual(hit["review_status"], "unreviewed")

        # An explicit human visual review is the only thing that changes this.
        review_evidence(
            self.workspace,
            "demo",
            hit["document_id"],
            hit["locator"],
            "Compared the OCR text character by character against the source image.",
        )
        self.assertEqual(
            search(self.workspace, "demo", "steady-state heat flux")[0]["review_status"],
            "reviewed",
        )

    # -- the engine runs but does not produce usable text --------------------

    def test_automatic_ocr_fails_closed_when_the_engine_reads_one_page_as_blank(self):
        self._two_frame_tiff()
        document = ingest(self.source, self.workspace, "demo")["documents"][0]
        self.assertEqual(document["needs_ocr_pages"], [1, 2])
        catalog_before = self._catalog_bytes()
        # What a real Tesseract does to a low-contrast scan: whitespace.
        runner = self._runner({1: "Readable first page.", 2: "   \n  \n"})

        result = auto_ocr_document(
            self.workspace, "demo", document["id"], probe=self._present, runner=runner
        )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "blank_transcription")
        self.assertFalse(result["imported"])
        self.assertIn("image:2", result["warning"])
        self.assertEqual(result["engine"]["execution"], "attempted")
        # Nothing partial is kept: the readable page is not imported either.
        self.assertEqual(self._catalog_bytes(), catalog_before)
        self.assertEqual(self._catalog()["documents"][0]["status"], "needs_ocr")
        self.assertFalse((self.workspace / "courses" / "demo" / "ocr-imports").exists())
        self.assertEqual(ocr_status(self.workspace, "demo")["status"], "ocr_required")

    def test_automatic_ocr_fails_closed_when_the_engine_errors(self):
        self._png()
        document = ingest(self.source, self.workspace, "demo")["documents"][0]
        catalog_before = self._catalog_bytes()
        runner = self._runner({1: OcrError("engine_failed", "OCR engine exited with status 1")})

        result = auto_ocr_document(
            self.workspace, "demo", document["id"], probe=self._present, runner=runner
        )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "engine_failed")
        self.assertFalse(result["imported"])
        self.assertEqual(self._catalog_bytes(), catalog_before)
        self.assertEqual(self._catalog()["documents"][0]["status"], "needs_ocr")

    def test_ocr_runner_is_bounded_and_reports_failure_rather_than_empty_text(self):
        image_path = self._png()

        failing_script = self.root / "failing-engine.sh"
        failing_script.write_text("#!/bin/sh\necho 'engine broke' >&2\nexit 3\n", encoding="utf-8")
        failing_script.chmod(0o700)
        with self.assertRaises(OcrError) as failed:
            build_runner(str(failing_script))(image_path)
        self.assertEqual(failed.exception.reason, "engine_failed")
        self.assertIn("status 3", failed.exception.message)

        missing = build_runner(str(self.root / "no-such-ocr-binary"))
        with self.assertRaises(OcrError) as absent:
            missing(image_path)
        self.assertEqual(absent.exception.reason, "engine_failed")

        slow = self.root / "slow-engine.sh"
        slow.write_text("#!/bin/sh\nsleep 5\n", encoding="utf-8")
        slow.chmod(0o700)
        with self.assertRaises(OcrError) as timed_out:
            build_runner(str(slow), timeout=0.5)(image_path)
        self.assertEqual(timed_out.exception.reason, "engine_timeout")

    # -- sources the adapter declines ----------------------------------------

    def test_automatic_ocr_without_a_rasterizer_leaves_the_manual_pdf_queue_usable(self):
        """PDFs are supported now, but only when a rasterizer is installed.

        This test previously asserted that PDF sources were declined outright.
        Automatic PDF OCR is now supported (see tests/test_pdf_ocr.py); what
        still has to hold is the half this test was really protecting: when the
        automatic path cannot run, the manual transcription path is untouched.
        """
        from engineering_assistant import ocr as ocr_module
        from pypdf import PdfWriter

        writer = PdfWriter()
        writer.add_blank_page(width=300, height=300)
        with (self.source / "scanned.pdf").open("wb") as handle:
            writer.write(handle)
        document = ingest(self.source, self.workspace, "demo")["documents"][0]
        self.assertEqual(document["kind"], "pdf")
        catalog_before = self._catalog_bytes()
        runner = self._runner({})

        with mock.patch.object(ocr_module, "_pdfium", None):
            result = auto_ocr_document(
                self.workspace, "demo", document["id"], probe=self._present, runner=runner
            )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "rasterizer_unavailable")
        self.assertFalse(result["imported"])
        self.assertEqual(runner.calls, [])
        self.assertEqual(self._catalog_bytes(), catalog_before)

        # Failing closed must not disturb the manual path for PDFs.
        manual = import_ocr_transcription(
            self.workspace,
            "demo",
            {
                "schema_version": 1,
                "document_id": document["id"],
                "source_sha256": document["sha256"],
                "provenance": {"method": "manual_transcription", "tool": "visual review"},
                "blocks": [{"locator": "page:1", "text": "Transcribed by hand."}],
            },
        )
        self.assertEqual(manual["status"], "extracted")
        self.assertEqual(self._catalog()["documents"][0]["ocr_import"]["review_status"], "unreviewed")

    def test_automatic_ocr_declines_a_source_truncated_at_ingest(self):
        self._two_frame_tiff()
        document = ingest(self.source, self.workspace, "demo", max_pdf_pages=1)["documents"][0]
        self.assertTrue(document["truncated"])
        catalog_before = self._catalog_bytes()
        runner = self._runner({1: "Readable page."})

        result = auto_ocr_document(
            self.workspace, "demo", document["id"], probe=self._present, runner=runner
        )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "source_truncated")
        self.assertIn("re-ingest", result["warning"])
        # The engine is never run for a source that could not accept the result.
        self.assertEqual(runner.calls, [])
        self.assertEqual(self._catalog_bytes(), catalog_before)

    def test_automatic_ocr_is_not_rerun_once_a_transcription_exists(self):
        self._png()
        document = ingest(self.source, self.workspace, "demo")["documents"][0]
        runner = self._runner({1: "Determine the steady-state heat flux."})

        first = auto_ocr_document(
            self.workspace, "demo", document["id"], probe=self._present, runner=runner
        )
        self.assertTrue(first["imported"])
        catalog_after_first = self._catalog_bytes()

        second = auto_ocr_document(
            self.workspace, "demo", document["id"], probe=self._present, runner=runner
        )
        self.assertEqual(second["status"], "blocked")
        self.assertEqual(second["reason"], "already_transcribed")
        self.assertFalse(second["imported"])
        self.assertEqual(runner.calls, [1])
        self.assertEqual(self._catalog_bytes(), catalog_after_first)

    def test_automatic_ocr_rejects_an_unknown_document_and_a_malformed_id(self):
        self._png()
        ingest(self.source, self.workspace, "demo")
        missing = auto_ocr_document(
            self.workspace, "demo", "0" * 20, probe=self._present, runner=self._runner({})
        )
        self.assertEqual(missing["reason"], "document_missing")
        self.assertFalse(missing["imported"])
        with self.assertRaises(ValueError):
            auto_ocr_document(self.workspace, "demo", "not-a-document-id")

    # -- one real-engine check, skipped wherever Tesseract is absent ---------

    @unittest.skipUnless(shutil.which("tesseract"), "no local tesseract engine installed")
    def test_automatic_ocr_against_a_real_local_engine(self):
        from PIL import Image, ImageDraw

        path = self.source / "printed.png"
        image = Image.new("RGB", (640, 160), "white")
        ImageDraw.Draw(image).text((20, 60), "HEAT TRANSFER", fill="black")
        image.save(path)
        document = ingest(self.source, self.workspace, "demo")["documents"][0]

        result = auto_ocr_document(self.workspace, "demo", document["id"])

        if result["status"] == "blocked":
            self.assertEqual(result["reason"], "blank_transcription")
            self.assertEqual(self._catalog()["documents"][0]["status"], "needs_ocr")
            return
        self.assertTrue(result["imported"])
        completed = self._catalog()["documents"][0]
        self.assertEqual(completed["blocks"][0]["origin"], "ocr_import")
        self.assertTrue(completed["blocks"][0]["text"].strip())
        self.assertEqual(completed["ocr_import"]["provenance"]["tool"], "tesseract")
        self.assertEqual(completed["ocr_import"]["review_status"], "unreviewed")
        self.assertFalse((self.workspace / "courses" / "demo" / "reviews.json").exists())


class HostileSourceTests(unittest.TestCase):
    """Malformed and hostile input reaching extract_source_blocks.

    Every fixture is generated here; nothing hostile is committed to the repo.
    These tests assert the bounded outcome this module guarantees, never an
    exception type or an interpreter behavior: expat's entity-amplification
    limit differs between the Python versions CI runs, so a test leaning on it
    would pass locally and prove nothing about the runner.
    """

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.source = self.root / "sources"
        self.workspace = self.root / "workspace"
        self.source.mkdir()

    def tearDown(self):
        self.tempdir.cleanup()

    def _docx(self, name, xml):
        path = self.source / name
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("word/document.xml", xml)
        return path

    # -- encodings -----------------------------------------------------------

    def test_undecodable_encoding_fails_closed_with_a_specific_reason(self):
        path = self.source / "undecodable.txt"
        # Bytes that are neither valid UTF-8 nor defined in cp1252.
        path.write_bytes(b"valid start \x81\x8d\x8f\x90\x9d end\n")

        result = extract_source_blocks(path)

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["blocks"], [])
        self.assertIn("encoding could not be determined", result["reason"])

    def test_oversized_utf8_source_is_not_silently_decoded_as_mojibake(self):
        """A truncated multi-byte character must not corrupt the whole file.

        Cutting at the byte cap used to split a UTF-8 sequence, fail the UTF-8
        decode, and fall back to cp1252 for *the entire file* - returning text
        in which every character was wrong while still reporting success.
        """
        path = self.source / "large.txt"
        path.write_bytes("€".encode("utf-8") * ((MAX_TEXT_BYTES // 3) + 10))

        text, truncated = _decode_text(path)

        self.assertTrue(truncated)
        self.assertTrue(text.startswith("€€€"))
        # The mojibake signature of a cp1252 re-decode.
        self.assertNotIn("â", text)
        self.assertEqual(set(text), {"€"})

        # The same cut against a two-byte character at the boundary.
        mixed = self.source / "mixed.txt"
        mixed.write_bytes(b"A" * (MAX_TEXT_BYTES - 1) + "é".encode("utf-8") + b"BB")
        text2, truncated2 = _decode_text(mixed)
        self.assertTrue(truncated2)
        self.assertEqual(set(text2), {"A"})

        # A four-byte character ending exactly at the cap is complete and must
        # survive: the boundary trim must not eat a character that was not cut.
        quad = self.source / "quad.txt"
        quad.write_bytes(b"A" * (MAX_TEXT_BYTES - 4) + "\U0001f4a9".encode("utf-8") + b"BB")
        text3, truncated3 = _decode_text(quad)
        self.assertTrue(truncated3)
        self.assertTrue(text3.endswith("\U0001f4a9"))

        # The same four-byte character cut in half must be dropped whole.
        cut = self.source / "cut.txt"
        cut.write_bytes(b"A" * (MAX_TEXT_BYTES - 2) + "\U0001f4a9".encode("utf-8"))
        text4, _ = _decode_text(cut)
        self.assertEqual(set(text4), {"A"})

    def test_utf16_source_is_named_rather_than_reported_as_binary(self):
        path = self.source / "utf16.txt"
        path.write_bytes("Design the heat exchanger.\n".encode("utf-16"))

        result = extract_source_blocks(path)

        self.assertEqual(result["status"], "error")
        self.assertIn("UTF-16", result["reason"])
        self.assertNotIn("binary content", result["reason"])

    def test_binary_content_is_still_rejected_as_binary(self):
        path = self.source / "binary.txt"
        path.write_bytes(b"text then \x00\x01\x02 binary\n")

        result = extract_source_blocks(path)

        self.assertEqual(result["status"], "error")
        self.assertIn("binary content", result["reason"])

    # -- text that misrepresents the page ------------------------------------

    def test_bidirectional_overrides_fail_closed_naming_codepoint_and_locator(self):
        path = self.source / "bidi.txt"
        path.write_text("Use ‮001 EULAV‬ here\n", encoding="utf-8")

        result = extract_source_blocks(path)

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["blocks"], [])
        self.assertIn("U+202E", result["reason"])
        self.assertIn("line:1", result["reason"])

    def test_every_bidirectional_override_and_isolate_is_rejected(self):
        for codepoint in (0x202A, 0x202B, 0x202C, 0x202D, 0x202E, 0x2066, 0x2067, 0x2068, 0x2069):
            with self.subTest(codepoint=f"U+{codepoint:04X}"):
                path = self.source / f"bidi-{codepoint:04x}.txt"
                path.write_text(f"Specification{chr(codepoint)}value\n", encoding="utf-8")
                result = extract_source_blocks(path)
                self.assertEqual(result["status"], "error")
                self.assertIn(f"U+{codepoint:04X}", result["reason"])

    def test_benign_invisible_characters_are_preserved(self):
        """Zero-width spaces and soft hyphens are common in real PDFs.

        They do not reorder text, so rejecting them would make ordinary
        coursework un-ingestible for no safety gain.
        """
        path = self.source / "benign.txt"
        path.write_text("zero​width and soft­hyphen\n", encoding="utf-8")

        result = extract_source_blocks(path)

        self.assertEqual(result["status"], "extracted")
        self.assertEqual(result["blocks"][0]["text"], "zero​width and soft­hyphen")

    def test_a_bidi_source_is_recorded_as_an_error_and_never_becomes_evidence(self):
        (self.source / "bidi.txt").write_text("Limit ‮001‬ MPa\n", encoding="utf-8")

        document = ingest(self.source, self.workspace, "demo")["documents"][0]

        self.assertEqual(document["status"], "error")
        self.assertEqual(document["blocks"], [])
        self.assertIn("U+202E", document["error"])
        self.assertEqual(search(self.workspace, "demo", "MPa"), [])

    def test_ocr_import_rejects_bidirectional_overrides(self):
        from PIL import Image

        Image.new("RGB", (40, 20), "white").save(self.source / "scan.png")
        document = ingest(self.source, self.workspace, "demo")["documents"][0]

        with self.assertRaises(ValueError) as rejected:
            import_ocr_transcription(
                self.workspace,
                "demo",
                {
                    "schema_version": 1,
                    "document_id": document["id"],
                    "source_sha256": document["sha256"],
                    "provenance": {"method": "manual_transcription", "tool": "visual review"},
                    "blocks": [{"locator": "image:1", "text": "Limit ‮001‬ MPa"}],
                },
            )
        self.assertIn("U+202E", str(rejected.exception))
        self.assertEqual(self._active(document["id"])["status"], "needs_ocr")

    def _active(self, document_id):
        catalog = json.loads(
            (self.workspace / "courses" / "demo" / "catalog.json").read_text(encoding="utf-8")
        )
        return next(item for item in catalog["documents"] if item["id"] == document_id)

    # -- absurd block counts and sizes ---------------------------------------

    def test_absurd_block_count_is_bounded_and_marked_truncated(self):
        path = self.source / "manylines.txt"
        path.write_bytes(b"line\n" * (MAX_BLOCKS + 5_000))

        result = extract_source_blocks(path)

        self.assertEqual(len(result["blocks"]), MAX_BLOCKS)
        self.assertTrue(result["truncated"])
        self.assertEqual(result["status"], "partial")

    def test_absurd_block_size_is_dropped_rather_than_silently_shortened(self):
        path = self.source / "oneline.txt"
        path.write_bytes(b"A" * (MAX_BLOCK_CHARS + 5_000))

        result = extract_source_blocks(path)

        # Shortening the text would misrepresent the page, so the block is
        # dropped and the document is marked incomplete instead.
        self.assertEqual(result["blocks"], [])
        self.assertTrue(result["truncated"])
        self.assertEqual(result["status"], "partial")

    def test_bounded_blocks_keep_short_neighbours_and_drop_only_the_oversized(self):
        path = self.source / "mixed-lengths.txt"
        path.write_bytes(b"short one\n" + b"B" * (MAX_BLOCK_CHARS + 10) + b"\nshort two\n")

        result = extract_source_blocks(path)

        self.assertEqual([block["text"] for block in result["blocks"]], ["short one", "short two"])
        self.assertTrue(result["truncated"])

    def test_a_bounded_source_is_recorded_as_partial_and_truncated(self):
        (self.source / "manylines.txt").write_bytes(b"line\n" * (MAX_BLOCKS + 100))

        document = ingest(self.source, self.workspace, "demo")["documents"][0]

        # `truncated` is the flag the rest of the contract already keys on:
        # a truncated source can never be accepted as a complete transcription.
        self.assertTrue(document["truncated"])
        self.assertEqual(document["status"], "partial")
        self.assertEqual(len(document["blocks"]), MAX_BLOCKS)

    def test_spreadsheet_and_document_rows_inherit_the_same_bound(self):
        from openpyxl import Workbook

        workbook = Workbook()
        sheet = workbook.active
        for row in range(MAX_BLOCKS + 500):
            sheet.cell(row=row + 1, column=1, value=f"row {row}")
        workbook.save(self.source / "big.xlsx")

        paragraphs = "".join(
            f"<w:p><w:t>paragraph {index}</w:t></w:p>" for index in range(MAX_BLOCKS + 500)
        )
        self._docx(
            "big.docx",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            + paragraphs
            + "</w:document>",
        )

        for name in ("big.xlsx", "big.docx"):
            with self.subTest(source=name):
                result = extract_source_blocks(self.source / name)
                self.assertEqual(len(result["blocks"]), MAX_BLOCKS)
                self.assertTrue(result["truncated"])
                self.assertEqual(result["status"], "partial")

    # -- container decompression bounds --------------------------------------

    def _deflated(self, name, members):
        """A compressed container, built here so no hostile binary is committed."""
        path = self.source / name
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for member, data in members.items():
                archive.writestr(member, data)
        return path

    def _oversized_xml(self, tag):
        """XML one chunk past the member bound, from a small compressed source."""
        filler = "A" * (MAX_ARCHIVE_MEMBER_BYTES + (1 << 20))
        return f"<{tag}>{filler}</{tag}>"

    def _workbook_members(self, extra=None):
        """A structurally complete workbook openpyxl will actually open.

        A stripped-down archive is rejected for a missing part before any
        member is read, which would make a container-bound test pass without
        ever exercising the bound.  Every relationship openpyxl resolves on
        the way to the strings table is present here.
        """
        spreadsheet = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        package = "http://schemas.openxmlformats.org/package/2006/relationships"
        document = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
        members = {
            "[Content_Types].xml": '<?xml version="1.0"?>'
            f'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
            "</Types>",
            "_rels/.rels": '<?xml version="1.0"?>'
            f'<Relationships xmlns="{package}">'
            f'<Relationship Id="rId1" Type="{document}/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>",
            "xl/workbook.xml": '<?xml version="1.0"?>'
            f'<workbook xmlns="{spreadsheet}" xmlns:r="{document}">'
            '<sheets><sheet name="S" sheetId="1" r:id="rId1"/></sheets></workbook>',
            "xl/_rels/workbook.xml.rels": '<?xml version="1.0"?>'
            f'<Relationships xmlns="{package}">'
            f'<Relationship Id="rId1" Type="{document}/worksheet" Target="worksheets/sheet1.xml"/>'
            f'<Relationship Id="rId2" Type="{document}/sharedStrings" Target="sharedStrings.xml"/>'
            "</Relationships>",
            "xl/worksheets/sheet1.xml": '<?xml version="1.0"?>'
            f'<worksheet xmlns="{spreadsheet}"><sheetData>'
            '<row r="1"><c r="A1" t="s"><v>0</v></c></row></sheetData></worksheet>',
            "xl/sharedStrings.xml": '<?xml version="1.0"?>'
            f'<sst xmlns="{spreadsheet}" count="1" uniqueCount="1"><si><t>cell</t></si></sst>',
        }
        members.update(extra or {})
        return members

    def _oversized_shared_strings(self):
        return (
            '<?xml version="1.0"?>'
            '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            f'count="1" uniqueCount="1"><si>{self._oversized_xml("t")}</si></sst>'
        )

    def test_docx_member_past_the_container_bound_is_refused_not_expanded(self):
        """The refusal must happen while reading, not after the text exists.

        Measured before this bound existed: a 199KB .docx expanded to 116MB of
        document.xml and returned a bounded-looking ``partial`` result, having
        already committed the memory.
        """
        body = self._oversized_xml("w:t")
        path = self._deflated(
            "bomb.docx",
            {
                "word/document.xml": '<?xml version="1.0"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                f"<w:p>{body}</w:p></w:document>"
            },
        )
        # The fixture is the attack: small on disk, enormous decompressed.
        self.assertLess(path.stat().st_size, MAX_ARCHIVE_MEMBER_BYTES // 100)

        result = extract_source_blocks(path)

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["blocks"], [])
        self.assertIn("container safety limit", result["reason"])
        self.assertIn("word/document.xml", result["reason"])

    def test_xlsx_shared_strings_past_the_container_bound_are_refused(self):
        """openpyxl's read_only mode streams rows but not the strings table.

        xl/sharedStrings.xml is materialized in full before the first row is
        yielded, so the block bounds never see it.  Measured before this bound
        existed: a 115KB .xlsx committed 229MB.
        """
        path = self._deflated(
            "bomb.xlsx",
            self._workbook_members(
                {"xl/sharedStrings.xml": self._oversized_shared_strings()}
            ),
        )
        self.assertLess(path.stat().st_size, MAX_ARCHIVE_MEMBER_BYTES // 100)

        result = extract_source_blocks(path)

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["blocks"], [])
        self.assertIn("container safety limit", result["reason"])
        self.assertIn("xl/sharedStrings.xml", result["reason"])

    def test_xlsm_is_bounded_by_the_same_container_limit_as_xlsx(self):
        """.xlsm shares the xlsx extraction path, so assert it rather than assume it."""
        path = self._deflated(
            "bomb.xlsm",
            self._workbook_members(
                {"xl/sharedStrings.xml": self._oversized_shared_strings()}
            ),
        )

        result = extract_source_blocks(path)

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["blocks"], [])
        self.assertIn("container safety limit", result["reason"])

    def test_many_small_members_are_bounded_in_aggregate(self):
        """No single member crosses the per-member bound; together they do."""
        member = "<x>" + "B" * (MAX_ARCHIVE_MEMBER_BYTES - 8) + "</x>"
        count = (MAX_ARCHIVE_TOTAL_BYTES // len(member)) + 2
        path = self._deflated(
            "aggregate.xlsx",
            self._workbook_members(
                {f"xl/filler{index}.xml": member for index in range(count)}
            ),
        )

        result = extract_source_blocks(path)

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["blocks"], [])
        self.assertIn("container safety limit", result["reason"])

    def test_understated_member_size_is_refused_rather_than_silently_truncated(self):
        """The bound counts decompressed bytes, never the declared size.

        A zip records each member's uncompressed size in a header its author
        controls, so a container can declare a small member and carry a large
        one.  Whatever the reading layer does with that mismatch, the outcome
        this module owns is a structured refusal and no blocks -- never a
        partial extraction presented as a complete one.
        """
        payload = (
            '<?xml version="1.0"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f"<w:p>{self._oversized_xml('w:t')}</w:p></w:document>"
        ).encode("utf-8")
        path = self._deflated("understated.docx", {"word/document.xml": payload})
        raw = path.read_bytes()
        honest = struct.pack("<I", len(payload))
        self.assertIn(honest, raw)
        # Understate the member in both the local header and the directory.
        path.write_bytes(raw.replace(honest, struct.pack("<I", 1024)))
        self.assertEqual(
            zipfile.ZipFile(path).getinfo("word/document.xml").file_size, 1024
        )

        result = extract_source_blocks(path)

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["blocks"], [])
        self.assertTrue(result["reason"])

    def test_a_member_inside_the_bound_is_not_re_amplified_by_parsing(self):
        """Bounding decompression alone does not bound memory.

        A member sized just under the per-member limit passes the container
        bound and is then handed to the XML parser.  Building the whole tree
        first re-amplifies it: 31MB of minimal paragraph markup parses into
        1.4 million elements, measured at 355MB allocated and 916MB RSS from
        a 77KB file -- a worse peak than the oversized member this bound
        rejects.  Parsing as the member decompresses keeps the peak tied to
        the blocks kept rather than the size of the member.

        Asserts allocation, because every observable output of this fixture
        is identical either way: it is bounded, truncated and partial whether
        the tree was streamed or built whole.
        """
        unit = "<w:p><w:t>x</w:t></w:p>"
        head = (
            '<?xml version="1.0"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        )
        body = unit * ((8 * 1024 * 1024) // len(unit))
        path = self._deflated("dense.docx", {"word/document.xml": head + body + "</w:document>"})
        del body
        # Well above what streaming needs, well below what building the whole
        # tree costs, so the guard is not sensitive to allocator details.
        budget = 48 * 1024 * 1024

        tracemalloc.start()
        try:
            result = extract_source_blocks(path)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()

        self.assertEqual(result["status"], "partial")
        self.assertTrue(result["truncated"])
        self.assertLess(peak, budget)

    def test_documents_within_the_container_bound_still_extract(self):
        """The bound must not refuse legitimate work.

        Sized from real documents: a .docx carrying MAX_BLOCKS paragraphs of
        ordinary prose measures 14.4MB of document.xml, well inside the bound.
        """
        paragraphs = "".join(
            f"<w:p><w:t>paragraph {index} of ordinary prose</w:t></w:p>"
            for index in range(1_000)
        )
        path = self._deflated(
            "ordinary.docx",
            {
                "word/document.xml": '<?xml version="1.0"?>'
                '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                + paragraphs
                + "</w:document>"
            },
        )

        result = extract_source_blocks(path)

        self.assertEqual(result["status"], "extracted")
        self.assertEqual(len(result["blocks"]), 1_000)
        self.assertFalse(result["truncated"])

    # -- malformed containers ------------------------------------------------

    def test_malformed_document_xml_returns_a_structured_error(self):
        path = self._docx("broken.docx", "<w:document><w:p><w:t>unclosed")

        result = extract_source_blocks(path)

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["blocks"], [])
        self.assertTrue(result["reason"])

    def test_entity_expansion_cannot_produce_an_unbounded_block(self):
        """Asserts our own bound, not the interpreter's.

        Some Python/expat builds refuse the document outright and others
        expand it; either way the result must be a bounded, honest one.
        """
        entities = "".join(
            f'<!ENTITY lol{index} "{"&lol%d;" % (index - 1) * 10}">' if index > 1
            else '<!ENTITY lol1 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">'
            for index in range(1, 7)
        )
        path = self._docx(
            "expansion.docx",
            '<?xml version="1.0"?><!DOCTYPE d [<!ENTITY lol "lol">' + entities + "]>"
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            "<w:p><w:t>&lol6;</w:t></w:p></w:document>",
        )

        result = extract_source_blocks(path)

        self.assertIn(result["status"], {"error", "partial", "extracted"})
        for block in result["blocks"]:
            self.assertLessEqual(len(block["text"]), MAX_BLOCK_CHARS)

    def test_corrupt_archive_and_corrupt_image_report_rather_than_raise(self):
        corrupt_docx = self.source / "corrupt.docx"
        corrupt_docx.write_bytes(b"this is not a zip archive at all")
        corrupt_image = self.source / "corrupt.png"
        corrupt_image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"garbage" * 10)
        corrupt_pdf = self.source / "corrupt.pdf"
        corrupt_pdf.write_bytes(b"%PDF-1.7\nnot really a pdf\n")

        for path in (corrupt_docx, corrupt_image, corrupt_pdf):
            with self.subTest(source=path.name):
                result = extract_source_blocks(path)
                self.assertEqual(result["status"], "error")
                self.assertEqual(result["blocks"], [])
                self.assertTrue(result["reason"])

    def test_extract_source_blocks_never_raises_on_any_hostile_fixture(self):
        """The unifying guarantee: a total function, whatever the input."""
        fixtures = {
            "undecodable.txt": b"\x81\x8d\x8f\x90\x9d",
            "utf16.txt": "text".encode("utf-16"),
            "binary.txt": b"a\x00b",
            "bidi.txt": "a‮b".encode("utf-8"),
            "empty.txt": b"",
            "corrupt.docx": b"not a zip",
            "corrupt.xlsx": b"not a zip either",
            "corrupt.pdf": b"%PDF-1.7 broken",
            "corrupt.png": b"\x89PNG\r\n\x1a\nbroken",
            "huge-line.txt": b"C" * (MAX_BLOCK_CHARS + 10),
        }
        for name, payload in fixtures.items():
            path = self.source / name
            path.write_bytes(payload)
            with self.subTest(source=name):
                result = extract_source_blocks(path)
                self.assertIn("status", result)
                self.assertIsInstance(result["blocks"], list)


if __name__ == "__main__":
    unittest.main()
