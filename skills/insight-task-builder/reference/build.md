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
