"""A plot carries its own physical size, and a figure cannot contradict it (#36).

``render_line_plot`` sizes its text against a target in points.  That text is
only as large on the page as the target says if the figure embedding the plot is
drawn at the same size, and before #36 nothing connected the two numbers: a
210pt plot embedded in a figure declaring 120pt printed its title near 3.6pt.

The plot now writes its target into the PNG's ``pHYs`` chunk, alongside a text
key that says the chunk was written by this project.  The renderer applies a
three-way rule:

* marked, nothing declared    -> draw at the marked physical size
* marked, declared differently -> refuse
* not marked                   -> the fitting rule from #29, unchanged

The third branch is the one that is easy to break by accident.  A PIL-written
image has no ``pHYs`` at all, and an image from another tool may carry one that
says nothing about legibility, so neither may be read as a physical size.

Every size here is measured from the built document (the PDF placement matrix
or the DOCX inline shape), never from the plot's own declaration.
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

PLOT = {
    "title": "Cooling curve",
    "x_label": "Time [s]",
    "y_label": "Temperature [K]",
    "series": [{"name": "Measured", "x": list(range(10)), "y": [300 + 9 * i for i in range(10)]}],
}
RENDERING = {
    "body_font_size": 12,
    "line_spacing": 1.5,
    "margin_inches": 1,
    "title_page": False,
    "number_body_pages": True,
    "table_captions_above": True,
    "figure_captions_below": True,
}
_PLACEMENT = re.compile(r"([\d.]+) 0 0 ([\d.]+) 0 0 cm\s*/\S+ Do")


def _solution(figure: dict) -> dict:
    return {
        "document_type": "worked_problem",
        "title": "Cooling Study",
        "sections": [{"heading": "Results", "body": "The measured response.", "figures": [dict(figure)]}],
        "calculations": [],
        "unresolved": [],
    }


def _plot(root: Path, name: str, **spec) -> str:
    render_line_plot({**PLOT, **spec}, root / "figures" / name)
    return f"figures/{name}"


def _pdf_points(root: Path, figure: dict) -> tuple[float, float]:
    output = root / "deliverables" / "figure.pdf"
    render_text_pdf(_solution(figure), output, style_profile={"rendering": dict(RENDERING)})
    placements = []
    for page in PdfReader(str(output)).pages:
        stream = page.get_contents().get_data().decode("latin-1")
        placements.extend((float(w), float(h)) for w, h in _PLACEMENT.findall(stream))
    if len(placements) != 1:
        raise AssertionError(f"expected one figure placement, found {placements}")
    return placements[0]


def _docx_points(root: Path, figure: dict) -> tuple[float, float]:
    output = root / "deliverables" / "figure.docx"
    render_text_docx(_solution(figure), output, style_profile={"rendering": dict(RENDERING)})
    shape = Document(str(output)).inline_shapes[0]
    return shape.width.pt, shape.height.pt


class PlotMarkerTests(unittest.TestCase):
    def test_a_plot_records_its_target_as_its_physical_size(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for target in (450, 300, 210, 150):
                with self.subTest(target=target):
                    path = root / "figures" / f"p{target}.png"
                    render_line_plot({**PLOT, "width": target}, path)
                    with Image.open(path) as image:
                        dpi = image.info.get("dpi")
                        pixels = image.size
                    self.assertIsNotNone(dpi, "the plot carries no physical size")
                    self.assertAlmostEqual(pixels[0] / dpi[0] * 72, target, delta=target * 0.001)


class UndeclaredPlotTests(unittest.TestCase):
    def test_an_undeclared_small_plot_is_drawn_at_its_own_target(self):
        """On origin/main a 150pt plot is 333px wide and is drawn at 333pt.

        The no-upscale cap reads pixels as points, so the plot lands at more than
        twice the size it was drawn for, and the page loses the space the author
        asked for.  The plot's own marker is the size it was designed to occupy.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            figure = {"path": _plot(root, "small.png", width=150), "caption": "Figure 1."}
            for measure in (_pdf_points, _docx_points):
                with self.subTest(renderer=measure.__name__):
                    width, _ = measure(root, figure)
                    self.assertAlmostEqual(width, 150.0, delta=0.2)

    def test_an_undeclared_default_plot_lands_where_it_always_did(self):
        """Passes on origin/main as well: a guard, not a reproduction.

        A default plot is 1000x650px and 450x292.5pt by marker, and the old
        fitting rule also drew it at 450x292.5pt, so the three-way rule must not
        move it.  The marker is quantized to whole pixels per metre, hence delta.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            figure = {"path": _plot(root, "default.png"), "caption": "Figure 1."}
            for measure in (_pdf_points, _docx_points):
                with self.subTest(renderer=measure.__name__):
                    width, height = measure(root, figure)
                    self.assertAlmostEqual(width, 450.0, delta=0.1)
                    self.assertAlmostEqual(height, 292.5, delta=0.1)

    def test_a_plot_larger_than_the_printable_area_is_refused_with_the_width_that_fits(self):
        """Shrinking it to fit would be the #29 defect again, just unannounced.

        On origin/main a 600pt plot is fitted down to 450pt and its text with it.
        The refusal names the width the author should render the plot at: the
        468pt text column at the default 1in margins (#32).
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            figure = {"path": _plot(root, "wide.png", width=600), "caption": "Figure 1."}
            for measure in (_pdf_points, _docx_points):
                with self.subTest(renderer=measure.__name__):
                    with self.assertRaises(ValueError) as caught:
                        measure(root, figure)
                    self.assertIn("468", str(caught.exception))


class DeclaredPlotTests(unittest.TestCase):
    def test_a_figure_declared_smaller_than_its_plot_is_refused(self):
        """The #36 reproduction: 210pt plot at 120pt printed its title near 3.6pt."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            path = _plot(root, "p210.png", width=210)
            for declared in ({"width": 120}, {"height": 60}):
                for measure in (_pdf_points, _docx_points):
                    with self.subTest(declared=declared, renderer=measure.__name__):
                        with self.assertRaises(ValueError) as caught:
                            measure(root, {"path": path, "caption": "Figure 1.", **declared})
                        self.assertIn("210", str(caught.exception))

    def test_a_figure_declared_larger_than_its_plot_is_refused(self):
        """Enlarging is refused too: the declaration still contradicts the plot."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            path = _plot(root, "p210.png", width=210)
            for measure in (_pdf_points, _docx_points):
                with self.subTest(renderer=measure.__name__):
                    with self.assertRaises(ValueError):
                        measure(root, {"path": path, "caption": "Figure 1.", "width": 300})

    def test_declaring_a_plot_at_its_own_target_is_accepted(self):
        """Passes on origin/main as well: a guard on the new refusal.

        ``pHYs`` stores whole pixels per metre, so the marked size is off the
        target by a few thousandths of a point.  An equality test would refuse
        the one declaration the contract asks authors to make.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            for target in (450, 330, 210, 150):
                path = _plot(root, f"p{target}.png", width=target)
                figure = {"path": path, "caption": "Figure 1.", "width": target}
                for measure in (_pdf_points, _docx_points):
                    with self.subTest(target=target, renderer=measure.__name__):
                        width, _ = measure(root, figure)
                        self.assertAlmostEqual(width, float(target), places=2)

    def test_a_bounding_box_that_fits_the_plot_is_not_a_contradiction(self):
        """Passes on origin/main as well.  The box binds on width; height is slack."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            path = _plot(root, "p210.png", width=210)
            width, _ = _pdf_points(root, {"path": path, "caption": "F.", "width": 210, "height": 300})
            self.assertAlmostEqual(width, 210.0, places=2)


class UnmarkedImageTests(unittest.TestCase):
    """The branch that is easiest to break: no marker means no change at all."""

    def _image(self, root: Path, size, **save) -> str:
        path = root / "figures" / "image.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", size, "white").save(path, **save)
        return "figures/image.png"

    def test_an_image_from_another_tool_keeps_the_fitting_rule(self):
        """Passes on origin/main as well: a guard.

        Most exporters write ``pHYs``.  A 2000x1000px schematic tagged 96dpi reads
        as 1500pt, which would be refused as larger than the page, and a declared
        300pt would be refused as a contradiction.  Neither is a plot drawn for a
        size, so both must fit exactly as before.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            path = self._image(root, (2000, 1000), dpi=(96, 96))
            undeclared = _pdf_points(root, {"path": path, "caption": "F."})
            declared = _pdf_points(root, {"path": path, "caption": "F.", "width": 300})
            # The 468pt text column at 1in margins (#32); 450pt before it.
            self.assertEqual(undeclared, (468.0, 234.0))
            self.assertEqual(declared, (300.0, 150.0))

    def test_an_image_with_no_physical_size_keeps_the_fitting_rule(self):
        """Passes on origin/main as well: PIL writes no ``pHYs``, so no 72dpi guess."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            path = self._image(root, (240, 160))
            self.assertEqual(_pdf_points(root, {"path": path, "caption": "F."}), (240.0, 160.0))
            self.assertEqual(_pdf_points(root, {"path": path, "caption": "F.", "width": 120}), (120.0, 80.0))


if __name__ == "__main__":
    unittest.main()
