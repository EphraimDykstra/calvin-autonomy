# ENGR 204 (Circuit Analysis and Electronics, lecture): what this pack knows

## Known, from 11 instructor prompts

- Each homework prompt gives numbered problems, many with circuit figures, and ends with a list of selected final answers for most numeric problems.
- Every prompt states the same grading rule: credit is for an honest attempt, and because the answers are given, **work must be shown**. A bare answer earns nothing, even a correct one.
- Circuit-simulator (PSPICE) problems are handed in as printouts or screen captures, either the schematic with voltages or currents displayed or a plot captured from the print preview. Plots need a title, axis labels, and a legend. Several problems ask for comments comparing the simulated values with the hand results.

## Known, from the instructor's own worked keys

- The pack carries fourteen methods, one per technique the prompts set, each with its own `basis` saying whether a prompt **states** it or a key **shows** it. Fetch one with `pack get engr204 methods.<id>`.
- Eight rest on a prompt and a key together. Mesh analysis, transients, diodes and three-phase rest on the prompts alone: no surviving key covers them, and each of those four says so.
- The keys are camera scans of handwriting, read by eye. A misread of a handwritten mark is possible in a way it is not for extracted text.

## Unknown

- How a solution should be laid out on a homework page, whether it is handwritten or typed, and how it is submitted. No completed homework exists.
- Anything about the final in the instructor's own hand beyond the study guide. No final paper and no final key are in this course's folder.
- The course policy. There is no syllabus.

## What to tell the student

"I know how this course's homework is graded: show the method, because the final answers are already given. I know the techniques this course sets, and for most of them how your instructor's own worked solutions are laid out. I know the shape of your two in-class tests and what the study guide says about the final. I don't know how your instructor wants a homework page laid out. If you have a graded problem set, send it."

## Exam shape

The pack carries an `exam_profile` built from the Test 1 paper, both keys, and the instructor's final-exam study guide, opened under the student's explicit instruction for shape only. It records how many problems each in-class test had, the points per problem as marked, one topic label per problem, the header rules, what aids were allowed, and the form the instructor's keys take. It records no question, no number out of a problem, no figure and no answer, and the keys' class statistics are recorded as a fact with the numbers left out.

Use it to lay out what a test covers and to shape practice. Its `not_documented` list is the honest boundary: the Test 2 paper, the final's paper and key, an in-class time limit, the in-class calculator policy, the formula-sheet size, quiz format, and how partial credit was awarded. Say those are unknown rather than filling them in.

## Preparing a student for a test

These are host instructions, and they live here so a host reading this course's card finds them. They are written to move to a shared playbook once one exists; when that happens this section goes, so that nobody maintains two copies.

Fetch before advising. `pack get engr204 exam_profile` answers `over_budget` and lists its children, so ask for the ones the task needs — `exam_profile.assessments`, `.aids_provided`, `.question_shape`, `.stated_rules`, `.not_documented` — rather than raising the budget. Then `pack get engr204 methods.<id>` for each topic you will teach.

Lay out the ground first. Say what the test covers and how the points fall, from `assessments`, and what the study guide says in `instructor_remarks`. Then say what is **not** known, from `not_documented`: the in-class time limit, the calculator policy, the formula-sheet size, how partial credit fell. Name those as unknown instead of filling them with a plausible guess.

Teach in the course's own method. Each `methods.<id>` carries the steps, the pitfalls, and a `basis` saying whether a prompt stated it or an instructor's key showed it; four of them rest on prompts alone and say so. Give the chapter pointer in `reading` for what to study.

Write new problems when practice is wanted. Match the recorded shape: the problem count, one topic per slot from the recorded labels, the same relative weights, the same mix of forms in `question_shape`, the header rules restated as instructions. The labels say what a slot is about and deliberately do not describe any real problem, so build from the method and the chapter, not from the label's wording. Produce the worked key separately, in the form this course's keys take: technique named first, substitution shown, answer boxed with its unit.

Label it honestly, every time: this is modelled on the shape of past tests in this course, and the content and difficulty are the tool's own. Never say, imply or let the framing suggest that a problem came from, resembles or predicts a real one, and never reproduce or paraphrase a real question.

Check attempts through `review` in the ordinary way. The `magnitudes` bound on power factor flags an answer for a second look, not a verdict. Some mistakes the engine cannot see: an apparent power reported in watts is dimensionally fine and wrong, and that one lives in `methods.ac-power`'s pitfalls.

Policy first, though. This course's `course_policy` is `confidence: "unknown"` with no source found. Unknown is neither permission nor prohibition: say that nothing in the archive establishes this course's stance on tool-written practice, suggest the student ask their instructor, and leave the decision with them.

## Related

The lab is covered separately in `engr204-lab`. The lecture writing handout in this course's folder (audience, abstracts, graphing, conclusions) supports lab reports, not homework.

## Do not

- Hand over a final answer without the method. It earns no credit here and teaches nothing.
- Help with a live test or a take-home exam, and never reproduce or paraphrase a question from a real one. Practice generated from the recorded shape is allowed, and is labelled as the tool's own work, modelled on the shape of past tests in this course.
