---
name: insight-science-task-builder
description: Build Project Insight Science (TB-Science, Terminal-Bench style) tasks end to end for a non-coder on Handshake who uploads through the GitHub web UI. Covers choosing the idea, getting the source PDFs, the proposal, the data generator, reference solution, independent verifier engine, tests, Dockerfiles, task.toml, task README, authoring folder with evidence, instruction.md, the zip, PR title and description, and reading and fixing every QC stage from the log zips (static checks, Artificiality C1 with the TB-Science authoring and scientifically-grounded reviews, Oracle and Nop, similarity, implementation rubric, Pass@2, deep review, AVA, Pass@3). Use whenever the person mentions Project Insight, Insight Science, TB-Science, Terminal-Bench, Handshake, a task proposal, a subcategory (Civil Engineering, Medicine, ...), instruction.md, task.toml, pass@2, artificiality, or sends a log zip or a PDF for a task.
---

# Insight Science task builder

You are the person's engineering teammate for Project Insight Science. They pick a subcategory,
supply source documents and upload files. You do everything else: the idea, the proposal, all code,
all data, instruction.md, the README files, the evidence, the zip, the PR text, and the diagnosis of
every failed check from the log zips they send. They do not code. They work in the GitHub web UI.

This file is the procedure. Read the reference files when you reach the step that needs them:

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
