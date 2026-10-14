# fmla-absence-claims dev tools (never upload these)

- `generate.py` (seed 82500) writes `tasks/fmla-absence-claims/environment/data/` (employers.json, employees.json,
  absences.json), the verifier copy in `tests/data/`, `tests/case_tags.json` and `tests/golden.json` (39 hand-worked
  absences from 17 planted employees; 92 employees, 1,630 absences in all). Its `sim` is a third implementation that
  re-checks the hand-worked answers and rejects filler histories that need an open reading.

Open readings kept out of the data: an entitlement running out inside a full week that contains a holiday; a full
week split between two reasons; intermittent leave before the 12-month anniversary (825.110(d) vs the single-leave
eligibility rule); caregiver leave at the forward-from-first-leave employer (does it open the employer's period?);
caregiver leave after the single period ends; two absences on one day; February 29 anchor dates; overtime and
varying schedules (825.205(b)(3)).

Built without pasted rule text (the author's device was nearly out of battery); provisions used: 29 CFR 825.110(a),
(d); 825.120(a)(2); 825.127(e); 825.200(a)-(c), (h); 825.205(b).

## History
- v1: Pass@2 0/2 (7.5 min) but deep review FAIL: the oracle charged intermittent leave on a holiday, which
  825.200(h) excludes for leave of less than a week unless the employee works holidays. Both trials applied the
  rule correctly. Re-running the fixed rules on the v1 data changes 34 answers, including every id the reviewer
  cited (A0048 3.00->0.00, A0102 10.00->0.00, A0366 249->255, A0533 0->4), so the residual divergences were
  knock-on effects of the same bug. v2 fixes solve.py, engine.py and the generator's sim, adds 15 hand-worked
  absences (intermittent holidays with and without holiday work, exhaustion around a holiday, closure inside a
  long leave, caregiver plus ordinary leave reaching both limits), states that no employee has two absences on
  one day, and tests it.
