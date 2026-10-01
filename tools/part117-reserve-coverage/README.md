# part117-reserve-coverage: author notes

These dev tools are not part of the task and are never shipped in either image.

- `generate.py` builds the synthetic data. It writes `environment/data/*.csv` and an identical copy in `tests/data/`.
- `calibrate.py` explains each pilot-trip result, checks every planted shortcut, and writes `tests/trap_pairs.json` when run with `--write`. With `--submit NAME` it writes a shortcut solver's output to `/app/output` so you can run the tests against it.

```bash
python tools/part117-reserve-coverage/generate.py
python tools/part117-reserve-coverage/calibrate.py --write      # add -v for a per-pair explanation
```

## What `instruction.md` must state

Write the prompt yourself. Each item below changes a graded answer, so the agent has to be able to find it in the prompt. Do not explain how to solve the task.

**Inputs**
- The input files are in `/app/data`.
- Every `*_local` time is local time at the station named on the same row (the trip's base for `trips.csv`, the pilot's base for `pilots.csv`).
- `stations.csv` gives each station's IANA time zone.
- `duties.csv` gives each pilot's complete duty history before the reserve period. `duty_type` is `FDP` or `OTHER`; `OTHER` is duty that is not a flight duty period (training or office).
- `legs.csv` gives the flight legs of each historical FDP, with block-out and block-in times.

**The situation**
- 14 CFR Part 117 applies, unaugmented.
- Every reserve is on short-call reserve, and the reserve availability period is in `pilots.csv`.
- No extensions, split duty or deadheading are involved.
- The 1,000-hour / 365-day limit can be ignored.

**Assignment rules**
- A pilot can take at most one trip.
- The pilot must match the trip's base, seat (no seat substitution) and equipment.
- The trip's report time must fall inside the pilot's reserve availability period.

**Acclimatization**
- Every pilot is acclimated to their base at the start of the history.
- Two places are in the same theater when their UTC offsets, compared at the time of arrival, differ by no more than 4 hours.
- The 36 duty-free hours that acclimate a pilot to a new theater must fall after arriving in that theater.

**Look-back windows**
- The 168-hour and 672-hour cumulative windows end at the scheduled end of the new FDP.
- Duty or flight time that is only partly inside a window counts only for the part inside it.
- A duty-free period counts toward the 30 hours only for the part inside the 168-hour window.

**Objective:** cover as many trips as possible, then minimize the total `callout_cost`.

**Outputs**
- `/app/output/legality.csv` has columns `pilot_id,trip_id,legal`, one row for every pilot and trip combination, with `legal` set to `true` or `false`.
- `/app/output/assignment.json` has `{"assignments": [{"trip_id": ..., "pilot_id": ...}], "trips_covered": int, "total_callout_cost": int}`.

**Your call (whether to state it):** the reserve-plus-FDP cap uses the *applicable* Table B limit, which includes the 30-minute reduction for a pilot who is not acclimated. That is how I read 117.21(c)(3), but a reviewer could call it a convention. If you think it is arguable, state it in the prompt.

**Do not say** anything about local departure time, recent Europe trips, DST, greedy assignment or the other traps. Finding those is the task.

## Check before submitting (written from memory, because eCFR was blocked from the build container)

- **Table B values:** `TABLE_B` in `solution/solve.py` and `_B` in `tests/engine.py`.
- **Table A:** 9 h for a report from 0500 to 1959, otherwise 8 h.
- **117.21(c)(3):** reserve plus FDP is capped at the lesser of 16 h or Table B + 4 h, measured from the start of the reserve availability period.
- **117.25(b):** 30 consecutive hours free in the 168 hours before beginning a reserve or an FDP.
- **117.25(e):** 10 consecutive hours of rest immediately before a reserve or an FDP.
- **117.23:** 60 h FDP / 168 h, 190 h FDP / 672 h, and 100 h flight time / 672 h.
- **117.3:** the "acclimated" and "theater" definitions.

If any value is different, fix it in both files, then rerun `generate.py`, `calibrate.py --write` and the oracle and nop checks.

## Calibration (current data)

- **Data:** 30 pilots and 30 trips, giving 900 pairs, of which 70 are legal.
- **Optimum:** 26 trips covered at a call-out cost of 5820.
- **Cross-check:** the oracle (`solve.py`) and the verifier engine (`tests/engine.py`) are written independently and agree on all 900 pairs and on the optimum.
- **Reference solution:** passes all 11 tests.
- **Nop** (no output): all 11 tests error, so reward 0.
- **Shortcut solvers:** each fails at least one test.

| Shortcut | Failing tests |
|---|---|
| Table B read on local departure time (no acclimatization) | 6 |
| "Back from Europe within 72 h means not acclimated" | 5 |
| Unreduced Table B in the reserve-plus-FDP cap | 3 |
| 30-hours-free checked only at reserve start | 3 |
| `OTHER` duty counted as FDP | 4 |
| Whole duty counted if it touches the window | 4 |
| EST used instead of EDT after 03-08 | 2 |
| Table A ignored | 2 |
| Greedy cheapest-first assignment | 2 |
