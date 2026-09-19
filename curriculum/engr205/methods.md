# ENGR 205 (Principles of Materials Science): read this before producing a deliverable

## What this pack can and cannot tell you

The rules here come from lab handouts and report sheets, one completed report sheet, one free-form write-up, one presentation deck, the course schedule, and two lab workbooks. No syllabus survives. The report sheets refer students to "Lab Manual appendices" for how to label figures and tables, and those appendices are not in the archive. Every labeling rule below is therefore either something a report sheet asks for directly or an inference, and `pack.json` says which. There is no graded return anywhere.

The completed work is not a model. The one completed sheet reports some values without units and some loads where strengths were asked for. The free-form write-up is informal and first person. Use them for structure only.

## Course policy

No syllabus was found, so the course's AI-use policy is unknown (`course_policy.confidence: unknown`). Ask the student to confirm it with the instructor, and record the answer.

## The deliverables

ENGR 205 labs do not use one report format. Identify which of these the student has:

1. **Report sheet plus workbook** (polymers, concrete 2). The handout is a Word worksheet. The student answers each numbered question in place, inserts the tables and figures on the hand-in list, and uploads the Excel workbook separately. Some labs also want the printed sheet stapled.
2. **Short tensile-test write-up** (metals). No prompt survives. One submission had a title block, a method section, a results discussion, a property table, and an appendix of stress-strain figures.
3. **Recorded presentation** (societal and environmental issues). An individual voice-over deck of about 6-10 slides. The handout's topic list is the grading rubric.

## The paired rule: workbook and report sheet

Students most often get this wrong. The workbook and the Word sheet are one submission in two files, and they have different jobs:

- **The workbook computes.** Raw data as supplied, the specimen dimensions in one place, formula columns filled down, and a summary cell for each reported property. Nothing is typed in as a finished number.
- **The report sheet presents.** Each chart and table the hand-in list names is rebuilt in Word as a numbered, captioned figure or table with units. The concrete sheet explicitly says not to print from Excel.
- **They must agree.** Every value in the sheet traces to a workbook cell, in the same units. When a question says "show/describe how this was determined", the answer gives the value, its units, and the method in one sentence.

## Methods

`pack.json` carries three methods with steps and pitfalls:

- `tensile-test-reduction`: engineering stress-strain, modulus from the slope, 0.2% offset yield, tensile strength, ductility, and resilience and toughness by the trapezoid rule.
- `polymer-stress-relaxation`: relaxation modulus from a held-strain force decay.
- `concrete-strength-statistics`: cylinder strength from fracture force, summary statistics, histograms, trend plots, and acceptance against a specified strength.

The two errors seen in the archive's own workbooks are worth checking every time:

- The toughness range stops where the resilience range does, so the two come out equal. Toughness has to integrate to fracture.
- One area formula is applied to data sets taken on different cylinder sizes, or air content is entered as a fraction in some rows and a percent in others.

## Checking a result

In a check-my-work session, compare the student's result against `magnitudes` in `pack.json` before building anything on it. Each range is physical plausibility, and its `basis` says so, or names the handout where one states a value. It is not a course rule. An out-of-range value is a question to ask, not a verdict: the `note` says what it usually means. Read the note for an in-range value too, because some slips land inside the range (a peak force that happens to look like a strength).

## When producing work for this course

1. Get the handout for the specific lab. The question numbering and the hand-in list are the whole structure.
2. Build the workbook first. Then answer the sheet from its summary cells.
3. Number and caption every figure and table, and put units on every axis and column.
4. For the presentation, cover every rubric topic on the handout, cite sources, and remember that the student records the narration.
5. Homework and ZyBook work are not covered. Say so if asked.
