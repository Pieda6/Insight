#!/usr/bin/env python3
"""Dev-only calibration for ssdi-work-review: oracle passes, empty output fails, and each common misreading of
20 CFR 404 fails at least one test. Each misreading is a small source edit of the reference solution. Needs /app."""
import shutil
import subprocess
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TASK = ROOT / "tasks" / "ssdi-work-review"
OUT = Path("/app/output/monthly_determinations.csv")
SRC = (TASK / "solution" / "solve.py").read_text()
SHORTCUTS = {
    "onset month always counted as a full month": [("full = idx(y, m) if dd == 1 else idx(y, m) + 1", "full = idx(y, m)")],
    "onset month never counted (even on the 1st)": [("full = idx(y, m) if dd == 1 else idx(y, m) + 1", "full = idx(y, m) + 1")],
    "waiting period of 6 months": [("max(full + 5,", "max(full + 6,")],
    "no 12-month limit on retroactivity": [("return max(full + 5, idx(fy, fm) - 12), idx(fy, fm)", "return full + 5, idx(fy, fm)")],
    "trial work months counted before the month of filing": [("service = i >= filed and gross", "service = gross")],
    "trial work months judged on countable earnings": [("and gross > a[\"trial_work_period_service_month\"]", "and countable > a[\"trial_work_period_service_month\"]")],
    "trial work amount inclusive": [("and gross > a[", "and gross >= a[")],
    "nine service months in total, no rolling window": [("if len([s for s in services if s >= i - 59]) == 9:", "if len(services) == 9:")],
    "rolling window of 61 months": [("s >= i - 59", "s >= i - 60")],
    "SGA amount inclusive": [("sga = countable > (", "sga = countable >= (")],
    "impairment-related work expenses not deducted": [(" - e[\"impairment_related_work_expenses\"]", "")],
    "employer subsidy not deducted": [(" - e[\"employer_subsidy\"]", "")],
    "blind SGA amount ignored": [("if ben[\"statutorily_blind\"]", "if False")],
    "extended period of 37 months": [("if i <= twp_end + 36:", "if i <= twp_end + 37:")],
    "extended period of 35 months": [("if i <= twp_end + 36:", "if i <= twp_end + 35:")],
    "no grace months": [("i <= cessation + 2", "i <= cessation")],
    "three grace months": [("i <= cessation + 2", "i <= cessation + 3")],
    "no termination after the extended period": [("            if sga:\n                ended = True", "            if False:\n                ended = True")],
    "SGA during the trial work period stops payment": [("rows.append((i, True, service))", "rows.append((i, not (sga and i >= filed), service))")],
}


def tests():
    p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(TASK / "tests" / "test_outputs.py")],
                       capture_output=True, text=True)
    return p.returncode


def run(src):
    mod = types.ModuleType("v")
    exec(compile(src, "v", "exec"), mod.__dict__)
    mod.main()


def main():
    Path("/app/data").mkdir(parents=True, exist_ok=True)
    for f in Path("/app/data").iterdir():
        f.unlink()
    for f in (TASK / "environment" / "data").iterdir():
        shutil.copy(f, Path("/app/data") / f.name)
    run(SRC)
    truth = OUT.read_text().splitlines()
    print("oracle rc", tests())
    OUT.unlink()
    print("nop rc", tests())
    ok = True
    for name, edits in SHORTCUTS.items():
        src = SRC
        for old, new in edits:
            assert old in src, (name, old)
            src = src.replace(old, new)
        run(src)
        got = OUT.read_text().splitlines()
        wrong = len(set(truth) ^ set(got)) // 2
        rc = tests()
        ok &= bool(rc)
        print(f"{'ok ' if rc else '!! PASSES'} {name:58s} ~rows wrong={wrong}")
    run(SRC)
    print("ALL SHORTCUTS FAIL" if ok else "SOME SHORTCUT PASSES")


if __name__ == "__main__":
    main()
