# Exemplar: ENGR 204 Lab formal report (shape only)

Derived from the instructor's report template and the Week 10 assignment with its Appendix A (the Engineering Department Report Standards). Where the template leaves a title or a choice to the author, the exemplar says so and does not borrow a student's wording. No student's report is a source for this shape. All substance is replaced by placeholders.

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

The template's fields are the title, author, date, course, instructor, and an experiment partner line. The section letter is not listed by the template or by Appendix A; it belongs here because the report file name carries it.

## Page 1: Abstract (own page, not section-numbered)

One short paragraph (the template allows up to two very short ones, 6-8 sentences at most), on its own page as here or on the title page. It summarizes the whole report and is not an introduction. It covers why the circuits were studied, which experiments were run (modeling, simulation, bench measurement), and what the comparison showed, stated qualitatively. It has no figure references and no detailed numbers.

## 1. Introduction and Goals

A lead paragraph that introduces the section and previews its subsections. The template says a section with subsections has at least two.

### 1.1 Goals or Objectives
The goals in two or three sentences, matching the assignment's stated goals.

### 1.2 [Second section title, chosen by the author]
The template leaves this title to the author. It holds what a peer with the same training needs to follow the analysis: the background theory, the transfer function or resonance condition with typeset equations, and diagrams of the system. The circuit diagrams pasted from the simulator are part of the body, as **Figure 1**, **Figure 2**, and so on, each captioned below and cited in the text before it appears. A short paragraph says how the realistic model differs from the ideal one and why that matters.

## 2. Experimental Procedure

A lead paragraph, then what was done, in past tense. It reports what happened so another student could repeat it, and it is not written as instructions.

### 2.1 Equipment Used
A short list or table of instruments and settings is fine, and a list table can replace a run of "the supply was set to X" sentences. It is followed by prose saying why each instrument was needed. A bare list is not enough.

### 2.2 Experimental Setup
How the circuit was wired and probed, the ground arrangement, any adjustment needed to get accurate measurements, and how the input amplitude was set once before connecting the circuit. A short description of how the source resistance was determined goes in the body, and the complete procedure goes in an appendix.

### 2.3 Other Verification Methods
The simulations and any other model checks, naming the tools (the simulator's full name on first mention, then its short name).

## 3. Experimental Results

A lead paragraph, then two subsections.

### 3.1 Recorded Data
All the data recorded: measured, theoretical, and simulated. Graphs show trends, and large tables go to an appendix with a reference in the text.
- **Figure 3** (caption below, cited in the text before the figure appears): gain against log frequency for the first circuit, with measured data as markers, the model traces as lines, and a legend. No title inside the graph.
- **Figure 4**: the same for the second circuit.
- A sentence per figure on what it shows, including any traces that overlap.

### 3.2 Data Analysis
One paragraph, at least, for each comparison the assignment lists for that lab. For the resonance lab they are:
1. Series against parallel circuit behavior.
2. Calculated against measured resonant frequency, [value, units] each.
3. Models against measurements.
4. Ideal against realistic model accuracy.
5. The two modeling methods, equation model against simulation.

Each paragraph names where error crept in, how significant it was, and whether a procedural change would remove it. The analysis also asks whether factors besides accuracy, such as simplicity or cost, should influence the choice of a model.

## 4. Conclusion

What was learned, tied to the goals in 1.1, with a suggestion for follow-up work.

## Appendices (separate PDF, referenced from the body)

Raw data and sample calculations, the Excel model and data tables (caption above each table), the simulation exports, and the complete source-resistance procedure. The template says to upload the appendices as a PDF alongside the Word report. The lettering and order are the author's choice, and each appendix is referred to from the body.
