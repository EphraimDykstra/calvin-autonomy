"""Structural checks for the ENGR 328 curriculum pack."""
import json
import unittest
from pathlib import Path

from engineering_assistant.course_profile import _validate_rendering
from engineering_assistant.identity import find_identity_leaks
from engineering_assistant.rendering import _body_page_budget

ROOT = Path(__file__).resolve().parents[1] / "curriculum" / "engr328"
TOP_KEYS = {"schema_version", "course", "coverage", "course_policy", "format", "methods", "assignment_families"}
COVERAGE_LEVELS = {"high", "partial", "none"}


class Engr328PackTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pack = json.loads((ROOT / "pack.json").read_text(encoding="utf-8"))

    def test_shared_shape(self):
        self.assertTrue(TOP_KEYS <= set(self.pack))
        self.assertEqual(self.pack["schema_version"], 1)
        self.assertEqual(self.pack["course"]["id"], "engr328")
        for key in ("format", "methods", "assignments"):
            self.assertIn(self.pack["coverage"][key], COVERAGE_LEVELS)
        self.assertTrue(self.pack["coverage"]["notes"].strip())

    def test_no_identity_keys_or_paths(self):
        self.assertEqual(find_identity_leaks(self.pack), [])

    def test_policy_is_unknown_not_invented(self):
        policy = self.pack["course_policy"]
        self.assertEqual(policy["permitted"], [])
        self.assertEqual(policy["prohibited"], [])
        self.assertIsNone(policy["student_asked"])
        self.assertIsNone(policy["professor_answer"])

    def test_renderer_settings_are_valid(self):
        rendering = self.pack["format"]["rendering"]
        # The real validator must accept the block, not just in-range values.
        _validate_rendering(rendering)
        self.assertIsNone(_body_page_budget(rendering))
        for family in self.pack["assignment_families"]:
            for stage in family["stage_details"]:
                if "max_body_pages" in stage:
                    budget = _body_page_budget({**rendering, "max_body_pages": stage["max_body_pages"]})
                    self.assertEqual(budget, stage["max_body_pages"])
        for key in ("title_page", "abstract", "number_body_pages", "table_captions_above", "figure_captions_below"):
            self.assertIs(rendering[key], True)
        self.assertTrue(8 <= rendering["body_font_size"] <= 14)
        self.assertTrue(1 <= rendering["line_spacing"] <= 2)
        self.assertTrue(0.5 <= rendering["margin_inches"] <= 1.5)
        # The margin has no evidence; it must stay labelled as a default.
        self.assertEqual(self.pack["format"]["rendering_basis"]["margin_inches"], "default")

    def test_methods_and_families_are_well_formed(self):
        ids = [m["id"] for m in self.pack["methods"]]
        self.assertEqual(len(ids), len(set(ids)))
        for method in self.pack["methods"]:
            self.assertTrue(method["steps"] and method["pitfalls"], method["id"])
        for family in self.pack["assignment_families"]:
            details = {d["id"] for d in family.get("stage_details", [])}
            self.assertEqual(details, set(family["stages"]), family["id"])
            self.assertTrue(family["what_good_looks_like"], family["id"])

    def test_every_exemplar_reference_resolves(self):
        referenced = {e for f in self.pack["assignment_families"] for e in f["exemplars"]}
        present = {p.stem for p in (ROOT / "exemplars").glob("*.md")}
        self.assertEqual(referenced, present)
        for stem in present:
            text = (ROOT / "exemplars" / f"{stem}.md").read_text(encoding="utf-8")
            self.assertIn(f"`{stem}`", text)
            self.assertIn("[Student Name]", text)

    def test_intake_is_addressable_and_grounded(self):
        """Each lab family says what a student must hand over, as fetchable nodes.

        The list is only reachable if every item carries a string ``id`` with no
        dot in it: ``pack_query._children`` gives a list no children otherwise,
        and a host would have to pull the whole block to read one line of it.
        """
        for family_id in ("ac-lab", "ic-lab"):
            family = next(f for f in self.pack["assignment_families"] if f["id"] == family_id)
            intake = family["intake"]
            self.assertTrue(intake, family_id)
            ids = [item["id"] for item in intake]
            self.assertEqual(len(ids), len(set(ids)), family_id)
            stages = set(family["stages"])
            for item in intake:
                where = f"{family_id}.{item['id']}"
                self.assertRegex(item["id"], r"^[a-z0-9][a-z0-9-]*$", where)
                for field in ("need", "why", "basis"):
                    self.assertTrue(item[field].strip(), where)
                # Every item says who supplies it, and an item the handout
                # answers must say what to do when no handout arrives, so the
                # list never dead-ends on a document the student does not have.
                self.assertIn(item["provided_by"], {"student", "handout", "pack"}, where)
                if item["provided_by"] == "handout":
                    self.assertTrue(item["if_absent"].strip(), where)
                # A stage list that names an unknown stage would send a host
                # looking for a submission this family does not have.
                self.assertLessEqual(set(item.get("stages", ())), stages, where)

    def test_intake_never_restates_the_stage_details(self):
        """Per-stage facts stay in ``stage_details``; intake points at them.

        Copying a stage's measured inputs into intake would give one fact two
        homes, and they would drift apart the first time a handout changed.
        """
        for family in self.pack["assignment_families"]:
            for item in family.get("intake", []):
                for stage in family["stage_details"]:
                    for measured in stage.get("measured_inputs", []):
                        self.assertNotIn(measured, item["need"], f"{family['id']}.{item['id']}")

    def test_page_budgets_follow_the_stated_limits(self):
        for family in ("ac-lab", "ic-lab"):
            fam = next(f for f in self.pack["assignment_families"] if f["id"] == family)
            budgets = {d["id"]: d["max_body_pages"] for d in fam["stage_details"]}
            self.assertEqual(budgets["final-report"], 4)
            self.assertTrue(all(v <= 3 for k, v in budgets.items() if k != "final-report"))


if __name__ == "__main__":
    unittest.main()
