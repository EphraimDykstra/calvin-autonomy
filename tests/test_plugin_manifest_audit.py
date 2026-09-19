"""The schema-aware audit rule for the two Claude Code plugin manifests (issue #41).

Names here are invented and assembled at test time; this file is not
audit-exempt and must not hold a real person's name.
"""

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / 'scripts'))
import check_distribution  # noqa: E402

INVENTED = ' '.join(['Jane', 'Q.', 'Example'])


class PluginManifestAuditTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        (self.root / '.claude-plugin').mkdir()
        self.marketplace = json.loads((REPO_ROOT / '.claude-plugin' / 'marketplace.json').read_text())
        self.plugin = json.loads((REPO_ROOT / '.claude-plugin' / 'plugin.json').read_text())

    def tearDown(self):
        self.tempdir.cleanup()

    def _audit(self, marketplace=None, plugin=None, names=()):
        (self.root / '.claude-plugin' / 'marketplace.json').write_text(json.dumps(marketplace or self.marketplace))
        (self.root / '.claude-plugin' / 'plugin.json').write_text(json.dumps(plugin or self.plugin))
        return check_distribution.audit(self.root, names)

    def test_committed_manifests_pass(self):
        self.assertEqual(self._audit(), [])

    def test_a_person_in_owner_name_fails(self):
        bad = copy.deepcopy(self.marketplace)
        bad['owner']['name'] = INVENTED
        errors = self._audit(marketplace=bad)
        self.assertTrue(any('owner.name is not a project label' in e for e in errors), errors)
        # And again through the forbidden-name scan when the name is configured.
        errors = self._audit(marketplace=bad, names=[INVENTED])
        self.assertTrue(any('forbidden name' in e for e in errors), errors)

    def test_owner_email_is_rejected(self):
        bad = copy.deepcopy(self.marketplace)
        bad['owner']['email'] = 'someone@example.invalid'
        self.assertTrue(any('$.owner.email is not a permitted key' in e for e in self._audit(marketplace=bad)))

    def test_unknown_key_is_rejected(self):
        bad = copy.deepcopy(self.plugin)
        bad['homepage'] = 'https://example.invalid'
        self.assertTrue(any('$.homepage is not a permitted key' in e for e in self._audit(plugin=bad)))

    def test_plugin_name_must_be_a_package_id(self):
        bad = copy.deepcopy(self.marketplace)
        bad['plugins'][0]['name'] = 'School Work'
        self.assertTrue(any('plugins[0].name is not a package id' in e for e in self._audit(marketplace=bad)))

    def test_forbidden_name_in_a_value_fails(self):
        bad = copy.deepcopy(self.plugin)
        bad['description'] = f'Help from {INVENTED}.'
        errors = self._audit(plugin=bad, names=[INVENTED])
        self.assertTrue(any('plugin.json' in e for e in errors), errors)
        self.assertTrue(any('$.description' in e for e in errors), errors)

    def test_personal_path_in_a_value_fails(self):
        bad = copy.deepcopy(self.plugin)
        bad['description'] = 'see ' + '/' + 'Users' + '/someone/notes'
        errors = self._audit(plugin=bad)
        self.assertTrue(any('plugin.json' in e for e in errors), errors)

    def test_sibling_file_keeps_the_generic_check(self):
        (self.root / '.claude-plugin' / 'other.json').write_text(json.dumps({'name': 'schoolwork'}))
        errors = self._audit()
        self.assertIn('identity metadata in .claude-plugin/other.json', errors)


if __name__ == '__main__':
    unittest.main()
