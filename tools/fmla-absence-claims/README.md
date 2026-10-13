# fmla-absence-claims dev tools (never upload these)

- `generate.py` (seed 82500) writes `tasks/fmla-absence-claims/environment/data/` (employers.json, employees.json,
  absences.json), the verifier copy in `tests/data/`, `tests/case_tags.json` and `tests/golden.json` (24 hand-worked
  absences from 12 planted employees; 87 employees, 1,615 absences in all). Its `sim` is a third implementation that
  re-checks the hand-worked answers and rejects filler histories that need an open reading.

Open readings kept out of the data: an entitlement running out inside a full week that contains a holiday; a full
week split between two reasons; intermittent leave before the 12-month anniversary (825.110(d) vs the single-leave
eligibility rule); caregiver leave at the forward-from-first-leave employer (does it open the employer's period?);
caregiver leave after the single period ends; two absences on one day; February 29 anchor dates; overtime and
varying schedules (825.205(b)(3)).

Built without pasted rule text (the author's device was nearly out of battery); provisions used: 29 CFR 825.110(a),
(d); 825.120(a)(2); 825.127(e); 825.200(a)-(c), (h); 825.205(b).
