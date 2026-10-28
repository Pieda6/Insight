# Authoring tools for stormwater-inspection-audit

Task: audit 39 construction sites in Puerto Rico under EPA's 2022 Construction General Permit (as modified
April 8, 2025) for January 1 to September 30, 2026, and list every requirement missed or met late.

These files are not copied into the agent or verifier images. Run them from this folder.

## Files
- `generate.py` (seed 40122): builds 28 random filler sites and the 11 planted sites, writes both data copies
  (`../environment/data`, `../tests/data`), `../tests/golden.json` (hand-worked rows of the planted sites) and
  `../tests/case_tags.json`. `python3 generate.py`.
- `sim.py`: the generator's own model of the rules (third implementation). In strict mode it reports cases where a
  second defensible reading would change the answer; the generator repairs them (adds an on-time inspection, or
  lowers a day's rain below the threshold) or regenerates the site.
- `planted.py`: the 11 planted sites, each with its expected rows worked by hand in the comments.
- `calibrate.py`: 47 shortcut solutions (source edits of solve.py); every one fails at least one test.
  `python3 calibrate.py` (uses `local_check.py`, which runs the solution and tests without Docker).
- `cgp_parts_1_10.txt`, `cgp_appendix_a.txt`: permit text extracted from the PDFs the person uploaded.

## Rules used (permit text in the two .txt files)
Parts 2.1.4 (maintenance, repeat fixes), 2.2.4 (track-out), 2.2.14 and footnotes 36 to 41 (stabilization, the
5-acre test of footnote 38), 3.2, 4.2, 4.3.1, 4.4.1 and footnotes 59, 67 to 69 (inspection frequency, storms,
working hours), 4.7.1 (reports), 5.1, 5.2.1, 5.4.1 (corrective actions, log, SWPPP), Appendix A ("business day",
"storm event"). Puerto Rico has no Part 9 conditions (Region 2 lists only New York Indian country).

## Open readings and how they are settled
Pinned in instruction.md (approved in the proposal QC): business days from the log; daily gauge readings are the
24-hour periods, rain at 23:59; storms are runs of measurable days, inspections after the first and last day at the
threshold; routine clock from the actual date of the latest inspection, one row when never inspected; schedule
changes count from the later of the latest inspection and the change; first month after stabilization to the same
date next month, 14 days then one month; 5-acre test over the whole project, completion day included; fourth and
later repeats are corrective actions; deadlines at 23:59 or the same clock time; met at the deadline is on time;
report rows use the first area listed; sort order and requirement names.

Kept out of the data by the strict model (`sim.py`):
- a late routine inspection whose deadline falls on a day with no working hours (footnote 67 could move it);
- a schedule change (stabilization, end of first month, resumption) while a routine inspection is already overdue;
- a storm on a day next to an area's schedule change;
- an area whose next business day after work stops is the restart day itself;
- stabilization completed after work resumes, or work on the day stabilization is completed.
By construction: significant repairs and new controls never share fix wording with routine fixes; ongoing areas
always have a logged day in the last 13 days of September; no dewatering, snow, frozen ground, arid areas, linear
sites, unforeseen circumstances or Lands of Exclusive Federal Jurisdiction.

## Checks (all run in this conversation)
- engine.py, solve.py and sim.py agree on all 1,197 rows; the planted sites match the hand-worked rows.
- local_check: oracle 12/12 tests pass, empty output fails.
- calibrate.py: all 47 shortcuts fail.

## History
- v1: first build.
