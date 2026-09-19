# Exemplar: IC lab energy-balance pre-submission (shape only)

- **id:** `ic-energy-balance-presubmission`
- **family:** `ic-lab`
- **stage:** `energy-balance`

This skeleton was paraphrased from the structure of a real submission and its EES file. **All numbers are invented.** The EES outline below is a block order with placeholder comments, not code. For EES syntax, see `curriculum/_shared/ees/`.

---

## Title page (unnumbered)

Descriptive title · [Student Name] · ENGR 328, Section [X] · [Instructor] · [Month Year]

**Abstract.** Method in two sentences: combustion model, calorimeter check, energy balance at one operating point. Then results in two or three sentences, as numbers: actual air-fuel ratio against theoretical, the fraction of fuel unburned, predicted against experimental exhaust cp, and the split of the chemical-energy drop into shaft power and heat loss.

## Body (numbered from 1; 2-3 pages)

**Objective.** One or two sentences.

**Methods.** Equations appear inline, numbered at the right margin, in this order:

1. Intake-air mass flow from the orifice relation (pressure-drop magnitude)
2. Exhaust flow as air plus fuel
3. Actual molar air-fuel ratio from measured flows
4. The actual combustion equation, with its six unknowns n, a, b, c, d, e
5. The burned-fuel oxygen relation
6. Calorimeter balance solved for experimental exhaust cp
7. The steady energy balance, fuel plus air equals exhaust plus heat loss plus shaft power

Figure 1 (caption below) is a schematic control volume around the engine, with arrows for fuel, air, exhaust, shaft power, and heat loss.

**Results.** One paragraph per topic: combustion (which of unburned fuel or excess O₂ is nonzero, and why that is expected for a small engine), the cp check (the size of the gap and its likely cause), and the energy balance. Table caption goes above:

*Table 1. Energy streams at the energy-data operating point (illustrative values).*

| Stream | Units | Value |
|---|---|---|
| Fuel + air enthalpy in | kW | −10.0 |
| Exhaust enthalpy out | kW | −20.0 |
| Drop in chemical energy | kW | 10.0 |
| Shaft power, τΩ | kW | 2.0 |
| Heat loss (residual) | kW | 8.0 |

An optional second figure is a grayscale-safe split of the chemical-energy drop, with a takeaway caption and no chart title.

**Conclusions.** Is the air-fuel ratio in the manual's expected band? Does the cp comparison support the modelled exhaust composition? Is the heat-loss fraction plausible for an air-cooled single-cylinder engine?

## Appendix

Raw data table (units in the headings), timed fuel measurements, per-stream intermediate values, and EES code with output.

## EES block order (placeholders only)

```
"--- header: course, lab, [Student Name] ---"
"--- 1. givens: raw readings with units, one block per instrument ---"
"--- 2. parameters: O2 and N2 molar fractions of air (editable), orifice Cd and diameter ---"
"--- 3. flows: intake air (orifice, |dP|, Pa->kPa before the root), fuel (pipette/time), exhaust = air + fuel ---"
"--- 4. theoretical combustion: C, H, O, N balances; theoretical molar AF ---"
"--- 5. actual AF from measured flows ---"
"--- 6. actual combustion: C, H, O, N balances + burned-fuel O2 relation + AF relation -> n,a,b,c,d,e ---"
"--- 7. exhaust mole fractions and mixture molar mass ---"
"--- 8. predicted mixture cp; experimental cp from calorimeter balance ---"
"--- 9. energy streams: air (O2+N2 ideal-gas h), fuel (liquid formation h adjusted to inlet T), exhaust (mixture h) ---"
"--- 10. shaft power (torque in N-m, speed converted to rad/s) ---"
"--- 11. energy balance -> heat loss residual; chemical-energy drop check ---"
```

Every block comments each equation with the manual's equation number, so a reader can match code to report.
