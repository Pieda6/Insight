# vancomycin-hemodialysis-monitoring

Vancomycin dosing by predialysis-concentration monitoring for 150 patients with MRSA infections on maintenance
hemodialysis (1,633 sessions), following the 2020 consensus guideline of ASHP, IDSA, PIDS and SIDP (Rybak et al.,
Am J Health-Syst Pharm 2020;77:835-864) and the unit's written dosing policy (data/protocol.md). For every session the agent reports the
predialysis level that counts, its status against 15 to 20 mg/L, and the dose.

## Difficulty

Dialysis pharmacists dose vancomycin this way: the guideline's Recommendation 13 gives loading and maintenance
doses by dialyzer permeability and by whether the dose is given during or after the session, and Recommendation 14
makes predialysis concentrations drive later dosing. The answer for each session depends on every earlier session:
the current maintenance dose is carried forward, changed in proportion when a level is out of range, held above 25
mg/L with the changed dose applying from the next session, and restarted from the table when the dialyzer or the
timing changes (42 patients). One wrong decision changes every later dose of that patient until a restart. Which
level counts depends on the guideline's sampling advice for hemodialysis (page 848: not during or for at least 2
hours after a treatment), which matters for patients with an interrupted session resumed the same day. Levels are
planted at the decision edges: results at or within a few tenths of 15, 20 and 25 mg/L, also through the umol/L
conversion; draws at 118 to 122 minutes before a session start; draws just before and after two hours from the end
of an interrupted run; repeat draws where the latest counts. The records carry the details real laboratory data has:
496 results in umol/L, 109 corrected results replacing an earlier result with the same accession, and 90 rejected
or cancelled specimens. Statuses: 739 sessions without a usable level, 193 below, 214 within, 487 above, with 226
held doses (counts in authoring/evidence/agreement.txt). Each shortcut tried (authoring/evidence/calibration.txt, 15
in all) gets many sessions right and others wrong.

## Solution

The reference solution (solution/solve.py) converts New York local times to a continuous clock, keeps each
corrected result in place of its original, converts umol/L to mg/L, and walks each patient's sessions in time
order. For each session it takes the latest numeric result drawn no more than 2 hours before the start and not
during or less than 2 hours after an earlier session, classifies it against 15 to 20 mg/L, and sets the dose: the
capped loading dose at the first session, a restart from the table on a dialyzer or timing change, otherwise the
current maintenance dose changed by 17.5 over the level when out of range (held above 25 mg/L), each dose rounded to
the nearest 250 mg when it is set.

## Verification

The verifier recomputes every session with its own independently written engine (tests/engine.py) from a private
copy of the inputs that exists only in the verifier image, and never runs agent code; the generator
(authoring/generate.py) is a third implementation, and all three agree on every session. The engine is checked
against a hand-worked five-session patient (tests/golden.json) covering the loading dose, a proportional increase, a
held dose after a umol/L result above 25 mg/L, a session without a level, and a restart with a level excluded by the
two-hour rule. Tests check input consistency, the value formats, one row per session in order, one test per
reading (tests/case_tags.json lists the sessions whose row changes if that reading is misread) and finally every
session: levels within 0.05 mg/L, status and dose exact. No dose sits within 0.2 mg of a 250 mg rounding midpoint,
so careful implementations cannot disagree. Reward is 1 only if every test passes.
