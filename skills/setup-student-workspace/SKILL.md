---
name: setup-student-workspace
description: Initialize a project-scoped student workspace and install the shared skills and host adapters safely.
---

Run the repository setup script with an explicit project workspace. Setup is idempotent: it creates private course, assignment, memory, and run locations and copies shared skills into `.agents/skills/` and `.claude/skills/`, with coordinator adapters for Codex and Claude where supported. Preserve user files and report drift; `--force` refreshes only files previously marked as managed. Do not alter global client settings, private source originals, or unrelated workspace files. Keep student data private and use generic paths in shareable material.

Run `.venv/bin/python scripts/setup.py --project-root . --workspace workspace`, then `.calvin-autonomy/bin/coursework --workspace workspace doctor --project-root .`. Treat doctor blockers as setup failures; an unavailable automatic OCR engine is a warning because explicit reviewed transcription import remains available. Add `--force` only to refresh managed generated files.
