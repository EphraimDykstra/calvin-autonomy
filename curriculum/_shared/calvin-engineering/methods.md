# Calvin Engineering: what carries across courses

Read this when a student's course has no pack of its own, or when its pack says nothing about the point in front of you. A course pack wins over this file, and the student's own handout wins over both.

## First: if the word "memo" appears, find out which memo

At Calvin, "technical memo" names two different documents, and producing the wrong one looks completely correct.

- **Short-report memo** (ENGR 209 lab, ENGR 319, ENGR 328, one handout family): a title page carrying the abstract, then a body of about two pages (objective, methods, results, discussion, conclusions), then appendices.
- **Header memo** (ENGR 322): a To / From / CC / Date / Re block, then an executive summary of about a page that leads with the answer.

If the handout mentions a title page, an abstract or a page count, it is the first kind. If it mentions To/From or an executive summary addressed to someone, it is the second. If you cannot tell, ask. Do not default to the header form because the word is "memo".

## The honest summary

Less carries across courses than you might expect. What does carry is well supported.

Every course in the archive that had a written format spec overrode the department's default somewhere. The single most reliable cross-course rule is therefore procedural: **get the handout first.** Most students can answer the questions below in thirty seconds from their own assignment sheet, and every one of them is a point where Calvin courses genuinely disagree.

The evidence comes from one student's archive of about ten engineering courses. It contains no graded or annotated work, so it shows what instructors asked for, not what earned marks. When counting agreement, three shared sources are each counted once:

- **ENGR 319 and ENGR 328** share one writing-guidelines handout (only the header differs), and the ENGR 209 lab handout derives from an ENGR 319 document. That makes one thermo-fluids family, not three independent votes.
- **ENGR 305 and ENGR 322** share an instructor.
- A **department report standards** document was found appended to an ENGR 204 Lab handout. Its title says it is department-wide, and its content reads that way, but it has been seen in only one course. Treat it as the likely default, not as confirmed policy.

## Apply these unless the handout says otherwise

Each of these rests on at least 3 distinct instructors writing in documents of their own, and no course contradicted any of them. Counting treats ENGR 204 lecture and lab as one instructor, ENGR 305 and 322 as one, and the shared ENGR 319/328 guidelines as one document.

- **Captions.** Tables are captioned above, figures below. Each is numbered, cited by number in the text, and placed near where it is first discussed.
- **Units and precision.** Every number carries units: text, tables, axes and appendices. Significant figures match the measurement, so trim spreadsheet output before using it.
- **Graphs.** Label both axes with the quantity and its units. The graph must read in grayscale, so vary markers or line styles, not just colour.
- **Arc of the body.** Objective, then a brief method, then results, then analysis or discussion, then conclusions. Section names vary; the order does not.
- **Results versus discussion.** Results state what was found. Discussion explains why: surprises, where error came in and how much it matters, and how the models compare. The conclusion answers each objective rather than repeating results.
- **Appendices.** Raw data and at least one sample calculation go here, and every appendix is pointed to from the body. Anything needed to follow the argument stays in the body. Appendices are tidy, never raw dumps.
- **Title block.** A descriptive title, author(s), date, course and section, and the instructor. Use [Student Name] and [Instructor] unless the student gives you values for their private run.
- **Page setup.** Typed, 1-inch margins (stated by two instructors and the department standards; the others say only "reasonable"), pages numbered at the bottom and away from the staple corner. Never fit a page limit by shrinking fonts, margins or figures.

Medium confidence (fewer independent sources, or the details differ):

- **Not a diary.** Report what was done and found. No chronology or feelings, and no retelling of the lab manual as instructions. No course contradicts this, but only the department standards, ENGR 204 Lab and the thermo-fluids family state it.
- **Equations.** Type them, number them, and place them where they are used, explained in the sentence around them. Never collect them into an appendix list.
- **Computation.** Repetitive math belongs in a spreadsheet or tool. The appendix holds a readable version plus one hand-worked sample case, so a reader can check the tool.
- **Independent check.** Compare the result against something independent: a second model, a simulation against measurement, a hand calculation against FEA, or a balance that should close. Report the gap as a percent difference and explain its cause.
- **Diagrams.** Draw the apparatus as a clean digital schematic with the parts labelled. Photos go in an appendix, if anywhere.

## Do not add these

- **Formal uncertainty propagation** (± bounds, root-sum-square). No engineering handout in the archive asked for it. They ask for percent error or difference, an explanation, and sensible significant figures. Adding it sounds rigorous, but it costs space under a page limit and was not requested. Add it only if the assignment asks.
- **Thermo-fluids habits presented as Calvin rules.** These are good practice, but seen in only one handout family:
  - superscript units, never a caret
  - × rather than *
  - a leading zero on numbers below one
  - right-margin equation numbers
  - lettered appendices that open with a list of appendices
  - no title inside a captioned graph

  Using them elsewhere does no harm. Do not tell a student they are required.

## Where courses disagree: ask, do not average

| Point | Department default | Where it differs |
|---|---|---|
| Abstract | Its own page, one paragraph, no detailed numbers, no figure references | ENGR 209, 319, 328: on the title page, with key results as numbers and units |
| Voice | Third person, past tense; first person only if the instructor allows | ENGR 204 Lab: active voice, I/we as a last resort. ENGR 319/328: never I, we, you, "the team". ENGR 322's model summary uses I and we |
| Line spacing | Double | ENGR 319 memo spec: single is fine; its labs and ENGR 328: 1.5 |
| Page 1 | Not stated | ENGR 204 Lab: the abstract page. ENGR 319/328: the first body page, with the title page unnumbered |
| Handwritten equations | Allowed in ink | ENGR 209, 319, 328: no handwriting anywhere in the report |
| Title inside a graph | Not stated | ENGR 204, 319, 328: none, the caption is the title. The ENGR 315 MATLAB exercise asks for a plot title. That is an instruction for that plot, not a report rule |
| Length | 5 to 10 pages | About 2 body pages (ENGR 209, 319); per-stage budgets (ENGR 328); open-ended (ENGR 305 FEA) |
| Draft before final | Not stated | Peer-review copies (ENGR 204 Lab, 319); graded section pre-submissions (ENGR 328); none (ENGR 209, 315) |

## Questions to ask a student in an uncovered course

Ask them in one short list, and skip any the handout already answers.

1. Can you share the handout, rubric or format spec?
2. If it says memo: is it a title page with an abstract, or a To/From/Date/Re memo?
3. Where does the abstract go, and should it give numbers?
4. May you write "I" or "we"?
5. Is there a page limit, and does it count figures and the title page?
6. What line spacing, if the handout does not say?
7. Is there a draft or peer-review stage first?
8. Do the spreadsheet or code go in an appendix, or get submitted separately?

Then tell the student which rules you applied from this file, and that they are cross-course defaults, not their instructor's stated rules. Where a rule from here conflicts with their handout, the handout is right.

## Exemplars

These show shape only. Every value in them is an invented stand-in.

- `exemplars/department-default-report-shape.md`: a formal lab report under the department default.
- `exemplars/title-page-short-report-shape.md`: the thermo-fluids "technical memo", including an error-comparison table.
- `exemplars/executive-summary-memo-shape.md`: the header-style memo, with placeholders.
