# Exemplar: A/C lab section pre-submission (shape only)

- **id:** `ac-section-presubmission`
- **family:** `ac-lab`
- **stages:** `section-c-d`, `section-b-c`, `section-a-b`

This skeleton was paraphrased from the structure of real pre-submissions. **Every number below is invented for illustration.** Some are left as `[…]`, and the rest are deliberately round stand-ins. None come from a lab run, and none should be reused. The connective prose is new. Recompute everything from the student's own data.

---

## Title page (unnumbered)

> **Moist-Air Energy and Water Accounting Across the Reheat Section of a Laboratory Air-Conditioning Duct**
>
> [Student Name] · ENGR 328, Section [X] · [Instructor] · [Month Year]
>
> **Abstract.** *(2 sentences, method)* Independent energy and water balances were performed on section C-D for a winter and a summer case, comparing forcing terms from electrical measurements with the air stream's measured response. *(2-3 sentences, results with numbers)* The energy error was [−xx]% in winter and [−xx]% in summer. The water error was [x]% and [x]%, with no water forced in either case. The dominant error source is identified as […].

## Body (numbered from 1; 2-3 pages)

**Objective.** One or two sentences: what is balanced, over which control volume, and for which seasons.

**Methods.** A short paragraph on how the states were fixed (dry bulb, wet bulb, and measured atmospheric pressure) and how the dry-air flow was found. Equations appear inline where first used, numbered at the right margin:

- dry-air flow from the orifice correlation, with the exit-station specific volume (1)
- the section energy balance with the forcing terms on the left and the air response on the right (2)
- percent error with forcing in the denominator (3)
- inlet-normalised error for cases with no forcing (4), with its water analogue (5)

Figure 1 (caption **below**) is a schematic control volume for this section only. It shows every arrow used in the balance and no others. Caption pattern: *Figure 1. Control volume for section C-D: moist air enters at C, the electrical reheater adds heat, and the fan's power is counted as heat to the air.*

**Results.** One short paragraph per season, pointing to the table. Table caption goes **above**:

*Table 1. Section C-D forcing, response, and error for both seasons (illustrative values).*

| Quantity | Units | Winter | Summer |
|---|---|---|---|
| Heater power, V²/R | kW | 1.00 | 0.00 |
| Fan power | kW | 0.10 | 0.10 |
| Total energy forcing | kW | 1.10 | 0.10 |
| Air response, ṁₐ(h_D − h_C) | kW | 0.80 | 0.05 |
| Energy error | % | −27 | −50 |
| Water forced | kg/s | 0 | 0 |
| Water response, ṁₐ(ω_D − ω_C) | kg/s | 1×10⁻⁵ | −1×10⁻⁵ |
| Water error (inlet-normalised) | % | 0.5 | −0.2 |

**Conclusions.** Three to five sentences. Is each error the expected sign and size? What physically causes it (sampling at only two points in a non-uniform duct)? What would reduce it (a traverse with many measurement points)? No narration of the lab session.

## Attachments (optional reading)

- **Appendix:** the raw data sheet, a table of calculated station properties, and EES code with output for each season.
- The online key-data form is submitted separately.

---

## How the three pre-submissions differ

| Stage | New content beyond the C-D pattern | Error findings |
|---|---|---|
| C-D (first) | Sets up station states, dry-air flow, and the reheater balance | 4 |
| B-C | Refrigerant states 1-3 (gauge converted to absolute), state 4 from h₄ = h₃, evaporator heat as negative forcing, condensate mass and its enthalpy | 4 |
| A-B (last) | Steam-generator sub-model; summer analysed with **two** control volumes, compared against each other | 6 |

The EES file for each season is carried forward and extended at every stage, and earlier blocks are corrected when a later stage exposes a mistake.
