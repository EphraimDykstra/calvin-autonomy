# EES for Calvin thermal-fluids courses

This is for the host model. It covers how to write EES the way ENGR 319, ENGR 328 and ENGR 333 expect: what to hand the student, what to ask them to bring back, and how to check what comes back. The rules are derived from course handouts, lab manuals and one student's EES files. The pack's rule nodes hold the same rules in structured form, and each rule has a `basis` field naming its source by document type.

**You cannot run EES.** It is Windows-only and runs on the engineering lab machines or the remote desktop. Every file you write is unverified until the student solves it and sends back the results. The exemplars (`exemplars.<id>`) have never been solved in EES either. Treat them as idiom, not as tested code.

## 1. Before writing anything

1. **Check the handout says EES is allowed for this problem.** ENGR 328 homework sheets often forbid EES because tests have no EES. Some allow a quick lookup, which the student reports as "from EES" without printing code. Others require full EES code. ENGR 319 computer problems prefer EES, but the student must use either EES property functions or textbook tables, never a mix.
2. **Identify the course. The two professors' conventions differ, so do not blend them.**

| | ENGR 328 | ENGR 333 |
|---|---|---|
| Unit system | Set in the Options dialog and saved with the file. **No `$UnitSystem` line.** | `$UnitSystem SI mass K bar kJ` (or whatever the handout names) as the first code line |
| Comments | `//` lines and capitalised section banners; `"..."` and `"!..."` for text that should print | `"..."` descriptive text; `{...}` for temporary check equations |
| Won't converge | Add limits when needed (T of at least 200 K; a film-boiling surface just above Tsat) and a realistic guess | Prefer good guesses; leave limits at -Inf/Inf; Update Guesses after each success |

## 2. The unit system: the highest-value warning

The ENGR 328 unit system lives in the GUI, not in the file. A student handed a 328-style file has no line telling them the setting exists. Nothing in the file warns them either. One documented case solved an ideal-gas regenerative cycle under Celsius when the inputs assumed Kelvin. The efficiency came out wrong and EES raised no error.

So, every time:

- **ENGR 333:** write `$UnitSystem ...` on the first code line.
- **ENGR 328:** put a comment near the top stating the intended system, e.g. `// Unit system (Options): SI, mass, K, kPa, kJ`. Tell the student to set exactly that before solving.
- Some handouts override the default for one problem, such as English units for a cycle or a molar basis for flame temperature. Read the sheet.
- Tag every input with units (`[K]`, `[kPa]`, `[g/s]`), including constants inside lab-manual formulas. Change units with `Convert(from,to)` and `ConvertTemp(from,to,value)`, never typed factors.
- EES reads unit strings case-insensitively: torque is `[N-m]`, because `[Nm]` reads as nanometres.
- Absolute temperature matters in radiation (`T^4`), exergy (`T0*DELTAs`) and ideal-gas lookups. `Convert(C,K)` scales a temperature *difference* and does not add 273.15. Use `ConvertTemp(C,K,T)` or a K unit system.

### When a number is about 1000 times off

The in-course causes are prefix mismatches between an input tag and the unit system:

- **Pa vs kPa.** Orifice pressure drops are read in Pa, but the file runs in kPa.
- **J vs kJ.** Heat-transfer correlations in W meet property enthalpies in kJ/kg. Convert `h_fg` with `Convert(kJ/kg, J/kg)`, or convert the result.
- **g vs kg.** The refrigerant flow meter reads g/s.
- **W vs kW.** Electrical heater power is added to kJ/kg times kg/s terms.

Two related traps: invented unit tags that are not real units, and redundant conversions such as `Convert(kW, kJ/s)`. Both leave unit errors that poison everything downstream. A factor near 18, 29 or 44 instead of 1000 means a mass-versus-molar basis error, not a prefix error.

## 3. How the code is laid out

Block order: header → unit system → GIVENS (raw data with units, gauge-to-absolute and conversions right beside each raw value) → constants looked up once → state properties → balances section by section → percent errors and checks → plot arrays plus a comment saying what to plot.

**Build order for a lab model.** The same A/C lab file was compared early and late in the semester. The first pass had givens, a few property calls and one section's balance. Its conversions used typed factors, and one humidity call wrongly used a refrigerant pressure. The final version added one section at a time, simplest first. Each section named its forcing and response terms. Typed factors became `Convert()` calls. The moist-air pressure was fixed to `P_atm` everywhere with a warning comment. Refrigerant states, COP and plot arrays came last, and unit errors were cleared before moving on. Write new lab code in that order, and tell the student to solve after each block. The ENGR 333 final-exam handout gives the same advice: solve after every equation you add.

**Header.** A short comment block with student, course, assignment and problem, professor, and date. Use placeholders (`[Student Name]`) in anything you write as an example.

**Naming.**
- States are arrays: `T[1]`, `P[1]`, `h[1]`, `s[1]`. Arrays are needed to plot states, even a single one.
- EES is case-insensitive, so `m` and `M` are the same variable. Use `MM` and `NN` for the last node index, and write `time` rather than `t`.
- Grid index origin follows the handout: 0-based for the 1D textbook examples, 1-based for the 2D busbar-type problems.
- Scalars are snake_case (`m_dot_a`, `Q_dot_evap`, `T_infinity`). Gauge readings end in `_Gauge`.
- Plot-only values get their own arrays (`T_psych[k]`, `P_R134a_plot[k]`).
- A string variable may hold the fluid (`fluid$ = 'Air'`, then `Enthalpy(fluid$, T=T[1])`). An ENGR 328 handout asks for exactly this.
- Avoid apostrophes in comments. EES uses single quotes for strings, and students reported apostrophes in comments causing trouble. This comes from student reports only, not from a handout.

**Equations.**
- Write balances in their long physical form and let EES solve the set. Do not isolate variables.
- Do not write ideal-gas or constant-cp shortcuts (`Pv=RT`, `q=cv*DELTAT`, `cp*ln(T2/T1)`) when the problem wants exact properties. Fix each state with two properties from the process relation (`s[2]=s[1]`, `v[2]=v[1]/r`) and look the rest up. If cp, R or molar mass is needed, get it from EES.

## 4. Property functions

- **Name decides the model.** A chemical formula (`CO2`, `H2O`, `N2`, `O2`, `CH4`, `C8H18`) is an ideal gas. A word name (`CarbonDioxide`, `Water`, `Nitrogen`, `Methane`, `n-Octane`) is a real fluid with all phases. Use `Water` for steam-table work.
- **Formation enthalpy.** `Enthalpy()` of an ideal-gas species already includes it, so one call gives the total. A real fluid's does not. For a liquid fuel, take `h_f` from the textbook and add the real-fluid change `h(T,P) - h(298 K,P)` from EES. `Enthalpy_formation` does not work for real liquids.
- **Air.** `Air` and `Air_ha` are different data sets. ENGR 328 asks for `Air`. The IC lab builds air from `O2` and `N2` for combustion enthalpies. ENGR 333 week-one work used `Air_ha`. Follow the handout, and do not mix them within one analysis.
- **Saturation.** `x=0` is saturated liquid at Tsat, not tap water. There is no quality above the critical point, so superheated vapour far above it is not `x=1`.
- **Psychrometrics (A/C lab).** Use `AirH2O` with `T=` dry bulb, `B=` wet bulb, and `P=` total pressure always passed explicitly. The functions are `Enthalpy`, `HumRat`, `Volume`, `RelHum`, `DewPoint` and `WetBulb`. h and v come back per kg of dry air. Never pass a refrigerant-loop pressure.
- **R134a loop.** Convert gauge readings to absolute pressure first. State 1 comes from T and P. State 3 is `x=0` at condenser pressure. State 4 is `h[4]=h[3]` at evaporator pressure. State 2s is `Enthalpy(R134a, P=P[2], s=s[1])`.
- **Reference state.** Absolute h and s differ between property packages, so compare differences.
- **Radiation.** EES provides `sigma#`. Use emissivity `0.999999999`, not 1, to avoid a singular resistance.

## 5. DUPLICATE, Sum and Integral

```
N_runs = 5
DUPLICATE i = 1, N_runs
  omega[i] = Speed[i] * Convert(RPM, rad/s)
END
```

- Nest `DUPLICATE` for 2D grids. Write interior, edge and corner equations as separate loops over their own ranges. Equation count must equal unknown count.
- Use a grid multiplier so node density changes in one place. Very dense grids can exhaust EES memory.
- Sum with `Sum(Q[m], m=1, MM)`, or `Sum(Q[2..a])` with the end bound precomputed into a variable.
- For transient work: `T[m] = T_init[m] + Integral(dTdt[m], time)`. Each node balance is written "all in", meaning every term is neighbour minus node and always added, set equal to rho_cp × volume × `dTdt[m]`. Use `rho_cp = k/alpha` when only diffusivity is given.
- Validate against a known case. Turn generation off and the profile must match a hand-solvable resistance network.

## 6. Parametric tables

Tables are GUI state, so a code listing does not show them. Write the code, then give the student table instructions:

1. Tables > New Parametric Table. Columns: the swept input plus the outputs, e.g. `time, T[0], T[1], T[2]`, or `r, eta_th`.
2. Comment out the equation that fixes the swept input.
3. Fill the input column (first value, last value, number of runs, linear), then Solve Table.
4. Plot from the table.

Uses seen in these courses: efficiency against compression or cutoff ratio, time histories for transient conduction, and top-surface heat loss against grid multiplier to show convergence. Before trusting a curve, check that one table row reproduces the single-solve answer.

## 7. When it will not solve

1. Solve after every equation. The failure is usually in the last one added.
2. Set a realistic guess in Variable Info, such as a temperature of a few hundred K rather than 1. Then Update Guesses once it solves. A default guess near absolute zero drives property calls out of range and gives a mathematical but unphysical answer. Any thermo result below 200 K is suspect.
3. Limits: follow the course (see the table in section 1).
4. A negative number under a fractional power usually means an unbounded unknown. Bound it, e.g. a surface temperature above Tsat.
5. An "inconsistency ... in block" error means redundant equations. Copy the file, comment everything out, and re-add equations one at a time.
6. Temporary check equations in braces are fine while debugging. Remove them before submitting.

## 8. What to tell the student, and what to ask back

Tell them:
- which unit system to set (ENGR 328) or confirm the directive line (ENGR 333);
- to paste the code into the Equations window, Check Units, then Solve;
- any Variable Info guesses and limits, and any parametric-table setup;
- which variables to mark as Key Variables for the printout.

Ask them to send back:
- the solution window, including the unit-settings line and the unit-check message;
- the Arrays table for state problems, and the parametric table plus plots for sweeps;
- the exact error text if it failed, and which equation EES highlighted.

## 9. Sanity-checking what comes back

- The unit-settings line matches what you asked for, and unit errors are zero.
- Temperatures are all above 200 K, and in the expected unit.
- Quality is between 0 and 1. Isentropic efficiency is below 1. COP and cycle efficiency are below the Carnot bound.
- Humidity ratio is positive and plausible. A moist-air enthalpy far from its chart value points to a wrong P.
- Signs follow in − out; an impossible negative mass flow means inconsistent units or a sign error.
- Energy balances close against the forcing term. Percent error is (response − forcing)/forcing × 100. Report negative errors as found; never flip signs to improve them.
- Magnitude: anything off by about 1000 goes to section 2.
- Grid results change little when the multiplier increases, and the zero-generation case matches the hand solution.
- If a handout gives an answer, compare against it. EES values may differ slightly from rounded book answers.

## 10. Corrections to an older style guide

An earlier personal EES style guide made two claims that the course sources contradict. Do not reintroduce them:

- It said string variables cannot be the fluid argument. Homework files use `Enthalpy(fluid$, ...)` successfully, and an ENGR 328 handout asks for it.
- It said liquid octane has no EES model. The IC lab manual prescribes `n-Octane` as the real fluid. The narrower true rule is that EES stores no formation enthalpy for it (section 4).

Its personal tone rules (jokes, running asides) are also dropped. They are not course convention.

## Source basis

All rules come from these documents, cited by type. Nothing below is quoted beyond a few words, and no numbers come from submitted work.

- **ENGR 328 lecture handouts:** the cycles-in-EES slide, the numerical-methods-in-EES handouts (1D and 2D), the transient-conduction handout, and a radiation-enclosure-network deck whose worked solution is stated to come from EES. These are the professor's own idiom and are weighted most heavily.
- **ENGR 328 homework sheets (weeks 1-12):** where EES is allowed, printout requirements, formation enthalpy and ideal-gas naming, element balances, guesses and limits, boiling-problem troubleshooting, and emissivity and `sigma#`.
- **ENGR 328 A/C laboratory manual:** unit tags on formula constants, the psychrometric-function appendix, `x=0` versus tap water, and the R134a energy rate.
- **ENGR 328 IC engine laboratory manual:** let EES convert units and look up properties, element balances, coefficient letters, `n-Octane`, formation enthalpy, mass versus molar mixing, and `N-m` versus `Nm` (a case-insensitive nanometre trap).
- **ENGR 328 student EES files (22) and their printouts:** block order, naming, the unit-system case, the unit-error fixes behind the factor-of-1000 section, and the early and late versions of the A/C lab file.
- **ENGR 333 EES files (11) and the week-one and week-two sheets:** the `$UnitSystem` directive and the `Air_ha` choice. A few single-call syntax probes were used only as syntax evidence.
- **ENGR 333 final-exam handout:** solve after every equation, prefer guesses to limits, temporary check equations, block-inconsistency debugging, and substitute substances.
- **ENGR 319 computer-problem sheet and week-5 homework sheet:** do not mix EES properties with tables, `Water` rather than `H2O`, and array notation for plotting.

What is thin: ENGR 333 is in progress, and only its first weeks and the final-exam guidance were available. The psychrometric and refrigeration rules rest on one lab in one semester. Parametric-table rules come from handouts and student notes, not a professor's code.
