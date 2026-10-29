# vancomycin-auc-dosing

AUC-guided vancomycin dosing for 240 adults treated for serious MRSA infections, following the 2020 consensus
guideline of ASHP, IDSA, PIDS and SIDP (Rybak et al., Am J Health-Syst Pharm 2020;77:835-864). For every patient
the agent reports the elimination rate constant and volume of distribution fitted to the patient's two usable
levels, the AUC over the first 48 hours, the steady-state AUC24 on the current order, exposure against the AUC/MIC
target of 400 to 600, and the new dose.

## Difficulty

Clinical pharmacists adjust vancomycin doses from measured levels every day, and since 2020 the guideline
recommends AUC-guided dosing for serious MRSA infections. Its first-order equation method (peak and trough near
steady state, in one dosing interval) is what pharmacists and AI agents reach for, and the guideline itself warns
that it is hard to use when doses are irregular. Hospital records rarely meet its assumptions: here levels are
drawn on the first day, around a dose, or two intervals apart; doses are late, early or held; infusions are
paused, slowed, sped up or stopped partway, so the drug actually given must be read from the pump's cumulative
volumes; loading doses differ from maintenance doses, and orders change. The patient's parameters therefore have
to come from superposition of every documented infusion in a one-compartment model, with the elimination rate
solved from the ratio of the two levels. Choosing the two usable levels means discarding rejected and cancelled
specimens and results below the reporting limit, and levels drawn while an infusion was running (pauses included)
or less than an hour after it actually stopped (the guideline's postdistributional sampling window), judged
against the documented stop, not the scheduled one. The MIC changes the target only when measured by broth
microdilution, as the guideline advises. The data holds 240 patients, 215 with irregular records, 130 with
mistimed levels, 41 with first-day levels; planted values put AUC24/MIC within 0.6 percent of 400 or 600 for 44
patients, the unrounded new dose within 5 mg of a 250 mg rounding midpoint for 50, and levels 55 to 59 or 61 to 65
minutes after an infusion for 119. Each of 20 shortcuts tried (the steady-state equations, ignoring pauses,
partial volumes or held doses, nominal infusion times, keeping mistimed levels, any-method MICs, other rounding,
trapezoid or doubled AUCs) gets many patients right and others wrong. The patients are synthetic but follow the
guideline's dosing ranges, infusion limits (at most 5 mg/mL and at least 1 hour per 1,000 mg) and published adult
vancomycin clearance and volume ranges.

## Solution

The reference solution (solution/solve.py) turns each administration's pump events into constant-rate segments
from the cumulative volumes, selects the two usable levels, writes each level as the sum of closed-form infusion
terms divided by the volume, solves the ratio of the two levels for the elimination rate by bisection after a
scan for the bracket, takes the volume from either level, integrates the closed-form segment terms over the first
48 hours, and applies the guideline target, the MIC rule and the dose rounding.

## Verification

The verifier recomputes every patient with its own independently written engine (tests/engine.py, which writes
each segment's contribution in a different form, solves the elimination rate by the Illinois regula falsi
method and integrates the 48-hour AUC numerically with 24-point Gauss-Legendre quadrature between event times)
from a private copy of the inputs that exists only in the verifier image, and never runs agent code. The data
generator (authoring/sim.py, which propagates the amount in the body from event to event and uses a mass balance
for the AUC) is a third implementation; the engine and generator agree within a relative 2e-13, every patient has
exactly one solution for the elimination rate between 1e-6 and 100 per hour, and AUC24/MIC stays at least 0.05
percent from 400 and 600 and the unrounded dose at least 0.5 mg from a rounding midpoint. The engine is checked
against closed-form one-compartment results: a single infusion, the steady-state peak, the Sawchuk-Zaske
elimination rate from a steady-state peak and trough, and the steady-state AUC over an interval. Tests check that
the inputs are consistent, the value formats, one row per patient in order, one test per method family (first-day
levels, doses between the levels, irregular records, mistimed levels, levels near one hour after an infusion,
rejected or unreportable results, broth microdilution and other-method MICs, changed orders, patients near the
target edges and near rounding steps, and each exposure category) and finally every patient, with numbers within
0.5 percent and exposure and new dose exact. Reward is 1 only if every test passes.
