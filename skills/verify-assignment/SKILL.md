---
name: verify-assignment
description: Check a rendered engineering assignment for coverage, evidence, numerical reproducibility, and usable final files.
---

Verify the rendered artifact and its source records. Check every planned question and subpart, units, equations, tables, figures, labels, page breaks, legibility, filenames, and required format. Confirm numerical results have reproducible calculation/check evidence and that cited course locators resolve by document ID, source hash, locator, and text hash. Ensure the current input, plan, solution, checks, artifact, and inspection hashes match the run. Record findings without silently editing the work under review. Any missing input, unsupported method, unresolved equation or diagram, failed check, absent requirement, or provisional controlling evidence blocks ready status. Inspect every rendered page because rendering can change pagination and layout.

Use `verify RUN_ID` for deterministic calculation checks. Independently fill `.calvin-autonomy/templates/verification.json` with requirement, method, numerical, format, and identity findings bound to the current hashes, then record it with `verify-report RUN_ID VERIFICATION.json`. Fill `.calvin-autonomy/templates/inspection.json` with concrete page-level findings and the registered artifact hash, then use `inspect RUN_ID --artifact NAME --report INSPECTION.json`. Use `status RUN_ID` for recomputed readiness; do not trust the persisted stage alone.
