import tempfile
import unittest
from pathlib import Path

from engineering_assistant.memory import forget_memory, list_memory, set_memory


class StudentMemoryTests(unittest.TestCase):
    def test_explicit_set_list_and_forget(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / "workspace"
            saved = set_memory(workspace, "report.voice", "third person", scope="ENGR328", source="student preference")
            self.assertEqual(saved["authority"], "preference_only")
            self.assertEqual(list_memory(workspace)["entries"]["report.voice"]["value"], "third person")
            self.assertTrue(forget_memory(workspace, "report.voice")["forgotten"])
            self.assertEqual(list_memory(workspace)["entries"], {})

    def test_rejects_secret_and_ability_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            for key in ("api_token", "credential", "ability"):
                with self.assertRaises(ValueError):
                    set_memory(workspace, key, "value", scope="all", source="user")


if __name__ == "__main__":
    unittest.main()
