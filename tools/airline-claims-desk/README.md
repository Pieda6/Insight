# airline-claims-desk dev tools (never upload these)

- `generate.py` (seed 25026) writes `tasks/airline-claims-desk/environment/data/` (claims.json,
  flights.json, airports.json, carrier.json, federal_holidays.json), the identical verifier copy in
  `tests/data/`, `tests/case_tags.json` and `tests/golden.json` (75 planted claims, hand-worked).
- `calibrate.py` (needs writable `/app`): oracle passes, empty output fails, 36 misreadings each fail
  at least one test.

v2 (after deep review): 260.4 refunds unused extras even when a voucher is accepted; declining a
change that is not significant owes nothing (stated in the instruction); covered flight / break in
journey (260.2); due dates counted from the earliest date under 260.6(a)(2) instead of a given
trigger date. Where a 260.4 refund could run from either the notice or the request, the data makes
them the same day.

Rule text used (pasted by the author from law.cornell.edu): 14 CFR 250.1, 250.2, 250.2a, 250.2b,
250.5, 250.6, 250.8; 260.2, 260.3, 260.4, 260.5, 260.6, 260.7, 260.10.
