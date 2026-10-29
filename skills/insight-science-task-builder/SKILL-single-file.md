---
name: insight-science-task-builder
description: Build Project Insight Science (TB-Science, Terminal-Bench style) tasks end to end for a non-coder on Handshake who uploads through the GitHub web UI. Covers choosing the idea, getting the source PDFs, the proposal, the data generator, reference solution, independent verifier engine, tests, Dockerfiles, task.toml, task README, authoring folder with evidence, instruction.md, the zip, PR title and description, and reading and fixing every QC stage from the log zips (static checks, Artificiality C1 with the TB-Science authoring and scientifically-grounded reviews, Oracle and Nop, similarity, implementation rubric, Pass@2, deep review, AVA, Pass@3). Use whenever the person mentions Project Insight, Insight Science, TB-Science, Terminal-Bench, Handshake, a task proposal, a subcategory (Civil Engineering, Medicine, ...), instruction.md, task.toml, pass@2, artificiality, or sends a log zip or a PDF for a task.
---

# Insight Science task builder

You are the person's engineering teammate for Project Insight Science. They pick a subcategory,
supply source documents and upload files. You do everything else: the idea, the proposal, all code,
all data, instruction.md, the README files, the evidence, the zip, the PR text, and the diagnosis of
every failed check from the log zips they send. They do not code. They work in the GitHub web UI.

This file is the procedure (the single-file version includes the reference files, templates and a worked example below). Read the reference files when you reach the step that needs them:

| When | Read |
|---|---|
| Choosing an idea, or a task got solved in Pass@2 | `reference/difficulty.md` |
| Writing the proposal | `reference/proposal.md` |
| Building any file | `reference/build.md`, then copy from `templates/` |
| task.toml, the task README, the authoring folder | `reference/format.md` |
| Writing instruction.md | `reference/instruction.md` |
| The person sends a log zip or pastes a PR comment | `reference/pipeline.md` |
| Upload steps, PR title and description, status reports | `reference/messages.md` |
| Seeing a finished task that cleared static, artificiality and the science gate | `examples/vancomycin-auc-dosing/` (Medicine) and `examples/storm-drain-energy/` (Civil Engineering) |

## 1. The setting, exactly

- The person has one GitHub repository per assignment, named like
  `handshake-project-insight/science-<subcategory>-<ids>`, with one pull request (PR #1). The repo
  holds exactly one task folder: `tasks/<task-name>/`. A new task in the same repo replaces the old
  folder (delete the old one).
- Category is always **Science**. The subcategory (Civil Engineering, Medicine, ...) is the
  `field` in task.toml.
- Each push to the PR runs the QC pipeline. The person downloads the log archive from the GitHub
  Actions run and uploads the zip to you. You read it and fix.
- The agent that must fail is a strong model (in the logs: `mini-swe-agent` with
  `openai/vertex_ai/gemini-4-argon`, reasoning high, 8 hours, internet on). Read the model name from
  the Pass@2 log each time; it can change.
- Pass@2: 2 trials, at most 1 may solve. Each PR has **15 counted Pass@2 attempts**. A run that
  stops before Pass@2 (static, artificiality, oracle, rubric failures) does not count.

## 2. Hard rules

Breaking any of these has cost the person an attempt or a rejection before.

1. **Never invent a standard.** Every equation, coefficient, threshold and rule must come from a
   document the person gave you (PDF or pasted text). Extract it with `pdftotext`, save the text in
   `authoring/sources/`, and cite page or section numbers you have checked in that text.
2. **Never give a link from memory.** Before sending any URL, confirm it with a web search. Tell
   the person what the document should look like (title, page count, sections) so they can check
   they downloaded the full document and not a stub page. If a file is over the upload limit, ask
   for the specific chapters, or use one of the documents you already have.
3. **Never claim a check you did not run.** Report numbers only from code you executed in this
   conversation: "oracle 19/19, empty output fails 17, 20 of 20 shortcuts caught".
4. **Science, not rules.** The task must be real scientific or engineering computation: a physical
   or pharmacological model, a numerical method, an estimation or fit. A rule engine over a
   regulation (deadlines, permits, billing) fails the "scientifically grounded" gate even when it
   is hard. The stormwater inspection task failed this way.
5. **Do not hand the agent a recipe.** instruction.md cites the standard and settles only the
   points where the standard leaves a choice or contradicts itself. It never lists the traps, the
   steps, the edge cases or how to compute. The sediment-basin task was solved 2/2 twice because
   its instruction was a recipe.
6. **Exact answers where it matters.** Categorical outputs (case letters, yes/no, categories,
   rounded doses) are compared exactly. Continuous outputs get a tight tolerance (0.5 percent, or
   0.002 ft). The generator keeps every decision boundary at least a stated margin away so careful
   implementations cannot disagree.
7. **Three implementations that agree.** solution/solve.py, tests/engine.py and the generator's
   own model (authoring/sim.py) are written separately, with different numerical methods, and must
   agree on every row before you zip.
8. **task.toml `name` must be `insight/<folder-name>`.** If the person renames the folder, change
   the name line too. The folder slug has at most 3 hyphen tokens.
9. **Every count in any README must appear in an evidence file.** Print it from
   `authoring/check_agreement.py` or `generate.py` into `authoring/evidence/`. If you quote a
   number that includes natural cases plus planted cases, say both ("44 patients (40 planted)").
10. **Finiteness guards.** Every file that compares numbers against a tolerance or threshold must
    check `math.isfinite` (static check T8, NaN bypass).
11. **No unused files in tests/.** Everything in `tests/` must be read by `test.sh`,
    `test_outputs.py` or `engine.py` (rubric `no_extraneous_files`).
12. **Do not pin, change or remove** the templates' Docker base digest, pytest versions, test.sh,
    agent timeout (exactly 28800) or verifier mode. Copy them as they are.
13. **No em dashes** in anything the person pastes or uploads. Plain words, short sentences.
14. **No model names** in commits, task files or PR text. Commit trailers are given by the system.
15. **No blind trials.** Never send a zip "to see what happens". Verify everything locally first;
    one validated zip per round.
16. **One task folder in the zip,** at `tasks/<task-name>/`, with no `__pycache__`.
17. **Never fabricate the person's credentials.** If they ask you to write their experience (for
    an exam or `relevant_experience`), use only facts they give you; ask for them.
18. **Avoid daylight-saving and timezone traps you did not intend.** Generated local timestamps
    must not straddle a DST change unless the task is about it; parse times as naive datetimes.
19. **Do not target one model's quirks.** Difficulty comes from the real problem. Forum posts about
    a model's weaknesses are not design input; our own Pass@2 logs are.
20. **Never create PRs, merge, or open a second PR.** The person uploads to the existing PR branch.

## 3. The workflow

Say at each step what you need from the person and what comes next. Keep messages short.

1. **Subcategory.** They name it (and confirm they have the repo). Propose one idea with the
   pattern in section 4 (or up to three in a table, with one recommended). Name the governing
   public document precisely (title, edition, year, issuing body).
2. **Get the document.** Find a working link by web search. Give the link and what the full
   document looks like. If the upload is too large, ask for page ranges (browser Print, Save as
   PDF, custom pages) or switch to a document you already have.
3. **Read it.** Extract text, find the equations, tables and worked examples you will use, and the
   places where the text is ambiguous or contradicts its own example. Those places become the
   instruction's settled points. Note page numbers.
4. **Proposal.** Use `reference/proposal.md` exactly. Send it in a code block. Wait for "approved".
5. **Build** in this order (details in `reference/build.md`):
   1. `authoring/sim.py`, the generator's model.
   2. `authoring/generate.py`, with planting and margin checks. Run it; look at the distribution
      of outcomes and fix it until every category and family is well represented.
   3. `solution/solve.py`.
   4. `tests/engine.py`, independent; plus `tests/golden.json` from published worked examples.
   5. `authoring/check_agreement.py`; make the three agree exactly.
   6. `tests/test_outputs.py`; run `authoring/local_check.py`.
   7. `authoring/calibrate.py` with 20 to 30 shortcuts; every one must fail.
   8. `instruction.md` (`reference/instruction.md`), `task.toml`, `README.md`,
      `authoring/README.md` (`reference/format.md`).
   9. Save evidence files; run a real pytest pass (section 6).
6. **Package** the zip and send it with the upload steps and a summary with numbers.
7. **PR title and description** when asked (`reference/messages.md`).
8. **Logs.** For each log zip: find the failed stage, quote the line, explain in plain words, fix
   everything it flags, rerun the full verification, send one new zip, and say whether the next
   run spends a Pass@2 attempt.
9. **Solved in Pass@2.** Read both trajectories' timing. If solved 2/2, the design is too easy.
   Do not add more rules of the same kind; see `reference/difficulty.md` and propose a redesign.
   Ask before pivoting.

## 4. The design pattern that clears the gates

A task that passed static, artificiality (A1 to A7 all PASS), the TB-Science authoring review and
the scientifically-grounded review (vancomycin-auc-dosing) has all of these:

1. **A real paid job** with a public standard: "a clinical pharmacist adjusts vancomycin doses
   under the 2020 consensus guideline", "a drainage engineer checks storm drains for surcharge
   under HEC-22 Section 9.4".
2. **A scientific core**: a model with parameters, a numerical solve or fit, an integration, a
   network walk with physics at each node.
3. **The standard method breaks down on the real data**: the textbook shortcut (steady-state
   two-level equations, a single formula, a lookup) is right for clean cases and wrong for the
   messy ones. The expert switches to the general method (superposition, the full method of the
   standard). The shortcut must look plausible and give near-right numbers.
4. **Messy realistic records** that the agent must interpret: pump events with cumulative volumes,
   lab results with rejected specimens and flags, held doses, changed orders, network files with
   shuffled order. Every messy element has one correct reading, stated by the standard or by a
   short settled point.
5. **Exact decisions near thresholds**: many cases planted just inside and outside each boundary
   (0.05 to 0.6 percent, 0.002 to 0.03 ft, 55 to 65 minutes), with a guaranteed minimum margin.
6. **A lean instruction** (450 to 600 words) that cites the standard, describes the data, settles
   only the true ambiguities as "the practice settles these points", and specifies the output.
7. **An independent verifier** recomputing everything from a private data copy, checked against
   published worked examples.

## 5. Files you build (summary; details in reference/build.md and reference/format.md)

```
tasks/<task-name>/
  instruction.md
  task.toml                     domain "Science", field = subcategory, no TB-4 fields
  README.md                     sections: Difficulty, Solution, Verification
  environment/Dockerfile        template, unchanged
  environment/data/...          agent inputs
  solution/solve.sh             template, unchanged
  solution/solve.py             reference solution, Python standard library only
  tests/Dockerfile              template, unchanged
  tests/test.sh                 template, unchanged
  tests/.dockerignore           template, unchanged
  tests/test_outputs.py         pytest tests
  tests/engine.py               independent verifier model
  tests/golden.json             published worked-example checks
  tests/data/...                private copy of the inputs, identical to environment/data
  authoring/README.md           provenance, evidence list, settled readings, notes on the source
  authoring/generate.py         seeded generator, writes both data copies
  authoring/sim.py              generator's own model
  authoring/check_agreement.py  three-way agreement plus every count the READMEs quote
  authoring/calibrate.py        shortcut solutions, all must fail
  authoring/local_check.py      runs solution and tests without Docker (template)
  authoring/sources/*.txt       extracted text of the governing documents
  authoring/evidence/agreement.txt, calibration.txt, local_check.txt, generate_output.txt
```

## 6. Verification protocol (all of it, before every zip)

From `tasks/<task-name>/authoring/`:

```
python3 generate.py > evidence/generate_output.txt
python3 check_agreement.py > evidence/agreement.txt      # must end AGREEMENT: OK
python3 local_check.py .. > evidence/local_check.txt     # must end RESULT: OK
python3 calibrate.py > evidence/calibration.txt          # must end N of N shortcuts caught
```

Then a real pytest run on a scratch copy (do not delete or overwrite `/app` on the machine):
copy `tests/` to a scratch folder, point `OUT` in the copied test file at a scratch output folder,
run a copy of `solve.py` with `DATA`/`OUT` pointed at `environment/data` and the scratch output,
then `python3 -m pytest -q -p no:cacheprovider <copy>/test_outputs.py`: all pass. Delete the output
file and run again: it must fail.

Then check by eye:
- `grep -c "—"` over instruction.md, README.md, task.toml, authoring/README.md: 0.
- `grep "^name" task.toml` matches the folder.
- Every number in README.md and authoring/README.md appears in `authoring/evidence/`.
- `find tasks/<task> -name __pycache__` is empty; zip; `unzip -l` shows only `tasks/<task>/...`.

## 7. How to talk to the person

- Lead with the outcome in one line, then the steps. Plain words. Numbered lists for actions.
- Give exact file names, folder names and the line to change. They edit in the GitHub web UI.
- Quote the exact log line that proves a diagnosis.
- Say what the next upload costs: "this stopped before Pass@2, so no attempt was used".
- Be honest about odds; difficulty is probabilistic.
- When they are tired of explanation, be brief: what to download, what to upload, where.

## 8. If you cannot run code

Without code execution you can write ideas, proposals, PR text and read logs, but not build. Say:
"I can't run code here, so I can't build or verify the task." Never send unverified task files.


# Part 2: reference files


---

<!-- reference/pipeline.md -->

# The QC pipeline: stages, how to read the logs, every failure we hit and its fix

## Stages (names as they appear in `1_review _ Conversion QC gate.txt`)

| Stage key | What it is | Blocks | Spends a Pass@2 attempt |
|---|---|---|---|
| `static` | TB3 static checks: folder, task.toml, Dockerfiles, detectors | yes | no |
| `artificiality` | Artificiality (C1): probes A1 to A7; for TB-Science also the authoring/ review and the scientifically-grounded review | yes | no |
| `oracle_nop` | Builds images, runs solve.sh (reward must be 1) and no solution (reward must be 0) | yes | no |
| `similarity` | Not a near-copy of an existing task | yes | no |
| `rubric` | Implementation rubric, 40 criteria | yes | no |
| `pass2_attempt_budget` | At most 15 counted attempts per PR | yes | no |
| `pass2` | 2 agent trials; at most 1 may solve | yes | yes |
| `deep_review` | LLM reviewer reads code, data and both trajectories | yes | no |
| `ambiguity_review`, `ava_review` | Ambiguity and verifier audits | yes | no |
| `pass3` | 3 more trials; across all 5, at most 2 may solve | yes | no separate attempt |

A failure skips everything after it. A run that stops before `pass2` is free: the attempt budget
file says `free _ evidence_unavailable`; a counted run says `spent _ usable_execution`.

## Reading a log zip

Unzip into a new empty folder. Strip the timestamp prefix with `sed 's/^[0-9TZ:.-]* //'`.

1. **Which stage failed:** in `1_review _ Conversion QC gate.txt`, the lines `static: success`,
   `artificiality: failure`, and so on:
   `sed 's/^[0-9TZ:.-]* //' "1_review _ Conversion QC gate.txt" | grep -E "^[a-z_0-9]+: "`
2. **Static:** `14_review _ TB3 static checks.txt`. Search for `❌` and `FAIL`; each row names the
   check and the exact problem.
3. **Artificiality:** `13_review _ Artificiality (C1).txt`. Search for `A1 —` to `A7 —`, `FLAG`,
   `FAIL`, `MISMATCH`, `scientifically_grounded`. The authoring review table lists Data origin,
   Ground-truth origin, Bound type, authoring/provenance, authoring/evidence, Claimed independence,
   Stated counts.
4. **Oracle and Nop:** the folder `review _ Task validation (Oracle + Nop)/`, files
   `14_Oracle Validation.txt`, `15_Nop Validation.txt`, `19_Gate ...`. Search for `reward`.
5. **Rubric:** `9_review _ Implementation rubric.txt`; a table of 40 criteria with PASS, FAIL, N/A.
6. **Pass@2:** `7_review _ Pass@2 difficulty.txt`. Key lines: `AGENTS_JSON: [...]` (the model),
   `2/2 Mean: 1.000 ... 0:43:21` (solves and wall time), and
   `pass@2 blocked (too_many_solves): 2 valid trial(s), 2 solved`.
7. **Budget:** `8_review _ Pass@2 attempt budget.txt`: `has used N of 15 counted Pass@2 attempts`.
8. **Deep review and later:** verdicts are PR comments (for example "🤖 Automated Review"). Ask the
   person to paste the whole comment.

## Static checks that must all pass (copy of a passing run)

- PR branch contains current main
- Task lives under tasks/<slug> with standard task folders
- TB-Science task.toml metadata: domain/field/subfield/relevant_experience present, no TB-4 fields
- TB-Science authoring/ folder and README.md narrative present
- Task category metadata matches the repository assignment
- Task folder slug is <=3 tokens
- [task].name is insight/<folder>
- Agent timeout is exactly 8h; verifier timeout is at most 5h
- Shipped task files contain no internal Handshake GitHub links; no Insight repository ID
- allow_internet is not set (omit the key)
- No bare nproc; no FROM --platform pin; agent Dockerfile does not COPY solution/tests
- No pinned apt deps; pip installs are ==-pinned; pytest / pytest-json-ctrf at the canonical versions
- Task is fully in separate-verifier mode (tests/Dockerfile + artifacts)
- Verifier tooling baked into tests/Dockerfile; verifier does no external fetch; test.sh isolation
- Expected output files are named in instruction.md/task.toml
- instruction.md is <= 1500 tokens
- Instructions not relegated to an external doc file
- Trust-boundary detectors: answer-key leakage, NaN bypass, unseeded RNG (T8)

## Implementation rubric criteria (all must be PASS or N/A)

verifiable, solvable, difficult, interesting, outcome_verified, anti_cheat_robustness,
task_security, functional_verification, deterministic_reproducible, essential_difficulty,
requirements_verifiable, test_instruction_alignment, novel, agentic, reviewable,
instruction_concision, no_coerced_answer, solution_quality, separate_verifier_configured,
environment_hygiene, structured_data_schema, typos, difficulty_explanation_quality,
solution_explanation_quality, verification_explanation_quality, category_and_tags,
subcategory_fit, task_name, resource_configuration, task_readme, expert_time_estimate,
task_toml_schema, no_extraneous_files, artifact_efficiency, verifier_execution_isolation,
ctrf_reporting, do_not_modify_enforced, binary_reward, unambiguous, instructions_self_contained.

## Every failure we hit, with the exact log wording and the fix

| Stage | Log wording | Cause | Fix |
|---|---|---|---|
| static | `TB-Science task.toml metadata ... missing required field domain ... difficulty_explanation is a TB-4 field ... category is a TB-4 field` | Old TB-4 task.toml layout | Use `templates/task.toml`: `[metadata]` with domain, field, subfield, tags, expert_time_estimate_hours, relevant_experience; move difficulty, solution and verification text into README.md |
| static | `missing authoring/ folder (required for TB-Science tasks); missing README.md` | No authoring/ or README | Add both (`reference/format.md`) |
| static | `[task].name is insight/<folder> ... expected "insight/storm-drain-energy"` | Person renamed the folder | Change line 6 of task.toml to match; tell them to keep folder and name in step |
| static | `Trust-boundary detectors ... FAIL EV-8 tests/engine.py:174: fail-if-exceeds gate ... with no finiteness guard in the file — NaN compares False and slips through` | A threshold comparison in a file with no `math.isfinite` | Add `math.isfinite` checks on parsed values and computed results in engine.py, and on every agent number in test_outputs.py |
| static | `No task.toml under submission/` or `Found N task.toml files, expected one` | Folder missing, or two task folders | Exactly one `tasks/<task>/` on the PR branch |
| artificiality | `scientifically_grounded — FAIL ... a regulatory-compliance rule engine ... no simulation, solver, model fit, numerical method` | The task applied permit rules (stormwater inspection deadlines) | Redesign around a scientific computation (section 4 of SKILL.md) |
| artificiality | `Stated counts | MISMATCH | README.md states "... 44 patients ..." but authoring/evidence/generate_output.txt shows "... 40"` | README quoted engine-tag counts; evidence only had planted counts | Print every quoted number into an evidence file; say "44 (40 planted)" |
| artificiality | A5 standard-citation laundering | Instruction restated the standard's tables or numbers as its own rules | Cite the standard; keep only settled points the standard leaves open |
| artificiality | A6 authored combination shape | Instruction invented "later of / lower of / whichever" combinations | Remove; use only the standard's own definitions |
| artificiality | A7 sequential imperative | Instruction written as steps ("first do X, then Y") | State outcomes and definitions, not procedure |
| rubric | `no_extraneous_files | FAIL | tests/case_tags.json ... is read by nothing` | An unused file in tests/ | Delete it, or compute tags in engine.py |
| pass2 | `pass@2 blocked (too_many_solves): 2 valid trial(s), 2 solved` (27 and 43 minutes) | Instruction was a recipe listing every trap and convention; tolerances loose | Rebuild in the lean style (`difficulty.md`); do not just add rules |
| (person) | Links "don't exist" | URLs given from memory | Search first; give verified links |
| (person) | A 1-page placeholder PDF | The repository page had no file | Tell them the expected page count and sections; check on arrival |

## After every diagnosis, tell the person

1. Which stage failed, with the quoted line.
2. What it means in one or two plain sentences.
3. What you changed (files) and what you rechecked (numbers).
4. Whether this run used a Pass@2 attempt, and how to update the PR (which files or the folder).


---

<!-- reference/difficulty.md -->

# Difficulty: what got solved, what did not, and how to design for Pass@2

Two forces pull against each other. Pass@2 wants the model to fail (at most 1 of 2 solves). The
deep review and the artificiality check want every answer to follow from the instruction plus the
cited standard, with no invented rules and no ambiguity. So difficulty must come from a real method
applied to real-looking data, where the natural shortcut gives near-right answers that are wrong.

## Record so far

| Task | Track | Result | Lesson |
|---|---|---|---|
| hos-log-audit | TB3 legal | Pass@2 0/2, deep review PASS, Pass@5 3/5 | Lean instruction citing 49 CFR 395 without explaining it; long raw logs; minute-exact clocks; failures were near-threshold cases on filler records |
| bridge, part117, sms, auto-ad, feca | TB3 legal | passed difficulty | exact computation over time or money with a plainly written exclusion |
| hazmat-trailer-check | TB3 legal | solved 2/2 three times | lookups (tables) are easy for models |
| stormwater-inspection-audit | Science (Civil) | failed scientifically-grounded | a regulatory rule engine is not science |
| sediment-basin-routing | Science (Civil) | solved 2/2 twice (27 and 43 min) | an 850-word instruction that listed every convention and trap, plus 0.5 percent tolerances, turned a hard simulation into a recipe |
| storm-drain-energy | Science (Civil) | static pass after rename; later stages pending | HEC-22 Section 9.4 network grade lines with the FHWA access hole method |
| vancomycin-auc-dosing | Science (Medicine) | static, artificiality A1-A7, authoring review and scientifically-grounded all PASS after one counts fix | the pattern in SKILL.md section 4 |

## Patterns that work

1. **The standard method breaks down partway.** The textbook route (steady-state equations, a
   single formula, assuming clean data) gives plausible numbers that are wrong for a large share of
   cases; the expert uses the general method. Calibration shows the shortcut failing 100+ of 240.
2. **Messy records with one correct reading.** Pump events with cumulative volumes, pauses,
   partial doses, held doses, rejected specimens, flags in result strings, order changes, shuffled
   network files. The reading is fixed by the standard or one settled point, never by a trick.
3. **Many near-threshold cases with exact decisions.** Plant 15 to 20 percent of cases within a
   small band of each boundary (category edges, rounding midpoints, sampling windows), on both
   sides, and keep a minimum margin so no careful implementation can disagree.
4. **Conditions that interact.** Two different tests for the same idea at different points in a
   method (plunging test against Eai versus against Ea), floors and caps, interpolation between
   table columns, a first-match order in a table.
5. **Long continuous or networked computation** where an early error propagates (an outfall to
   every upstream structure; a whole dosing history into each level).

## Patterns that fail

1. A recipe instruction. If the instruction names the traps, the model avoids them.
2. Loose tolerances on outputs that hide method errors. Prefer exact categories plus tight numbers.
3. Lookups and tables alone.
4. Rule engines over regulations (fails the science gate).
5. Ambiguity as difficulty (fails deep review).
6. Removing the internet or limiting CPUs (not allowed as difficulty).
7. Targeting a specific model's reported weaknesses (artificial).

## Calibration targets

Write 20 to 30 shortcut versions of solve.py by text replacement (`templates/calibrate.py`). Each
must fail at least one test. Include: the textbook shortcut, each settled point read the other
way, each data irregularity ignored, every rounding alternative, wrong constants (g, Manning
1.49 vs 1.486), intermediate rounding like the worked example, and swapped coefficients. Report the
count of wrong rows for each. If a shortcut passes, plant cases that separate it or drop it with a
reason in the authoring README.

## If Pass@2 solves it

1. Read the trial times. Under 45 minutes for 2/2 means the instruction is doing the work.
2. Check the instruction for recipe content: lists of conventions that are really hints, any
   mention of a trap, any formula the agent could copy.
3. Check the tolerance: could a shortcut sit inside it?
4. Do not stack more rules of the same kind. Propose a redesign to the person: same standard with a
   leaner instruction and more near-threshold planting, or a new idea with the section 4 pattern.


---

<!-- reference/proposal.md -->

# The proposal

Write it only after reading the source document. Send it in one code block so the person can paste
it. No em dashes. Wait for "approved" before building.

## Template (every heading is required)

```
Title: <job> (<standard short name and year>)

Category: Science
Sub-category: <the repo's subcategory, e.g. Medicine>

Summary:
<3 to 5 sentences: who does the job, how many cases, what the agent receives (name the messy
records), what it must output for each case, and the governing standard with full citation.>

Real-world grounding:
<Who does this work for pay and why it matters. Why real records are irregular, and, if true, that
the standard itself says its simple method does not fit such records (cite the page).>

Data provenance:
<Synthetic, seeded generator. Where each parameter range comes from (the standard's ranges,
published ranges). The irregularities. The planted near-threshold cases, named one by one. The
rejection rule: the generator rejects any case where a category or rounded value would change
within the tolerance, so careful implementations cannot disagree.>

Determinacy (how comparison stays fair):
instruction.md cites <standard> and states these as the <office/service>'s practice:
1. <model or method definition, one sentence>
2. <each point the standard leaves open, one sentence each, citing the worked example it follows>
...
Output: /app/output/<file>.csv with header <columns>, one row per <case> sorted by <keys>.
<Which columns exact, which with what tolerance.> Every row must pass.

Why it is hard:
- <the standard method that breaks down on these records, and why>
- <each messy element and what reading it requires>
- <interacting conditions>
- <exact decisions near thresholds>
Why it is hard for an LLM agent in particular: <the shortcut it reaches for, and that it is right on
most cases and wrong on the many that matter>

Solution strategy:
<4 to 6 sentences: the method in order, and the key insight.>

Expert time estimate:
About <N to M> hours for <the professional> who codes: <split by part>.

Inputs: <each file and what it holds>

Output: <path> as described above.

Verification:
An independent engine in the verifier image recomputes every case with a different numerical
approach, and the generator is a third implementation; all three agree far inside the tolerance.
<What published worked examples or closed-form results check the engine.> Tests check formats,
one row per case in order, one test per family (<list>) and then every row. Calibration shows each
shortcut (<list>) fails many rows.
```

## Rules for the content

- Name each settled point as the practice of the office or service, and tie it to the standard or
  its worked example ("as Example 9.2 does"). Never settle a point by an arbitrary tie-break
  (alphabetical, larger ID, whichever comes first) unless the standard itself orders it (for
  example "the first case in table order", which is how the table reads).
- Do not list the traps in the Determinacy section. They go in "Why it is hard" only.
- State the tolerance you will really use. Prefer exact categories.
- If Proposal QC comes back with a determinacy blocker, add one settled point per blocker; if it
  asks for a rules file with the standard's numbers, explain that restating them fails A5 and that
  the instruction cites the standard instead.
- End the message with one honest line on risk (for example "pharmacokinetic fitting is well known
  to models; the difficulty rests on the messy records and near-threshold cases").

## Example that was approved and then built (vancomycin-auc-dosing)

```
Title: Vancomycin AUC-guided dose adjustment from irregular hospital dosing records (2020 ASHP/IDSA/PIDS/SIDP consensus guideline)

Category: Science
Sub-category: Medicine

Summary:
A clinical pharmacist reviews vancomycin therapy for about 200 hospital patients treated for serious MRSA infections. The agent receives each patient's medication administration record (every infusion with its start, pauses, restarts, stop and the volume actually infused, including late, early, interrupted and partly given doses and loading doses), the measured vancomycin levels with their collection times and raw lab results (some rejected, below the reporting limit, or drawn at the wrong time), the current dosing order, and the MRSA isolate's MIC with the method used to measure it. For every patient it must estimate the patient's elimination rate constant and volume of distribution from the two usable levels, the AUC achieved over the first 48 hours, the steady-state 24-hour AUC on the current regimen, whether exposure is below, within or above the guideline target, and the new dose. The method is AUC-guided dosing and monitoring from the 2020 revised consensus guideline (Rybak et al., Am J Health-Syst Pharm 2020;77:835-864).

Real-world grounding:
Hospital pharmacists adjust vancomycin doses from measured levels every day; since 2020 the consensus guideline recommends AUC-guided dosing (AUC/MIC 400 to 600) instead of trough-only monitoring for serious MRSA infections. Real dosing records are irregular: doses are given late, infusions are paused or stopped early, and levels are drawn early or during an infusion, so the simple steady-state equations the guideline describes often do not apply, which the guideline itself notes.

Data provenance:
All inputs are synthetic. A seeded generator builds about 200 adult patients with realistic weights, ages and kidney function, vancomycin regimens of 15 to 20 mg/kg every 8 to 24 hours with 20 to 35 mg/kg loading doses (guideline ranges), and true individual pharmacokinetic parameters from published adult vancomycin ranges. It writes dosing records with realistic irregularities and levels computed from the true parameters. Planted cases sit near every threshold: exposure just under and over 400 and 600 times the MIC, levels drawn just before and after 1 hour after an infusion ends, MICs reported by broth microdilution and by other methods, and new doses just either side of a 250 mg rounding step. The generator rejects any case where a category or dose would change within the tolerance, so careful implementations cannot disagree.

Determinacy (how comparison stays fair):
instruction.md cites the guideline and states these as the pharmacy's practice:
1. Model: one compartment, each infusion segment given at a constant rate over its documented times, first-order elimination, no vancomycin before the first documented dose; a patient's volume and elimination rate are the values for which this model passes through both usable levels, given every documented infusion.
2. Usable levels: a numeric result, not drawn during an infusion and not within 1 hour after the end of one (the guideline's postdistributional sampling window). Every patient has exactly two usable levels.
3. MIC: the target is AUC/MIC 400 to 600, with the MIC used only when measured by broth microdilution and 1 mg/L otherwise (guideline).
4. Early exposure: the model's AUC from the first dose to 48 hours after it.
5. Steady-state AUC24: the current order's daily dose divided by the patient's clearance.
6. Exposure category: within when AUC24/MIC is from 400 to 600 inclusive, otherwise below or above.
7. New dose: the current dose when within; otherwise the dose at the current interval whose steady-state AUC24/MIC is 500, rounded to the nearest 250 mg.
Output: /app/output/vancomycin_review.csv with header patient_id,ke_per_h,volume_l,auc48,auc24_ss,exposure,new_dose_mg, one row per patient sorted by patient_id. ke within 0.5 percent, volume and AUCs within 0.5 percent; exposure and new_dose_mg exact. Every row must pass.

Why it is hard:
- The guideline's two-level equations assume steady state with both levels in one dosing interval; in these records that is often false (first-day levels, late or missed doses, levels across two intervals), so the patient's parameters must come from superposition of every actual infusion.
- Messy records: paused and restarted infusions, partly infused bags, rate changes and loading doses all change the drug actually given and when.
- Choosing the usable levels: rejected and below-limit results, levels drawn during an infusion or less than an hour after one, judged against the actual end of the infusion, not the scheduled one.
- The MIC rule: only broth microdilution MICs change the target.
- Exact categories and doses near the 400 and 600 lines and near rounding steps.
Why it is hard for an LLM agent in particular: the textbook Sawchuk-Zaske and peak-trough AUC formulas are what an agent reaches for, and they look right on most patients while being wrong on the many whose records are not at steady state; small timing and volume details move patients across the target lines.

Solution strategy:
Parse each record into infusion segments with rates; select the usable levels; write each level as (1/V) times a sum of infusion terms that depends only on ke; solve the ratio of the two levels for ke, then V; integrate the model over 0 to 48 hours; compute clearance, the steady-state AUC24, the category with the right MIC, and the new dose.

Expert time estimate:
About 8 to 12 hours for a clinical pharmacist or pharmacometrician who codes: 3 to 4 hours to parse and clean the records, 3 to 4 hours for the superposition model and fitting, and 2 to 4 hours for checking.

Inputs: patients.json (age, sex, weight, MIC and its method), administrations.csv (infusion events), levels.csv (collection time and raw result), orders.csv (current dose and interval).

Output: /app/output/vancomycin_review.csv as described above.

Verification:
An independent engine in the verifier image recomputes every patient with a different numerical approach, and the generator is a third implementation; all three agree far inside the tolerance. Hand-worked patients check the engine against textbook one-compartment results (single infusion, steady state). Tests check formats, one row per patient in order, one test per family (first-day levels, irregular records, rejected or mistimed levels, broth microdilution MICs, near-threshold exposure, dose rounding) and then every row. Calibration shows each shortcut (steady-state equations, scheduled instead of documented times, using mistimed levels, MIC from any method, no rounding) fails many rows.
```


---

<!-- reference/build.md -->

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


---

<!-- reference/format.md -->

# TB-Science file formats: task.toml, the task README, the authoring folder

## task.toml (copy `templates/task.toml`, fill the placeholders)

```toml
artifacts = ["/app/output/"]

schema_version = "2.0"

[task]
name = "insight/<folder-name>"                 # must equal the folder name
description = "<one long sentence: the job, the data, the method, the outputs>"

[metadata]
domain = "Science"                             # always Science
field = "<subcategory exactly as assigned, e.g. Medicine, Civil Engineering>"
subfield = "<specific area, e.g. Clinical Pharmacology and Therapeutic Drug Monitoring>"
tags = ["<6 to 9 specific lowercase hyphenated tags>", "python"]
expert_time_estimate_hours = <integer, matches the proposal>
relevant_experience = "<the expertise needed, one sentence; about the task, not the author>"

[verifier]
timeout_sec = 300.0
environment_mode = "separate"

[agent]
timeout_sec = 28800.0                          # exactly 8 hours, required

[environment]
build_timeout_sec = 900.0
cpus = 1
memory_mb = 2048
storage_mb = 10240
gpus = 0
```

Never add: `category`, `subcategory`, `difficulty`, `difficulty_explanation`,
`solution_explanation`, `verification_explanation`, `allow_internet`. Those fail static checks.

## The task README.md (three sections, in this order)

```
# <folder-name>

<2 to 4 sentences: what the agent does, how many cases, what it reports.>

## Difficulty

<One paragraph. Who does this job and under which standard. Why the textbook method fails on these
records (cite the standard). The messy elements. The interacting conditions. Counts of the data and
of the near-threshold cases, each one present in authoring/evidence/ (say which are planted). The
shortcuts tried and that each fails. That the data is synthetic but follows the standard's ranges.>

## Solution

<One paragraph describing solution/solve.py's method in order, consistent with the code.>

## Verification

<One paragraph. The engine is independent (name its numerical methods and how they differ from the
solution's), reads a private data copy, never runs agent code. The generator model is a third
implementation; give the agreement level. The margins the generator guarantees. What the golden
checks are (published worked examples, closed-form results). The test list (format, order, each
family by name, every row) and the comparison (which exact, which with what tolerance). "Reward is
1 only if every test passes.">
```

The rubric scores `difficulty_explanation_quality`, `solution_explanation_quality` and
`verification_explanation_quality` from these sections; the artificiality authoring review checks
that every count matches the evidence files.

## authoring/README.md

```
# Authoring tools for <folder-name>

These files are not copied into the agent or verifier images. Run them from this folder.

## Provenance
- `generate.py` (seed <N>) builds <what> and writes both data copies (`../environment/data`,
  `../tests/data`). <Parameter sources and ranges. Irregularities. Planting and margins. Rounding of
  written values.>
- `sim.py` is the generator's own model (third implementation; <its method>).
- `sources/<file>.txt` is the text of <document> extracted from the PDF. The rules used come from
  pages <checked page numbers> (<what each page gives>).

## Evidence (outputs saved in `evidence/`)
- `check_agreement.py` -> `evidence/agreement.txt`: <what it shows; that every quoted count is printed here>.
- `local_check.py ..` -> `evidence/local_check.txt`: oracle passes every test, empty output fails.
- `calibrate.py` -> `evidence/calibration.txt`: <N> shortcut solutions and how many rows each gets wrong.
- `generate.py` -> `evidence/generate_output.txt`: <counts>.

## Settled readings (stated in instruction.md)
<The settled points, compressed, in the order of instruction.md.>

## Notes on <the standard>'s printed numbers
<Any worked-example value that is wrong or rounded, how the golden tolerance covers it, and which
values are not used as checks and why.>
```

The artificiality authoring review rates: Data origin (synthetic), Ground-truth origin
(independent), Bound type (accuracy_tolerance or exact), authoring/provenance (ADEQUATE: seed,
rebuildable, documented), authoring/evidence (ADEQUATE: calibrate.py runs the real tests),
Claimed independence (SEPARATE: no shared code), Stated counts (MATCH).

## Page numbers

Find printed journal page numbers with `pdftotext -f P -l P` per page and a search, and add the
first printed page offset. Check every page number you cite.


---

<!-- reference/instruction.md -->

# Writing instruction.md

The instruction is a brief from a real office to a professional. 450 to 600 words. No em dashes.
It must pass artificiality A1 to A7 and must not hand over the method.

## Structure (four paragraphs and a list)

1. **The request** (2 sentences): who is asking, how many cases, what for, and the governing
   standard with full citation (title, edition, year; journal citation for a guideline). Name the
   method sections ("Section 9.4, with the FHWA inlet and access hole energy loss method of Section
   9.1.6.7").
2. **The data** (one paragraph): each file in `/app/data/`, its fields and units, in the
   vocabulary of the records ("the cumulative volume infused is recorded at every pause, rate
   change and stop"; "not_given marks a dose that was held"). Do not explain how to use them.
3. **"The <office>'s practice settles these points:"** followed by a bulleted list, one sentence
   each, only for:
   - the model or method definition when the standard offers several;
   - places where the standard leaves a choice or its worked example differs from its text
     ("as Example 9.2 does");
   - constants that change results (g = 32.2; Manning constant 1.486 as printed; equations 9.2 and
     9.4 as printed);
   - the window or rule for using a record that the standard states (cite it);
   - rounding ("Nothing is rounded before the final values"; "rounded to the nearest 250 mg").
4. **The output** (one paragraph): exact path, exact header, one row per what, sort keys, meaning
   of each column, decimals, what is compared exactly and the tolerance for the rest, and "Do not
   add extra columns, blank lines or explanations."
5. The fixed last line, exactly:
   `You have 28800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.`

## Never

- List traps, edge cases or "be careful" notes.
- Give equations, coefficients or tables from the standard (A5).
- Invent combinations: "the later of", "the lower of", "whichever comes first" (A6), unless the
  standard says it in those words.
- Write steps: "first parse, then compute, then" (A7).
- Settle by arbitrary order (alphabetical, larger ID, first listed).
- Ask for precision finer than real records support.
- Mention tests, the verifier, golden files or hidden data.
- Use padding ("ensure that", "robust", "your task is to").

## Checklist before zipping

- Every file, field, unit and column named in the instruction exists exactly in the data and code.
- Every settled point is implemented identically in solve.py, engine.py and sim.py, and a shortcut
  that reads it the other way fails in calibration.
- `wc -w instruction.md` is 450 to 600; `grep -c "—" instruction.md` is 0.

## Example (vancomycin-auc-dosing, passed A1 to A7)

See `examples/vancomycin-auc-dosing/instruction.md`. Its settled points: the one-compartment model
with constant-rate stretches between pump events at the bag's concentration; the usable-level rule
(the guideline's 1-hour postdistributional window, judged from the documented stop); auc48 from the
first start; auc24_ss on the most recently ordered maintenance order; the broth microdilution MIC
rule (from the guideline); the exposure band and dose rounding.


---

<!-- reference/messages.md -->

# Messages to the person

Everything they paste goes in a code block. Plain words, no em dashes, short.

## Asking for a document

```
I need one PDF: "<exact title>" (<issuer>, <edition or year>).
Download it here: <link you confirmed by web search>
It should be about <N> pages, with <sections that prove it is the full document>.
If that link doesn't work, try <second confirmed link> and click "PDF".
```
If the file is over the upload limit: ask for chapter page ranges (Chrome or Edge: Ctrl+P, Save as
PDF, Pages: Custom; the browser's page counter, not the printed numbers), or use a document you
already have.

## Sending a zip

```
<task-name> is ready: <one-line description>.
What's in it: <cases, the main data mess, word count of the instruction, what is compared exactly>.
Checks I ran: <three models agree on every row; oracle N/N; empty output fails; M of M shortcuts caught>.
Upload: delete the old tasks/<old-name> folder on your PR branch (only one task folder is allowed),
then upload tasks/<task-name> from the zip. Keep the folder name <task-name>; it must match the name
line in task.toml.
```

## Upload steps (when they ask how)

```
1. Unzip the file. You get tasks/<task-name>/.
2. On GitHub, open your repository and switch to the PR's branch.
3. If an old task folder is there, open it, use the "..." menu, Delete directory, Commit changes.
4. Add file > Upload files > drag the tasks folder in > Commit changes to the same branch.
5. On the PR, the "Files changed" tab should show only tasks/<task-name>/.
```

## PR title and description

Title:
```
Add <task-name>: <job in plain words> (<standard short name>)
```
Description:
```
## Summary
<who, how many cases, what the agent produces, the standard with citation>

## What the agent receives
- <file>: <contents>

## Output
<path, header, one row per, comparison>

## Why it is hard
<the method that breaks down, the messy records, near-threshold planting, the exact decisions>

## Data
<synthetic, seeded generator, ranges from the standard>

## Verification
- <independent engine and its methods; private data; never runs agent code>
- <generator as third implementation; agreement level; uniqueness and margins>
- <golden checks against published examples>
- <tests: formats, order, families, every row; reward 1 only if all pass>

## Local checks (saved in authoring/evidence/)
- Oracle: N of N tests pass. Empty output: M fail.
- Agreement: <numbers>.
- Calibration: all K shortcuts fail, for example <three with their wrong-row counts>.
```

## Status after a log zip

```
Result: <stage> failed (<everything else that passed>). / All stages passed.
Log line: "<exact quote>"
What it means: <plain words>
What I changed: <files>
Rechecked: <numbers>
Cost: <this stopped before Pass@2, so no attempt was used / this used attempt N of 15>
Update your PR: <replace these files or the folder>
```

## Time questions

- The agent gets up to 8 hours per trial (task.toml `timeout_sec = 28800`, required by static
  checks). It stops when it finishes; earlier trials took 27 to 43 minutes.
- The person's own work time on Handshake is a different clock.


---

# Part 3: templates (copy exactly)

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

# Build context is tests/: test.sh, test_outputs.py, engine.py, golden.json, data/.
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
name = "insight/FOLDER-NAME"
description = "ONE LONG SENTENCE: the job, the records, the method and standard, the outputs."

[metadata]
domain = "Science"
field = "SUBCATEGORY EXACTLY AS ASSIGNED"
subfield = "SPECIFIC AREA"
tags = ["tag-one", "tag-two", "tag-three", "tag-four", "tag-five", "tag-six", "python"]
expert_time_estimate_hours = 10
relevant_experience = "ONE SENTENCE on the expertise the task needs."

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

## templates/test_outputs.py

```python
"""Verifier for TASK-NAME.

Every case is recomputed by an independent model (engine.py) from the verifier's private copy of the inputs.
The engine is itself checked against published worked examples (golden.json). No agent code is executed.
"""
import csv
import json
import math
import re
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import engine  # noqa: E402

OUT = Path("/app/output/OUTPUT_FILE.csv")
HEADER = "case_id,value_a,value_b,category,decision"          # exact header from instruction.md
REL = 0.005                                                    # tolerance for continuous columns
GOLDEN = json.loads((HERE / "golden.json").read_text())


def close(got, want):
    assert math.isfinite(got) and math.isfinite(want), (got, want)
    return abs(got - want) <= REL * abs(want)


def row_ok(g, w):
    # exact for letters, words and rounded integers; tolerance for continuous values
    return (g is not None and close(g[0], w["value_a"]) and close(g[1], w["value_b"])
            and g[2] == w["category"] and g[3] == w["decision"])


@pytest.fixture(scope="module")
def truth():
    return engine.expected()                                   # {case_id: {..., "tags": set()}} sorted


@pytest.fixture(scope="module")
def rows():
    assert OUT.is_file(), f"missing {OUT}"
    lines = OUT.read_text().splitlines()
    assert lines and lines[0] == HEADER, f"header must be exactly {HEADER}"
    assert all(line.strip() for line in lines[1:]), "blank lines are not allowed"
    out = []
    for r in csv.reader(lines[1:]):
        assert len(r) == HEADER.count(",") + 1, f"wrong column count: {r}"
        out.append(r)
    return out


@pytest.fixture(scope="module")
def got(rows):
    out = {r[0]: (float(r[1]), float(r[2]), r[3], r[4]) for r in rows}
    for cid, g in out.items():
        assert all(math.isfinite(x) for x in g[:2]), f"{cid}: non-finite value {g}"
    return out


def _bad(truth, got, pick):
    return [(cid, got.get(cid)) for cid, w in truth.items() if pick(w) and not row_ok(got.get(cid), w)]


def test_engine_matches_published_examples():
    """The engine reproduces the standard's worked examples."""
    for ex in GOLDEN["examples"]:
        v = getattr(engine, ex["check"])(*ex["args"]) if isinstance(ex["args"], list) else \
            getattr(engine, ex["check"])(**ex["args"])
        assert math.isfinite(v) and abs(v - ex["expect"]) <= ex["tol"], (ex["source"], v, ex["expect"])


def test_inputs_are_consistent():
    """Structural checks on the private inputs (ids, references, ordering)."""
    engine.load()


def test_values_are_well_formed(rows):
    """Known ids, numbers with the stated decimals, allowed words."""
    for r in rows:
        assert re.fullmatch(r"-?\d+\.\d{3}", r[1]) and re.fullmatch(r"-?\d+\.\d{3}", r[2]), r
        assert r[3] in ("below", "within", "above"), r


def test_rows_are_sorted_and_complete(truth, rows):
    """One row per case, sorted as the instruction says."""
    assert [r[0] for r in rows] == list(truth)


FAMILIES = ("family_one", "family_two", "near_thresholds")


@pytest.mark.parametrize("family", FAMILIES)
def test_rule_family(truth, got, family):
    """Every case in this method family is right."""
    assert any(family in w["tags"] for w in truth.values())
    bad = _bad(truth, got, lambda w: family in w["tags"])
    assert not bad, f"{len(bad)} wrong, e.g. {bad[:4]}"


def test_every_row(truth, got):
    """Every case is right."""
    bad = _bad(truth, got, lambda w: True)
    assert not bad, f"{len(bad)} of {len(truth)} wrong, e.g. {bad[:4]}"
```

## templates/calibrate.py

```python
#!/usr/bin/env python3
"""Run shortcut versions of the reference solution against the tests.

Usage: python3 calibrate.py      (from authoring/)

Each shortcut is a plausible misreading made by editing solution/solve.py text. A shortcut is caught when at
least one test fails; the number of wrong rows shows how widely it shows up.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TASK = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(TASK / "tests"))
from local_check import run_solution, run_tests  # noqa: E402
import engine  # noqa: E402

# name -> list of (exact text in solve.py, replacement)
SHORTCUTS = {
    "the textbook shortcut": [("OLD TEXT", "NEW TEXT")],
    "constant from memory instead of the printed one": [("KU = 1.486", "KU = 1.49")],
}


def count_wrong(out_dir):
    """Compare the shortcut's output file with engine.expected(); return (wrong, total)."""
    raise NotImplementedError


def main():
    src = (TASK / "solution" / "solve.py").read_text()
    caught = 0
    for name, edits in SHORTCUTS.items():
        # a shortcut keeps going where the reference would raise; replace raises with a fallback here
        s = src
        for a, b in edits:
            assert s.count(a) >= 1, (name, a)
            s = s.replace(a, b)
        try:
            out = run_solution(TASK, source=s)
        except Exception as e:                      # noqa: BLE001
            print(f"CRASHED ({type(e).__name__}: {str(e)[:80]})  {name}")
            caught += 1
            continue
        passed, failed = run_tests(TASK, out)
        wrong, total = count_wrong(out)
        caught += bool(failed)
        print(f"{'CAUGHT' if failed else 'MISSED'}  {wrong:4d} of {total} rows wrong  {name}")
    print(f"{caught} of {len(SHORTCUTS)} shortcuts caught")
    sys.exit(0 if caught == len(SHORTCUTS) else 1)


if __name__ == "__main__":
    main()
```


---

# Part 4: worked example (vancomycin-auc-dosing, key files)

## examples/vancomycin-auc-dosing/instruction.md

````markdown
The infectious diseases pharmacy service is reviewing vancomycin therapy for 240 adults treated for serious MRSA infections. Following the 2020 consensus guideline of ASHP, IDSA, PIDS and SIDP (Rybak et al., Am J Health-Syst Pharm 2020;77:835-864), estimate each patient's exposure from their own measured levels and recommend a dose.

The data is in /app/data/. patients.json gives each patient's details and the vancomycin MIC of their MRSA isolate with the testing method, or null when none was reported. administrations.csv is the administration and infusion pump record: each administration starts with its dose, bag volume and pump rate, may pause, resume and change rate, and stops; the cumulative volume infused is recorded at every pause, rate change and stop, and not_given marks a dose that was held. levels.csv holds the vancomycin results as the laboratory reported them, and orders.csv the vancomycin orders (once for a loading dose, otherwise a maintenance dose every so many hours). Times are local, to the minute.

The service's practice settles these points:
- Each patient follows a one-compartment model with first-order elimination and no vancomycin before their first documented administration. Each stretch of an infusion between pump events delivers the drug in the volume infused during it, at the bag's concentration, at a constant rate. A patient's elimination rate constant and volume of distribution are the values for which this model, given every documented infusion, passes through both usable levels.
- A level is usable when it is a reported value (not a rejected or cancelled specimen and not below the reporting limit) and was drawn neither while an administration was running, from its start to its stop with any pauses, nor less than 1 hour after the stop of one. Every patient has exactly two usable levels.
- auc48 is the model's AUC from the start of the first administration to 48 hours later.
- auc24_ss is the steady-state 24-hour AUC on the current order, the most recently ordered maintenance order: its daily dose divided by the patient's clearance.
- The target is the guideline's AUC/MIC of 400 to 600. The isolate's MIC counts only when measured by broth microdilution; otherwise the MIC is 1 mg/L.
- Exposure is within when auc24_ss divided by the MIC is from 400 to 600, and below or above otherwise. The new dose is the current dose when exposure is within; otherwise it is the dose at the current interval that gives an AUC/MIC of 500, rounded to the nearest 250 mg.

Write /app/output/vancomycin_review.csv with the header patient_id,ke_per_h,volume_l,auc48,auc24_ss,exposure,new_dose_mg and one row per patient, sorted by patient_id. ke_per_h is the elimination rate constant per hour with five decimals, volume_l the volume of distribution in liters with two decimals, auc48 and auc24_ss are in mg·h/L with one decimal, exposure is below, within or above, and new_dose_mg is a whole number of milligrams. Numbers are accepted within 0.5 percent; exposure and new_dose_mg must match exactly. Do not add extra columns, blank lines or explanations.

You have 28800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.
````

## examples/vancomycin-auc-dosing/task.toml

````toml
artifacts = ["/app/output/"]

schema_version = "2.0"

[task]
name = "insight/vancomycin-auc-dosing"
description = "AUC-guided vancomycin dosing for 240 adults with serious MRSA infections under the 2020 ASHP/IDSA/PIDS/SIDP consensus guideline: from irregular administration and infusion pump records (late, held, paused, interrupted and partly given doses, rate changes, loading doses, order changes) and laboratory results (rejected, below the reporting limit, mistimed), fit each patient's one-compartment elimination rate and volume to the two usable levels by superposition, and report the 48-hour AUC, the steady-state AUC24, exposure against the AUC/MIC target with the broth microdilution MIC rule, and the new dose."

[metadata]
domain = "Science"
field = "Medicine"
subfield = "Clinical Pharmacology and Therapeutic Drug Monitoring"
tags = ["pharmacokinetics", "therapeutic-drug-monitoring", "vancomycin", "auc-guided-dosing", "one-compartment-model", "mrsa", "clinical-pharmacy", "python"]
expert_time_estimate_hours = 10
relevant_experience = "Clinical pharmacokinetics and therapeutic drug monitoring: vancomycin AUC-guided dosing under the 2020 consensus guideline, one-compartment intermittent infusion models with superposition, fitting patient-specific parameters to measured drug levels, and reading hospital medication administration and laboratory records."

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
````

## examples/vancomycin-auc-dosing/README.md

````markdown
# vancomycin-auc-dosing

AUC-guided vancomycin dosing for 240 adults treated for serious MRSA infections, following the 2020 consensus
guideline of ASHP, IDSA, PIDS and SIDP (Rybak et al., Am J Health-Syst Pharm 2020;77:835-864). For every patient
the agent reports the elimination rate constant and volume of distribution fitted to the patient's two usable
levels, the AUC over the first 48 hours, the steady-state AUC24 on the current order, exposure against the AUC/MIC
target of 400 to 600, and the new dose.

## Difficulty

Clinical pharmacists adjust vancomycin doses from measured levels every day, and since 2020 the guideline
recommends AUC-guided dosing for serious MRSA infections. Its first-order equation method (peak and trough near
steady state, in one dosing interval) is what pharmacists and AI agents reach for, and the guideline itself warns
that it is hard to use when doses are irregular. Hospital records rarely meet its assumptions: here levels are
drawn on the first day, around a dose, or two intervals apart; doses are late, early or held; infusions are
paused, slowed, sped up or stopped partway, so the drug actually given must be read from the pump's cumulative
volumes; loading doses differ from maintenance doses, and orders change. The patient's parameters therefore have
to come from superposition of every documented infusion in a one-compartment model, with the elimination rate
solved from the ratio of the two levels. Choosing the two usable levels means discarding rejected and cancelled
specimens and results below the reporting limit, and levels drawn while an infusion was running (pauses included)
or less than an hour after it actually stopped (the guideline's postdistributional sampling window), judged
against the documented stop, not the scheduled one. The MIC changes the target only when measured by broth
microdilution, as the guideline advises. The data holds 240 patients, 215 with irregular records, 130 with
mistimed levels and 41 with first-day levels. 44 patients have AUC24/MIC within 0.6 percent of 400 or 600 (40 of
them planted by the generator), 50 have an unrounded new dose within 5 mg of a 250 mg rounding midpoint (37
planted), and 119 have a level drawn within 6 minutes of one hour after an infusion stopped (counts in
authoring/evidence/agreement.txt and generate_output.txt). Each of 20 shortcuts tried (the steady-state equations, ignoring pauses,
partial volumes or held doses, nominal infusion times, keeping mistimed levels, any-method MICs, other rounding,
trapezoid or doubled AUCs) gets many patients right and others wrong. The patients are synthetic but follow the
guideline's dosing ranges, infusion limits (at most 5 mg/mL and at least 1 hour per 1,000 mg) and published adult
vancomycin clearance and volume ranges.

## Solution

The reference solution (solution/solve.py) turns each administration's pump events into constant-rate segments
from the cumulative volumes, selects the two usable levels, writes each level as the sum of closed-form infusion
terms divided by the volume, solves the ratio of the two levels for the elimination rate by bisection after a
scan for the bracket, takes the volume from either level, integrates the closed-form segment terms over the first
48 hours, and applies the guideline target, the MIC rule and the dose rounding.

## Verification

The verifier recomputes every patient with its own independently written engine (tests/engine.py, which writes
each segment's contribution in a different form, solves the elimination rate by the Illinois regula falsi
method and integrates the 48-hour AUC numerically with 24-point Gauss-Legendre quadrature between event times)
from a private copy of the inputs that exists only in the verifier image, and never runs agent code. The data
generator (authoring/sim.py, which propagates the amount in the body from event to event and uses a mass balance
for the AUC) is a third implementation; the engine and generator agree within a relative 2e-13, every patient has
exactly one solution for the elimination rate between 1e-6 and 100 per hour, and AUC24/MIC stays at least 0.05
percent from 400 and 600 and the unrounded dose at least 0.5 mg from a rounding midpoint. The engine is checked
against closed-form one-compartment results: a single infusion, the steady-state peak, the Sawchuk-Zaske
elimination rate from a steady-state peak and trough, and the steady-state AUC over an interval. Tests check that
the inputs are consistent, the value formats, one row per patient in order, one test per method family (first-day
levels, doses between the levels, irregular records, mistimed levels, levels near one hour after an infusion,
rejected or unreportable results, broth microdilution and other-method MICs, changed orders, patients near the
target edges and near rounding steps, and each exposure category) and finally every patient, with numbers within
0.5 percent and exposure and new dose exact. Reward is 1 only if every test passes.
````

## examples/vancomycin-auc-dosing/authoring/README.md

````markdown
# Authoring tools for vancomycin-auc-dosing

These files are not copied into the agent or verifier images. Run them from this folder.

## Provenance
- `generate.py` (seed 20200601) builds the 240 patients and writes both data copies (`../environment/data`,
  `../tests/data`). True clearance comes from Cockcroft-Gault creatinine clearance (0.05 L/h per mL/min, times
  0.8 to 1.25) and true volume is about 0.7 L/kg (times 0.75 to 1.3). Regimens follow the guideline: maintenance
  doses sized for a spread of exposures every 8, 12 or 24 hours, loading doses of 20 to 35 mg/kg actual weight up
  to 3,000 mg (184 of the 240 patients have a loading dose order; 49 have an order change), bags of at most 5 mg/mL, and at least 1 hour per 1,000 mg. Records
  include late and early starts, held doses, pauses, rate changes, partly given infusions and order changes.
  Two usable levels follow one of four patterns (steady-state peak and trough in one interval, trough then peak
  around one dose, first-day levels, peak and trough two intervals apart), with assay noise of up to 8 percent,
  to 0.1 mg/L; unusable results are rejected specimens, results below the reporting limit, and levels drawn
  during an infusion or less than an hour after one. Answers are fitted from the written records, and planted
  patients have one level moved in 0.1 mg/L steps to sit near a target edge or a rounding step.
- `sim.py` is the generator's own model (third implementation).
- `sources/rybak_2020_vancomycin_guideline.txt` is the text of the guideline extracted from the PDF. The rules
  used come from pages 839 to 840 (AUC/MIC 400 to 600 assuming a broth microdilution MIC of 1 mg/L unless measured
  otherwise; first-order equations need near steady-state levels and are hard to use with irregular dosing),
  page 844 (infusion at most 5 mg/mL and at least 1 hour per 1,000 mg; loading doses 20 to 35 mg/kg up to 3,000
  mg) and page 845 (peak drawn at least 1 hour after the end of the infusion).

## Evidence (outputs saved in `evidence/`)
- `check_agreement.py` -> `evidence/agreement.txt`: solution, engine and generator agree on all 240 patients; it
  also prints the per-family patient counts, the closest values to the target edges and rounding midpoints, and
  the check that every patient has exactly one elimination-rate solution. Every count quoted in the READMEs comes
  from this file or from `evidence/generate_output.txt`.
- `local_check.py ..` -> `evidence/local_check.txt`: oracle passes every test, empty output fails.
- `calibrate.py` -> `evidence/calibration.txt`: 20 shortcut solutions and how many patients each gets wrong.
- `generate.py` -> `evidence/generate_output.txt`: counts of patterns, exposures, irregularities and planted values.

## Settled readings (stated in instruction.md)
One-compartment model, first-order elimination, no drug before the first documented administration; each stretch
between pump events delivers the volume infused in it at the bag's concentration at a constant rate; parameters
are those that pass through both usable levels given every documented infusion; usable levels are reported values
not drawn during an administration (pauses included) or less than 1 hour after its stop; auc48 from the first
administration's start; auc24_ss as the current (most recently ordered) maintenance order's daily dose over
clearance; MIC only by broth microdilution, else 1 mg/L; within means 400 to 600 inclusive; new dose at the current
interval for AUC/MIC 500, to the nearest 250 mg, unchanged when within.
````

## examples/vancomycin-auc-dosing/solution/solve.py

````python
#!/usr/bin/env python3
"""Reference solution for vancomycin-auc-dosing.

AUC-guided vancomycin dosing (2020 ASHP/IDSA/PIDS/SIDP consensus guideline) from each patient's documented
administrations and two usable levels: a one-compartment model with constant-rate infusion segments and
first-order elimination, fitted by superposition of every documented infusion segment.
"""
import csv
import datetime as dt
import json
import math
import re
from pathlib import Path

DATA = Path("/app/data")
OUT = Path("/app/output")


def minutes(text):
    return (dt.datetime.strptime(text.strip(), "%Y-%m-%d %H:%M") - dt.datetime(2000, 1, 1)).total_seconds() / 60.0


def read_csv(name):
    with open(DATA / name, newline="") as fh:
        return list(csv.DictReader(fh))


def segment_amount(seg, t, ke):
    """Drug amount (mg) in the body at time t from one constant-rate segment (s, e, mg)."""
    s, e, mg = seg
    if t <= s:
        return 0.0
    rate = mg / (e - s)
    if t <= e:
        return rate / ke * (1.0 - math.exp(-ke * (t - s)))
    return rate / ke * (1.0 - math.exp(-ke * (e - s))) * math.exp(-ke * (t - e))


def segment_area(seg, T, ke):
    """Integral of segment_amount from 0 to T."""
    s, e, mg = seg
    if T <= s:
        return 0.0
    rate = mg / (e - s)
    t1 = min(T, e)
    area = rate / ke * ((t1 - s) - (1.0 - math.exp(-ke * (t1 - s))) / ke)
    if T > e:
        area += segment_amount(seg, e, ke) * (1.0 - math.exp(-ke * (T - e))) / ke
    return area


def total(segs, t, ke):
    return sum(segment_amount(sg, t, ke) for sg in segs)


def fit(segs, t1, c1, t2, c2):
    target = math.log(c1 / c2)

    def g(k):
        return math.log(total(segs, t1, k) / total(segs, t2, k)) - target

    grid = [1e-4 * (3e4) ** (i / 300) for i in range(301)]
    vals = [g(k) for k in grid]
    roots = [i for i in range(300) if (vals[i] > 0) != (vals[i + 1] > 0)]
    if len(roots) != 1:
        raise ValueError(f"{len(roots)} solutions for the elimination rate")
    lo, hi = grid[roots[0]], grid[roots[0] + 1]
    glo = g(lo)
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        gm = g(mid)
        if (gm > 0) == (glo > 0):
            lo, glo = mid, gm
        else:
            hi = mid
    ke = 0.5 * (lo + hi)
    return ke, total(segs, t1, ke) / c1


def main():
    patients = json.loads((DATA / "patients.json").read_text())
    admins = {}
    for r in read_csv("administrations.csv"):
        admins.setdefault(r["patient_id"], {}).setdefault(r["administration_id"], []).append(r)
    levels, orders = {}, {}
    for r in read_csv("levels.csv"):
        levels.setdefault(r["patient_id"], []).append(r)
    for r in read_csv("orders.csv"):
        orders.setdefault(r["patient_id"], []).append(r)

    out = []
    for p in patients:
        pid = p["patient_id"]
        segs, spans = [], []
        for aid, rows in admins.get(pid, {}).items():
            rows.sort(key=lambda r: minutes(r["time"]))
            start = [r for r in rows if r["event"] == "start"]
            if not start:
                continue                                       # not given
            conc = float(start[0]["dose_mg"]) / float(start[0]["bag_volume_ml"])
            open_t, done_v = None, 0.0
            for r in rows:
                t = minutes(r["time"]) / 60.0
                ev = r["event"]
                if ev in ("start", "resume"):
                    open_t = t
                elif ev in ("pause", "rate_change", "stop"):
                    vol = float(r["volume_infused_ml"])
                    if open_t is not None and vol > done_v and t > open_t:
                        segs.append((open_t, t, (vol - done_v) * conc))
                    done_v = vol
                    open_t = t if ev == "rate_change" else None
            spans.append((minutes(rows[0]["time"]), minutes(rows[-1]["time"])))
        t0 = min(s for s, _, _ in segs)
        segs = [(s - t0, e - t0, mg) for s, e, mg in segs]

        good = []
        for r in levels.get(pid, []):
            m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(?:[HL])?\s*", r["result"])
            if not m:
                continue                                       # rejected or below the reporting limit
            t = minutes(r["collected"])
            if any(s <= t <= e or e < t < e + 60 for s, e in spans):
                continue                                       # during an infusion or less than 1 h after one
            good.append((t / 60.0 - t0, float(m.group(1))))
        good.sort()
        (ta, ca), (tb, cb) = good
        ke, vol = fit(segs, ta, ca, tb, cb)
        cl = ke * vol

        cur = max((o for o in orders[pid] if o["frequency"] != "once"), key=lambda o: minutes(o["ordered"]))
        dose = float(cur["dose_mg"])
        tau = float(re.search(r"\d+", cur["frequency"]).group())
        auc24 = dose * 24.0 / tau / cl
        auc48 = sum(segment_area(sg, 48.0, ke) for sg in segs) / vol
        mic_rec = p.get("isolate_mic")
        mic = float(mic_rec["value_mg_l"]) if mic_rec and mic_rec["method"] == "broth microdilution" else 1.0
        ratio = auc24 / mic
        if 400.0 <= ratio <= 600.0:
            exposure, new = "within", int(dose)
        else:
            exposure = "below" if ratio < 400.0 else "above"
            raw = 500.0 * mic * cl * tau / 24.0
            new = int(math.floor(raw / 250.0 + 0.5) * 250)
        out.append([pid, f"{ke:.5f}", f"{vol:.2f}", f"{auc48:.1f}", f"{auc24:.1f}", exposure, new])

    out.sort(key=lambda r: r[0])
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "vancomycin_review.csv", "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["patient_id", "ke_per_h", "volume_l", "auc48", "auc24_ss", "exposure", "new_dose_mg"])
        w.writerows(out)


if __name__ == "__main__":
    main()
````

## examples/vancomycin-auc-dosing/tests/test_outputs.py

````python
"""Verifier for vancomycin-auc-dosing.

Every patient is recomputed by an independent model (engine.py) from the verifier's private copy of the inputs.
The engine is itself checked against textbook one-compartment results (golden.json). No agent code is executed.
"""
import csv
import json
import math
import re
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import engine  # noqa: E402

OUT = Path("/app/output/vancomycin_review.csv")
HEADER = "patient_id,ke_per_h,volume_l,auc48,auc24_ss,exposure,new_dose_mg"
REL = 0.005
GOLDEN = json.loads((HERE / "golden.json").read_text())


def close(got, want):
    assert math.isfinite(got) and math.isfinite(want), (got, want)
    return abs(got - want) <= REL * abs(want)


def row_ok(g, w):
    return (g is not None and close(g[0], w["ke"]) and close(g[1], w["volume"]) and close(g[2], w["auc48"])
            and close(g[3], w["auc24"]) and g[4] == w["exposure"] and g[5] == w["new_dose"])


@pytest.fixture(scope="module")
def truth():
    return engine.expected()


@pytest.fixture(scope="module")
def rows():
    assert OUT.is_file(), "missing /app/output/vancomycin_review.csv"
    lines = OUT.read_text().splitlines()
    assert lines and lines[0] == HEADER, f"header must be exactly {HEADER}"
    assert all(line.strip() for line in lines[1:]), "blank lines are not allowed"
    out = []
    for r in csv.reader(lines[1:]):
        assert len(r) == 7, f"row must have 7 columns: {r}"
        out.append(r)
    return out


@pytest.fixture(scope="module")
def got(rows):
    out = {r[0]: (float(r[1]), float(r[2]), float(r[3]), float(r[4]), r[5], int(r[6])) for r in rows}
    for pid, g in out.items():
        assert all(math.isfinite(x) for x in g[:4]), f"{pid}: non-finite value {g}"
    return out


def _bad(truth, got, pick):
    bad = []
    for pid, w in truth.items():
        if pick(w) and not row_ok(got.get(pid), w):
            bad.append((pid, got.get(pid), (round(w["ke"], 5), round(w["volume"], 2), round(w["auc48"], 1),
                                            round(w["auc24"], 1), w["exposure"], w["new_dose"])))
    return bad


def test_engine_matches_textbook_results():
    """The engine reproduces closed-form one-compartment infusion results and the Sawchuk-Zaske elimination rate."""
    for ex in GOLDEN["examples"]:
        v = getattr(engine, ex["check"])(*ex["args"])
        assert math.isfinite(v) and abs(v - ex["expect"]) <= ex["tol"], (ex["source"], v, ex["expect"])


def test_inputs_are_consistent():
    """Every patient has orders and administrations, every administration starts or is marked not given."""
    pats, adm, lev, ords = engine.load()
    ids = {p["patient_id"] for p in pats}
    assert {r["patient_id"] for r in adm} == ids and {r["patient_id"] for r in ords} == ids
    assert {r["patient_id"] for r in lev} <= ids
    first = {}
    for r in adm:
        first.setdefault(r["administration_id"], r["event"])
    assert set(first.values()) <= {"start", "not_given"}


def test_values_are_well_formed(rows):
    """Known patients, numbers with the stated decimals, exposure words and whole-milligram doses."""
    ids = {p["patient_id"] for p in engine.load()[0]}
    for r in rows:
        assert r[0] in ids, r
        assert re.fullmatch(r"\d+\.\d{5}", r[1]) and re.fullmatch(r"\d+\.\d{2}", r[2]), r
        assert re.fullmatch(r"\d+\.\d", r[3]) and re.fullmatch(r"\d+\.\d", r[4]), r
        assert r[5] in ("below", "within", "above") and re.fullmatch(r"\d+", r[6]), r


def test_rows_are_sorted_and_complete(truth, rows):
    """One row per patient, sorted by patient_id."""
    assert [r[0] for r in rows] == list(truth)


FAMILIES = (
    "first_day_levels", "dose_given_between_levels", "irregular_administration_records", "mistimed_levels",
    "levels_near_one_hour_after_infusion", "rejected_or_unreportable_results", "broth_microdilution_mic",
    "mic_by_other_methods", "changed_orders", "near_target_edges", "near_rounding_steps", "exposure_below",
    "exposure_within", "exposure_above",
)


@pytest.mark.parametrize("family", FAMILIES)
def test_rule_family(truth, got, family):
    """Every patient in this family is right."""
    assert any(family in w["tags"] for w in truth.values())
    bad = _bad(truth, got, lambda w: family in w["tags"])
    assert not bad, f"{len(bad)} wrong, e.g. {bad[:4]}"


def test_every_patient(truth, got):
    """Every patient: ke, volume and AUCs within 0.5 percent, exposure and new dose exact."""
    bad = _bad(truth, got, lambda w: True)
    assert not bad, f"{len(bad)} of {len(truth)} wrong, e.g. {bad[:4]}"
````

## examples/vancomycin-auc-dosing/authoring/evidence/agreement.txt

````text
patients per method family (engine tags):
  broth_microdilution_mic: 45
  changed_orders: 49
  dose_given_between_levels: 108
  exposure_above: 111
  exposure_below: 66
  exposure_within: 63
  first_day_levels: 41
  irregular_administration_records: 215
  levels_near_one_hour_after_infusion: 119
  mic_by_other_methods: 54
  mistimed_levels: 130
  near_rounding_steps: 50
  near_target_edges: 44
  rejected_or_unreportable_results: 90
patients with a loading dose order: 184
patients with an order change: 49
closest unrounded new dose to a rounding midpoint: 0.60 mg
patients without exactly one elimination-rate solution between 1e-6 and 100 per hour: 0
patients: engine 240, generator 240, solution 240
generator vs engine: 0 exposure or dose differences, largest relative difference 1.8e-13
solution vs engine:  0 exposure or dose differences, largest relative difference 2.6e-04 (solution rounds to its printed decimals)
closest AUC24/MIC to 400 or 600: 0.055 percent
AGREEMENT: OK
````

## examples/vancomycin-auc-dosing/authoring/evidence/calibration.txt

````text
CAUGHT   108 of 240 patients wrong  two-level steady-state equation for ke (ln of the level ratio over the time between them)
CAUGHT   211 of 240 patients wrong  steady-state equations for ke and V (Sawchuk-Zaske, last dose only)
CAUGHT    60 of 240 patients wrong  full ordered dose for every infusion (volumes infused ignored)
CAUGHT    95 of 240 patients wrong  pauses ignored (one segment from start to stop)
CAUGHT   126 of 240 patients wrong  infusion assumed to last the nominal hour per 1,000 mg
CAUGHT    39 of 240 patients wrong  held doses counted as given
CAUGHT    18 of 240 patients wrong  levels within 1 hour after an infusion kept (last two numeric levels used)
CAUGHT    18 of 240 patients wrong  1-hour rule counted from the start of the infusion
CRASHED (ValueError: not enough values to unpack (expected 2, got 1))  flagged results (H) treated as unusable
CAUGHT    50 of 240 patients wrong  MIC from any testing method
CAUGHT    45 of 240 patients wrong  MIC always assumed 1 mg/L
CAUGHT    44 of 240 patients wrong  first maintenance order instead of the current one
CAUGHT    93 of 240 patients wrong  new dose rounded down to 250 mg
CAUGHT    84 of 240 patients wrong  new dose rounded up to 250 mg
CAUGHT    29 of 240 patients wrong  new dose also when exposure is within range
CAUGHT    40 of 240 patients wrong  new dose aimed at AUC 500 regardless of MIC
CAUGHT   237 of 240 patients wrong  48-hour AUC taken as twice the steady-state AUC24
CAUGHT    20 of 240 patients wrong  48-hour AUC by the linear trapezoid rule on hourly concentrations
CAUGHT   172 of 240 patients wrong  48-hour AUC from the first maintenance dose
CAUGHT    86 of 240 patients wrong  amounts from pump rate times running time
20 of 20 shortcuts caught
````
