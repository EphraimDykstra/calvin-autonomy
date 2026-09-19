# ENGR 204 Lab: read this before producing a deliverable

ENGR 204 Lab is the sophomore circuits lab. It has three deliverable families, and they have different shapes. Identify which one the assignment is before writing anything.

| Family | Shape | Coverage |
| --- | --- | --- |
| Formal analog lab report | Title page, abstract page, outline-numbered sections, appendices as a separate PDF | High: department standards plus the instructor's own report template |
| Short-form report (op-amp and filter design labs) | Header block, requirements, filled comparison table, one graph, short analysis | Partial: two filled-in copies of what looks like the instructor's template; the blank is not in the archive |
| Weekly digital-logic worksheet | Fill-in handout | None: the answers were handwritten, with no text layer |

## Course policy

No syllabus was found, so no AI-use policy is known in either direction. `course_policy.confidence` is `unknown`. Ask the student to check with the instructor before graded work, and record the answer.

## Formal report conventions

These come from two instructor-side sources: the department report standards appended to the lab assignment, and the instructor's own blank report template, which gives guidance section by section. Where the two differ, the template is the more specific and the assignment outranks both. The rules differ from ENGR 319 in several ways that are easy to get backwards:

- **The abstract goes on its own page after the title page, or on the title page.** The template allows either, and its own page is the safer default. It is one short paragraph (the template allows up to two very short ones, 6-8 sentences at most), it summarizes the whole report and is not an introduction, it does not reference figures or tables, and it avoids detailed numbers.
- **The abstract page is page 1.** In 319 the title page is unnumbered and the body starts at page 1.
- **Double spacing**, at least 1-inch margins, and visible paragraph breaks.
- **Outline-numbered sections** up to three levels, built with Word heading styles. The template's order is Introduction and Goals, Experimental Procedure (equipment, setup, other verification methods), Experimental Results (recorded data, then analysis), Conclusion, Appendices. The authors may deviate if they have a reason. Every section opens with a lead paragraph, and a section with subsections has at least two.
- **Length:** the ceiling is roughly 8-10 written pages, and the best reports run about 5 pages of text.
- **Voice:** the department default is third person and past tense. The instructor template prefers active voice where it can be done without "I" or "we", and allows them as a last resort. Keep one tense per paragraph.
- **Captions and citation:** titles go above tables and below figures, numbered in the order cited, and a caption must stand alone ("Figure 3. Flow Tube Setup", not "Figure 3" or "Flow Tube Setup"). Cite every figure and table in the text before it appears. If a thing is not a table, call it a figure.
- **Procedure section:** it reports what happened and never tells the reader what to do. The equipment section is not a bare list; it says why each instrument was needed.
- **Data and equations:** show trends with graphs unless the data set is very small, and put large tables in an appendix. A small equation may sit in a sentence; one that changes the line spacing is centered and set off with white space.
- **Analysis:** say where error crept in, how significant it was, and whether a procedural change would remove it. Compare the models on more than accuracy, such as simplicity or cost.
- **Graphs:** no title inside the chart, measured data as markers only, models as unmarked lines, a log frequency axis for sweeps, limits fitted to the data, a legend, and legibility in grayscale.
- **Appendices:** raw and model data tables, simulation exports, and the source-resistance procedure, delivered as a separate PDF and referenced from the body.
- **Naming:** the full trademarked simulator name on first reference, then the short form, capitalized consistently. The report file follows the assignment's naming pattern.

## Method

The core analysis compares three sources of data: an Excel equation model (ideal and realistic), a PSpice simulation (ideal and realistic), and bench measurements. All of them use the **measured** component values and are overlaid on one log-frequency gain plot. The assignment names the comparisons to discuss, and each one gets its own paragraph. Supporting methods are the function-generator output-resistance measurement and the nominal, tolerance-range, and measured progression used in the design labs. `pack.json` has steps and pitfalls for each.

Common failure points: reading the input amplitude from the generator display instead of the scope, confusing peak with peak-to-peak, leaving nominal-value models in a final report that asks for measured values only, and reversed op-amp supply rails. Two errors seen in student submissions (observed practice, not course rules) are worth checking every time: a gain column headed V/V that holds dB, and tolerance-range rows that repeat the nominal gain instead of recomputing it from the extreme resistor ratio.

## Where coverage is thin

- The instructor template is a **format** source, so it settles the formal report's layout and prose rules. It says nothing about which circuits to model or how to derive a result, so methods stay partial.
- Only **one** completed formal report exists, and it is a student's own of unknown submission status. Its layout follows the template. Its prose is a complaint about the lab, so do not imitate its voice, and it is not used as a model of what a good discussion says.
- The short-form reports rest on two submissions whose register is informal and which contain errors. They appear to be filled-in copies of the instructor's short-form templates (their file metadata credits the instructor, and the filter report's table rows cite the assignment's step numbers), so their header, section labels, and table rows are probably instructor-specified. Nothing states which text was original, the blank templates are not in the archive, and their prose style should not be imitated.
- No syllabus, no returned grading, and no rubric text. The peer-review rubric is referred to in the lab assignment but is not in the archive.
- There are no tests. The lab has weekly worksheets and reports, so the pack carries no `exam_profile`. The PSpice homework and Quartus project files in the source folder are tool output with no prompts or answers.
