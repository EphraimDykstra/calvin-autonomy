"""Issue #20: the gate's forbidden-name scan must be reachable, and honest.

``audit()`` could scan for names, but ``main()`` never passed any, so the gate
every contributor and CI runs caught no human name while still printing
``distribution audit passed``.
"""
import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import check_distribution

ENV = "CALVIN_FORBIDDEN_NAMES"


def _run(root, env_value=None):
    environ = {k: v for k, v in os.environ.items() if k != ENV}
    if env_value is not None:
        environ[ENV] = env_value
    out, err = io.StringIO(), io.StringIO()
    with patch.dict(os.environ, environ, clear=True), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = check_distribution.main([str(root)])
    return code, out.getvalue(), err.getvalue()


class ForbiddenNameGateTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "notes.txt").write_text("Prepared by Wren Quillfeather.\n", encoding="utf-8")

    def tearDown(self):
        self._tmp.cleanup()

    def test_gate_fails_on_a_configured_name_in_the_tree(self):
        code, _, err = _run(self.root, "Wren Quillfeather")
        self.assertEqual(code, 1)
        self.assertIn("forbidden name in notes.txt", err)

    def test_names_separate_on_semicolons_and_newlines_not_commas(self):
        self.assertEqual(_run(self.root, "Ossian Brack;\nWren Quillfeather")[0], 1)
        # A comma is part of a name ("Quillfeather, Wren"), not a separator.
        self.assertEqual(_run(self.root, "Quillfeather, Wren")[0], 0)

    def test_failure_output_never_echoes_the_name(self):
        _, out, err = _run(self.root, "Wren Quillfeather")
        self.assertNotIn("Quillfeather", out + err)

    def test_pass_with_names_says_the_scan_ran(self):
        code, out, _ = _run(self.root, "Ossian Brack;Tamsin Vell")
        self.assertEqual(code, 0)
        self.assertIn("distribution audit passed", out)
        self.assertIn("forbidden-name scan: 2 names, clean", out)
        self.assertNotIn("Ossian", out)

    def test_pass_without_names_says_the_scan_did_not_run(self):
        code, out, _ = _run(self.root)
        self.assertEqual(code, 0)
        self.assertIn("distribution audit passed", out)
        self.assertIn(f"forbidden-name scan: not run, {ENV} is not set", out)

    def test_blank_setting_counts_as_not_set(self):
        self.assertIn("not run", _run(self.root, " ; \n")[1])

    def test_a_name_too_short_to_scan_safely_is_refused(self):
        code, out, err = _run(self.root, "Wren Quillfeather;Qx")
        self.assertEqual(code, 2)
        self.assertIn("cannot identify anyone", err)
        self.assertNotIn("Qx", out + err)
        self.assertNotIn("audit passed", out)


if __name__ == "__main__":
    unittest.main()


class RepositorySlugTests(unittest.TestCase):
    """The install command necessarily contains the owner's GitHub handle.

    Exercised with invented names: this file is not audit-exempt, so spelling
    the real handle here would fail the scan these tests are about.
    """

    SLUG = "RoeJ/example-project"
    NAMES = "Jane Roe;Roe;RoeJ"

    def _strip(self, text):
        return check_distribution._without_permitted(text, (self.SLUG,))

    def _flagged(self, text):
        scannable = self._strip(text).casefold()
        return any(n.casefold() in scannable for n in self.NAMES.split(";"))

    def test_the_install_command_is_permitted(self):
        # Dropping bare surnames from the name list would lose the protection
        # that matters; exempting whole files loses more.  One exact public
        # string is the narrowest answer.
        self.assertFalse(self._flagged(f"Run `/plugin marketplace add {self.SLUG}` to install."))

    def test_a_real_name_in_the_same_file_still_fails(self):
        self.assertTrue(self._flagged(
            f"Run `/plugin marketplace add {self.SLUG}` to install.\nWritten by Jane Roe.\n"
        ))

    def test_the_allowance_does_not_cover_the_handle_alone(self):
        # Only the full slug is public project metadata.  A bare handle in
        # prose is the owner's identity like any other.
        self.assertTrue(self._flagged("Contact RoeJ with questions."))

    def test_the_shipped_allowance_is_a_repository_slug(self):
        # Checks the real constant's shape without spelling its value.
        self.assertTrue(check_distribution.PERMITTED_NAME_STRINGS)
        for entry in check_distribution.PERMITTED_NAME_STRINGS:
            self.assertRegex(entry, r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")
