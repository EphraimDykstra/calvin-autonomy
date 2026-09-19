# MATLAB for Calvin engineering labs

This is for the host model. It covers how to write MATLAB scripts and figures the way ENGR 315 Lab expects, which is the only course in the archive with MATLAB evidence. `pack.json` holds the same rules in structured form, each with a `basis` field naming its source by document type. `curriculum/engr315-lab/` holds the report format that these scripts feed.

**You cannot run MATLAB.** Every script you write is unverified until the student runs it and sends back what it printed and the figure it drew. The exemplars in `exemplars/` have never been run either. Treat them as idiom, not as tested code.

**What this pack does not cover.** Simulink (named in the Lab 1 title, no evidence), the Control System Toolbox (`tf`, `step`, `pzmap`, `rlocus`), Live Scripts, and anything another course's handout says. When a student in another course uses MATLAB, read that handout first; the plotting and script rules below are the part most likely to carry over, and the header block is the part least likely to.

## 1. The script is the deliverable

- Everything runs from one m-file, top to bottom. Commands typed at the `>>` prompt do not count. A reader must be able to press Run and get every number and the final figure.
- Open with the course template header (see `exemplars/script-header.m`): course line, Author, Date with version, Title, File Name, then `clc`, `close all`, `clear all`. Keep the template's caveat that `clear all` is skipped when a Simulink model reads workspace variables.
- The File Name in the header must match the name the file is saved under. A header copied forward from the previous experiment and never updated is a slip seen twice in the evidence.
- Write MATLAB in capitals in the report, never Matlab.
- Each student writes and runs their own files. Running a classmate's m-file to get results is treated as plagiarism in both handouts. Write the script for the student to run; never present it as something they can submit unread.

## 2. File naming

The pattern is `[StudentName]_Lab[N]_Ex[M]_v[K].m` per experiment, or `[StudentName]_Lab[N]_v[K].m` when one file covers the lab. The next experiment starts from a copy of the previous file, renamed, with `v1` reset or bumped.

The sources disagree on what `[StudentName]` is:

| Source | Says |
|---|---|
| Lab 1 handout | the student's name |
| instructor template header | first and last name, underscore between |
| Lab 2 guidelines checklist | the file name includes the student's initials |
| the submitted files | surname and given name run together, no separator |

Follow the current lab's handout. If it is silent, ask the student which form their section uses. Never fill in a real name in anything you write into this repo.

## 3. Computing a response

- **Elementwise operators.** `t` is a vector, so `.*`, `./`, `.^` wherever `t` meets another vector. `x*sin(x)` with a column `x` is a dimension error; the Lab 1 handout makes the student see this on purpose.
- **`exp(x)`, never `e^x`.** MATLAB has no built-in `e`.
- **Cases in a vector, rows in a matrix, one `for` loop.** Preallocate with `zeros(numel(cases), numel(t))`. The Lab 2 handout requires the loop and forbids repeating near-identical lines.
- **Boundary values.** A closed form that divides by something zero at a regime boundary (the second-order `sqrt(1 - zeta^2)` at `zeta = 1`) is evaluated just inside the boundary, and the report says why.
- **Complex branches past the boundary.** Beyond it, `sqrt` goes imaginary and `acos` returns a complex angle. MATLAB then plots only the real part, with a warning, and the branch can flip the sign of the whole curve. Wrap the entire expression in `real()`, not a factor of it, and have the script print the initial value for every case; if one case starts at minus the initial condition, the branch is wrong.

## 4. Figures

The Lab 2 handout is specific, and its rules are the most portable part of this pack.

1. **One `plot` call** with several `x, y, style` triples draws all the cases. Keep the handles: `h = plot(...)`.
2. **Black line styles, one per case:** `'-k'`, `'--k'`, `'-.k'`, `':k'`. The figure must read on a grayscale printout, so color alone never distinguishes curves. Four styles exist; a fifth trace needs a marker or a gray `'Color', [0.5 0.5 0.5]`.
3. **An overlay must not reuse a style already in use.** A red dotted overlay on a figure that already has a black dotted curve turns into two identical dotted lines in grayscale. This happened in the one submitted report with an overlay.
4. **Title, both axis labels with units, and a legend.** The in-plot `title` is ENGR 315's rule. Other courses' report standards (ENGR 204 Lab, for one) forbid a title inside a captioned graph, so check the course before adding one. Greek letters in TeX: `'\zeta = 0.3'`, `'\omega_n'`, `'\tau'`. A legend that says `zeta = 0.3` is marked wrong.
5. **Overlays** go on with `hold on` and end with `hold off`. Build the legend from the handles you want named: `legend([h(1) h(2) hr(1)], {...})`. See `exemplars/overlay-hold-on.m`.
6. **No touch-ups in the figure window.** Axis limits, labels, and styles are set in code. The figure the script leaves on screen is the one in the report.
7. Set `xlim` so the interesting part fills the plot, even when the time vector runs longer.

## 5. Checking before the screenshot

The strongest practice in the evidence is a short list of expected values computed independently of the plot, checked before the figure was captured. Do the same:

- Have the script `fprintf` a value per case that has a known answer: the initial condition, the value at one time constant, a peak ratio with a closed form.
- Tell the student what each printed value should be, and what a wrong one means.
- A warning about ignored imaginary parts is a defect, not noise.
- Some correct results look wrong (an overdamped curve that is slower than the critically damped one). Know what the analysis expects before "fixing" a curve.

## 6. What to tell the student, and what to ask back

Tell them:
- the file name to save under, and to replace the header placeholders with their own details;
- to run the whole file (Run, or F5), not pasted lines;
- which printed values to compare against, and what each should be.

Ask them to send back:
- the Command Window output, including any warning or error text verbatim;
- the exported figure;
- the MATLAB release if a function is missing or behaves differently.

## Source basis

All rules come from these documents, cited by type. Nothing is quoted beyond a few words, and no value from submitted work appears in this pack or its exemplars.

- **ENGR 315 Lab 1 handout:** script workflow, file naming, elementwise operators, `roots`, MATLAB capitalization, m-files included and uploaded.
- **ENGR 315 Lab 2 guidelines:** the `for` loop, one plot call, line styles for grayscale, TeX Greek letters, `hold on`, no figure touch-ups, the formatting checklist.
- **Instructor m-file template:** the header block and the `clear all` caveat.
- **One student's Week 1 and Week 2 m-files and output-check notes:** the header in practice, the stale File Name line, `e^` versus `exp`, the complex-branch guard, legend-by-handle, and the check-before-screenshot habit.

What is thin: one course, two weeks, one student. Nothing on Simulink or toolbox functions. The exemplars use an invented first-order RC circuit so that no exemplar is the answer to a lab.
