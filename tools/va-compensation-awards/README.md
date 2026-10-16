# va-compensation-awards dev tools (never upload these)

- `generate.py` (seed 38400) writes `tasks/va-compensation-awards/environment/data/` (veterans.json,
  disabilities.json, rating_decisions.json, dependents.json, compensation_rates.json), the verifier copy in
  `tests/data/`, `tests/case_tags.json` and `tests/golden.json` (22 planted veterans worked by hand, 990 rows;
  222 veterans, 9,990 rows in all; hospital_and_convalescence.json added in v2). Its `sim` is the third implementation; in strict mode it rejects any veteran
  whose answer needs an open reading. `sim_answers.json` holds its answers (dev only).
- `calibrate.py` (needs writable `/app`): oracle passes, empty output fails, 38 misreadings each fail a test.

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

## v2 (after a blind trial solved v1 7,200/7,200)
Built from the rule text the author pasted (rule_text.md): 3.31 (with (c)(5)), 3.105, 3.400, 3.401, 4.25, 4.26 (2023
amendment), 4.29, 4.30. Added: 4.29 hospital totals with the authorized-absence rules ((a)(1) more than 4 days or
more than 8 in total in the first 21 days, (a)(2) more than 14 days later), treatment beginning after admission
(4.29(b)) and convalescence months (4.29(e)); 4.30 convalescent totals; the same-month payment exception
3.31(c)(5); reductions under 3.105(e); Table I rounding as the official method (exact arithmetic now gives wrong
answers); 4.26(b) for four extremities and the 4.26(d) most favorable exclusion; boundary-dense filler (claims,
increases and dependent reports on the one-year date or the day after under 3.110).
Open readings kept out: one-year limits ending on a weekend or holiday with receipt in the 3.110(b) extension;
absences near day 21 and hospitalizations of 20 to 23 days (day counting); more than one 14-day absence (the
"third consecutive" clause); long absences with convalescence; bilateral values ending in .5 when the rounding
changes the rating; 60-day reduction periods ending near a month boundary or on a weekend that moves the month;
reductions that do not lower the payment, during separation-pay recovery, or near a temporary total; temporary
totals that overlap each other or a rating change; late dependent reports after a newly established qualifying
rating (3.401(b) against 5110(f)).
- v2 blind trial (fresh agent, cold): 9,850/9,990 rows, 54 veterans wrong. It raised two open readings that were then
  removed from the data: a return after an absence treated as discharge (a fresh 21-day count?) and treatment
  before service connection (4.29(b) "if otherwise in order"); stays with absences now end within 19 days of the
  absence that counts as discharge, the 21-day test gives the same answer with or without the days away, and stays
  are only for disabilities already service connected. Rerunning the trial's own script on the corrected data:
  every remaining wrong row traces to a misreading under the pasted text: 3.31(c)(5) applied to 4.30 ratings and
  to 4.29 stays whose convalescence months run past the month ("including any period of post-hospitalization
  convalescence"), and the 4.26(d) most favorable exclusion. A second 4.26(d) veteran and single-month stays
  (with and without convalescence) were added for density.
