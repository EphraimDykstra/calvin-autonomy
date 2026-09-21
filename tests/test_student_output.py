"""The student-facing block must not be able to disagree with the JSON.

The text format exists so a student reads a verdict instead of decoding a
result object, and the web page quotes it as the tool's own output.  Both of
those claims fail the moment the text can say something the JSON does not, so
the tests here are about agreement rather than about wording:

* every number printed is parsed back and compared with the value it came
  from, so a rounding that changed an answer fails rather than reading nicely;
* the verdict word is derived from ``correct`` and checked against it;
* a hedge stays a hedge: the printed word is "likely cause", never "cause".

The width test keeps the block inside a split pane, and the shape tests pin
the cases the engine really produces, including the two that a formatter
written from a summary of the engine would get wrong: a dimension mismatch
carries no recomputed value, and a correct answer can still be an implausible
magnitude.
"""

from __future__ import annotations

import json
import re
import unittest

from engineering_assistant.review import review_work
from engineering_assistant.student_output import WRAP, _label_for, format_review

FILM_TEMP = {
    "id": "film-temp",
    "method": "(T_s + T_inf) / 2",
    "inputs": {"T_s": {"value": 120, "unit": "degC"}, "T_inf": {"value": 20, "unit": "degC"}},
    "student_answer": {"value": 70, "unit": "K"},
}
STRAIN = {
    "id": "strain",
    "method": "dL / L",
    "inputs": {"dL": {"value": 0.6, "unit": "mm"}, "L": {"value": 250, "unit": "mm"}},
    "student_answer": {"value": 0.24, "unit": "1"},
}
CORRECT = {
    "id": "ok-step",
    "method": "(a + b) / 2",
    "inputs": {"a": {"value": 10, "unit": "m"}, "b": {"value": 20, "unit": "m"}},
    "student_answer": {"value": 15, "unit": "m"},
}
NO_CAUSE = {
    "id": "no-cause",
    "method": "a * b",
    "inputs": {"a": {"value": 3, "unit": "m"}, "b": {"value": 4, "unit": "m"}},
    "student_answer": {"value": 17, "unit": "m^2"},
}
DIMENSION = {
    "id": "dim-mismatch",
    "method": "dL / L",
    "inputs": {"dL": {"value": 0.6, "unit": "mm"}, "L": {"value": 250, "unit": "mm"}},
    "student_answer": {"value": 0.0024, "unit": "m"},
}
BROKEN = {
    "id": "broken",
    "method": "a / b",
    "inputs": {"a": {"value": 1, "unit": "m"}, "b": {"value": 0, "unit": "s"}},
    "student_answer": {"value": 5, "unit": "m/s"},
}
UNNAMED = {
    "method": "a + b",
    "inputs": {"a": {"value": 1, "unit": "m"}, "b": {"value": 1, "unit": "m"}},
    "student_answer": {"value": 9, "unit": "m"},
}
DENSITY = {
    "id": "density",
    "method": "m / V",
    "inputs": {"m": {"value": 1200, "unit": "kg"}, "V": {"value": 1, "unit": "m^3"}},
    "student_answer": {"value": 1200, "unit": "kg/m^3"},
    "magnitude": "air density",
}
MAGNITUDES = [
    {
        "quantity": "air density",
        "unit": "kg/m^3",
        "typical_range": [1.0, 1.3],
        "note": "Near 1000 usually means the density of water was used.",
    }
]

ALL_SHAPES = [CORRECT, DIMENSION, NO_CAUSE, DENSITY, BROKEN, UNNAMED]

# A quantity value is "<number>[ <unit>]" or "<number> to <number>[ <unit>]".
# The unit itself can contain a digit ("kg/m^3"), so only the numeric slots are
# read: the start of the value, and whatever follows " to ".
_VALUE_NUMBER = re.compile(r"(?:^|(?<= to ))(-?\d+\.?\d*(?:[eE][-+]?\d+)?)")

# The lines that carry a quantity, as opposed to prose or a cause name.  A unit
# can contain a digit ("m^3"), so the number tokens are taken from the value
# and matched against the result object rather than against the whole line.
_QUANTITY_LINE = re.compile(r"^  (you wrote|recomputed|usual range) +(.+)$", re.MULTILINE)


def _numbers_in(result: dict) -> set[float]:
    """Every numeric value anywhere in the result object."""
    found: set[float] = set()

    def walk(node):
        if isinstance(node, bool):
            return
        if isinstance(node, (int, float)):
            found.add(float(node))
        elif isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(result)
    return found


class DerivationTests(unittest.TestCase):
    """The text cannot say a number or a verdict the JSON does not."""

    def test_every_quantity_the_block_prints_round_trips_to_a_value_in_the_json(self):
        # The strong form of "nothing is rounded into a different answer".
        # Every number on a quantity line is parsed back and must equal a value
        # actually present in the result object, exactly -- not merely look
        # close to one.  Prose is checked separately, by the verbatim test
        # below: digits inside a hint or a pack note are part of a string the
        # engine wrote, not a quantity this formatter chose how to print.
        result = review_work(ALL_SHAPES, MAGNITUDES)
        values = _numbers_in(result)
        quantities = _QUANTITY_LINE.findall(format_review(result))
        self.assertTrue(quantities, "the block printed no quantity lines at all")
        for label, printed in quantities:
            tokens = _VALUE_NUMBER.findall(printed)
            self.assertTrue(tokens, f"the {label!r} line printed no number: {printed!r}")
            for token in tokens:
                with self.subTest(label=label, token=token):
                    self.assertIn(
                        float(json.loads(token)),
                        values,
                        f"{token!r} is printed on the {label!r} line but no such value "
                        "is in the result object",
                    )

    def test_the_engines_prose_is_reproduced_word_for_word(self):
        # A hedge survives only if the hint is not rewritten.  Wrapping may
        # move a line break and nothing else, so the block with its whitespace
        # normalised must contain each hint and note exactly as the JSON holds
        # it.  This is what stops the text and the JSON explaining a slip
        # differently.
        # The fixture set deliberately includes the hedged, hint-rich cases
        # (film temperature and strain) and not only ALL_SHAPES: a paraphrase
        # test whose fixtures carry no hedging words would pass while the
        # formatter quietly rewrote "probably" or "likely" out of a hint.
        result = review_work(ALL_SHAPES + [FILM_TEMP, STRAIN], MAGNITUDES)
        flat = " ".join(format_review(result).split())
        strings = []
        for step in result["steps"]:
            strings.extend(cause["hint"] for cause in step.get("likely_causes", []) or [])
            if isinstance(step.get("magnitude"), dict) and step["magnitude"].get("note"):
                strings.append(step["magnitude"]["note"])
        self.assertTrue(strings, "no engine prose was exercised")
        self.assertTrue(
            any("probably" in text or "likely" in text for text in strings),
            "the fixtures carry no hedged prose, so this test would not notice one being dropped",
        )
        for text in strings:
            with self.subTest(prose=text[:40]):
                self.assertIn(" ".join(text.split()), flat)

    def test_the_recomputed_value_is_printed_at_full_precision(self):
        result = review_work([FILM_TEMP])
        actual = result["steps"][0]["actual"]
        text = format_review(result)
        printed = re.search(r"recomputed\s+(\S+)", text).group(1)
        self.assertEqual(json.loads(printed), actual)
        self.assertEqual(float(printed), 343.15)

    def test_the_verdict_word_follows_the_correct_field(self):
        for step, word in ((CORRECT, "OK"), (FILM_TEMP, "NOT RIGHT")):
            result = review_work([step])
            with self.subTest(step=step["id"]):
                self.assertIs(result["steps"][0]["correct"], word == "OK")
                self.assertIn(word, format_review(result))

    def test_a_likely_cause_is_never_printed_as_a_verdict(self):
        # The engine's field is `likely_causes` and the skill is explicit that
        # these are not findings.  A block that printed "cause:" would state a
        # guess as a fact, which is the one thing this format must not do.
        text = format_review(review_work([FILM_TEMP]))
        self.assertIn("likely cause", text)
        # \b matters: without it this matches the "cause" inside "because",
        # so the first hint written with that word would fail the test for the
        # wrong reason and read as the hedge having broken.
        self.assertNotRegex(text, r"(?<!likely )\bcause\b")


class ShapeTests(unittest.TestCase):
    def test_the_film_temperature_block(self):
        self.assertEqual(
            format_review(review_work([FILM_TEMP])),
            "film-temp   NOT RIGHT\n"
            "  you wrote     70 K\n"
            "  recomputed    343.15 K\n"
            "  likely cause  temperature scale\n"
            "  The answer is off by 273.15. A Celsius value was used\n"
            "  as kelvin, or the reverse.",
        )

    def test_the_strain_block_prints_no_unit_for_a_plain_number(self):
        # A dimensionless answer is spelled "1" by the unit parser.  Printing
        # that after the number would read as a unit, so it is dropped -- named
        # and tested here rather than left as a silent exemption.
        text = format_review(review_work([STRAIN]))
        self.assertEqual(
            text,
            "strain   NOT RIGHT\n"
            "  you wrote     0.24\n"
            "  recomputed    0.0024\n"
            "  likely cause  percent\n"
            "  The answer is off by a factor of 100. A percentage was\n"
            "  probably used as a fraction, or a fraction as a\n"
            "  percentage.",
        )
        self.assertNotIn("0.24 1", text)

    def test_a_correct_step_gets_one_line_and_no_padding(self):
        self.assertEqual(format_review(review_work([CORRECT])), "ok-step   OK   15 m")

    def test_a_wrong_step_with_no_named_cause_says_so(self):
        text = format_review(review_work([NO_CAUSE]))
        self.assertEqual(review_work([NO_CAUSE])["steps"][0]["likely_causes"], [])
        self.assertIn("No known slip shape matches this one.", text)
        self.assertNotIn("likely cause", text)

    def test_a_dimension_mismatch_prints_no_recomputed_value(self):
        # The engine returns before recomputing, so there is no value to show.
        # A formatter that assumed one would print None.
        step = review_work([DIMENSION])["steps"][0]
        self.assertNotIn("actual", step)
        text = format_review(review_work([DIMENSION]))
        self.assertNotIn("recomputed", text)
        self.assertNotIn("None", text)
        self.assertIn("likely cause  dimension", text)

    def test_the_dimension_hint_reads_as_a_sentence(self):
        # Pins the wording this worker replaced: the old string restated the
        # unit and then named its dimension in SI base symbols, "in m (m) ...
        # dimension dimensionless", which is not a sentence a student can use.
        hint = review_work([DIMENSION])["steps"][0]["likely_causes"][0]["hint"]
        self.assertEqual(
            hint, "The answer is written in m, but this quantity is a plain number with no unit."
        )

    def test_a_correct_answer_can_still_be_an_implausible_magnitude(self):
        # `magnitude` is computed outside the wrong-answer branch, so this is
        # reachable, and the one-line rule for a correct step must not hide it.
        step = review_work([DENSITY], MAGNITUDES)["steps"][0]
        self.assertTrue(step["correct"])
        self.assertFalse(step["magnitude"]["plausible"])
        text = format_review(review_work([DENSITY], MAGNITUDES))
        self.assertIn("SIZE LOOKS WRONG", text)
        self.assertIn("usual range", text)
        self.assertIn("The arithmetic is right", text)

    def test_a_step_that_could_not_be_checked_says_that_and_not_a_verdict(self):
        text = format_review(review_work([BROKEN]))
        self.assertIn("COULD NOT CHECK", text)
        self.assertNotIn("NOT RIGHT", text)

    def test_a_step_without_an_id_is_named_by_position(self):
        self.assertIn("step 2", format_review(review_work([CORRECT, UNNAMED])))


class SummaryTests(unittest.TestCase):
    def test_the_summary_comes_first_and_only_wrong_steps_get_blocks(self):
        text = format_review(review_work(ALL_SHAPES, MAGNITUDES))
        self.assertTrue(text.startswith("6 steps: 2 right, 3 wrong, 1 could not be checked."))
        # The correct, plausible step is named in no block of its own.
        self.assertNotIn("ok-step   OK", text)
        self.assertIn("Needs attention:", text)

    def test_the_attention_list_is_the_one_the_result_object_names(self):
        # The block builds this list with the same predicate `review_work`
        # used, which is the last place the text could drift from the JSON: if
        # the engine's rule for needing attention changed, nothing else in this
        # suite would notice the block still printing the old one.
        # A long id is in the fixtures on purpose: names are clipped for the
        # width, so `expected` is derived through `_label_for` rather than from
        # the raw id.  The claim under test is that the printed list maps one
        # to one onto `needs_attention`, not that the clip is any particular
        # width -- deriving it the other way would make this test restate the
        # formatter instead of checking it against the engine.
        steps = ALL_SHAPES + [dict(FILM_TEMP, id="a-step-id-far-too-long-to-print-beside-a-verdict-word")]
        result = review_work(steps, MAGNITUDES)
        text = format_review(result)
        printed = re.search(r"Needs attention: (.+?)(?:\n\n|\Z)", text, re.S).group(1)
        printed_names = [name.strip() for name in " ".join(printed.split()).split(",")]
        # `needs_attention` holds ids in step order, so an unnamed step is
        # recovered by its position among all the steps, not among these.
        expected = [
            _label_for(step, index)
            for index, step in enumerate(result["steps"], start=1)
            if step.get("id") in result["needs_attention"]
            or (step.get("id") is None and None in result["needs_attention"])
        ]
        self.assertEqual(printed_names, expected)
        self.assertEqual(len(printed_names), len(result["needs_attention"]))

    def test_the_counts_come_from_the_result_object(self):
        result = review_work(ALL_SHAPES, MAGNITUDES)
        text = format_review(result)
        self.assertEqual(result["checked"], 5)
        self.assertEqual(result["correct"], 2)
        self.assertIn(f"{len(result['steps'])} steps:", text)
        self.assertIn(f"{result['correct']} right", text)

    def test_a_run_where_every_step_errored_never_reads_like_a_pass(self):
        # "0 right, 0 wrong" would read as nothing being wrong, so zero counts
        # are not named at all.
        result = review_work([BROKEN, dict(BROKEN, id="broken-2")])
        text = format_review(result)
        self.assertEqual(result["checked"], 0)
        self.assertNotIn("0 right", text)
        self.assertNotIn("0 wrong", text)
        self.assertTrue(text.startswith("2 steps: 2 could not be checked."))

    def test_a_single_step_gets_no_summary_line(self):
        self.assertTrue(format_review(review_work([FILM_TEMP])).startswith("film-temp"))


class CoursePackNoteTests(unittest.TestCase):
    """An id that matched no installed pack is said, not passed over."""

    NOTE = {
        "requested": "engr315",
        "installed": False,
        "magnitude_ranges": "unavailable",
        "did_you_mean": ["engr315-lab"],
    }

    def _rendered(self, note):
        return format_review(review_work([FILM_TEMP], None, course_pack=note))

    def _flat(self, note):
        """Whitespace-normalised: the note wraps, and where it wraps is not the claim."""
        return " ".join(self._rendered(note).split())

    def test_the_note_is_said_first_because_it_qualifies_every_verdict(self):
        self.assertTrue(self._rendered(self.NOTE).startswith('No course pack is installed as "engr315"'))
        self.assertIn("so no magnitude ranges were available to check against", self._flat(self.NOTE))

    def test_a_near_match_is_named(self):
        self.assertIn("Did you mean engr315-lab?", self._flat(self.NOTE))

    def test_no_near_match_claims_none(self):
        text = self._flat(dict(self.NOTE, requested="engr999", did_you_mean=[]))
        self.assertNotIn("Did you mean", text)
        self.assertIn('installed as "engr999"', text)

    def test_several_near_matches_are_all_named(self):
        text = self._flat(dict(self.NOTE, did_you_mean=["engr204", "engr204-lab"]))
        self.assertIn("Did you mean engr204 or engr204-lab?", text)

    def test_nothing_is_printed_when_the_pack_was_found(self):
        # The field is absent in the ordinary result, so the block is unchanged.
        self.assertNotIn("course pack", format_review(review_work([FILM_TEMP])))

    def test_the_note_does_not_disturb_the_verdict_block(self):
        # The published block must survive the note being added above it.
        plain = format_review(review_work([FILM_TEMP]))
        self.assertTrue(self._rendered(self.NOTE).endswith(plain))

    def test_the_note_stays_inside_the_width(self):
        for note in (self.NOTE, dict(self.NOTE, did_you_mean=["engr204", "engr204-lab"])):
            for line in self._rendered(note).splitlines():
                with self.subTest(line=line):
                    self.assertLessEqual(len(line), WRAP)


class UnboundedInputTests(unittest.TestCase):
    """The format promises 56 columns for inputs it did not choose.

    A step id and a unit are both written by whoever built the steps file, so
    neither may push a line past the width the whole design rests on.
    """

    LONG_ID = "film-temperature-at-the-plate-surface-for-part-b-of-question-four"
    LONG_UNIT = "kg-m^2/s^3-K-mol-per-really-long-made-up-compound-unit"

    def _long_id_step(self):
        return dict(FILM_TEMP, id=self.LONG_ID)

    def test_a_long_step_id_does_not_overflow_the_verdict_line(self):
        for steps in ([self._long_id_step()], [self._long_id_step(), CORRECT, BROKEN]):
            text = format_review(review_work(steps))
            for line in text.splitlines():
                with self.subTest(line=line):
                    self.assertLessEqual(len(line), WRAP)

    def test_a_clipped_id_is_marked_as_clipped(self):
        text = format_review(review_work([self._long_id_step()]))
        self.assertNotIn(self.LONG_ID, text)
        self.assertIn("...", text)
        self.assertIn("NOT RIGHT", text)

    def test_the_block_and_the_attention_list_spell_a_long_id_the_same_way(self):
        # Clipping happens in one place precisely so these cannot diverge.
        result = review_work([self._long_id_step(), CORRECT])
        text = format_review(result)
        printed = _label_for(result["steps"][0], 1)
        self.assertEqual(text.count(printed), 2, text)

    # The unit registry refuses a symbol it does not know, so a unit this long
    # cannot be produced through `review_work` today.  The formatter is still
    # held to the width for one, because its promise is about its own input and
    # not about which inputs another module currently allows: the registry
    # gains symbols as courses are added, and a pack's magnitude unit is never
    # checked against it at all.  Hence a result object built directly here.
    def _synthetic(self, **over):
        step = {"id": "u", "correct": False, "claimed": 0.24, "unit": self.LONG_UNIT,
                "actual": 0.0024, "likely_causes": [], **over}
        return {"schema_version": 1, "steps": [step], "checked": 1,
                "correct": 1 if step.get("correct") else 0, "needs_attention": ["u"]}

    def test_a_long_unit_wraps_instead_of_overflowing(self):
        for line in format_review(self._synthetic()).splitlines():
            with self.subTest(line=line):
                self.assertLessEqual(len(line), WRAP)

    def test_a_wrapped_value_keeps_its_number_on_the_first_line(self):
        # The wrap may move the unit onto a continuation line; it may never
        # split the number, which is what the derivation test reads back.
        text = format_review(self._synthetic())
        first = next(line for line in text.splitlines() if "you wrote" in line)
        self.assertIn("0.24", first)

    def test_a_correct_step_with_a_long_unit_falls_back_to_the_labelled_form(self):
        text = format_review(self._synthetic(correct=True, claimed=15))
        self.assertTrue(text.startswith("u   OK"))
        self.assertIn("you wrote", text)
        for line in text.splitlines():
            self.assertLessEqual(len(line), WRAP)

    def test_the_short_cases_are_untouched_by_the_guard(self):
        # The guard must be invisible for ordinary input, or it would have
        # silently changed the blocks the web page quotes.
        self.assertEqual(format_review(review_work([CORRECT])), "ok-step   OK   15 m")


class WidthTests(unittest.TestCase):
    def test_no_line_is_wider_than_the_wrap(self):
        # It renders in a split pane and on a phone, so the block is narrow.
        for label, steps, magnitudes in (
            ("all shapes", ALL_SHAPES, MAGNITUDES),
            ("film-temp", [FILM_TEMP], None),
            ("strain", [STRAIN], None),
            ("density", [DENSITY], MAGNITUDES),
        ):
            for line in format_review(review_work(steps, magnitudes)).splitlines():
                with self.subTest(case=label, line=line):
                    self.assertLessEqual(len(line), WRAP)

    def test_the_block_is_plain_ascii_with_no_colour_or_box_drawing(self):
        text = format_review(review_work(ALL_SHAPES, MAGNITUDES))
        self.assertTrue(text.isascii(), "the block must survive a proportional fallback font")
        self.assertNotIn("\x1b", text, "no ANSI escapes: the host renders this as markdown")


if __name__ == "__main__":
    unittest.main()
