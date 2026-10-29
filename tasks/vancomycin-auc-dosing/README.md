# vancomycin-auc-dosing

AUC-guided vancomycin dosing for 240 adults treated for serious MRSA infections, 74 of them on hemodialysis,
following the 2020 consensus guideline of ASHP, IDSA, PIDS and SIDP (Rybak et al., Am J Health-Syst Pharm
2020;77:835-864). For every patient the agent reports the patient's own elimination rate constant and volume of
distribution fitted to the two usable levels, the AUC over the first 48 hours, the AUC over the 24 hours before
the later level (the guideline's sampling-period AUC), exposure against the target of 400 to 600, and the new dose.

## Difficulty

Clinical pharmacists adjust vancomycin doses from measured levels every day, and since 2020 the guideline
recommends AUC-guided dosing for serious MRSA infections. Its first-order equation method (peak and trough near
steady state, in one dosing interval) is what pharmacists and AI agents reach for, and the guideline itself warns
that it is hard to use when doses are irregular. Hospital records rarely meet its assumptions: levels are drawn on
the first day, around a dose, or two intervals apart; doses are late, early or held; infusions are paused, slowed,
sped up or stopped partway, so the drug actually given must be read from the pump's cumulative volumes. Patients
on hemodialysis add the hard part of real practice: contemporary high-permeability dialyzers clear vancomycin
substantially (guideline p. 846), so elimination is the patient's own clearance plus the dialyzer's while a session
runs, and many doses are given during the final part of a session, as the guideline describes. The elimination
rate is then not constant, the superposition of single-dose curves at one rate no longer holds, and the patient's
clearance and volume must be solved together through every infusion and dialysis breakpoint; the generator rejects
any patient with more than one exact solution. The records carry the details real hospital data has: times are New
York local time and most courses cross the 2026 daylight-saving change, so elapsed time must be computed on a
continuous clock; one laboratory reports in umol/L; some results were corrected after release, the corrected value
replacing the original with the same accession. Usable levels exclude rejected and cancelled specimens, results
below the reporting limit, and levels drawn during an infusion or a dialysis session or less than an hour after an
infusion stopped. The AUC is the guideline's sampling-period AUC and the new dose follows the guideline's
proportional change of the dose (p. 840), with the MIC taken as 1 mg/L as Recommendation 6 advises although 92
patients have a measured MIC other than 1. The data holds 240 patients: 74 on hemodialysis (38 with a dose given
during a session, 34 with a level drawn during one), 157 whose course crosses a clock change, 65 with results in
umol/L, 71 with a corrected result, 203 with irregular records, 135 with mistimed levels, 40 with first-day levels
and 144 with a dose given between their two levels. 62 patients have an AUC within 2 percent of 400 or 600, 51 an
unrounded new dose within 2 percent of a 250 mg rounding midpoint, and 109 a level drawn within 6 minutes of one
hour after an infusion stopped (counts in authoring/evidence/agreement.txt). Each shortcut tried (see
authoring/evidence/calibration.txt: ignoring dialysis or spreading it over the course, unconverted dialyzer
clearance, levels during dialysis kept, steady-state AUCs and doses, naive local times, umol/L read as mg/L,
originals kept instead of corrections, ignoring pauses, partial volumes or held doses, keeping mistimed levels,
using measured MICs, other rounding, trapezoid AUCs) gets many patients right and others wrong. The patients are
synthetic but follow the guideline's dosing ranges, infusion limits (at most 5 mg/mL and at least 1 hour per 1,000
mg), thrice-weekly 3.5 to 4 hour dialysis on high-permeability dialyzers, and published adult vancomycin clearance
and volume ranges.

## Solution

The reference solution (solution/solve.py) converts New York local times to a continuous clock with the US
daylight-saving rules, keeps each corrected result in place of its original, converts umol/L to mg/L, turns each
administration's pump events into constant-rate segments from the cumulative volumes, and builds a timeline of
every infusion and dialysis breakpoint with the infusion rate and dialyzer clearance in each interval. It selects
the two usable levels, carries the amount in the body across the timeline in closed form, and finds the patient's
clearance and volume by a coarse grid search followed by a damped two-dimensional Newton iteration from the best
starting points until the fit is exact. It integrates the closed-form interval terms for the 48-hour AUC and the
sampling-period AUC, classifies exposure against 400 to 600 and scales the current dose in proportion to reach
500, rounded to the nearest 250 mg.

## Verification

The verifier recomputes every patient with its own independently written engine (tests/engine.py: an explicit
event-by-event state machine for the amount in the body, nested Illinois regula falsi for the clearance and volume,
outer on the volume and inner on the elimination rate from the level ratio, and 24-point Gauss-Legendre quadrature
between event times for the AUCs) from a private copy of the inputs that exists only in the verifier image, and
never runs agent code. The data generator (authoring/sim.py, nested bisection with closed-form interval
propagation) is a third implementation; the engine and generator agree within a relative 2.2e-12, the solution's
printed values are the engine's values rounded to the stated decimals, every patient has exactly one clearance and
volume through both levels (a 7 x 7 multistart Newton search finds no second solution), the AUC stays at least 0.6
percent from 400 and 600 and the unrounded dose at least 0.6 percent from a rounding midpoint, both more than the
0.5 percent numeric tolerance. The engine is checked against closed-form results: a single infusion, the
steady-state peak, the Sawchuk-Zaske elimination rate from a steady-state peak and trough, the steady-state AUC
over an interval, the total AUC of one dose (dose over clearance), and a hand-worked infusion followed by a
dialysis session. Tests check that the inputs are consistent, the value formats, one row per patient in order, one
test per method family (hemodialysis patients, doses during dialysis, levels during dialysis, first-day levels,
doses between the levels, irregular records, mistimed levels, levels near one hour after an infusion, rejected or
unreportable results, measured MICs other than 1 mg/L, changed orders, courses crossing a clock change, results in
umol/L, corrected results, patients near the target edges and near rounding steps, and each exposure category) and
finally every patient, with numbers within 0.5 percent and exposure and new dose exact. Reward is 1 only if every
test passes.
