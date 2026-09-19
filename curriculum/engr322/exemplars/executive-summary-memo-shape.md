# Exemplar: ENGR 322 executive-summary memo (shape only)

Derived from the structure of the course's model executive summary and one student memo that follows it. Every value is a placeholder, and the example assignment is invented. This describes the shape. It is not a template to fill in word for word.

This is **not** the title-page-and-abstract technical memo used in ENGR 319 and 328, and not ENGR 328's "executive summary", which is the abstract block on a title page. It has no title page, no abstract, no headings, no figures and no appendices.

---

```
To:     [Recipient]
From:   [Student Name]
CC:     [CC]
Date:   [Date]
Re:     Executive summary of [assignment name]
```

**Paragraph 1: the result.** Opens with the recommended value of the design variable, with units and the basis of its safety factor (yield, electrode allowable, proof load). Names both methods used to reach it in the same breath. A reader who stops here has the answer.

**Paragraph 2: agreement.** Gives the difference between the two methods as a number. If the FEA showed artefacts (single-node spikes at a sharp corner, a weld root or a load point), names them, says they are a modelling artefact, and says what was read instead.

**Paragraph 3: the hand method and its bias.** Names the hand method (for a weld, the group treated as a line) and the simplification it makes. States which direction that simplification moves the computed stress, and whether that errs on the safe side.

**Paragraph 4 (one per secondary question).** Answers each extra question from the prompt in two or three sentences: the answer first, then the reason.

**Closing.** One sentence tying the recommendation to the agreement between methods.

---

## Checks before handing it in

- It fits on one page.
- Every number has units, and the percentage agreement is stated, not implied.
- The FEA and the hand calculation were both actually run by the student. The memo reports them and does not replace them.
- Every question the prompt asks is answered somewhere in the memo.
