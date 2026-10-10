# auto-ad-clearance dev tools (never upload these)

- `generate.py` (seed 1026) writes `tasks/auto-ad-clearance/environment/data/` (deal_worksheets.json,
  ads.csv, dealer_group.json), the identical verifier copy in `tests/data/`, `tests/case_tags.json`
  and `tests/golden.json` (128 ads, expected outcome derived from scenario intent with the
  generator's own Newton APR solver).
- `calibrate.py` (needs writable `/app`): oracle passes, empty output fails, and 22 misreadings of
  Regulation Z each fail at least one test (fee classification shortcuts, spreadsheet RATE(),
  actual-day fraction, wrong tolerances, trigger-term mistakes, rate label, rate increase,
  broadcast alternative misuse, partial repayment terms).

Rule text used (pasted by the author from law.cornell.edu / consumerfinance.gov):
12 CFR 1026.4, 1026.18, 1026.22, 1026.24, Appendix J, and Supplement I comments to 1026.4 and 1026.24.
