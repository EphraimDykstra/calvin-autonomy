# Exemplar: ENGR 305 FEA report (shape only)

Derived from the structure of the instructor's model FEA report and one completed student report. Every value is a placeholder, and no geometry or load from the archive is reused. This describes the shape. It is not text to copy.

The FEA numbers and screenshots must come from the student's own simulation. This repo cannot run FEA.

---

## Title block (top of page 1, no separate title page)

```
[REPORT TITLE]
[What is compared with what]
[Student Name] | ENGR 305 | [date]
```

## Introduction

Two or three sentences: the loading cases studied, the two methods (hand calculation and FEA in [software]), and the aim of showing where they agree and why they differ.

## Procedure

How each model was built to match its hand-calculation assumptions: geometry simplified to the textbook shape, material properties ([E], [G], [Poisson's ratio]) from [source], the supports chosen to reproduce the hand boundary conditions, and how each load was applied.

## [N]. [Loading case, e.g. Axial load on a three-section bar]

- One sentence on the setup, and a figure only if words cannot describe the load or support clearly.
- The governing equation, where it is first used, e.g. total deflection as the sum of PL/(AE) over the sections.
- **Table N - [inputs for this case]** (caption above): Variable | Value | Units.
- **Figure N - [what the FEA plot shows]** (caption below): one FEA result that makes one point.
- **Table N+1 - [comparison]** (caption above):

| Quantity [units] | Hand calc | FEA | % difference |
|---|---|---|---|
| [quantity] | [value] | [value] | [value] |

- The difference explained: [which approximation, in which method], which makes the hand value [higher / lower]. If it is over about 5 percent, give the specific cause.

Repeat for torsional load, pressure vessel and stress concentration, and for any extra cases.

## Discussion

The most important section. Draw the cases into one lesson about using FEA, for example that boundary conditions decide the answer, that mesh quality governs stress risers, or that results near a load point cannot be trusted. Honest criticism of the software or of one's own modelling is acceptable.

## Conclusion

A short restatement of the introduction and the discussion, with one clause on how well the results agreed overall.

---

## The workbook behind it

One worksheet per case, holding the inputs table (derived values by formula), the comparison table (FEA values typed in from the study, percent difference by formula) and the screenshots. The report's tables are transcribed from these sheets. Check that every number matches the workbook before submitting.
