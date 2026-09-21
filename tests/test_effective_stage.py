"""`effective_stage` is a verdict, and may never read as a pass.

It used to fall through to the raw pipeline stage whenever a run was neither
ready nor provisional, so a blocked run described itself with whatever word the
pipeline had last written: `checked`, `verified`, `rendered`, `inspected`.  All
four read as success, in the field whose name most invites trusting it, and any
host reading the JSON saw them.  That is a false-ready shape, which this project
treats as a release blocker rather than a wording problem.

So the field is now a closed set of four verdicts, and the raw stage lives in
`pipeline_stage` under a name that promises nothing.  The tests here hold both
halves: that the vocabulary cannot grow, and that a run walked through every
pass-reading stage never once reports one.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from engineering_assistant.runtime import (
    EFFECTIVE_STAGES,
    load_run,
    save_run,
    start_run,
    status_run,
)

# Every word `state['stage']` can hold, from the assignments in runtime.py.
ALL_PIPELINE_STAGES = (
    "received",
    "grounded",
    "solved",
    "checked",
    "verified",
    "rendered",
    "rejected",
    "inspected",
    "ready",
)

# The ones that read as success to someone skimming.  These are the reason the
# field is closed: each was reachable as an `effective_stage` on a run that
# could not be handed in.
PASS_READING = ("checked", "verified", "rendered", "inspected", "ready")


class EffectiveStageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.workspace = Path(self.tmp.name) / "ws"
        source = Path(self.tmp.name) / "assignment.txt"
        source.write_text("Q1. Answer the question.\n")
        start_run(self.workspace, "r", "engr209", source)

    def _at_stage(self, stage: str) -> dict:
        """Put the run at one pipeline stage and ask for its status.

        The state is written directly on purpose: driving the whole pipeline
        would make the run ready at the end, and what is under test is what a
        run says about itself when it is *not*.
        """
        state = load_run(self.workspace, "r")
        state["stage"] = stage
        save_run(self.workspace, state)
        return status_run(self.workspace, "r")

    def test_no_pipeline_stage_ever_reaches_the_verdict(self):
        # The regression test for the defect itself.  This run is blocked at
        # every one of these stages: nothing was solved, rendered or inspected,
        # whatever the stage field says.
        for stage in ALL_PIPELINE_STAGES:
            with self.subTest(stage=stage):
                status = self._at_stage(stage)
                self.assertFalse(status["readiness"]["ready"])
                self.assertIn(status["effective_stage"], EFFECTIVE_STAGES)
                if stage in PASS_READING:
                    self.assertNotEqual(
                        status["effective_stage"],
                        stage,
                        f"a blocked run reported {stage!r}, which reads as a pass",
                    )

    def test_a_blocked_run_says_blocked_whatever_stage_it_sits_at(self):
        for stage in ALL_PIPELINE_STAGES:
            if stage == "ready":
                continue  # that one is 'stale', asserted below
            with self.subTest(stage=stage):
                self.assertEqual(self._at_stage(stage)["effective_stage"], "blocked")

    def test_a_run_that_was_certified_and_changed_is_stale_not_blocked(self):
        # `evaluation.py` detects this exact word, and it makes a different
        # claim from 'blocked': this one was certified, then moved under us.
        self.assertEqual(self._at_stage("ready")["effective_stage"], "stale")

    def test_the_raw_stage_is_still_available_under_an_honest_name(self):
        # Nothing is hidden by the change; it is relabelled.
        for stage in ALL_PIPELINE_STAGES:
            with self.subTest(stage=stage):
                self.assertEqual(self._at_stage(stage)["pipeline_stage"], stage)

    def test_the_vocabulary_is_closed(self):
        # The defect got in because the field was open to whatever stage word
        # existed. If a stage is added later, this is what should fail first.
        self.assertEqual(EFFECTIVE_STAGES, ("ready", "provisional", "stale", "blocked"))
        for word in EFFECTIVE_STAGES:
            with self.subTest(word=word):
                self.assertNotIn(
                    word,
                    set(ALL_PIPELINE_STAGES) - {"ready"},
                    "a verdict word collides with a pipeline stage, which is how the two got confused",
                )


if __name__ == "__main__":
    unittest.main()
