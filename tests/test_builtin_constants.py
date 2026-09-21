"""pi is available without being supplied, and a supplied pi still wins.

A review of any geometry or rotation problem needs pi, and the evaluator had
no constants, so every such step failed with "Missing variable: pi" before it
reached the student's actual mistake.  Two independent reports, a persona test
and a screw-jack step, hit it in the same place.

The interesting half is precedence.  A course can tell a student to use 3.14,
and then 3.14 is the number their work was done with: checking them against
3.14159 would report a discrepancy they did not make.  So a supplied value
wins.  It wins visibly, because the other case looks identical from inside the
check: a value of 3 is a typo, and a silent preference would confirm an answer
computed from a wrong constant.

Both are asserted here against the same worked example, because the pair is
the argument.
"""

import math
import unittest

from engineering_assistant.calculations import check_calculation, evaluate
from engineering_assistant.review import review_step
from engineering_assistant.units import (
    BUILTIN_CONSTANTS,
    DIMENSIONLESS,
    UnitError,
    expression_dimension,
    shadowed_constants,
)


def _area_step(pi_value=None, claimed=3.14):
    """The circle area of a 2 in bar: the shape of the reported defect."""
    inputs = {"d": {"value": 2, "unit": "in"}}
    if pi_value is not None:
        inputs["pi"] = {"value": pi_value, "unit": "dimensionless"}
    return {
        "id": "area",
        "method": "pi * d**2 / 4",
        "inputs": inputs,
        "student_answer": {"value": claimed, "unit": "in^2"},
        "tolerance": 1e-4,
    }


class BuiltInPiTests(unittest.TestCase):
    def test_review_resolves_pi_without_it_being_supplied(self):
        # The defect: this used to error with "Missing variable: pi" before it
        # could say anything about the student's answer.
        result = review_step(_area_step(claimed=3.1416))
        self.assertNotIn("error", result)
        self.assertAlmostEqual(result["actual"], math.pi, places=9)
        self.assertTrue(result["correct"])

    def test_verify_resolves_pi_in_dimensional_mode(self):
        result = check_calculation({
            "id": "c", "expression": "pi * r**2",
            "variables": {"r": {"value": 1, "unit": "m"}},
            "unit": "m^2", "expected": math.pi, "tolerance": 1e-9,
        })
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["mode"], "dimensional")

    def test_verify_resolves_pi_in_arithmetic_mode(self):
        # Both modes, identically: a constant that worked in one and not the
        # other would be a trap laid for whoever used the other.
        result = check_calculation({
            "id": "c", "expression": "2 * pi * 3", "variables": {},
            "unit": "dimensionless", "expected": 6 * math.pi, "tolerance": 1e-9,
        })
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["mode"], "arithmetic")

    def test_pi_is_dimensionless(self):
        self.assertEqual(expression_dimension("pi", {}), DIMENSIONLESS)

    def test_pi_carries_no_dimension_into_a_product(self):
        # If pi arrived with a dimension it would corrupt every expression it
        # appeared in, and the dimension check would reject correct work.
        self.assertEqual(
            expression_dimension("pi * r", {"r": (0.0, 1.0, 0.0, 0.0, 0.0, 0.0)}),
            (0.0, 1.0, 0.0, 0.0, 0.0, 0.0),
        )

    def test_the_value_is_the_real_one(self):
        self.assertEqual(evaluate("pi", {}), math.pi)

    def test_an_unknown_name_is_still_refused(self):
        # The built-in must not become a general permission to omit inputs.
        with self.assertRaises(ValueError):
            evaluate("tau", {})
        with self.assertRaises(UnitError):
            expression_dimension("tau", {})


class PrecedenceTests(unittest.TestCase):
    """A supplied value wins, and the result says so."""

    def test_a_supplied_pi_is_the_one_used(self):
        result = review_step(_area_step(3.14))
        self.assertAlmostEqual(result["actual"], 3.14 * 4 / 4, places=9)
        self.assertTrue(result["correct"])

    def test_without_it_the_same_answer_is_marked_wrong(self):
        # The pair is the argument for explicit-wins.  This student did their
        # work with 3.14 as their course told them to; checked against the
        # built-in, their correct answer is reported as a discrepancy they
        # never made.
        result = review_step(_area_step(None))
        self.assertFalse(result["correct"])

    def test_a_supplied_pi_is_reported(self):
        shadow = review_step(_area_step(3.14))["shadowed_constants"][0]
        self.assertEqual(shadow["name"], "pi")
        self.assertEqual(shadow["supplied"], 3.14)
        self.assertEqual(shadow["builtin"], math.pi)
        self.assertAlmostEqual(shadow["relative_difference"], 5.0695e-4, places=7)

    def test_a_mistyped_pi_is_used_and_reported(self):
        # The case a silent preference would hide: 3 is not a course
        # convention, and the report is how a reader tells the two apart.
        result = review_step(_area_step(3))
        self.assertEqual(result["actual"], 3.0)
        self.assertFalse(result["correct"])
        self.assertAlmostEqual(result["shadowed_constants"][0]["relative_difference"], 0.045070, places=5)

    def test_an_exact_pi_reports_nothing(self):
        # No threshold, so no noise either: a step that supplies math.pi has
        # nothing to say about it.
        self.assertNotIn("shadowed_constants", review_step(_area_step(math.pi)))

    def test_verify_reports_a_shadow_in_both_modes(self):
        dimensional = check_calculation({
            "id": "c", "expression": "pi * r**2",
            "variables": {"r": {"value": 1, "unit": "m"}, "pi": {"value": 3.14, "unit": "dimensionless"}},
            "unit": "m^2", "expected": 3.14, "tolerance": 1e-9,
        })
        arithmetic = check_calculation({
            "id": "c", "expression": "pi * 4", "variables": {"pi": 3.14},
            "unit": "dimensionless", "expected": 12.56, "tolerance": 1e-9,
        })
        for result in (dimensional, arithmetic):
            with self.subTest(mode=result["mode"]):
                self.assertTrue(result["passed"], result)
                self.assertEqual(result["shadowed_constants"][0]["supplied"], 3.14)

    def test_the_report_reads_both_value_shapes(self):
        # {value, unit} where units are declared, a bare number where they
        # are not.  Missing one shape would silently stop reporting.
        self.assertTrue(shadowed_constants({"pi": 3.14}))
        self.assertTrue(shadowed_constants({"pi": {"value": 3.14, "unit": "dimensionless"}}))

    def test_nothing_is_reported_when_no_constant_is_supplied(self):
        self.assertEqual(shadowed_constants({"r": 2}), [])
        self.assertEqual(shadowed_constants({}), [])


class CorrectWithBuiltinTests(unittest.TestCase):
    """Say whether "correct" rests on the supplied constant.

    A host writes a step by reading the student's work, so it can transcribe
    the student's own wrong constant into it.  The check then adopts that
    error as a premise and confirms the answer: a circle area of 3.0 in^2 is
    marked correct because the step said pi is 3.  Recomputing with the
    built-in is how a reader can tell, and it needs no threshold.
    """

    def test_a_supplied_constant_can_confirm_a_wrong_answer(self):
        # The failure that motivates the field, asserted rather than argued.
        result = review_step(_area_step(3, claimed=3.0))
        self.assertTrue(result["correct"])
        self.assertFalse(result["correct_with_builtin"])

    def test_the_same_answer_is_wrong_without_the_supplied_constant(self):
        self.assertFalse(review_step(_area_step(None, claimed=3.0))["correct"])

    def test_a_course_convention_is_the_same_shape(self):
        # pi = 3.14 with an answer of 3.14 is also correct only because of the
        # supplied value.  The check cannot tell a course convention from a
        # typo, and this field does not pretend to: it reports the dependency
        # and leaves the judgement to a reader who knows the course.
        result = review_step(_area_step(3.14, claimed=3.14))
        self.assertTrue(result["correct"])
        self.assertFalse(result["correct_with_builtin"])

    def test_a_supplied_constant_can_also_cause_a_wrong_verdict(self):
        # The mirror case: the student used the exact value and the step
        # supplied 3.14, so the student is marked wrong for being right.
        result = review_step(_area_step(3.14, claimed=math.pi))
        self.assertFalse(result["correct"])
        self.assertTrue(result["correct_with_builtin"])

    def test_the_field_is_absent_when_no_constant_was_supplied(self):
        # It answers a question that was not asked otherwise, and an always
        # present field would read as a claim about every step.
        self.assertNotIn("correct_with_builtin", review_step(_area_step(None, claimed=3.1416)))

    def test_the_field_is_absent_when_the_supplied_value_is_exact(self):
        self.assertNotIn("correct_with_builtin", review_step(_area_step(math.pi, claimed=3.1416)))


class OneConstantTests(unittest.TestCase):
    """The list is one entry long, and that is the design, not an omission."""

    def test_pi_is_the_only_built_in(self):
        self.assertEqual(set(BUILTIN_CONSTANTS), {"pi"})

    def test_e_is_not_a_built_in(self):
        # "e" is ordinary notation for eccentricity, a void ratio or an error
        # term.  A host that meant its own variable and forgot to supply it
        # must get a refusal, not 2.718 used silently.  exp() already covers
        # the exponential.
        with self.assertRaises(ValueError):
            evaluate("e", {})

    def test_g_is_not_a_built_in_and_would_collide(self):
        # "g" is already the gram.  A constant of that name would make m * g
        # ambiguous between a mass times gravity and a value in grams, and a
        # dimensioned gravity varies with the unit system a course chose.
        from engineering_assistant.units import _REGISTRY

        self.assertIn("g", _REGISTRY)
        self.assertNotIn("g", BUILTIN_CONSTANTS)
        with self.assertRaises(ValueError):
            evaluate("g", {})

    def test_every_built_in_is_a_finite_plain_number(self):
        # A dimensioned or non-finite constant would corrupt the dimension
        # check that everything else here relies on.
        for name, value in BUILTIN_CONSTANTS.items():
            with self.subTest(constant=name):
                self.assertIsInstance(value, float)
                self.assertTrue(math.isfinite(value))
                self.assertEqual(expression_dimension(name, {}), DIMENSIONLESS)

    def test_no_built_in_collides_with_a_unit_or_a_function(self):
        from engineering_assistant.calculations import FUNCTIONS
        from engineering_assistant.units import _REGISTRY

        for name in BUILTIN_CONSTANTS:
            with self.subTest(constant=name):
                self.assertNotIn(name, _REGISTRY)
                self.assertNotIn(name, FUNCTIONS)


if __name__ == "__main__":
    unittest.main()
