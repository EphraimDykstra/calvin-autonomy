# Exemplar: ENGR 319 group computer problem (shape only)

Derived from the structure of completed 319 computer-problem reports. All substance is replaced by placeholders.

---

## Title page (unnumbered)

```
[Computer problem title]
[Student Name], [Student Name], [Student Name]
ENGR 319 - Group [N]
[Instructor]
[date]

Abstract
[3-4 sentences: the design goal and constraint, the method (tool plus sweep or
optimizer), the recommended design values [value, units], and the resulting
objective [value, units].]
```

## Body (short, usually 1-2 pages)

**Introduction and Methods**

- The requirement being met, stated as a constraint, such as "[quantity] between [lower] and [upper] at all times" or "minimum life-cycle cost."
- The tool, and the single property source used. Say explicitly whether that is the tool's built-in property functions or the textbook tables. The prompt forbids mixing them.
- The state-point logic, for a cycle: which states share a pressure, which process links each pair, and where the isentropic efficiency enters.
- How the search was run: which variables were swept, over what range, and how the optimum was recognized.

**Results and Analysis**

- **Table 1** (caption above): one row per design iteration. Columns hold what changed in that trial, the constraint check, and the objective. This table shows the reasoning path, not just the answer.
- **Table 2** (cycle problems, caption above): state-point properties T, P, v, h, s per state, with units.
- **Figure 1** (caption below): the objective plotted against the design variable(s), with the chosen point marked so the optimum can be read off the graph.
- Two to three sentences justifying the recommendation and noting any constraint that is active at the optimum.

## Appendices

- The commented, documented computations: the equation set with symbols defined, the initial hand estimate, the first computer model, and the final design. The prompt requires these to be in an appendix.
- A T-s or P-h diagram with the numbered states, for cycle problems.
- Cost or energy-balance breakdown tables.

Equations in the appendix are typeset and numbered, and each has a one-line statement of what it computes.
