# ENGR 204 Lab: guide

ENGR 204 Lab is the sophomore circuits lab. It has three deliverable families, and they have different shapes. Identify which one the assignment is before writing anything.

| Family | Shape | Coverage |
| --- | --- | --- |
| Formal analog lab report | Title page, abstract page, outline-numbered sections, appendices as a separate PDF | High: the Week 10 assignment with its Appendix A (department report standards) plus the instructor's report template |
| Short-form report (op-amp and filter design labs) | Header block, requirements, filled comparison table, one graph, short analysis | Partial: the assignments list the report contents; blank templates not found, so typography and layout are unspecified |
| Weekly digital-logic worksheet | Fill-in handout | Partial: each handout states what to hand in; page layout is the handout's own |

## Course policy

No syllabus was found, so no AI-use policy is known in either direction. `course_policy.confidence` is `unknown`. Ask the student to check with the instructor before graded work, and record the answer.

## Formal report conventions

The high rating on this page is for the formal report only. These rules come from two instructor sources: the Week 10 lab assignment, whose Appendix A is the Engineering Department Report Standards, and the instructor's report template, which gives guidance section by section. Where the two differ, the template is the more specific and the assignment outranks both. The template is a student-saved copy with no student content, so it is treated as the instructor's but cannot be shown identical to the original. A file named as the SP24 template in the term folder is a student's draft saved over it, and no rule here rests on it. The rules differ from ENGR 319 in several ways that are easy to get backwards:

- **The abstract goes on its own page after the title page, or on the title page.** The template allows either, and its own page is the safer default. It is one short paragraph (the template allows up to two very short ones, 6-8 sentences at most), it summarizes the whole report and is not an introduction, it does not reference figures or tables, and it avoids detailed numbers.
- **The abstract page is page 1.** In 319 the title page is unnumbered and the body starts at page 1.
- **Double spacing**, at least 1-inch margins, and visible paragraph breaks.
- **Outline-numbered sections** built with Word heading styles. The template's own sections use two levels; a third level appeared in a student's report, and neither source sets a limit. The template's order is Introduction and Goals (goals or objectives, then a second section whose title the author chooses), Experimental Procedure (equipment, setup, other verification methods), Experimental Results (recorded data, then analysis), Conclusion, Appendices. The authors may deviate if they have a reason. Every section opens with a lead paragraph, and a section with subsections has at least two.
- **Length:** the ceiling is roughly 8-10 written pages, and the best reports run about 5 pages of text.
- **Voice:** Appendix A says third person and past tense, with first person and active voice permitted in some situations, so check with the instructor. The template prefers active voice where it can be done without "I" or "we", and allows them as a last resort. Keep one tense per paragraph.
- **Captions and citation:** titles go above tables and below figures, numbered in the order cited, and a caption must stand alone ("Figure 3. Flow Tube Setup", not "Figure 3" or "Flow Tube Setup"). Cite every figure and table in the text before it appears. If a thing is not a table, call it a figure.
- **Procedure section:** it reports what happened and never tells the reader what to do. The equipment section is not a bare list; it says why each instrument was needed.
- **Data and equations:** show trends with graphs unless the data set is very small, and put large tables in an appendix. A small equation may sit in a sentence; one that changes the line spacing is centered and set off with white space.
- **Analysis:** say where error crept in, how significant it was, and whether a procedural change would remove it. Compare the models on more than accuracy, such as simplicity or cost.
- **Graphs:** no title inside the chart, measured data as markers only, models as unmarked lines, a log frequency axis for sweeps, limits fitted to the data, a legend, and legibility in grayscale. The Week 9 pre-lab turn-in is different: it asks for graphs with titles and legends, so the no-title rule is for the formal report.
- **Precision:** write so another student could duplicate the results, and name each quantity exactly, for example a voltage labeled with a polarity on the diagram (V_R1 measured with the oscilloscope probe), not "the voltage".
- **Appendices:** raw data, sample calculations, the Excel tables, simulation exports, and the complete source-resistance procedure, delivered as a separate PDF alongside the Word report and referenced from the body.
- **Naming:** the full trademarked simulator name on first reference, then the short form, capitalized consistently. The report file follows the assignment's naming pattern.

## Method

The core analysis compares three sources of data: an Excel equation model (ideal and realistic), a PSpice simulation (ideal and realistic), and bench measurements. All of them use the **measured** component values and are overlaid on one log-frequency gain plot. The assignment names the comparisons to discuss, and each one gets its own paragraph. Supporting methods are the function-generator output-resistance measurement and the nominal, tolerance-range, and measured progression used in the design labs. The pack's method nodes (`methods.<id>`) have steps and pitfalls for each.

Common failure points: reading the input amplitude from the generator display instead of the scope, confusing peak with peak-to-peak, leaving nominal-value models in a final report that asks for measured values only, and reversed op-amp supply rails. Two errors seen in student submissions (observed practice, not course rules) are worth checking every time: a gain column headed V/V that holds dB, and tolerance-range rows that repeat the nominal gain instead of recomputing it from the extreme resistor ratio.

## Where coverage is thin

- The template and the assignment are **format** sources. They settle the formal report's layout and prose rules and say nothing about which circuits to model or how to derive a result, so methods stay partial. The active-filter assignment does state the filter relations and the component tolerances, and those are recorded as the course's stated method; the component values of any one lab are not.
- Only **one** completed formal report was found, and it is a student's own, written as a complaint about the lab. A near-identical copy is named as the assignment prescribes, but nothing shows either was submitted or graded. Its layout follows the template. Do not imitate its voice, and do not use it as a model of what a good discussion says.
- The short-form reports: the assignments list the contents, and say a template with placeholders is on Moodle, but the blank templates were not found in the iCloud term folders or OneDrive, so typography and page layout are unspecified. The two student reports appear to be filled-in copies (their file metadata credits the instructor, and the filter report's table rows cite the assignment's step numbers). Nothing states which text was original, they are informal and contain errors, and their prose should not be imitated.
- The weekly worksheets: the printed handout text was read for what to hand in, and the students' handwritten answers were not. No problem content or values are recorded.
- No syllabus, no returned grading, and no rubric text were found. The peer-review rubric is referred to in the lab assignment and was not found.
- There are no tests for the lab, so the pack carries no exam profile. The PSpice homework and Quartus project files in the source folders are tool output with no prompts or answers.
