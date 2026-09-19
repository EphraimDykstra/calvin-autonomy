import json
import tempfile
import unittest
import subprocess
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import setup
import check_distribution

REPO_ROOT = Path(__file__).resolve().parents[1]
# Derived from the source tree, never hand-typed: adding a skill or agent must
# fail a test rather than quietly go uninstalled and unchecked.
SKILL_NAMES = tuple(sorted(p.name for p in (REPO_ROOT / 'skills').iterdir() if p.is_dir()))
AGENT_NAMES = tuple(sorted(
    p.stem for p in (REPO_ROOT / '.claude' / 'agents').iterdir() if p.suffix == '.md'
))


def _frontmatter_name(path):
    """Return the ``name:`` field of a Markdown frontmatter block."""
    lines = path.read_text(encoding='utf-8').splitlines()
    if not lines or lines[0].strip() != '---':
        return None
    for line in lines[1:]:
        if line.strip() == '---':
            break
        if line.startswith('name:'):
            return line.split(':', 1)[1].strip()
    return None


class SetupTests(unittest.TestCase):
    def test_idempotent_and_preserves_local_edit(self):
        with tempfile.TemporaryDirectory() as t:
            project=Path(t)/'student-project'; w=project/'workspace'
            args=['--project-root',str(project),'--workspace',str(w)]
            setup.main(args); setup.main(args)
            target=project/'.agents/skills/complete-assignment/SKILL.md'
            self.assertTrue(target.exists()); target.write_text('local edit')
            setup.main(args); self.assertEqual(target.read_text(),'local edit')
            setup.main(args+['--force']); self.assertNotEqual(target.read_text(),'local edit')
            user=project/'.agents/skills/user-note.md'; user.write_text('keep')
            setup.main(args+['--force']); self.assertEqual(user.read_text(),'keep')
            self.assertFalse((w/'.agents').exists())
            self.assertTrue((project/'.claude/skills/complete-assignment/SKILL.md').exists())
            self.assertTrue((project/'.codex/agents/assignment-coordinator.toml').exists())
            self.assertTrue((project/'.codex/agents/course-profile-curator.toml').exists())
            self.assertTrue((project/'.claude/skills/build-course-profile/SKILL.md').exists())
            self.assertTrue((project/'.calvin-autonomy/templates/inspection.json').exists())
            self.assertTrue((project/'.calvin-autonomy/templates/evaluation-manifest.json').exists())
            self.assertTrue((project/'.calvin-autonomy/templates/assignment.json').exists())
            launcher=project/'.calvin-autonomy/bin/coursework'
            self.assertTrue(launcher.exists())
            launcher_text=launcher.read_text()
            self.assertIn('project_root=',launcher_text)
            self.assertIn('.venv/bin/python',launcher_text)
            result=subprocess.run([str(launcher),'--help'],cwd=project,text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('coursework',result.stdout)
            result=subprocess.run(
                [str(launcher),'--workspace',str(w),'doctor','--project-root',str(project)],
                cwd=project,text=True,capture_output=True,
            )
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertTrue(json.loads(result.stdout)['ready'])
    def test_doctor_checks_every_skill_and_agent_the_repository_ships(self):
        """doctor's expected set must not drift from the source tree."""
        from engineering_assistant.doctor import MANAGED_AGENTS, MANAGED_SKILLS
        self.assertEqual(tuple(sorted(MANAGED_SKILLS)), SKILL_NAMES)
        self.assertEqual(tuple(sorted(MANAGED_AGENTS)), AGENT_NAMES)

    def test_installed_skills_and_agents_are_structurally_discoverable(self):
        """Assert the file-level preconditions a host needs to discover these.

        This checks that installation puts real, non-symlinked files at the
        exact paths Claude Code and Codex scan, each carrying frontmatter whose
        declared name matches its location.  It does NOT prove that a host
        process running in a separate project tree actually lists them; that
        requires observing a second session and is not verifiable from here.
        """
        with tempfile.TemporaryDirectory() as t:
            project = Path(t) / 'student-project'
            workspace = project / 'workspace'
            setup.main(['--project-root', str(project), '--workspace', str(workspace)])
            for skills_root in (project / '.claude' / 'skills', project / '.agents' / 'skills'):
                for name in SKILL_NAMES:
                    path = skills_root / name / 'SKILL.md'
                    self.assertTrue(path.is_file(), f'missing skill file: {path}')
                    self.assertFalse(path.is_symlink(), f'skill must not be a symlink: {path}')
                    self.assertEqual(
                        _frontmatter_name(path), name,
                        f'frontmatter name must match its directory: {path}',
                    )
            for name in AGENT_NAMES:
                path = project / '.claude' / 'agents' / f'{name}.md'
                self.assertTrue(path.is_file(), f'missing agent file: {path}')
                self.assertFalse(path.is_symlink(), f'agent must not be a symlink: {path}')
                self.assertEqual(_frontmatter_name(path), name)
                self.assertTrue((project / '.codex' / 'agents' / f'{name}.toml').is_file())

    def test_synthetic_example_runs_one_assignment_end_to_end(self):
        """Drive the shipped fixture through the whole workflow to ready."""
        driver = REPO_ROOT / 'examples' / 'synthetic' / 'run_workflow.py'
        self.assertTrue(driver.is_file(), 'synthetic example driver is missing')
        with tempfile.TemporaryDirectory() as t:
            result = subprocess.run(
                [sys.executable, str(driver), '--workspace', str(Path(t) / 'workspace'), '--quiet'],
                text=True, capture_output=True, cwd=str(REPO_ROOT),
                env={**__import__('os').environ, 'PYTHONPATH': str(REPO_ROOT / 'src')},
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            run_root = Path(t) / 'workspace' / 'assignments' / 'synthetic-run-1'
            state = json.loads((run_root / 'run.json').read_text())
            self.assertEqual(state['stage'], 'ready')
            # The deliverable the plan declared exists and is a real PDF.
            artifact = run_root / 'deliverables' / 'submission.pdf'
            self.assertTrue(artifact.is_file())
            self.assertEqual(artifact.read_bytes()[:5], b'%PDF-')
            # Every declared calculation was independently checked and passed.
            self.assertTrue(state['checks'])
            self.assertTrue(all(check['passed'] is True for check in state['checks']))
            # Identity never leaves the framework placeholders.
            self.assertEqual(state['identity']['display_name'], '[Student Name]')
            self.assertIs(state['identity']['explicit'], False)

    def test_synthetic_example_directory_holds_no_generated_output(self):
        """The fixture is inputs only; a run must never write back into it.

        Asserted against the shapes a run actually produces rather than an
        exact file manifest, so adding a legitimate input stays possible while
        generated output still fails loudly.
        """
        fixture = REPO_ROOT / 'examples' / 'synthetic'
        generated_names = {'run.json', 'catalog.json', 'reviews.json', 'deliverables'}
        generated_suffixes = {'.pdf', '.docx', '.xlsx', '.png'}
        for path in fixture.rglob('*'):
            self.assertNotIn(
                path.name, generated_names,
                f'generated run output must not live in the fixture: {path}',
            )
            self.assertNotIn(
                path.suffix.casefold(), generated_suffixes,
                f'rendered artifact must not live in the fixture: {path}',
            )

    def test_distribution_excludes_workspace_and_rejects_personal_path(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t); (root/'workspace').mkdir(); (root/'workspace'/'x').write_text('x')
            self.assertEqual(check_distribution.audit(root),[])
            (root/'workspace').rename(root/'src'); (root/'src'/'x').write_text('/Users/example/private')
            self.assertTrue(check_distribution.audit(root))
    def test_distribution_skips_venv_cache(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t); (root/'.venv').mkdir(); (root/'.venv'/'secret.key').write_text('x'); (root/'build').mkdir(); (root/'build'/'generated.py').write_text('/Users/example/private')
            self.assertEqual(check_distribution.audit(root),[])

if __name__=='__main__': unittest.main()
