"""Observations record slips caught in the student's own work: events, never traits.

The next session is smarter for knowing a percentage slipped into a modulus
calculation last week.  It would be worse, and the file the student can read
would be hurtful, if that were written down as "weak at units".  Every refusal
below is what keeps the first from turning into the second.
"""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from engineering_assistant.cli import main
from engineering_assistant.memory import (
    MAX_OBSERVATIONS,
    forget_observations,
    list_memory,
    list_observations,
    record_observation,
    set_memory,
)


class ObservationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self._tmp.name) / "ws"
        self.addCleanup(self._tmp.cleanup)

    def test_a_slip_is_recorded_against_the_work(self):
        entry = record_observation(self.ws, "engr205", "relaxation modulus, polymer lab", "percent")
        self.assertEqual(entry["authority"], "observation")
        self.assertEqual(entry["cause"], "percent")
        # Nothing the student wrote is kept: no values, no working.
        self.assertEqual(set(entry), {"course", "topic", "cause", "recorded_at", "authority"})

    def test_a_cause_outside_the_vocabulary_is_refused(self):
        # The vocabulary is the classifier's own, so it cannot be widened into
        # an assessment of the student.
        with self.assertRaises(ValueError):
            record_observation(self.ws, "engr205", "modulus", "doesn't understand units")

    def test_a_topic_that_judges_the_student_is_refused(self):
        for topic in ("weak at unit conversions", "careless with signs", "always forgets the minus", "struggles with ratios"):
            with self.subTest(topic=topic):
                with self.assertRaises(ValueError):
                    record_observation(self.ws, "engr205", topic, "sign")

    def test_recent_first_and_filtered_by_course(self):
        record_observation(self.ws, "engr205", "first", "sign")
        record_observation(self.ws, "engr322", "other course", "percent")
        record_observation(self.ws, "engr205", "second", "inverted")
        topics = [o["topic"] for o in list_observations(self.ws, "engr205")["observations"]]
        self.assertEqual(topics, ["second", "first"])

    def test_the_listing_carries_no_summary(self):
        # Counting causes into "this student tends to" is the aggregation into
        # a trait this store exists to refuse, so none is offered.
        record_observation(self.ws, "engr205", "a", "sign")
        record_observation(self.ws, "engr205", "b", "sign")
        self.assertEqual(set(list_observations(self.ws)), {"schema_version", "observations"})

    def test_the_store_is_bounded(self):
        for i in range(MAX_OBSERVATIONS + 5):
            record_observation(self.ws, "engr205", f"step {i}", "decimal")
        items = list_observations(self.ws, limit=1000)["observations"]
        self.assertEqual(len(items), MAX_OBSERVATIONS)
        self.assertEqual(items[0]["topic"], f"step {MAX_OBSERVATIONS + 4}")

    def test_the_student_can_forget_one_course_or_everything(self):
        record_observation(self.ws, "engr205", "a", "sign")
        record_observation(self.ws, "engr322", "b", "sign")
        self.assertEqual(forget_observations(self.ws, "engr205")["forgotten"], 1)
        self.assertEqual(len(list_observations(self.ws)["observations"]), 1)
        self.assertEqual(forget_observations(self.ws)["forgotten"], 1)
        self.assertEqual(list_observations(self.ws)["observations"], [])

    def test_preferences_are_untouched(self):
        set_memory(self.ws, "units", "SI", scope="all", source="student")
        record_observation(self.ws, "engr205", "a", "sign")
        entry = list_memory(self.ws)["entries"]["units"]
        self.assertEqual(entry["authority"], "preference_only")


class ObservationCommandTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ws = Path(self._tmp.name) / "ws"
        self.addCleanup(self._tmp.cleanup)

    def _cli(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            try:
                code = main(["--workspace", str(self.ws), "memory", *args])
            except SystemExit as exc:
                code = exc.code
        return code, out.getvalue()

    def test_record_then_list(self):
        code, _ = self._cli("observe", "--course", "engr205", "--topic", "strain units, lab 3", "--cause", "percent")
        self.assertEqual(code, 0)
        code, out = self._cli("observations", "--course", "engr205")
        self.assertEqual(json.loads(out)["observations"][0]["cause"], "percent")

    def test_a_judgement_is_refused_at_the_command_line_too(self):
        code, _ = self._cli("observe", "--course", "engr205", "--topic", "weak at units", "--cause", "percent")
        self.assertNotEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
