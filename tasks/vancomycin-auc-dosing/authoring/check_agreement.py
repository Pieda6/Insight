#!/usr/bin/env python3
"""Check that the reference solution, the verifier engine and the generator's model agree on every patient.

Usage: python3 check_agreement.py      (from authoring/)
"""
import sys
sys.dont_write_bytecode = True       # never leave __pycache__ in the submitted task folder
import csv
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TASK = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(TASK / "tests"))
import engine  # noqa: E402
import generate  # noqa: E402
from local_check import run_solution  # noqa: E402


def rel(a, b):
    return abs(a - b) / max(abs(b), 1e-12)


def main():
    truth = engine.expected(TASK / "tests" / "data")
    gen = generate.rebuild_answers()
    out = run_solution(TASK)
    with open(out / "vancomycin_review.csv", newline="") as fh:
        sol = {r["patient_id"]: r for r in csv.DictReader(fh)}
    worst_gen = worst_sol = 0.0
    cat_gen = cat_sol = 0
    for pid, w in truth.items():
        g = gen[pid]
        worst_gen = max(worst_gen, rel(g["ke"], w["ke"]), rel(g["V"], w["volume"]), rel(g["auc48"], w["auc48"]),
                        rel(g["auc24"], w["auc24"]))
        cat_gen += g["exposure"] != w["exposure"] or g["new"] != w["new_dose"]
        s = sol[pid]
        worst_sol = max(worst_sol, rel(float(s["ke_per_h"]), w["ke"]), rel(float(s["volume_l"]), w["volume"]),
                        rel(float(s["auc48"]), w["auc48"]), rel(float(s["auc24_ss"]), w["auc24"]))
        cat_sol += s["exposure"] != w["exposure"] or int(s["new_dose_mg"]) != w["new_dose"]
    ratio_margin = min(min(abs(w["auc24"] / m / 400 - 1), abs(w["auc24"] / m / 600 - 1))
                       for w, m in ((w, gen[p]["mic"]) for p, w in truth.items()))
    # counts quoted in README.md and authoring/README.md
    from collections import Counter
    fam = Counter(t for w in truth.values() for t in w["tags"])
    print("patients per method family (engine tags):")
    for k in sorted(fam):
        print(f"  {k}: {fam[k]}")
    pats, adm, lev, ords = engine.load(TASK / "tests" / "data")
    print(f"patients with a loading dose order: {len({o['patient_id'] for o in ords if o['frequency'] == 'once'})}")
    print(f"patients with an order change: {fam['changed_orders']}")
    round_margin = min(abs(gen[p]["raw"] / 250 - math.floor(gen[p]["raw"] / 250) - 0.5) * 250 / gen[p]["raw"]
                       for p in gen if gen[p]["exposure"] != "within")
    print(f"closest unrounded new dose to a rounding midpoint: {100 * round_margin:.3f} percent of the dose")
    multi = 0
    for p in pats:
        pid = p["patient_id"]
        by = {}
        for r in adm:
            if r["patient_id"] == pid:
                by.setdefault(r["administration_id"], []).append(r)
        segs, spans = [], []
        for rows in by.values():
            sg, sp = engine.segments_of(rows)
            if sp:
                segs += sg
                spans.append(sp)
        t0 = min(a for a, _, _ in segs)
        segs = [(a - t0, b - t0, m) for a, b, m in segs]
        spans = [(a - t0, b - t0) for a, b in spans]
        use = []
        for r in lev:
            v = engine.parse_result(r["result"]) if r["patient_id"] == pid else None
            if v is None:
                continue
            t = engine.hours(r["collected"]) - t0
            if not any(a <= t <= b or 0 < t - b < 1 for a, b in spans):
                use.append((t, v))
        (t1, c1), (t2, c2) = sorted(use)
        f = lambda k: engine.amount(segs, t1, k) * c2 - engine.amount(segs, t2, k) * c1
        pts = [10 ** (-6 + 8 * i / 2000) for i in range(2001)]
        vals = [f(k) for k in pts]
        multi += sum((vals[i] > 0) != (vals[i + 1] > 0) for i in range(2000)) != 1
    print(f"patients without exactly one elimination-rate solution between 1e-6 and 100 per hour: {multi}")
    print(f"patients: engine {len(truth)}, generator {len(gen)}, solution {len(sol)}")
    print(f"generator vs engine: {cat_gen} exposure or dose differences, largest relative difference {worst_gen:.1e}")
    print(f"solution vs engine:  {cat_sol} exposure or dose differences, largest relative difference {worst_sol:.1e}"
          " (solution rounds to its printed decimals)")
    print(f"closest AUC24/MIC to 400 or 600: {100 * ratio_margin:.3f} percent")
    ok = len(truth) == len(gen) == len(sol) and not cat_gen and not cat_sol and worst_gen < 1e-8 and worst_sol < 5e-4 \
        and ratio_margin > 0.005 and round_margin > 0.005 and not multi
    print("AGREEMENT:", "OK" if ok else "PROBLEM")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
