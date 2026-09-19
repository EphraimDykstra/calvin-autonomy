# Synthetic end-to-end example

A self-contained, entirely invented assignment that exercises one complete
workflow: ingest, evidence review, course profile, plan, render, reproducible
checks, verification, inspection, ready status.

Nothing here comes from a real course. The assignment, the method notes, and the
worked solution were written for this fixture, and identity fields are the
placeholders `[Student Name]` and `[Student ID]`.

## Run it

From the repository root, with the project installed:

    python examples/synthetic/run_workflow.py --workspace workspace/example

All generated output (the course catalog, the run state, the rendered PDF)
goes to `--workspace`. The driver refuses to run if that path resolves inside
this directory, so the fixture stays inputs-only. `workspace/` is gitignored.

The same run is exercised by
`tests/test_setup.py::SetupTests::test_synthetic_example_runs_one_assignment_end_to_end`.

## The problem

A cantilever beam carries a 500 N point load at its free end. Span 2.0 m,
rectangular section 0.05 m by 0.10 m, E = 200 GPa.

| Quantity | Method | Result |
| --- | --- | --- |
| Maximum bending stress | `sigma = M / S`, `M = P*L`, `S = b*h^2/6` | 12.0 MPa |
| Maximum free-end deflection | `delta = P*L^3/(3*E*I)`, `I = b*h^3/12` | 1.60 mm |

Both land on values a reviewer can check by hand. Neither is exact in floating
point (each carries about 4e-15 of residue), so the fixture tests the tolerance
path rather than exact equality.

## Files

| File | Role |
| --- | --- |
| `course-method-notes.md` | Invented course material; ingested, then reviewed as controlling method evidence |
| `assignment.md` | The current assignment handed to `start` |
| `structured-assignment.json` | `assignment.json` filled in, for `match` |
| `course-profile.json` | Profile rules and rendering; the driver injects catalog-resolved evidence |
| `plan.json` | Requirements, deliverables, verification policy; the driver injects evidence and the profile hash |
| `solution.json` | The worked solution; fully static, contains no hashes |
| `run_workflow.py` | The driver |

## Why a driver instead of frozen JSON

Every hash in this framework binds to bytes produced at run time. Plan evidence
binds to the ingested source hash and to the per-block text hash; the course
profile hash is the digest of the *stored* profile, which gains a `course` key
on the way in, so it is not the digest of the file in this directory; the
verification report binds to the run's own checks and artifacts.

A fixture of static JSON with baked-in digests would only ever reproduce on the
machine that baked it, and it would test nothing except that a digest can be
copied. The driver recomputes each binding from the live run, so the example
exercises the binding rules themselves.

For the same reason the driver locates its citations by distinctive phrase
rather than by line number. Editing the prose in `course-method-notes.md` or
`assignment.md` cannot silently break the evidence chain; it fails loudly with
a `fixture drift` message naming the phrase it could no longer find.

## Ordering that matters

`render` must run before `verify`. Registering an artifact clears any recorded
verification report, and `render` records the solution, which clears the
calculation checks. Running `verify` first silently discards its own results.
`render` also records the solution itself, so a separate `record-solution` is
not needed in the happy path.
