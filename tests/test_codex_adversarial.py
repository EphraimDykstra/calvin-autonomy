"""Invariants an independent model chose to attack, kept as regression guards.

Written by a second model run blind against the engine.  Its run was made
against a stale worktree, so four of its six findings had already been fixed on
main and two were rebutted before, in tests/test_independent_findings.py, which
owns those two: a repeated solidus reads left to right, and "unit prefix" names
the mechanism behind a dimensionless thousand-fold error rather than claiming
the answer carries a prefix.  What remains here is the four cases that guard
behaviour this project promises, phrased by someone who was trying to break it.
"""

import json
import tempfile
import unittest
from pathlib import Path

from engineering_assistant.curriculum import CurriculumError, SCHEMA_VERSION, load_pack
from engineering_assistant.memory import record_observation
from engineering_assistant.review import review_step
from engineering_assistant.units import UnitError, convert


class UnitRefusalTests(unittest.TestCase):
    def test_temperature_difference_cannot_be_converted_to_an_absolute_scale(self):
        # A 10 deltaF change is not an absolute degF reading.  Returning an
        # offset absolute temperature makes a wrong temperature look converted.
        with self.assertRaises(UnitError):
            convert(10, "deltaF", "degF")


class ReviewFalseAssuranceTests(unittest.TestCase):
    def test_default_two_percent_limit_does_not_expand_past_two_percent(self):
        # A symmetric comparison would accept 102.01 as "within 2%" of 100
        # even though the student's relative error is 2.01%.
        step = {
            "id": "boundary",
            "method": "F / A",
            "inputs": {
                "F": {"value": 100, "unit": "N"},
                "A": {"value": 1, "unit": "m^2"},
            },
            "student_answer": {"value": 102.01, "unit": "Pa"},
        }
        self.assertFalse(review_step(step)["correct"])


class CurriculumFailClosedTests(unittest.TestCase):
    def test_pack_with_only_a_policy_confidence_is_refused(self):
        # Reporting a policy as "stated" without its source or summary is a
        # false course-policy claim, not a usable course pack.
        pack = {
            "schema_version": SCHEMA_VERSION,
            "coverage": {"format": "none", "methods": "none", "assignments": "none"},
            "course_policy": {"confidence": "stated"},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pack.json"
            path.write_text(json.dumps(pack), encoding="utf-8")
            with self.assertRaises(CurriculumError):
                load_pack(path)


class ObservationJudgementTests(unittest.TestCase):
    def test_a_trait_without_the_banned_words_is_refused(self):
        # Still an assessment of the student, even though it avoids the
        # obvious words (weak, careless, struggles, and so on).
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                record_observation(Path(directory), "engr205", "has difficulty with unit conversions", "percent")


if __name__ == "__main__":
    unittest.main()
