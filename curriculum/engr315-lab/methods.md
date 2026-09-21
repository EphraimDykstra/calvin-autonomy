# ENGR 315 Lab (Control Systems Laboratory)

This is for the host model. It covers the weekly lab report and the methods the first two labs teach. The pack's rule nodes hold the same rules in structured form, each with a `basis`. The MATLAB conventions (script header, file naming, plotting for grayscale, checks before the screenshot) are in the shared MATLAB pack (`tool:matlab`) and apply to every lab here. Use both packs.

**Evidence.** The Lab 1 and Lab 2 handouts, each ending in a report checklist, and a completed report for each. That covers two weeks of a semester. There is no Week 3 folder and no Week 3 handout. One loose Week 3 file exists, a hand-algebra draft (see section 6). No syllabus was found, so the AI-use policy is unknown. Both handouts require each student to write and run their own m-files.

## 1. How a lab runs

1. Read the textbook sections the handout names (Dorf and Bishop, *Modern Control Systems*).
2. Write and run the m-file in lab, individually. Discussion is allowed; running a classmate's file is plagiarism.
3. Write the report in Word from the saved files.
4. Upload the report and, separately, every m-file before the next lab starts. Lab 1 states a 20% penalty for m-files that are not uploaded.

## 2. The report

The handout's checklist is the specification. Read the current one before anything below.

- **Header block, no title page:** course line, `Lab #[N]: [title]`, `[Student Name]`, `[Instructor] · Calvin University`, date. Observed practice, not a stated rule.
- **Sections:** Lab 1 asks for Objectives, Results & Analysis, Conclusion. Lab 2 adds Procedure. Use the current handout's list; do not merge them.
- **Objectives:** one rephrased paragraph, full sentences, no bullets or numbers. Copying the handout's objectives is called out in both checklists.
- **Procedure (Lab 2 on):** the system picture, the equation that characterizes it, what the m-file does, and a pointer to the code appendix.
- **Results & Analysis:** one subsection per experiment. Lab 1's numbered questions are restated and answered under their experiment. The analysis explains why, with the physics and the poles, and cites figures and tables for support.
- **Conclusion:** answers the objectives.
- **Figures:** caption below, `Figure N. ...`, figure and caption centered, capital F in the text. The plot also carries its own title inside the graph, which the Lab 2 handout asks for. Other courses' report standards (ENGR 204 Lab, ENGR 319, ENGR 328) forbid an in-graph title on a captioned figure. That is a real difference between courses; follow ENGR 315's rule here and theirs there.
- **Tables:** caption above, `Table N. ...`, capital T in the text.
- **Page numbers** at the bottom.
- **Code** in the report, in the body or an appendix the procedure refers to.
- **Not specified anywhere:** font, margins, spacing, references, title page. Do not invent requirements for them.

See the exemplar `exemplars.lab-report-shape`.

## 3. Where the written guidelines and the submitted Lab 2 report differ

The Lab 2 guidelines and the report submitted for them were compared item by item. Most items match. These do not, or the guidelines are ambiguous:

| Item | Guidelines | Submitted report | What to do |
|---|---|---|---|
| File name | "include the student initials" | surname and given name run together, `[StudentName]_Lab2_Report` | Follow the current handout. Lab 1 and the m-file template ask for the name, so the rule has drifted. Ask the student which form their section uses. |
| Grayscale | every plot looks different in black and white | the envelope overlay was red dotted, the same style as the black dotted overdamped curve | Give every overlay a style no other curve uses (shared MATLAB pack, section 4). |
| Legend | example text mentions a legend "showing three cases" | four cases plus the envelope | The handout's own figure has four cases; name every trace. |
| Axis labels | example `Time[sec]`, `Response y(t)` | `time (s)`, `displacement (mm)` | Either form carries quantity and unit. The handout's reference figure itself uses the second form. |
| Table caption | captions left-aligned on top; separately, figures, tables and captions centered | table centered, caption left-aligned | Center the table, left-align its caption. |
| Time span | a hint vector running to 50 s | computed to 50 s, displayed to 5 s with `xlim` | Fine: compute long, show the part that matters, set in code. |

Items that match: four sections, objectives as a rephrased paragraph, the system picture and equation in Procedure, code in an appendix referred to from Procedure, one `for` loop and one plot call, Greek letters in TeX, no figure touch-ups, captions under figures, capital F and T, page numbers at the bottom.

## 4. Lab 1 against its report

Lab 1's checklist asked for three sections and the report used three. It asked for m-files in the report and the report showed each script as a screenshot beside its plot. Its Experiment 9 asks the student to confirm in writing that they read the report instructions; the report did. The report itself matched its checklist. The m-files did not fully match the template: one kept the template's unfilled Author and File Name placeholder lines, and another carried a File Name line copied from the previous experiment. The shared MATLAB pack's `header_block` rule (File Name must match the saved file) exists because of this.

## 5. Methods

### Second-order response across damping regimes (Lab 2)

- Force balance on the mass gives the ODE in M, b, k. The response is written through the natural frequency and the damping ratio, both functions of M, b, k.
- The handout fixes the regimes: undamped, underdamped, critically damped, overdamped. The closed form divides by sqrt(1 - zeta^2), so "critical" is evaluated just below 1, as the handout directs, and the report says why.
- Tie every regime to its poles. The real part sets the decay, the imaginary part sets oscillation. An underdamped envelope is a picture of the real part.
- The overdamped response is slower than the critically damped one, because one pole moves toward the origin. That is a result to explain, not a bug to fix.
- Check a number against a closed form: the ratio of successive extrema, or the initial value in every case.
- Choose the underdamped value below 0.5. The handout says that is what lets the damping show.
- The handout also says to compare the behavior of different values in the underdamped and overdamped cases, while the plot needs only one value each. Make the comparison in the analysis with computed values for a second zeta in each regime, or ask the student whether more traces are wanted. The archived report compared a second underdamped value in one sentence and no second overdamped value. With no graded copy, whether that met the instructor's expectation is unknown.
- MATLAB traps (complex branch past zeta = 1, `real()` over the whole expression) are in the shared MATLAB pack, section 3.

**What the student brings back from the run.** Nothing here runs MATLAB, so ask for three things: y(0) for each zeta (every one must be 1, an identity of the handout's equation; the handout does not ask for it, but it is the quickest way to catch a sign-flipped overdamped curve), the figure exactly as the script draws it, and every number the analysis will quote. Do not put a number in the report that the run did not produce.

**Checking a result.** The pack carries two `magnitudes` for this lab, both derived from the handout's own equation and neither a course rule: y(0) divided by y0, and the ratio of successive extrema for an underdamped zeta below 0.5. An out-of-range value is a question to ask, not a verdict. The `note` says what it usually means.

### Supporting mathematics (Lab 1)

Partial fractions, quadratic roots in `-a ± bj` form, block reduction to one polynomial over one polynomial (the transfer function), complex numbers as vectors and in polar form, and convergence of decaying exponentials. `roots` needs an explicit 0 for every missing power.

### Block-diagram reduction and step response (provisional, Week 3 draft)

The only evidence is one loose Week 3 draft that is not known to have been submitted. No handout for that lab was found, so this is observed practice, not a requirement. Read the lab's own handout first.

- Define the transfer function as output over input, `T = Y/R`, so that `Y = T R`.
- Reduce the loop symbolically first. For negative feedback the closed-loop transfer function is the forward-path product over one plus the loop product. Name every block before substituting numbers, and check the sign at the summing junction.
- Substitute the numeric blocks only after the symbolic result is written, then clear the inner denominators by multiplying numerator and denominator by their common denominator, until `T` is one polynomial over one polynomial.
- Spot-check by evaluating the unreduced and the reduced `T` at one test value of `s` that makes no denominator zero. They must agree. This is this pack's recommendation, not something the draft did.
- For a step of size `A` the input is `R(s) = A/s`. Multiply `T` by it; the step adds a pole at the origin.
- One slip to watch for: turning `1/(1 + a)` into `1 + 1/a` when simplifying a complex fraction. They are not equal. The draft's numeric reduction did this, and the spot check catches it.
- If the handout asks for a plot or a toolbox result, the student runs MATLAB and brings the numbers back. Nothing here is evidence about that work.

## 6. What this pack does not know

- Anything after Week 2: Simulink, toolbox functions (`tf`, `step`, root locus, Bode), hardware rigs, and whatever report changes those labs bring. A search by name and by modification date since mid August 2026 of all seven iCloud term folders and OneDrive found no Week 3 handout, no later report, and no Simulink or toolbox file. File contents were read only for the ENGR 315 lab items, so a handout filed under an unrelated name would be missed. The one loose Week 3 file is a hand-algebra draft of two experiments with no prose, no report sections, and no sign it was submitted. It says nothing about the Week 3 report format, toolbox work, Simulink, or hardware, so those gaps stay open. The Lab 2 handout lists textbook Section 2.9 (simulation with control design software) as reading and invites optional exploration of Simulink; neither is a requirement, and neither is evidence about the later labs.
- The syllabus, the grading weights, and the AI-use policy.
- The instructor's feedback on either report. There is no graded copy, so "matches the checklist" is the strongest claim available, not "scored well".

## Source basis

Cited by type only. No course text is reproduced beyond a few words, no values from submitted work appear, and the exemplar uses an invented system.

- **Lab 1 handout:** MATLAB introduction, math review, general report instructions and checklist, upload rule and penalty. Kept in the iCloud ENGR 315 LAB folder, not in the OneDrive one.
- **Lab 2 guidelines:** spring-mass-damper experiments, content and formatting checklists.
- **Instructor m-file template.**
- **Week 1 and Week 2 submitted reports**, and the Week 2 m-files and output-check notes.
- **Week 3 Lab Report (a loose file, not a folder):** a hand-algebra draft of two experiments. Evidence of what one student worked through, not of what was required; it supports only the provisional block-diagram method above.
