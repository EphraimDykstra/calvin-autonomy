"""A caret in an expression is refused, and the refusal says why.

The notation really is inconsistent, which is the whole reason this happens:
a unit string writes a power with a caret, "in^2", and an expression writes
one with two stars, "d**2".  A host that has just typed the first types the
second the same way, and got back "Unsupported expression for dimensional
checking", which says nothing about powers.  It is the first thing anyone
writing a geometry step hits.

The semantics are deliberately unchanged.  A caret is not quietly read as a
power: reinterpreting an operator is how a wrong answer gets certified.  It
is refused, as before, with a message that names the likely cause.

The other half of this was the more serious possibility, and it turned out
not to exist: `2^3` does not silently evaluate to 1.  BitXor is not in the
allowed operator table, so it is refused rather than computed.  Asserted here
so it stays that way.
"""

import unittest

from engineering_assistant.calculations import check_calculation, evaluate
from engineering_assistant.units import UnitError, expression_dimension, power_notation_hint

LENGTH = (0.0, 1.0, 0.0, 0.0, 0.0, 0.0)


class NoSilentBitwiseTests(unittest.TestCase):
    """The dangerous reading never happens."""

    def test_a_caret_on_two_integers_is_refused_not_computed(self):
        # If this ever returns 1, a host has been handed a wrong number with
        # no warning, which is worse than any error message.
        with self.assertRaises(ValueError):
            evaluate("2^3", {})

    def test_a_caret_check_does_not_pass_by_computing_xor(self):
        result = check_calculation({
            "id": "c", "expression": "2^3", "variables": {},
            "unit": "dimensionless", "expected": 1, "tolerance": 1e-9,
        })
        self.assertFalse(result["passed"])
        self.assertIn("error", result)

    def test_a_caret_is_never_treated_as_a_power(self):
        # The fix is to the message, not the semantics.  8 would mean the
        # caret had been reinterpreted.
        result = check_calculation({
            "id": "c", "expression": "2^3", "variables": {},
            "unit": "dimensionless", "expected": 8, "tolerance": 1e-9,
        })
        self.assertFalse(result["passed"])


class PowerHintTests(unittest.TestCase):
    def test_the_arithmetic_path_explains_the_caret(self):
        with self.assertRaises(ValueError) as caught:
            evaluate("d^2", {"d": 2.0})
        message = str(caught.exception)
        self.assertIn("**", message)
        self.assertIn("d**2", message)

    def test_the_dimensional_path_explains_the_caret(self):
        # The path a review takes, and the one the report came from.
        with self.assertRaises(UnitError) as caught:
            expression_dimension("pi * d^2 / 4", {"d": LENGTH})
        message = str(caught.exception)
        self.assertIn("**", message)
        self.assertIn("pi * d**2 / 4", message)

    def test_the_hint_shows_the_corrected_form_of_what_was_typed(self):
        # Reading a corrected version of your own expression is faster than
        # reading a rule about expressions in general.
        self.assertIn("a**2 + b**2", power_notation_hint("a^2 + b^2"))

    def test_the_hint_names_both_conventions(self):
        # Saying only "use **" invites the opposite mistake in a unit string,
        # where the caret is correct.
        hint = power_notation_hint("d^2")
        self.assertIn("in^2", hint)

    def test_an_expression_without_a_caret_gets_no_hint(self):
        self.assertEqual(power_notation_hint("a * b"), "")

    def test_an_unrelated_refusal_is_not_decorated(self):
        # A message that explained powers on every failure would be noise,
        # and would misdirect on a genuinely different mistake.
        with self.assertRaises(ValueError) as caught:
            evaluate("a % b", {"a": 1.0, "b": 2.0})
        self.assertNotIn("**", str(caught.exception))

    def test_the_hint_survives_a_non_string(self):
        self.assertEqual(power_notation_hint(None), "")

    def test_the_corrected_form_actually_evaluates(self):
        # The suggestion has to be right, not just plausible: a hint that
        # produced another error would send a host in a circle.
        self.assertEqual(evaluate("d**2", {"d": 3.0}), 9.0)
        self.assertEqual(expression_dimension("d**2", {"d": LENGTH}), (0.0, 2.0, 0.0, 0.0, 0.0, 0.0))


if __name__ == "__main__":
    unittest.main()
