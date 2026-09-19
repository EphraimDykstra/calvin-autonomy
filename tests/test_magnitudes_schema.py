"""The loader must refuse a plausibility range a review cannot use.

tests/test_pack_magnitudes.py checks the ranges in this tree.  That leaves the
pack nobody has written yet unchecked, which is the one that matters: a pack a
student or a contributor adds is exactly the pack no shipped-pack test ever
sees, and `magnitudes` drives the only check that catches a strain of 5 where
0.05 belongs.

Two failures are worth the code.  An inverted range makes `low <= value <=
high` false for every value, so a correct answer is flagged and a student
taught by false alarms learns to ignore the check.  A unit the engine cannot
read does not degrade to "no check": review.py converts into that unit and
catches the UnitError into the step's `error`, so every review naming the
quantity reports an error to the student instead of a review.
"""

import json
import tempfile
import unittest
from pathlib import Path

from engineering_assistant.curriculum import (
    CurriculumError,
    MAGNITUDE_BASIS_KINDS,
    SCHEMA_VERSION,
    load_pack,
)
from engineering_assistant.review import review_step


def _entry(**overrides):
    entry = {
        "quantity": "yield strength of mild steel",
        "unit": "MPa",
        "typical_range": [200, 400],
        "basis": "Physical plausibility, not a course rule.",
        "note": "A value far outside this is usually a unit slip.",
    }
    entry.update(overrides)
    return entry


def _pack(magnitudes, **overrides):
    pack = {
        "schema_version": SCHEMA_VERSION,
        "course": {"id": "engr000", "code": "ENGR 000", "title": "Example Course"},
        "coverage": {
            "format": "none",
            "methods": "none",
            "assignments": "none",
            "notes": "Nothing is evidenced.",
        },
        "course_policy": {
            "source": "syllabus",
            "confidence": "unknown",
            "summary": "No policy was found.",
        },
        "assignment_families": [],
        "magnitudes": magnitudes,
    }
    pack.update(overrides)
    return pack


class MagnitudeSchemaTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _write(self, pack):
        path = self.root / "pack.json"
        path.write_text(json.dumps(pack), encoding="utf-8")
        return path

    def _refuses(self, magnitudes, expected):
        with self.assertRaises(CurriculumError) as caught:
            load_pack(self._write(_pack(magnitudes)))
        self.assertIn(expected, str(caught.exception))

    # -- the benign answers stay reachable ---------------------------------

    def test_a_pack_with_no_magnitudes_loads(self):
        pack = _pack([])
        del pack["magnitudes"]
        self.assertNotIn("magnitudes", load_pack(self._write(pack)))

    def test_an_empty_list_loads(self):
        # A course with no plausibility bounds is an honest absence.
        self.assertEqual(load_pack(self._write(_pack([])))["magnitudes"], [])

    def test_a_complete_entry_loads(self):
        loaded = load_pack(self._write(_pack([_entry()])))
        self.assertEqual(loaded["magnitudes"][0]["unit"], "MPa")

    def test_every_basis_kind_is_reachable(self):
        for kind in MAGNITUDE_BASIS_KINDS:
            with self.subTest(basis=kind):
                entry = _entry(basis=f"{kind}: stated on the lab handout.")
                self.assertTrue(load_pack(self._write(_pack([entry])))["magnitudes"])

    # -- every field is load bearing ---------------------------------------

    def test_an_unknown_key_is_refused(self):
        self._refuses([_entry(tolerance=0.1)], "unknown key")

    def test_a_missing_field_is_refused(self):
        for key in ("quantity", "unit", "basis", "note"):
            with self.subTest(missing=key):
                entry = _entry()
                del entry[key]
                self._refuses([entry], f"needs a non-empty {key}")

    def test_a_blank_field_is_refused(self):
        self._refuses([_entry(note="   ")], "needs a non-empty note")

    def test_an_entry_that_is_not_an_object_is_refused(self):
        self._refuses(["yield strength"], "must be an object")

    def test_magnitudes_that_is_not_a_list_is_refused(self):
        self._refuses({"quantity": "x"}, "magnitudes must be a list")

    # -- the range has to be a range ---------------------------------------

    def test_an_inverted_range_is_refused(self):
        # The dangerous direction: every value falls outside, so the check
        # flags correct answers and teaches a student to ignore it.
        self._refuses([_entry(typical_range=[400, 200])], "flags every answer")

    def test_an_empty_range_is_refused(self):
        self._refuses([_entry(typical_range=[200, 200])], "flags every answer")

    def test_a_range_of_the_wrong_length_is_refused(self):
        for bounds in ([200], [200, 300, 400], []):
            with self.subTest(typical_range=bounds):
                self._refuses([_entry(typical_range=bounds)], "list of two numbers")

    def test_a_non_numeric_bound_is_refused(self):
        for bounds in (["200", 400], [None, 400], [True, 400]):
            with self.subTest(typical_range=bounds):
                self._refuses([_entry(typical_range=bounds)], "finite numbers")

    def test_an_infinite_bound_is_refused(self):
        # json.dumps writes bare Infinity, which json.loads reads back as a
        # float, so this reaches the loader rather than failing to serialise.
        self._refuses([_entry(typical_range=[200, float("inf")])], "finite numbers")

    def test_a_negative_range_is_allowed(self):
        # Plenty of real quantities are negative.  The rule is ordering, not
        # sign, and a sign rule would refuse honest evidence.
        entry = _entry(quantity="residual compressive stress", typical_range=[-400, -200])
        self.assertTrue(load_pack(self._write(_pack([entry])))["magnitudes"])

    # -- a bound says what kind of bound it is -----------------------------

    def test_a_basis_that_names_no_kind_is_refused(self):
        self._refuses([_entry(basis="It seemed about right.")], "basis must open with")

    def test_physics_may_not_be_dressed_as_a_course_rule(self):
        # The field exists to keep these apart.  A student told the course
        # requires a value learns a rule that does not exist.
        message = "whether physics or the course is what sets it"
        self._refuses([_entry(basis="The professor probably wants this.")], message)

    # -- a review must be able to use the entry ----------------------------

    def test_a_unit_the_engine_cannot_read_is_refused(self):
        self._refuses([_entry(unit="dB")], "not one the unit engine reads")

    def test_the_refusal_says_the_registry_may_be_what_is_short(self):
        # A contributor with a legitimate dB bound must be pointed at the
        # registry, not left to delete good evidence to get a pack loading.
        self._refuses([_entry(unit="dB")], "Add the unit to the registry")

    def test_a_repeated_quantity_is_refused(self):
        # review.py takes the first match, so the second entry is a range
        # someone wrote, and believes is applied, that never runs.
        self._refuses([_entry(), _entry(typical_range=[1, 2])], "quantity repeats")

    def test_a_repeated_quantity_would_really_be_unreachable(self):
        # Proves the reason the check exists rather than asserting it: the
        # first entry's range is what a review applies, and 250 MPa is inside
        # it while being far outside the second entry's 1 to 2.
        first, second = _entry(), _entry(typical_range=[1, 2])
        step = {
            "id": "s1",
            "method": "sigma",
            "inputs": {"sigma": {"value": 250, "unit": "MPa"}},
            "student_answer": {"value": 250, "unit": "MPa"},
            "magnitude": "yield strength of mild steel",
        }
        result = review_step(step, [first, second])
        self.assertEqual(result["magnitude"]["range"], [200, 400])
        self.assertTrue(result["magnitude"]["plausible"])


if __name__ == "__main__":
    unittest.main()
