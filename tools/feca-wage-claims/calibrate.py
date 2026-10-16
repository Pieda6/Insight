#!/usr/bin/env python3
"""Dev-only calibration for feca-wage-claims (never uploaded): oracle passes, empty output fails, and each
common misreading of the FECA and 20 CFR Part 10 fails at least one test. Each misreading is a small source edit of the
reference solution. Needs a writable /app."""
import csv
import shutil
import subprocess
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TASK = ROOT / "tasks" / "feca-wage-claims"
OUT = Path("/app/output/claim_determinations.csv")
SRC = (TASK / "solution" / "solve.py").read_text()
SHORTCUTS = {
    # ---- COP days (10.215)
    "injury day never charged": [('before_shift = is_work(hurt_day) and hurt.strftime("%H:%M") < emp["shift_start"]', "before_shift = False")],
    "partial days not charged": [('if chargeable_workday(d):', 'if chargeable_workday(d) and not status[d]["hours_absent_per_day"]:')],
    "regular days off never charged": [("elif not part_time and not is_work(d) and is_disabled(d):", "elif False:")],
    "regular days off charged without medical evidence": [("elif not part_time and not is_work(d) and is_disabled(d):", "elif not part_time and not is_work(d):")],
    "days off only between two charged workdays": [("if chargeable_workday(p) or chargeable_workday(n):", "if chargeable_workday(p) and chargeable_workday(n):")],
    "days off only after a charged workday": [("if chargeable_workday(p) or chargeable_workday(n):", "if chargeable_workday(p):")],
    "part-time: only scheduled days": [("if part_time or is_work(d):\n                    status[d] = r", "if is_work(d):\n                    status[d] = r")],
    "leave not counted toward 45": [('if not eligible or r is None or r["absence_requested_as"] == "leave without pay":',
                                     'if not eligible or r is None or r["absence_requested_as"] != "continuation of pay":')],
    "no 45-day limit": [("len(charged) < 45", "len(charged) < 10 ** 6")],
    "45 workdays instead of calendar days": [("len(charged) < 45", "len([x for x in charged if is_work(x)]) < 45")],
    # ---- eligibility (10.205, 10.220)
    "notice within 30 days exclusive": [('<= hurt_day + timedelta(days=30)', '< hurt_day + timedelta(days=30)')],
    "notice deadline ignored": [('and day(claim["notice_filed_with_supervisor"]) <= hurt_day + timedelta(days=30)', '')],
    "45 days to stop work exclusive": [("and first <= hurt_day + timedelta(days=45))", "and first < hurt_day + timedelta(days=45))")],
    "45 days to stop work ignored": [("and first <= hurt_day + timedelta(days=45))", ")")],
    "occupational disease gets COP": [('traumatic = claim["claim_type"].startswith("traumatic")', "traumatic = True")],
    # ---- returns to work (10.207)
    "no COP after a return": [("return stop_date(d) <= first_back + timedelta(days=45)     # 10.207(c)", "return False")],
    "COP after any return": [("return stop_date(d) <= first_back + timedelta(days=45)     # 10.207(c)", "return True")],
    "45 days from the return exclusive": [("return stop_date(d) <= first_back + timedelta(days=45)     # 10.207(c)", "return stop_date(d) < first_back + timedelta(days=45)")],
    # ---- waiting period (8117, 10.401)
    "no waiting period": [("waiting = 3 if len(spell) <= 14 else 0", "waiting = 0")],
    "waiting period always": [("waiting = 3 if len(spell) <= 14 else 0", "waiting = 3")],
    "waiting period unless 14 days or more": [("waiting = 3 if len(spell) <= 14 else 0", "waiting = 3 if len(spell) < 14 else 0")],
    "compensation only for workdays": [("            for d in spell[waiting:]:", "            for d in [x for x in spell[waiting:] if is_work(x)]:")],
    # ---- pay rate (8114, 10.5(s))
    "pay rate at injury only": [("rate, since = max(annual(hurt_day), annual(first)), first", "rate, since = annual(hurt_day), first")],
    "pay rate at the start of each spell": [("rate, since = max(annual(hurt_day), annual(first)), first", "rate, since = annual(spell[0]), first")],
    "recurrence pay rate ignored": [("if start > shift_months(back, 6) and annual(start) > rate:", "if False:")],
    "recurrence pay rate without the six months": [("if start > shift_months(back, 6) and annual(start) > rate:", "if annual(start) > rate:")],
    "standby premium excluded": [('* (100 + pay["standby_duty_premium_percent_5545c1"]) / 100', "")],
    "overtime included": [('* (100 + pay["standby_duty_premium_percent_5545c1"]) / 100',
                           '* (100 + pay["standby_duty_premium_percent_5545c1"]) / 100 + emp["overtime_pay_last_12_months_cents"]')],
    "wage grade always 260 days": [('{"5": 260, "5.5": 280, "6": 300}[emp["workweek_days"]]', "260")],
    # ---- dependents and COLA (8110, 10.405, 10.420)
    "dependents ignored": [("share = Fraction(3, 4) if dependent(d) else Fraction(2, 3)", "share = Fraction(2, 3)")],
    "students ignored": [("if on < shift_months(born, 276) and any(", "if False and any(")],
    "child counted through the 18th birthday": [("if on < shift_months(born, 216) or", "if on <= shift_months(born, 216) or")],
    "no cost-of-living adjustments": [("if when <= d and since < shift_months(when, -12):", "if False:")],
    "COLA after one year from the injury": [("if when <= d and since < shift_months(when, -12):", "if when <= d and hurt_day < shift_months(when, -12):")],
    "COLA regardless of the one-year test": [("if when <= d and since < shift_months(when, -12):", "if when <= d:")],
}


def tests():
    p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                        str(TASK / "tests" / "test_outputs.py")], capture_output=True, text=True)
    return p.returncode, [ln.split("::", 1)[1].split(" ")[0] for ln in p.stdout.splitlines() if ln.startswith("FAILED")]


def run(src):
    mod = types.ModuleType("solve_variant")
    exec(compile(src, "solve_variant", "exec"), mod.__dict__)
    mod.main()


def main():
    Path("/app/data").mkdir(parents=True, exist_ok=True)
    for f in Path("/app/data").iterdir():
        f.unlink()
    for f in (TASK / "environment" / "data").iterdir():
        shutil.copy(f, Path("/app/data") / f.name)
    run(SRC)
    truth = {r["claim_id"]: r for r in csv.DictReader(open(OUT))}
    print("oracle", tests())
    OUT.unlink()
    print("nop rc", tests()[0])
    ok = True
    for name, edits in SHORTCUTS.items():
        src = SRC
        for old, new in edits:
            assert old in src, (name, old)
            src = src.replace(old, new)
        try:
            run(src)
        except Exception as e:  # noqa: BLE001
            print(f"   crash {name}: {e!r} (counts as failing)")
            continue
        got = {r["claim_id"]: r for r in csv.DictReader(open(OUT))}
        wrong = sum(1 for c, v in truth.items() if got.get(c) != v)
        rc, failed = tests()
        ok &= bool(rc)
        fams = [f.split("[")[1].rstrip("]") for f in failed if "family" in f]
        print(f"{'ok ' if rc else '!! PASSES'} {name:58s} wrong={wrong:3d} {fams}")
    run(SRC)
    print("ALL SHORTCUTS FAIL" if ok else "SOME SHORTCUT PASSES")


if __name__ == "__main__":
    main()

