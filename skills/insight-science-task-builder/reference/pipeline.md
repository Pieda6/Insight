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
8. **Deep review and later:** the log only says `Deep review did not PASS (fail-closed)`. The verdict is the PR
   comment "🤖 Automated Review": ask the person to paste the whole comment. It has the verdict, Blocking Issues
   each ending in a Fix, Unresolved Checks, a gate ledger, and a trajectory analysis saying exactly where both agents
   failed. Read the trajectory analysis first: if the agents got the whole crux right, fixing the blocker will make
   the task solvable, so redesign instead of uploading the fix.

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
| deep_review | `Verdict: FAIL — the decisive MIC-selection rule ... is not uniquely derivable from agent-visible material; both pass@2 trials independently adopted the "assume 1 mg/L" reading and failed only on it` (gates U1, U2, U3, T6.3, T10.3-CAT, T-ATTRIB, G-DIFF) | A decisive rule was only cited, and my version contradicted the guideline's Recommendation 6 | State every decisive rule in instruction.md, faithful to the source; never let failures hinge on a convention |
| deep_review (unresolved) | `tolerances_justified (exposure boundary × 0.5% tolerance)`, `near_rounding_steps` | Category boundaries planted 0.05 percent away while numbers were accepted within 0.5 percent | Keep boundary and rounding margins larger than the numeric tolerance |
| (person) | Links "don't exist" | URLs given from memory | Search first; give verified links |
| (person) | A 1-page placeholder PDF | The repository page had no file | Tell them the expected page count and sections; check on arrival |

## After every diagnosis, tell the person

1. Which stage failed, with the quoted line.
2. What it means in one or two plain sentences.
3. What you changed (files) and what you rechecked (numbers).
4. Whether this run used a Pass@2 attempt, and how to update the PR (which files or the folder).
