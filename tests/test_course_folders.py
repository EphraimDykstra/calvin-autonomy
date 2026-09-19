"""Runs are scoped to their course, and the two layouts that exist stay working.

Course *materials* were already segregated under `courses/<course>/`.  Student
*work* was not: every run from every course landed flat in `assignments/`, so a
junior taking five courses got one undifferentiated pile.  These tests cover the
one segment that fixes it and the ways it could go wrong.
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / 'scripts'))
import setup  # noqa: E402

from engineering_assistant.runtime import (  # noqa: E402
    course_dir, load_run, run_dir, runs_root, start_run, status_run, workspace_of,
)


class CourseFolderTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.ws = self.root / 'workspace'
        self.source = self.root / 'assignment.txt'
        self.source.write_text('requirements', encoding='utf-8')

    def test_each_course_keeps_its_own_folder(self):
        """The point of the feature: five courses, five folders, not one pile."""
        start_run(self.ws, 'lab-3', 'engr319', self.source)
        start_run(self.ws, 'hw-7', 'engr331', self.source)
        self.assertTrue((self.ws / 'assignments' / 'engr319' / 'lab-3' / 'run.json').is_file())
        self.assertTrue((self.ws / 'assignments' / 'engr331' / 'hw-7' / 'run.json').is_file())
        # Nothing is left at the old flat location.
        self.assertFalse((self.ws / 'assignments' / 'lab-3').exists())
        self.assertEqual(
            sorted(p.name for p in runs_root(self.ws).iterdir()), ['engr319', 'engr331'],
        )

    def test_a_run_is_found_by_its_id_without_naming_its_course(self):
        """No downstream command takes a course; the run id alone has to find it."""
        start_run(self.ws, 'lab-3', 'engr319', self.source)
        self.assertEqual(load_run(self.ws, 'lab-3')['course'], 'engr319')
        self.assertEqual(run_dir(self.ws, 'lab-3'), course_dir(self.ws, 'engr319') / 'lab-3')

    def test_a_course_with_no_pack_still_gets_a_folder(self):
        """An unknown course is a normal course here; it must not be a special case."""
        start_run(self.ws, 'hw-1', 'engr999', self.source)
        self.assertTrue((self.ws / 'assignments' / 'engr999' / 'hw-1' / 'run.json').is_file())

    def test_a_run_id_is_matched_by_name_and_never_as_a_glob(self):
        """A wildcard id must not resolve to somebody else's run.

        `validate_run_id` allows `*`, `?` and `[`, which were inert while a run
        id was only ever a literal path component.  Resolving one by pattern
        would let `lab*` load another course's `lab-3`, and the next write would
        save it back under that run's own id: a silent cross-course overwrite.
        """
        start_run(self.ws, 'lab-3', 'engr319', self.source)
        for wildcard in ('lab*', 'lab-?', 'lab-[0-9]', '*'):
            with self.subTest(run_id=wildcard):
                with self.assertRaises(FileNotFoundError):
                    load_run(self.ws, wildcard)
        self.assertEqual(load_run(self.ws, 'lab-3')['course'], 'engr319')

    def test_a_new_run_id_that_reads_as_a_pattern_is_refused(self):
        """Stop minting ids that read as filename patterns.

        Nothing on the run-id path globs any more, so this is not what makes
        resolution safe.  It stops the project creating names that invite the
        same mistake again, and the message has to name the character, because
        a student told only "invalid run id" cannot tell what to change.
        """
        for bad in ('lab*', 'lab-?', 'lab[1]', '*'):
            with self.subTest(run_id=bad):
                with self.assertRaises(ValueError) as caught:
                    start_run(self.ws, bad, 'engr319', self.source)
                message = str(caught.exception)
                self.assertIn(repr(next(c for c in '*?[' if c in bad)), message)
                self.assertIn('pattern', message)
        self.assertFalse(runs_root(self.ws).exists(), 'a refused id must create nothing')

    def test_a_run_already_named_with_a_pattern_character_still_loads(self):
        """Loading stays permissive; there is no migration.

        Tightening the read path would orphan a run a student already has, which
        is the one thing this whole change is not allowed to do.
        """
        start_run(self.ws, 'lab-1', 'engr319', self.source)
        existing = course_dir(self.ws, 'engr319')
        (existing / 'lab-1').rename(existing / 'lab[1]')
        state_path = existing / 'lab[1]' / 'run.json'
        state_path.write_text(state_path.read_text().replace('"lab-1"', '"lab[1]"'), encoding='utf-8')
        self.assertEqual(load_run(self.ws, 'lab[1]')['run_id'], 'lab[1]')
        self.assertEqual(run_dir(self.ws, 'lab[1]'), existing / 'lab[1]')

    def test_a_run_id_used_in_another_course_is_refused_not_silently_shadowed(self):
        """Two runs sharing an id would make `run_id` ambiguous for every later command."""
        start_run(self.ws, 'lab-3', 'engr319', self.source)
        with self.assertRaises(ValueError):
            start_run(self.ws, 'lab-3', 'engr331', self.source)
        self.assertFalse((self.ws / 'assignments' / 'engr331' / 'lab-3' / 'run.json').exists())


class LegacyLayoutTests(unittest.TestCase):
    """Runs made before runs were course-scoped must keep working.

    Two layouts are supported on purpose:

        <workspace>/assignments/<course>/<run_id>/run.json   current
        <workspace>/assignments/<run_id>/run.json            legacy

    The flat fall-through in `_resolve_run_dir` is NOT dead code and must not be
    "cleaned up".  There is no migration: a student's existing runs stay exactly
    where they are, and removing it orphans every one of them with no error to
    notice.  It is easy to mistake for the not-found path, because a missing run
    is reported against the same place, so these tests are what stands between a
    tidy-up and a student's lost work.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.ws = self.root / 'workspace'
        self.source = self.root / 'assignment.txt'
        self.source.write_text('requirements', encoding='utf-8')

    def _make_legacy_run(self, run_id='old-lab', course='engr319', workspace=None):
        """Build a run, then move it to where the previous layout put it."""
        workspace = self.ws if workspace is None else workspace
        start_run(workspace, run_id, course, self.source)
        legacy = runs_root(workspace) / run_id
        shutil.move(str(course_dir(workspace, course) / run_id), str(legacy))
        (runs_root(workspace) / course).rmdir()
        return legacy

    def test_a_legacy_run_is_still_found_and_loaded(self):
        legacy = self._make_legacy_run()
        self.assertEqual(run_dir(self.ws, 'old-lab'), legacy)
        self.assertEqual(load_run(self.ws, 'old-lab')['course'], 'engr319')

    def test_a_legacy_run_reports_the_same_status_as_a_course_scoped_one(self):
        """Proves the workspace is resolved at both depths.

        Readiness resolves plan evidence and the course profile against the
        workspace, which used to be derived by counting parents.  At the wrong
        depth that silently looks in the wrong place, so the two layouts must
        produce identical blockers rather than merely not crashing.
        """
        start_run(self.ws, 'new-lab', 'engr319', self.source)
        nested = status_run(self.ws, 'new-lab')['readiness']
        legacy_ws = self.root / 'legacy-workspace'
        self._make_legacy_run(run_id='new-lab', course='engr319', workspace=legacy_ws)
        legacy = status_run(legacy_ws, 'new-lab')['readiness']
        self.assertEqual(legacy['blockers'], nested['blockers'])
        self.assertTrue(nested['blockers'], 'a blocker-free run would make this comparison vacuous')

    def test_a_new_run_cannot_reuse_a_legacy_run_id(self):
        self._make_legacy_run(run_id='old-lab')
        with self.assertRaises(ValueError):
            start_run(self.ws, 'old-lab', 'engr331', self.source)


class CourseFolderContainmentTests(unittest.TestCase):
    """The failure that would destroy a student's work without warning.

    Claude Code replaces the plugin directory on every update and deletes the
    plugin data directory on uninstall.  A workspace there loses everything, so
    course folders, which are derived from the workspace, must never reach it.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_no_course_folder_is_created_inside_the_plugin_cache_or_data_store(self):
        for store in ('cache', 'data'):
            fake_home = self.root / f'home-{store}'
            project = fake_home / '.claude' / 'plugins' / store / 'calvin-autonomy' / 'schoolwork'
            for extra in ([], ['--plugin']):
                code = setup.main(['--project-root', str(project), '--workspace', 'workspace', *extra])
                self.assertEqual(code, 2)
                self.assertFalse(project.exists(), 'a refused setup must create nothing')
            # The workspace is refused, so the course folder under it cannot exist.
            outside = self.root / f'student-{store}'
            unsafe_workspace = project / 'workspace'
            code = setup.main(['--project-root', str(outside), '--workspace', str(unsafe_workspace)])
            self.assertEqual(code, 2)
            self.assertFalse(unsafe_workspace.exists())
            self.assertFalse(course_dir(unsafe_workspace, 'engr319').exists())

    def test_a_course_name_cannot_place_runs_outside_the_workspace(self):
        ws = self.root / 'workspace'
        source = self.root / 'assignment.txt'
        source.write_text('requirements', encoding='utf-8')
        for hostile in ('../escape', 'a/b', '..', '/absolute', '.hidden', 'a\\b'):
            with self.subTest(course=hostile):
                with self.assertRaises(ValueError):
                    course_dir(ws, hostile)
                with self.assertRaises(ValueError):
                    start_run(ws, 'run-1', hostile, source)
        self.assertFalse((self.root / 'escape').exists())

    def test_every_course_folder_stays_inside_its_workspace(self):
        ws = self.root / 'workspace'
        for course in ('engr319', 'engr204-lab', 'a', 'A_1-2'):
            with self.subTest(course=course):
                resolved = course_dir(ws, course).resolve()
                self.assertTrue(resolved.is_relative_to(ws.resolve()))


class WorkspaceDepthTests(unittest.TestCase):
    def test_workspace_is_recovered_from_a_run_root_at_either_depth(self):
        ws = Path('/tmp/ws')
        self.assertEqual(workspace_of(ws / 'assignments' / 'engr319' / 'lab-3'), ws)
        self.assertEqual(workspace_of(ws / 'assignments' / 'lab-3'), ws)

    def test_a_course_literally_named_assignments_still_resolves(self):
        """Checked nested-first, so the one ambiguous name does not misresolve."""
        ws = Path('/tmp/ws')
        self.assertEqual(workspace_of(ws / 'assignments' / 'assignments' / 'lab-3'), ws)


if __name__ == '__main__':
    unittest.main()
