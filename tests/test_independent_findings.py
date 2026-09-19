"""Findings from an independent adversarial test pass by a different model.

A second model was asked to break the student-facing checks, knowing only the
modules and what they promise.  Four of its six findings were real and are
pinned here.  Two were not, and the correct behaviour is pinned instead, so
neither is later "fixed" in the wrong direction.
"""

import json
import tempfile
import unittest
from pathlib import Path

from engineering_assistant.curriculum import CurriculumError, SCHEMA_VERSION, load_pack
from engineering_assistant.memory import record_observation
from engineering_assistant.review import classify_discrepancy, review_step
from engineering_assistant.units import UnitError, convert, dimension_of


class RealFindingTests(unittest.TestCase):
    def test_a_temperature_difference_cannot_become_an_absolute_reading(self):
        # 10 deltaF converted to degF returned a plausible absolute temperature
        # that means nothing.
        for source, target in (("deltaF", "degF"), ("deltaC", "degC"), ("degC", "deltaC")):
            with self.subTest(source=source, target=target):
                with self.assertRaises(UnitError):
                    convert(10, source, target)

    def test_a_difference_still_converts_between_difference_scales(self):
        # The benign case: differences convert to each other and to K.
        self.assertAlmostEqual(convert(18, "deltaF", "deltaC"), 10.0)
        self.assertAlmostEqual(convert(10, "deltaC", "K"), 10.0)

    def test_the_tolerance_is_measured_against_the_correct_value(self):
        # math.isclose measured against the larger number, so 102.01 passed as
        # "within 2%" of 100 though it is 2.01% off.
        step = {"id": "b", "method": "F / A",
                "inputs": {"F": {"value": 100, "unit": "N"}, "A": {"value": 1, "unit": "m^2"}},
                "student_answer": {"value": 102.01, "unit": "Pa"}}
        self.assertFalse(review_step(step)["correct"])
        step["student_answer"]["value"] = 101.99
        self.assertTrue(review_step(step)["correct"])

    def test_a_policy_needs_a_source_and_a_summary(self):
        # "stated" with nothing else reads as a known rule nobody can check.
        pack = {"schema_version": SCHEMA_VERSION,
                "coverage": {"format": "none", "methods": "none", "assignments": "none"},
                "course_policy": {"confidence": "stated"}}
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "pack.json"
            path.write_text(json.dumps(pack))
            with self.assertRaises(CurriculumError):
                load_pack(path)

    def test_judgements_phrased_without_the_obvious_words_are_refused(self):
        # A word list cannot be complete; these are the phrasings that slipped
        # past the first one.
        for topic in ("has difficulty with unit conversions", "tends to drop signs",
                      "keeps confusing kPa and Pa", "doesn't understand ratios"):
            with self.subTest(topic=topic):
                with tempfile.TemporaryDirectory() as d:
                    with self.assertRaises(ValueError):
                        record_observation(Path(d), "engr205", topic, "percent")

    def test_ordinary_work_topics_are_still_accepted(self):
        # A filter that refuses honest topics is its own failure.
        for topic in ("strain units, lab 3", "relaxation modulus, polymer lab",
                      "hitch preload", "pitot tube velocity"):
            with self.subTest(topic=topic):
                with tempfile.TemporaryDirectory() as d:
                    record_observation(Path(d), "engr205", topic, "percent")


class RebuttedFindingTests(unittest.TestCase):
    def test_two_slashes_mean_what_division_means(self):
        # Rebutted.  Division is left-associative, so kJ/kg/K is (kJ/kg)/K,
        # which is kJ/(kg K): one quantity, not two readings.  Refusing it
        # would reject a correct unit students write routinely.
        self.assertEqual(dimension_of("kJ/kg/K"), dimension_of("kJ/kg-K"))
        self.assertAlmostEqual(convert(1, "kJ/kg/K", "J/kg-K"), 1000.0)

    def test_a_dimensionless_thousandfold_error_can_be_a_unit_prefix(self):
        # Rebutted.  A dimensionless answer is usually a ratio of quantities
        # that have units: a strain from a length change in mm over a length
        # in m is a thousand times off.  The cause stays; the hint now points
        # at the quantities in the ratio rather than at the answer's unit.
        causes = classify_discrepancy(0.001, 1.0, True, False)
        prefix = [c for c in causes if c["cause"] == "unit prefix"]
        self.assertTrue(prefix)
        self.assertIn("ratio", prefix[0]["hint"])


if __name__ == "__main__":
    unittest.main()
