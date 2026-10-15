# va-compensation-awards dev tools (never upload these)

- `generate.py` (seed 38400) writes `tasks/va-compensation-awards/environment/data/` (veterans.json,
  disabilities.json, rating_decisions.json, dependents.json, compensation_rates.json), the verifier copy in
  `tests/data/`, `tests/case_tags.json` and `tests/golden.json` (10 planted veterans worked by hand, 450 rows;
  160 veterans, 7,200 rows in all). Its `sim` is the third implementation; in strict mode it rejects any veteran
  whose answer needs an open reading. `sim_answers.json` holds its answers (dev only).
- `calibrate.py` (needs writable `/app`): oracle passes, empty output fails, 26 misreadings each fail a test.

## Why this replaced cobra-claims-review
COBRA was solved 2/2 (v3) and 3,587/3,587 by a blind trial (v4): every rule was a textbook date or amount
check. The passed tasks (hours of service, FMLA) need intricate procedures even when the rules are known; here the
combined ratings table with the bilateral factor, effective dates, the 3.31 payment lag, dependency dates and a
recovery ledger interact per veteran per month.

## Open readings kept out of the data
- Rounding: the rounded table and exact combination (with the bilateral value rounded or not) must give the same
  final rating on every day, otherwise the veteran is rejected; no Table I half values decide anything.
- Bilateral disabilities of both arms and both legs at once (one factor or two?).
- Claims within 7 days of a year after separation; increases first shown within 7 days of a year before the
  claim; dependents reported within 7 days of a year after the event.
- Original claims within the year for a disability first shown after separation ("day following separation or
  date entitlement arose").
- Dependents who existed before an award that starts before its claim (3.401(b) "date of claim" against 5110(f)).
- Increases first shown before the earlier rating's effective date.
- No reductions, severances, temporary totals, TDIU, SMC, 3.324, drill pay, retired pay; children stay under 18;
  marriages continue. A scar is placed on the chest so no skin disability sits on a limb.
Rates are this task's tables (built from the December 1, 2023 veteran-alone rates and the yearly COLAs).
