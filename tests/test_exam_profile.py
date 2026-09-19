"""An exam profile must be refused unless it can establish its own honesty.

A profile is data claiming to describe a real assessment.  The claim is worth
something only if nothing in the repository can make it without saying what it
rests on, what it does not know, and whether the material behind it was ever
established as genuine.  Before this existed, `load_pack` ignored the block
entirely: a profile could assert a five-problem exam with a 50 minute limit,
sourced from nothing, and load without complaint.

Two failures are specifically guarded here.  A profile that leaves a field
absent rather than naming it unknown reads downstream as zero, which is how a
thin profile quietly becomes a confident one.  And a profile built on material
nobody verified is exactly the case the project has already paid for: a file
named like a real final exam turned out to be machine-generated practice.
"""

import json
import tempfile
import unittest
from pathlib import Path

from engineering_assistant.curriculum import (
    CurriculumError,
    DEFAULT_CURRICULUM,
    EXAM_CONFIDENCE,
    SCHEMA_VERSION,
    SHAPE_LABEL_MAX,
    load_pack,
    load_packs,
)


def _profile(**overrides):
    """A minimal profile that passes, so the checks measure something."""
    profile = {
        "confidence": "stated",
        "basis": "one instructor course schedule.",
        "status": "thin: placement only.",
        "not_documented": ["question count", "time limit"],
        "assessments": [
            {"id": "test-1", "source": "course schedule", "topics": ["diffusion"]}
        ],
    }
    profile.update(overrides)
    return profile


def _pack(profile=None, **overrides):
    pack = {
        "schema_version": SCHEMA_VERSION,
        "course": {"id": "engr000", "code": "ENGR 000", "title": "Example Course"},
        "coverage": {
            "format": "none",
            "methods": "none",
            "assignments": "none",
            "notes": "Nothing is evidenced.",
        },
        "course_policy": {
            "source": "syllabus",
            "confidence": "unknown",
            "summary": "No policy was found.",
        },
        "assignment_families": [],
    }
    if profile is not None:
        pack["exam_profile"] = profile
    pack.update(overrides)
    return pack


class ExamProfileTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _write(self, pack):
        path = self.root / "pack.json"
        path.write_text(json.dumps(pack), encoding="utf-8")
        return path

    def _refuses(self, profile, expected):
        with self.assertRaises(CurriculumError) as caught:
            load_pack(self._write(_pack(profile)))
        self.assertIn(expected, str(caught.exception))

    # -- the benign answers have to be reachable ---------------------------

    def test_a_pack_with_no_profile_loads(self):
        # Most courses have no exam evidence at all.  An absent profile is an
        # honest absence, not a failure, or authors learn to invent one.
        loaded = load_pack(self._write(_pack()))
        self.assertNotIn("exam_profile", loaded)

    def test_a_complete_profile_loads(self):
        loaded = load_pack(self._write(_pack(_profile())))
        self.assertEqual(loaded["exam_profile"]["confidence"], "stated")

    def test_every_allowed_field_loads_together(self):
        # Guards the closed key set from the other direction: a legitimate
        # field wrongly left out of the set would refuse honest evidence.
        profile = _profile(
            quizzes="Three, marked tentative on the schedule.",
            stated_rules=["Box your answers.", "Units or no credit."],
            pre_submission_checklist=["Check that every page is numbered."],
            instructor_remarks=["Chapter 6 slide: list every value with units."],
            practice_generation_note="Inference, not a documented rule.",
            aids_provided={
                "equation_sheet": "One four-page sheet, equations only.",
                "calculator": "not documented",
                "open_note": "not documented",
                "time_limit": "not documented",
                "not_documented": "Whether a student-made sheet was allowed.",
            },
            question_shape=[
                {"type": "true or false", "source": "a lab prep sheet", "from_exam": False}
            ],
            assessments=[
                {
                    "id": "final",
                    "source": "course schedule",
                    "placement": "finals week",
                    "chapters": "not stated",
                    "topics": ["ceramics", "composites"],
                    "question_count": 5,
                    "points": "roughly equal across five problems",
                    "time_limit": "two hours",
                    "note": "No document says it is cumulative.",
                }
            ],
        )
        loaded = load_pack(self._write(_pack(profile)))
        self.assertEqual(len(loaded["exam_profile"]["assessments"]), 1)

    # -- content never enters ----------------------------------------------

    def test_an_unknown_key_is_refused(self):
        # The closed key set is the whole content mechanism.  It cannot read
        # prose, but it makes a field *named* for content impossible to add
        # without a schema change a reviewer sees.
        self._refuses(_profile(sample_question="A 2 m bar carries 40 kN..."), "unknown key")

    def test_a_key_named_for_an_answer_is_refused(self):
        for key in ("answer_key", "solutions", "problem_statements"):
            with self.subTest(key=key):
                self._refuses(_profile(**{key: "anything"}), "never content")

    def test_an_unknown_key_inside_an_assessment_is_refused(self):
        profile = _profile(
            assessments=[{"id": "t1", "source": "schedule", "problem_text": "..."}]
        )
        self._refuses(profile, "unknown key")

    def test_an_unknown_key_inside_aids_is_refused(self):
        self._refuses(_profile(aids_provided={"answers": "..."}), "unknown key")

    def test_an_unknown_key_inside_question_shape_is_refused(self):
        profile = _profile(
            question_shape=[
                {"type": "true or false", "source": "sheet", "from_exam": False, "text": "..."}
            ]
        )
        self._refuses(profile, "unknown key")

    def test_a_topic_longer_than_a_label_is_refused(self):
        # A topic is a label.  A problem restated as a topic is the one shape
        # of leak a length bound can actually catch.
        profile = _profile(
            assessments=[
                {"id": "t1", "source": "schedule", "topics": ["x" * (SHAPE_LABEL_MAX + 1)]}
            ]
        )
        self._refuses(profile, "these are labels")

    def test_a_question_type_longer_than_a_label_is_refused(self):
        profile = _profile(
            question_shape=[
                {"type": "y" * (SHAPE_LABEL_MAX + 1), "source": "sheet", "from_exam": False}
            ]
        )
        self._refuses(profile, "these are labels")

    # -- a profile says what it rests on -----------------------------------

    def test_a_profile_with_no_basis_is_refused(self):
        profile = _profile()
        del profile["basis"]
        self._refuses(profile, "needs a non-empty basis")

    def test_a_blank_basis_is_refused(self):
        self._refuses(_profile(basis="   "), "needs a non-empty basis")

    def test_a_profile_with_no_status_is_refused(self):
        profile = _profile()
        del profile["status"]
        self._refuses(profile, "needs a non-empty status")

    def test_an_assessment_with_no_source_is_refused(self):
        # Per-item provenance, at the granularity the evidence has: a profile
        # level basis cannot say which document placed which test.
        self._refuses(_profile(assessments=[{"id": "test-1"}]), "needs a non-empty source")

    def test_an_assessment_with_no_id_is_refused(self):
        self._refuses(
            _profile(assessments=[{"source": "course schedule"}]), "needs a non-empty id"
        )

    def test_a_question_shape_with_no_source_is_refused(self):
        profile = _profile(question_shape=[{"type": "true or false", "from_exam": True}])
        self._refuses(profile, "needs a non-empty source")

    # -- confidence, and what an unverified profile may claim --------------

    def test_a_missing_confidence_is_refused(self):
        profile = _profile()
        del profile["confidence"]
        self._refuses(profile, "confidence is None")

    def test_an_unrecognised_confidence_is_refused(self):
        # Refuse rather than degrade to a default: degrading converts "we do
        # not know" into a claim.
        self._refuses(_profile(confidence="probably"), "expected one of")

    def test_every_confidence_level_is_reachable(self):
        for level in sorted(EXAM_CONFIDENCE):
            with self.subTest(confidence=level):
                profile = _profile(confidence=level)
                if level == "unverified":
                    del profile["assessments"]
                loaded = load_pack(self._write(_pack(profile)))
                self.assertEqual(loaded["exam_profile"]["confidence"], level)

    def test_an_unverified_profile_may_not_describe_an_assessment(self):
        # The lesson, as a mechanism: a file named like a real final turned
        # out to be machine-generated practice, and every shape claim it
        # carried would have been false.
        self._refuses(_profile(confidence="unverified"), "carries assessments")

    def test_an_unverified_profile_may_not_list_aids(self):
        profile = _profile(
            confidence="unverified",
            aids_provided={"calculator": "any scientific calculator"},
        )
        del profile["assessments"]
        self._refuses(profile, "carries aids_provided")

    def test_an_unverified_profile_may_not_name_question_shapes(self):
        profile = _profile(
            confidence="unverified",
            question_shape=[{"type": "true or false", "source": "x", "from_exam": True}],
        )
        del profile["assessments"]
        self._refuses(profile, "carries question_shape")

    def test_an_unverified_profile_may_still_record_what_is_unknown(self):
        # Recording that unverified material exists is useful; describing an
        # exam from it is not.  The block stays usable for the honest case.
        profile = _profile(confidence="unverified")
        del profile["assessments"]
        loaded = load_pack(self._write(_pack(profile)))
        self.assertEqual(loaded["exam_profile"]["not_documented"], ["question count", "time limit"])

    # -- not_documented is required, and must name something ---------------

    def test_a_profile_with_no_not_documented_is_refused(self):
        profile = _profile()
        del profile["not_documented"]
        self._refuses(profile, "not_documented must be a list")

    def test_an_empty_not_documented_is_refused(self):
        # An empty list is a claim of completeness with nothing behind it.  A
        # genuinely complete profile should cost someone a reviewed change.
        self._refuses(_profile(not_documented=[]), "must name at least one thing")

    def test_a_blank_entry_in_not_documented_is_refused(self):
        self._refuses(_profile(not_documented=["  "]), "non-empty string")

    # -- a shape seen in materials is not a shape seen on an exam ----------

    def test_a_question_shape_with_no_from_exam_is_refused(self):
        profile = _profile(question_shape=[{"type": "true or false", "source": "a lab sheet"}])
        self._refuses(profile, "from_exam must be true or false")

    def test_a_non_boolean_from_exam_is_refused(self):
        profile = _profile(
            question_shape=[{"type": "true or false", "source": "x", "from_exam": "yes"}]
        )
        self._refuses(profile, "from_exam must be true or false")

    def test_both_from_exam_values_load(self):
        for observed in (True, False):
            with self.subTest(from_exam=observed):
                profile = _profile(
                    question_shape=[
                        {"type": "true or false", "source": "x", "from_exam": observed}
                    ]
                )
                loaded = load_pack(self._write(_pack(profile)))
                self.assertIs(loaded["exam_profile"]["question_shape"][0]["from_exam"], observed)

    # -- shape values are values, not blanks -------------------------------

    def test_a_blank_stated_field_is_refused(self):
        # A stated field that says nothing reads downstream as an answered
        # question.  Unknown is spelled by omission, or in not_documented.
        self._refuses(
            _profile(assessments=[{"id": "t1", "source": "s", "time_limit": ""}]),
            "needs a non-empty time_limit",
        )

    def test_a_question_count_of_zero_is_refused(self):
        self._refuses(
            _profile(assessments=[{"id": "t1", "source": "s", "question_count": 0}]),
            "question_count must be",
        )

    def test_a_boolean_question_count_is_refused(self):
        self._refuses(
            _profile(assessments=[{"id": "t1", "source": "s", "question_count": True}]),
            "question_count must be",
        )

    def test_a_question_count_reads_as_a_number_or_as_evidence(self):
        for count in (5, "five problems, one per chapter"):
            with self.subTest(question_count=count):
                profile = _profile(
                    assessments=[{"id": "t1", "source": "s", "question_count": count}]
                )
                loaded = load_pack(self._write(_pack(profile)))
                self.assertEqual(
                    loaded["exam_profile"]["assessments"][0]["question_count"], count
                )

    def test_a_profile_that_is_not_an_object_is_refused(self):
        self._refuses(["test-1"], "must be an object")

    def test_an_assessment_that_is_not_an_object_is_refused(self):
        self._refuses(_profile(assessments=["test-1"]), "must be an object")


class ShippedExamProfileTests(unittest.TestCase):
    """The loader is only worth something if the shipped packs go through it."""

    def test_a_shipped_pack_carries_a_profile(self):
        # Guards against the key being renamed or the block disappearing, in
        # which case every check above would pass while checking nothing that
        # ships.
        packs = load_packs(DEFAULT_CURRICULUM)
        carriers = [name for name, pack in packs.items() if "exam_profile" in pack]
        self.assertTrue(carriers, "no shipped pack carries an exam_profile")

    def test_a_shipped_from_exam_claim_is_not_contradicted_by_its_basis(self):
        # A tripwire, not a general check, and named for what it does: it
        # matches one known phrase, the one ENGR 205's basis uses to say no
        # exam paper survives.  A pack whose basis says "no final was kept"
        # would pass it while making exactly the claim this guards against.
        # Today it asserts nothing at all, because every shipped entry is
        # from_exam false and the loop skips before the assertion.  It earns
        # its place when real tests are mined and the first true appears;
        # calling it more than that would repeat the question_shape_seen
        # mistake in the test suite instead of the pack.
        for name, pack in load_packs(DEFAULT_CURRICULUM).items():
            profile = pack.get("exam_profile")
            if not profile:
                continue
            observed = [
                entry for entry in profile.get("question_shape", []) or []
                if entry["from_exam"]
            ]
            if not observed:
                continue
            with self.subTest(pack=name):
                self.assertNotIn(
                    "No test paper",
                    profile["basis"],
                    f"{name}: question_shape claims from_exam, but the basis says "
                    "no exam paper survives",
                )


if __name__ == "__main__":
    unittest.main()
