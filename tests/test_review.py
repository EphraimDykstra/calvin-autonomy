"""Check-my-work: recompute a student's answer and name the likely slip.

Each step takes the problem's GIVENS as inputs, the course's correct method,
and the answer the student wrote.  Recomputing from the student's own
intermediate values would reproduce their mistake and pass it, so the givens
are what make a slip visible.
"""

import unittest

from engineering_assistant.review import classify_discrepancy, review_step, review_work


def step(method, inputs, value, unit, **extra):
    return {"id": "s", "method": method, "inputs": inputs, "student_answer": {"value": value, "unit": unit}, **extra}


def causes(result):
    return [c["cause"] for c in result.get("likely_causes", [])]


class CorrectWorkTests(unittest.TestCase):
    def test_a_right_answer_is_correct(self):
        # The benign case must be reachable, or the review measures nothing.
        r = review_step(step("F / A", {"F": {"value": 500, "unit": "N"}, "A": {"value": 0.0001, "unit": "m^2"}}, 5, "MPa"))
        self.assertTrue(r["correct"], r)

    def test_a_rounded_answer_within_tolerance_is_correct(self):
        # Students round intermediate values; 2% is the default allowance.
        r = review_step(step("F / A", {"F": {"value": 500, "unit": "N"}, "A": {"value": 0.0001, "unit": "m^2"}}, 5.05, "MPa"))
        self.assertTrue(r["correct"])

    def test_an_answer_in_different_units_is_converted_not_marked_wrong(self):
        r = review_step(step("F / A", {"F": {"value": 500, "unit": "N"}, "A": {"value": 0.0001, "unit": "m^2"}}, 5000, "kPa"))
        self.assertTrue(r["correct"])


class NamedSlipTests(unittest.TestCase):
    """The mistakes a student actually makes, each named rather than just marked."""

    def test_a_dropped_minus_sign(self):
        r = review_step(step("W - Q", {"W": {"value": 10, "unit": "kJ"}, "Q": {"value": 25, "unit": "kJ"}}, 15, "kJ"))
        self.assertFalse(r["correct"])
        self.assertIn("sign", causes(r))

    def test_an_upside_down_transfer_function(self):
        # Gain is output over input.  Writing input over output gives the
        # reciprocal, which is the slip this check exists to name.
        r = review_step(step("V_out / V_in", {"V_out": {"value": 10, "unit": "V"}, "V_in": {"value": 2, "unit": "V"}}, 0.2, "dimensionless"))
        self.assertFalse(r["correct"])
        self.assertIn("inverted", causes(r))

    def test_an_inverted_ratio_shows_in_the_units(self):
        # A dimensioned ratio written upside down has the inverse units, so it
        # is caught before any arithmetic.
        r = review_step(step("d / t", {"d": {"value": 100, "unit": "m"}, "t": {"value": 20, "unit": "s"}}, 0.2, "s/m"))
        self.assertIn("inverted", causes(r))

    def test_grams_used_as_kilograms(self):
        r = review_step(step("m_dot * dh", {"m_dot": {"value": 17, "unit": "g/s"}, "dh": {"value": 100, "unit": "kJ/kg"}}, 1700, "kW"))
        self.assertIn("unit prefix", causes(r))

    def test_a_percentage_used_as_a_fraction(self):
        # The dry-run slip: strain 5 entered where 0.05 belonged.  Recomputed
        # from the problem's givens, the student's modulus is 100 times low.
        r = review_step(step("sigma / strain", {"sigma": {"value": 5.12, "unit": "MPa"}, "strain": {"value": 0.05, "unit": "dimensionless"}}, 1.024, "MPa"))
        self.assertIn("percent", causes(r))

    def test_a_misplaced_decimal(self):
        r = review_step(step("F / A", {"F": {"value": 500, "unit": "N"}, "A": {"value": 0.0001, "unit": "m^2"}}, 0.5, "MPa"))
        self.assertIn("decimal", causes(r))

    def test_celsius_used_as_kelvin(self):
        r = review_step(step("T", {"T": {"value": 25, "unit": "degC"}}, 25, "K"))
        self.assertIn("temperature scale", causes(r))

    def test_a_wrong_answer_with_no_familiar_shape_is_still_wrong(self):
        # The 72 degF reading carried in as 306.48 K.  Nothing about it
        # matches a known slip, so no cause is claimed, but it is still wrong.
        r = review_step(step("T", {"T": {"value": 72, "unit": "degF"}}, 306.48, "K"))
        self.assertFalse(r["correct"])
        self.assertAlmostEqual(r["actual"], 295.372, places=2)
        self.assertEqual(causes(r), [])


class MagnitudeTests(unittest.TestCase):
    RANGE = [{"quantity": "relaxation modulus", "unit": "MPa", "typical_range": [20, 5000], "note": "100x low usually means strain as a percent."}]

    def test_an_implausible_answer_is_flagged_with_the_pack_note(self):
        r = review_step(step("sigma / strain", {"sigma": {"value": 5.12, "unit": "MPa"}, "strain": {"value": 0.05, "unit": "dimensionless"}},
                             1.024, "MPa", magnitude="relaxation modulus"), self.RANGE)
        self.assertFalse(r["magnitude"]["plausible"])
        self.assertIn("percent", r["magnitude"]["note"])

    def test_a_plausible_answer_passes_the_range(self):
        r = review_step(step("sigma / strain", {"sigma": {"value": 5.12, "unit": "MPa"}, "strain": {"value": 0.05, "unit": "dimensionless"}},
                             102.4, "MPa", magnitude="relaxation modulus"), self.RANGE)
        self.assertTrue(r["magnitude"]["plausible"])

    def test_a_range_is_compared_in_its_own_unit(self):
        r = review_step(step("sigma / strain", {"sigma": {"value": 5.12, "unit": "MPa"}, "strain": {"value": 0.05, "unit": "dimensionless"}},
                             0.1024, "GPa", magnitude="relaxation modulus"), self.RANGE)
        self.assertTrue(r["correct"])
        self.assertAlmostEqual(r["magnitude"]["value_in_range_unit"], 102.4)

    def test_an_unknown_magnitude_name_is_an_error(self):
        r = review_step(step("F", {"F": {"value": 1, "unit": "N"}}, 1, "N", magnitude="nope"), self.RANGE)
        self.assertIn("error", r)


class StructureTests(unittest.TestCase):
    """A review that could be built backwards would pass every mistake."""

    def test_an_expected_value_is_refused(self):
        s = step("F / A", {"F": {"value": 500, "unit": "N"}, "A": {"value": 0.0001, "unit": "m^2"}}, 5, "MPa")
        s["expected"] = 5
        r = review_step(s)
        self.assertIn("tautology", r["error"])

    def test_inputs_without_units_are_refused(self):
        r = review_step({"id": "s", "method": "a * b", "inputs": {"a": 2, "b": 3}, "student_answer": {"value": 6, "unit": "N"}})
        self.assertIn("error", r)

    def test_an_unknown_unit_is_an_error_not_a_hint(self):
        # A step written wrongly must say so, never produce a confident cause.
        r = review_step(step("F", {"F": {"value": 1, "unit": "KW"}}, 1, "kW"))
        self.assertIn("error", r)
        self.assertNotIn("likely_causes", r)

    def test_the_summary_lists_what_needs_attention(self):
        right = step("F / A", {"F": {"value": 500, "unit": "N"}, "A": {"value": 0.0001, "unit": "m^2"}}, 5, "MPa", id="a")
        wrong = step("F / A", {"F": {"value": 500, "unit": "N"}, "A": {"value": 0.0001, "unit": "m^2"}}, -5, "MPa", id="b")
        report = review_work([right, wrong])
        self.assertEqual(report["correct"], 1)
        self.assertEqual(report["needs_attention"], ["b"])

    def test_the_classifier_claims_nothing_for_an_arbitrary_error(self):
        self.assertEqual(classify_discrepancy(10.0, 13.7, False, False), [])


class ReviewCommandTests(unittest.TestCase):
    """The check has to be reachable from the CLI a host actually drives."""

    def _run(self, payload, *extra):
        import contextlib, io, json, tempfile
        from pathlib import Path
        from engineering_assistant.cli import main
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "steps.json"
            path.write_text(json.dumps(payload))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = main(["--workspace", str(Path(d) / "ws"), "review", str(path), *extra])
            return code, json.loads(out.getvalue())

    def test_the_command_names_the_slip(self):
        code, report = self._run({"steps": [step("V_out / V_in", {"V_out": {"value": 10, "unit": "V"}, "V_in": {"value": 2, "unit": "V"}}, 0.2, "dimensionless")]})
        self.assertEqual(code, 0)
        self.assertIn("inverted", causes(report["steps"][0]))

    def test_the_course_pack_supplies_the_ranges(self):
        # Named by the pack's own quantity string, so the range and its note
        # come from the shipped pack rather than from the host.
        import json
        from pathlib import Path
        pack = json.loads((Path(__file__).resolve().parents[1] / "curriculum" / "engr205" / "pack.json").read_text())
        quantity = pack["magnitudes"][1]["quantity"]
        code, report = self._run({"steps": [step("sigma / strain", {"sigma": {"value": 5.12, "unit": "MPa"}, "strain": {"value": 0.05, "unit": "dimensionless"}},
                                                  1.024, "MPa", magnitude=quantity)]}, "--course", "engr205")
        self.assertEqual(code, 0)
        self.assertFalse(report["steps"][0]["magnitude"]["plausible"])


if __name__ == "__main__":
    unittest.main()
