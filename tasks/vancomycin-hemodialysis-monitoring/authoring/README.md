# Authoring tools for vancomycin-hemodialysis-monitoring

These files are not copied into the agent or verifier images. Run them from this folder. None of them writes
`__pycache__`.

## Provenance
- `generate.py` (seed 20200346) builds 150 patients and writes both data copies, `evidence/answers.json` and
  `../tests/case_tags.json`. Thrice-weekly sessions (Monday, Wednesday, Friday or Tuesday, Thursday, Saturday) of
  210 to 240 minutes, 9 to 13 per patient, starting 05:00 to 13:00 near the March 8 or November 1, 2026 clock
  changes or in June; 20 percent of patients have one session interrupted and resumed 150 to 230 minutes later.
  Dialyzer high permeability (70 percent) or low, dose given intradialytically or after dialysis (half each); 30
  percent of patients change one of them during the course. Weights 52 to 112 kg, drifting up to 1.2 kg per session.
  Levels before about 65 percent of sessions after the first, 18 percent of them drawn 118 to 122 minutes before the
  start; 45 percent of values at or within 1.5 mg/L of 15, 20 or 25; 12 percent corrected later under the same
  accession; repeat draws, rejected or cancelled specimens and post-dialysis levels. 30 percent of patients have a
  laboratory reporting umol/L (to 0.1 umol/L; answers use the written value times 1.4493).
- Patients are redrawn when a dose would sit within 0.2 mg of a rounding midpoint, a level within 0.0001 mg/L of 15,
  20 or 25 other than exactly, or a draw within 0.5 minute of the window edge other than exactly.
- `sources/rybak_2020_vancomycin_guideline.txt`: the guideline text. Rules used: Recommendation 13 table (page 847:
  loading 25 mg/kg after dialysis, 30 or 35 mg/kg intradialytic for low or high permeability; maintenance 7.5
  or 10 mg/kg after dialysis, 7.5 to 10 or 10 to 15 mg/kg intradialytic); Recommendation 14 (predialysis 15 to 20
  mg/L, monitoring drives subsequent dosing, page 847); page 848 sampling advice (not during or for at least 2 hours
  after hemodialysis); page 845 (loading doses not exceeding 3,000 mg).

## Settled readings (the unit's protocol, stated in instruction.md)
Middle of a range in the table; the session's own weight; loading at the first session in the data; the latest
numeric result drawn no more than 2 hours before the start, among those the sampling advice allows; proportional
change to 17.5 mg/L outside 15 to 20, given at that session; hold above 25 with the changed dose applying from the
next session; current dose starting at the second session's weight-based maintenance dose and restarting on a
dialyzer or timing change; rounding to 250 mg when set, the rounded dose carried forward.

## Evidence (outputs saved in `evidence/`)
- `agreement.txt`: solution, engine and generator agree on all 1,633 sessions, with every count quoted in the READMEs.
- `local_check.txt` (`python3 local_check.py ..`): oracle passes every test, empty output fails.
- `calibration.txt` (`calibrate.py`): 15 shortcut solutions and how many sessions each gets wrong.
- `generate_output.txt`.

## Notes
No draw-to-session interval straddles a clock change, so local times read without daylight saving give the same
intervals; times are still New York local time as stated.
