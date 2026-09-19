# Exemplar: ENGR 319 lab technical memo (shape only)

Derived from the structure of completed 319 lab memos. All substance is replaced by placeholders. It teaches layout and argument order. It is not a draft.

---

## Title page (unnumbered, does not count toward the body)

```
[Experiment title]
[Student Name]
ENGR 319 [section] - [group, if applicable]
[Instructor]
[date]

Abstract
[One paragraph, 4-6 sentences.]
  - Objective: what quantity or behavior the experiment characterizes.
  - Method in a phrase: the measurement and the analysis technique (calibration, sweep, fit).
  - Result 1: [value, units] for the primary quantity.
  - Result 2: [value, units] for the secondary quantity, with the fit or selection criterion.
  - Comparison: how result 1 sits relative to a cited reference value or range [source].
```

## Body page 1

**Introduction and Methods** (about half a page of text, the rest figure and equations)

- One or two sentences giving the objective in engineering terms.
- One sentence on the apparatus that points to the schematic: "... shown in Figure 1."
- **Figure 1** placed right after its first reference: a digital apparatus schematic with every component labeled, including sensor locations and the distances or areas the analysis uses. Caption below: `Figure 1. [Apparatus description].`
- The governing relation, typeset and numbered at the right margin:

```
            [governing equation]                                [Equation 1]
```

- One sentence defining the symbols in Equation 1 that are not obvious.
- One sentence naming every processing decision the prompt did not dictate (offset correction, which data were averaged, how the fit parameter was chosen), with the reason for each.
- Further equations (2, 3, ...) appear only where their step of the analysis is described, never ahead of it.

## Body page 2

**Results and Analysis**

- **Figure 2**: measured data as markers and the model or fit as a single line, with axes labeled with units, no chart title, no grid, inward ticks. When the prompt requires a reference value on the graph, it appears there as a labeled line or band with its source.
- Two to four sentences that read the figure: the trend, the fitted or averaged value [value, units], and the scatter or uncertainty.
- **Table 1** only if the prompt asks for tabulated results per run. Caption above: `Table 1. [content].`
- Optional **Figure 3** to prove a selection, such as error against the fit parameter with the minimum marked. Otherwise it goes to the appendix and is referenced there.

**Conclusions**

- A short list, one conclusion per required analysis item in the prompt, each with its number and units.
- One sentence on the largest source of error and its direction.

The body ends at the bottom of page 2, not above it and not below it.

## Appendices

```
List of Appendices
  Appendix A - Raw data sheet (scan)
  Appendix B - Data reduction tables
  Appendix C - Supporting plots
```

- **A:** the scanned original hand-recorded data sheet. If none exists, say why in one sentence.
- **B:** digested tables of inputs, converted values, and intermediate results, with units in the headers and 2-3 significant digits.
- **C:** any supporting plots that did not fit in the body, each captioned.

Each appendix page carries its heading. No appendix page is a bare list of equations.
