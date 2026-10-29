# Authoring tools for vancomycin-auc-dosing

These files are not copied into the agent or verifier images. Run them from this folder. None of them writes
`__pycache__`.

## Provenance
- `generate.py` (seed 20200601) builds the 240 patients and writes both data copies (`../environment/data`,
  `../tests/data`). Non-dialysis patients: true clearance from Cockcroft-Gault creatinine clearance (0.05 L/h per
  mL/min, times 0.8 to 1.25), maintenance doses every 8, 12 or 24 hours. Hemodialysis patients (74 of 240): own
  clearance 0.15 to 0.7 L/h, thrice-weekly sessions of 210 to 240 minutes 48, 48 and 72 hours apart, a
  high-permeability dialyzer clearing 80 to 150 mL/min, a 20 to 25 mg/kg loading dose and a maintenance dose with
  each session, given during its final part or after it. Volume is about 0.7 L/kg (times 0.75 to 1.3). Loading
  doses of 20 to 35 mg/kg actual weight up to 3,000 mg (183 of the 240 patients have a loading dose order; 54
  have an order change), bags of at most 5 mg/mL, and at least 1 hour per 1,000 mg. Records include late and early
  starts, held doses, pauses, rate changes and partly given infusions. Usable level pairs follow seven patterns:
  four for non-dialysis patients (steady-state peak and trough in one interval, trough then peak around one dose,
  first-day levels, peak and trough two intervals apart) and three for dialysis patients (a post-dose level then a
  pre-dialysis level, two pre-dialysis levels, a post-dose level then the pre-dialysis level two sessions later),
  with assay noise of up to 8 percent, to 0.1 mg/L. Unusable results are rejected specimens, results below the
  reporting limit, and levels drawn during an infusion, during a dialysis session, or less than an hour after an
  infusion.
- Times are generated on a UTC clock and written as New York local time. Most courses start shortly before the
  March 8 or November 1, 2026 change (157 patients' courses cross one); no timestamp falls in the repeated hour
  01:00 to 01:59 on November 1. About 30 percent of patients have a laboratory that reports umol/L (written to 0.1
  umol/L, answers computed from the written value times 1.4493; 65 patients kept it after the margin checks).
  About 15 percent of usable results get an earlier wrong result with the same accession and a later corrected one
  (71 patients).
- Answers are fitted from the written records. Planted patients have one level moved on its 0.1 grid so the AUC
  sits 0.6 to 2 percent from 400 or 600, or the unrounded new dose 0.6 to 2 percent from a rounding midpoint.
  Every patient keeps both margins at least 0.6 percent, more than the 0.5 percent tolerance, and must have exactly
  one exact (clearance, volume) solution in a 7 x 7 multistart Newton search over 0.001 to 60 L/h and 3 to 3,000 L.
- `sim.py` is the generator's own model (third implementation; closed-form propagation between breakpoints, nested
  bisection, and the multistart uniqueness search).
- `sources/rybak_2020_vancomycin_guideline.txt` is the text of the guideline extracted from the PDF. The rules
  used come from pages 839 to 840 (AUC/MIC 400 to 600; first-order equations need near steady-state levels and are
  hard to use with irregular dosing; the AUC from the sampling period, and changes of the total daily dose giving
  proportional changes in the AUC), page 842 (Recommendation 6: assume an MIC of 1 mg/L; do not lower the dose
  when the broth microdilution MIC is below 1 mg/L), page 844 (infusion at most 5 mg/mL and at least 1 hour per
  1,000 mg; loading doses 20 to 35 mg/kg up to 3,000 mg), page 845 (peak drawn at least 1 hour after the end of
  the infusion) and page 846 (substantial clearance by contemporary high-permeability dialyzers; doses commonly
  given during the final hours of the session).

## Evidence (outputs saved in `evidence/`)
- `check_agreement.py` -> `evidence/agreement.txt`: solution, engine and generator agree on all 240 patients; it
  also prints the per-family patient counts, the closest values to the target edges and rounding midpoints, and
  the check that every patient has exactly one clearance and volume. Every count quoted in the READMEs comes from
  this file or from `evidence/generate_output.txt`.
- `local_check.py ..` -> `evidence/local_check.txt`: oracle passes every test, empty output fails.
- `calibrate.py` -> `evidence/calibration.txt`: shortcut solutions and how many patients each gets wrong.
- `generate.py` -> `evidence/generate_output.txt`: counts of patterns, exposures, irregularities and planted
  values (counts of events such as doses during dialysis include patients the generator later redrew).

## Settled readings (stated in instruction.md)
Times are New York local time (America/New_York); results are in mg/L or umol/L (vancomycin 1449.3 g/mol); a
corrected result replaces the earlier result with the same accession; hemodialysis.csv gives each session and the
dialyzer's vancomycin clearance. One-compartment model with first-order elimination at the patient's own
clearance, plus the dialyzer's clearance while a session runs, fitted to the two usable levels and everything
documented as given. Usable levels are reported values not drawn during an administration (pauses included) or a
dialysis session, or less than 1 hour after an administration stopped. No Bayesian estimation or population
priors; only the administration record decides what was given and when; nothing rounded before the final values.
ke_per_h is the patient's own rate off dialysis; auc48 from the first administration's start; auc24 over the 24
hours before the later usable level; exposure against 400 to 600 with the MIC taken as 1 mg/L for everyone
(Recommendation 6); new dose is the most recently ordered maintenance dose, unchanged when within, otherwise
scaled in proportion to bring auc24 to 500 and rounded to the nearest 250 mg.

## Notes
Five drawn patients had two exact (clearance, volume) solutions (for example two pre-dialysis levels that a slower
clearance with a larger volume fits as well as a faster clearance with a smaller one); the generator redraws such
patients so the answer is unique.
