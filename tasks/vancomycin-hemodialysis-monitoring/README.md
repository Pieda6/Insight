# vancomycin-hemodialysis-monitoring

Vancomycin dosing by predialysis-concentration monitoring for 150 patients with MRSA infections on maintenance
hemodialysis (1,652 sessions), under the 2020 consensus guideline of ASHP, IDSA, PIDS and SIDP (Rybak et al., Am J
Health-Syst Pharm 2020;77:835-864). For every session the agent reports the predialysis level that counts, its
status against the guideline's predialysis target, and the dose.

## Difficulty

Dialysis pharmacists dose vancomycin this way, and the guideline supplies the rules: Recommendation 13 (page 847)
gives loading and maintenance doses in mg/kg by dialyzer permeability and by whether the dose is given during or
after the session; Recommendation 14 sets the predialysis target and says predialysis monitoring should drive
subsequent dosing, with the weight-based doses only a starting point until concentrations have been determined;
page 848 says blood for vancomycin concentrations should not be drawn during or for at least 2 hours after a
hemodialysis treatment; page 845 caps loading doses. None of these numbers is in the instruction. The answer for
each session depends on the earlier ones: weight-based doses (from that session's weight, dialyzer and timing) until
a level has been determined, then the previous dose, changed in proportion when a level is out of range, so one
wrong decision changes every later dose of that patient. Levels are planted at the decision edges: results at or
within a few tenths of 15 and 20 mg/L, also through the umol/L conversion; draws at 118 to 122 minutes before a
session start; draws just before and after two hours from the end of an interrupted run resumed the same day;
repeat draws where the latest counts. The records carry the details real laboratory data has: 413 results in
umol/L, 109 corrected results replacing an earlier result with the same accession, and 97 rejected or cancelled
specimens; 39 patients change dialyzer or dose timing during the course. Statuses: 718 sessions without a usable
level, 225 below, 358 within, 351 above (counts in authoring/evidence/agreement.txt). Each shortcut tried
(authoring/evidence/calibration.txt, 15 in all) gets many sessions right and others wrong.

## Solution

The reference solution (solution/solve.py) converts New York local times to a continuous clock, keeps each corrected
result in place of its original, converts umol/L to mg/L, and walks each patient's sessions in time order. For each
session it takes the latest numeric result drawn no more than 2 hours before the start and not during or less than 2
hours after an earlier session, classifies it against 15 to 20 mg/L, and sets the dose: the loading dose (at most
3,000 mg) at the first session; afterwards the weight-based maintenance dose until a level has been determined and
the previous dose after that, changed by 17.5 over the level when the level is out of range; every dose rounded to
the nearest 250 mg.

## Verification

The verifier recomputes every session with its own independently written engine (tests/engine.py) from a private
copy of the inputs that exists only in the verifier image, and never runs agent code; the generator
(authoring/generate.py) is a third implementation, and all three agree on every session. The engine is checked
against a hand-worked five-session patient (tests/golden.json) covering the loading dose, a proportional increase
from the weight-based dose, a proportional decrease after a umol/L result, a session without a level, and a level
excluded by the two-hour rule after an interrupted session. Tests check input consistency, the value formats, one row
per session in order, one test per reading (tests/case_tags.json lists the sessions whose row changes if that
reading is misread) and finally every session: levels within 0.05 mg/L, status and dose exact. No dose sits within
0.2 mg of a 250 mg rounding midpoint, so careful implementations cannot disagree. Reward is 1 only if every test
passes.
