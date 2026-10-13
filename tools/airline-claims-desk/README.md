# airline-claims-desk dev tools (never upload these)

- `generate.py` (seed 25026) writes `tasks/airline-claims-desk/environment/data/` (claims.json,
  flights.json, airports.json, carrier.json, federal_holidays.json), the identical verifier copy in
  `tests/data/`, `tests/case_tags.json` and `tests/golden.json` (66 planted claims, hand-worked).
- `calibrate.py` (needs writable `/app`): oracle passes, empty output fails, 27 misreadings each fail
  at least one test.

Rule text used (pasted by the author from law.cornell.edu): 14 CFR 250.1, 250.2, 250.2a, 250.2b,
250.5, 250.6, 250.8; 260.2, 260.3, 260.4, 260.5, 260.6, 260.7, 260.10.
