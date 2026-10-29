# Authoring tools for vancomycin-auc-dosing

These files are not copied into the agent or verifier images. Run them from this folder.

## Provenance
- `generate.py` (seed 20200601) builds the 240 patients and writes both data copies (`../environment/data`,
  `../tests/data`). True clearance comes from Cockcroft-Gault creatinine clearance (0.05 L/h per mL/min, times
  0.8 to 1.25) and true volume is about 0.7 L/kg (times 0.75 to 1.3). Regimens follow the guideline: maintenance
  doses sized for a spread of exposures every 8, 12 or 24 hours, loading doses of 20 to 35 mg/kg actual weight up
  to 3,000 mg (156 of the 240 patients have a loading dose order; 60 have an order change), bags of at most 5 mg/mL, and at least 1 hour per 1,000 mg. Records
  include late and early starts, held doses, pauses, rate changes, partly given infusions and order changes.
  Two usable levels follow one of four patterns (steady-state peak and trough in one interval, trough then peak
  around one dose, first-day levels, peak and trough two intervals apart), with assay noise of up to 8 percent,
  to 0.1 mg/L; unusable results are rejected specimens, results below the reporting limit, and levels drawn
  during an infusion or less than an hour after one. Answers are fitted from the written records, and planted
  patients have one level moved in 0.1 mg/L steps to sit near a target edge or a rounding step.
- `sim.py` is the generator's own model (third implementation).
- `sources/rybak_2020_vancomycin_guideline.txt` is the text of the guideline extracted from the PDF. The rules
  used come from pages 839 to 840 (AUC/MIC 400 to 600 assuming a broth microdilution MIC of 1 mg/L unless measured
  otherwise; first-order equations need near steady-state levels and are hard to use with irregular dosing),
  page 844 (infusion at most 5 mg/mL and at least 1 hour per 1,000 mg; loading doses 20 to 35 mg/kg up to 3,000
  mg) and page 845 (peak drawn at least 1 hour after the end of the infusion).

## Evidence (outputs saved in `evidence/`)
- `check_agreement.py` -> `evidence/agreement.txt`: solution, engine and generator agree on all 240 patients; it
  also prints the per-family patient counts, the closest values to the target edges and rounding midpoints, and
  the check that every patient has exactly one elimination-rate solution. Every count quoted in the READMEs comes
  from this file or from `evidence/generate_output.txt`.
- `local_check.py ..` -> `evidence/local_check.txt`: oracle passes every test, empty output fails.
- `calibrate.py` -> `evidence/calibration.txt`: 20 shortcut solutions and how many patients each gets wrong.
- `generate.py` -> `evidence/generate_output.txt`: counts of patterns, exposures, irregularities and planted values.

## Settled readings (stated in instruction.md)
One-compartment model with first-order elimination fitted to each patient's two usable levels and everything
documented as given; usable levels are reported values not drawn while an administration was running (pauses
included) or less than 1 hour after it stopped; no Bayesian estimation or population priors; only the
administration record decides what was given and when; nothing rounded before the final values; auc48 from the
first administration's start; auc24_ss on the most recently ordered maintenance regimen; the guideline's AUC/MIC
target and MIC rule (cited, not restated); new dose at the current interval for AUC/MIC 500, to the nearest 250
mg, unchanged when within.

