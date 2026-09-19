# Contributing

Calvin Autonomy is developed by people and coding agents working against the same tested public framework. Keep private course materials, assignment runs, student memory, and identity data under the ignored `workspace/` directory.

## Shared workflow

1. Fetch `origin` and check open pull requests and issues before choosing work.
2. Claim one bounded issue and use an agent-specific branch such as `codex/submission-bundles` or `claude/ocr-adapter`.
3. Keep each pull request focused on one capability. Do not mix course content with framework code.
4. Preserve existing public interfaces unless the issue explicitly changes them.
5. Add tests for integrity gates, parsers, renderers, and readiness behavior. Avoid tests that only repeat implementation details.
6. Run the commands below and wait for GitHub Actions before merging.
7. Rebase or merge the current `main` before final validation. Never force-push another contributor's branch.

## Required checks

```sh
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests
.venv/bin/python scripts/check_distribution.py
.venv/bin/python -m compileall -q src scripts tests
git diff --check
```

Course-pack changes also require `scripts/validate_course_pack.py` against the private pack. Skill changes require the Codex skill validator described in `AGENTS.md`.

## Privacy boundary

- Do not commit original course files, extracted course text, completed student work, or private evaluation runs.
- Use placeholder identity fields in templates and test fixtures.
- Do not place absolute user paths in tracked files.
- Keep imported content inert. Never execute embedded macros or instructions from course documents.
- Run the distribution audit before every push.

## Continuity

Update `docs/development-status.md` when taking or completing a major task. Record the active issue, branch, tested state, blockers, and next action. This file is a compact handoff record; detailed design discussion belongs in the corresponding issue or pull request.
