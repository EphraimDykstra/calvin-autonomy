# Physics 133 Lab (introductory mechanics): read this before producing a deliverable

## What this pack can and cannot tell you

One lab handout survives (Lab 01, measurement and density). Its "What You'll Turn In" list is the only format rule an instructor stated. Three completed group reports (Labs 06-08) show what was turned in later in the term, but their handouts were not kept, so the pack cannot check their question numbering.

The lecture syllabus says the lab writing standards are in separate handouts, which are not in the archive. There are no graded returns, and who ran the lab section is not established. The completed reports contain unit errors (joules computed from grams) and uncertainties that break Lab 01's own rules, so they show structure only.

## Course policy

The lab has no syllabus of its own. The archived lecture syllabus covers collaboration and plagiarism but has no generative-AI statement (`course_policy.confidence: unknown`). Ask the student to confirm the current policy, and record the answer.

## The deliverable

A weekly group report, in groups of three, as a single PDF:

- A cover sheet with the names, the experiment title, and the date. Later reports used a title block instead, and the stated rule is a cover sheet.
- A captioned data table pasted from LoggerPro.
- Each requested graph filling most of a page, with data points, a best-fit line, and axis labels with units.
- Answers to the handout's numbered questions.
- Concluding remarks.

## The paired rule: PDF and LoggerPro file

The PDF and the LoggerPro file are submitted together, and **every group member submits both** each week even though they are identical. LoggerPro holds the manual columns, the uncertainty columns, the calculated columns, and the fits. The PDF shows the table, the graphs with their fits visible, and the answers. A slope quoted in an answer should be the slope on the graph, with the fit's uncertainty, converted to SI units.

## Uncertainty rules (stated in Lab 01)

- Uncertainty to **one significant digit**, and the value rounded to the same place.
- The uncertainty of a digital readout is half its last digit, unless reading it in practice is worse.
- Propagate by **max minus best**. For a quotient, push the numerator up and the denominator down.
- A negligible input uncertainty may be dropped from the propagation, but say that it was dropped.

## Methods

`pack.json` carries five methods with steps and pitfalls:

- `max-min-uncertainty`
- `slope-as-measured-quantity`, which prefers a linear fit and reads the intercept physically
- `video-analysis-kinematics`
- `conservation-check`, for momentum and energy in collisions
- `torque-equilibrium`

## When producing work for this lab

1. Get the week's handout. The question numbers are the structure, and only the student has them.
2. Put every quantitative answer in the form value ± uncertainty with units, and every comparison in the form "agree within uncertainty" or "do not agree".
3. Make the graphs full-page with their fits visible, and make sure they match the LoggerPro file.
4. Keep the concluding remarks specific and professional. Name one real error source instead of saying "human error".
