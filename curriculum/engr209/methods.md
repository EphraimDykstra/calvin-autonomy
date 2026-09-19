# ENGR 209 (Material Balances and Fluid Mechanics): read this before producing a deliverable

## What this pack can and cannot tell you

Both graded deliverable families have a readable instructor prompt with explicit format rules: the fluid-flow lab handout, and the plant material-balance design project prompt. Those prompts are the rules here. Each family also has exactly one completed group submission, and both depart from their prompts in ways a student would lose credit for, so they contribute structure only.

The archive is missing three things:

- The **Technical Memo instructions** the lab handout points to on Moodle. Ask the student for them, and follow them over this pack where they differ.
- A **syllabus**, so the course policy is unknown.
- Any **homework** prompt or solution.

Exams are individual assessed work and are deliberately left out.

## Course policy

No syllabus was found (`course_policy.confidence: unknown`). Ask the student to confirm the current AI-use policy with the instructors, and record the answer. The take-home exam instructions require entirely individual work. Do not help with an exam.

## The two deliverables

**Lab technical memo** (one per team of 3-4):

- A title page with the team members, section, group, tube, and lab date and time, and an abstract that gives the key result as a number.
- A body of at most two pages, under the headings Introduction/Background, Method and Equipment, Data/Results, Analysis/Discussion, and Conclusions. No handwriting in it.
- Figures with units, axis labels, and captions.
- Everything else in appendices, including the scanned raw data sheet recorded in ink.
- Written for a supervisor making a decision. It is not a diary.

**Design project report** (an assigned group of 3):

- It recommends an operating procedure.
- Results are shown as graphs and tables.
- The appendix must contain the spreadsheet or program and a hand calculation of one representative case.
- Only substantial contributors are listed as authors, and every number has appropriate significant figures.

## The paired rule: spreadsheet, hand calculation, report

Students get this wrong most often, and the archived submission got it wrong. The prompt makes three artifacts carry the design project:

1. **The spreadsheet** computes every case over the full operating period.
2. **The hand calculation** solves one representative case from the flow diagram, with units, to prove the spreadsheet is written correctly. It goes in the appendix as clean work, not photos of scratch attempts.
3. **The report** presents the recommendation and the graphs and tables from the spreadsheet.

The hand-calculated case must match the spreadsheet's row for the same case, and the spreadsheet itself goes in the appendix. A link to an online sheet does not satisfy the prompt.

In the lab memo the relationship is lighter. The spreadsheet's digested calculation table goes in an appendix, and the body carries only the result and its graph.

## Methods

`pack.json` carries four methods with steps and pitfalls:

- `material-balance-dof`: labeled flow diagram, basis, degree-of-freedom analysis, solution order, and a sanity check. The take-home grading scheme scores each of these as its own step.
- `reactor-recycle-economics`: fractional conversion, recycle closure, and converting streams into the units their prices use.
- `schedule-optimization-sweep`: a decaying parameter, a costly reset with downtime, and a sweep of the schedule rather than an assumed one.
- `pitot-orifice-calibration`: baseline subtraction, density at the tube conditions, and the calibration factor as a slope. It matches ENGR 319's `calibration-as-slope` method.

## Checking a result

In a check-my-work session, compare the student's result against `magnitudes` in `pack.json` before building anything on it. Each range is physical plausibility, and its `basis` says so, or names the handout where one states a value. It is not a course rule. An out-of-range value is a question to ask, not a verdict: the `note` says what it usually means. Read the note for an in-range value too, because some slips land inside the range (standard sea-level air density used instead of the tube conditions).

## When producing work for this course

1. Get the prompt or handout, and the Moodle Technical Memo instructions if the student has them.
2. For the design project, build the spreadsheet, then do the hand case, then write the report, and check that the hand case matches.
3. For the memo, fit the result into two pages with a title-page abstract, and put everything else in appendices.
4. Never state a result that the spreadsheet or the hand calculation does not produce.
