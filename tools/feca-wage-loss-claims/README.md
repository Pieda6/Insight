# feca-wage-loss-claims dev tools (never upload these)

- `generate.py` (seed 81180) writes `tasks/feca-wage-loss-claims/environment/data/` (employees.json, claims.json,
  time_and_attendance.json, medical_evidence.json, cost_of_living_adjustments.json), the verifier copy in `tests/data/`,
  `tests/case_tags.json` and `tests/golden.json` (23 claims worked by hand; 323 claims in all). Its `sim` is the third
  implementation; in strict mode it rejects any claim whose answer would depend on an open reading.
  `sim_answers.json` holds its answers (dev only).
- `calibrate.py` (needs writable `/app`): oracle passes, empty output fails, 36 misreadings each fail a test.
- `rule_text.md`: the rule text pasted by the author (20 CFR 10.5, Subpart C 10.200-10.224, Subpart E 10.400-10.441;
  5 U.S.C. 8105, 8110, 8114, 8117, 8118).

## Why this task (after va-compensation-awards was solved 2/2)
The accepted HOS task is a minute-level engine over raw logs with several clocks that recalculate each other. VA was a
monthly step function whose traps were rule details GPT knows. Here every answer comes from a day-by-day walk of time and
attendance records: the 45 calendar days of COP (injury day by time of injury against shift start, partial days, leave,
regular days off from the adjoining workdays and medical evidence, part-time calendar days, the 10.207 window after the
first return), then spells of pay loss with the 8117 waiting period, the 10.5(s) pay rate, 8110 augmentation day by
day and 10.420 COLAs. A misplaced day moves the 45th COP day and every later day of compensation.

## Open readings kept out of the data
- The waiting period after COP or leave (8117(a)(1) "disability exceeds 14 days" against 8118(c) and 10.401(a) "pay
  loss continues for more than 14 calendar days"): pay loss after COP or leave, and every later spell, is longer than
  14 days; short spells occur only on claims with no COP and no leave before them.
- Days off counted only because they adjoin leave (10.215(d) "COP has been used" against (e) "as if in COP status").
- A day off counted only through a following workday that falls past the 45-day cap.
- Pay loss beginning or ending next to days off that the medical evidence covers; pay loss without medical evidence;
  partial days of pay loss; part-time pay loss (10.216(b) rates).
- Holidays next to the edges of COP or pay-loss stretches; injuries at the minute the shift starts.
- Appointment days after the 10.207 window; recurrences within 3 days of six months after the return; disability
  beginning within 3 days of a year before a COLA that falls in the pay loss; a pay change between the first disabled
  day off and the first absence.
Settled by fact sentences: no Postal Service employees; every claim, absence, recurrence (CA-2a, regular pay elected)
and medical period accepted; COP not payable becomes leave without pay; weekly basis paid in sevenths, exact until the
claim total; no 10.406 limits reached; dependents in the household; day counting.
