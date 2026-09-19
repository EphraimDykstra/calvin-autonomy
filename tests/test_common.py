import unittest
from pathlib import Path

from engineering_assistant.common import permitted_source


class PermittedSourceTests(unittest.TestCase):
    """A hidden ancestor is allowed; a hidden target is still refused."""

    def test_hidden_ancestor_does_not_refuse_an_ordinary_file(self):
        # The case that motivated the change: a checkout under a hidden
        # directory made every absolute path unusable.
        self.assertTrue(
            permitted_source(Path('/home/user/.claude/worktrees/w/workspace/plan.json'))
        )
        self.assertTrue(permitted_source(Path('/home/user/.config/project/assignment.md')))
        self.assertTrue(permitted_source(Path('.claude/worktrees/w/solution.json')))

    def test_hidden_target_is_still_refused(self):
        """The original intent: a dot-prefixed *filename* stays refused.

        This is the assertion the fix must not quietly open.
        """
        self.assertFalse(permitted_source(Path('.env')))
        self.assertFalse(permitted_source(Path('/home/user/project/.env')))
        self.assertFalse(permitted_source(Path('/home/user/.claude/worktrees/w/.env')))
        self.assertFalse(permitted_source(Path('project/.netrc')))
        # A hidden directory named as the target is still refused.
        self.assertFalse(permitted_source(Path('/home/user/project/.ssh')))

    def test_secret_like_components_are_refused_at_any_depth(self):
        """Every non-dot rule still applies to ancestors, not just the target."""
        for candidate in (
            '/home/user/secrets/assignment.md',
            '/home/user/project/api-token/notes.md',
            '/home/user/credentials/plan.json',
            '/home/user/project/auth.json',
            '/home/user/project/server.pem',
            '/home/user/project/signing.key',
            '/home/user/project/id_rsa',
            '/home/user/project/~$report.docx',
            '/home/user/project/Report alias',
        ):
            with self.subTest(candidate=candidate):
                self.assertFalse(permitted_source(Path(candidate)))

    def test_secret_rules_still_apply_under_a_hidden_ancestor(self):
        """Relaxing the ancestor dot rule must not shelter a secret below it."""
        self.assertFalse(permitted_source(Path('/home/user/.claude/w/id_rsa')))
        self.assertFalse(permitted_source(Path('/home/user/.claude/secrets/plan.json')))

    def test_ordinary_paths_remain_permitted(self):
        self.assertTrue(permitted_source(Path('examples/synthetic/assignment.md')))
        self.assertTrue(permitted_source(Path('/home/user/project/solution.json')))


if __name__ == '__main__':
    unittest.main()
