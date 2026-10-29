# Building the task

Language: Python 3.11, standard library only, in every file (solve.py, engine.py, tests, authoring
scripts). No numpy or scipy: the agent image has none installed and the verifier image has only
pytest and pytest-json-ctrf. Work in `/home/user/<repo>/tasks/<task-name>/` (or the sandbox's
working folder) and keep a scratchpad for temporary files.

Create the folders first:
```
mkdir -p tasks/<t>/{environment/data,solution,tests/data,authoring/evidence,authoring/sources}
```
Copy the unchanged templates: `environment.Dockerfile` to `environment/Dockerfile`,
`tests.Dockerfile` to `tests/Dockerfile`, `test.sh`, `tests.dockerignore` to `tests/.dockerignore`,
`solve.sh` to `solution/solve.sh`, `local_check.py` to `authoring/local_check.py`.

## 1. Source text

`pdftotext <pdf> authoring/sources/<name>.txt` (or `-layout` for tables). Read the method
sections, every table you use, and every worked example. List:
- the equations and constants (copy exactly, including printed constants like 0.46 and 2.67);
- worked-example numbers usable as golden checks, and which of them are rounded or wrong;
- the places where the text and the example disagree, or the text leaves a choice. Each becomes a
  settled point in instruction.md, phrased as the office's practice and tied to the example.

## 2. authoring/sim.py, the generator's model

A complete implementation of the method with step functions the generator can call while it builds
data (for example `pipe_state(...)`, `structure_state(...)`, `amount_at(...)`, `fit(...)`) and a
whole-case `evaluate()` used for agreement. Use a numerical method different from the solution's
(bisection in depth versus Newton in angle; state propagation versus superposition).

## 3. authoring/generate.py

- `SEED = <int>`; `random.Random(SEED)`; no unseeded randomness anywhere.
- Build cases from realistic parameter ranges taken from the standard (cite them in the docstring).
- Add the real-world mess: irregular timing, interruptions, partial events, rejected or flagged
  values, order changes, shuffled record order, redundant fields (for example pump rate next to
  recorded volume) whose correct use the instruction settles.
- **Write values at the precision real records have** (times to the minute, volumes to 1 mL,
  elevations to 0.01 ft, levels to 0.1 mg/L), and compute the answers from the written values.
- **Planting**: for each boundary that changes an output, move one input on its written grid
  (0.01 ft, 0.1 mg/L, 1 minute) and recompute until the signed distance to the boundary lies in a
  band (for example 0.002 to 0.03 ft, or 0.05 to 0.6 percent), on a randomly chosen side. Plant
  15 to 30 percent of cases. Count planted cases in a `STATS` Counter and print it.
- **Margins**: after building each case, compute every comparison that decides a category and
  reject or re-draw the case if any is closer than the minimum margin (for example 0.001 ft,
  0.05 percent, 0.5 mg). Exception: structural ties where the same quantity is reached two ways by
  construction (a pipe at normal depth has HGL = invert + yn exactly); set them exactly in all
  three implementations and let the verifier accept either letter within 1e-6.
- Avoid ambiguous inputs entirely (a level drawn during a pause when the rule speaks of
  infusions; a time exactly on a boundary). Reject them in the generator rather than adding rules.
- Avoid DST: choose an epoch after the spring change and keep all dates before the autumn change.
- Write both data copies (`environment/data`, `tests/data`) identically.
- Print a summary: counts per category and outcome, planted counts, redraws.
- Tune distributions until every outcome category and every family has dozens of cases.

## 4. solution/solve.py

`DATA = Path("/app/data")`, `OUT = Path("/app/output")`, a `main()` that writes the CSV. Clear
names, short comments, one pass per case. Use closed forms where they exist. Parse times as naive
datetimes with an explicit reference (`(t - datetime(2000,1,1)).total_seconds()`), never
`.timestamp()` (local timezone). Format numbers exactly as the instruction says.

## 5. tests/engine.py

Independent: different parsing code, different structure (queue versus recursion), different
solver (Illinois regula falsi, safeguarded Newton, Gauss-Legendre quadrature), different algebraic
form. It exposes:
- `DATA = Path(__file__).resolve().parent / "data"`
- `load(data=None)` and `expected(...)` returning truth rows sorted like the output, with the set of
  accepted letters where a structural tie exists, and family tags computed from its own trace;
- small functions that golden.json calls (published worked-example checks);
- `math.isfinite` checks on parsed inputs and computed results (static check T8).

## 6. tests/golden.json

`{"examples": [{"source": "<document, example, step, printed value>", "check": "<engine function>",
"args": [...] or {...}, "expect": <printed value>, "tol": <covers the printed rounding>}]}`.
Use published worked examples first, then closed-form textbook results. If a printed value is
rounded from a rounded intermediate, widen that one tolerance and say why in "source". If a
printed value is wrong, leave it out and note it in the authoring README.

## 7. tests/test_outputs.py (copy `templates/test_outputs.py`)

Fixtures: `truth` (engine), `rows` (header exact, no blank lines, column count), `got` (parsed,
with `math.isfinite` on every number). Tests:
1. engine matches published examples (golden.json);
2. inputs are consistent (ids, tree or record structure);
3. values are well formed (regex per column, allowed words);
4. rows are sorted and complete (exact key order);
5. `test_rule_family[<family>]` parametrized over 10 to 15 families, each asserting some case
   exists and every case in it is right;
6. every row.
Comparison: exact for letters, words and rounded integers; relative or absolute tolerance for
continuous values.

## 8. authoring/check_agreement.py

Loads engine truth, the generator's answers (from `sim.py` on the written files) and the solution
output (via `local_check.run_solution`). Prints: row counts; letter or category differences
(must be 0); the largest numeric differences (generator vs engine about 1e-12; solution vs engine
within its printed rounding); the closest distance to every boundary (must be at least the
margin); uniqueness checks (for example one root in a wide range); and **every count the READMEs
quote** (per-family counts from engine tags, numbers of loading doses, order changes, planted
counts). Ends with `AGREEMENT: OK` or `PROBLEM` and a matching exit code.

## 9. authoring/calibrate.py (copy `templates/calibrate.py`)

A dict of shortcut name to a list of `(old_text, new_text)` replacements in solve.py. Each must
apply (`assert s.count(a) >= 1`). Let shortcuts keep going where the reference raises (replace the
raise with a fallback) so you can count wrong rows. Print CAUGHT or MISSED and wrong-row counts;
exit non-zero unless all are caught.

## 10. Verification and packaging

Run the protocol in SKILL.md section 6. Commit (if in git) with a plain message. Zip:
```
find tasks/<t> -name __pycache__ -type d -prune -exec rm -r {} +
zip -qr <scratch>/<t>.zip tasks/<t> -x '*__pycache__*'
unzip -l <scratch>/<t>.zip | tail -1
```
Send the zip, then a short summary with the numbers.
