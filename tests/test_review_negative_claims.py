"""Tests for the negative-claim reviewer.

These assert the DETECTOR behaves correctly on synthetic packs built for the
purpose. They deliberately do NOT assert that the real packs under curriculum/
are free of hits: every hit the tool produced on the live packs when it was
written was benign, so such an assertion would encode today's prose rather than
a property worth holding, and would break on the next honest edit.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from review_negative_claims import review  # noqa: E402


def _pack(tmp: Path, body: dict) -> Path:
    path = tmp / "pack.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


class ReviewNegativeClaims(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_catches_a_pack_that_denies_a_document_it_cites(self):
        """The case the tool exists for, in the shape it really occurred.

        The citation names a 'design project prompt'; the denial says only 'the
        prompt'. Matching the full phrase would miss this, which is why the tool
        matches on the head noun.
        """
        hits = review(_pack(self.tmp, {
            "assignment_families": [
                {"basis": "the design project prompt, which states the report rules"}
            ],
            "methods": [
                {"pitfalls": ["Not confirmed against the prompt, which was not in "
                              "the archived folder."]}
            ],
        }))
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["head"], "prompt")
        self.assertEqual(hits[0]["cited_documents"], ["design project prompt"])
        self.assertFalse(hits[0]["several_documents_share_this_head"])

    def test_plain_negation_is_not_a_denial_of_existence(self):
        """'a lecture deck, not a spec' qualifies a document; it does not deny one."""
        hits = review(_pack(self.tmp, {
            "conventions": {
                "graphs": {"basis": "the ENGR 204 lecture slides and the department standards"},
                "note": "The ENGR 204 lecture slides are a lecture deck, not a spec, "
                        "and the rule is not established for other courses.",
            }
        }))
        self.assertEqual(hits, [])

    def test_an_absence_stated_in_a_basis_field_is_not_a_citation(self):
        """A basis may itself record an absence.

        'No report, lab manual, or report sheet survives' must not register a
        lab manual as a document the pack relies on, or the pack contradicts
        itself by definition.
        """
        hits = review(_pack(self.tmp, {
            "assignment_families": [
                {"basis": "No report, lab manual, or report sheet survives, so "
                          "structure and layout are unknown."}
            ]
        }))
        self.assertEqual(hits, [])

    def test_a_bare_head_noun_does_not_ground_a_citation(self):
        """'the handout' names no particular document, so nothing can contradict it."""
        hits = review(_pack(self.tmp, {
            "format": {"basis": "copied from the handout"},
            "coverage": {"notes": "No handout survives for this course."},
        }))
        self.assertEqual(hits, [])

    def test_precedence_is_not_treated_as_provenance(self):
        """A precedence entry is an authority order, not a claim to hold the document.

        Packs routinely name a document there precisely to say they lack it.
        """
        hits = review(_pack(self.tmp, {
            "format": {"precedence": ["the specific homework prompt (none survive in "
                                      "the archive; ask the student for it)"]},
            "coverage": {"notes": "There are no assignment prompts and no rubric."},
        }))
        self.assertEqual(hits, [])

    def test_flags_when_several_cited_documents_share_a_head_noun(self):
        """Ambiguous referents are surfaced as lower confidence, not dropped.

        A pack may legitimately cite one lab's handout and deny another's.
        """
        hits = review(_pack(self.tmp, {
            "assignment_families": [
                {"basis": "the lab 01 handout"},
                {"basis": "the societal issues handout"},
            ],
            "coverage": {"notes": "The Lab 06 handouts were not kept."},
        }))
        self.assertTrue(hits)
        self.assertTrue(all(h["several_documents_share_this_head"] for h in hits))

    def test_reports_where_the_contradiction_lives(self):
        """A hit has to be actionable: it names both ends of the contradiction."""
        hits = review(_pack(self.tmp, {
            "format": {"figures": {"basis": "the ENGR 319 memo format spec"}},
            "coverage": {"notes": "No memo format spec was retained."},
        }))
        self.assertEqual(len(hits), 1)
        hit = hits[0]
        self.assertEqual(hit["cited_at"], [".format.figures.basis"])
        self.assertEqual(hit["denied_at"], ".coverage.notes")
        self.assertIn("No memo format spec was retained.", hit["sentence"])

    def test_one_denying_sentence_is_reported_once(self):
        """A phrase can carry several head nouns; the contradiction is still one thing.

        'the ENGR 319 memo format spec' contains both 'memo' and 'spec'. Reporting
        it twice only lengthens the list a human has to read.
        """
        hits = review(_pack(self.tmp, {
            "format": {"figures": {"basis": "the ENGR 319 memo format spec"}},
            "coverage": {"notes": "No memo format spec was retained."},
        }))
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["heads"], ["memo", "spec"])

    def test_runs_over_the_real_packs_without_raising(self):
        """The tool must survive every shipped pack. What it finds is for a human."""
        curriculum = Path(__file__).resolve().parents[1] / "curriculum"
        packs = sorted(curriculum.rglob("pack.json"))
        self.assertTrue(packs, "expected shipped packs to review")
        for pack in packs:
            for hit in review(pack):
                self.assertIn("sentence", hit)
                self.assertIn("denied_at", hit)


if __name__ == "__main__":
    unittest.main()
