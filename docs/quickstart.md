# Quickstart

Identity is private and opt-in. `start` uses `[Student Name]` and `[Student ID]` placeholders unless `--display-name` or `--student-id` is supplied; an explicitly supplied value is stored only in that run. Reusable examples remove identity-labelled metadata and redact supplied names and IDs before writing `examples.json`. Shared skills, templates, examples, and docs must stay generic and must not contain course files or local absolute paths.

Run setup from the repository root:

    python3 -m venv .venv
    .venv/bin/python -m pip install -e .
    .venv/bin/python scripts/setup.py --project-root . --workspace workspace
    .calvin-autonomy/bin/coursework --workspace workspace doctor --project-root .
    .calvin-autonomy/bin/coursework --workspace workspace init

Setup is repeatable and project-scoped. It installs shared skills into the opened project's `.agents/skills/` and `.claude/skills/`, installs host adapters and `.calvin-autonomy/bin/coursework`, and keeps private data under `workspace/`. Existing student files are retained. `doctor` checks the launcher, required Python modules, private workspace, and Claude/Codex discovery files without changing them; unavailable automatic OCR is reported as a warning. Use `--force` only when refreshing files previously marked managed.

Ingest a bounded course sample with `.calvin-autonomy/bin/coursework --workspace workspace ingest PATH --course COURSE_ID --max-files 50 --max-pages 100`, then search with `.calvin-autonomy/bin/coursework --workspace workspace search "topic or method" --course COURSE_ID`. Search returns a `status` with what was searched (the course, and how many documents and blocks). On `found`, `results` carries the document ID, source hash, locator, extracted-text hash, and durable review status for each hit. A search that finds nothing carries no `results` at all and says which kind of nothing it found: `no_match` means the course's text was searched and does not contain the terms, while `nothing_indexed` and `no_catalog` mean nothing was searched, so neither is evidence about the course. Each of those carries a `next` saying what to do. Image files and image-only PDF pages stay visibly unresolved with hash-bound OCR review manifests; `ocr-status --course COURSE_ID` lists them and reports whether a local OCR engine is present without running it.

To add an externally produced transcription, copy `.calvin-autonomy/templates/ocr-transcription.json` to a private working file. Set its `document_id` and `source_sha256` from `ocr-status`, describe the transcription tool under `provenance`, and supply exactly one nonblank block for each pending locator. Import it with `.calvin-autonomy/bin/coursework --workspace workspace ocr-import TRANSCRIPTION.json --course COURSE_ID`. The source must have been fully ingested; truncated documents and missing, extra, or duplicate locators are rejected. The import preserves native PDF text, stores the normalized transcription under the private workspace with source/content/file hashes, and refuses replacement imports. An identical retry is idempotent. Imported text is still unreviewed: visually compare each exact location with its source and run `evidence-review` for every locator that will control a method or format. Unreviewed evidence cannot control a method or format. Readiness checks the review registry rather than trusting a plan assertion. Build a reviewed profile from `.calvin-autonomy/templates/course-profile.json`, register it with `profile-set PROFILE.json --course COURSE_ID`, and use the hash returned by `profile-show --course COURSE_ID` in assignment plans. The renderer consumes its normalized font, spacing, margin, title-page, abstract, caption, and page-number rules.

To build the reusable-example index, place a structured, reviewed example in a
private workspace file and run `coursework --workspace workspace example-add FILE --course COURSE_ID`. For a new
assignment, copy `.calvin-autonomy/templates/assignment.json` into the private run, fill it only from the current assignment and reviewed course evidence, and run `coursework --workspace workspace match FILE --course COURSE_ID`; if a prior example
matches, `coursework --workspace workspace adapt CURRENT PRIOR --out MANIFEST.json` produces a change manifest.
The manifest identifies what can be reused and what must be recalculated or
rewritten for the current requirements. It never copies prior student identity,
results, or artifact paths.

For an assignment, supply original requirements and all inputs, then ask Claude Code or Codex to use `complete-assignment`. The host starts the private run with an explicit run ID, reads the source, writes a plan based on `.calvin-autonomy/templates/plan.json`, retrieves matching same-course evidence/examples, and solves after the plan is established. It records reproducible numerical checks and renders every declared PDF, DOCX, or XLSX artifact. The assignment verifier then records a hash-bound report covering every requirement plus method, numerical, format, and identity checks. A separate structured inspection report records the visual review of each artifact. Missing measurements, invented or stale locators, unreviewed controlling evidence, unresolved requirements, missing required calculations, corrupt or wrong-format artifacts, failed verification, or incomplete inspection block ready status. `status` recomputes readiness from files instead of trusting a saved stage. Execute mode returns concise deliverables and does not add quizzes.

Student memory is explicit and private: `memory list`, `memory set`, and `memory forget`. Memory stores preferences and pointers, never replaces current assignment instructions or course evidence. Never put coursework or generated private data in shareable files.

## Adding a course: seeing where you stand

The steps above describe the work. Three read-only reports tell you where you are in it, what is
still pending, and what the course can actually back. None of them writes anything, and none of
them takes your word for a state it can check itself.

### Where am I?

    .calvin-autonomy/bin/coursework --workspace workspace onboarding-status --course COURSE_ID

Onboarding runs in a fixed order (ingest sources, resolve extraction and OCR, review evidence,
register the profile, register examples) because each step needs the one before it. The report
names the single step to work on next and what each unfinished step is holding up. Abridged, for a
course whose style guide was re-ingested after its profile was registered:

```json
{
  "course": "course-205",
  "ready": false,
  "next_step": "review_evidence",
  "steps": [
    {"id": "ingest_sources",     "state": "done",    "blocks": []},
    {"id": "resolve_extraction", "state": "done",    "blocks": []},
    {"id": "review_evidence",    "state": "pending",
     "detail": "0 of 1 extracted passage(s) reviewed; 1 cited passage(s) pending exact visual review",
     "blocks": ["register_profile", "register_examples"]},
    {"id": "register_profile",   "state": "blocked",
     "detail": "cited evidence does not resolve as reviewed: evidence 1 locator or text hash is stale",
     "blocks": ["register_examples"]},
    {"id": "register_examples",  "state": "blocked", "blocks": []}
  ]
}
```

Read `state` as: `done` is finished, `pending` is yours to do now, `blocked` is waiting on
something earlier. A finished step blocks nothing. Work `next_step` and re-run; the report is
recomputed from the workspace every time, so it cannot drift from the real state.

### What is pending review?

    .calvin-autonomy/bin/coursework --workspace workspace evidence-queue --course COURSE_ID

```json
{
  "course": "course-205",
  "status": "review_required",
  "pending_count": 1,
  "pending": [
    {"document_id": "style-guide", "locator": "page:1", "state": "stale",
     "text_sha256": "02cdb6af…", "blocks": ["course-profile"]}
  ],
  "blocks_total": 1, "blocks_reviewed": 0, "blocks_awaiting_review": 1,
  "documents_awaiting_extraction": 0
}
```

Each pending entry says where the passage is (`document_id`, `locator`), why it is pending
(`state`), and what it is holding up (`blocks`). Work the queue down by state:

- `unreviewed`: extracted and resolving, but nobody has confirmed it. Review it.
- `stale`: the source changed under a review that already happened, so the old review no longer
  describes the current text. Review the new text.
- `unextracted`: the source is still in the OCR queue. Resolve extraction first; `ocr-status`
  lists what is waiting.
- `unresolved`: the citation points at a document that is not an active source of this course.
  Fix the citation.

The queue deliberately carries identifiers, hashes, and states, never the extracted text, and
never previous reviewers' notes. This is the reason behind the review rule stated above: the
review is an *exact visual* review of the rendered page. If the queue handed you the extracted
text, you could approve a passage by reading the queue instead of the source, and a review that
never looked at the page is the failure the review gate exists to prevent. Open the document at
that locator, look at it, then run `evidence-review` for that locator.

## What a course can actually back

    .calvin-autonomy/bin/coursework --workspace workspace coverage --course COURSE_ID

Optionally pass `--expected FILE`, a JSON object naming what you are about to attempt, so the
report also answers for work that has no coverage at all:

    {"assignment_families": ["design-project"], "methods": [], "formatting_rules": []}

```json
{
  "course": "course-205",
  "ready": true,
  "summary": {"reviewed": 4, "provisional": 2, "absent": 1},
  "items": [
    {"kind": "assignment_family", "name": "design-project", "state": "absent",
     "reason": "nothing registered for this course covers it", "sources": []},
    {"kind": "assignment_family", "name": "heat-exchanger-homework", "state": "reviewed",
     "reason": "1 reviewed example(s) registered", "sources": ["hx-1"]},
    {"kind": "assignment_family", "name": "lab-report", "state": "provisional",
     "reason": "1 registered example(s), none marked reviewed", "sources": ["lab-1"]},
    {"kind": "formatting_rule", "name": "reporting", "state": "reviewed",
     "reason": "backed by resolved, reviewed course evidence", "sources": ["course-profile"]}
  ],
  "blockers": []
}
```

### Three states, not two

`reviewed`, `provisional`, and `absent` are three different answers. Nothing collapses them into a
yes and a no.

- **`reviewed`**: resolved, reviewed evidence stands behind it. Someone looked at the rendered
  source and confirmed it, and that source still matches the citation today.
- **`provisional`**: registered, but nothing reviewed backs it. The material is in the workspace
  and was never confirmed against the source.
- **`absent`**: nothing covers it at all.

**`provisional` is not a soft yes.** It is not "mostly reviewed" or "reviewed enough for
homework." It means the claim is sitting in the workspace unconfirmed, which is the same evidentiary
position as not having it, with the added risk that it looks like coverage at a glance. In the
report above, `lab-report` is provisional: there is a lab report example registered, nobody
reviewed it, and the course therefore cannot back lab report work yet. The fix is to review it,
not to proceed carefully.

### What absent means in practice

`coverage` reports; it does not enforce. An absent family does not itself trigger a refusal. It
tells you that nothing in this course backs that work, and the refusal arrives downstream, where
the gates are:

- A plan cannot cite reviewed same-course evidence that does not exist, so `resolve_evidence`
  holds the run short of ready and `status` keeps reporting it unresolved.
- Rendering loads the course profile, so a missing or degraded profile stops artifacts being
  produced at all.

Reading `coverage` first turns that late, scattered failure into one early answer. A course that
reports `heat-exchanger-homework: reviewed` and `lab-report: provisional` will do the first and
refuse the second, and **the refusal is the system working correctly.** A tool that produced a
confident lab report for a course with no reviewed lab report evidence would be guessing at your
instructor's requirements and presenting the guess as coursework. Being told no is the useful
answer; it says go review the evidence, or go find out what the instructor actually wants.

### Reading `ready`

`ready` is the whole-course summary, and it is false whenever anything would make support an
overstatement: a missing or degraded profile, no assignment family with a reviewed example behind
it, or a source still unextracted and therefore unread. An unread source can carry a formatting
rule or method constraint that contradicts everything else in the report, so it blocks a clear
result exactly as a missing profile does. `blockers` lists every reason in full.
