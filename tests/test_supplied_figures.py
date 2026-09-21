"""A figure the student sends gets into the run, and stays what it was.

A solution may reference a figure only by a path inside its own run, and nothing
put one there: a host had to copy the file by hand, with nothing checking what
it copied. These tests cover the arrival of that file and the one thing that
must not go unnoticed afterwards, a swap.
"""

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from engineering_assistant.common import sha256
from engineering_assistant.runtime import (
    add_supplied_figure,
    load_run,
    run_dir,
    start_run,
    status_run,
)


def _image(path, colour="white"):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (120, 80), colour).save(path)
    return path


class SuppliedFigureTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.ws = self.root / "ws"
        self.source = self.root / "assignment.txt"
        self.source.write_text("Report the coefficient of performance.")
        start_run(self.ws, "r1", "engr328", self.source)
        self.run_root = run_dir(self.ws, "r1")

    def test_a_supplied_image_lands_inside_the_run_and_is_recorded(self):
        chart = _image(self.root / "incoming" / "ph-chart.png")
        result = add_supplied_figure(self.ws, "r1", chart)
        placed = self.run_root / "figures" / "ph-chart.png"
        self.assertTrue(placed.is_file())
        self.assertEqual(result["figure"], {"path": "figures/ph-chart.png", "sha256": sha256(chart)})
        self.assertEqual(load_run(self.ws, "r1")["supplied_figures"], [result["figure"]])

    def test_it_is_copied_not_referenced(self):
        """The run has to stand on its own bytes, not on a file elsewhere."""
        chart = _image(self.root / "incoming" / "ph-chart.png")
        add_supplied_figure(self.ws, "r1", chart)
        chart.unlink()
        self.assertTrue((self.run_root / "figures" / "ph-chart.png").is_file())
        self.assertNotIn(
            "a supplied figure is missing or changed: figures/ph-chart.png",
            status_run(self.ws, "r1")["readiness"]["blockers"],
        )

    def test_a_swapped_figure_becomes_a_blocker(self):
        chart = _image(self.root / "incoming" / "ph-chart.png")
        add_supplied_figure(self.ws, "r1", chart)
        _image(self.run_root / "figures" / "ph-chart.png", colour="black")
        self.assertIn(
            "a supplied figure is missing or changed: figures/ph-chart.png",
            status_run(self.ws, "r1")["readiness"]["blockers"],
        )

    def test_a_deleted_figure_becomes_a_blocker(self):
        chart = _image(self.root / "incoming" / "ph-chart.png")
        add_supplied_figure(self.ws, "r1", chart)
        (self.run_root / "figures" / "ph-chart.png").unlink()
        self.assertIn(
            "a supplied figure is missing or changed: figures/ph-chart.png",
            status_run(self.ws, "r1")["readiness"]["blockers"],
        )

    def test_replacing_a_figure_under_the_same_name_records_the_new_bytes(self):
        first = _image(self.root / "incoming" / "ph-chart.png")
        add_supplied_figure(self.ws, "r1", first)
        second = _image(self.root / "incoming2" / "ph-chart.png", colour="black")
        add_supplied_figure(self.ws, "r1", second)
        figures = load_run(self.ws, "r1")["supplied_figures"]
        self.assertEqual(len(figures), 1)
        self.assertEqual(figures[0]["sha256"], sha256(second))
        self.assertNotIn(
            "a supplied figure is missing or changed: figures/ph-chart.png",
            status_run(self.ws, "r1")["readiness"]["blockers"],
        )

    def test_a_file_that_is_not_an_image_is_refused(self):
        text = self.root / "incoming" / "notes.png"
        text.parent.mkdir(parents=True, exist_ok=True)
        text.write_text("This is not an image.")
        with self.assertRaises(ValueError) as caught:
            add_supplied_figure(self.ws, "r1", text)
        self.assertIn("image", str(caught.exception))

    def test_a_name_cannot_escape_the_run(self):
        chart = _image(self.root / "incoming" / "ph-chart.png")
        for name in ("../escape.png", "/tmp/escape.png", "../../escape.png"):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    add_supplied_figure(self.ws, "r1", chart, name)

    def test_a_symlinked_source_is_refused(self):
        chart = _image(self.root / "incoming" / "ph-chart.png")
        link = self.root / "incoming" / "link.png"
        link.symlink_to(chart)
        with self.assertRaises(ValueError):
            add_supplied_figure(self.ws, "r1", link)

    def test_the_renderer_accepts_what_this_placed(self):
        """The two halves have to agree, or the file arrives and cannot be drawn."""
        from engineering_assistant.rendering import _safe_figure

        chart = _image(self.root / "incoming" / "ph-chart.png")
        record = add_supplied_figure(self.ws, "r1", chart)["figure"]
        self.assertEqual(_safe_figure(self.run_root, record["path"]).name, "ph-chart.png")


if __name__ == "__main__":
    unittest.main()
