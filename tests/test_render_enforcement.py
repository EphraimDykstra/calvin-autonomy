import tempfile
import unittest
from pathlib import Path

from PIL import Image
from pypdf import PdfReader

from engineering_assistant.rendering import render_text_docx, render_text_pdf

BASE_RENDERING = {
    "body_font_size": 12,
    "line_spacing": 1.5,
    "margin_inches": 1,
    "title_page": True,
    "abstract": True,
    "number_body_pages": True,
    "table_captions_above": True,
    "figure_captions_below": True,
}


def _figure(root: Path, name: str = "schematic.png") -> str:
    """Write a small real image inside the run so the renderer will accept it."""
    path = root / "figures" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (240, 160), "white").save(path)
    return f"figures/{name}"


def _solution(sections, *, appendices=None, figures_in=None):
    solution = {
        "document_type": "technical_report",
        "title": "Radiation Study",
        "abstract": "Abstract text for the title page.",
        "sections": sections,
        "calculations": [],
        "unresolved": [],
    }
    if appendices is not None:
        solution["appendices"] = appendices
    return solution


def _long_section(index, figure_path=None, role=None):
    # Enough prose to reliably fill a page at 12pt/1.5 spacing.
    body = " ".join(f"Sentence {index}-{n} describing the measured cooling behaviour in detail." for n in range(70))
    section = {"heading": f"Section {index}", "body": body, "requirement_ids": ["r1"]}
    if figure_path:
        figure = {"path": figure_path, "caption": f"Figure {index}."}
        if role:
            figure["role"] = role
        section["figures"] = [figure]
    return section


class RequiredFigureTests(unittest.TestCase):
    def test_pdf_render_refuses_when_a_required_figure_role_is_absent(self):
        """A course that requires an apparatus schematic must not render without one.

        The assignment states the requirement, the profile records it, and until
        now nothing compared the two: a deliverable missing a required figure
        rendered silently and reached later stages looking complete.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            output = root / "deliverables" / "submission.pdf"
            solution = _solution([_long_section(1)])
            rendering = {**BASE_RENDERING, "required_figures": ["apparatus-schematic"]}
            with self.assertRaises(ValueError) as caught:
                render_text_pdf(solution, output, style_profile={"rendering": rendering})
            self.assertIn("apparatus-schematic", str(caught.exception))
            self.assertFalse(output.exists())

    def test_pdf_render_accepts_the_required_figure_in_an_appendix(self):
        """Courses differ on whether a schematic belongs in the body or an appendix."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            output = root / "deliverables" / "submission.pdf"
            path = _figure(root)
            solution = _solution(
                [_long_section(1)],
                appendices=[{
                    "heading": "Appendix A",
                    "body": "Apparatus.",
                    "figures": [{"path": path, "caption": "Figure A1.", "role": "apparatus-schematic"}],
                }],
            )
            rendering = {**BASE_RENDERING, "required_figures": ["apparatus-schematic"]}
            render_text_pdf(solution, output, style_profile={"rendering": rendering})
            self.assertTrue(output.exists())

    def test_required_figure_matching_ignores_case_and_surrounding_space(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            output = root / "deliverables" / "submission.pdf"
            path = _figure(root)
            solution = _solution([_long_section(1, path, "  Apparatus-Schematic ")])
            rendering = {**BASE_RENDERING, "required_figures": ["apparatus-schematic"]}
            render_text_pdf(solution, output, style_profile={"rendering": rendering})
            self.assertTrue(output.exists())

    def test_caption_text_alone_does_not_satisfy_a_required_role(self):
        """Roles are declared, not inferred, so rewording a caption cannot break or fake the rule."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            output = root / "deliverables" / "submission.pdf"
            path = _figure(root)
            section = _long_section(1, path)
            section["figures"][0]["caption"] = "Figure 1. Apparatus schematic of the test rig."
            solution = _solution([section])
            rendering = {**BASE_RENDERING, "required_figures": ["apparatus-schematic"]}
            with self.assertRaises(ValueError):
                render_text_pdf(solution, output, style_profile={"rendering": rendering})

    def test_docx_render_also_refuses_a_missing_required_figure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            output = root / "deliverables" / "submission.docx"
            solution = _solution([_long_section(1)])
            rendering = {**BASE_RENDERING, "required_figures": ["apparatus-schematic"]}
            with self.assertRaises(ValueError):
                render_text_docx(solution, output, style_profile={"rendering": rendering})
            self.assertFalse(output.exists())

    def test_malformed_required_figures_declaration_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run" / "deliverables" / "submission.pdf"
            solution = _solution([_long_section(1)])
            for bad in ("apparatus-schematic", [""], [3]):
                with self.assertRaises(ValueError):
                    render_text_pdf(
                        solution, output,
                        style_profile={"rendering": {**BASE_RENDERING, "required_figures": bad}},
                    )


class BodyPageBudgetTests(unittest.TestCase):
    def test_render_refuses_a_body_longer_than_the_course_allows(self):
        """The instructor's two-page body limit is objective and must be enforced.

        A five-page body against a two-page requirement is the most visible way a
        submission fails to follow instructions, and it previously rendered clean.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            output = root / "deliverables" / "submission.pdf"
            solution = _solution([_long_section(i) for i in range(1, 6)])
            rendering = {**BASE_RENDERING, "max_body_pages": 2}
            with self.assertRaises(ValueError) as caught:
                render_text_pdf(solution, output, style_profile={"rendering": rendering})
            message = str(caught.exception)
            self.assertIn("at most 2", message)
            self.assertFalse(output.exists(), "a non-compliant artifact must not be left on disk")

    def test_body_within_the_budget_renders(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            output = root / "deliverables" / "submission.pdf"
            solution = _solution([_long_section(1)])
            rendering = {**BASE_RENDERING, "max_body_pages": 2}
            render_text_pdf(solution, output, style_profile={"rendering": rendering})
            self.assertTrue(output.exists())

    def test_appendix_pages_do_not_count_against_the_body_budget(self):
        """The course limit is on the body; appendices are explicitly expected to be longer."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            output = root / "deliverables" / "submission.pdf"
            appendices = [{"heading": f"Appendix {i}", "body": _long_section(i)["body"]} for i in range(1, 5)]
            solution = _solution([_long_section(1)], appendices=appendices)
            rendering = {**BASE_RENDERING, "max_body_pages": 2}
            render_text_pdf(solution, output, style_profile={"rendering": rendering})
            self.assertTrue(output.exists())
            self.assertGreater(len(PdfReader(str(output)).pages), 4)

    def test_no_budget_declared_leaves_behaviour_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            output = root / "deliverables" / "submission.pdf"
            solution = _solution([_long_section(i) for i in range(1, 6)])
            render_text_pdf(solution, output, style_profile={"rendering": dict(BASE_RENDERING)})
            self.assertTrue(output.exists())

    def test_malformed_page_budget_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "run" / "deliverables" / "submission.pdf"
            solution = _solution([_long_section(1)])
            for bad in (0, -1, 2.5, True, "2"):
                with self.assertRaises(ValueError):
                    render_text_pdf(
                        solution, output,
                        style_profile={"rendering": {**BASE_RENDERING, "max_body_pages": bad}},
                    )


if __name__ == "__main__":
    unittest.main()
