"""A search that finds nothing has to say which kind of nothing it found.

`search` used to return a bare `[]` for every miss.  That is silence in the
same shape a hit arrives in, and silence is what a model fills with a guess:
a host that cannot tell "this course's material was searched and does not
contain this" from "nothing has been indexed for this course" will answer the
second as though it were the first, from general knowledge, which is the one
thing this project exists to stop.

So a miss is structurally unlike a hit.  It carries no `results` key at all,
it names a status the caller cannot read as results, and it shows the work:
which course, how many documents and blocks were actually searched.  Zero
blocks searched is not evidence of absence, and the envelope makes that
readable rather than something a caller has to already know.
"""

import tempfile
import unittest
from pathlib import Path

from engineering_assistant.ingest import ingest, search


class SearchStatusTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.workspace = root / "workspace"
        self.source = root / "source"
        self.source.mkdir(parents=True)
        self.addCleanup(self._tmp.cleanup)

    def _ingest(self, name="notes.md", text="Steady-state heat flux through the wall.\n"):
        (self.source / name).write_text(text, encoding="utf-8")
        return ingest(self.source, self.workspace, "demo")

    # -- a hit still looks like a hit --------------------------------------

    def test_a_hit_carries_its_results_and_the_found_status(self):
        self._ingest()
        found = search(self.workspace, "demo", "heat flux")
        self.assertEqual(found["status"], "found")
        self.assertEqual(found["results"][0]["locator"], "line:1")
        self.assertEqual(found["course"], "demo")
        self.assertEqual(found["query"], "heat flux")

    def test_a_hit_reports_what_was_searched(self):
        self._ingest()
        found = search(self.workspace, "demo", "heat flux")
        self.assertEqual(found["documents_searched"], 1)
        self.assertGreaterEqual(found["blocks_searched"], 1)

    def test_the_limit_still_bounds_the_results(self):
        self._ingest(text="flux one\nflux two\nflux three\n")
        found = search(self.workspace, "demo", "flux", limit=2)
        self.assertEqual(len(found["results"]), 2)
        # The count is the work done, not the results returned.  A caller
        # that sees 2 of 3 must be able to tell that a limit was applied.
        self.assertEqual(found["blocks_searched"], 3)

    # -- the three kinds of nothing ----------------------------------------

    def test_indexed_material_that_does_not_match_is_no_match(self):
        self._ingest()
        missed = search(self.workspace, "demo", "thermodynamic availability")
        self.assertEqual(missed["status"], "no_match")
        # The claim this status is allowed to support: text was read, and the
        # terms are not in it.
        self.assertGreaterEqual(missed["blocks_searched"], 1)

    def test_a_course_with_no_catalog_is_not_a_miss(self):
        missed = search(self.workspace, "demo", "heat flux")
        self.assertEqual(missed["status"], "no_catalog")
        self.assertEqual(missed["documents_searched"], 0)
        self.assertEqual(missed["blocks_searched"], 0)

    def test_a_course_whose_documents_carry_no_text_is_not_a_miss(self):
        # An image needs OCR, so it is a document with nothing to search.
        # Reporting that as "no match" would turn a pending task into a
        # finding about the course.
        from PIL import Image

        Image.new("RGB", (40, 20), "white").save(self.source / "scan.png")
        ingest(self.source, self.workspace, "demo")
        missed = search(self.workspace, "demo", "heat flux")
        self.assertEqual(missed["status"], "nothing_indexed")
        self.assertEqual(missed["blocks_searched"], 0)

    def test_the_two_kinds_of_empty_are_different_statuses(self):
        # The distinction is the whole point, so assert it directly rather
        # than trusting two separate tests to stay in step.
        empty = search(self.workspace, "demo", "heat flux")["status"]
        self._ingest()
        searched = search(self.workspace, "demo", "thermodynamic availability")["status"]
        self.assertNotEqual(empty, searched)

    # -- a miss cannot be mistaken for results -----------------------------

    def test_no_miss_carries_a_results_key(self):
        self._ingest()
        for query, expected in (("thermodynamic availability", "no_match"),):
            with self.subTest(status=expected):
                missed = search(self.workspace, "demo", query)
                self.assertEqual(missed["status"], expected)
                self.assertNotIn("results", missed)

    def test_a_miss_with_no_catalog_carries_no_results_key(self):
        self.assertNotIn("results", search(self.workspace, "demo", "heat flux"))

    def test_every_miss_says_what_to_do_next(self):
        # Without this the host knows it failed and not what that means, and
        # the three misses call for three different actions.
        no_catalog = search(self.workspace, "demo", "heat flux")
        self._ingest()
        no_match = search(self.workspace, "demo", "thermodynamic availability")
        for missed in (no_catalog, no_match):
            with self.subTest(status=missed["status"]):
                self.assertTrue(missed["next"].strip())
        self.assertNotEqual(no_catalog["next"], no_match["next"])

    def test_the_no_match_guidance_forbids_answering_from_general_knowledge(self):
        # The specific failure the envelope exists to prevent, asserted so a
        # future edit cannot soften it into a neutral "nothing found".
        self._ingest()
        guidance = search(self.workspace, "demo", "thermodynamic availability")["next"]
        self.assertIn("general knowledge", guidance)

    def test_a_status_that_searched_nothing_says_it_is_not_absence(self):
        guidance = search(self.workspace, "demo", "heat flux")["next"]
        self.assertIn("nothing was searched", guidance)

    # -- a caller error is an error, not a status --------------------------

    def test_an_empty_query_is_refused(self):
        # Neither "no results" nor "found nothing": the caller asked wrong,
        # and returning a miss would let that pass as evidence about a course.
        for query in ("", "   "):
            with self.subTest(query=query):
                with self.assertRaises(ValueError):
                    search(self.workspace, "demo", query)

    def test_a_non_positive_limit_is_refused(self):
        for limit in (0, -1):
            with self.subTest(limit=limit):
                with self.assertRaises(ValueError):
                    search(self.workspace, "demo", "heat flux", limit=limit)


if __name__ == "__main__":
    unittest.main()
