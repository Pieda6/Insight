# ssdi-work-review dev tools (never upload these)

- `generate.py` (seed 15920) writes `tasks/ssdi-work-review/environment/data/` (beneficiaries.json, earnings.json,
  annual_amounts.json), the verifier copy, `tests/case_tags.json` and `tests/golden.json` (15 hand-worked planted
  claimants; 95 claimants, 2,381 earnings months, 6,237 output rows). Its `sim` is a third implementation that
  re-checks the hand-worked answers and rejects filler that needs an open reading.
- `calibrate.py` (needs writable `/app`): oracle passes, empty output fails, 19 misreadings each fail.

Open readings kept out of the data: work in the 12 months after onset (no trial work period, 404.1592(d)); SGA
before the month of filing (would contradict disability); a grace period running past the extended period; a
first SGA month after the extended period with no cessation inside it; self-employment (80-hour test); averaging
and unsuccessful work attempts (stated as facts); medical improvement; expedited reinstatement.

Built from the author's knowledge of 20 CFR 404.315, 404.621, 404.1574, 404.1576, 404.1592 and 404.1592a; SSA
annual amounts 2018-2025 (TWP 850/880/910/940/970/1050/1110/1160; SGA 1180/1220/1260/1310/1350/1470/1550/1620;
blind 1970/2040/2110/2190/2260/2460/2590/2700).
