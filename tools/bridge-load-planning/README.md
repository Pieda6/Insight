# bridge-load-planning: author notes

These dev tools are not part of the task, so don't upload them.

- `generate.py` builds the fleet and pallets, writes identical data to `environment/data/` and `tests/data/`, and writes `tests/expected.json` with the proven minimum.
- `calibrate.py` cross-checks the verifier engine against the solver on random loads, then runs the empty (nop) submission, the reference solution, and five shortcut solvers through the real tests. Every shortcut must fail.

```bash
python tools/bridge-load-planning/generate.py
mkdir -p /app && cp -r tasks/bridge-load-planning/environment/data /app/data
python tools/bridge-load-planning/calibrate.py
```

## Calibration (current data)

- **Fleet:** 14 units, 32 slider settings and 64 pallets weighing 612,475 lb in total.
- **Minimum:** 12 units. The 11 strongest units can legally carry at most 564,721 lb in total, so 11 is impossible. The reference solution finds a legal 12-unit plan in about 2 seconds.
- **Engine cross-check:** 0 mismatches on 4,000 random loads.
- **Nop** (no output): every test errors, so reward 0.
- **Reference solution:** all 8 tests pass.

| Shortcut | Test that fails |
|---|---|
| No 34k + 34k two-tandem allowance | minimum number of units (needs 13) |
| Span rounded down to whole feet | minimum number of units |
| Bridge Formula checked only on the whole truck | Bridge Formula on every axle group |
| No Bridge Formula at all | Bridge Formula on every axle group |
| Greedy heaviest-first | minimum number of units |

## What `instruction.md` must state

Write the prompt yourself, as plain paragraphs, and keep it under 1,500 tokens. Each item below changes the graded answer, so the agent has to be able to find it in the prompt.

**Situation**
- Heavy freight has to ship on the company's tractor-trailers, using as few units as possible.
- Every loaded truck must be legal on the Interstate under 23 CFR 658.17.

**Inputs**
- `/app/data/units.csv` holds the tractor and trailer geometry: `unit_id`, `tractor_model`, `steer_x_in`, `drive1_x_in`, `drive2_x_in`, `kingpin_x_in` and `trailer_inside_length_in`.
- `/app/data/sliders.csv` lists the allowed slider settings for each unit: `unit_id`, `slider_position_id`, `trailer1_x_in`, `trailer2_x_in` and the empty weight on each axle (`tare_steer_lb`, `tare_drive1_lb`, `tare_drive2_lb`, `tare_trailer1_lb`, `tare_trailer2_lb`).
- `/app/data/pallets.csv` holds `pallet_id`, `description`, `weight_lb` and `length_in`.
- `/app/reference/worked_examples.md` has two worked numeric examples.

**Geometry and conventions**
- All `_x_in` values are inches from the trailer's inside front wall, with rearward positive. The steer axle is negative.
- A pallet's position is a whole number of inches from the front wall to the pallet's front edge.
- Pallets sit in a single lane, inside the inside length, without overlapping. Any order and any gaps are allowed.
- Each pallet's weight acts at the middle of its length.
- Each tandem's load splits equally between its two axles.
- Every used unit gets exactly one of its own slider settings.

**Limits**
- Axle 1 is a single axle (20,000 lb). Axles 2–3 and 4–5 are tandems (34,000 lb each). Gross is limited to 80,000 lb.
- The Bridge Formula applies to every group of two or more consecutive axles.
- Spans are converted to whole feet by rounding to the nearest foot, with half a foot rounding up. W is rounded to the nearest 500 lb, with 250 rounding up.
- The 34,000 + 34,000 lb two-tandem provision applies to axles 2–5 when that span is 36 ft or more.
- Legality is judged on exact loads, not rounded ones.

**Goal:** use the fewest units. Any legal plan that uses the minimum is accepted.

**Outputs**
- `/app/output/load_plan.csv` has columns `pallet_id,unit_id,position_in`, one row per pallet.
- `/app/output/units.csv` has columns `unit_id,slider_position_id`, one row per unit used.
- `/app/output/summary.json` has two keys:
  - `units_used`: a whole number.
  - `axle_loads_lb`: maps each used `unit_id` to 5 whole numbers in the order steer, drive 1, drive 2, trailer 1, trailer 2. Round half up; values within 1 lb of the exact loads are accepted.

**Last line, exactly:**
`You have 28800 seconds to complete this task. Do not cheat by using online solutions or hints specific to this task.`

**Do not mention**
- that the inner axle group is the one that often binds;
- greedy loading;
- which units are forward-only;
- that the minimum is 12;
- how to solve it (lever balance, MILP and so on).

## Check against eCFR before submitting (written from memory)

- **23 CFR 658.17:** limits of 20,000 single, 34,000 tandem and 80,000 gross. The Bridge Formula W = 500(LN/(N-1) + 12N + 36). The two-consecutive-tandem provision: 34,000 lb each when the first-to-last axle distance is 36 ft or more.
- **23 CFR 658.5:** single and tandem axle definitions (40 in and 96 in).

Our rounding rules are stated in the task as conventions, so they stay fair either way. If the regulation's text differs, adjust `bridge_limit` in `solution/solve.py` and `tests/engine.py`, then rerun both tools.
