# Exemplar: ENGR 205 lab report sheet with workbook (shape only)

This comes from the structure of the report-sheet handouts and one completed sheet (one answer on it is pasted chatbot output and is not used), with every piece of substance replaced by a placeholder. The polymers handout says answers may be typed directly into the document. The concrete 2 handout is silent on typing and its one handed-in copy is handwritten on the printed page, so follow the handout in hand. The questions themselves come from the handout for that week. This shows how to answer in place and how the sheet relates to the workbook. It does not show what the answers are. See `methods.md`.

---

## The Word report sheet

```
[Report sheet title from the handout]
[Student Name]        Group: [group number]        [date]
```

**PART 1: [Part title from the handout]**

**1.** [Question text stays as the handout gives it.]

[Answer directly under the question: one or two sentences, or the selected option with a one-line reason.]

**2.** [Question asking for an equation.]

[Equation typed with the equation editor, symbols defined in one line, units stated.]

**Table 1.** [Descriptive title naming the specimens and what was measured.]

| Specimen | [Quantity] ([units]) | [Quantity] ([units]) | Observed behavior |
| --- | --- | --- | --- |
| [specimen] | [value] | [value] | [short description] |

**PART 3: [Part title]**

**7.** What is the approximate [property]? (Show/describe how this was determined.)

[value] [units]. [One sentence naming the method, for example the slope of the linear region between two stated strains, or the 0.2% offset intersection. The number is the one computed in workbook cell [sheet!cell].]

*[Figure inserted here, rebuilt from the workbook chart and not printed from Excel.]*

**Figure 1.** [Descriptive title: the material, the test, and the conditions.]

- Axes: [quantity] ([units]) on each, with no chart title inside the plot area.
- Markers for measured points. A legend when there is more than one series.

**8.** [Trend or acceptance question.]

[State the relevant statistic or criterion ([statistic] = [value] [units] against [criterion]), then the conclusion, then one sentence of reasoning.]

---

## The Excel workbook (uploaded separately)

| Sheet | Holds |
| --- | --- |
| `Data` | The raw data exactly as supplied, with the column headers carrying units. |
| `Specimen` | The measured dimensions and the area formula. Every stress column refers to this cell and does not retype it. |
| `Reduction` | Formula columns (stress, strain, strength) filled down, and summary cells for each reported property. |
| `Charts` | The source chart for each report figure. |

Before submitting, check that every number in the Word sheet traces to one of these summary cells, in the same units.
