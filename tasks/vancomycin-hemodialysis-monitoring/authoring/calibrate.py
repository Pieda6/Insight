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
    "levels during or within 2 hours after an earlier session kept": [
        ("\n                  and not any(a <= t < b + 120 for a, b in spans[:k])]", "]")],
    "window of 3 hours": [("start - 120 <= t < start", "start - 180 <= t < start")],
    "window end exclusive (exactly 2 hours dropped)": [("start - 120 <= t < start", "start - 120 < t < start")],
    "umol/L read as mg/L": [('x * (MG_PER_UMOL if r["units"] == "umol/L" else 1.0)', "x")],
    "original kept over the correction": [('if r["accession"] not in reports or r["status"] == "corrected":',
                                           'if r["accession"] not in reports:')],
    "earliest level in the window": [("level = max(ok)[1] if ok else None", "level = min(ok)[1] if ok else None")],
    "range ends exclusive": [("elif level < LOW:", "elif level <= LOW:"), ("elif level > HIGH:", "elif level >= HIGH:")],
    "scaled to 15 mg/L": [("TARGET, LOW", "TARGET, LOW_"), ("= 17.5, 15.0,", "= 15.0, 15.0,"), ("LOW_", "LOW")],
    "rounded down": [("math.floor(x / 250.0 + 0.5)", "math.floor(x / 250.0)")],
    "loading not capped": [("min(w * LOADING[key], 3000.0)", "w * LOADING[key]")],
    "intradialytic range low end": [('("intradialytic", "low"): 8.75, ("intradialytic", "high"): 12.5',
                                     '("intradialytic", "low"): 7.5, ("intradialytic", "high"): 10.0')],
    "no restart on a dialyzer or timing change": [
        ('elif key != (ss[k - 1]["vancomycin_timing"], ss[k - 1]["dialyzer"]):', "elif False:")],
    "no hold above 25 mg/L": [("dose = 0 if level > HOLD else current", "dose = current")],
    "held session keeps the old dose for later": [
        ("                    current = to_250(current * TARGET / level)\n                    dose = 0 if level > HOLD else current",
         "                    new = to_250(current * TARGET / level)\n                    dose = 0 if level > HOLD else new\n"
         "                    current = current if level > HOLD else new")],
    "loading dose carried as the maintenance dose": [("dose = to_250(min(w * LOADING[key], 3000.0))",
                                                      "dose = current = to_250(min(w * LOADING[key], 3000.0))")],
}


def main():
    truth = engine_loader.truth()
    ok_all = True
    print(f"{len(S)} shortcuts, each must fail at least one test")
    for name, reps in S.items():
        src = SOLVE
        for old, new in reps:
            assert src.count(old) == 1, (name, old)
            src = src.replace(old, new)
        out = local_check.run_solution(TASK, src)
        with open(out / "session_doses.csv") as fh:
            got = {r["session_id"]: (r["status"], int(r["dose_mg"])) for r in csv.DictReader(fh)}
        wrong = sum(got[k] != w[1:] for k, w in truth.items())
        failed = bool(local_check.run_tests(TASK, out)[1])
        ok_all &= failed
        print(f"{'caught' if failed else 'MISSED'}  {wrong:5d} of {len(truth)} sessions wrong  {name}")
    print("CALIBRATION:", "every shortcut caught" if ok_all else "SOME SHORTCUT PASSES")


if __name__ == "__main__":
    main()
