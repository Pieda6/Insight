#!/usr/bin/env python3
"""Check that the reference solution, the verifier engine and the generator's model agree on every row.

Usage: python3 check_agreement.py      (from authoring/)
"""
import csv
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
TASK = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(TASK / "tests"))
import engine  # noqa: E402
import sim  # noqa: E402
from local_check import run_solution  # noqa: E402


def main():
    truth = engine.expected(TASK / "tests" / "data")
    systems, flows, tw = engine.load(TASK / "tests" / "data")
    gen = {}
    for s in systems:
        for ev in flows:
            for pid, r in sim.evaluate(s, flows[ev], tw[(s["system_id"], ev)]).items():
                gen[(s["system_id"], ev, pid)] = r
    out = run_solution(TASK)
    with open(out / "pipe_grades.csv", newline="") as fh:
        sol = {(r["system_id"], r["event"], r["pipe_id"]): r for r in csv.DictReader(fh)}

    worst_gen = worst_sol = 0.0
    letters_gen = letters_sol = 0
    for w in truth:
        key = w[:3]
        case, cond, accepted, eo, ei, ea, sur = w[3:]
        g = gen[key]
        if g[0] != case or g[1] != cond or g[5] != sur:
            letters_gen += 1
        worst_gen = max(worst_gen, abs(g[2] - eo), abs(g[3] - ei), abs(g[4] - ea))
        r = sol[key]
        if r["ds_case"] != case or r["us_condition"] not in accepted or r["surcharged"] != sur:
            letters_sol += 1
        worst_sol = max(worst_sol, abs(float(r["egl_ds_ft"]) - eo), abs(float(r["egl_us_ft"]) - ei),
                        abs(float(r["structure_egl_ft"]) - ea))
    # every threshold comparison stays at least 0.001 ft from its boundary
    near = []
    closest = {}
    for s in systems:
        for ev in flows:
            tr = {}
            engine.evaluate(s, flows[ev], tw[(s["system_id"], ev)], trace=tr)
            for pid, t in tr.items():
                checks = {"Table 9.6": [t["egl_a_down"] - (t["boc_o"] + x) for x in (0.0, t["yc"], t["yn"], t["dia"])],
                          "Table 9.7": [t["hgl_i"] - (t["boc_i"] + x) for x in
                                        ((t["dia"], t["yc"]) if t["at_normal"] else (t["dia"], t["yc"], t["yn"]))],
                          "plunging test": [z - t["eai"] for z in t["inflow_zk"]],
                          "surcharge": [t["za"] + t["ea"] - t["rim"]]}
                for name, vals in checks.items():
                    for v in vals:
                        closest[name] = min(closest.get(name, 9e9), abs(v))
                        if abs(v) < 0.001:
                            near.append((s["system_id"], ev, pid, name, v))
                        if abs(v) <= 0.03:
                            closest[name + " within 0.03 ft (count)"] = closest.get(name + " within 0.03 ft (count)", 0) + 1
    for k in sorted(closest):
        print(f"  {k}: {closest[k]:.4f}" if "count" not in k else f"  {k}: {closest[k]}")
    print(f"comparisons closer than 0.001 ft to a threshold: {len(near)}")
    print(f"rows: engine {len(truth)}, generator {len(gen)}, solution {len(sol)}")
    print(f"generator vs engine: {letters_gen} letter or yes/no differences, largest elevation difference "
          f"{worst_gen:.2e} ft")
    print(f"solution vs engine:  {letters_sol} letter or yes/no differences, largest elevation difference "
          f"{worst_sol:.4f} ft (solution rounds to 3 decimals)")
    ok = len(truth) == len(gen) == len(sol) and not letters_gen and not letters_sol and worst_gen < 1e-6 \
        and worst_sol <= 0.0005 + 1e-9 and not near
    print("AGREEMENT:", "OK" if ok else "PROBLEM")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
