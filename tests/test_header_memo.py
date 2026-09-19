"""The header memo: To, From, CC, Date and Re, then the body.

"Technical memo" names two documents at Calvin, and the renderer could produce
only one.  An ENGR 322 executive-summary memo came out with no header, looking
finished and being the wrong document.  These render real files and read them
back, because a header that exists in the solution but not on the page is the
failure being fixed.
"""

import tempfile
import unittest
from pathlib import Path

from engineering_assistant.rendering import memo_header_rows, render_text_docx, render_text_pdf


def _memo(**header):
    base = {"to": "[Instructor]", "date": "September 19, 2026", "re": "Hitch preload recommendation"}
    base.update(header)
    return {
        "document_type": "memo",
        "title": "Executive summary",
        "memo_header": base,
        "sections": [{"heading": "Summary", "body": "Torque the bolts to the specified preload."}],
    }


def _pdf_text(path):
    from pypdf import PdfReader

    return "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)


def _docx_text(path):
    from docx import Document

    return "\n".join(p.text for p in Document(str(path)).paragraphs)


class HeaderRowsTests(unittest.TestCase):
    def test_rows_come_in_memo_order(self):
        rows = memo_header_rows(_memo(cc="Lab section"), "[Student Name]")
        self.assertEqual([label for label, _ in rows], ["To", "From", "CC", "Date", "Re"])

    def test_from_defaults_to_the_run_identity(self):
        rows = dict(memo_header_rows(_memo(), "[Student Name]"))
        self.assertEqual(rows["From"], "[Student Name]")

    def test_cc_is_optional(self):
        labels = [label for label, _ in memo_header_rows(_memo(), "[Student Name]")]
        self.assertNotIn("CC", labels)

    def test_the_subject_falls_back_to_the_title(self):
        memo = _memo(re="")
        self.assertEqual(dict(memo_header_rows(memo, "[Student Name]"))["Re"], "Executive summary")

    def test_an_incomplete_header_is_refused(self):
        # Without its header a memo looks finished and is the wrong document.
        for field in ("to", "date"):
            with self.subTest(missing=field):
                with self.assertRaises(ValueError) as caught:
                    memo_header_rows(_memo(**{field: ""}), "[Student Name]")
                self.assertIn(field.capitalize(), str(caught.exception))

    def test_a_memo_with_no_header_at_all_is_refused(self):
        memo = _memo()
        del memo["memo_header"]
        with self.assertRaises(ValueError):
            memo_header_rows(memo, "[Student Name]")


class RenderedMemoTests(unittest.TestCase):
    """Read the files back: the header has to be on the page, not just in the data."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _assert_header_then_body(self, text):
        for label in ("To:", "From:", "Date:", "Re:"):
            self.assertIn(label, text)
        self.assertIn("[Instructor]", text)
        self.assertIn("Hitch preload recommendation", text)
        # The header comes first, and the body after it.
        self.assertLess(text.index("To:"), text.index("Re:"))
        self.assertLess(text.index("Re:"), text.index("Torque the bolts"))

    def test_the_pdf_carries_the_header(self):
        path = render_text_pdf(_memo(), self.root / "memo.pdf")
        self._assert_header_then_body(_pdf_text(path))

    def test_the_docx_carries_the_header(self):
        path = render_text_docx(_memo(), self.root / "memo.docx")
        self._assert_header_then_body(_docx_text(path))

    def test_a_memo_has_no_title_page(self):
        # A header memo opens on its header, whatever a course's title-page
        # setting says for its reports.
        path = render_text_pdf(_memo(), self.root / "memo.pdf", style_profile={"rendering": {"title_page": True}})
        from pypdf import PdfReader

        first = PdfReader(str(path)).pages[0].extract_text() or ""
        self.assertIn("To:", first)
        self.assertIn("Torque the bolts", first)

    def test_rendering_refuses_a_memo_without_its_header(self):
        memo = _memo()
        del memo["memo_header"]
        with self.assertRaises(ValueError):
            render_text_pdf(memo, self.root / "memo.pdf")
        with self.assertRaises(ValueError):
            render_text_docx(memo, self.root / "memo.docx")

    def test_a_report_is_unaffected(self):
        report = {"document_type": "technical_report", "title": "Tensile test",
                  "abstract": "The modulus was measured.",
                  "sections": [{"heading": "Results", "body": "It was measured."}]}
        text = _pdf_text(render_text_pdf(report, self.root / "report.pdf"))
        self.assertNotIn("To:", text)
        self.assertIn("Tensile test", text)


if __name__ == "__main__":
    unittest.main()
