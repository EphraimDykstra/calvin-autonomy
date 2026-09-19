"""The tracked skill mirrors must equal their sources.

``skills/`` holds each skill's source, and ``.claude/skills/`` and
``.agents/skills/`` hold the copies a host actually reads.  ``setup.py``
refreshes a copy only when a manifest marks it as managed, which is the right
caution in a student's project but means nothing re-syncs the copies committed
to this repository.  An edited source with a stale mirror ships the old skill
to every student, and nothing in a passing suite would say so.
"""

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIRRORS = (".claude/skills", ".agents/skills")


class SkillMirrorTests(unittest.TestCase):
    def test_every_mirror_matches_its_source(self):
        sources = sorted(p for p in (ROOT / "skills").glob("*/SKILL.md"))
        self.assertTrue(sources, "no skill sources found")
        for source in sources:
            name = source.parent.name
            for mirror in MIRRORS:
                copy = ROOT / mirror / name / "SKILL.md"
                with self.subTest(skill=name, mirror=mirror):
                    self.assertTrue(copy.is_file(), f"{mirror}/{name} is missing")
                    self.assertEqual(
                        copy.read_text(encoding="utf-8"),
                        source.read_text(encoding="utf-8"),
                        f"{mirror}/{name}/SKILL.md is stale; copy it from skills/{name}/",
                    )


if __name__ == "__main__":
    unittest.main()
