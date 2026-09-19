"""The legend never hides data (#37).

Before #37 the legend was drawn on an opaque panel in the top right of the plot
area, and a data marker there disappeared under it.  Nothing looked wrong: the
plot simply had one fewer marker than the data table, which a reader cannot see
and a visual inspection is unlikely to catch.

The legend now sits in the band above the axes, beside the y-axis label, so it
cannot overlap drawn data by construction.  These tests do not assert where the
legend is.  They assert the property, against the rendered image:

* a marker placed where the legend used to sit leaves the same ink on the
  image as the same marker placed in open plot area, i.e. none of it is hidden;
* whatever the legend's text covers is blank canvas when the names are blank,
  so nothing drawn from the data sits underneath it.
"""
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageChops

from engineering_assistant.plots import render_line_plot

TARGETS = (450, 300, 210, 150)
# Bounds are held by these three points, so adding a fourth never moves the axes.
CORNERS = [(0.0, 0.0), (10.0, 0.0), (0.0, 10.0)]


def _render(root: Path, name: str, series: list, **spec) -> Image.Image:
    path = render_line_plot({"title": "Cooling curve", "series": series, **spec}, root / name)
    with Image.open(path) as image:
        return image.convert("L")


def _scatter(points, name="Measured"):
    return {"name": name, "x": [p[0] for p in points], "y": [p[1] for p in points], "connect": False}


def _ink(one: Image.Image, two: Image.Image) -> int:
    """Pixels that differ between two renders."""
    difference = ImageChops.difference(one, two).point(lambda value: 255 if value else 0)
    return difference.histogram()[255]


class LegendHidesNoMarkerTests(unittest.TestCase):
    def test_a_marker_in_the_top_right_corner_is_fully_drawn(self):
        """The #37 reproduction, measured on the image.

        On origin/main the top-right marker leaves no ink at all at 210pt and
        150pt: the legend panel is drawn over it.  At 450pt and 300pt a
        one-entry panel happens to miss this marker, so those two subtests pass
        on origin/main; the three-series test below fails there at 450pt.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for target in TARGETS:
                with self.subTest(target=target):
                    base = _render(root, "base.png", [_scatter(CORNERS)], width=target)
                    corner = _render(root, "corner.png", [_scatter(CORNERS + [(10.0, 10.0)])], width=target)
                    middle = _render(root, "middle.png", [_scatter(CORNERS + [(5.0, 5.0)])], width=target)
                    open_ink = _ink(base, middle)
                    self.assertGreater(open_ink, 0, "the reference marker drew nothing")
                    self.assertGreaterEqual(
                        _ink(base, corner), open_ink * 0.9,
                        f"the top-right marker lost ink at {target}pt: "
                        f"{_ink(base, corner)} pixels against {open_ink} in open plot area",
                    )

    def _assert_corner_marker_drawn(self, root: Path, others: list, **spec) -> None:
        base = _render(root, "base.png", [_scatter(CORNERS)] + others, **spec)
        corner = _render(root, "corner.png", [_scatter(CORNERS + [(10.0, 9.5)])] + others, **spec)
        middle = _render(root, "middle.png", [_scatter(CORNERS + [(5.0, 5.0)])] + others, **spec)
        self.assertGreater(_ink(base, middle), 0, "the reference marker drew nothing")
        self.assertGreaterEqual(_ink(base, corner), _ink(base, middle) * 0.9)

    def test_every_series_marker_survives_a_three_series_legend(self):
        """A taller legend reaches further down; every series' corner marker still shows.

        At 150pt three rows above the axes leave no readable plot, so the legend
        goes to a column right of the axes instead.  On origin/main every
        subtest fails: the panel covers the corner.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            others = [_scatter(CORNERS, "Model"), _scatter(CORNERS, "Handbook")]
            for target in (450, 210, 150):
                with self.subTest(target=target):
                    self._assert_corner_marker_drawn(root, others, width=target, y_label="Temperature [K]")

    def test_names_too_wide_to_sit_beside_the_label_still_hide_nothing(self):
        """The legend moves to rows of its own above the axes, not into them."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            others = [_scatter(CORNERS, "Lumped capacitance model fit")]
            for target in (300, 210):
                with self.subTest(target=target):
                    self._assert_corner_marker_drawn(
                        root, others, width=target, y_label="Surface temperature [K]",
                    )

    def test_a_legend_that_fits_nowhere_outside_the_axes_is_refused(self):
        """Better to refuse than to hide data or clip the legend.

        On origin/main this renders: the 45-character name runs off the left
        edge of a 150pt canvas and the panel hides the top of the data.
        """
        with tempfile.TemporaryDirectory() as directory:
            series = [_scatter(CORNERS, "Measured surface temperature, thermocouple 3")]
            with self.assertRaises(ValueError) as caught:
                _render(Path(directory), "refused.png", series, width=150, y_label="Temperature [K]")
            self.assertIn("legend", str(caught.exception))


class LegendCoversNothingTests(unittest.TestCase):
    def test_nothing_is_drawn_under_the_legend_text(self):
        """Blank the names: whatever their text covered must be empty canvas.

        The data zigzags across the whole plot area so that a legend anywhere
        inside the axes would sit on it.  This fails on origin/main at every
        target, because the legend is inside the axes.

        If blanking the name ever changed the legend's placement, the two
        renders would differ across the whole plot, the region would take in
        the data, and this would fail rather than pass: the comparison errs
        towards a false alarm, never a false pass.
        """
        zigzag = {"name": "Measured", "x": list(range(11)), "y": [0, 10] * 5 + [0]}
        blanked = {**zigzag, "name": " " * len(zigzag["name"])}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for target in TARGETS:
                with self.subTest(target=target):
                    named = _render(root, "named.png", [zigzag], width=target)
                    blank = _render(root, "blank.png", [blanked], width=target)
                    region = ImageChops.difference(named, blank).getbbox()
                    self.assertIsNotNone(region, "the legend drew no text")
                    under = blank.crop(region)
                    self.assertEqual(
                        under.getextrema(), (255, 255),
                        f"something is drawn under the legend text at {target}pt",
                    )

    def test_the_legend_does_not_move_the_plot_when_names_change(self):
        """Names that fit beside the label never reflow the plot.

        This is the premise that makes the blanked-name comparison above sound:
        blanking a name must change nothing but the name's own ink.  On
        origin/main it fails, because the panel was right-aligned to the name.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            short = _render(root, "short.png", [_scatter(CORNERS, "A")])
            long = _render(root, "long.png", [_scatter(CORNERS, "A much longer series name")])
            no_names_short = _render(root, "s0.png", [_scatter(CORNERS, " ")])
            no_names_long = _render(root, "l0.png", [_scatter(CORNERS, " " * 25)])
            self.assertIsNone(ImageChops.difference(no_names_short, no_names_long).getbbox())
            self.assertIsNotNone(ImageChops.difference(short, long).getbbox())


if __name__ == "__main__":
    unittest.main()
