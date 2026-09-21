# ENGR 322 (Machine Design): guide

## What this pack can and cannot tell you

The strongest evidence here is the **instructor's own model executive-summary memo**, written for one module homework with the answer left as placeholders. One student memo follows it closely. That is the grader showing what they want, and it pins down the memo format.

The rest is thinner. The module homework prompts are typed and readable, but most answers are handwritten on the printed prompt, so this pack cannot say how a worked solution should be laid out. Two completed lab handouts and one time-stepping set were read as page images. Their layout is recorded as the student's observed practice (`format.homework_presentation.observed_practice`), not as a rule, and none carries a grader mark. There is no syllabus, no rubric beyond one project handout, and no graded returns.

**Thin, on purpose:** the student's own module-numbered calculator workbook (a student tool, not an instructor document) has ten topic sheets (bolts, screw jacks, welds, fatigue, shafts, bearings, drive trains, hydraulics, springs, brakes and clutches), and this pack gives steps for only three of those topics (bolts, welds and screw jacks). The screw-jack steps come from the instructor's own module prompt and are thin: the prompt states the order of the asks, what it supplies and one warning, and no worked solution or class derivation survives. The fatigue module's prompt is only a problem list and two property tables, so nothing was derived from it. Do not fill the gap from a textbook and present it as this instructor's method. A file that looks like a 2025 final exam sits in the student's archive. It is not instructor material. The question is closed: nothing here is derived from it, and nothing ever should be.

The same instructor wrote the ENGR 305 FEA report template, so the hand-versus-FEA rule shared by the two packs comes from one source, not two.

## "Memo" means something different here

In ENGR 322 the prose deliverable is an **executive summary in memo form**: a To / From / CC / Date / Re header, then about five short paragraphs on one page. There is no title page, no abstract, no headings, no figures and no appendices.

That is a different document from the "technical memo" of ENGR 319 and 328, which has a title page carrying an abstract, a short body and appendices. The words collide twice: "memo" names both documents, and ENGR 328 calls the abstract block on its title page an "executive summary". A host that produces the other course's memo here will look completely correct and be wrong. Use the exemplar `exemplars.executive-summary-memo-shape`.

The header's recipient and CC are student-supplied. This repo never fills them from archived memos.

## Course policy

No syllabus was found, so the course's AI-use policy is unknown (`course_policy.confidence: unknown`). Ask the student to check it with the instructor, and record the answer.

## The executive summary, paragraph by paragraph

1. What was solved, by which methods, and the answer with its safety-factor basis.
2. How closely the methods agreed, as a percentage, and any FEA artefact (a spike at a corner or load point) and how it was handled.
3. The hand method, its approximation, and which way that biases the answer.
4. One short paragraph per secondary question in the prompt.
5. A closing sentence of confidence that restates the answer.

The memo reports work the student did. It never replaces it. If the FEA or the hand calculation has not been run, the memo cannot say the methods agreed.

## Methods

The pack's method nodes (`methods.<id>`) give steps and pitfalls for hand-versus-FEA reconciliation, weld groups treated as lines, eccentric bolt groups, bolt preload torque, screw-jack torque and efficiency, and explicit time stepping in a spreadsheet. Two habits the course visibly cares about:

- **Check the answer two ways.** Module prompts ask for hand and FEA solutions that agree well enough to be convincing, with the difference explained.
- **Build your own calculator, and do not trust an unchecked online one.** A fastener prompt warns about an online chart that was wrong. The student's test corrections trace a lost problem to trusting an online calculator over their own correct hand result.

## Checking a result

In a check-my-work session, compare the student's result against the pack's `magnitudes` node before building anything on it. Each range is physical plausibility, and its `basis` says so, or names the handout where one states a value. It is not a course rule. An out-of-range value is a question to ask, not a verdict: the `note` says what it usually means. Read the note for an in-range value too, because some slips land inside the range (lbf-in labelled lbf-ft is off by 12, which a wide range cannot always see).

## When producing work for this course

1. Get the module prompt. Answer every numbered question it asks.
2. For an executive summary, confirm the student has both the hand and FEA results, and the numbers to report, before drafting.
3. Keep it to one page, with every number in units.
4. For module homework itself, say plainly that the pack has no presentation format for it, and ask how the student's section turns work in.
