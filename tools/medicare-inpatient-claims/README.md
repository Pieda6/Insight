# medicare-inpatient-claims dev tools (never upload these)

- `generate.py` (seed 40960) writes `tasks/medicare-inpatient-claims/environment/data/` (beneficiaries.json,
  facilities.json, stays.json, claims.json, part_b_blood.json, part_a_amounts.json), the identical verifier copy
  in `tests/data/`, `tests/case_tags.json` and `tests/golden.json` (65 hand-worked claims from 35 planted
  beneficiaries; 155 beneficiaries, 2,483 stays, 853 claims in all).
- The generator carries a third implementation of the rules (`sim`). It re-checks every hand-worked answer and
  rejects any filler history that needs an open reading (`contested`).
- `calibrate.py` (needs writable `/app`): oracle passes, empty output fails, 37 misreadings (source edits of
  the reference solution) each fail at least one test.

## Blind trials (a separate agent solving cold from instruction, data and rule text)
- HOS (accepted task): 438/439, so it fails, like the real Pass@2 trials. Medicare first build: 927/927. Added
  409.85(c) (SNF coinsurance capped by the facility's daily charge, straddling 2025/2026) and 409.30(a)
  (pre-entitlement days count toward the 3 days) after that run.

## Why this replaced airline-claims-desk
Parts 250/260 decide each airline claim with a short, stateless check; v3, v4 and v5 were solved 2/2 (or 331/332
in a blind trial) in 8 to 12 minutes. Part A cost sharing is stateful like hours of service: benefit periods,
per-period day counters, lifetime reserve and psychiatric counters, calendar-year amounts and blood units all
carry across years of history.

## Open readings kept out of the data
- A nursing-facility stay that starts a benefit period, or a psychiatric stay with no paid days that starts one
  (409.60(a) "receives ... services" for uncovered care).
- Custodial nursing-facility days after a period has ended (would they start a new period?): a custodial tail
  always ends within 61 days of the last skilled day.
- The deductible year for a first paid stay that crosses January 1 (409.82(a)(4)): never in the queue.
- Two hospital stays in the 30 days before a nursing-facility admission, a psychiatric hospital stay as the
  qualifying stay, a qualifying stay that began before entitlement.
- Blood on a day Medicare does not pay for; Part A and Part B blood on the same day.
- Reserve-day elections (none filed; charges always exceed coinsurance, so no deemed election either).
Settled by fact sentences: day counting (admission day to the day before discharge), observation is outpatient,
every hospital meets 1861(e)(1), where the deductible is charged, every stay in the queue is in a period.

Rule text used (pasted by the author from law.cornell.edu): 42 CFR 409.30, 409.60, 409.61, 409.62, 409.63,
409.65, 409.80, 409.82, 409.83, 409.85, 409.87; CMS fact sheets for 2025 and 2026 Part A amounts.
