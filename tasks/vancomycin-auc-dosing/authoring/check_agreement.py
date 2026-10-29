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
        # printed values must be the engine's values rounded to the stated decimals
        worst_sol = max(worst_sol, abs(float(s["ke_per_h"]) - w["ke"]) / 5e-7, abs(float(s["volume_l"]) - w["volume"]) / 5e-3,
                        abs(float(s["auc48"]) - w["auc48"]) / 5e-2, abs(float(s["auc24"]) - w["auc24"]) / 5e-2)
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
    # the engine raises unless each patient has exactly one clearance and volume through both levels
    multi = 0
    for p in pats:
        try:
            engine.evaluate(p, [r for r in adm if r["patient_id"] == p["patient_id"]],
                            [r for r in lev if r["patient_id"] == p["patient_id"]],
                            [r for r in ords if r["patient_id"] == p["patient_id"]],
                            [r for r in engine.load_dialysis(TASK / "tests" / "data") if r["patient_id"] == p["patient_id"]])
        except ValueError:
            multi += 1
    print(f"patients without exactly one fitted clearance and volume: {multi}")
    print(f"patients: engine {len(truth)}, generator {len(gen)}, solution {len(sol)}")
    print(f"generator vs engine: {cat_gen} exposure or dose differences, largest relative difference {worst_gen:.1e}")
    print(f"solution vs engine:  {cat_sol} exposure or dose differences; largest printed-value difference "
          f"{worst_sol:.3f} of half a unit in the last printed decimal (must be at most 1)")
    print(f"closest AUC24/MIC to 400 or 600: {100 * ratio_margin:.3f} percent")
    ok = len(truth) == len(gen) == len(sol) and not cat_gen and not cat_sol and worst_gen < 1e-8 and worst_sol <= 1.0 + 1e-6 \
        and ratio_margin > 0.005 and round_margin > 0.005 and not multi
    print("AGREEMENT:", "OK" if ok else "PROBLEM")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
