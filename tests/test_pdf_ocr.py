import importlib.util
import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from PIL import Image

from engineering_assistant import ocr
from engineering_assistant.evidence import evidence_review_status
from engineering_assistant.ingest import auto_ocr_document, ingest, ocr_status

HAVE_PYPDFIUM2 = importlib.util.find_spec("pypdfium2") is not None


class _FakePage:
    def __init__(self, size, rotation=0):
        self._size = size
        self._rotation = rotation

    def render(self, scale=1.0):
        width = max(int(self._size[0] * scale), 1)
        height = max(int(self._size[1] * scale), 1)
        if self._rotation in (90, 270):
            width, height = height, width
        return _FakeBitmap((width, height))


class _FakeBitmap:
    def __init__(self, size):
        self._size = size

    def to_pil(self):
        return Image.new("RGB", self._size, "white")


class _FakeRasterizer:
    """Stands in for pypdfium2 so every branch is testable without it installed."""

    def __init__(self, pages, *, open_error=None):
        self._pages = pages
        self._open_error = open_error
        self.closed = False

    def PdfDocument(self, path):  # noqa: N802 - mirrors the real API
        if self._open_error is not None:
            raise self._open_error
        return self

    def __len__(self):
        return len(self._pages)

    def __getitem__(self, index):
        return self._pages[index]

    def close(self):
        self.closed = True


class PdfOcrTests(unittest.TestCase):
    """Automatic OCR of scanned PDF pages.

    Every branch runs with an injected rasterizer and runner, so the class
    passes with neither pypdfium2 nor an OCR engine installed. The one test
    that needs the real rasterizer is skipped when it is absent.
    """

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.source = self.root / "sources"
        self.workspace = self.root / "workspace"
        self.source.mkdir()

    def tearDown(self):
        self.tempdir.cleanup()

    def _scanned_pdf(self, name="scan.pdf", pages=2, rotation=0):
        """A PDF carrying only images, so ingestion queues it for OCR."""
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas

        image = self.source / "_page.png"
        Image.new("RGB", (120, 80), "white").save(image)
        path = self.source / name
        pdf = canvas.Canvas(str(path), pagesize=letter)
        for _ in range(pages):
            if rotation:
                pdf.setPageRotation(rotation)
            pdf.drawImage(str(image), 40, 40, width=300, height=200)
            pdf.showPage()
        pdf.save()
        image.unlink()
        return path

    def _catalog_bytes(self):
        return (self.workspace / "courses" / "demo" / "catalog.json").read_bytes()

    def _catalog(self):
        return json.loads(self._catalog_bytes().decode("utf-8"))

    def _runner(self, mapping):
        calls = []

        def run(image_path):
            page = int(Path(image_path).stem.rsplit("-", 1)[1])
            calls.append(page)
            value = mapping[page]
            if isinstance(value, BaseException):
                raise value
            return value

        run.calls = calls
        return run

    @staticmethod
    def _present():
        return "/usr/bin/tesseract"

    def _queued(self):
        document = ingest(self.source, self.workspace, "demo")["documents"][0]
        self.assertEqual(document["status"], "needs_ocr", "fixture must queue for OCR")
        self.assertEqual(document["kind"], "pdf")
        return document

    # -- no rasterizer installed --------------------------------------------

    def test_pdf_without_a_rasterizer_fails_closed_and_changes_nothing(self):
        self._scanned_pdf()
        document = self._queued()
        before = self._catalog_bytes()
        runner = self._runner({})

        with mock.patch.object(ocr, "_pdfium", None):
            result = auto_ocr_document(
                self.workspace, "demo", document["id"], probe=self._present, runner=runner
            )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["reason"], "rasterizer_unavailable")
        self.assertFalse(result["imported"])
        self.assertIn("pypdfium2", result["warning"])
        self.assertEqual(runner.calls, [], "the engine must not run without a rasterizer")
        self.assertEqual(self._catalog_bytes(), before)
        self.assertEqual(ocr_status(self.workspace, "demo")["status"], "ocr_required")

    # -- the load-bearing guarantee -----------------------------------------

    def test_pdf_ocr_output_is_never_treated_as_reviewed_evidence(self):
        """OCR is not review, and rasterizing a page does not change that.

        Text a machine read off a rendered page must stay unreviewed until a
        person records an exact visual comparison against the source. If a
        change ever lets PDF OCR produce reviewed evidence on its own, this
        test is what must stop it.
        """
        self._scanned_pdf(pages=1)
        document = self._queued()
        raster = _FakeRasterizer([_FakePage((612, 792))])
        runner = self._runner({1: "Determine the steady-state heat flux."})

        auto_ocr_document(
            self.workspace, "demo", document["id"],
            probe=self._present, runner=runner, rasterizer=raster,
        )

        completed = self._catalog()["documents"][0]
        block = completed["blocks"][0]
        self.assertEqual(block["locator"], "page:1")
        self.assertEqual(
            evidence_review_status(
                self.workspace, "demo", completed["id"], completed["sha256"],
                block["locator"], block["text_sha256"],
            ),
            "unreviewed",
        )
        self.assertFalse((self.workspace / "courses" / "demo" / "reviews.json").exists())

    def test_every_pending_page_is_transcribed_with_a_page_locator(self):
        self._scanned_pdf(pages=2)
        document = self._queued()
        raster = _FakeRasterizer([_FakePage((612, 792)), _FakePage((612, 792))])
        runner = self._runner({1: "Page one text.", 2: "Page two text."})

        result = auto_ocr_document(
            self.workspace, "demo", document["id"],
            probe=self._present, runner=runner, rasterizer=raster,
        )

        self.assertTrue(result["imported"])
        self.assertEqual(result["locators"], ["page:1", "page:2"])
        self.assertEqual(result["engine"]["rasterizer"], "pypdfium2")
        self.assertEqual(result["engine"]["raster_dpi"], 200)
        self.assertEqual(self._catalog()["documents"][0]["status"], "extracted")

    # -- fail-closed branches ------------------------------------------------

    def test_a_blank_page_imports_nothing_at_all(self):
        """A partial transcription cannot satisfy all-or-nothing coverage."""
        self._scanned_pdf(pages=2)
        document = self._queued()
        before = self._catalog_bytes()
        raster = _FakeRasterizer([_FakePage((612, 792)), _FakePage((612, 792))])
        runner = self._runner({1: "Page one text.", 2: "   \n  "})

        result = auto_ocr_document(
            self.workspace, "demo", document["id"],
            probe=self._present, runner=runner, rasterizer=raster,
        )

        self.assertEqual(result["reason"], "blank_transcription")
        self.assertFalse(result["imported"])
        self.assertEqual(self._catalog_bytes(), before, "page 1 must not be imported alone")

    def test_a_page_over_the_pixel_cap_fails_closed(self):
        self._scanned_pdf(pages=1)
        document = self._queued()
        before = self._catalog_bytes()
        raster = _FakeRasterizer([_FakePage((9000, 9000))])
        runner = self._runner({1: "unreachable"})

        result = auto_ocr_document(
            self.workspace, "demo", document["id"],
            probe=self._present, runner=runner, rasterizer=raster,
        )

        self.assertEqual(result["reason"], "page_too_large")
        self.assertIn("lower dpi", result["warning"])
        self.assertEqual(runner.calls, [])
        self.assertEqual(self._catalog_bytes(), before)

    def test_an_unopenable_pdf_fails_closed(self):
        self._scanned_pdf(pages=1)
        document = self._queued()
        raster = _FakeRasterizer([], open_error=RuntimeError("damaged xref"))
        runner = self._runner({})

        result = auto_ocr_document(
            self.workspace, "demo", document["id"],
            probe=self._present, runner=runner, rasterizer=raster,
        )

        self.assertEqual(result["reason"], "pdf_unreadable")
        self.assertEqual(runner.calls, [])

    def test_a_missing_page_fails_closed(self):
        self._scanned_pdf(pages=2)
        document = self._queued()
        raster = _FakeRasterizer([_FakePage((612, 792))])  # document claims 2 pages
        runner = self._runner({1: "Page one text."})

        result = auto_ocr_document(
            self.workspace, "demo", document["id"],
            probe=self._present, runner=runner, rasterizer=raster,
        )

        self.assertEqual(result["reason"], "page_missing")
        self.assertFalse(result["imported"])

    def test_an_out_of_range_dpi_is_rejected(self):
        raster = _FakeRasterizer([_FakePage((612, 792))])
        for bad in (0, -1, 5000, 200.0, True):
            with self.assertRaises(ocr.OcrError) as caught:
                ocr.transcribe_pdf_pages(
                    Path("ignored.pdf"), [1], lambda p: "text", dpi=bad, rasterizer=raster
                )
            self.assertEqual(caught.exception.reason, "raster_dpi_invalid")

    def test_transcribe_pdf_pages_without_a_rasterizer_raises(self):
        with mock.patch.object(ocr, "_pdfium", None):
            with self.assertRaises(ocr.OcrError) as caught:
                ocr.transcribe_pdf_pages(Path("ignored.pdf"), [1], lambda p: "text")
        self.assertEqual(caught.exception.reason, "rasterizer_unavailable")

    # -- the real rasterizer -------------------------------------------------

    @unittest.skipUnless(HAVE_PYPDFIUM2, "pypdfium2 is not installed")
    def test_real_rasterizer_applies_the_page_rotation(self):
        """Rendering, rather than extracting XObjects, is the whole safety claim.

        A rotated page must rasterize to the orientation a reader sees. Pulling
        embedded images out of the page ignores the transform and would return
        portrait pixels for a landscape page.
        """
        from pypdf import PdfReader

        path = self._scanned_pdf(name="rotated.pdf", pages=1, rotation=90)
        page = PdfReader(str(path)).pages[0]
        self.assertEqual(page.get("/Rotate"), 90, "fixture must carry a page rotation")
        box = (round(float(page.mediabox.width)), round(float(page.mediabox.height)))

        captured = {}

        def runner(image_path):
            with Image.open(image_path) as image:
                captured["size"] = image.size
            return "text from the rendered page"

        blocks = ocr.transcribe_pdf_pages(path, [1], runner, dpi=72)

        self.assertEqual(blocks[0]["locator"], "page:1")
        # The rendered raster is the mediabox transposed, which is the /Rotate 90
        # transform actually applied. Extracting the embedded XObject instead
        # would return the image in its own orientation and ignore this entirely.
        self.assertEqual(captured["size"], (box[1], box[0]))
        self.assertNotEqual(captured["size"], box)

    @unittest.skipUnless(HAVE_PYPDFIUM2, "pypdfium2 is not installed")
    def test_real_rasterizer_honours_dpi(self):
        path = self._scanned_pdf(name="dpi.pdf", pages=1)
        sizes = {}

        def make_runner(key):
            def runner(image_path):
                with Image.open(image_path) as image:
                    sizes[key] = image.size
                return "text"
            return runner

        ocr.transcribe_pdf_pages(path, [1], make_runner(72), dpi=72)
        ocr.transcribe_pdf_pages(path, [1], make_runner(144), dpi=144)

        self.assertAlmostEqual(sizes[144][0] / sizes[72][0], 2.0, delta=0.02)


if __name__ == "__main__":
    unittest.main()
