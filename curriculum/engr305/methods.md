# ENGR 305 (Mechanics of Materials): read this before producing a deliverable

## What this pack can and cannot tell you

**Well covered:** the FEA report. The instructor wrote a model report with placeholder values. It sets the sections, an agreement target of about 5 percent (or an explanation), a rough length, and a rule for when an image earns its place. The lab-exercise prompts survive too, as does one completed report with its workbook.

**Thin:** test-correction memos, with two instances and no prompt, and the cantilever beam lab, whose workbook survives but whose report is almost all images.

**Not covered:** chapter problem sets. All 13 are scanned handwriting with no text layer, and nothing about their format is inferred. There is no syllabus.

The instructor is the same as ENGR 322's. The hand-versus-FEA rule and the test-correction habit appear in both packs, but they come from one source, not two independent ones.

## Course policy

No syllabus was found, so the course's AI-use policy is unknown (`course_policy.confidence: unknown`). Ask the student to check it with the instructor, and record the answer.

## Report plus workbook: how the two relate

The brief for this pack asked this question directly, and the answer is that it depends on the assignment:

- **FEA report.** The workbook is the calculation of record. It has one sheet per exercise, holding an inputs table (Variable / Value / Units, derived values by formula), a comparison table (hand / FEA / percent difference, with the FEA values typed in from the simulation) and the screenshots. The report transcribes those tables as captioned Word tables and explains them.
- **Cantilever lab.** The pairing is reversed. The worksheet holds the trials, the averages, the FEA comparison, the chart and the typed answers to the six guiding questions. The report is mostly images.

So before drafting either file, ask which one carries the answers. Then check that every number in the report matches the workbook. The archive shows why: an input entered with the wrong exponent sign survived into the report because no formula used that cell, and a rounded value hard-coded into a formula quietly cut the link to its inputs.

## The FEA report

Structure: a title block (no title page), Introduction, Procedure, one section per loading case (axial, torsion, pressure vessel, stress concentration, plus optional extras), Discussion, Conclusion. See `exemplars/fea-report-shape.md`.

Each loading-case section gives the hand equation, a figure, a hand / FEA / percent table and the cause of the difference. The Discussion is the section the instructor weights most. It should draw the cases into one lesson, and honest criticism is acceptable. Tables are captioned above and figures below.

The FEA values and screenshots must come from the student's own model. This repo cannot run FEA, and a report must never claim an agreement that was not measured.

## Methods

`pack.json` covers hand-versus-FEA validation, stress and strain transformation (angle from x to n, counter-clockwise positive), axial deflection with indeterminate and thermal cases, carrying units, and stress concentration. The single most costly error in this archive is **a moment left in foot-pounds inside a psi calculation**, a factor of 12. Both test-correction memos trace lost points to it.

## Checking a result

In a check-my-work session, compare the student's result against `magnitudes` in `pack.json` before building anything on it. Each range is physical plausibility, and its `basis` says so, or names the handout where one states a value. It is not a course rule. An out-of-range value is a question to ask, not a verdict: the `note` says what it usually means. Read the note for an in-range value too, because some slips land inside the range (a moment left in ft-lb is off by 12, which a wide range cannot always see).

## When producing work for this course

1. Get the prompt, whether a lab exercise, the report or the test.
2. For an FEA report, collect the student's hand results, FEA results and screenshots first. Draft from those numbers only.
3. For a test-correction memo, write one section per missed problem naming the specific error and the specific change.
4. For chapter problem sets, say plainly that this pack has no format for them, and ask how the student's section turns homework in.
