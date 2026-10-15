# cobra-claims-review dev tools (never upload these)

- `generate.py` (seed 49800) writes `tasks/cobra-claims-review/environment/data/` (plan.json, people.json,
  events.json, elections.json, premium_payments.json, claims.json), the verifier copy in `tests/data/`,
  `tests/case_tags.json` and `tests/golden.json` (118 hand-worked claims from 46 planted families; 215 families,
  475 people, 9,578 payments, 3,587 claims in all). Its `sim` is a third implementation that re-checks every
  hand-worked answer and, in strict mode, rejects any filler family that needs an open reading. `sim_answers.json`
  holds its answers for every claim (dev only).
- `calibrate.py` (needs writable `/app`): oracle passes, empty output fails, 65 misreadings (source edits of the
  reference solution) each fail at least one test.

## Why this replaced ssdi-work-review
SSDI (one counter and one state machine per person) was solved 2/2 in 6 minutes, like airline and Medicare. The
tasks that passed (hours of service, FMLA) had several windows and caps that change each other. Here the 18, 29 and
36-month periods, the window in which a second event counts, the 150% premium months, the 45-day first payment
window, the shortfall margin and notices, and early termination all interact per person and per family.

## Open readings kept out of the data
- Loss-of-coverage date (last covered day or first day without): no election falls on the one day that differs.
- First 60 days of COBRA: no disability onset on day 61 (Apr 1 + 60).
- Second-event notice measured from the event or from the loss of coverage it causes: late notices are always
  later than 60 days after the first of the next month.
- A disabled beneficiary with a second event (150% through month 36?) or with the Medicare-before period.
- Others keeping 29 months after the disabled person's own coverage ended: no such claims after month 18.
- A disabled person who never validly elected; a determination before COBRA began.
- Death as a second event: every dependent sends a timely notice, so the employer-notice reading agrees.
- Other coverage or Medicare beginning on the election day; claims on the first day of other coverage or Medicare,
  or the day after a period counted from the employee's Medicare date.
- A shortfall of exactly 10%; a shortfall notice on a payment short by more than the margin; any date after the
  files' as-of date (Oct 15, 2026).
Settled by fact sentences: coverage ends at the end of the month of the event and COBRA starts the next day, which
is the loss date and the start of every measured period; month and day counting; dates sent; divorce, 26th
birthday and employee Medicare effect on eligibility; single coverage; rounding; no reinstatement.

Rule text used: 26 CFR 54.4980B-2 (qualifying events), -3 (qualified beneficiaries), -6 (election), -7 (duration:
Q/A-1 early termination, Q/A-4 maximum period, Q/A-5 disability, Q/A-6 second events, Q/A-7 Medicare before),
-8 (premiums: 102% / 150%, 30-day grace, 45 days after election, shortfall of the lesser of $50 or 10%).

## History
- v1: artificiality A6 FAIL: the task.toml explanations spelled out the rules' conditions ("only if", "the later of",
  "the first failure"). v2 rewrote them to cite the provisions.
- v2: Pass@2 blocked with 1 valid trial (the other hit AgentSetupTimeoutError), and that trial solved all 2,922
  claims in 7 minutes: every rule was textbook COBRA. v3 adds rules that are clear in the text but not the first
  reading: 54.4980B-10 (the event of an employee who does not return from FMLA leave is the last day of the leave,
  not the recorded termination), 54.4980B-6 Q/A-4 (a revoked waiver gives coverage only from the revocation, with
  the plan giving the least coverage the rules allow), a child the plan keeps covering past 26 because of a
  disability (the birthday is no second event), and spouses' own Medicare after the election. It drops instruction
  sentences that gave answers away (no reinstatement, the day-before end, claims on or after COBRA's start).
  Open readings kept out: FMLA termination recorded in the same month as the leave ends; other events between the
  leave and the recorded termination; a disabled beneficiary who waived; claims on the revocation date; partial
  payment in a revocation month (always paid in full, so proration does not matter).
- v3: Pass@2 2/2 solved in 9 minutes (gpt-6.1-sol). The yes/no answer per claim checked each rule in isolation;
  the passed Operations/Claims task (fmla-absence-claims) asks for a number from a running ledger, so one wrong
  decision changes later answers. v4 asks for the plan payment of every claim: each person's deductible and
  out-of-pocket maximum per calendar year across active coverage and COBRA (54.4980B-5 credit), uncovered claims
  count for nothing, coinsurance rounded half up. Claims under active coverage before the loss of coverage are in
  the file. The instruction follows the FMLA task's layout. Open reading kept out: whether the out-of-pocket maximum
  (not only the deductible) carries into COBRA; the generator drops active claims of any person where it would
  change a payment. Planted claims exceed every deductible so coverage always shows in the payment.
