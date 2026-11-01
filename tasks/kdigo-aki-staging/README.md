# kdigo-aki-staging

Acute kidney injury in 120 adult ICU admissions, defined and staged under the KDIGO Clinical Practice Guideline for
Acute Kidney Injury (Kidney Int Suppl 2012;2:1-138), Recommendations 2.1.1 and 2.1.2 (Table 2). For every admission
the agent reports the highest stage reached, when a criterion was first met and when that stage was first reached.

## Difficulty

Intensivists and nephrologists stage acute kidney injury every day, and quality audits, trials and alert systems
depend on doing it exactly. The guideline gives the criteria; the work is applying all of them together to raw ICU
records. Creatinine criteria are judged at every result: 1.5, 2.0 and 3.0 times the known baseline, a rise of at least
0.3 mg/dl over any result in the previous 48 hours, and a rise to 4.0 mg/dl or more (which reaches stage 3 even when
the ratio is lower, for the patients with a high baseline). Initiation of renal replacement therapy is stage 3. The
urine output criteria (below 0.5 ml/kg/h for 6 and for 12 hours, below 0.3 ml/kg/h for 24 hours, anuria for 12
hours) are judged over every period of that length, from volumes charted at irregular intervals of one to four hours:
the moment a criterion is first met usually falls between chartings, and a solver that only checks periods ending at a
charting gets 65 admissions wrong. The highest stage and its time come from whichever criterion gives it first.
Results are planted at the decision edges: creatinine ratios within 0.3 to 3 percent of 1.5, 2.0 and 3.0, high
baselines rising to 3.92 to 4.12 mg/dl, oliguric episodes at average rates within 1.2 to 12 percent of 0.5 and 0.3
ml/kg/h, and anuric episodes of 9 to 17 hours. The records carry real laboratory and charting detail: 371 results in
umol/L, 83 corrected results replacing an earlier result with the same accession, 55 rejected or cancelled
specimens, and 76 admissions crossing a 2026 clock change in New York local time. Counts are in
authoring/evidence/agreement.txt; each of 12 shortcuts tried (authoring/evidence/calibration.txt) gets admissions
wrong.

## Solution

The reference solution (solution/solve.py) converts New York local times to a continuous clock, keeps each corrected
result in place of its original, converts umol/L at 88.4, and evaluates every creatinine criterion at every result.
It builds each admission's cumulative urine volume, linear within each charting interval, and for each urine
criterion finds the earliest end of a period of that length whose volume falls below the limit (weight times rate
times hours) by solving on the piecewise-linear volume between the chartings and the chartings shifted by the period.
It adds renal replacement therapy as stage 3 and reports the highest stage, the first time any criterion was met and
the first time the highest stage was reached.

## Verification

The verifier recomputes every admission with its own independently written engine (tests/engine.py: bisection for
the moment a urine criterion is met) from a private copy of the inputs, and never runs agent code. The generator
(authoring/generate.py) is a third implementation; stages agree on every admission and times within 2e-9 minutes.
The engine is checked against a hand-worked admission (tests/golden.json). Generated admissions are redrawn when a
creatinine ratio is within 0.2 percent of a threshold, a rise within 0.004 mg/dl of 0.3 or a pair within 10 minutes of
48 hours, a value within 0.004 of 4.0, or a urine period average within 1 percent of a limit, so careful
implementations cannot disagree. Tests check input consistency, formats, one row per admission in order, one test
per reading (tests/case_tags.json) and finally every admission: stage exact, times within 1 minute. Reward is 1 only
if every test passes.
