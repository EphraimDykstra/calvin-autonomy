"""Plausibility ranges in the shipped packs must be honest about what they are.

A range is a magnitude check, not a course rule.  A strain entered as 5 where
0.05 belongs is a valid dimensionless number and passes every arithmetic and
unit check, so only magnitude sense catches it.  That makes the ranges worth
shipping, and it also makes a mislabelled or inverted range dangerous: a host
would flag a correct answer, and a student taught by false alarms learns to
ignore the check.
"""

import json
import math
import unittest
from pathlib import Path

from engineering_assistant.curriculum import MAGNITUDE_BASIS_KINDS


CURRICULUM = Path(__file__).resolve().parents[1] / "curriculum"

REQUIRED = ("quantity", "unit", "typical_range", "basis", "note")

# The loader owns both of these now.  Imported rather than restated, because
# two spellings of one rule is how a pack ends up satisfying the copy that was
# not the one being enforced.
BASIS_KINDS = MAGNITUDE_BASIS_KINDS


def _entries():
    for path in sorted(CURRICULUM.glob("*/pack.json")):
        pack = json.loads(path.read_text(encoding="utf-8"))
        for entry in pack.get("magnitudes", []) or []:
            yield path.parent.name, entry


class MagnitudeTests(unittest.TestCase):
    def test_some_pack_carries_magnitudes(self):
        # Guards against the glob or the key name silently matching nothing.
        self.assertTrue(list(_entries()))

    def test_every_entry_is_complete(self):
        for pack_id, entry in _entries():
            with self.subTest(pack=pack_id, quantity=entry.get("quantity")):
                for key in REQUIRED:
                    value = entry.get(key)
                    if key == "typical_range":
                        continue
                    self.assertTrue(
                        isinstance(value, str) and value.strip(),
                        f"{pack_id}: magnitudes entry needs a non-empty '{key}'",
                    )

    def test_range_is_two_ordered_finite_numbers(self):
        for pack_id, entry in _entries():
            with self.subTest(pack=pack_id, quantity=entry.get("quantity")):
                bounds = entry.get("typical_range")
                self.assertIsInstance(bounds, list)
                self.assertEqual(len(bounds), 2)
                low, high = bounds
                for bound in (low, high):
                    self.assertIsInstance(bound, (int, float))
                    self.assertNotIsInstance(bound, bool)
                    self.assertTrue(math.isfinite(bound))
                self.assertLess(low, high, f"{pack_id}: an inverted range flags every answer")

    def test_basis_says_what_kind_of_bound_it_is(self):
        for pack_id, entry in _entries():
            with self.subTest(pack=pack_id, quantity=entry.get("quantity")):
                self.assertTrue(
                    entry["basis"].startswith(BASIS_KINDS),
                    f"{pack_id}: basis must open with one of {BASIS_KINDS}",
                )


if __name__ == "__main__":
    unittest.main()
