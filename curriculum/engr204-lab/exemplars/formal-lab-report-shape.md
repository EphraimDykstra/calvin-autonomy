# Exemplar: ENGR 204 Lab formal report (shape only)

Derived from the structure of a completed 204 Lab formal report and the instructor template's guidance. All substance is replaced by placeholders.

---

## Title page

```
[Report title]
[Student Name]
[date]
Engineering 204 Lab - Section [letter]
[Instructor]
Experiment Partner: [Partner Name]
```

## Page 1: Abstract (own page, not section-numbered)

One paragraph. It covers why the circuits were studied, which experiments were run (modeling, simulation, bench measurement), and what the comparison showed, stated qualitatively. It has no figure references and no detailed numbers.

## 1. Introduction and Goals

A short lead-in that previews subsections 1.1 and 1.2.

### 1.1 Goals and Objectives
The goals in two or three sentences, matching the assignment's stated goals.

### 1.2 Background and Context
Theory a peer with the same training needs: the transfer function or resonance condition, with typeset equations.

#### 1.2.1 [First circuit] schematics (ideal and realistic)
- **Figure 1** (caption below): the realistic circuit, including source resistance. The caption says what the realistic model adds.
- **Figure 2**: the ideal circuit.
- One paragraph on the difference between the two models and why it matters.

#### 1.2.2 [Second circuit] schematics (ideal and realistic)
The same pattern as 1.2.1, with Figures 3 and 4.

## 2. Experimental Procedure

What was done, in past tense. It is not written as instructions.

### 2.1 Equipment Used
A list table of instruments and settings, which replaces sentences like "the generator was set to ...".

### 2.2 Experimental Setup
How the circuit was wired and probed, the ground arrangement, and how the input amplitude was set once before connecting the circuit.

### 2.3 Other Verification Methods
The source-resistance determination in brief, pointing to the full procedure in an appendix.

## 3. Experimental Results

### 3.1 Recorded Data
- **Figure 5** (caption below): gain against log frequency for the first circuit, with measured data as markers and four model traces as lines, plus a legend.
- **Figure 6**: the same for the second circuit.
- One sentence per figure on what it shows, including any traces that overlap.

### 3.2 Data Analysis
One paragraph for each comparison the assignment lists:
1. [First circuit] against [second circuit] behavior.
2. Calculated against measured resonant or corner frequency, [value, units] each.
3. Models against measurement.
4. Ideal against realistic model accuracy.
5. Equation model against simulation.

Each paragraph names where error came in and whether a procedure change would reduce it.

## 4. Conclusion

What was learned, tied to the goals in 1.1, with one or two follow-up experiments.

## Appendices (separate PDF, referenced from the body)

- **A:** equation-model data tables (caption above each table).
- **B:** simulation export tables.
- **C:** measured values of the components used, and the measured sweep data.
- **D:** the source-resistance procedure.
