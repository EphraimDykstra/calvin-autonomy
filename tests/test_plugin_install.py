"""The Claude Code plugin install path: manifest, plugin-mode setup, and doctor.

These check the files a plugin install depends on. They do not prove a host
loads the plugin; that was observed separately with `claude --plugin-dir` and
is recorded in the PR, not asserted here.
"""

import json
import re
import shlex
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / 'scripts'))
import setup  # noqa: E402

AGENT_NAMES = tuple(sorted(
    p.stem for p in (REPO_ROOT / '.claude' / 'agents').iterdir() if p.suffix == '.md'
))


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.marketplace = json.loads((REPO_ROOT / '.claude-plugin' / 'marketplace.json').read_text())
        self.plugin = json.loads((REPO_ROOT / '.claude-plugin' / 'plugin.json').read_text())

    def test_marketplace_serves_the_repository_root_as_the_schoolwork_plugin(self):
        self.assertTrue(self.marketplace['name'])
        self.assertTrue(self.marketplace['owner']['name'])
        entries = {entry['name']: entry for entry in self.marketplace['plugins']}
        self.assertEqual(entries['schoolwork']['source'], './')
        self.assertEqual(self.plugin['name'], 'schoolwork')
        self.assertTrue((REPO_ROOT / 'skills' / 'schoolwork' / 'SKILL.md').is_file())

    def test_every_shipped_agent_is_declared_and_every_declared_path_exists(self):
        """The plugin default is agents/ at the root, which this repo lacks.

        So each agent must be listed; one left out would silently not load.
        """
        declared = self.plugin['agents']
        for path in declared:
            self.assertTrue(path.startswith('./'), path)
            self.assertNotIn('\\', path, 'backslash paths load on Windows only')
            self.assertTrue((REPO_ROOT / path).is_file(), path)
        self.assertEqual(tuple(sorted(Path(p).stem for p in declared)), AGENT_NAMES)

    def test_skills_are_left_to_the_default_scan(self):
        """Declaring skills on a root-source entry would replace the skills/ scan."""
        self.assertNotIn('skills', self.plugin)
        self.assertNotIn('skills', self.marketplace['plugins'][0])


class PluginSetupTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_plugin_mode_installs_launcher_and_workspace_but_no_skill_copies(self):
        project = self.root / 'student-project'
        workspace = project / 'workspace'
        self.assertEqual(setup.main(['--project-root', str(project), '--workspace', str(workspace), '--plugin']), 0)
        for copied in ('.claude/skills', '.agents/skills', '.claude/agents', '.codex/agents', '.claude/roles'):
            self.assertFalse((project / copied).exists(), f'{copied} would duplicate the plugin copy')
        self.assertIn('mode=plugin', (workspace / '.calvin-autonomy-managed').read_text().splitlines())
        self.assertTrue((project / '.calvin-autonomy' / 'templates' / 'assignment.json').is_file())

        launcher = project / '.calvin-autonomy' / 'bin' / 'coursework'
        # The student's project may hold an unrelated .venv; plugin mode must
        # never prefer it over the plugin's own interpreter.
        self.assertEqual(
            launcher.read_text(),
            f'#!/bin/sh\nexec {shlex.quote(sys.executable)} -m engineering_assistant.cli "$@"\n',
        )
        self.assertNotIn('project_python', (launcher.parent / 'coursework.cmd').read_text())
        result = subprocess.run(
            [str(launcher), '--workspace', str(workspace), 'doctor', '--project-root', str(project)],
            cwd=project, text=True, capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report['install_mode'], 'plugin')
        self.assertTrue(report['ready'], report['blockers'])
        self.assertEqual(set(report['managed_skills']['schoolwork']), {'claude'})

    def test_project_mode_doctor_still_requires_the_project_copies(self):
        project = self.root / 'student-project'
        workspace = project / 'workspace'
        setup.main(['--project-root', str(project), '--workspace', str(workspace), '--plugin'])
        # Same tree, marker says project mode: the missing copies must block.
        marker = workspace / '.calvin-autonomy-managed'
        marker.write_text('\n'.join(l for l in marker.read_text().splitlines() if l != 'mode=plugin') + '\n')
        from engineering_assistant.doctor import diagnose
        report = diagnose(project, workspace)
        self.assertEqual(report['install_mode'], 'project')
        self.assertFalse(report['ready'])

    def test_setup_refuses_a_workspace_inside_the_plugin_cache_or_data_store(self):
        for store in ('cache', 'data'):
            fake_home = self.root / f'home-{store}'
            project = fake_home / '.claude' / 'plugins' / store / 'calvin-autonomy' / 'schoolwork'
            for extra in ([], ['--plugin']):
                code = setup.main(['--project-root', str(project), '--workspace', 'workspace', *extra])
                self.assertEqual(code, 2)
                self.assertFalse(project.exists(), 'a refused setup must create nothing')
            outside = self.root / f'student-{store}'
            code = setup.main(['--project-root', str(outside), '--workspace', str(project / 'workspace')])
            self.assertEqual(code, 2)
            self.assertFalse((project / 'workspace').exists())

    def test_plugin_mode_refuses_a_project_inside_the_plugin_source_tree(self):
        with unittest.mock.patch.object(setup, 'ROOT', self.root / 'plugin-root'):
            code = setup.main(['--project-root', str(self.root / 'plugin-root' / 'sub'), '--plugin'])
        self.assertEqual(code, 2)

    def test_windows_launcher_is_written_with_crlf_and_a_goto_branch(self):
        project = self.root / 'student-project'
        setup.main(['--project-root', str(project), '--workspace', str(project / 'workspace')])
        raw = (project / '.calvin-autonomy' / 'bin' / 'coursework.cmd').read_bytes()
        self.assertIn(b'\r\n', raw)
        self.assertNotIn(b'\n', raw.replace(b'\r\n', b''), 'every line ending must be CRLF')
        text = raw.decode()
        self.assertIn(r'.venv\Scripts\python.exe', text)
        self.assertIn('goto fallback', text)
        self.assertIn('-m engineering_assistant.cli %*', text)

    def test_posix_launcher_also_finds_a_windows_layout_venv(self):
        """Claude Code on Windows runs its shell tool in Git Bash."""
        project = self.root / 'student-project'
        setup.main(['--project-root', str(project), '--workspace', str(project / 'workspace')])
        text = (project / '.calvin-autonomy' / 'bin' / 'coursework').read_text()
        self.assertIn('.venv/bin/python', text)
        self.assertIn('.venv/Scripts/python.exe', text)


class BootstrapParityTests(unittest.TestCase):
    """bootstrap.sh and bootstrap.ps1 must print the same keys in the same order.

    This reads both scripts; it does not run the PowerShell one, which has
    never been executed on Windows.
    """

    KEY = re.compile(r'\\?"([a-z_]+)\\?":')

    def test_final_status_lines_share_keys_and_order(self):
        sh = (REPO_ROOT / 'scripts' / 'bootstrap.sh').read_text()
        ps = (REPO_ROOT / 'scripts' / 'bootstrap.ps1').read_text()
        sh_final = sh[sh.rindex("printf 'CALVIN_BOOTSTRAP"):]
        sh_final = sh_final[:sh_final.index('\n  "$MODE"')]
        ps_final = ps[ps.rindex("Write-Output ('CALVIN_BOOTSTRAP"):]
        ps_final = ps_final[:ps_final.index("']}')") + 5]
        expected = ['mode', 'python', 'venv', 'deps', 'cli', 'pdf_rasterizer', 'tesseract',
                    'ocr_engine', 'ocr_engine_version', 'needs']
        self.assertEqual(self.KEY.findall(sh_final), expected)
        self.assertEqual(self.KEY.findall(ps_final), expected)

    def test_early_exit_lines_share_keys_too(self):
        sh = (REPO_ROOT / 'scripts' / 'bootstrap.sh').read_text()
        ps = (REPO_ROOT / 'scripts' / 'bootstrap.ps1').read_text()
        sh_early = next(l for l in sh.splitlines() if 'CALVIN_BOOTSTRAP' in l and '"python":null' in l)
        ps_early = next(l for l in ps.splitlines() if 'CALVIN_BOOTSTRAP' in l and '"python":null' in l)
        self.assertEqual(self.KEY.findall(sh_early), self.KEY.findall(ps_early))

    def test_powershell_script_is_ascii(self):
        """Windows PowerShell 5.1 reads a BOM-less script as the ANSI code page."""
        (REPO_ROOT / 'scripts' / 'bootstrap.ps1').read_bytes().decode('ascii')


if __name__ == '__main__':
    unittest.main()
