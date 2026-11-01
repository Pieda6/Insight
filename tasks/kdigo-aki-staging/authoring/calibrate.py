"""Shortcut solutions: solve.py with one reading changed by text replacement. Each must fail at least one test."""
import sys
sys.dont_write_bytecode = True       # never leave __pycache__ in the submitted task folder
import csv
from pathlib import Path

import engine_loader
import local_check

TASK = Path(__file__).resolve().parent.parent
SOLVE = (TASK / "solution" / "solve.py").read_text()
S = {
    "umol/L read as mg/dL": [('x / UMOL_PER_MG if r["units"] == "umol/L" else x', "x")],
    "original kept over the correction": [('if r["accession"] not in reports or r["status"] == "corrected":',
                                           'if r["accession"] not in reports:')],
    "rise window 24 hours": [("t - t0 <= 48 * 60", "t - t0 <= 24 * 60")],
    "rise compared with the first result only": [("for t0, c0 in results[:i])", "for t0, c0 in results[:1])")],
    "rise to 4.0 mg/dl ignored": [("            if c >= 4.0 and (rise or ratio >= 1.5):\n                s = 3\n", "")],
    "renal replacement ignored": [('for r in groups.get(("rrt.csv", pid), []):', 'for r in []:')],
    "urine periods ending at charting times only": [
        ("    pts = sorted({lo, hi} | {t for t in ts if lo < t < hi} | {t + span for t in ts if lo < t + span < hi})",
         "    pts = sorted(t for t in ts if lo <= t <= hi)"),
        ("            if prev is None:\n                return x\n", "            return x\n")],
    "anuria ignored": [(", (12, 0.0, 3, True))", ")")],
    "stage 1 urine needs 12 hours": [("((6, 0.5, 1, False),", "((12, 0.5, 1, False),")],
    "urine per kg ignored (ml/h)": [("rate * w * hours", "rate * 70 * hours")],
    "clock change ignored": [("offset_h = 4 if start <= wall < end else 5", "offset_h = 5")],
    "ratio stages ignored beyond stage 1": [("s = 3 if ratio >= 3.0 else 2 if ratio >= 2.0 else 1 if (ratio >= 1.5 or rise) else 0",
                                             "s = 1 if (ratio >= 1.5 or rise) else 0")],
}


def main():
    truth = engine_loader.truth()
    ok = True
    print(f"{len(S)} shortcuts, each must fail at least one test")
    for name, reps in S.items():
        src = SOLVE
        for old, new in reps:
            assert src.count(old) == 1, (name, old)
            src = src.replace(old, new)
        out = local_check.run_solution(TASK, src)
        with open(out / "aki_staging.csv") as fh:
            got = {r["patient_id"]: r["max_stage"] for r in csv.DictReader(fh)}
        wrong = sum(got[k] != str(w[0]) for k, w in truth.items())
        failed = bool(local_check.run_tests(TASK, out)[1])
        ok &= failed
        print(f"{'caught' if failed else 'MISSED'}  {wrong:4d} of {len(truth)} stages wrong  {name}")
    print("CALIBRATION:", "every shortcut caught" if ok else "SOME SHORTCUT PASSES")


if __name__ == "__main__":
    main()
