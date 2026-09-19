"""The frame a figure is fitted into follows the profile's margins (#32).

Before #32 both renderers fitted images into a fixed 6.25in x 4.5in frame.  A
profile with 1.5in margins has a 5.5in text column, so a full-width figure ran
0.75in past the margin the profile declared, and a profile with 0.5in margins
got figures narrower than the text beside them.

The frame is now derived from the page and the margins:

* width  = page width minus both margins, i.e. the text column;
* height = half of the page height minus both margins, so a figure at full
  height still leaves room on its page for its caption and some text.  At the
  default 1in margins that is exactly the 4.5in used before.

The same issue covers a second divergence in the same lines: for an image
smaller than the frame, the PDF capped scale at 1 and the DOCX stretched it to
fill the frame, drawing the same undeclared figure at about four times the area.
The DOCX now takes the PDF's cap.

Sizes are measured from the built documents: the placement matrix in the PDF
content stream, and the inline shape in the DOCX.
"""
import re
import tempfile
import unittest
from pathlib import Path

from docx import Document
from PIL import Image
from pypdf import PdfReader

from engineering_assistant.plots import render_line_plot
from engineering_assistant.rendering import render_text_docx, render_text_pdf

PAGE_WIDTH = 612.0
RENDERING = {
    "body_font_size": 12,
    "line_spacing": 1.5,
    "title_page": False,
    "number_body_pages": True,
    "table_captions_above": True,
    "figure_captions_below": True,
}
# reportlab emits "1 0 0 1 x y cm" to position the image and then
# "w 0 0 h 0 0 cm" to scale it, immediately before drawing it.
_PLACED = re.compile(
    r"1 0 0 1 ([\d.]+) ([\d.]+) cm\s*q\s*([\d.]+) 0 0 ([\d.]+) 0 0 cm\s*/\S+ Do"
)


def _solution(figure: dict) -> dict:
    return {
        "document_type": "worked_problem",
        "title": "Cooling Study",
        "sections": [{"heading": "Results", "body": "The measured response.", "figures": [dict(figure)]}],
        "calculations": [],
        "unresolved": [],
    }


def _image(root: Path, size, name: str = "image.png") -> str:
    path = root / "figures" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, "white").save(path)
    return f"figures/{name}"


def _profile(margin: float) -> dict:
    return {"rendering": {**RENDERING, "margin_inches": margin}}


def _pdf_placement(root: Path, figure: dict, margin: float) -> tuple[float, float, float, float]:
    """(left edge, width, height) of the one figure the page draws, in points."""
    output = root / "deliverables" / "figure.pdf"
    render_text_pdf(_solution(figure), output, style_profile=_profile(margin))
    found = []
    for page in PdfReader(str(output)).pages:
        stream = page.get_contents().get_data().decode("latin-1")
        found.extend(tuple(float(v) for v in match) for match in _PLACED.findall(stream))
    if len(found) != 1:
        raise AssertionError(f"expected one figure placement, found {found}")
    x, _, width, height = found[0]
    return x, width, height


def _docx_size(root: Path, figure: dict, margin: float) -> tuple[float, float]:
    output = root / "deliverables" / "figure.docx"
    render_text_docx(_solution(figure), output, style_profile=_profile(margin))
    shape = Document(str(output)).inline_shapes[0]
    return round(shape.width.pt, 2), round(shape.height.pt, 2)


class FrameFollowsMarginsTests(unittest.TestCase):
    def test_a_full_width_figure_stays_inside_wide_margins(self):
        """The #32 reproduction.  On origin/main this draws 450pt into a 396pt column."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            figure = {"path": _image(root, (2000, 1000)), "caption": "Figure 1."}
            margin = 1.5 * 72
            x, width, height = _pdf_placement(root, figure, 1.5)
            self.assertGreaterEqual(x, margin - 0.01, "the figure starts inside the left margin")
            self.assertLessEqual(x + width, PAGE_WIDTH - margin + 0.01, "the figure overruns the right margin")
            self.assertEqual((width, height), (396.0, 198.0))
            self.assertEqual(_docx_size(root, figure, 1.5), (396.0, 198.0))

    def test_a_full_width_figure_fills_a_narrow_margin_column(self):
        """On origin/main a 0.5in-margin page still gets a 6.25in (450pt) figure."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            figure = {"path": _image(root, (2000, 1000)), "caption": "Figure 1."}
            _, width, height = _pdf_placement(root, figure, 0.5)
            self.assertEqual((width, height), (540.0, 270.0))
            self.assertEqual(_docx_size(root, figure, 0.5), (540.0, 270.0))

    def test_default_margins_give_the_full_text_column(self):
        """Deliberate change: at 1in margins the column is 6.5in, not the old 6.25in.

        On origin/main this draws at 450x225pt.  No existing test pinned it.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            figure = {"path": _image(root, (2000, 1000)), "caption": "Figure 1."}
            _, width, height = _pdf_placement(root, figure, 1)
            self.assertEqual((width, height), (468.0, 234.0))

    def test_the_height_bound_is_half_the_text_height(self):
        """At 1in margins that is exactly the old 4.5in, so the default does not move.

        A tall image binds on height.  At 2.5in margins the text block is 6in
        tall and the bound is 3in (216pt); on origin/main it stays at 324pt.
        The 1in case passes on origin/main as well: it is the guard.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            figure = {"path": _image(root, (1000, 2000)), "caption": "Figure 1."}
            for margin, expected in ((1, (162.0, 324.0)), (2.5, (108.0, 216.0))):
                with self.subTest(margin=margin):
                    _, width, height = _pdf_placement(root, figure, margin)
                    self.assertEqual((width, height), expected)
                    self.assertEqual(_docx_size(root, figure, margin), expected)

    def test_a_declared_size_wider_than_the_column_is_refused(self):
        """On origin/main 420pt is accepted at 1.5in margins, and overruns them."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            path = _image(root, (2000, 1000))
            for render in (_pdf_placement, _docx_size):
                with self.subTest(renderer=render.__name__):
                    with self.assertRaises(ValueError) as caught:
                        render(root, {"path": path, "caption": "F.", "width": 420}, 1.5)
                    self.assertIn("printable area", str(caught.exception))

    def test_a_default_plot_that_no_longer_fits_is_refused_with_the_width_that_does(self):
        """A 450pt plot cannot be drawn at 450pt in a 396pt column.

        Shrinking it would print its text below the size it was drawn for, so
        the renderer refuses and names the width to render it at.  On
        origin/main it is drawn at 450pt against the fixed 6.25in frame and
        runs 54pt past the 1.5in margins.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            render_line_plot(
                {"series": [{"name": "Measured", "x": [0, 1, 2], "y": [1, 4, 9]}]},
                root / "figures" / "plot.png",
            )
            figure = {"path": "figures/plot.png", "caption": "Figure 1."}
            for render in (_pdf_placement, _docx_size):
                with self.subTest(renderer=render.__name__):
                    with self.assertRaises(ValueError) as caught:
                        render(root, figure, 1.5)
                    self.assertIn("396", str(caught.exception))

    def test_margins_that_leave_no_room_for_a_figure_are_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            figure = {"path": _image(root, (200, 100)), "caption": "Figure 1."}
            for render in (_pdf_placement, _docx_size):
                with self.subTest(renderer=render.__name__):
                    with self.assertRaises(ValueError):
                        render(root, figure, 4.25)


class NoUpscaleTests(unittest.TestCase):
    def test_docx_does_not_stretch_a_small_image_past_its_natural_size(self):
        """The second #32 defect.  On origin/main the DOCX draws this at 450x300pt."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            figure = {"path": _image(root, (240, 160)), "caption": "Figure 1."}
            self.assertEqual(_docx_size(root, figure, 1), (240.0, 160.0))

    def test_both_renderers_draw_an_undeclared_image_at_the_same_size(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            for size in ((240, 160), (2000, 1000), (1000, 2000)):
                path = _image(root, size, name=f"i{size[0]}x{size[1]}.png")
                figure = {"path": path, "caption": "Figure 1."}
                for margin in (0.5, 1, 1.5):
                    with self.subTest(size=size, margin=margin):
                        _, width, height = _pdf_placement(root, figure, margin)
                        self.assertEqual(_docx_size(root, figure, margin), (width, height))


if __name__ == "__main__":
    unittest.main()
