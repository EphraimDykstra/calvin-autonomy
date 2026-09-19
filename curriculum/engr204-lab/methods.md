# ENGR 204 Lab: read this before producing a deliverable

ENGR 204 Lab is the sophomore circuits lab. It has three deliverable families, and they have different shapes. Identify which one the assignment is before writing anything.

| Family | Shape | Coverage |
| --- | --- | --- |
| Formal analog lab report | Title page, abstract page, outline-numbered sections, appendices as a separate PDF | High: department standards plus the instructor template's guidance |
| Short-form report (op-amp and filter design labs) | Header block, requirements, filled comparison table, one graph, short analysis | Partial: the instructor template it refers to is not in the archive |
| Weekly digital-logic worksheet | Fill-in handout | None: the answers were handwritten, with no text layer |

## Course policy

No syllabus was found, so no AI-use policy is known in either direction. `course_policy.confidence` is `unknown`. Ask the student to check with the instructor before graded work, and record the answer.

## Formal report conventions

These come from two instructor-side sources: the department report standards appended to the lab assignment, and the guidance text inside the instructor's report template. They differ from ENGR 319 in several ways that are easy to get backwards:

- **The abstract gets its own page**, after the title page. In 319 it goes on the title page. It is one paragraph, it does not reference figures or tables, and it avoids detailed numbers.
- **The abstract page is page 1.** In 319 the title page is unnumbered and the body starts at page 1.
- **Double spacing**, at least 1-inch margins, and visible paragraph breaks.
- **Outline-numbered sections** up to three levels, built with Word heading styles. The template's order is Introduction and Goals, Experimental Procedure, Experimental Results (recorded data, then analysis), Conclusion, Appendices. The authors may deviate if they have a reason.
- **Length:** the ceiling is roughly 8-10 written pages, and the best reports run about 5 pages of text.
- **Voice:** the department default is third person and past tense. The instructor template prefers active voice where it can be done without "I" or "we", and allows them as a last resort. Keep one tense per paragraph.
- **Captions:** titles go above tables and below figures, numbered sequentially and referenced by number.
- **Graphs:** no title inside the chart, measured data as markers only, models as unmarked lines, a log frequency axis for sweeps, limits fitted to the data, a legend, and legibility in grayscale.
- **Appendices:** raw and model data tables, simulation exports, and the source-resistance procedure, delivered as a separate PDF and referenced from the body.
- **Naming:** the full trademarked simulator name on first reference, then the short form, capitalized consistently. The report file follows the assignment's naming pattern.

## Method

The core analysis compares three sources of data: an Excel equation model (ideal and realistic), a PSpice simulation (ideal and realistic), and bench measurements. All of them use the **measured** component values and are overlaid on one log-frequency gain plot. The assignment names the comparisons to discuss, and each one gets its own paragraph. Supporting methods are the function-generator output-resistance measurement and the nominal, tolerance-range, and measured progression used in the design labs. `pack.json` has steps and pitfalls for each.

Common failure points: reading the input amplitude from the generator display instead of the scope, confusing peak with peak-to-peak, leaving nominal-value models in a final report that asks for measured values only, and reversed op-amp supply rails.

## Where coverage is thin

- Only **one** completed formal report exists. The template file in the archive with "template" in its name is a completed submission (the inventory flags this). What survives of the instructor's original template is the guidance text left inside it.
- The short-form reports rest on two submissions whose register is informal. Their layout is recorded as observed, not specified, and their prose style should not be imitated.
- No syllabus, no returned grading, and no rubric text. The peer-review rubric is referred to in the lab assignment but is not in the archive.
