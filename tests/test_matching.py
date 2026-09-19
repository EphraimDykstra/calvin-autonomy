import copy
import json
import tempfile
import unittest
from pathlib import Path

from engineering_assistant.matching import (
    compare_assignments,
    match_examples,
    register_example,
)


def assignment(**overrides):
    value = {
        "id": "beam-01",
        "title": "Cantilever beam sizing",
        "family": "beam-sizing",
        "method": "Euler Bernoulli",
        "assumptions": {"boundary": "fixed-free", "linear": True},
        "inputs": {"length": {"value": 2.0, "unit": "m"}, "load": {"value": 100, "unit": "N"}},
        "requirements": [
            {"id": "r1", "text": "Calculate maximum bending stress"},
            {"id": "r2", "text": "Include a stress versus length plot"},
        ],
        "deliverables": ["calculation", "stress plot"],
        "text": "Size the cantilever beam under the stated load.",
    }
    value.update(overrides)
    return value


class MatchingTests(unittest.TestCase):
    def test_compare_classifies_exact_input_method_and_presentation_changes(self):
        old = assignment()
        self.assertEqual(compare_assignments(old, assignment())["classification"], "exact_repeat")
        changed_input = assignment(inputs={**old["inputs"], "length": {"value": 6.56, "unit": "ft"}})
        compared = compare_assignments(old, changed_input)
        self.assertEqual(compared["classification"], "input_variant")
        self.assertTrue(any(d["field"] == "inputs.length" and d["reason"] == "input unit changed" for d in compared["differences"]))
        compared = compare_assignments(old, assignment(method="finite element"))
        self.assertEqual(compared["classification"], "method_changing_variant")
        self.assertTrue(any(d["field"] == "method" for d in compared["differences"]))
        compared = compare_assignments(old, assignment(deliverables=["calculation", "stress plot", "summary figure"]))
        self.assertEqual(compared["classification"], "presentation_only")

    def test_assumptions_and_requirements_are_explicit_and_conservative(self):
        old = assignment()
        current = assignment(
            assumptions={"boundary": "pinned-pinned", "linear": True},
            requirements=[
                {"id": "new-r1", "text": "Calculate maximum bending stress"},
                {"id": "r2", "text": "Include a stress versus length plot"},
                {"id": "r3", "text": "Report the safety factor"},
            ],
        )
        compared = compare_assignments(old, current)
        self.assertEqual(compared["classification"], "method_changing_variant")
        self.assertTrue(any(d["field"] == "assumptions" for d in compared["differences"]))
        self.assertTrue(any(d["kind"] == "changed" and d["field"] == "requirements" for d in compared["differences"]))
        self.assertTrue(any(d["kind"] == "added" for d in compared["differences"]))

    def test_missing_structure_does_not_establish_match(self):
        compared = compare_assignments({"title": "same"}, {"title": "same"})
        self.assertEqual(compared["classification"], "no_useful_match")
        self.assertFalse(compared["match"])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            register_example(root, "course-a", {"id": "old", "assignment": assignment(), "artifacts": []})
            self.assertEqual(match_examples(root, "course-a", {"title": "same"}), [])

    def test_registration_is_idempotent_and_course_scoped(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            example = {"id": "beam-example", "assignment": assignment(), "artifacts": ["artifacts/beam.pdf"], "review_status": "reviewed"}
            self.assertEqual(register_example(root, "course-a", example), example)
            self.assertEqual(register_example(root, "course-a", example), example)
            with self.assertRaises(ValueError):
                register_example(root, "course-a", {**example, "assignment": assignment(method="finite element")})
            self.assertEqual(match_examples(root, "course-b", assignment()), [])
            stored = json.loads((root / "courses" / "course-a" / "examples.json").read_text())
            self.assertEqual(stored["schema_version"], 1)
            self.assertEqual(len(stored["examples"]), 1)

    def test_unsafe_artifacts_and_invalid_numbers_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for path in ("../outside.pdf", "auth.json", ".env", "keys/id_rsa"):
                with self.subTest(path=path):
                    with self.assertRaises(ValueError):
                        register_example(root, "course-a", {"id": "bad", "assignment": assignment(), "artifacts": [path]})
            with self.assertRaises(ValueError):
                register_example(root, "course-a", {"id": "nan", "assignment": assignment(inputs={"x": {"value": float("nan"), "unit": "m"}}), "artifacts": []})

    def test_stale_incorrect_examples_and_weak_family_matches_are_skipped(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stale = {"id": "stale", "assignment": assignment(), "artifacts": [], "review_status": "reviewed", "status": "incorrect"}
            register_example(root, "course-a", stale)
            weak = assignment(title="Unrelated", text="A wholly different experiment", requirements=[{"id": "x", "text": "Measure temperature"}], inputs={"temperature": {"value": 5, "unit": "C"}})
            register_example(root, "course-a", {"id": "weak", "assignment": weak, "artifacts": [], "review_status": "reviewed"})
            self.assertEqual(match_examples(root, "course-a", assignment()), [])

    def test_provisional_examples_are_retained_but_not_matched(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registered = register_example(root, "course-a", {"id": "pending", "assignment": assignment(), "artifacts": [], "review_status": "provisional"})
            self.assertEqual(registered["review_status"], "provisional")
            self.assertEqual(match_examples(root, "course-a", assignment()), [])


def exchanger(**overrides):
    """A synthetic, invented two-stream exchanger assignment.

    Every lookalike case below keeps ``family`` and ``method`` byte-identical to
    this baseline.  The physics that decides the method lives in the problem
    statement, which is exactly how a real handout states it and exactly the
    shape that used to slip through as ``presentation_only``.
    """
    value = {
        "id": "hx-01",
        "title": "Two-stream exchanger sizing",
        "family": "heat-exchanger",
        "method": "log mean temperature difference",
        "assumptions": {"fouling": "neglected"},
        "inputs": {
            "m_hot": {"value": 1.5, "unit": "kg/s"},
            "T_hot_in": {"value": 90.0, "unit": "C"},
            "T_cold_in": {"value": 20.0, "unit": "C"},
        },
        "requirements": [
            {"id": "q1", "text": "Determine the required heat transfer area"},
            {"id": "q2", "text": "Report the outlet temperature of each stream"},
        ],
        "deliverables": ["calculation"],
        "text": "The exchanger operates at steady state in a parallel-flow arrangement.",
    }
    value.update(overrides)
    return value


class LookalikeMethodChangeTests(unittest.TestCase):
    """Near-identical assignments that require a different physical method.

    These are the highest-severity cases: treating one of these as reusable
    produces a confident wrong answer instead of a blocker.
    """

    def assert_method_changing(self, previous, current, *, because=""):
        compared = compare_assignments(previous, current)
        self.assertEqual(
            compared["classification"],
            "method_changing_variant",
            msg=f"lookalike must not read as reusable ({because}): {compared['reasons']}",
        )
        self.assertTrue(compared["match"])
        return compared

    def test_flow_arrangement_swap_is_method_changing(self):
        compared = self.assert_method_changing(
            exchanger(),
            exchanger(text="The exchanger operates at steady state in a counterflow arrangement."),
            because="parallel-flow vs counterflow",
        )
        self.assertTrue(
            any("flow arrangement" in reason for reason in compared["reasons"]),
            msg=f"reason should name the conflicting regime, got {compared['reasons']}",
        )

    def test_crossflow_is_distinct_from_both_parallel_and_counterflow(self):
        for prior_text in (
            "The exchanger operates in a parallel-flow arrangement.",
            "The exchanger operates in a counterflow arrangement.",
        ):
            with self.subTest(prior=prior_text):
                self.assert_method_changing(
                    exchanger(text=prior_text),
                    exchanger(text="The exchanger operates in a crossflow arrangement."),
                    because="crossflow differs from every other arrangement",
                )

    def test_steady_state_versus_transient_is_method_changing(self):
        compared = self.assert_method_changing(
            exchanger(text="The exchanger operates at steady state in a counterflow arrangement."),
            exchanger(text="The exchanger is started from cold and the transient response is of interest."),
            because="steady-state vs transient",
        )
        self.assertTrue(any("time dependence" in reason for reason in compared["reasons"]))

    def test_steady_state_versus_transient_stated_only_in_assumptions(self):
        self.assert_method_changing(
            exchanger(assumptions={"fouling": "neglected", "regime": "steady state"}),
            exchanger(assumptions={"fouling": "neglected", "regime": "transient"}),
            because="regime moved into assumptions",
        )

    def test_added_constraint_in_problem_statement_is_method_changing(self):
        self.assert_method_changing(
            exchanger(text="Size the exchanger. Neglect the pressure drop through the tube bundle."),
            exchanger(text="Size the exchanger. Account for the pressure drop through the tube bundle."),
            because="a neglected term became a modeled term",
        )

    def test_removed_constraint_in_problem_statement_is_method_changing(self):
        self.assert_method_changing(
            exchanger(text="Size the exchanger. The shell side is perfectly insulated."),
            exchanger(text="Size the exchanger. The shell side loses heat to the surroundings."),
            because="a boundary condition was removed",
        )

    def test_added_boundary_condition_in_assumptions_is_method_changing(self):
        self.assert_method_changing(
            exchanger(),
            exchanger(assumptions={"fouling": "neglected", "shell_side": "insulated"}),
            because="a boundary condition was added",
        )

    def test_same_numbers_different_requested_quantity_is_method_changing(self):
        """Inputs byte-identical; only the quantity being solved for changes."""
        prior = exchanger()
        # Stated as a requirement, reusing the requirement ID.  The inputs are
        # carried over from the prior assignment object itself, so the "same
        # numbers" premise is enforced rather than assumed.
        current = exchanger(
            inputs=copy.deepcopy(prior["inputs"]),
            requirements=[
                {"id": "q1", "text": "Determine the overall heat transfer coefficient"},
                {"id": "q2", "text": "Report the outlet temperature of each stream"},
            ],
        )
        self.assert_method_changing(prior, current, because="requested quantity changed")

        # Stated only in the problem statement, requirements untouched.
        self.assert_method_changing(
            exchanger(text="Using the data above, determine the required surface area."),
            exchanger(text="Using the data above, determine the exit temperature of the cold stream."),
            because="requested quantity changed in the problem statement only",
        )

    def test_basis_change_is_method_changing(self):
        for name, before, after, because in (
            ("per-mass to per-mole", {"value": 2100.0, "unit": "kJ/kg"}, {"value": 2100.0, "unit": "kJ/kmol"}, "energy basis"),
            ("mass flow to molar flow", {"value": 1.5, "unit": "kg/s"}, {"value": 1.5, "unit": "kmol/s"}, "flow basis"),
            ("gauge to absolute", {"value": 250.0, "unit": "kPa", "basis": "gauge"}, {"value": 250.0, "unit": "kPa", "basis": "absolute"}, "pressure basis"),
            ("dry to wet", {"value": 0.4, "unit": "-", "basis": "dry basis"}, {"value": 0.4, "unit": "-", "basis": "wet basis"}, "composition basis"),
        ):
            with self.subTest(case=name):
                self.assert_method_changing(
                    exchanger(inputs={**exchanger()["inputs"], "h_fg": before}),
                    exchanger(inputs={**exchanger()["inputs"], "h_fg": after}),
                    because=because,
                )

    def test_removed_input_is_method_changing_but_added_input_is_an_input_variant(self):
        base = exchanger()
        without = {k: v for k, v in base["inputs"].items() if k != "T_cold_in"}
        # A datum the prior method consumed is gone: that method cannot be run.
        self.assert_method_changing(
            base, exchanger(inputs=without), because="an input the prior method needed was removed"
        )
        # An extra datum is ambiguous, so it stays an input variant rather than
        # inflating the method-changing class.
        compared = compare_assignments(base, exchanger(inputs={**base["inputs"], "U": {"value": 850.0, "unit": "W/m2K"}}))
        self.assertEqual(compared["classification"], "input_variant")

    def test_lookalike_reaches_the_caller_through_match_examples(self):
        """End-to-end: the ranked result a host actually reads must say method-changing."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            register_example(root, "course-a", {
                "id": "hx-parallel",
                "assignment": exchanger(),
                "artifacts": [],
                "review_status": "reviewed",
            })
            current = exchanger(text="The exchanger operates at steady state in a counterflow arrangement.")
            matches = match_examples(root, "course-a", current)
            self.assertEqual(len(matches), 1, msg="the lookalike should still be retrievable as evidence")
            self.assertEqual(matches[0]["classification"], "method_changing_variant")
            self.assertTrue(any("flow arrangement" in reason for reason in matches[0]["reasons"]))


class MatchingStaysUsefulTests(unittest.TestCase):
    """The other direction: a matcher that calls everything changed is useless."""

    def test_identical_assignment_is_still_an_exact_repeat(self):
        self.assertEqual(compare_assignments(exchanger(), exchanger())["classification"], "exact_repeat")

    def test_deliverables_only_change_is_still_presentation_only(self):
        compared = compare_assignments(exchanger(), exchanger(deliverables=["calculation", "summary figure"]))
        self.assertEqual(compared["classification"], "presentation_only")

    def test_title_only_change_is_still_presentation_only(self):
        compared = compare_assignments(exchanger(), exchanger(title="Exchanger surface area sizing"))
        self.assertEqual(compared["classification"], "presentation_only")

    def test_equivalent_compound_units_are_not_a_basis_change(self):
        """kg/kmol and g/mol are the same quantity at different scales.

        Comparing basis markers as one unordered set saw mass+mole on one side
        and mole on the other and called it a basis change, forcing a
        method-changing classification onto a pure rescale.  The markers must be
        compared position by position: both are a mass per mole.
        """
        base = exchanger()
        for name, before, after in (
            ("molar mass kg/kmol -> g/mol", "kg/kmol", "g/mol"),
            ("specific energy kJ/kg -> J/g", "kJ/kg", "J/g"),
        ):
            with self.subTest(case=name):
                compared = compare_assignments(
                    exchanger(inputs={**base["inputs"], "M": {"value": 18.0, "unit": before}}),
                    exchanger(inputs={**base["inputs"], "M": {"value": 18.0, "unit": after}}),
                )
                self.assertEqual(
                    compared["classification"], "input_variant",
                    msg=f"equivalent compound units must not read as a basis change: {compared['reasons']}",
                )

    def test_pure_unit_rescale_stays_an_input_variant(self):
        """m -> ft is the same physical length under the same method."""
        base = exchanger()
        compared = compare_assignments(
            exchanger(inputs={**base["inputs"], "length": {"value": 2.0, "unit": "m"}}),
            exchanger(inputs={**base["inputs"], "length": {"value": 6.56, "unit": "ft"}}),
        )
        self.assertEqual(compared["classification"], "input_variant")

    def test_numbers_only_change_stays_an_input_variant(self):
        base = exchanger()
        compared = compare_assignments(
            base, exchanger(inputs={**base["inputs"], "T_hot_in": {"value": 95.0, "unit": "C"}})
        )
        self.assertEqual(compared["classification"], "input_variant")

    def test_regime_term_present_on_both_sides_does_not_flip_anything(self):
        """A shared regime word is agreement, not conflict."""
        compared = compare_assignments(
            exchanger(text="The exchanger operates at steady state in a counterflow arrangement."),
            exchanger(text="The exchanger operates at steady state in a counterflow arrangement."),
        )
        self.assertEqual(compared["classification"], "exact_repeat")

    def test_reworded_problem_statement_is_flagged_without_inventing_a_regime(self):
        """Wording churn is still conservative, but must not claim a false regime conflict."""
        compared = compare_assignments(
            exchanger(text="The exchanger operates at steady state in a counterflow arrangement."),
            exchanger(text="Operating at steady state, the counterflow exchanger is to be sized."),
        )
        self.assertFalse(
            any("conflict" in reason or "regime" in reason for reason in compared["reasons"]),
            msg=f"no regime conflict exists here, got {compared['reasons']}",
        )


if __name__ == "__main__":
    unittest.main()
