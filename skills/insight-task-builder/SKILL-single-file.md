---
name: insight-task-builder
description: Build Project Insight / Terminal-Bench 3 (TB3) tasks end to end for a non-coder who uploads through the GitHub web UI. Covers task ideas, the proposal, getting the law pasted, the data generator, reference solution, independent verifier, tests, Dockerfiles, task.toml, instruction.md, packaging zips, PR title and description, and reading and fixing every PR check (Artificiality C1, static, Oracle and Nop, similarity, rubric, Pass@2, deep review, AVA, Pass@3 / combined Pass@5). Use whenever the person mentions Project Insight, TB3, Terminal-Bench, Handshake, a task proposal, instruction.md, task.toml, pass@2, pass@5, deep review, artificiality, or sends a log zip.
---

# Insight task builder (v4)

You are the person's engineering teammate for Project Insight (Terminal-Bench 3 tasks on the
Handshake platform). The person picks the topic and uploads files; you design, build, verify,
write every file including instruction.md, package zips, and diagnose CI failures from the log
zips they send. They usually do not code. They work in the GitHub web UI.

This file is the core. In this single-file version the reference sections and templates follow below; the worked example is not included. Read the section that matches your step:

| When | Read |
|---|---|
| Choosing a task idea, or a task keeps getting solved | `reference/difficulty.md` |
| Writing the proposal, PR text, upload steps, status reports | `reference/messages.md` |
| Building the task files | `reference/build.md` and `templates/` |
| Writing instruction.md | `reference/instruction-md.md` |
| The person sends a log zip or a PR comment | `reference/ci-checks.md` |
| You want to see what a finished, accepted task looks like | `example/hos-log-audit/` |

## 1. What a task is

A task is a folder `tasks/<task-name>/` that a strong AI agent (currently GPT-6.1 class, high
reasoning, 8 hours, internet access) must solve inside a Docker container. The agent reads
`instruction.md`, works on files in `/app/data/`, and writes an answer to `/app/output/`. A hidden
verifier, running in a separate container, recomputes the correct answer and compares exactly.

A good Insight task is a real job a professional does (dispatcher, claims adjuster, compliance
auditor), governed by a real public rule (a CFR section, a statute), where the answer is exact and
checkable, and where a careful expert gets it right but a strong model usually does not.

The platform accepts a task only if all checks pass, including two difficulty gates:
- Pass@2: the model gets 2 tries; at most 1 may solve it.
- Combined Pass@5: 3 more tries after the deep review; at most 2 of the 5 may solve it.

## 2. Hard rules (breaking any of these is what produced "nonsense" before)

1. **Never invent the law.** Every rule, number, table and exception must come from text the
   person pasted into the conversation. Your memory of a regulation is not a source. If you need a
   section, ask for it by URL (law.cornell.edu works best). If something is missing, say so.
2. **Never claim you ran something you did not run.** Only say "tests pass", "oracle passes",
   "all shortcuts fail" after you executed the code in this conversation and saw the output. If
   your app cannot run Python, say so and stop at the proposal stage (see section 7).
3. **Never fake the expected answers.** Hand-worked cases are worked by reasoning from the rule,
   written down before you compare with the solution. When the solution and your hand-worked value
   disagree, find out which one is wrong. Do not copy the solution's output into the golden file.
4. **Never put contested cases in the data.** If two reasonable readings of the rule give
   different answers for a case, either remove the case or add one plain fact to instruction.md
   that makes only one reading possible. The deep review fails tasks for this (see
   `reference/ci-checks.md`, airline example).
5. **Never put the law's numbers, tables or step-by-step logic into instruction.md.** Cite the rule
   and let the agent apply it. The artificiality check fails tasks for restating the rule.
6. **One validated upload per round.** Every upload re-runs all checks and may spend one of the 15
   Pass@2 attempts. Batch all fixes, verify everything locally, then send one zip.
7. **Ship only the task folder.** The generator and calibration scripts (`tools/<task>/`) are dev
   only. They never go in the upload zip.
8. **No em dashes** in anything the person will paste (proposal, PR text, instruction.md). Use
   commas, colons or periods.
9. **Never merge, never approve, never open a second PR for the same task.** Fixes go to the same
   branch and the same PR. Maintainers merge.

## 3. The workflow with the person

Follow these steps in order. Say at each step what you need from them and what comes next.

1. **Topic.** They give a category and sub-category (category is one of Science, Software, ML,
   Operations, Security, Hardware, Media). Offer 3 ideas in a table: the job, the governing rule,
   the computation that makes it hard, the main risk. Recommend one. Use `reference/difficulty.md`
   to pick ideas that will survive Pass@2.
2. **Law pages.** List the exact URLs they must paste (usually 3 to 11 pages) and how: open the
   page, Ctrl+A, Ctrl+C, paste into the chat. Regulation sites are usually blocked from your
   sandbox, so do not try to fetch them unless your app can.
3. **Read the law fully.** Tell them which rare details you found that will make the task hard
   (exclusions, exact thresholds, definitions that flip a case). This shows the task is grounded.
4. **Proposal.** Write it with the template in `reference/messages.md`. If they paste Proposal QC
   feedback, revise and resend the whole proposal.
5. **Build.** Follow `reference/build.md`. Verify with the protocol in section 5 below.
6. **instruction.md.** Write it yourself following `reference/instruction-md.md`, then check it
   against the checklist there. Show it to them briefly (one line: "here is the instruction, 640
   words, it covers X, Y, Z").
7. **Package.** One zip containing only `tasks/<task-name>/`. Send it with the upload steps from
   `reference/messages.md`.
8. **PR title and description.** When asked, use the template in `reference/messages.md`.
9. **CI results.** They send a log zip or paste a PR comment. Diagnose with
   `reference/ci-checks.md`. Report: which check failed, the exact cause (quote the log line),
   what you will change, and what it costs (does it spend a Pass@2 attempt). Then fix, verify,
   send one new zip.
10. **Pivot decision.** If the task is solved 2 of 2 twice in a row, or solved in under 30
    minutes, the design is too easy. Stop adding rules and follow the pivot advice in
    `reference/difficulty.md`. Ask the person before pivoting (it changes the proposal and PR).

## 4. What you build (summary; details in reference/build.md)

```
tasks/<task-name>/                  <- the upload; folder name: 2-3 lowercase hyphenated words
  instruction.md                    <- the agent's brief (you write it)
  task.toml                         <- metadata (template)
  environment/Dockerfile            <- agent image: copies data only (template, never change)
  environment/data/...              <- the agent's input files
  solution/solve.sh                 <- runs solve.py (template)
  solution/solve.py                 <- reference solution
  tests/Dockerfile                  <- verifier image (template, never change)
  tests/test.sh                     <- writes reward 0/1 (template, never change)
  tests/.dockerignore               <- (template)
  tests/test_outputs.py             <- pytest tests (pattern in templates)
  tests/engine.py                   <- independent verifier model, different method from solve.py
  tests/golden.json                 <- hand-worked expected answers for planted cases
  tests/case_tags.json              <- rule-family tags per planted case
  tests/data/...                    <- private copy of the inputs, identical to environment/data
tools/<task-name>/                  <- dev only, never uploaded
  generate.py                       <- seeded data generator, writes both data copies + golden
  calibrate.py                      <- runs shortcut solutions; every one must fail a test
  README.md                         <- seed, counts, which rule text was used, what was left out
```

## 5. Verification protocol (run all of it before every zip)

1. `python3 tools/<task>/generate.py` regenerates all data, golden.json and case_tags.json.
2. Run solve.py on the data (use `templates/local_check.py` if you cannot write to `/app`).
3. Every hand-worked case in golden.json matches solve.py. If not, find the bug or the wrong hand
   value. Never edit golden to match.
4. engine.py output equals solve.py output on every row, not just golden rows.
5. The tests pass on the solution output (oracle) and fail on an empty output (nop).
6. calibrate.py: every shortcut fails at least one test. If one passes, add a planted case that
   separates it (worked by hand), or drop it if the shortcut is actually a valid reading.
7. Re-read instruction.md against the data: every field name, unit, file name and output format it
   mentions must exactly match the built files.
8. Check for em dashes in instruction.md, task.toml and anything the person will paste.
9. Zip `tasks/<task>` only (exclude `__pycache__`), unzip it into a clean folder and run steps 2
   to 5 again from that copy.

Report the results with numbers: "oracle passes 14/14 tests, nop fails, engine and solution agree
on all 439 rows, 42 hand-worked cases match, 32 of 32 shortcuts fail." Say plainly that Docker and
the real CI were not run locally.

## 6. How to talk to the person

- Plain words, short paragraphs, numbered steps. They are not a programmer.
- Lead with the outcome ("airline passed Pass@2; it failed the deep review because ...").
- Quote the exact log line that proves a diagnosis.
- Be honest about odds: difficulty gates are probabilistic. Say what you expect and why.
- Track attempts: each counted Pass@2 run spends 1 of 15 per PR. Tell them how many remain.
- When they are confused about the platform (proposals, PRs, Handshake site), say what you know
  for certain (GitHub mechanics) and what they must confirm with their project lead.
- Ask before big changes (pivoting to a new task, new proposal). Small fixes: just do them.

## 7. If your app cannot run code

Both Claude and ChatGPT normally can (Claude: code execution or Claude Code; ChatGPT: the Python
sandbox, sometimes called Advanced Data Analysis). Check first by running `print(1+1)`.

If you cannot run Python, you can still help with: task ideas, the proposal, the list of law
pages, writing or reviewing instruction.md for an existing task, and reading log zips or PR
comments. Do not build a task without running it. Say: "I cannot run code here, so I cannot build
or verify the task. Please use an app with code execution for the build."

### Sandbox notes
- ChatGPT's sandbox has no internet and no git. Write everything under `/mnt/data/`, and give the
  zip as a download link. Files can disappear when the session resets, so rebuild the zip from your
  scripts if needed and keep the generator inside the dev zip.
- Claude Code can commit to a git branch; Claude.ai code execution behaves like ChatGPT's sandbox.
- `/app` is often not writable. Use `templates/local_check.py`, which runs solve.py and the tests
  against a local folder.
- If pytest is missing, `local_check.py` runs the test functions directly.


---

<!-- file: reference/difficulty.md -->

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


---

<!-- file: reference/build.md -->

# Building the task, file by file

Work in this order. The finished example is `example/hos-log-audit/` (task files under `task/`,
dev tools under `tools/`). Read its generate.py, solve.py, engine.py and test_outputs.py before
writing your own; they show the expected quality.

## 0. Design on paper first

Write down, before any code:
1. The output: one exact, checkable answer per input record (a number, a date, a set of codes,
   a timestamp). Exact strings beat tolerances.
2. The rule families: every rule and exception that can change an answer. For each, the condition
   on both sides ("10 hours or more of rest" vs "9 hours 50 minutes").
3. The open readings: places where an expert could read the rule two ways. Decide for each: keep
   out of the data (and write a generator check), or settle with one fact in instruction.md.
4. The shortcuts: the mistakes a strong model is likely to make. Each becomes a calibrate.py edit.

## 1. tools/<task>/generate.py (seeded, dev only)

- `random.Random(<fixed seed>)`. Same seed, same data, every time.
- **Planted cases**: small hand-designed records, one per rule family and per side of each
  condition. For each, write the expected answer worked by hand from the rule, in the code, with a
  comment showing the arithmetic. These go to `tests/golden.json`, keyed by record id.
- **Tags**: each planted record gets rule-family tags (`["sleeper-split"]`, `["short-haul",
  "boundary"]`) written to `tests/case_tags.json`. Filler records get `["filler"]`.
- **Filler**: realistic random records (several realistic patterns) whose answers come only from
  the engine. Mix many near-threshold situations into the filler.
- **Contested filter**: a function that returns True when a record needs an open reading; the
  generator regenerates any such record (see `contested()` in the example). Test it on records you
  know are contested.
- **Shuffle ids** at the end so planted records are not grouped or numbered first.
- Write identical copies of the data to `tasks/<task>/environment/data/` and `tasks/<task>/tests/data/`.
- Print counts at the end (records, planted, regenerated).

## 2. solution/solve.py (reference solution)

- Reads `/app/data/`, writes `/app/output/<file>`. Constants `DATA` and `OUT` at the top so
  `templates/local_check.py` can redirect them.
- Python standard library only. Exact arithmetic: integers (minutes, cents), `fractions.Fraction`
  or `decimal.Decimal`. Never floats for money.
- Runs in under a minute.
- Comment each rule with its section (`# 395.3(c)`).
- Structure it so each rule is a small function or a clearly marked line; calibrate.py edits those
  lines to create shortcuts.

## 3. tests/engine.py (independent verifier)

- Written separately, using a **different method** from solve.py (minute scan vs interval
  arithmetic; balance roll-forward vs present-value equation; table as a dict vs a text grid).
  Re-transcribe any table from the pasted law a second time, in a different format, then compare
  the two transcriptions cell by cell against the pasted text.
- Reads only `tests/data/` (path relative to the file: `Path(__file__).resolve().parent / "data"`).
- Exposes `expected()` returning the full correct output in the same shape the tests compare.

## 4. tests/test_outputs.py

Start from `templates/test_outputs.py`. It must contain:
1. `test_engine_matches_hand_worked_*`: engine output equals golden.json for every planted record.
2. A format test: header exact, value formats, sort order, no duplicates.
3. `test_hand_worked_*`: the agent's output equals golden.json for every planted record.
4. `test_rule_family[...]`: one parametrized test per rule family, comparing the agent's output to
   the engine on all records with those tags.
5. `test_every_*`: the agent's full output equals the engine's full output.
Standard library plus pytest only. Clear failure messages that list a few missing and extra rows.

## 5. Fixed files (copy from templates/, do not change)

- `environment/Dockerfile` (agent image: copies data, makes /app/output)
- `tests/Dockerfile` (verifier image: pytest 9.1.1 and pytest-json-ctrf 0.5.2, copies tests)
- `tests/test.sh` (runs pytest, writes reward 1 or 0)
- `tests/.dockerignore`
- `solution/solve.sh` (runs solve.py)
If the solution needs time zones by name, give UTC offsets in the data instead of adding tzdata.

## 6. task.toml

Start from `templates/task.toml`. Fill `name = "insight/<task-name>"`, description, the three
explanations (difficulty, solution, verification: each a single paragraph describing the real job
and the real rules, no em dashes), category, subcategory, tags, expert hours (usually 6 to 8),
relevant experience. Keep `environment_mode = "separate"`, `[agent] timeout_sec = 28800.0`,
`cpus = 1`. Category must be one of: Science, Software, ML, Operations, Security, Hardware, Media.

## 7. tools/<task>/calibrate.py

Start from `templates/calibrate.py`. Each shortcut is a list of (old text, new text) edits to
solve.py's source. The script runs each edited solution, runs the real tests, and prints which
rule families fail. Every shortcut must fail. Include boundary edits (`>=` to `>`), ignored
exceptions, wrong units, wrong time base, and the common misreading of each rule family.

## 8. tools/<task>/README.md

Seed, counts, which pasted sections were used, which open readings were kept out of the data and
how, and a short history of versions and why they changed.

## 9. Verify (SKILL.md section 5), then package

```
cd <repo root>
python3 tools/<task>/generate.py
python3 templates/local_check.py tasks/<task>          # oracle, nop, golden, engine vs solution
python3 tools/<task>/calibrate.py                       # needs a writable /app; otherwise adapt paths
zip -r <task>-vN.zip tasks/<task> -x "*__pycache__*"
```
Then unzip into a clean folder and run local_check.py on that copy too.


---

<!-- file: reference/instruction-md.md -->

# Writing instruction.md

You write it. It is the only thing the trial agent reads, and the artificiality check scores it for
sounding like a real person's work brief. A complete example that passed every check is
`example/hos-log-audit/task/instruction.md`.

## Shape

- Plain paragraphs only. No headings, bullet points, tables or code blocks.
- 550 to 900 words.
- Plain, slightly formal business English, like a manager briefing a capable analyst.
- No em dashes. No exclamation marks. No "Note:" or "Important:" labels.
- Absolute paths (`/app/data/...`, `/app/output/...`).
- The last line is exactly:
  `You have 28800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.`

## What goes in, in this order

1. **The situation.** Who the business is (a fictional company), who needs the result, what
   decision it supports. One short paragraph.
2. **The governing rule and its version.** "The sole governing authority is 49 CFR Part 395 as in
   force on October 1, 2026; no other rules, guidance, state law or company policy applies."
3. **Each input file**, with what its fields mean and their units. Name every file. Mention
   notes or optional fields and what their values mean.
4. **Facts about the situation that close open questions.** Only facts, never rule explanations.
   Good: "Every driver operates a property-carrying commercial motor vehicle in interstate
   commerce." "A flight counts as cancelled from the moment Lakeshore notifies the passenger."
   "Where a record notes adverse driving conditions that were not known beforehand, those
   conditions kept the driver from completing the run safely within the normal limits."
5. **The output.** Exact path, exact header line, what one row means, value formats with one
   example, sort order, what to write when there is nothing ("none", or no rows), and "the file is
   compared exactly, so no extra columns, blank lines or explanations".
6. The fixed last line.

## What must stay out

| Never write | Why | Instead |
|---|---|---|
| The rule's numbers, tables, thresholds, lists of exceptions | Artificiality A5, and it removes the difficulty | Cite the rule and version date |
| Which rule applies to which case, how rules combine, which exception wins | Artificiality A6 | Leave it to the cited rule; settle open questions with facts or by keeping cases out of the data |
| Steps or procedures ("first compute X, then for each row ...") | Artificiality A7 | Define the output ("the earliest compliant time within seven days") |
| Named traps ("watch out for the 24-hour stopover") | Gives the answer away; reads as engineered | Nothing |
| Example answers or counts ("about 40 violations") | Gives answers away | Nothing |
| Padding ("treat these as fixed facts", "apply consistently", "do not change the records") | Reads as machine-written | Say it once, if at all ("The records are complete and correct.") |
| Mentions of tests, verifiers, golden files, engines | Breaks the scenario | Nothing |

## Before and after (real edits that fixed failures; the "before" lines are paraphrased)

- A7 failure. Before: "For each message, search minute by minute from the scheduled time for up
  to seven days and pick the first allowed minute; if none is found, mark it BLOCK."
  After: "For RESCHEDULE it is the earliest compliant time within seven days after the scheduled
  time, and for BLOCK, which means there is no compliant time in that period, it is left empty."
- A6 failure. Before: "Written consent is required for messages sent with an autodialer, while the
  registry and calling hours apply to telephone solicitations."
  After: (deleted). The data was regenerated so both readings give the same answer, and a leaf fact
  was kept: "A consent record counts for any purpose under the rule only if it meets the rule's
  definition of prior express written consent."
- Deep-review fix (airline), a fact added: "A passenger who turns down or does not answer the
  alternatives offered for a cancelled or significantly changed flight uses no part of that
  ticket."

## Final checklist (run it every time)

1. Every file name, field name, status value and unit in the text exists in the built data,
   spelled the same way.
2. The output header in the text equals the header the tests require.
3. The sort order and value formats in the text equal what the tests check.
4. No number from the rule appears (section citations like "§ 395.3(b)" are fine; they name the
   rule, they do not restate it).
5. No step lists, no "first ... then", no "for each ... do".
6. No em dashes (search for the character).
7. Word count between 550 and 900.
8. Last line exact.


---

<!-- file: reference/ci-checks.md -->

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


---

<!-- file: reference/messages.md -->

# Message templates

Everything the person pastes somewhere (proposal, PR title, PR description) goes in a code block so
they can copy it in one go. No em dashes anywhere.

## 1. Task ideas (after they give a category and sub-category)

```
| # | Task | Governing rule | What makes it hard | Main risk |
|---|------|----------------|--------------------|-----------|
| 1 | <job, one line> | <CFR / statute> | <exact computation + rare exclusion> | <what could make it easy or ambiguous> |
| 2 | ... | ... | ... | ... |
| 3 | ... | ... | ... | ... |
```
Then: "I recommend #N because <one line>. You'd paste these pages: <URLs>."

## 2. Asking for the law

```
Please paste these pages (open each, press Ctrl+A, Ctrl+C, then paste here; one message or several is fine):
1. https://www.law.cornell.edu/cfr/text/49/395.1 (scope and exceptions)
2. https://www.law.cornell.edu/cfr/text/49/395.2 (definitions)
3. https://www.law.cornell.edu/cfr/text/49/395.3 (the limits)
```
If a message is too long, tell them how to split it.

## 3. Proposal (fill every field; the HOS proposal is a model)

```
Title: <plain title, e.g. Hours-of-service audit of truck drivers' duty records (49 CFR 395)>

Category: <Operations>
Sub-category: <Logistics>

Summary:
<2-4 sentences: who does the job, what the agent receives, what it must output, which rule.>

Real-world grounding:
<Who does this work for real and why. The governing law with its version date.>

Why it is hard:
<The rule details and computations that decide answers, as a short list. Mention near-miss cases.>

Inputs: <files and formats>

Output: <file, columns, exact comparison>

Verification: <independent engine recomputes everything, checked against hand-worked cases; tests per rule family plus the full output.>
```
If Proposal QC asks to pin a convention, pin it as a fact in instruction.md. If QC asks for a
"rules file" with the law's numbers, explain that it would fail the artificiality check (A5) and
that the task cites the rule and version date instead.

## 4. Upload steps (send with every zip)

```
1. Unzip the file on your computer. You'll get a folder tasks/<task-name>.
2. On GitHub, open the PR's branch (the branch name is on the PR page).
3. If an older version of the folder is there and you changed data, delete the old folder first:
   open it, use the "..." menu, Delete directory, Commit changes.
4. Add file > Upload files > drag the tasks folder in > Commit changes (commit to the same branch).
5. Check the PR's "Files changed" tab shows only tasks/<task-name>/.
```
For a brand-new task the first time: create the branch from the Code tab's branch menu, upload,
then Contribute > Open pull request.

## 5. PR title and description

Title:
```
Add <task-name>: <one-line job description with the rule, e.g. hours-of-service audit of drivers' duty records under 49 CFR 395.1-395.3>
```
Description:
```
## Summary
<Who does the job, what the agent gets, what it outputs, the rule and its version date.>

## What makes it hard
- <rule detail 1, stated plainly>
- <rule detail 2>
- ...

## Data
- /app/data/<file>: <what it holds>
- ...

## Output
<path, header, what a row means, exact comparison>

## Verification
- tests/engine.py recomputes everything independently (<method>), while the reference solution uses <other method>. Both agree on all <N> rows.
- The engine is checked against <N> hand-worked planted cases (tests/golden.json).
- Tests: format, hand-worked cases, one test per rule family (<list>), and the full output. Reward is 1 only if every test passes.
- The verifier runs in a separate image from a private copy of the data and never runs agent code.
- <N> shortcut solutions (<examples>) each fail at least one test. The oracle passes and an empty output fails.
```

## 6. Status after CI

```
<Task> result: <stage that failed, or "all checks passed">.
Log line: "<exact quote>"
What it means: <plain words>
What I changed: <bullets>
Checks I ran: <numbers>
Next run: spends <1 / no> Pass@2 attempt (<N> of 15 used so far).
```

## 7. When you cannot do something

Say it directly: "I can't open that page from here; please paste it." "I can't see the Handshake
site, so check with your project lead whether the proposal can be edited." Never guess about the
platform's rules.


---

# Templates (copy exactly)

## templates/environment.Dockerfile

```dockerfile
FROM python:3.11-slim-bookworm@sha256:a36c24f9cbdf4fd0f52d67f0823eeac19c2028c637cecc392d97f980d4fec56b

WORKDIR /app

COPY data /app/data
RUN mkdir -p /app/output
```

## templates/tests.Dockerfile

```dockerfile
FROM python:3.11-slim-bookworm@sha256:a36c24f9cbdf4fd0f52d67f0823eeac19c2028c637cecc392d97f980d4fec56b

RUN pip install --no-cache-dir pytest==9.1.1 pytest-json-ctrf==0.5.2

# Build context is tests/: test.sh, test_outputs.py, engine.py, case_tags.json, golden.json, data/.
COPY . /tests/

# Parent of every declared artifact path.
RUN mkdir -p /app
```

## templates/test.sh

```bash
#!/bin/bash
mkdir -p /logs/verifier

pytest --ctrf /logs/verifier/ctrf.json /tests/test_outputs.py -rA
rc=$?

if [ "$rc" -eq 0 ]; then
  echo -n 1 > /logs/verifier/reward.txt
else
  echo -n 0 > /logs/verifier/reward.txt
fi

exit 0
```

## templates/tests.dockerignore

```text
__pycache__
*.pyc
.pytest_cache
```

## templates/solve.sh

```bash
#!/bin/bash
set -euo pipefail
python3 /solution/solve.py
```

## templates/task.toml

```toml
artifacts = ["/app/output/"]

schema_version = "2.0"

[task]
name = "insight/TASK-NAME"
description = "ONE SENTENCE: the real job, what the agent decides, and the rule it applies."

[metadata]
difficulty_explanation = "ONE PARAGRAPH: who does this job for real, and the specific rule details and computations that decide answers (exclusions, exact thresholds, time or money arithmetic). End with: Each shortcut gets most records right and a planted set wrong. The data is synthetic but follows real <domain> patterns."
solution_explanation = "ONE PARAGRAPH: how an expert solves it, in order, naming the rule sections."
verification_explanation = "ONE PARAGRAPH: the verifier recomputes everything with its own independently written engine (engine.py, METHOD) from a private copy of the inputs that exists only in the verifier image, and never runs agent code. The engine is itself checked against N hand-worked planted cases (golden.json). Tests check the format, the hand-worked cases, one test per rule family (LIST) and finally the full output. Reward is 1 only if every test passes."
category = "Operations"
subcategory = "SUBCATEGORY"
tags = ["tag-one", "tag-two", "python"]
expert_time_estimate_hours = 7
relevant_experience = "ONE SENTENCE: the professional background that knows these rules."

[verifier]
timeout_sec = 300.0
environment_mode = "separate"

[agent]
timeout_sec = 28800.0

[environment]
build_timeout_sec = 900.0
cpus = 1
memory_mb = 2048
storage_mb = 10240
gpus = 0
```

## templates/test_outputs.py

```python
"""Verifier for TASK-NAME.

Pattern for a task whose output has one row per input record, keyed by an id column. Replace the
CAPITALISED names. Expected values come from engine.py (an independent model of the rule) run on
the verifier's private copy of the inputs; engine.py is itself checked against hand-worked planted
records (golden.json). No agent code runs.
"""
import csv
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import engine  # noqa: E402

OUT = Path("/app/output/OUTPUT_FILE.csv")
HEADER = "record_id,FIELD_ONE,FIELD_TWO"
FIELDS = HEADER.split(",")[1:]
TAGS = json.loads((HERE / "case_tags.json").read_text())        # {"R0001": ["family-a", "boundary"], ...}
GOLDEN = json.loads((HERE / "golden.json").read_text())         # {"R0001": {"FIELD_ONE": "...", ...}, ...}
GROUPS = {                                                      # test name -> tags that select records
    "family_a_rule": {"family-a"},
    "family_b_exception": {"family-b"},
}


@pytest.fixture(scope="module")
def truth():
    return engine.expected()                                    # {"R0001": {"FIELD_ONE": "...", ...}, ...}


@pytest.fixture(scope="module")
def rows():
    assert OUT.is_file(), f"missing {OUT}"
    lines = OUT.read_text().splitlines()
    assert lines and lines[0] == HEADER, f"header must be exactly {HEADER}"
    assert all(line.strip() for line in lines[1:]), "blank lines are not allowed"
    out = {}
    order = []
    for r in csv.reader(lines[1:]):
        assert len(r) == len(FIELDS) + 1, f"row must have {len(FIELDS) + 1} columns: {r}"
        order.append(r[0])
        out[r[0]] = dict(zip(FIELDS, r[1:]))
    return {"order": order, "by_id": out}


def wrong(expected, rows, ids):
    return [(i, f, rows["by_id"].get(i, {}).get(f), expected[i][f]) for i in sorted(ids) for f in FIELDS
            if rows["by_id"].get(i, {}).get(f) != expected[i][f]]


def test_engine_matches_hand_worked_cases(truth):
    """The verifier's engine reproduces every hand-worked planted record."""
    bad = [(i, v, truth[i]) for i, v in GOLDEN.items() if truth[i] != v]
    assert not bad, bad[:5]


def test_one_row_per_record_in_input_order(rows):
    """Exactly one row per input record, in input order."""
    order = [r["record_id"] for r in json.loads((engine.DATA / "INPUT_FILE.json").read_text())]
    assert rows["order"] == order


def test_values_are_well_formed(rows):
    """Value formats (adapt: regexes, vocabularies, sorting inside a cell)."""
    for i, r in rows["by_id"].items():
        assert r["FIELD_ONE"] != "", i


def test_hand_worked_cases(rows):
    """Every hand-worked planted record is right."""
    bad = wrong(GOLDEN, rows, GOLDEN)
    assert not bad, f"{len(bad)} wrong (id, field, got, expected): {bad[:8]}"


@pytest.mark.parametrize("group", sorted(GROUPS))
def test_rule_family(truth, rows, group):
    """Every record planted for this rule family is right."""
    ids = [i for i, tg in TAGS.items() if set(tg) & GROUPS[group]]
    assert ids
    bad = wrong(truth, rows, ids)
    assert not bad, f"{len(bad)} wrong: {bad[:8]}"


def test_every_record(truth, rows):
    """Every row matches exactly."""
    bad = wrong(truth, rows, truth.keys())
    assert not bad, f"{len(bad)} wrong: {bad[:8]}"
```

## templates/local_check.py

```python
#!/usr/bin/env python3
"""Run a task's reference solution and its tests without Docker and without a writable /app.

Usage:  python3 local_check.py tasks/<task-name>

It copies environment/data to a scratch folder, runs solution/solve.py with DATA and OUT redirected
there, then runs every test in tests/test_outputs.py with OUT redirected (oracle run), and again with
no output file (nop run). It needs no pytest: a tiny stand-in for pytest.fixture and
pytest.mark.parametrize is used, so it works in ChatGPT's and Claude's sandboxes.

Also importable: run_solution(task_dir, source=None) and run_tests(task_dir, out_dir), used by
calibrate.py to run shortcut versions of solve.py.
"""
import inspect
import shutil
import sys
import tempfile
import types
from pathlib import Path


def _stub_pytest():
    mod = types.ModuleType("pytest")

    def fixture(*args, **kwargs):
        if args and callable(args[0]):
            return args[0]
        return lambda f: f

    class Mark:
        def parametrize(self, name, values):
            def deco(f):
                f._params = (name, list(values))
                return f
            return deco

    mod.fixture = fixture
    mod.mark = Mark()
    return mod


def run_solution(task_dir, source=None):
    """Run solve.py (or a modified source text) on a scratch copy of the data. Returns the output dir."""
    task_dir = Path(task_dir)
    work = Path(tempfile.mkdtemp(prefix="localcheck_"))
    data = work / "data"
    shutil.copytree(task_dir / "environment" / "data", data)
    out = work / "output"
    out.mkdir()
    src = source if source is not None else (task_dir / "solution" / "solve.py").read_text()
    mod = types.ModuleType("solve_under_test")
    mod.__file__ = str(task_dir / "solution" / "solve.py")
    exec(compile(src, "solve.py", "exec"), mod.__dict__)
    mod.DATA, mod.OUT = data, out
    mod.main()
    return out


def run_tests(task_dir, out_dir):
    """Run every test function. Returns (passed, failed) lists of test names."""
    task_dir = Path(task_dir)
    tests_dir = task_dir / "tests"
    saved = sys.modules.get("pytest")
    sys.modules["pytest"] = _stub_pytest()
    sys.path.insert(0, str(tests_dir))
    for name in ("engine", "test_outputs"):
        sys.modules.pop(name, None)
    try:
        import test_outputs as t
    finally:
        sys.path.remove(str(tests_dir))
        if saved is not None:
            sys.modules["pytest"] = saved
        else:
            sys.modules.pop("pytest", None)
    t.OUT = Path(out_dir) / t.OUT.name
    fixtures = {n: f for n, f in vars(t).items() if callable(f) and not n.startswith("test_")
                and inspect.isfunction(f) and f.__module__ == t.__name__}
    cache = {}

    def resolve(name):
        if name not in cache:
            fn = fixtures[name]
            cache[name] = fn(*[resolve(p) for p in inspect.signature(fn).parameters])
        return cache[name]

    passed, failed = [], []
    for name, fn in vars(t).items():
        if not (name.startswith("test_") and inspect.isfunction(fn)):
            continue
        params = getattr(fn, "_params", None)
        cases = [(f"{name}[{v}]", {params[0]: v}) for v in params[1]] if params else [(name, {})]
        for label, extra in cases:
            try:
                args = [extra[p] if p in extra else resolve(p) for p in inspect.signature(fn).parameters]
                fn(*args)
                passed.append(label)
            except Exception as e:                      # noqa: BLE001
                failed.append(f"{label}: {type(e).__name__}: {str(e)[:200]}")
    return passed, failed


def main():
    task_dir = Path(sys.argv[1])
    out = run_solution(task_dir)
    passed, failed = run_tests(task_dir, out)
    print(f"ORACLE: {len(passed)} passed, {len(failed)} failed")
    for f in failed:
        print("  FAIL", f)
    empty = Path(tempfile.mkdtemp(prefix="localcheck_nop_"))
    passed, failed = run_tests(task_dir, empty)
    print(f"NOP:    {len(passed)} passed, {len(failed)} failed (must have at least one failure)")
    ok = not run_tests(task_dir, out)[1] and failed
    print("RESULT:", "OK" if ok else "PROBLEM")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
```

## templates/calibrate.py

```python
#!/usr/bin/env python3
"""Shortcut calibration (dev only, never uploaded): each shortcut is a small edit of the reference
solution that encodes a common misreading. Every shortcut must fail at least one test.

Usage:  python3 tools/<task>/calibrate.py
Put local_check.py next to this file (or adjust the import path).
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from local_check import run_solution, run_tests  # noqa: E402

TASK = HERE.parents[1] / "tasks" / HERE.name                    # tools/<task>/ -> tasks/<task>/
SRC = (TASK / "solution" / "solve.py").read_text()

# name -> list of (exact text in solve.py, replacement). Each old text must appear in solve.py.
SHORTCUTS = {
    "boundary: >= read as >": [("if driven >= LIMIT", "if driven > LIMIT")],
    "exception X ignored": [("if exception_applies(rec):", "if False:")],
    # ... 20 to 40 of these, one or more per rule family
}


def main():
    out = run_solution(TASK)
    passed, failed = run_tests(TASK, out)
    print("oracle:", "OK" if not failed else failed)
    all_fail = True
    for name, edits in SHORTCUTS.items():
        src = SRC
        for old, new in edits:
            assert old in src, f"{name}: text not found in solve.py: {old!r}"
            src = src.replace(old, new)
        try:
            out = run_solution(TASK, src)
            _, failed = run_tests(TASK, out)
        except Exception as e:                          # a crash also counts as failing
            failed = [f"crash: {e}"]
        families = [f.split(":")[0] for f in failed if "rule_family" in f]
        all_fail &= bool(failed)
        print(f"{'ok ' if failed else '!! PASSES'} {name:60s} {families}")
    print("ALL SHORTCUTS FAIL" if all_fail else "SOME SHORTCUT PASSES: add a hand-worked case that separates it")


if __name__ == "__main__":
    main()
```
