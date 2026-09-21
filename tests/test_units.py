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


class CircuitUnitTests(unittest.TestCase):
    """The units ENGR 204's own prompts write, and the two that cannot be.

    The registry admits units that appear in course material, so each symbol
    below was counted in the eleven ENGR 204 homework prompts, the final-exam
    study guide, or the Test 1 paper before it was added.  A partial set is
    worse than none for a student checking work: the check fails part-way
    through a problem, on a unit rather than on the mistake it exists to find.
    """

    def test_prefixed_electrical_units_scale_to_their_base(self):
        cases = (
            ("mV", "V", 1e-3), ("kV", "V", 1e3),
            ("mA", "A", 1e-3), ("uA", "A", 1e-6),
            ("kohm", "ohm", 1e3), ("kohms", "ohm", 1e3),
            ("mW", "W", 1e-3), ("uW", "W", 1e-6),
            ("mF", "farad", 1e-3), ("uF", "farad", 1e-6),
            ("nF", "farad", 1e-9), ("pF", "farad", 1e-12),
            ("fF", "farad", 1e-15),
            ("mH", "H", 1e-3),
            ("uC", "coulomb", 1e-6),
            ("MHz", "Hz", 1e6),
            ("ms", "s", 1e-3),
        )
        for unit, base, factor in cases:
            with self.subTest(unit=unit):
                self.assertEqual(dimension_of(unit), dimension_of(base))
                self.assertAlmostEqual(convert(1, unit, base), factor, delta=abs(factor) * 1e-9)

    def test_electrical_dimensions_are_the_si_ones(self):
        # Built from the defining relations, so a mistyped exponent in the
        # registry shows up here rather than in a student's answer.
        self.assertEqual(dimension_of("farad"), dimension_of("A-s/V"))
        self.assertEqual(dimension_of("H"), dimension_of("V-s/A"))
        self.assertEqual(dimension_of("coulomb"), dimension_of("A-s"))
        self.assertEqual(dimension_of("V"), dimension_of("W/A"))
        self.assertEqual(dimension_of("ohm"), dimension_of("V/A"))

    def test_a_time_constant_reads_in_the_units_the_course_writes(self):
        # tau = R*C, written kohm and uF, is milliseconds.
        self.assertEqual(dimension_of("kohm-uF"), dimension_of("s"))
        self.assertAlmostEqual(convert(1, "kohm-uF", "ms"), 1.0)

    def test_a_resonant_frequency_reads_in_the_units_the_course_writes(self):
        # 1/sqrt(L*C) with mH and uF is rad/s; the course writes krad/s.
        self.assertEqual(dimension_of("1/mH^0.5-uF^0.5"), dimension_of("1/s"))
        self.assertAlmostEqual(convert(10000, "rad/s", "krad/s"), 10.0)
        self.assertAlmostEqual(convert(200, "rad/sec", "rad/s"), 200.0)

    def test_degrees_are_angles_and_never_temperatures(self):
        # A phasor angle round trip, and the separation that matters: "deg"
        # is an angle, "degC" and "degF" are temperatures, and no conversion
        # crosses between them.
        self.assertAlmostEqual(convert(90, "deg", "rad"), math.pi / 2)
        self.assertAlmostEqual(convert(math.pi, "rad", "deg"), 180.0)
        self.assertAlmostEqual(convert(-36.3, "deg", "rad"), math.radians(-36.3))
        for other in ("degC", "degF", "K", "deltaC"):
            with self.subTest(other=other):
                with self.assertRaises(UnitError):
                    convert(1, "deg", other)
                with self.assertRaises(UnitError):
                    convert(1, other, "deg")

    def test_apparent_and_reactive_power_carry_the_watts_dimension(self):
        # Recorded, not hidden: VA, var and W are the same dimension, so the
        # engine cannot tell an apparent power from a real one.  The course
        # distinction is a method pitfall, not a dimensional one.
        self.assertEqual(dimension_of("VA"), dimension_of("W"))
        self.assertEqual(dimension_of("var"), dimension_of("W"))

    def test_a_bare_f_or_c_is_still_the_temperature_it_has_always_been(self):
        # The thermodynamics courses decide these two symbols, and adding
        # electrical units must not move them.
        self.assertAlmostEqual(convert(32, "F", "degC"), 0.0)
        self.assertAlmostEqual(convert(25, "C", "K"), 298.15)

    def test_a_bare_f_or_c_meant_electrically_is_told_how_to_write_it(self):
        # "10 F" cannot refuse, because it parses as Fahrenheit.  The failure
        # surfaces at the conversion, and that message has to name the real
        # spelling or the student learns nothing from it.
        with self.assertRaises(UnitError) as caught:
            convert(10, "F", "uF")
        self.assertIn("Fahrenheit", str(caught.exception))
        self.assertIn("uF", str(caught.exception))
        with self.assertRaises(UnitError) as caught:
            convert(10, "uC", "C")
        self.assertIn("Celsius", str(caught.exception))
        self.assertIn("coulomb", str(caught.exception))

    def test_a_temperature_mismatch_that_means_nothing_electrical_says_nothing_extra(self):
        # The hint is consulted only when the other side is electrical, so an
        # ordinary thermodynamics mismatch keeps its plain message.
        with self.assertRaises(UnitError) as caught:
            convert(10, "F", "m")
        self.assertNotIn("Fahrenheit", str(caught.exception))

    def test_capitalised_spellings_stay_refused(self):
        # "KW" is already refused because it could be kelvin-watt; the same
        # caution applies to the new symbols.  Guessing case is how a wrong
        # conversion comes to look right.
        for unit in ("KHZ", "Mhz", "KOhm", "MA", "NF"):
            with self.subTest(unit=unit):
                with self.assertRaises(UnitError):
                    parse_unit(unit)

    def test_the_decibel_is_still_refused_after_the_electrical_additions(self):
        # dB is the one 204 unit deliberately left out: it is logarithmic and
        # this registry is linear.  Named here so a later pass adding
        # electrical units does not quietly sweep it in.
        with self.assertRaises(UnitError):
            parse_unit("dB")


if __name__ == "__main__":
    unittest.main()
