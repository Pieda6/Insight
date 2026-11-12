# The full record: every task, every run, every fix (Nov 2026)

Read this before designing anything. It is the experience behind every rule in this skill. Each entry says what was
built, what each QC run said, what was changed, and what it taught.

## The people and the repos

- The person is a Handshake contributor who does not code. They upload zips and edit files in the GitHub web UI,
  paste PR comments, and upload the GitHub Actions log zips (`logs_<runid>.zip`) and, when asked, the Pass@2
  artifacts (`pass2-output.zip`, `pass2-summary.zip`) and the AVA artifact (`ava-review-evidence.zip`).
- Repos seen (one PR each, PR #1, one task folder at a time):
  - `handshake-project-insight/science-civil-engineering-0a3a71a5-d1d644572183` (user MysoreKishor): storm-drain-energy.
  - `handshake-project-insight/science-medicine-0a3a71a5-0d214dd18ea4` (user Wallevic): vancomycin, prostate,
    kdigo, tg71.
  - `handshake-project-insight/science-london-medicine-0a3a71a5-c44ac3fd7018`: tg51. This repo runs the extra
    **Kyoto** checks and expects `field = "London Medicine"` (see `kyoto.md`).
  - Hertz (a different project, see `hertz.md`): `Handshake-project-hertz/hertz-HTZ-T10015`, fork
    `Priyasahu81179/hertz-HTZ-T10015`.
- All task work is also kept in this repository (`pieda6/insight`) under `tasks/<name>/`, branch
  `claude/friendly-bell-2xtcee`; zips are built in the scratchpad and sent with SendUserFile.
- The Pass@2 agent: `mini-swe-agent` with `openai/vertex_ai/gemini-4-argon` (Gemini). 15 counted Pass@2 attempts
  per PR. The medicine PR had used 10 of 15 before KDIGO and about 11 after the first TG-71 run.

## Chronology

### TB3 legal tasks (before this skill) 
hos-log-audit passed Pass@2 and deep review (lean instruction citing 49 CFR 395, long raw logs, minute-exact clocks).
bridge, part117, sms, auto-ad, feca passed difficulty. hazmat-trailer-check was solved 2/2 three times (lookups are
easy). The FECA task's instruction style ("name the governing standard, describe the data, state only facts") is the
style the person wants everywhere: no clues, no hints, no method.

### Civil: stormwater-inspection-audit
Failed the scientifically-grounded review: a rule engine over permit deadlines is not science.

### Civil: sediment-basin-routing
Solved 2/2 twice (27 and 43 min). The 850-word instruction listed every convention and trap; tolerances 0.5 percent.

### Civil: storm-drain-energy (HEC-22 4th ed. 2024, Sec. 9.4, FHWA access-hole energy-loss method)
Cleared the gates the person reported as "cleared all checks"; one later run crashed in the ambiguity audit (infra,
reported to support, no task change). Why it worked: categorical outputs (case letters, conditions) compared exactly,
431 comparisons planted within 0.03 ft of a dividing line, errors propagate upstream through a network, two similar
tests at different steps, floors, caps and table interpolation, a recent standard the model only half remembers, and
no standard text shipped (the instruction names HEC-22). It is the reference design (examples/storm-drain-energy).

### Medicine: vancomycin-auc-dosing (Rybak 2020 consensus guideline)
v1 solved 2/2 (56 min); v2 Pass@2 0/2 but deep review FAIL on an unstated MIC rule that also contradicted the
guideline's Rec. 6; v3 (rule fixed) solved 2/2 (16 min); v4 solved 2/2; v5 (hemodialysis subpopulation) solved 2/2
(34 min) and an outside review found grounding flaws. Retired.

### Medicine: vancomycin-hemodialysis-monitoring
Artificiality A3 (invented specification) and A6 (authored combination) failures, then the science review FAILED
("no small edit suffices"). Abandoned. Lesson: invented policy prose fails A3/A6 no matter how it is phrased.

### Medicine: prostate-seed-dosimetry (AAPM TG-43U1, Rivard 2004)
60 patients, 2,939 seeds, 1,200 points, eight seed models, vendor certificates. Runs:
- Decisive rule (nearest-neighbour extrapolation, Appendix C) left in the cited report only: Pass@2 passed, deep
  review FAIL (U1-U3, G-DIFF: "the rule is not uniquely pinned by agent-visible text").
- Rule stated in the instruction: solved 2/2.
- Report text shipped as `/app/data/tg43u1.txt` with the rule unstated: solved 2/2 (the model read Appendix C).
- A Pass@2 log once failed on a credential scrub of trial artifacts (infra).
Lesson: one buried rule is not difficulty; the deep review calls failures on it an artifact, and once visible the model
finds it.

### Medicine: kdigo-aki-staging (KDIGO 2012 AKI guideline)
120 ICU admissions, creatinine in mg/dL and umol/L with corrections and rejected specimens, irregular urine charting,
renal replacement therapy, New York local times across DST. Static T8 failed once (NaN detector) and was fixed with
`math.isfinite` guards in engine.py. Every check before Pass@2 passed, science included. Pass@2 solved 2/2.
The trajectories (pass2-output.zip) showed the model spending half its steps hunting borderline values and testing
every alternative reading (naive time vs DST, 26.5 vs 26.52, thresholds within 0.005), then writing the solution
around step 57. Planted edges with one correct reading never trap it.

### Medicine: tg71-mu-check (AAPM TG-71, Gibbons 2014): the closest to a full pass
Monitor units for 6 MV photon and 9 MeV electron beams from the report's own Tables II-IX; engine reproduces all six
Sec. 8 worked examples (266, 156, 135, 200, 252, 250 MU). Runs, in order:
1. Folder `tg71-monitor-unit-check`: static FAIL, slug has 4 tokens (max 3). Renamed `tg71-mu-check`.
2. Added TB-4 fields (difficulty_explanation, solution_explanation, verification_explanation, category,
   subcategory) because an old local copy of check-task-fields.sh asked for them: live static FAIL "difficulty_explanation
   is a TB-4 field; move its text to the task README.md and remove it from task.toml". Removed. The live check wants
   exactly: domain, field, subfield, tags, expert_time_estimate_hours, relevant_experience. Never trust the local copy
   of check-task-fields.sh or check-subcategory.py over a passing live run.
3. Full TG-71 text shipped as `/app/data/tg71.txt`, 91 beams: Pass@2 solved 2/2 in about 28 min. Both trials matched
   the engine to 0.0001 percent on every beam. The trajectory (44 steps): list data, read every table, spend ~15 steps
   reading tg71.txt section by section including the worked examples, test Eq. 1 vs Eq. 3, the Mayneord bracket, WF
   field size, OAR projection, power-law distances and both SSDeff geometric means against the data, bounds-check every
   lookup, write one script, submit.
4. Removed tg71.txt (instruction names TG-71 with its citation, like the civil task names HEC-22), shifted beams toward
   electrons at extended distance and the power-law lung correction (83 beams). Result: **Pass@2 passed** (at least one
   trial failed), **deep review PASS, ambiguity review PASS**, then **AVA BLOCK** (B2 accepted_task_violation): the
   instruction said "do not round to whole monitor units" but the 0.3 percent tolerance accepts a rounded 298 MU.
5. AVA fix: the output sentence became only "Each value is accepted within 0.3 percent of the correct value"; added
   tests that the allowed-value band never exceeds the tolerance and that every case tag really moves its beam outside
   it (answers two advisory AVA findings). Pass@2 passed again; **deep review FAIL**: both trials failed exactly the
   same 4 electron beams by reducing rectangular inserts with the equivalent square for SSDeff and the air-gap factor,
   while TG-71 (Sec. 3.B.2.d and Eq. 22) uses the geometric mean of the sides. The reviewer could not see the report
   (not in the repo) and ruled the rule undisclosed (U1, U2, U3, T5.1, T6.3, T10.3-CAT, G-DIFF), and warned that
   writing the rule out would make the task too easy.
6. Fix chosen: one instruction sentence pointing to the governing sections without stating the rule ("A rectangular
   insert is taken as the report takes rectangular electron fields, for the output factor (Sec. 2.B.2), the effective
   SSD (Sec. 3.B.2.d) and the air gap factor (Sec. 3.B.2.e)."), the report's exact wording saved in
   `authoring/sources/tg71_rectangular_electron_fields.txt`, and the same quotes as comments in tests/engine.py next to
   the code. Two calibration shortcuts added for the agents' equivalent-square reading. Outcome not reported before the
   person moved on.

### London Medicine: tg51-output-audit (AAPM TG-51 1999 + 2014 photon addendum)
Source PDFs: TG-51 from the person (Wiley download; strip its "Downloaded from ... by <institution>" footer lines),
the addendum downloaded by Claude from `https://www.aapm.org/pubs/reports/RPT_67_Addendum.pdf` after adding
`www.aapm.org` to the environment's allowed hosts (RPT_67.pdf itself redirects to Wiley, which is blocked).
Design: 12 clinics' annual calibration worksheets, 138 beams (71 photon, 67 electron): signed polarity readings, two
voltages, mixed units (C/F; kPa, hPa, mmHg, inHg), electrometer ranges, raw depth scans (open, lead foil at 50 or 30
cm), chamber-axis profiles for Prp, clinical electron PDD, SAD/SSD set-ups, old chambers (TG-51 Table I) and new ones
(addendum Table I with the Sec. 3.E replacements), cross-calibrated plane-parallel chambers (Eq. 22, Pelec = 1).
Runs:
1. Static PASS. Artificiality FAIL on three new blocking checks: category alignment ("repository field london
   medicine vs metadata field Medicine"), Kyoto allowed tool use (stdlib only, no listed tool), Kyoto allowed task type
   (applying a protocol to synthetic worksheets is none of REPRODUCE, EXTRACT, TRAIN_EVAL, REPAIR_PORT). A1-A7, the
   authoring review and scientific grounding all PASSED. The run stopped before Pass@2 (attempt budget "free").
2. Rebuilt as **REPAIR_PORT**: ships a legacy Python 2 program `tg51calc` (numpy, scipy, 1999 protocol, removed APIs
   np.float and scipy.interp, no inHg, plus realistic legacy faults); numpy 2.2.6 and scipy 1.15.3 pinned in the agent
   image; the solution is the repaired port (solution/tg51calc copied over /app/tg51calc by solve.sh); `field =
   "London Medicine"`. A mechanical port gets 128 of 138 beams wrong. Pending.

### Hertz: HTZ-T10015 (csvkit header normalization)
See `hertz.md`. Attempt 1 submitted: codebase PR #1 and brief PR #2; automated pre-check "no blocking issues" and
the automated brief review "Brief approved at this commit". Waiting for Review 1.

## What the person asked for, in their words (keep doing these)

- "DO NOT DO ANY BLIND TRIALS." Verify everything locally; one validated zip per round.
- "Don't have a fresh agent solve it" (it spends their limit). Never run a test agent.
- "No clues, hints, guidance": FECA style. "It should try and understand what we need."
- "Be fast", "my Claude limit is nearly finished": short messages, act, do not re-explain.
- "Use what you have": reuse documents already uploaded before asking for more; when a document is needed, try to
  fetch it yourself first (and ask for the environment change if a host is blocked).
- "Go through each and every single task done so far. Look at how did this one stump? How did it pass?" Always design
  from the record in this file and `trajectories.md`, not from intuition.
- No em dashes in anything they paste. Plain words.
- No watermarks: no "Generated with Claude", no AI mentions in files, no co-author trailers in anything uploaded to
  their repos (the Insight branch commits in *this* repo keep the system's trailers; their PRs must not).
- They need the PR title, PR description and proposal for every task, the proposal in the exact format of
  `proposal.md` (they rejected a looser format: "that's not even how the proposal should be").
