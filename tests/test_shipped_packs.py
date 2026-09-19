"""Every pack that ships must load, and must name what its rules rest on.

test_curriculum.py proves the loader refuses a bad pack.  This proves the packs
actually in the tree are not bad ones.  Without it the loader only ever sees
fixtures, and a malformed pack reaches a student before anything objects.
"""

import json
import unittest
from pathlib import Path

from engineering_assistant.curriculum import (
    COVERAGE_DIMENSIONS,
    DEFAULT_CURRICULUM,
    POLICY_CONFIDENCE,
    TOOL_COVERAGE_DIMENSIONS,
    coverage_report,
    load_packs,
    load_tool_packs,
)


CURRICULUM = Path(__file__).resolve().parents[1] / "curriculum"

# Per-item provenance is spelled "basis" everywhere.  The packs were written by
# different authors against one written specification, and two spellings of the
# same idea is how a consumer ends up reading only half of it.
PROVENANCE_KEY = "basis"

# Packs attach provenance at the granularity their evidence actually has: the
# lab packs tag an assignment family, while ENGR 328 tags individual rules and
# stages.  Requiring one granularity would force an author to invent a claim at
# a level they cannot support, so require only that a family says somewhere
# what it rests on.
PROVENANCE_KEYS = frozenset({PROVENANCE_KEY, "grading_structure_basis", "evidence_note"})

# An exemplar is referenced by id; the file is that id with a .md suffix.
EXEMPLAR_SUFFIX = ".md"


def _names_provenance(value):
    """True if ``value`` or anything inside it carries a provenance key."""
    if isinstance(value, dict):
        if PROVENANCE_KEYS & value.keys():
            return True
        return any(_names_provenance(item) for item in value.values())
    if isinstance(value, list):
        return any(_names_provenance(item) for item in value)
    return False


def _packs():
    return load_packs(CURRICULUM)


class ShippedPackTests(unittest.TestCase):
    def test_every_shipped_pack_loads(self):
        # load_packs raises on the first bad pack, so reaching here is the
        # assertion.  The count guards against the glob silently matching none.
        packs = _packs()
        self.assertTrue(packs, f"no packs found under {CURRICULUM}")

    def test_coverage_report_describes_every_pack(self):
        report = coverage_report(_packs())
        self.assertEqual(report["course_count"], len(_packs()))
        for course in report["courses"]:
            self.assertIn(course["policy_confidence"], POLICY_CONFIDENCE)
            for dimension in COVERAGE_DIMENSIONS:
                self.assertIn(dimension, course["coverage"])

    def test_every_pack_explains_what_is_thin(self):
        # A coverage level without a note tells a student a course is "partial"
        # and nothing about which part.  The note is the actionable half.
        for pack_id, pack in _packs().items():
            with self.subTest(pack=pack_id):
                notes = pack["coverage"].get("notes")
                self.assertTrue(
                    isinstance(notes, str) and notes.strip(),
                    f"{pack_id}: coverage.notes must say what is thin",
                )

    def test_assignment_families_name_their_provenance(self):
        for pack_id, pack in _packs().items():
            for family in pack.get("assignment_families", []):
                with self.subTest(pack=pack_id, family=family.get("id")):
                    self.assertTrue(
                        _names_provenance(family),
                        f"{pack_id}: an assignment family must say what it rests on, "
                        f"through one of {sorted(PROVENANCE_KEYS)}",
                    )

    def test_no_pack_spells_provenance_a_second_way(self):
        # Catches the divergence this rename fixed, rather than trusting the
        # next pack author to have read the convention.
        for path in sorted(CURRICULUM.glob("*/pack.json")):
            with self.subTest(pack=path.parent.name):
                self.assertNotIn(
                    '"evidence":',
                    path.read_text(encoding="utf-8"),
                    f"{path.parent.name}: use '{PROVENANCE_KEY}' for provenance",
                )

    def test_a_policy_that_cannot_be_stated_carries_no_terms(self):
        # The loader enforces this, but assert it against the real packs too:
        # an archived syllabus read as current is the specific false claim this
        # product cannot afford, and it would ship silently.
        for pack_id, pack in _packs().items():
            policy = pack["course_policy"]
            if policy["confidence"] in {"stale", "unknown"}:
                with self.subTest(pack=pack_id):
                    self.assertFalse(policy.get("permitted"))
                    self.assertFalse(policy.get("prohibited"))

    def test_exemplars_referenced_by_a_pack_exist(self):
        # A dangling reference degrades to "no exemplar" at the point of use,
        # which reads to the host as a course with nothing to adapt from.
        for path in sorted(CURRICULUM.glob("*/pack.json")):
            pack = json.loads(path.read_text(encoding="utf-8"))
            for family in pack.get("assignment_families", []):
                for name in family.get("exemplars", []) or []:
                    with self.subTest(pack=path.parent.name, exemplar=name):
                        exemplar = path.parent / "exemplars" / (name + EXEMPLAR_SUFFIX)
                        self.assertTrue(
                            exemplar.is_file(),
                            f"{path.parent.name}: missing exemplar {exemplar.name}",
                        )


class InstructorPrivacyTests(unittest.TestCase):
    """No pack names a person.  This has to be structural, not remembered."""

    def test_no_pack_declares_an_instructor(self):
        # An instructor is a third party who never agreed to appear in a public
        # repository, and the packs are the tempting place to put them because
        # conventions really do vary by instructor.  Key those by course code
        # instead: it survives a staffing change and covers every section.
        for pack_id, pack in _packs().items():
            with self.subTest(pack=pack_id):
                self.assertIsNone(
                    pack.get("course", {}).get("professor"),
                    f"{pack_id}: course.professor must be null; key rules by course code",
                )

    def test_exemplars_use_a_placeholder_for_an_instructor(self):
        # A title page or memo header genuinely needs a name.  The pack records
        # the slot; the student supplies the value at run time.
        for path in sorted(CURRICULUM.glob("*/exemplars/*.md")):
            text = path.read_text(encoding="utf-8")
            with self.subTest(exemplar=path.name):
                self.assertNotIn(
                    "Professor ",
                    text,
                    f"{path.name}: use the [Instructor] placeholder, never a name",
                )


class RenderingBudgetTests(unittest.TestCase):
    """A null page budget is no check, not a permissive default."""

    def test_a_null_page_budget_says_where_the_real_one_lives(self):
        # _body_page_budget returns None for a null, and the renderer then
        # checks nothing.  A pack may legitimately leave it null when the limit
        # varies by stage, but it must then point at the stage that has it, or
        # the rule silently stops being enforced.
        for pack_id, pack in _packs().items():
            rendering = pack.get("format", {}).get("rendering")
            if not isinstance(rendering, dict) or "max_body_pages" not in rendering:
                continue
            if rendering["max_body_pages"] is not None:
                continue
            with self.subTest(pack=pack_id):
                self.assertTrue(
                    rendering.get("max_body_pages_note"),
                    f"{pack_id}: a null max_body_pages must say where the real limit lives",
                )
                stage_limits = [
                    stage.get("max_body_pages")
                    for family in pack.get("assignment_families", [])
                    for stage in family.get("stage_details", [])
                ]
                self.assertTrue(
                    [limit for limit in stage_limits if isinstance(limit, int) and limit > 0],
                    f"{pack_id}: no stage declares a page limit, so none can be applied",
                )


class MagnitudeUnitTests(unittest.TestCase):
    """A range a check cannot read is a range that never gets checked."""

    def test_every_magnitude_unit_parses(self):
        # The unit registry was first built from thermodynamics EES files, and
        # the mechanics packs then used in, ksi and lbf-ft, none of which it
        # knew.  A review step pointing at those ranges would have failed.
        from engineering_assistant.units import UnitError, parse_unit

        for pack_id, pack in _packs().items():
            for entry in pack.get("magnitudes", []):
                with self.subTest(pack=pack_id, quantity=entry.get("quantity", "")[:40]):
                    try:
                        parse_unit(entry["unit"])
                    except UnitError as exc:
                        self.fail(f"{pack_id}: magnitude unit {entry['unit']!r} does not parse: {exc}")


class SharedToolPackTests(unittest.TestCase):
    """The EES pack ships with the most exemplars and was checked by nothing."""

    def test_every_tool_pack_loads(self):
        packs = load_tool_packs(CURRICULUM)
        self.assertTrue(packs, f"no tool packs found under {CURRICULUM}/_shared")

    def test_tool_packs_are_not_loaded_as_courses(self):
        # A tool pack answers different questions and has no course_policy.
        # Loading it as a course would fail, so the two must stay separate.
        self.assertNotIn("_shared", load_packs(CURRICULUM))

    def test_tool_coverage_is_reported(self):
        report = coverage_report(load_packs(CURRICULUM), load_tool_packs(CURRICULUM))
        self.assertTrue(report["tools"])
        for tool in report["tools"]:
            for dimension in TOOL_COVERAGE_DIMENSIONS:
                self.assertIn(dimension, tool["coverage"])
            self.assertTrue(
                isinstance(tool["notes"], str) and tool["notes"].strip(),
                f"{tool['id']}: coverage.notes must say what is thin",
            )


class DefaultCurriculumTests(unittest.TestCase):
    def test_default_is_install_relative(self):
        # The launcher does not change directory, so a relative default would
        # report no coverage from a subdirectory: a student told the system
        # knows nothing about a course it knows a great deal about.
        self.assertTrue(DEFAULT_CURRICULUM.is_absolute())
        self.assertEqual(DEFAULT_CURRICULUM, CURRICULUM)
        self.assertTrue(load_packs(DEFAULT_CURRICULUM))


if __name__ == "__main__":
    unittest.main()
