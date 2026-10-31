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
  A predialysis draw 3 to 115 minutes before about 65 percent of sessions after the first (never less than 2 hours
  after the previous session); 45 percent of values at or within 1.5 mg/L of 15 or 20; 12 percent corrected later
  under the same accession; rejected or cancelled specimens; draws during 15 percent of sessions; post-dialysis
  draws after 40 percent of sessions, within 2 hours of the end when the next session has its own predialysis draw,
  otherwise sometimes at 116 to 125 minutes; for an interrupted session, a draw between the two runs 110 to 135
  minutes after the first run ended. 30 percent of patients have a
  laboratory reporting umol/L (to 0.1 umol/L; answers use the written value times 1.4493).
- Patients are redrawn when a dose would sit within 0.2 mg of a rounding midpoint, a level within 0.0001 mg/L of 15
  or 20 other than exactly, or more than one result the sampling advice allows for one session.
- `sources/rybak_2020_vancomycin_guideline.txt`: the guideline text. Rules used: Recommendation 13 table (page 847:
  loading 25 mg/kg after dialysis, 30 or 35 mg/kg intradialytic for low or high permeability; maintenance 7.5
  or 10 mg/kg after dialysis, 7.5 to 10 or 10 to 15 mg/kg intradialytic); Recommendation 14 (predialysis 15 to 20
  mg/L, monitoring drives subsequent dosing, page 847); page 848 sampling advice (not during or for at least 2 hours
  after hemodialysis); page 845 (loading doses not exceeding 3,000 mg).

## Settled readings
From the guideline: Recommendation 13 doses by permeability and timing; Recommendation 14 target of 15 to 20 mg/L and
monitoring driving subsequent dosing once concentrations have been determined (weight-based doses as the starting
point); no sampling during or for at least 2 hours after hemodialysis (page 848); loading doses at most 3,000 mg
(page 845). Stated as facts in instruction.md: each result belongs to the session that follows it; midpoint of a dose range; the weight before that session; 17.5 mg/L as the aim of a dose change (the
proportional change itself follows the guideline, page 840); doses prepared to the nearest 250 mg.

## Evidence (outputs saved in `evidence/`)
- `agreement.txt`: solution, engine and generator agree on all 1,651 sessions, with every count quoted in the READMEs.
- `local_check.txt` (`python3 local_check.py ..`): oracle passes every test, empty output fails.
- `calibration.txt` (`calibrate.py`): 12 shortcut solutions and how many sessions each gets wrong.
- `generate_output.txt`.

## Notes
No draw-to-session interval straddles a clock change, so local times read without daylight saving give the same
intervals; times are still New York local time as stated.
