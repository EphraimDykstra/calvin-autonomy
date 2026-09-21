"""The title page carries the group and the instructor, in both renderers.

A course pack can require a title page to name the professor and the group, and
no pack may hold either: both belong to the student's own materials. They reach
the page through the solution's metadata at run time, and an unsupplied
instructor prints a visible placeholder rather than a blank line that would read
as a finished page.
"""
import json
import tempfile
import unittest
from pathlib import Path

from docx import Document
from pypdf import PdfReader

from engineering_assistant.rendering import (
    INSTRUCTOR_PLACEHOLDER,
    render_text_docx,
    render_text_pdf,
    title_page_lines,
)

RENDERING = {
    "body_font_size": 12,
    "line_spacing": 1.5,
    "margin_inches": 1,
    "title_page": True,
    "abstract": True,
    "number_body_pages": True,
    "table_captions_above": True,
    "figure_captions_below": True,
}


def _solution(metadata):
    return {
        "document_type": "technical_report",
        "title": "Duct Accounting",
        "abstract": "Abstract text for the title page.",
        "metadata": metadata,
        "sections": [{"heading": "Objective", "body": "Body text.", "requirement_ids": ["r1"]}],
        "calculations": [],
        "unresolved": [],
    }


def _pdf_text(solution):
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory) / "run" / "deliverables" / "submission.pdf"
        render_text_pdf(solution, output, style_profile={"rendering": RENDERING})
        return PdfReader(str(output)).pages[0].extract_text()


def _docx_text(solution):
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory) / "run" / "deliverables" / "submission.docx"
        render_text_docx(solution, output, style_profile={"rendering": RENDERING})
        return "\n".join(p.text for p in Document(str(output)).paragraphs)


class TitlePageFieldTests(unittest.TestCase):
    def test_supplied_group_and_instructor_reach_both_renderers(self):
        solution = _solution({
            "course": "ENGR 328, Section A",
            "group": "Group 4",
            "instructor": "Quillfeather",
            "date": "20 September 2026",
        })
        for name, text in (("pdf", _pdf_text(solution)), ("docx", _docx_text(solution))):
            self.assertIn("Group 4", text, name)
            self.assertIn("Quillfeather", text, name)
            self.assertNotIn(INSTRUCTOR_PLACEHOLDER, text, name)

    def test_unsupplied_instructor_prints_the_placeholder_not_a_blank(self):
        """A blank line reads as finished; a placeholder says what is missing."""
        solution = _solution({"course": "ENGR 328, Section A", "date": "20 September 2026"})
        for name, text in (("pdf", _pdf_text(solution)), ("docx", _docx_text(solution))):
            self.assertIn(INSTRUCTOR_PLACEHOLDER, text, name)

    def test_absent_group_prints_nothing(self):
        """A course asks for the group "if applicable", so no group is no line."""
        lines = title_page_lines(_solution({"course": "ENGR 328"}), "[Student Name]")
        self.assertEqual(lines, ["ENGR 328", "[Student Name]", INSTRUCTOR_PLACEHOLDER])

    def test_blank_and_malformed_metadata_do_not_produce_empty_lines(self):
        for metadata in ({"group": "   ", "instructor": ""}, [], None, "ENGR 328"):
            lines = title_page_lines({"metadata": metadata}, "[Student Name]")
            self.assertEqual(lines, ["[Student Name]", INSTRUCTOR_PLACEHOLDER], metadata)

    def test_no_shipped_pack_or_template_stores_an_instructor_name(self):
        """The name arrives at run time; nothing shipped holds one.

        The check walks the parsed JSON rather than the text, because a pack
        may legitimately *name the field* in a list of what a title page must
        carry, as engr204-lab does, without holding anybody's name.
        """
        root = Path(__file__).resolve().parents[1]

        def walk(node, path):
            if isinstance(node, dict):
                for key, value in node.items():
                    if key in ("instructor", "professor") and isinstance(value, str):
                        self.assertEqual(value, INSTRUCTOR_PLACEHOLDER, f"{path}:{key}")
                    walk(value, path)
            elif isinstance(node, list):
                for item in node:
                    walk(item, path)

        files = list((root / "curriculum").rglob("*.json")) + list((root / "templates").glob("*.json"))
        self.assertTrue(files)
        for path in files:
            walk(json.loads(path.read_text(encoding="utf-8")), path)


if __name__ == "__main__":
    unittest.main()
