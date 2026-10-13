# airline-claims-desk dev tools (never upload these)

- `generate.py` (seed 25026) writes `tasks/airline-claims-desk/environment/data/` (claims.json,
  flights.json, airports.json, carrier.json, federal_holidays.json), the identical verifier copy in
  `tests/data/`, `tests/case_tags.json` and `tests/golden.json` (82 planted claims, hand-worked; 172 claims in all).
- `calibrate.py` (needs writable `/app`): oracle passes, empty output fails, 40 misreadings each fail
  at least one test.

v2 (after deep review): 260.4 refunds unused extras even when a voucher is accepted; declining a
change that is not significant owes nothing (stated in the instruction); covered flight / break in
journey (260.2); due dates counted from the earliest date under 260.6(a)(2) instead of a given
trigger date. Where a 260.4 refund could run from either the notice or the request, the data makes
them the same day.

v3 failed Pass@2 (2/2 solved in about 9 minutes): every rule was a short lookup. v4 publishes
flight times as local wall times at each airport (time zones in airports.json; record timestamps
stay UTC with a Z) and places many flights around the EU (Oct 25) and US (Nov 1) 2026 clock
changes. Wall times in a repeated hour are never written (the generator rejects such filler claims
and asserts none remain), so every local time names one instant. Planted cases: lateness 2 h 50 m
that reads as 1 h 50 m, a 4 h 20 m stopover that reads as 3 h 20 m, a 3 h retiming that reads as 2 h,
a 25 h London stopover that reads as 24 h, a due date from the UTC (not local) departure date, and
bag segment lengths that read longer than 12 h on the wall clocks.

Rule text used (pasted by the author from law.cornell.edu): 14 CFR 250.1, 250.2, 250.2a, 250.2b,
250.5, 250.6, 250.8; 260.2, 260.3, 260.4, 260.5, 260.6, 260.7, 260.10.
