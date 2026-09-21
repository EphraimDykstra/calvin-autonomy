# ENGR 328 (Thermodynamics 2): guide

Where a guide section and a rule node disagree, the rule node is authoritative, and the disagreement is a bug to report.

## How much to trust this pack

- **Format rules come from professor-written handouts**: a general technical-report guideline sheet, a lab schedule that describes each deliverable, and the two lab manuals, all distributed in Spring 2026. These are strong evidence. They have since been re-read directly and checked rule by rule against this pack, rather than trusted from the summary of an earlier round, and no contradiction was found. The per-stage page budget was confirmed from the schedule independently of the pack. See `evidence_tiers.verification_note` for what was checked.
- **A few writing rules come from a one-page handout by the same professor, originally issued for an earlier ENGR 319 lab** and filed with this course's lab material. These are marked `prior_handout`: no first person, no hand calculations, typeset units and multiplication signs, leading zeros, and page-number position. They very likely still apply, but they were not re-issued under this course's header.
- **No graded copy, instructor annotation or syllabus was found**, in either of the student's two document archives, searched by filename and by checking every word-processor file for tracked changes and reviewer comments. A syllabus did exist, since the schedule refers the student to it, but no copy is held. Every "what good looks like" statement is therefore derived from the written instructions rather than from a marked-up submission. The author of the submissions reports that this course's memos and lab reports scored highly, so the observed structure is reported to have worked, but that is self-reported, not a graded artifact, and the written handout still wins wherever the two disagree.
- **The student exemplars break some written rules.** Both final reports run past the four-page body limit, one numbers its title page, and one power-curve submission has no page numbers. **When an exemplar and a handout disagree, follow the handout.** This is not a formality: the author reports losing 1-2% per report, and on work graded for technical writing these three violations are the most likely place those points went. Holding the page budget and the title-page convention is the concrete way to do better than the exemplar.

- **The page budget does not enforce itself.** This pack's `format.rendering` leaves `max_body_pages` null on purpose, because the limit differs by stage: 3 body pages for a pre-submission, 4 for a final, 2 for the efficiency submission. The renderer only checks a budget it was given, so a null value means no check runs at all. Before rendering, copy the relevant `assignment_families[].stage_details[].max_body_pages` into the rendering profile. Skip that and the one rule we know cost marks here is the one rule going unchecked.
- **AI-use policy is unknown** (see `course_policy`). The lab manuals separately require lab analysis and writing to be individual work. Surface that to the student; do not decide it for them.
- **Margins are not specified** ("reasonable margins" is all the source says). The renderer's 1 in default is a default, not a course rule.

## The report format, in the order a reader meets it

1. **Title page, unnumbered.** A descriptive title (never just "Lab 1"), `[Student Name]`, course number and section (plus group, if any), the professor's surname spelled correctly, and the date with the correct year. The abstract sits on this page. It gives a few sentences on what was done and how, then a few sentences of key results as real numbers with units. The final report calls this block an executive summary; it is the same block.
2. **Body, numbered from 1.** Page numbers go at the bottom, centred or in the outside corner, never in the stapling corner. Headings stand out so that skimming them gives the outline. Every lab submission in the archive uses unnumbered headings in the order Objective, Methods, Results, Conclusions. That order is observed, not mandated.
3. **Equations** are typed in an equation editor and numbered sequentially in order of first reference. The number sits in parentheses at the right margin. Each equation is introduced and explained in the sentence around it. Never screenshot the manual, and never park equations in an appendix while the body refers to them. Use real Greek symbols, superscript units (m³/s, not m^3/s), and × or · for multiplication, never `*`.
4. **Figures** are centred and captioned **below**. The caption states the takeaway, not a bare label ("the equipment" is bad; a sentence saying what the figure shows is good). A captioned chart has no chart title. Charts must read in grayscale, must not be screenshots, and use schematic rather than photographic diagrams. Comparable plots share axis ranges. Never let a chart fill a page under a page limit, and never shrink one until it is unreadable.
5. **Tables** are captioned **above**, and the caption may be brief for large data tables. Units go in the column headings.
6. **Numbers** always carry units, everywhere, including appendices and graph axes. Significant digits must reflect measurement accuracy, even in appendices and printed spreadsheets. Values below one take a leading zero.
7. **Voice.** No I, we, you, the team, or the author. No diary narration of the lab session. Do not spend body space on routine unit conversions. Use one font at 11-12 pt and 1.5 line spacing.
8. **Appendices** are lettered: A, B, C, with sub-items A.1, A.2 where useful. The manual itself refers to an appendix in exactly that style. The observed finals open with Appendix A as a list of appendices, then raw data, calculated properties, charts, equipment data, and EES code. The appendices are optional reading: **the body must tell the whole story if the appendices were lost**. Whether appendix tables continue the body's numbering or restart per appendix (B.1) is unresolved in the evidence. Choose one and use it consistently.
9. **Physical form.** The report is printed, stapled, and handed in at the start of class. Each pre-submission also has an online key-data form due.

## The two lab families

Both labs follow the same rhythm: three short pre-submissions during the semester, then one final report. On-time, adequate submissions earn completion credit. The final report is graded for technical content and technical writing and carries most of the weight. (That is the Spring 2026 structure, and weights may change by term.) Every pre-submission is a self-contained short report of **2-3 body pages**, with attachments behind it: raw data, intermediate analysis, and EES code. Each final has a **4-page** body plus lettered appendices.

### A/C duct lab: three duct sections, two seasons

The apparatus is a duct with three sections. A-B adds steam and preheat, B-C cools and dehumidifies over an R134a evaporator, and C-D reheats with electric resistors. It runs a summer case and a winter case. **The pre-submissions are due downstream to upstream: C-D, then B-C, then A-B.** The schedule's due dates fix that order, and the manual calls C-D the simplest place to start. Every pre-submission covers both seasons for its one section.

The whole lab rests on one idea. **Forcing and response are computed independently and then compared; neither is ever solved from the other.** Forcing is what was done to the air: heater power (V²/R per element, summed in parallel, never the nameplate rating), fan power (from the manual's voltage chart), steam added or condensate removed along with the enthalpy those streams carry, and heat absorbed by the refrigerant. Response is what the air did: dry-air flow times the change in humidity ratio or enthalpy between stations. Percent error is (response − forcing)/forcing. Where nothing was forced, normalise by the inlet value instead. Into the air is positive, out of it is negative. **A 0% error is a red flag**: it means the balance was solved for the forcing term, which is homework-problem thinking and defeats the experiment.

What each stage adds:

- **C-D** sets up everything the later stages reuse: station states from dry bulb, wet bulb, and measured atmospheric pressure; dry-air flow from the orifice manometer (using the specific volume at the exit station); and the reheater balance. There are four error findings: water and energy, in both seasons.
- **B-C** adds the refrigeration side. Convert gauge pressures to absolute before any property call. State 4 is not measured: assume saturated liquid at the condenser outlet and an isenthalpic valve, so h₄ = h₃. Condensate forms at the evaporator and leaves near room temperature. There are four error findings.
- **A-B** adds the steam-generator sub-model. Steam rate equals net heat (electrical input minus the manual's convective loss) divided by the enthalpy rise from subcooled tap water to saturated vapour at room pressure. Tap water is not quality 0. **Summer needs two control-volume formulations, compared against each other, so this stage has six error findings instead of four.**
- **Final** condenses all three sections and adds the system-level results: a psychrometric chart and an R134a P-h diagram for each season, plus COP and compressor isentropic efficiency for each season. Evaporator effectiveness and UA (from effectiveness-NTU with capacity ratio zero) are extra credit. It closes with a brief conclusion per section, then overall conclusions on error size, whether it is plausible, where it comes from, and how to reduce it. Single-point wet-bulb sampling across a non-uniform duct is the expected dominant error source.

The EES model is one file per season and grows with every stage. The first submission holds givens, station states, dry-air flow, and the C-D block. Each later stage appends its section block and corrects earlier ones. The final adds the cycle metrics. Expect corrections between stages: the final is a rewrite to a tighter budget, not the pre-submissions stapled together.

### IC engine lab: three different analyses of one data set

A single-cylinder engine drives a dynamometer, and a counter-flow water calorimeter sits on the exhaust. **Unlike the A/C lab, the three pre-submissions are three different analyses, not one analysis repeated over three sections.**

- **Power curves** (2-3 pages). Shaft power is torque × angular speed at each operating speed. Plot power and torque against speed on one figure. The key finding is peak power and peak torque, each with the speed where it occurs; do not assume they coincide. Excel is acceptable for this plot.
- **Energy balance** (2-3 pages). The course flags this as the longest analysis, roughly a hundred lines of EES in about fifteen independent blocks, so build it over weeks. In order:
  1. Intake air flow comes from the orifice relation. Use the magnitude of the pressure drop, and keep Pa and kPa straight inside the square root.
  2. Fuel flow comes from the timed pipette volume. Exhaust flow is air plus fuel.
  3. Solve the theoretical octane balance element by element. Keep the O₂/N₂ fractions as editable parameters rather than hard-coding the N:O ratio.
  4. Compute the actual molar air-fuel ratio from measured flows and check it against the manual's expected band; being well below theoretical is normal.
  5. Solve the actual equation for n, a, b, c, d, and e using the manual's letters. Exactly one of unburned fuel (a) or excess O₂ (d) is nonzero.
  6. Predict mixture cp and compare it with the calorimeter's experimental cp.
  7. Air energy uses O₂ and N₂ ideal-gas enthalpies, which already include formation. Do not use the generic air or humid-air substance here.
  8. Fuel energy uses liquid-octane formation enthalpy from the textbook table, adjusted to the inlet temperature.
  9. Exhaust energy is the mass flow times the mixture enthalpy at the exhaust temperature, on a consistent molar or mass basis.
  10. Heat loss is the residual of the balance.

  Present the drop in chemical energy as equal to shaft power plus heat loss; negative absolute enthalpies are expected and harmless. Include a diagram of the energy flows.
- **Efficiency** (2 pages). Overall thermal efficiency is shaft power over (LHV × fuel flow), computed at every speed. The key finding is **efficiency plotted against engine power**, not against speed or run number, with a discussion of the trend with load.
- **Final** combines all three. It closes with a brief conclusion on each energy stream, then overall conclusions on energies, efficiencies, and whether the results are reasonable.

## What to collect, and what to do when something is missing

*This section describes how a host drives a 328 lab report. It lives here because the course it applies to is this one; when the shared playbooks land it moves there, and this copy goes, so that nobody maintains two.*

**Collect before you start.** Each lab family carries an intake list at `assignment_families.<family>.intake`: fetch it and ask only for what the student has not already given. It says what is needed, why, and who has it, and it points at the stage details rather than repeating them, so the stage the student names decides the section scope and the page budget. Two of its items exist because this pack holds no names: the group, if the submission is a group one, and the professor's surname.

**The title page needs both of those.** Pass them in the solution's `metadata` as `group` and `instructor`, along with `course`, `section` and `date`. An instructor you were not given prints as the literal `[Instructor]`, which is a visibly unfinished page rather than a wrong one; do not guess a name and do not leave the line out. The student fills it in, or tells you and you re-render.

**Place a student's image before you render it.** A solution may reference a figure only by a path inside its own run, so a file the student sends has to be put there first: `add-figure` copies it in, refuses anything that is not an image it can open, and records its hash so a file swapped afterwards is caught rather than quietly standing behind a finished deliverable. Do this before `render`, because the render draws what the solution points at.

**Two of this course's required charts are permanently the student's to supply.** The final report asks for a psychrometric chart and an R134a pressure-enthalpy diagram for each season. Both are property-data backgrounds, and property data is cited here and brought back by the student, never shipped or redrawn by this tool. So these are not a feature that is missing: they are an input, like the EES values, and they arrive the same way. The control-volume diagram each section needs is the student's too, for the simpler reason that nothing here draws one.

**When something like that is still outstanding, say so in the run rather than in prose.** `declare-inputs`, before `verify-report`, records what the run is waiting for: an id, the sentence the student reads, and the requirements it holds up. The requirement's own finding then records `awaiting: <id>` in place of passing, and the verifier report binds — so everything else about the deliverable still gets checked and reported, instead of the whole report being refused because one input has not arrived. `status` then reports the run **blocked**, with a plain `waiting on you: …` line naming exactly what to send. It can reach neither ready nor provisional while anything is outstanding, which is the point: this records a gap, it does not excuse one.

Write the sentence so a tired student can act on it alone: "Send the psychrometric chart for each season, summer and winter, as image files" rather than "charts missing". Two inputs may not ask in the same words, because identical sentences would collapse into one line and the student would send one thing and stop.

**When it arrives:** `add-figure` the file, declare whatever is still outstanding (an empty list when nothing is), put the figure in the solution, re-render, and re-bind the verifier report with the requirement genuinely passed. Withdrawing a declaration on its own does not make a run ready: the report was bound to the old declaration, so it goes stale and has to be rebuilt against the work as it now stands.

## EES in this course

EES is the expected tool for any lab analysis beyond simple plots. The manuals ask for raw data in and as few hand-entered numbers as possible, with units, conversions, and property lookups left to the software. Code is printed in the appendix with its solution output. Homework sets that assign EES expect printed code with the answers visible as key variables. For EES syntax, unit handling, property functions, and file layout, use the shared EES pack (`coursework pack show tool:ees`); this pack does not duplicate it. The course-specific traps are in `pack.json` under each method's pitfalls: refrigerant pressures in moist-air calls, gauge pressure, unit tags, and torque units that a case-insensitive solver reads as nanometres.

## Homework

Weekly sets are submitted in the assigned order. Each set names which of its problems require EES; that is stated per set, not once for the course, so read the set rather than assuming. Some prompts supply the expected answer; reproduce it or explain the difference. There is no written page-format specification for homework, so do not invent one.

**Working together is allowed; sharing code is not.** The sets say so in the course's own words. Whether that covers code a tool writes, as opposed to code another student wrote, is a question the rule predates and does not answer. Surface it to the student once before helping with an EES homework problem, say that the judgement is theirs and their professor's rather than this tool's, and then follow their decision. Do not resolve it here, and do not refuse on the strength of an ambiguity the course has not settled.

**Lab assistance stops before a submission is due.** The schedule sets a cut-off after which the instructor no longer answers lab questions (`instructor_support_window` on each lab family). The exact period is a scheduling detail that drifts between terms and is deliberately not recorded as a rule; tell the student the convention exists and have them read their own current schedule for it, so they plan questions ahead of it. Despite the similar name this is not an `assistance_rules` entry: it carries no status and no severity and says nothing about what help this tool may give.

**The tool choice is not EES-or-hand.** Problems the set does not assign to EES are often worked by hand, and the archive shows those written directly on the printed prompt. That is observed, not specified, and it is not the only alternative: the archive also shows a spreadsheet used to tabulate and plot results the solver produced, and a CAD thermal simulation used to re-solve a conduction problem that had already been solved numerically. Where a problem is solved more than one way, print each solve and compare them; do not let one silently replace the other. Follow whatever the set assigns, and where it assigns nothing, choose. (The simulation file is filed with the following week's set but is a steady-state run dated between the two, so which set it belonged to is ambiguous.)

**The sets go well beyond the two labs**, over radiation surface properties, two-dimensional steady and transient conduction, boiling, and radiation enclosure networks. Every method in this pack is a lab method or the general shape of an EES homework solution, so no method is stated for those topics. That gap is unmined, not unfillable: instructor problem statements for most weeks of the term exist in the student's course archive and have not been read into this pack yet. The rule nodes record the table and example labels the course's own working files cite. Those files do not name the textbook, so the labels are left unresolved there, and they are not unique across the books this course pair uses. Do not resolve a label against a book the student has not confirmed, and do not cite a value read from one.

## Exemplars

Exemplars (`exemplars.<id>`) are redacted, paraphrased skeletons that preserve structure and method only. Every number in them is invented and marked illustrative, so none of them can serve as an answer key. Use them to see how a stage is shaped, never as a source of values.
