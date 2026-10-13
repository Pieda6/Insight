# Worked example: hos-log-audit

A complete task that passed artificiality, static, oracle and nop, similarity, rubric, Pass@2 (0 of 2
solved), the deep review and the AVA audit. Its first version was solved 3 of 5 at Pass@5, one too
many; this is the second version, which added near-threshold cases (see tools/README.md).

- `task/` is exactly what was uploaded as `tasks/hos-log-audit/`, except the data files
  (environment/data, tests/data) and golden.json / case_tags.json, which generate.py recreates.
- `tools/` is the dev-only generator, calibration script and README.

To regenerate and check it in your sandbox:
1. Recreate the layout `tasks/hos-log-audit/` (copy of `task/`) and `tools/hos-log-audit/` (copy of `tools/`)
   under one folder. generate.py writes into `../../tasks/hos-log-audit` relative to itself.
2. `python3 tools/hos-log-audit/generate.py`
3. `python3 <skill>/templates/local_check.py tasks/hos-log-audit` should print ORACLE 13 passed, NOP failures, OK.

Note: this example's calibrate.py writes to /app (it was run in a container where /app was writable).
For new tasks use `templates/calibrate.py`, which works in any sandbox.

What to learn from it:
- generate.py: hand-worked planted drivers with the arithmetic in comments; realistic filler fleets;
  `contested()` that regenerates any record needing an open reading; shuffled ids.
- solve.py (minute scan) and engine.py (interval arithmetic): two independent methods that agree on
  every row.
- test_outputs.py: engine vs golden, format, hand-worked, one test per rule family, full output.
- instruction.md: 585 words, facts only, cites the rule, no numbers from the rule, exact output spec.
