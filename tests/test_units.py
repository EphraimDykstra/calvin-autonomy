"""Dimensional checking: catch the unit mistakes arithmetic alone cannot.

The regression that motivates the module is real.  A student recorded an
ambient temperature of 72 degF and carried 306.48 K into the analysis.  That is
92 degF.  The arithmetic downstream was internally consistent, so a check that
only recomputed the expression passed it.  A check that knows what degF is
does not.
"""

import math
import unittest

from engineering_assistant.calculations import check_calculation
from engineering_assistant.units import (
    UnitError,
    convert,
    dimension_of,
    parse_unit,
)


class FahrenheitRegressionTests(unittest.TestCase):
    """The hold-out finding, reproduced as a failing check."""

    def test_a_fahrenheit_reading_carried_in_as_the_wrong_kelvin_value_fails(self):
        result = check_calculation(
            {
                "id": "ambient",
                "expression": "T_amb",
                "variables": {"T_amb": {"value": 72, "unit": "degF"}},
                "expected": 306.48,
                "unit": "K",
                "tolerance": 0.01,
            }
        )
        self.assertFalse(result["passed"])
        self.assertEqual(result["mode"], "dimensional")
        self.assertAlmostEqual(result["actual"], 295.372, places=2)

    def test_the_correct_conversion_passes(self):
        # The benign answer must be reachable, or the check measures nothing.
        result = check_calculation(
            {
                "id": "ambient",
                "expression": "T_amb",
                "variables": {"T_amb": {"value": 72, "unit": "degF"}},
                "expected": 295.372,
                "unit": "K",
                "tolerance": 0.01,
            }
        )
        self.assertTrue(result["passed"], result)


class ParseUnitTests(unittest.TestCase):
    def test_ees_compound_notation(self):
        # EES writes a product in the denominator with a hyphen: kJ/kg-K is
        # kJ/(kg*K), not (kJ/kg)*K.
        self.assertEqual(dimension_of("kJ/kg-K"), dimension_of("m^2/s^2-K"))

    def test_product_with_hyphen(self):
        self.assertEqual(dimension_of("N-m"), dimension_of("J"))

    def test_negative_and_fractional_exponents(self):
        self.assertEqual(dimension_of("m^-2"), dimension_of("1/m^2"))
        self.assertEqual(dimension_of("kg^0.5-m^0.5"), dimension_of("kg^0.5-m^0.5"))

    def test_pressure_units_agree(self):
        for unit in ("kPa", "bar", "mbar", "psi", "psia", "mmHg", "mmH2O", "kN/m^2"):
            with self.subTest(unit=unit):
                self.assertEqual(dimension_of(unit), dimension_of("Pa"))

    def test_kilohertz_and_microseconds_read(self):
        # Both were found missing while adding the magnitudes loader check:
        # ordinary prefixed units that a signals or timing bound would use,
        # refused only because nothing had needed them yet.
        self.assertEqual(dimension_of("kHz"), dimension_of("Hz"))
        self.assertEqual(dimension_of("us"), dimension_of("s"))
        self.assertAlmostEqual(convert(2, "kHz", "Hz"), 2000.0)
        self.assertAlmostEqual(convert(1500, "us", "s"), 0.0015)

    def test_the_decibel_stays_refused(self):
        # Logarithmic, and every unit here is read linearly as
        # value*factor + offset.  Registering it would make 20 dB convert to
        # 20 V/V rather than 10, and would let a review check "3 dB + 3 dB =
        # 6 dB" as correct arithmetic.  Refusing is the honest answer until
        # dB can be given a dimension nothing else matches.
        with self.assertRaises(UnitError):
            parse_unit("dB")

    def test_unknown_unit_is_refused_rather_than_guessed(self):
        # "KW" could be kilowatt or kelvin-watt.  Guessing is how a wrong
        # conversion looks correct, so an unrecognised unit refuses.
        for unit in ("KW", "MM", "furlong", ""):
            with self.subTest(unit=unit):
                with self.assertRaises(UnitError):
                    parse_unit(unit)


class AffineTemperatureTests(unittest.TestCase):
    """Celsius and Fahrenheit carry an offset, so they cannot be multiplied."""

    def test_standalone_affine_units_convert_with_their_offset(self):
        self.assertAlmostEqual(convert(0, "degC", "K"), 273.15)
        self.assertAlmostEqual(convert(32, "degF", "K"), 273.15)
        self.assertAlmostEqual(convert(212, "degF", "degC"), 100.0)

    def test_ees_bare_c_means_celsius(self):
        # In EES "C" is Celsius: it appears 159 times across the course files
        # and never as the coulomb.  The data decides the meaning here.
        self.assertAlmostEqual(convert(25, "C", "K"), 298.15)

    def test_affine_unit_inside_a_compound_is_refused(self):
        # This construct appears in real course EES: [m^3-C/s].  Multiplying by
        # an offset scale silently produces a wrong number, so it must refuse
        # and point at the delta unit that means what the author intended.
        for unit in ("m^3-C/s", "kJ/kg-degC", "W/m-degF", "degC^2"):
            with self.subTest(unit=unit):
                with self.assertRaises(UnitError) as caught:
                    parse_unit(unit)
                self.assertIn("delta", str(caught.exception))

    def test_delta_units_are_differences_without_an_offset(self):
        self.assertAlmostEqual(convert(10, "deltaC", "K"), 10.0)
        self.assertAlmostEqual(convert(18, "deltaF", "deltaC"), 10.0)
        self.assertEqual(dimension_of("kJ/kg-deltaC"), dimension_of("kJ/kg-K"))

    def test_absolute_kelvin_and_rankine_may_appear_in_compounds(self):
        self.assertEqual(dimension_of("W/m^2-K"), dimension_of("W/m^2-deltaC"))
        self.assertAlmostEqual(convert(1.8, "R", "K"), 1.0)


class DimensionalCheckTests(unittest.TestCase):
    def _check(self, expression, variables, unit, expected, tolerance=1e-6):
        return check_calculation(
            {
                "id": "c",
                "expression": expression,
                "variables": variables,
                "unit": unit,
                "expected": expected,
                "tolerance": tolerance,
            }
        )

    def test_power_from_mass_flow_and_enthalpy_change(self):
        # 2 kg/s through a 50 kJ/kg rise is 100 kW.
        result = self._check(
            "m_dot * dh",
            {"m_dot": {"value": 2, "unit": "kg/s"}, "dh": {"value": 50, "unit": "kJ/kg"}},
            "kW",
            100,
        )
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["mode"], "dimensional")

    def test_grams_per_second_are_converted_before_use(self):
        # The factor-of-1000 slip the EES pack warns about: 17 g/s is not
        # 17 kg/s, and a check that ignores the prefix passes the wrong answer.
        result = self._check(
            "m_dot * dh",
            {"m_dot": {"value": 17, "unit": "g/s"}, "dh": {"value": 100, "unit": "kJ/kg"}},
            "kW",
            1700,
            tolerance=0.01,
        )
        self.assertFalse(result["passed"])
        self.assertAlmostEqual(result["actual"], 1.7, places=6)

    def test_declared_result_of_the_wrong_dimension_fails(self):
        result = self._check(
            "m_dot * dh",
            {"m_dot": {"value": 2, "unit": "kg/s"}, "dh": {"value": 50, "unit": "kJ/kg"}},
            "kJ",
            100,
        )
        self.assertFalse(result["passed"])
        self.assertIn("dimension", result["error"])

    def test_adding_incompatible_quantities_fails(self):
        result = self._check(
            "T + P",
            {"T": {"value": 300, "unit": "K"}, "P": {"value": 101, "unit": "kPa"}},
            "K",
            401,
        )
        self.assertFalse(result["passed"])
        self.assertIn("dimension", result["error"])

    def test_temperature_difference_in_celsius_is_correct(self):
        # Both readings convert to kelvin, so the offsets cancel.
        result = self._check(
            "T2 - T1",
            {"T1": {"value": 20, "unit": "degC"}, "T2": {"value": 30, "unit": "degC"}},
            "deltaC",
            10,
        )
        self.assertTrue(result["passed"], result)

    def test_exp_and_log_require_a_dimensionless_argument(self):
        result = self._check(
            "exp(T)",
            {"T": {"value": 300, "unit": "K"}},
            "dimensionless",
            1,
        )
        self.assertFalse(result["passed"])
        self.assertIn("dimensionless", result["error"])

    def test_sqrt_halves_the_dimension(self):
        result = self._check(
            "sqrt(A)",
            {"A": {"value": 4, "unit": "m^2"}},
            "m",
            2,
        )
        self.assertTrue(result["passed"], result)


class ModeTests(unittest.TestCase):
    """A check that silently did not check is the false-ready failure."""

    def test_plain_numbers_run_in_arithmetic_mode_and_say_so(self):
        result = check_calculation(
            {"id": "c", "expression": "a * b", "variables": {"a": 2, "b": 3},
             "unit": "kW", "expected": 6}
        )
        self.assertTrue(result["passed"])
        self.assertEqual(result["mode"], "arithmetic")

    def test_mixing_united_and_bare_variables_is_refused(self):
        # Checking dimensions with half the variables undeclared would either
        # invent a dimension or skip the check, and either one reports a pass
        # that means less than it says.
        result = check_calculation(
            {"id": "c", "expression": "a * b",
             "variables": {"a": {"value": 2, "unit": "kg/s"}, "b": 3},
             "unit": "kW", "expected": 6}
        )
        self.assertFalse(result["passed"])
        self.assertIn("every variable", result["error"])

    def test_an_unknown_unit_errors_rather_than_passing(self):
        result = check_calculation(
            {"id": "c", "expression": "a",
             "variables": {"a": {"value": 2, "unit": "KW"}},
             "unit": "kW", "expected": 2}
        )
        self.assertFalse(result["passed"])
        self.assertIn("error", result)


if __name__ == "__main__":
    unittest.main()
