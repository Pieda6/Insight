# PR checks: what each one wants, how to read the logs, how to fix

## The stages, in order

| # | Stage (name in logs) | Passes when | Spends a Pass@2 attempt? |
|---|---|---|---|
| 1 | artificiality (Artificiality C1) | instruction.md reads like a real person's brief, not an engineered puzzle (probes A1 to A7, three LLM votes) | No |
| 2 | static (TB3 static checks) | folder layout, task.toml fields, Dockerfiles are valid | No |
| 3 | oracle_nop (Task validation, Oracle + Nop) | solve.sh gets reward 1, doing nothing gets reward 0 | No |
| 4 | similarity | the task is not a near-copy of an existing Terminal-Bench task (verdict UNIQUE) | No |
| 5 | rubric (Implementation rubric) | tests, verifier and metadata meet the implementation rubric | No |
| 6 | pass2_attempt_budget | fewer than 15 counted attempts used on this PR | No |
| 7 | pass2 (Pass@2 difficulty) | of 2 model trials, at most 1 solved and at least 1 genuinely failed | Yes, if any trial solved or genuinely failed |
| 8 | deep_review (TB3 deep review) | an LLM reviewer finds no blocking issue (it reads the code, data and both Pass@2 trajectories) | No |
| 9 | ava_review (AVA verifier audit) | the verifier is sound | No |
| 10 | pass3 (Pass@3 difficulty, combined Pass@5) | 3 more trials; across all 5, at most 2 solved | No separate attempt |

A failure stops everything after it. "Merging is blocked" on the PR is normal; maintainers merge.
Every push to the task folder re-runs all stages.

## Reading a log zip

The person downloads the log archive from the GitHub Actions run and uploads the zip to you.
Unzip it into its own empty folder. Then:

1. **Which stage failed:** open `1_review _ Conversion QC gate.txt` (or the folder
   `review _ Conversion QC gate/`) and search for lines like `deep_review: failure`. A one-liner:
   `grep -h "^[0-9TZ:.-]* [a-z0-9_]*: \(success\|failure\|skipped\)" *.txt | sed 's/^[0-9TZ:.-]* //' | sort -u`
2. **Artificiality:** `review _ Artificiality (C1)/10_Run artificiality (C1) review.txt` has a
   table of A1 to A7 verdicts, each with a "Fix:" line.
3. **Static:** `13_review _ TB3 static checks.txt`; search for `error`.
4. **Oracle and Nop:** `review _ Task validation (Oracle + Nop)/` step files; search for `reward`.
5. **Pass@2:** `review _ Pass@2 difficulty/22_Difficulty gate.txt` has a line like
   `pass@2 blocked (too_many_solves): 2 valid trial(s), 2 solved`. The run log
   `14_Run pass@2.txt` shows the trial time (for example `2/2 Mean: 1.000 ... 0:18:12`).
6. **Pass@3 / combined Pass@5:** `review _ Pass@3 difficulty (combined Pass@5) _ .../23_Difficulty gate.txt`,
   for example `combined pass@5 blocked (too_many_solves): 5 valid trial(s), 3 solved`.
7. **Attempt budget:** `7_review _ Pass@2 attempt budget.txt` says
   `has used N of 15 counted Pass@2 attempts`.
8. **Deep review:** its verdict is NOT in the log zip. It is a PR comment headed
   **"🤖 Automated Review"**. Ask the person to copy the whole comment. It contains the verdict,
   blocking issues with a "Fix:" line each, and an analysis of what the trial agents got wrong
   (including which test cases they missed). That analysis is the best guide to difficulty.
9. **Pass@2 / Pass@3 comments:** headed "🎯 Pass@2 difficulty check" and "🎯 Pass@3 difficulty
   check (TB2 → TB3)". The bot may update them in place, so they can sit higher up the PR.

## Failures we hit and how they were fixed

### Artificiality (A5, A6, A7)
- **A5, standard-citation laundering:** the instruction restated the rule's numbers or tables
  (thresholds, a list of exceptions). Fix: delete them, cite the rule and its version date.
- **A6, authored combination shape:** the instruction explained which rule applies to which case,
  or how rules combine ("written consent is required for X; quiet hours apply to solicitations").
  Fix: delete the explanation. If it was settling an ambiguity, make the data avoid the ambiguous
  case, and keep only leaf facts.
- **A7, sequential imperative:** a step list or search procedure ("for each message, search from
  the scheduled minute up to 7 days; if none, block"). Fix: describe the outcome instead
  ("RESCHEDULE is the earliest compliant time within seven days; BLOCK means there is none").
- Padding sentences ("these are fixed facts", "apply them consistently") read as machine-written.
  Delete them.
- The three votes vary between runs. A borderline instruction can pass once and fail the next
  time, so fix every flagged sentence, not just the majority.

### Static
- `No task.toml under submission/`: the task folder was not on the PR branch (only other changes
  were). Fix: upload `tasks/<task>/` to the PR branch.
- One task per PR: if a task is replaced, delete the old task folder from the branch.

### Pass@2 "too_many_solves"
The task is too easy. Read `difficulty.md`. Do not add more lookups. Look at the trial time: under
30 minutes means the design is far from hard enough.

### Deep review FAIL (airline example)
Verdict: "the decisive rule for refunding unprovided ancillary fees ... is undisclosed and
contestable; both pass@2 agents independently converged on a §260.4-grounded reading the golden
rejects." The reviewer checks, among others:
- **decisive_rule_recoverable:** can the expected answer be derived from instruction.md plus the
  cited rule?
- **graded_interpretation_unambiguous:** is there a second reasonable reading that gives a
  different answer?
- **independent convergence:** if both trials reached the same "wrong" answer, the reviewer
  treats that as evidence the reading is reasonable.
Fix: follow the plain text of the rule where it is clear; where it is not, add one fact sentence
to instruction.md or remove the cases. Then make sure the task is still hard for the right reasons
(the fix may remove the only thing that stopped the model).

### Deep review PASS with "Unresolved" items
Unresolved checks are routed to human review and do not block. Still close them when cheap: make
the generator reject the situations they describe, so a human reviewer finds nothing.

### Combined Pass@5 "too_many_solves" (hos example, 3 of 5)
The deep review's trajectory analysis showed the failed trials passed every rule-family test and
missed only 2 to 3 near-threshold cases on filler records. Fix: add many more near-threshold
cases of the same kinds (and hand-worked planted versions), without adding new rules or any
contested reading.

## After every diagnosis, tell the person
1. Which stage failed, quoting the log line.
2. What it means in plain words.
3. What you will change.
4. Whether the next run spends a Pass@2 attempt, and how many remain.
