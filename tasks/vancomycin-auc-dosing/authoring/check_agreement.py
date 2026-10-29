#!/usr/bin/env python3
"""Check that the reference solution, the verifier engine and the generator's model agree on every patient.

Usage: python3 check_agreement.py      (from authoring/)
"""
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
    print(f"patients: engine {len(truth)}, generator {len(gen)}, solution {len(sol)}")
    print(f"generator vs engine: {cat_gen} exposure or dose differences, largest relative difference {worst_gen:.1e}")
    print(f"solution vs engine:  {cat_sol} exposure or dose differences, largest relative difference {worst_sol:.1e}"
          " (solution rounds to its printed decimals)")
    print(f"closest AUC24/MIC to 400 or 600: {100 * ratio_margin:.3f} percent")
    ok = len(truth) == len(gen) == len(sol) and not cat_gen and not cat_sol and worst_gen < 1e-8 and worst_sol < 5e-4 \
        and ratio_margin >= 0.0005
    print("AGREEMENT:", "OK" if ok else "PROBLEM")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
