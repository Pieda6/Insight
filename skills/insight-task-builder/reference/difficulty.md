# Designing a task that passes the difficulty gates without failing the deep review

Two forces pull against each other:
- **Pass@2 / Pass@5** want the model to fail: at most 1 solve in 2 tries, at most 2 in 5.
- **The deep review** wants every expected answer to follow uniquely from the instruction plus the
  cited rule. A task that is hard only because it is ambiguous gets failed.

So the difficulty must come from rules that are clear once read carefully, but that a strong model
applies wrong, together with exact computation where one slip changes an exact answer.

## What happened to every task so far

| Task | Rule | Result | Why |
|---|---|---|---|
| bridge-load-planning (Ops) | 23 CFR 658.17, 23 U.S.C. 127 | Passed difficulty | A statute that overrides the regulation (idle-reduction weight allowance), plus the Bridge Formula over every axle group. |
| part117-reserve-coverage (Ops) | 14 CFR 117 | Passed difficulty | Rolling rest and duty windows across time zones, acclimatization status. |
| sms-send-schedule (Marketing) | 47 CFR 64.1200 | Passed, submitted | A definition that excludes cases (a "telephone solicitation" excludes calls with consent or an existing relationship, so quiet hours do not apply), consent judged from raw elements, earliest allowed minute across daylight-saving changes. |
| auto-ad-clearance (Marketing) | 12 CFR 1026 (Reg Z) | Passed, submitted | Each charge judged a finance charge or not from raw facts; Appendix J APR with an odd first period; triggering terms read from ad copy. |
| hazmat-trailer-check (Logistics) | 49 CFR 172, 173, 177 | Failed Pass@2 three times (2/2 solved in 14 to 18 minutes) | Rule lookups (placard tables, segregation table). Adding more rules, a classification layer and bulk packagings did not help. The model reads and applies tables perfectly. Pivoted. |
| airline-claims-desk (Claims) | 14 CFR 250, 260 | v1: passed Pass@2 (0/2) but **failed deep review** | Both trials failed on the same point: whether unused paid extras are refunded when a voucher is accepted. That reading was genuinely open, so the difficulty was "for the wrong reason". Fixed by following the plain text and adding real difficulty (break in journey, due dates counted from dates the rule sets). |
| hos-log-audit (Logistics) | 49 CFR 395 | Pass@2 0/2, deep review PASS, AVA PASS, Pass@5 3/5 (one too many) | Minute-exact clocks with sleeper-berth splits, carrier days in local time, restarts, travel time, exceptions with history. Failed trials missed only near-threshold cases on long logs. v2 added more near-threshold cases. |

## Patterns that work

1. **Exact computation over time or money.** Minute-level clocks, rolling windows, local days vs
   UTC, daylight saving, business-day counting with holidays, interest-rate methods with odd
   periods. One slip changes an exact answer.
2. **A definition or exclusion that flips a common assumption,** written plainly in the rule but
   easy to skip: "telephone solicitation" excluding consented calls; a "covered flight" excluding
   segments after a break in journey; a combustible liquid not being regulated in non-bulk
   packaging; air miles being nautical miles.
3. **Raw facts that must be judged against a definition,** instead of pre-classified fields:
   consent records broken into elements, charges described by their facts, lab data instead of a
   hazard class. The agent must classify before applying the main rule.
4. **Near-threshold cases, many of them, mixed into realistic filler.** 9 h 30 m of rest when the
   rule needs 10; a 29-minute break when the rule needs 30; 165 statute miles against a 150
   air-mile radius; exactly 14 h 00 m against "within 14 hours". The hos-log-audit failures were
   all of this kind, on filler records, not on the obvious planted cases.
5. **Conditions that need history:** "used within the previous 6 days unless a restart
   intervened", "previous five tours released at home".
6. **Statute vs regulation conflicts,** where the newer statute overrides the regulation text.

## Patterns that fail

1. **Lookups.** Tables, placards, lists of thresholds. The model fetches the rule from the
   internet and applies it perfectly.
2. **More of the same.** Adding rule families to a lookup task does not change the outcome.
3. **Volume alone.** More rows of the same kind do not add difficulty; the model's code is
   general. Volume helps only when it multiplies near-threshold cases.
4. **Ambiguity.** If the model fails because two readings are possible, the deep review fails the
   task. See `ci-checks.md`.
5. **Puzzles or optimization with many valid answers.** The verifier needs one exact answer.

## Keep contested readings out of the data

For every rule, list the places where a competent expert could read it two ways. For each one:
- Remove such cases from the data, and make the generator reject them automatically (see
  `contested()` in `example/hos-log-audit/tools/generate.py`), or
- Add one plain fact to instruction.md that settles it. State it as a fact about the situation
  ("A flight counts as cancelled from the moment Lakeshore notifies the passenger"), not as a rule
  explanation.

Examples we had to handle:
- HOS: whether driving beyond the limits after a sleeper-berth pair voids the pair or is a
  violation. The data never has that situation.
- HOS: whether a 2-hour off-duty period (not in the berth) can be half of a pair. The data never
  has it.
- Airline: whether a refund deadline starts on the announcement day or the flight day. Settled
  with one fact sentence.
- Airline: whether the bag-fee refund date is the request date or the day the delay limit passed.
  The data makes both the same day.
- Hazmat: whether DANGEROUS may cover a single leftover category. The generator rejects such loads.

## Plant cases on both sides of every condition

For every rule and every exception, plant at least one case where it applies and one where it
narrowly does not, each worked by hand. Tag each case with its rule family so the tests can report
families separately.

## When to pivot

Pivot to a different task (ask the person first) when:
- the task is solved 2 of 2 twice, or
- the trials finish in under 30 minutes, or
- the only way you can see to add difficulty is ambiguity.

Pick a new task with patterns 1 and 4 from the "work" list. Time-based audits (hours of service,
rest rules, billing periods, statutory deadlines with business days) have been the most reliable.

## Calibration

`calibrate.py` runs shortcut solutions: small edits of the reference solution that encode a
common mistake (rolling 168 hours instead of carrier days, `>` instead of `>=`, an exception
ignored, a threshold off by one unit). Every shortcut must fail at least one test. Aim for 20 to 40.
If a shortcut passes, either plant a hand-worked case that separates it, or, if the case would be
contested, drop the shortcut and note why in the README.
