# ENGR 319: read this before producing a deliverable

ENGR 319 is the junior thermal-fluids course that comes directly before ENGR 328. It shares that course's textbook family (Cengel) and its heat-transfer reference. The deliverable conventions, however, are **not** the ENGR 328 conventions. Do not carry a 328 report shape into 319 work.

## Course policy comes first

The archived syllabus for Fall 2025 included a generative-AI policy. Syllabi have since been revised, and the current terms are unknown. Before doing any graded work for this course, show the student `course_policy` from `pack.json` and ask them to get an answer from the professor that is specific to the assignment in front of them. When they have one, record it in `professor_answer`. Until then, treat the policy as unknown, not as permissive.

## What the deliverable is

Every graded write-up is a **technical memo**. The professor's written memo spec and the lab prompts define it. The lab prompt outranks the general spec where they differ, and they differ in two places. The spec allows 1 to 2 pages of text; the lab prompts require exactly two. The spec accepts single spacing; the lab guidelines state a preference for 1.5.

The shape:

- An unnumbered title page carrying the title, author, course and section, group if any, the professor, the date, **and the abstract**. It does not count toward the page limit.
- A body of exactly two full pages for labs. Figures inside it count toward the two pages. Page 1 is the first body page, and page numbers are centered at the bottom.
- 1 to 5 figures or tables carrying the results. Figure captions go below and table captions above, both centered, formatted as `Figure N. Title.` and `Table N. Title.`. They are numbered in order of first reference and placed where they are first referenced.
- Lettered appendices, opening with a list of appendices, with a heading on each page. They hold the scanned raw data sheet, the detailed calculations, and supporting plots, all in digested form.

Equations are typeset in Word's equation editor. They are numbered at the right margin and appear where they are used, each followed by a sentence explaining it. The spec does not fix the label form. The professor's handouts use `(N)`, and one completed memo used `[Equation N]`. Pick one form and use it throughout. Never collect equations into an appendix list.

Graphs follow the spec's minimal-ink rules: no grid lines, inward ticks, 1-2-5 axis steps, labels large enough to read when projected, and no chart title when the figure has a caption. Measured data are drawn as markers.

Writing is third person and concise. Leave out narration of what the group did while standing at the bench, and leave out the explanation of unit conversions. Typesetting details are graded: real superscripts, `×` or `·` for multiplication, a leading zero on decimals, Greek glyphs, and sensible significant digits even in the appendices.

## Tooling: two different rules

- **Labs: Excel for the math, Word for the memo.** The lab guidelines tell students not to do hand calculations and to put the repetitive math in a spreadsheet.
- **Computer problems: EES preferred.** The second computer-problem prompt names EES as the preferred tool and accepts Mathcad, MATLAB, or Excel. It requires one property source throughout: either the tool's built-in property functions or the textbook tables, never mixed. The commented computations go in an appendix. The completed computer problems in the archive used Excel with textbook tables, which is allowed. The first computer-problem prompt is an image-only scan, so its rules are assumed to match and are not confirmed.

Encoding "319 is Excel-only" would be wrong. On computer problems it would push a student against the professor's stated preference.

## Methods

The core method is the classical **state-point / property-table** analysis. Number the states, fix each one with two properties, read or interpolate from the tables, apply the isentropic efficiency through the 2s state, then run the device-by-device energy balances with units on every line. Labs add spreadsheet data reduction: gauge zero offsets, a unit-consistent conversion column, and one formula filled across all points. They also add two recurring analysis patterns:

- **Calibration as a slope.** Plot measured against ideal and fit through the origin. The slope is the single constant.
- **Parameter sweep.** Sweep one model parameter, compute the sum of squared error over every data point (or the cost, for a design), and prove the choice with a graph.

`pack.json` lists steps and pitfalls for each method. The pitfalls come from real failure modes. Two to watch for:

1. A single mis-converted input, such as room temperature in the wrong absolute unit, propagates into every result and leaves no internal inconsistency to reveal it. Check each converted input against an independent conversion.
2. When the prompt asks for a handbook or reference value on a graph, it has to be on the graph itself, with its source. A vague comparison to "online values" in the text does not meet that requirement. If the course text does not tabulate the exact surface condition, report the bracketing range and say so. Do not substitute a value for a different finish.

## Where coverage is thin

- **Homework:** only prompts with bare answers survive. How solutions should be presented is unknown beyond "units on every answer."
- **Exams and equation sheets:** image-only scans, not read.
- **Grading intent:** there are no instructor-annotated returns. The peer-review checklist in the first lab prompt is the closest thing to a rubric.
- **First computer problem:** the prompt is a scan, as noted under tooling.

Exemplars in `exemplars/` show structure only, with placeholder tokens where the substance goes.
