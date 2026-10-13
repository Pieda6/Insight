# hos-log-audit dev tools (never upload these)

- `generate.py` (seed 395003) writes `tasks/hos-log-audit/environment/data/` (carriers.json, terminals.json,
  drivers.json, logs.json), the identical verifier copy in `tests/data/`, `tests/case_tags.json` and
  `tests/golden.json` (42 planted drivers with hand-worked violations). Filler drivers are long-haul,
  split-sleeper, regional and near-threshold sleeper-berth fleets whose answers come from the engine only;
  `contested()` regenerates any filler log that would need one of the open readings listed below.
- `calibrate.py` (needs writable `/app`): oracle passes, empty output fails, 32 misreadings (source edits of
  the reference solution) each fail at least one test.

Contested readings kept out of the data on purpose: a sleeper-berth pair whose surrounding driving would
break the recalculated limits (395.1(g)(1)(ii)(D) read as a limit or as a condition of the pair), driving
between two paired rests beyond the original 14 hours (retroactive exclusion), a pure off-duty period as
the short half of a pair, sleeper-berth time inside a 34-hour restart, adverse conditions combined with
the 30-minute break, invalid 16-hour claims followed by another claim. No daylight-saving change falls
inside the records (late August to mid October 2026), and terminals carry a fixed UTC offset.

Rule text used (pasted by the author from law.cornell.edu): 49 CFR 395.1, 395.2, 395.3.
v2 (after Pass@5 3/5): the two failed Pass@2 trials missed only near-threshold split and break
cases on filler drivers, so 14 near-threshold drivers and 7 planted near-miss drivers were added.

Replaces hazmat-trailer-check in the Operations / Logistics PR after hazmat was solved 2/2 three times.
