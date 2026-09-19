# Exemplar: ENGR 315 Lab weekly report (shape only)

Derived from the report checklists in the first two lab handouts and the structure of two completed reports. All substance is replaced by placeholders or by an invented first-order RC system that is not a lab in this course. Section list follows the Lab 2 checklist; a lab whose handout asks for three sections drops Procedure.

---

## Header block (top of page 1, no separate title page)

```
ENGR 315 - Control Systems
Lab #[N]: [Lab title]
[Student Name]
[Instructor] · Calvin University
[date]
```

## Objectives

One paragraph, full sentences, no list. Say in your own words what the lab set out to understand and what the student had to produce. For example: the objective was to see how the time constant of a first-order circuit governs how fast it approaches its final value, and to produce the comparison from a single m-file whose figure reads in grayscale.

## Procedure

A sentence introducing the system, then its picture:

```
[system diagram]
Figure 1. [System name].
```

The governing equation, typeset, with every symbol defined in the sentence after it. Then two or three sentences on what the m-file does: which parameter it sweeps, how the cases are stored and looped, anything the formula needed (a boundary value, a `real()` wrapper) and why. Point to the code: "The m-file is listed in Appendix A."

## Results and Analysis

### Experiment 1: [what varies]

```
[figure produced by the m-file, unedited]
Figure 2. [What is plotted, for which cases].
```

Open by pointing at the figure ("Figure 2 shows ..."). Then one short paragraph per case, explaining the behavior through the physics and the math, each claim tied to the figure or a table.

```
Table 1. [What the table compares].
| [parameter] | [derived quantity] | [behavior] |
```

Check at least one number with a closed form against the plot, and say that it matched.

### Experiment 2: [what was added]

Same pattern: what was added to the figure, what it shows, why.

## Conclusion

State that the objectives were met or not, then answer each objective in the order the Objectives paragraph set them.

## Appendix A: MATLAB Code

The complete m-file as monospaced text, header filled in, File Name matching the uploaded file. The body refers to this appendix by name.

---

Page numbers at the bottom of every page. Figures and their captions centered, captions below; table captions above. "Figure" and "Table" capitalized in the text.
