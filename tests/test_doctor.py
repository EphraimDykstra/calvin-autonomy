import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from engineering_assistant.doctor import MANAGED_AGENTS, MANAGED_SKILLS, diagnose


def _managed_files():
    """Every file a fully installed project is expected to hold."""
    for name in MANAGED_SKILLS:
        yield f".agents/skills/{name}/SKILL.md"
        yield f".claude/skills/{name}/SKILL.md"
    for name in MANAGED_AGENTS:
        yield f".codex/agents/{name}.toml"
        yield f".claude/agents/{name}.md"
    yield ".calvin-autonomy/bin/coursework"


def _build_project(root, skip=()):
    workspace = root / "workspace"
    workspace.mkdir(exist_ok=True)
    for relative in _managed_files():
        if relative in skip:
            continue
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("managed", encoding="utf-8")
    return workspace


class DoctorTests(unittest.TestCase):
    def test_complete_project_is_ready_with_optional_ocr_warning(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = _build_project(root)
            with patch("engineering_assistant.ocr.engine_probe", return_value=None):
                result = diagnose(root, workspace)
            self.assertTrue(result["ready"], result["blockers"])
            self.assertEqual(result["blockers"], [])
            self.assertFalse(result["ocr"]["automatic_engine_available"])
            self.assertTrue(result["warnings"])

    def test_one_missing_managed_skill_blocks_readiness(self):
        """A tree holding complete-assignment but missing another skill is not ready.

        The spot check this replaced passed such a tree, so the host would only
        discover the gap when it failed to find the skill mid-assignment.
        """
        missing = ".claude/skills/verify-assignment/SKILL.md"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = _build_project(root, skip=(missing,))
            result = diagnose(root, workspace)
            self.assertFalse(result["ready"])
            self.assertIn(
                "managed skill is missing for claude: verify-assignment",
                result["blockers"],
            )
            self.assertFalse(result["managed_skills"]["verify-assignment"]["claude"])
            self.assertTrue(result["managed_skills"]["verify-assignment"]["codex"])
            # The original spot-checked integration is still reported present.
            self.assertTrue(result["project_discovery"]["claude_skills"])

    def test_one_missing_managed_agent_blocks_readiness(self):
        missing = ".claude/agents/assignment-verifier.md"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = _build_project(root, skip=(missing,))
            result = diagnose(root, workspace)
            self.assertFalse(result["ready"])
            self.assertIn(
                "managed agent is missing for claude: assignment-verifier",
                result["blockers"],
            )

    def test_missing_integrations_and_workspace_block_readiness(self):
        with tempfile.TemporaryDirectory() as directory:
            result = diagnose(Path(directory), Path(directory) / "workspace")
            self.assertFalse(result["ready"])
            self.assertTrue(any("workspace" in blocker for blocker in result["blockers"]))
            self.assertTrue(any("launcher" in blocker for blocker in result["blockers"]))


if __name__ == "__main__":
    unittest.main()
