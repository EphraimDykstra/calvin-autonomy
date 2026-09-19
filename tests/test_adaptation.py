import tempfile
import unittest
import json
from pathlib import Path

from engineering_assistant.adaptation import build_adaptation_manifest
from engineering_assistant.cli import main


def assignment(**changes):
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
        "deliverables": ["calculation"],
        "text": "Size the cantilever beam under the stated load.",
    }
    value.update(changes)
    return value


class AdaptationTests(unittest.TestCase):
    def test_adapt_cli_writes_manifest_without_prior_identity_or_result(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            current_path = root / "current.json"
            prior_path = root / "prior.json"
            out_path = root / "manifest.json"
            current_path.write_text(json.dumps(assignment(deliverables=["calculation", "plot"])))
            prior_path.write_text(json.dumps({
                "id": "prior-student-007",
                "student_name": "Prior Student",
                "student_id": "S-007",
                "assignment": assignment(),
                "solution": {"answer": 123.0},
                "artifacts": ["private/prior.pdf"],
            }))
            result = main([
                "--workspace", str(root / "workspace"), "adapt", str(current_path),
                str(prior_path), "--out", str(out_path), "--name", "Current Student",
                "--student-id", "run-8",
            ])
            self.assertEqual(result, 0)
            manifest = json.loads(out_path.read_text())
            encoded = json.dumps(manifest)
            self.assertEqual(manifest["identity"], {"name": "Current Student", "student_id": "run-8"})
            self.assertNotIn("Prior Student", encoded)
            self.assertNotIn("S-007", encoded)
            self.assertNotIn("123.0", encoded)

    def test_numeric_and_unit_twist_requires_recalculation(self):
        prior = {"id": "reference", "assignment": assignment(), "artifacts": []}
        current = assignment(inputs={"length": {"value": 6.56, "unit": "ft"}, "load": {"value": 100, "unit": "N"}})
        manifest = build_adaptation_manifest(current, prior)
        self.assertTrue(manifest["recalculation_required"])
        self.assertEqual(manifest["classification"], "input_variant")
        self.assertTrue(any(item["field"] == "inputs" and "unit" in item["reason"] for item in manifest["stale_fields"]))
        self.assertEqual(manifest["identity"], {"name": "<student-name>", "student_id": "<student-id>"})

    def test_added_plot_is_deliverable_change_and_coverage_is_current(self):
        prior = {"id": "reference", "assignment": assignment(), "artifacts": []}
        current = assignment(deliverables=["calculation", "stress plot"])
        manifest = build_adaptation_manifest(current, prior, {"name": "Current Student", "student_id": "run-7"})
        self.assertEqual(manifest["classification"], "presentation_only")
        self.assertFalse(manifest["recalculation_required"])
        self.assertTrue(any(item.get("field") == "deliverables" for item in manifest["deliverable_changes"]))
        self.assertEqual(len(manifest["current_requirement_coverage"]), 2)
        self.assertTrue(all(item["current_work_required"] for item in manifest["current_requirement_coverage"]))
        self.assertEqual(manifest["identity"]["name"], "Current Student")

    def test_changed_boundary_and_method_mark_method_unfit(self):
        prior = {"id": "reference", "assignment": assignment(), "artifacts": []}
        current = assignment(method="finite element", assumptions={"boundary": "pinned-pinned", "linear": True})
        manifest = build_adaptation_manifest(current, prior)
        self.assertTrue(manifest["recalculation_required"])
        self.assertEqual(manifest["classification"], "method_changing_variant")
        self.assertEqual(manifest["method_validity"]["status"], "changed")
        self.assertFalse(manifest["method_validity"]["direct_reuse"])
        self.assertTrue(any(item["field"] == "assumptions" for item in manifest["stale_fields"]))

    def test_stale_result_and_prior_identity_are_never_copied(self):
        prior = {
            "id": "alice-student-001",
            "student_name": "Alice Example",
            "student_id": "S-12345",
            "assignment": assignment(student_name="Alice Example"),
            "solution": {"student_name": "Alice Example", "answer": 42.0},
            "result": {"value": 42.0},
            "artifacts": ["private/alice-answer.pdf"],
        }
        manifest = build_adaptation_manifest(assignment(), prior, {"name": "Bob Example", "student_id": "run-9"})
        self.assertTrue(manifest["recalculation_required"])
        self.assertTrue(any(item["kind"] == "stale_prior_result" for item in manifest["stale_fields"]))
        self.assertTrue(any(item.get("field") == "prior_results" for item in manifest["deliverable_changes"]))
        serialized = str(manifest)
        self.assertNotIn("Alice Example", serialized)
        self.assertNotIn("S-12345", serialized)
        self.assertNotIn("alice-student-001", serialized)
        self.assertNotIn("42.0", serialized)
        self.assertIn("Bob Example", serialized)


def exchanger(**changes):
    """Synthetic, invented exchanger assignment shared by the lookalike tests."""
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
    value.update(changes)
    return value


def prior_of(assignment_value):
    return {"id": "prior-reference", "assignment": assignment_value, "artifacts": []}


class LookalikeManifestTests(unittest.TestCase):
    """The manifest is what a host consumes, so the lookalike guard must hold here.

    A classifier that says ``method_changing_variant`` while the manifest still
    says ``recalculation_required: False`` and ``valid_for_adaptation`` is a fix
    that looks complete and is not.
    """

    LOOKALIKES = {
        "parallel to counterflow": "The exchanger operates at steady state in a counterflow arrangement.",
        "steady to transient": "The exchanger is started from cold and the transient response is of interest.",
        "constraint added": "The exchanger operates at steady state in a parallel-flow arrangement. Account for the pressure drop.",
        "requested quantity changed": "At steady state in a parallel-flow arrangement, find the exit temperature of the cold stream.",
    }

    def test_every_lookalike_forces_recalculation_and_blocks_method_reuse(self):
        for name, text in self.LOOKALIKES.items():
            with self.subTest(case=name):
                manifest = build_adaptation_manifest(exchanger(text=text), prior_of(exchanger()))
                self.assertEqual(manifest["classification"], "method_changing_variant")
                self.assertTrue(
                    manifest["recalculation_required"],
                    msg="a lookalike must never report that no recalculation is needed",
                )
                self.assertNotEqual(manifest["method_validity"]["status"], "valid_for_adaptation")
                self.assertFalse(manifest["method_validity"]["direct_reuse"])
                self.assertFalse(
                    any(part.get("safe_to_reuse") for part in manifest["reusable_parts"]),
                    msg="nothing may be marked safe to reuse across a method change",
                )

    def test_text_identical_requirement_is_not_reusable_under_a_method_change(self):
        """Requirement wording unchanged does not mean the prior work survives."""
        manifest = build_adaptation_manifest(
            exchanger(text="The exchanger operates at steady state in a counterflow arrangement."),
            prior_of(exchanger()),
        )
        coverage = manifest["current_requirement_coverage"]
        self.assertEqual(len(coverage), 2)
        for item in coverage:
            self.assertTrue(item["current_work_required"])
            self.assertTrue(
                item["reuse_blocked_by"],
                msg=f"requirement {item['id']} reads reusable under a method change: {item}",
            )

    def test_explicit_method_rename_blocks_every_requirement(self):
        manifest = build_adaptation_manifest(exchanger(method="effectiveness NTU"), prior_of(exchanger()))
        self.assertEqual(manifest["method_validity"]["status"], "changed")
        for item in manifest["current_requirement_coverage"]:
            self.assertIn("method", item["reuse_blocked_by"])

    def test_incomparable_prior_never_reads_permissively(self):
        """no_useful_match establishes nothing, so nothing may look reusable.

        Matching method labels are not evidence when the comparison itself
        failed: this is the path where least is known, so it must be the most
        conservative, not the least.
        """
        incomparable = prior_of(exchanger(family="pipe-network"))
        manifest = build_adaptation_manifest(exchanger(), incomparable)
        self.assertEqual(manifest["classification"], "no_useful_match")
        self.assertTrue(manifest["recalculation_required"])
        self.assertFalse(manifest["method_validity"]["direct_reuse"])
        self.assertTrue(manifest["reuse_blocked_by"])
        for item in manifest["current_requirement_coverage"]:
            self.assertTrue(
                item["reuse_blocked_by"],
                msg=f"requirement {item['id']} reads reusable against an incomparable prior: {item}",
            )

    def test_prior_numerical_results_are_never_reused(self):
        prior = {
            "id": "prior-reference",
            "assignment": exchanger(),
            "result": {"area": 18.4},
            "solution": {"answer": 18.4},
            "artifacts": ["artifacts/prior.pdf"],
        }
        for text in self.LOOKALIKES.values():
            with self.subTest(text=text[:40]):
                manifest = build_adaptation_manifest(exchanger(text=text), prior)
                self.assertTrue(manifest["recalculation_required"])
                self.assertTrue(any(item["kind"] == "stale_prior_result" for item in manifest["stale_fields"]))
                self.assertNotIn("18.4", str(manifest))


class ManifestStaysUsefulTests(unittest.TestCase):
    """The other direction: unchanged requirements must still read unchanged."""

    def test_unchanged_requirement_survives_a_pure_input_change(self):
        base = exchanger()
        manifest = build_adaptation_manifest(
            exchanger(inputs={**base["inputs"], "T_hot_in": {"value": 95.0, "unit": "C"}}),
            prior_of(base),
        )
        self.assertEqual(manifest["classification"], "input_variant")
        coverage = manifest["current_requirement_coverage"]
        self.assertTrue(all(item["status"] == "unchanged_requirement" for item in coverage))
        self.assertTrue(
            all(not item["reuse_blocked_by"] for item in coverage),
            msg="an input change must not block the prior approach for every requirement",
        )
        # Numbers still have to be redone even though the approach carries over.
        self.assertTrue(manifest["recalculation_required"])
        self.assertTrue(all(item["current_work_required"] for item in coverage))

    def test_unchanged_requirement_survives_a_deliverables_only_change(self):
        manifest = build_adaptation_manifest(
            exchanger(deliverables=["calculation", "summary figure"]), prior_of(exchanger())
        )
        self.assertEqual(manifest["classification"], "presentation_only")
        for item in manifest["current_requirement_coverage"]:
            self.assertEqual(item["status"], "unchanged_requirement")
            self.assertFalse(item["reuse_blocked_by"])

    def test_only_the_edited_requirement_is_marked_changed(self):
        current = exchanger(requirements=[
            {"id": "q1", "text": "Determine the required heat transfer area"},
            {"id": "q2", "text": "Report the outlet pressure of each stream"},
        ])
        coverage = build_adaptation_manifest(current, prior_of(exchanger()))["current_requirement_coverage"]
        by_id = {item["id"]: item for item in coverage}
        self.assertEqual(by_id["q1"]["status"], "unchanged_requirement")
        self.assertEqual(by_id["q2"]["status"], "changed_requirement")

    def test_coverage_does_not_depend_on_requirement_order(self):
        """An exact ID match must win over a fuzzy text match, whatever the order.

        With a similarly worded requirement listed first, a fuzzy match could
        consume the prior entry that an exact ID was entitled to, so the same
        two requirements classified differently depending on their order.
        """
        prior = exchanger(requirements=[{"id": "q1", "text": "Determine the required heat transfer area"}])
        q1 = {"id": "q1", "text": "Determine the required heat transfer area"}
        q9 = {"id": "q9", "text": "Determine the required heat transfer area"}
        for label, ordering in (("id-first", [q1, q9]), ("id-last", [q9, q1])):
            with self.subTest(order=label):
                coverage = build_adaptation_manifest(
                    exchanger(requirements=ordering), prior_of(prior)
                )["current_requirement_coverage"]
                by_id = {item["id"]: item for item in coverage}
                self.assertEqual(
                    by_id["q1"]["status"], "unchanged_requirement",
                    msg=f"the exact ID match lost its prior requirement in {label} order: {coverage}",
                )
                self.assertTrue(by_id["q1"]["prior_alignment"])
                self.assertEqual(by_id["q9"]["status"], "new_requirement")
                self.assertFalse(by_id["q9"]["prior_alignment"])

    def test_one_prior_requirement_is_not_consumed_twice(self):
        """An ID match must retire the prior requirement it consumed."""
        prior = exchanger(requirements=[{"id": "q1", "text": "Determine the required heat transfer area"}])
        current = exchanger(requirements=[
            {"id": "q1", "text": "Determine the required heat transfer area"},
            {"id": "q9", "text": "Determine the required heat transfer area"},
        ])
        coverage = build_adaptation_manifest(current, prior_of(prior))["current_requirement_coverage"]
        aligned = [item for item in coverage if item["prior_alignment"]]
        self.assertEqual(
            len(aligned), 1,
            msg=f"one prior requirement backed two current requirements: {coverage}",
        )


if __name__ == "__main__":
    unittest.main()


class RecalculationFlagSafetyTests(unittest.TestCase):
    """What protects the run when recalculation_required is False.

    ``recalculation_required`` answers whether a prior numeric result exists
    that must not be copied, not whether the current run must do its own work.
    When a prior example carries no results at all it is False, and issue #15
    asked whether that is a false-ready path.  It is not: every requirement
    still reports ``current_work_required`` and nothing is ever marked safe to
    reuse.  These tests pin that, so a later change cannot flip the flag to a
    constant True while quietly weakening the fields that actually carry the
    guarantee.
    """

    @staticmethod
    def _assignment(**overrides):
        base = {
            "family": "beam", "method": "euler-bernoulli", "title": "Beam",
            "text": "Find the maximum bending stress.",
            "inputs": {"length": {"value": 2.0, "unit": "m"}, "load": {"value": 100, "unit": "N"}},
            "requirements": [
                {"id": "r1", "text": "Calculate maximum bending stress"},
                {"id": "r2", "text": "Report the factor of safety"},
            ],
            "deliverables": ["calculation"],
        }
        base.update(overrides)
        return base

    def _manifest(self, current):
        prior = {"id": "reference", "assignment": self._assignment(), "artifacts": []}
        return build_adaptation_manifest(current, prior)

    def test_an_exact_repeat_of_a_resultless_prior_still_requires_all_current_work(self):
        manifest = self._manifest(self._assignment())
        self.assertEqual(manifest["classification"], "exact_repeat")
        self.assertFalse(manifest["recalculation_required"])
        coverage = manifest["current_requirement_coverage"]
        self.assertEqual(len(coverage), 2)
        self.assertTrue(
            all(item["current_work_required"] for item in coverage),
            "every requirement must still demand current work",
        )
        self.assertTrue(
            all(part["safe_to_reuse"] is False for part in manifest["reusable_parts"]),
            "no part may be marked safe to reuse",
        )

    def test_a_presentation_only_change_of_a_resultless_prior_requires_all_current_work(self):
        manifest = self._manifest(self._assignment(deliverables=["calculation", "stress plot"]))
        self.assertEqual(manifest["classification"], "presentation_only")
        self.assertFalse(manifest["recalculation_required"])
        self.assertTrue(all(item["current_work_required"] for item in manifest["current_requirement_coverage"]))
        self.assertTrue(all(part["safe_to_reuse"] is False for part in manifest["reusable_parts"]))

    def test_a_prior_that_does_carry_results_forces_recalculation(self):
        """The flag is not vacuous: give the prior a result and it flips."""
        prior = {
            "id": "reference",
            "assignment": self._assignment(),
            "artifacts": [],
            "results": {"max_stress": {"value": 12.0, "unit": "MPa"}},
        }
        manifest = build_adaptation_manifest(self._assignment(), prior)
        self.assertTrue(
            manifest["recalculation_required"],
            "a prior result must always force recalculation",
        )
        self.assertTrue(any(item["kind"] == "stale_prior_result" for item in manifest["stale_fields"]))
