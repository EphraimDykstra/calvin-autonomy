# Pilot status

The framework is usable for bounded local pilots. It is not yet a claim that every ENGR 328 assignment family is validated.

## Implemented

- Repeatable Claude Code and Codex skill/agent installation
- Dedicated course-profile curator for reviewed professor-specific methods and deliverable conventions
- Private project workspace and explicit student memory
- Hash-preserving, idempotent PDF, DOCX, XLSX, and bounded image ingestion
- Fail-closed OCR queues plus hash-bound, complete transcription import that remains unreviewed until exact visual comparison
- Optional automatic OCR for image and scanned-PDF sources; PDF pages are rendered at 200 dpi so the page transform is applied, and the rasterizer is an optional extra whose absence leaves scanned sources in the manual queue
- Course-scoped search with page, sheet, or paragraph locators
- Historical syllabus AI-section exclusion
- Same-course example registration and assignment-family matching
- Difference manifests that remove prior identity and stale results
- Durable assignment plans, solutions, calculation checks, artifacts, and readiness state
- Placeholder identity by default and a distribution privacy audit
- Plain worked-problem PDF rendering with visual inspection
- Technical-report PDF rendering with an unnumbered title/abstract page, numbered body pages, equations, tables with captions above, figures with captions below, and appendices
- Editable DOCX rendering with course-profile layout, tables, figures, captions, appendices, placeholder identity, and body-page numbering
- Editable XLSX rendering with summary, engineering tables, calculation records, formula-injection protection, and deterministic output
- Same-course evidence resolution using document IDs, source hashes, locators, extracted-text hashes, and reviewed status
- Plan and solution hashes, solution-bound calculation checks and artifacts, requested-format parsing, and structured artifact inspection
- Durable evidence-review registry; plan text cannot self-promote provisional evidence to reviewed
- Independent structured verifier reports bound to input, plan, solution, calculation-check, and artifact hashes
- Project-local CLI launcher installed beside Claude Code and Codex skills
- Read-only setup doctor for dependencies, launcher, workspace, client discovery, and optional OCR capability
- Recomputed status that detects changed inputs, plans, solutions, or deliverables after a run was marked ready
- Deterministic grayscale-readable engineering plots, sized in points so a small figure keeps page-legible text, with the legend placed outside the axes so it cannot hide data
- Generic 10-20-run held-out evaluation harness with false-ready, blocker, coverage, verification, stale-detection, and correction-time metrics
- Rendering enforces the course profile's stated format: a body-page budget, required figure roles, and a printable frame derived from the profile's margins rather than fixed constants
- Plots are self-describing: a rendered plot carries its own target size, so the size it was drawn for and the size it is placed at cannot silently disagree
- A visual inspection that finds problems is recorded rather than refused, so "inspected and rejected" is distinguishable from "nobody looked", and readiness names the recorded findings
- Recording steps that invalidate downstream work report what they discarded instead of dropping it silently
- Identity values too short to redact without corrupting surrounding text are refused rather than accepted and shredded
- Distribution audit scans tracked files for supplied real names, and states which scans actually ran
- Archive members are bounded as they decompress, and parsed as they decompress, so neither an oversized member nor an in-bound member that re-amplifies while parsing can exhaust memory
- Document type definitions are refused in DOCX and XLSX parts, so entity expansion cannot depend on a version-specific parser limit

## Pilot evidence

These results were observed in a private workspace. **None of them is reproducible from a clean
checkout**, and nothing in this repository substantiates them: private course material, run
records, and evaluation manifests live outside the shared tree by design, so a reader cannot
verify any entry below. The held-out evaluation in particular requires a manifest referencing
runs that are not distributed. Treat this section as a record of what was observed, not as
evidence a reader can check.

- Radiation heat-loss homework: requirements covered, two calculations checked, course answer reproduced, PDF visually inspected, ready with no blockers
- Counterflow heat exchanger homework: method selected from reviewed course evidence and problem conditions, eight calculations checked, course answers reproduced, PDF visually inspected, ready with no blockers
- Numerical-conduction adaptation: Homework 9 matched Homework 10, the steady-to-transient change was classified as method-changing, and all current requirements require fresh work
- Missing-input laboratory case: blocked because measured data was absent; no values or deliverable were invented
- Internal-combustion performance report: seven real operating points were preserved; 21 power, thermal-efficiency, and panel-power comparison calculations passed; the efficiency plot was ordered by shaft power; the five-page report passed independent verification and visual/privacy inspection; ready with no blockers
- Private 10-case held-out evaluation: 10/10 expected outcomes matched across two runs, zero false-ready and false-blocked cases, 7/7 expected blockers detected, 6/6 stale cases detected, and 40/42 planned requirements structurally covered

## Still provisional

- Held-out air-conditioning report: blocked until a current assignment prompt and authoritative measurement dataset are supplied; the available historical report contains unresolved conflicting measurements
- Full internal-combustion energy-balance report beyond the validated performance-curve sub-report
- Semantic interpretation of equations and diagrams. Automatic OCR now covers image and scanned-PDF sources, and explicit hash-bound transcription import remains available, but **no local OCR engine is installed on the development machine**, so the engine half of that path is exercised only through injected test runners
- Discipline-specific active spreadsheet formulas, EES, MATLAB, and archive deliverables; generic deterministic PDF, DOCX, XLSX, and plot generation is implemented
- Fresh-checkout testing in both Claude Code and Codex on separate student machines

An unsupported or unvalidated family must remain incomplete instead of being represented as ready.
