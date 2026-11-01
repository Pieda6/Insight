# Authoring tools for kdigo-aki-staging

These files are not copied into the agent or verifier images. Run them from this folder. None of them writes
`__pycache__`.

## Provenance
- `sources/kdigo_2012_aki_section2.txt`: text of Section 2 of the KDIGO Clinical Practice Guideline for Acute
  Kidney Injury (Kidney Int Suppl 2012;2:1-138): Recommendation 2.1.1 (definition), 2.1.2 and Table 2 (staging), and
  the accompanying text that patients are staged by the criteria giving the highest stage.
- `generate.py` (seed 20120301) builds 120 admissions and writes both data copies, `evidence/answers.json` and
  `../tests/case_tags.json`. Admissions of 3.0 to 6.9 days starting near the March 8 or November 1, 2026 clock
  changes or in July; weights 50 to 120 kg; baseline creatinine 0.60 to 1.60 mg/dl, or 1.75 to 2.40 for 15 percent
  (who rise to 3.92 to 4.12 mg/dl); peak ratios near 1.5, 2.0 or 3.0 for half the admissions; creatinine every 6 to 26
  hours with 1.5 percent assay noise, 30 percent of patients reported in umol/L, 10 percent of results corrected and 6
  percent rejected or cancelled; renal replacement therapy for 45 percent of admissions with a peak ratio of at least
  2.4 (7 started). Urine charted every 1 to 4 hours (integer ml) at 0.6 to 1.6 ml/kg/h with one episode: mild 0.40 to
  0.56 ml/kg/h for 4.5 to 15 hours, moderate 0.18 to 0.45 for 11 to 32 hours, or anuric for 9 to 17 hours.
- Redraw rules (44 drawn admissions were redrawn) are listed in the README.

## Settled readings
From the guideline: the definition and every staging criterion of Table 2; staging by the highest stage any
criterion gives. Stated as facts in instruction.md: the known creatinine before admission is the baseline and every
rise happened during the admission (so the 7-day presumption holds; every admission lasts at most 7 days); a result
counts from the time the blood was drawn; urine flowed evenly over each charting interval; output per kg uses the
weight at admission; a urine criterion is met at the first moment the urine over the stated hours just before it meets
it, within the charted record; 88.4 umol/L per mg/dL.

## Evidence (outputs saved in `evidence/`)
- `agreement.txt`: solution, engine and generator agree on all 120 admissions, with every count quoted in the READMEs.
- `local_check.txt` (`python3 local_check.py ..`): oracle passes every test, empty output fails.
- `calibration.txt` (`calibrate.py`): 12 shortcut solutions and how many stages each gets wrong.
- `generate_output.txt`.
