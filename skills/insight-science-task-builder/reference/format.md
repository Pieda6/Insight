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
