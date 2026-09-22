"""Engine selection for automatic OCR, and provenance that names the engine that ran."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from engineering_assistant import ocr
from engineering_assistant.ingest import auto_ocr_document, ingest


class EngineSelectionTests(unittest.TestCase):
    def test_tesseract_is_preferred_when_its_binary_is_on_path(self):
        with mock.patch.object(ocr.shutil, "which", return_value="/usr/bin/tesseract"), \
                mock.patch.object(ocr, "rapidocr_available", return_value=True):
            self.assertEqual(ocr.engine_probe(), ocr.Engine("tesseract", "/usr/bin/tesseract"))

    def test_rapidocr_is_the_default_without_tesseract(self):
        with mock.patch.object(ocr.shutil, "which", return_value=None), \
                mock.patch.object(ocr, "rapidocr_available", return_value=True):
            self.assertEqual(ocr.engine_probe().name, "rapidocr")

    def test_no_engine_is_reported_as_none(self):
        with mock.patch.object(ocr.shutil, "which", return_value=None), \
                mock.patch.object(ocr, "rapidocr_available", return_value=False):
            self.assertIsNone(ocr.engine_probe())

    def test_a_bare_path_names_a_tesseract_binary(self):
        self.assertEqual(ocr.as_engine("/opt/tesseract").name, "tesseract")
        self.assertIsNone(ocr.as_engine(None))
        with self.assertRaises(TypeError):
            ocr.as_engine(42)

    def test_probing_does_not_import_the_engine(self):
        """A plain CLI call must not pay for onnxruntime and OpenCV."""
        code = (
            "import sys; from engineering_assistant import ocr, doctor; ocr.engine_probe(); "
            "print('rapidocr_onnxruntime' in sys.modules or 'onnxruntime' in sys.modules)"
        )
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, check=True
        )
        self.assertEqual(result.stdout.strip(), "False")


class ReadingOrderTests(unittest.TestCase):
    @staticmethod
    def _box(x0, y0, x1, y1):
        return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]

    def test_runs_on_one_line_join_left_to_right_and_lines_top_to_bottom(self):
        detections = [
            [self._box(300, 112, 450, 150), "42.5 kW", 0.9],
            [self._box(150, 46, 350, 84), "balance: Q", 0.9],
            [self._box(20, 110, 300, 152), "Heat exchanger", 0.9],
            [self._box(20, 44, 150, 86), "Energy", 0.9],
        ]
        self.assertEqual(
            ocr.reading_order(detections), "Energy balance: Q\nHeat exchanger 42.5 kW"
        )

    def test_nothing_detected_is_blank_and_malformed_runs_are_skipped(self):
        self.assertEqual(ocr.reading_order(None), "")
        self.assertEqual(ocr.reading_order([["not a box", "x", 1.0], [self._box(0, 0, 1, 1), "  ", 1]]), "")


class _ScanFixture(unittest.TestCase):
    """A temporary course workspace and synthetic printed pages."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.source = self.root / "sources"
        self.workspace = self.root / "workspace"
        self.source.mkdir()

    def tearDown(self):
        self.tempdir.cleanup()

    def _catalog(self):
        return json.loads((self.workspace / "courses" / "demo" / "catalog.json").read_text())

    def _image(self, lines):
        """A synthetic printed page. Never a scan of real coursework."""
        from PIL import Image, ImageDraw, ImageFont

        path = self.source / "printed.png"
        image = Image.new("RGB", (900, 90 + 70 * len(lines)), "white")
        draw = ImageDraw.Draw(image)
        try:
            font = ImageFont.load_default(size=40)
        except TypeError:  # Pillow < 10.1 has no sized default font
            font = ImageFont.load_default()
        for index, line in enumerate(lines):
            draw.text((20, 40 + 70 * index), line, fill="black", font=font)
        image.save(path)
        return path


class RapidOcrProvenanceTests(_ScanFixture):
    def test_provenance_names_rapidocr_when_rapidocr_ran(self):
        self._image(["placeholder"])
        document = ingest(self.source, self.workspace, "demo")["documents"][0]
        result = auto_ocr_document(
            self.workspace, "demo", document["id"],
            probe=lambda: ocr.Engine(ocr.RAPIDOCR, ocr.RAPIDOCR_MODULE),
            runner=lambda path: "Determine the steady-state heat flux.",
        )
        self.assertTrue(result["imported"])
        self.assertEqual(result["engine"]["name"], "rapidocr")
        record = self._catalog()["documents"][0]["ocr_import"]
        self.assertEqual(record["provenance"]["tool"], "rapidocr")
        self.assertEqual(record["review_status"], "unreviewed")

    def test_no_engine_names_both_options_and_fails_closed(self):
        self._image(["placeholder"])
        document = ingest(self.source, self.workspace, "demo")["documents"][0]
        result = auto_ocr_document(self.workspace, "demo", document["id"], probe=lambda: None)
        self.assertEqual(result["reason"], "engine_unavailable")
        self.assertIsNone(result["engine"]["name"])
        self.assertIn("rapidocr", result["warning"])
        self.assertIn("tesseract", result["warning"])
        self.assertEqual(self._catalog()["documents"][0]["status"], "needs_ocr")

    @unittest.skipUnless(ocr.rapidocr_available(), "rapidocr-onnxruntime is not installed")
    def test_rapidocr_reads_a_printed_page_end_to_end(self):
        """The real engine, in its child process, through the real importer."""
        self._image(["HEAT TRANSFER", "Flow rate 42 kg/s"])
        document = ingest(self.source, self.workspace, "demo")["documents"][0]
        self.assertEqual(document["status"], "needs_ocr")

        result = auto_ocr_document(
            self.workspace, "demo", document["id"],
            probe=lambda: ocr.Engine(ocr.RAPIDOCR, ocr.RAPIDOCR_MODULE),
        )

        self.assertTrue(result["imported"], result)
        completed = self._catalog()["documents"][0]
        text = completed["blocks"][0]["text"]
        if sys.version_info >= (3, 10):
            self.assertIn("HEAT TRANSFER", text)
        else:
            # On 3.9 pip resolves an older onnxruntime, which reads the words
            # correctly but can drop the gap between them. Known and accepted:
            # 3.9 is the last-resort interpreter, and OCR output is reviewed.
            self.assertIn("HEATTRANSFER", text.replace(" ", ""))
        self.assertIn("42", text)
        self.assertLess(text.index("HEAT"), text.index("42"), "lines must be in reading order")
        provenance = completed["ocr_import"]["provenance"]
        self.assertEqual(provenance["tool"], "rapidocr")
        self.assertTrue(provenance["version"].startswith("rapidocr-onnxruntime "))
        self.assertEqual(completed["ocr_import"]["review_status"], "unreviewed")

    @unittest.skipUnless(ocr.rapidocr_available(), "rapidocr-onnxruntime is not installed")
    def test_rapidocr_reads_a_blank_page_as_blank_and_imports_nothing(self):
        from PIL import Image

        Image.new("RGB", (400, 200), "white").save(self.source / "blank.png")
        document = ingest(self.source, self.workspace, "demo")["documents"][0]
        result = auto_ocr_document(
            self.workspace, "demo", document["id"],
            probe=lambda: ocr.Engine(ocr.RAPIDOCR, ocr.RAPIDOCR_MODULE),
        )
        self.assertEqual(result["reason"], "blank_transcription")
        self.assertFalse(result["imported"])
        self.assertEqual(self._catalog()["documents"][0]["status"], "needs_ocr")


class OcrRunCommandTests(_ScanFixture):
    """`coursework ocr-run` is the only student-reachable path to automatic OCR."""

    def _cli(self, *args):
        from engineering_assistant import cli
        from contextlib import redirect_stdout
        import io

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = cli.main(["--workspace", str(self.workspace), *args])
        return code, json.loads(buffer.getvalue())

    def test_ocr_run_without_an_engine_blocks_and_leaves_the_queue(self):
        self._image(["placeholder"])
        document = ingest(self.source, self.workspace, "demo")["documents"][0]
        with mock.patch.object(ocr, "engine_probe", return_value=None):
            code, out = self._cli("ocr-run", "--course", "demo", "--document-id", document["id"])
        self.assertEqual(code, 0)
        self.assertEqual(out["reason"], "engine_unavailable")
        self.assertFalse(out["imported"])
        self.assertEqual(self._catalog()["documents"][0]["status"], "needs_ocr")

    @unittest.skipUnless(ocr.rapidocr_available(), "rapidocr-onnxruntime is not installed")
    def test_ocr_run_transcribes_a_printed_scan_unreviewed(self):
        self._image(["HEAT TRANSFER"])
        document = ingest(self.source, self.workspace, "demo")["documents"][0]
        with mock.patch.object(ocr.shutil, "which", return_value=None):
            code, out = self._cli("ocr-run", "--course", "demo", "--document-id", document["id"])
        self.assertEqual(code, 0)
        self.assertTrue(out["imported"], out)
        self.assertEqual(out["engine"]["name"], "rapidocr")
        self.assertEqual(self._catalog()["documents"][0]["ocr_import"]["review_status"], "unreviewed")

    def test_help_names_printed_scans_and_the_handwriting_route(self):
        result = subprocess.run(
            [sys.executable, "-m", "engineering_assistant.cli", "ocr-run", "--help"],
            capture_output=True, text=True, check=True,
        )
        self.assertIn("printed", result.stdout)
        self.assertIn("ocr-import", result.stdout)


class EngineReportTests(unittest.TestCase):
    def test_engine_line_is_one_json_object_naming_the_probe_result(self):
        result = subprocess.run(
            [sys.executable, "-m", "engineering_assistant.ocr", "--engine"],
            capture_output=True, text=True, check=True,
        )
        payload = json.loads(result.stdout)
        found = ocr.engine_probe()
        self.assertEqual(payload["engine"], found.name if found else None)

    def test_doctor_names_the_engine_and_the_handwriting_limit(self):
        from engineering_assistant.doctor import diagnose

        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            ocr, "engine_probe", return_value=ocr.Engine(ocr.RAPIDOCR, ocr.RAPIDOCR_MODULE)
        ):
            report = diagnose(Path(directory), Path(directory) / "workspace")
        self.assertEqual(report["ocr"]["automatic_engine"], "rapidocr")
        self.assertTrue(report["ocr"]["automatic_engine_available"])
        self.assertIn("handwriting", report["ocr"]["limits"])


if __name__ == "__main__":
    unittest.main()
