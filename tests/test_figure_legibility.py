"""A small figure must be a readable figure, and a declared size must be honoured.

Every assertion here is made in **points on the printed page**, never in source
pixels.  That distinction is the whole of issue #29: a plot can carry text at any
nominal font size and still be illegible, because what the reader sees is the
source text scaled by however much the renderer shrank the image to make it fit.

Two instruments do all the work:

* ``_title_points`` renders the same plot twice, once with an inked title and
  once with a blank one of equal length, and measures the vertical extent of the
  difference.  That is the title's ink and nothing else -- no font metric, no
  layout constant, no assumption about how the plot is drawn.  Converting it with
  ``target_points / canvas_pixels`` gives the height the reader actually sees.
* ``_pdf_figure_points`` reads the image's placement matrix straight out of the
  PDF content stream, which is the size the page really draws it at.  This is
  deliberately not a file hash: a hash would notice a change without saying what
  changed or why it mattered, and would break on any unrelated reportlab update.

None of these assertions pin a pixel dimension, a font size, or a margin, so
tuning the layout does not break them; only regressing legibility does.
"""
from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from docx import Document
from PIL import Image, ImageChops
from pypdf import PdfReader

from engineering_assistant.plots import render_line_plot
from engineering_assistant.rendering import render_text_docx, render_text_pdf

# Below roughly six points, text on a printed page stops being readable by a
# marker skimming a stack of reports.  The requirement that opened issue #29 was
# that a material, a finish and a computed value appear *on the graph*, so this
# floor is what makes that requirement satisfiable rather than merely declared.
LEGIBLE_POINTS = 6.0

PLOT = {
    "x_label": "Time [s]",
    "y_label": "Temperature [K]",
    "series": [{"name": "Measured", "x": list(range(10)), "y": [300 + 9 * i for i in range(10)]}],
}
BASE_RENDERING = {
    "body_font_size": 12,
    "line_spacing": 1.5,
    "margin_inches": 1,
    "title_page": False,
    "number_body_pages": True,
    "table_captions_above": True,
    "figure_captions_below": True,
}
# "1000 0 0 650 0 0 cm" immediately before the image is drawn: the width and
# height, in points, that this page gives the figure.
_PLACEMENT = re.compile(r"([\d.]+) 0 0 ([\d.]+) 0 0 cm\s*/\S+ Do")


def _title_points(root: Path, target: float | None, probe: str = "Hxy") -> float:
    """Height of the plot title's ink, in points on the page, at this target size."""
    sized = {**PLOT, **({"width": target} if target is not None else {})}
    tag = str(target)
    inked = render_line_plot({**sized, "title": probe}, root / f"inked-{tag}.png")
    blank = render_line_plot({**sized, "title": " " * len(probe)}, root / f"blank-{tag}.png")
    with Image.open(inked) as one, Image.open(blank) as two:
        canvas_pixels = one.size[0]
        box = ImageChops.difference(one.convert("L"), two.convert("L")).getbbox()
    if box is None:
        raise AssertionError("the title drew no ink at all")
    points_per_pixel = (target if target is not None else 450.0) / canvas_pixels
    return (box[3] - box[1]) * points_per_pixel


def _figure_solution(figure: dict, *, sections: int = 1) -> dict:
    body = " ".join(f"Sentence {n} describing the measured cooling behaviour." for n in range(14))
    return {
        "document_type": "worked_problem",
        "title": "Cooling Study",
        "sections": [
            {"heading": f"Section {i}", "body": body, "figures": [dict(figure)]}
            for i in range(1, sections + 1)
        ],
        "calculations": [],
        "unresolved": [],
    }


def _write_image(root: Path, size: tuple[int, int], name: str = "plot.png") -> str:
    path = root / "figures" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, "white").save(path)
    return f"figures/{name}"


def _pdf_figure_points(path: Path) -> list[tuple[float, float]]:
    """Every figure placement in the document, as (width, height) in points."""
    placements = []
    for page in PdfReader(str(path)).pages:
        stream = page.get_contents().get_data().decode("latin-1")
        placements.extend((float(w), float(h)) for w, h in _PLACEMENT.findall(stream))
    return placements


class PlotLegibilityTests(unittest.TestCase):
    def test_shrinking_a_figure_does_not_shrink_its_text(self):
        """Halving a figure must not halve the words printed inside it.

        On origin/main the plot canvas is a fixed 1000x650 regardless of the size
        asked for, so the only way to make a figure physically smaller was to
        scale the whole image down and the text went with it.  Measured against
        origin/main this ratio is 0.47 -- text shrinking in exact proportion to
        the figure, which is precisely the defect.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            large = _title_points(root, 450)
            small = _title_points(root, 210)
            area_ratio = (210 / 450) ** 2
            self.assertLess(area_ratio, 0.25, "the small figure should be far smaller in area")
            self.assertGreaterEqual(
                small / large, 0.7,
                f"text shrank with the figure: {small:.2f}pt at 210pt vs {large:.2f}pt at 450pt",
            )

    def test_text_is_legible_at_every_target_size(self):
        """The floor holds at the default size and at a deliberately dense one."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for target in (None, 450, 330, 210, 150):
                with self.subTest(target=target):
                    points = _title_points(root, target)
                    self.assertGreaterEqual(
                        points, LEGIBLE_POINTS,
                        f"title renders at {points:.2f}pt on the page at target {target}",
                    )

    def test_a_long_title_stays_inside_a_small_figure(self):
        """Legible but clipped satisfies the requirement no better than tiny.

        The requirement behind issue #29 is that the material, the finish, the
        computed average and the handbook value appear *on the graph*.  Enlarging
        the text to reach the floor above is only half of that: at a narrow
        target the title then ran off both edges of the canvas and the numbers
        were still missing from the artifact.  A visual inspection caught this
        after the legibility assertions were already green, which is why the
        rendered page is checked and not only the measurements.

        This one is a guard on the new behaviour rather than a reproduction of
        the old: on origin/main it passes vacuously, because the declared target
        is ignored and the title is drawn on a canvas that is always 1000px wide.
        """
        long_title = "Ground finish, Ra 1.6 um, h_avg = 742 W/m2K (handbook 700)"
        with tempfile.TemporaryDirectory() as directory:
            for target in (450, 300, 210, 150):
                with self.subTest(target=target):
                    plain = render_line_plot(
                        {**PLOT, "width": target, "title": " "},
                        Path(directory) / f"plain-{target}.png",
                    )
                    titled = render_line_plot(
                        {**PLOT, "width": target, "title": long_title},
                        Path(directory) / f"titled-{target}.png",
                    )
                    with Image.open(plain) as one, Image.open(titled) as two:
                        canvas = two.size
                        ink = ImageChops.difference(one.convert("L"), two.convert("L")).getbbox()
                    self.assertIsNotNone(ink)
                    self.assertGreater(ink[0], 0, f"title ink touches the left edge at {target}pt")
                    self.assertLess(ink[2], canvas[0], f"title ink touches the right edge at {target}pt")
                    self.assertLess(ink[3], canvas[1], "title ink runs off the bottom")

    def test_a_target_too_small_to_draw_readably_is_refused(self):
        """Better to refuse than to emit a figure whose axes have no room for labels."""
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                render_line_plot({**PLOT, "width": 24}, Path(directory) / "tiny.png")

    def test_malformed_plot_target_sizes_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for bad in (0, -300, True, "300", float("nan"), 10_000):
                with self.subTest(bad=bad):
                    with self.assertRaises(ValueError):
                        render_line_plot({**PLOT, "width": bad}, root / "bad.png")


class EndToEndLegibilityTests(unittest.TestCase):
    """Measure the text on the page of a real PDF, not the plot in isolation.

    Every other legibility assertion here converts pixels to points using the
    plot's own declared target.  That is only the size on the page if the figure
    embedding the plot declares the same number, so this test takes the scale
    from the PDF's own placement matrix instead and closes the loop: plot
    rendered, figure embedded, PDF built, ink measured against what the page
    actually draws.

    The mismatched case -- a 210pt plot in a figure declaring 150pt, which drew
    its title near 2.9pt -- is now refused by the renderer (issue #36); see
    ``test_plot_physical_size``.
    """

    def test_a_plot_embedded_at_its_own_target_is_legible_on_the_page(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            figures = root / "figures"
            figures.mkdir(parents=True)
            for target in (450, 300, 210):
                with self.subTest(target=target):
                    sized = {**PLOT, "width": target}
                    inked = render_line_plot({**sized, "title": "Hxy"}, figures / f"i{target}.png")
                    blank = render_line_plot({**sized, "title": "   "}, figures / f"b{target}.png")
                    with Image.open(inked) as one, Image.open(blank) as two:
                        canvas_pixels = one.size[0]
                        box = ImageChops.difference(one.convert("L"), two.convert("L")).getbbox()
                    output = root / "deliverables" / f"page{target}.pdf"
                    render_text_pdf(
                        _figure_solution({
                            "path": f"figures/i{target}.png", "caption": "Figure 1.", "width": target,
                        }),
                        output, style_profile={"rendering": dict(BASE_RENDERING)},
                    )
                    drawn_width = _pdf_figure_points(output)[0][0]
                    on_page = (box[3] - box[1]) * drawn_width / canvas_pixels
                    self.assertAlmostEqual(drawn_width, float(target), places=2)
                    self.assertGreaterEqual(
                        on_page, LEGIBLE_POINTS,
                        f"title renders at {on_page:.2f}pt on a real page at target {target}",
                    )


class DeclaredFigureSizeTests(unittest.TestCase):
    def test_pdf_draws_a_figure_at_its_declared_size(self):
        """origin/main computes its own scale and discards these keys entirely."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            path = _write_image(root, (240, 160))
            output = root / "deliverables" / "declared.pdf"
            render_text_pdf(
                _figure_solution({"path": path, "caption": "Figure 1.", "width": 120}),
                output, style_profile={"rendering": dict(BASE_RENDERING)},
            )
            self.assertEqual(_pdf_figure_points(output), [(120.0, 80.0)])

    def test_pdf_leaves_an_undeclared_figure_exactly_where_it_was(self):
        """The default path must not move, or the page budget silently reflows.

        A figure that declares no size is still drawn at the pre-change size, so
        every existing page-count assertion keeps its meaning.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            path = _write_image(root, (240, 160))
            output = root / "deliverables" / "undeclared.pdf"
            render_text_pdf(
                _figure_solution({"path": path, "caption": "Figure 1."}),
                output, style_profile={"rendering": dict(BASE_RENDERING)},
            )
            self.assertEqual(_pdf_figure_points(output), [(240.0, 160.0)])

    def test_docx_draws_a_declared_figure_at_the_same_size_as_the_pdf(self):
        """One declared number has to mean one physical size in both renderers."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            path = _write_image(root, (240, 160))
            figure = {"path": path, "caption": "Figure 1.", "width": 120}
            pdf = root / "deliverables" / "both.pdf"
            docx = root / "deliverables" / "both.docx"
            profile = {"rendering": dict(BASE_RENDERING)}
            render_text_pdf(_figure_solution(figure), pdf, style_profile=profile)
            render_text_docx(_figure_solution(figure), docx, style_profile=profile)
            shape = Document(str(docx)).inline_shapes[0]
            self.assertEqual(
                (round(shape.width.pt, 2), round(shape.height.pt, 2)), _pdf_figure_points(pdf)[0]
            )

    def test_a_declared_size_is_a_bounding_box_and_never_distorts_the_figure(self):
        """Whichever dimension binds, the image keeps its 3:2 aspect ratio."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            path = _write_image(root, (240, 160))
            profile = {"rendering": dict(BASE_RENDERING)}
            for declared, expected in (
                ({"width": 120}, (120.0, 80.0)),
                ({"height": 80}, (120.0, 80.0)),
                ({"width": 120, "height": 300}, (120.0, 80.0)),
                ({"width": 400, "height": 80}, (120.0, 80.0)),
            ):
                with self.subTest(declared=declared):
                    output = root / "deliverables" / "box.pdf"
                    render_text_pdf(
                        _figure_solution({"path": path, "caption": "Figure 1.", **declared}),
                        output, style_profile=profile,
                    )
                    self.assertEqual(_pdf_figure_points(output), [expected])

    def test_a_figure_declared_larger_than_the_printable_area_is_refused(self):
        """Silently reducing a declared size is the defect, not the remedy."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            path = _write_image(root, (240, 160))
            output = root / "deliverables" / "oversize.pdf"
            for declared in ({"width": 600}, {"height": 400}):
                with self.subTest(declared=declared):
                    with self.assertRaises(ValueError) as caught:
                        render_text_pdf(
                            _figure_solution({"path": path, "caption": "Figure 1.", **declared}),
                            output, style_profile={"rendering": dict(BASE_RENDERING)},
                        )
                    self.assertIn("printable area", str(caught.exception))

    def test_malformed_figure_sizes_are_rejected_by_both_renderers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            path = _write_image(root, (240, 160))
            profile = {"rendering": dict(BASE_RENDERING)}
            for bad in (0, -120, True, "120", float("inf")):
                for renderer, name in ((render_text_pdf, "bad.pdf"), (render_text_docx, "bad.docx")):
                    with self.subTest(bad=bad, renderer=renderer.__name__):
                        with self.assertRaises(ValueError):
                            renderer(
                                _figure_solution({"path": path, "caption": "F.", "width": bad}),
                                root / "deliverables" / name, style_profile=profile,
                            )


class PageBudgetInteractionTests(unittest.TestCase):
    """The point of the whole change: the budget and legibility stop excluding each other."""

    def _render(self, root: Path, declared: dict, budget: int) -> Path:
        path = _write_image(root, (1000, 650))
        output = root / "deliverables" / "budget.pdf"
        rendering = {**BASE_RENDERING, "max_body_pages": budget}
        render_text_pdf(
            _figure_solution({"path": path, "caption": "Figure.", **declared}, sections=3),
            output, style_profile={"rendering": rendering},
        )
        return output

    def test_default_sized_figures_overrun_a_two_page_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            with self.assertRaises(ValueError) as caught:
                self._render(root, {}, 2)
            self.assertIn("at most 2", str(caught.exception))

    def test_declaring_a_smaller_figure_brings_the_same_body_within_budget(self):
        """On origin/main there is no way to do this: the keys change nothing.

        Same prose, same three figures, same limit -- only the declared figure
        size differs, and that is now enough to satisfy the instructor's limit
        while the figures stay readable (see PlotLegibilityTests).
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "run"
            output = self._render(root, {"width": 150}, 2)
            self.assertTrue(output.exists())
            self.assertEqual(_pdf_figure_points(output), [(150.0, 97.5)] * 3)


if __name__ == "__main__":
    unittest.main()
