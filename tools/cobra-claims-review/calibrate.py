#!/usr/bin/env python3
"""Dev-only calibration for cobra-claims-review (never uploaded): oracle passes, empty output fails, and each
common misreading of 26 CFR 54.4980B fails at least one test. Each misreading is a small source edit of the
reference solution. Needs a writable /app."""
import csv
import shutil
import subprocess
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TASK = ROOT / "tasks" / "cobra-claims-review"
OUT = Path("/app/output/claim_determinations.csv")
SRC = (TASK / "solution" / "solve.py").read_text()
OPENS = 'opens = max(start_day, day(e["election_notice_date"]))'
DIS = 'within_first_60 = day(ssa["disabled_since"]) <= start_day + timedelta(days=59)'
TOLD = 'told <= day(ssa["determination_date"]) + timedelta(days=60)'
PCT = "percent = 150 if p in disabled and start + 18 <= k <= start + 28 else 102"
SHORT = "if gap > 5000 or gap * 10 > owed:"
DEAD = "deadline = max(first_day(k) + timedelta(days=30), elected + timedelta(days=45))"
EARLY = "if begins and begins > elected:"

SHORTCUTS = {
    # ---- start of coverage and maximum periods (54.4980B-7 Q/A-4)
    "period counted from the month of the event": [("start = month_index(qe_day) + 1", "start = month_index(qe_day)")],
    "18 months for every qualifying event": [("months = 36 if not short_period", "months = 18 if not short_period")],
    "reduction of hours then termination restarts the period": [
        ("qe = evs[0]", "qe = [e for e in evs if e['event'] in ('termination', 'reduction_of_hours', 'death', 'divorce', 'child_reaches_26')][-1] if evs[0]['event'] == 'reduction_of_hours' else evs[0]")],
    # ---- election (54.4980B-6)
    "election period from the notice only": [(OPENS, 'opens = day(e["election_notice_date"])')],
    "election period from the qualifying event": [(OPENS, 'opens = max(qe_day, day(e["election_notice_date"]))')],
    "election period 59 days": [("return day(e[\"elected_on\"]) <= opens + timedelta(days=60)",
                                 "return day(e[\"elected_on\"]) <= opens + timedelta(days=59)")],
    "election period 61 days": [("return day(e[\"elected_on\"]) <= opens + timedelta(days=60)",
                                 "return day(e[\"elected_on\"]) <= opens + timedelta(days=61)")],
    "election not retroactive": [('"yes" if span and span[0] <= k <= span[1] else "no"',
                                  '"yes" if span and span[0] <= k <= span[1] and c["date_of_service"] >= elections[c["person_id"]]["elected_on"] else "no"')],
    # ---- disability extension (54.4980B-7 Q/A-5, 54.4980B-8 Q/A-1)
    "disability extension ignored": [("months = 36 if not short_period else (29 if disabled else 18)",
                                      "months = 36 if not short_period else 18")],
    "first 60 days counted from the qualifying event": [(DIS, 'within_first_60 = day(ssa["disabled_since"]) <= qe_day + timedelta(days=59)')],
    "first 60 days means fewer than 60": [(DIS, 'within_first_60 = day(ssa["disabled_since"]) <= start_day + timedelta(days=58)')],
    "onset must be after COBRA began": [(DIS, 'within_first_60 = start_day <= day(ssa["disabled_since"]) <= start_day + timedelta(days=59)')],
    "disability notice deadline ignored": [(TOLD, "True")],
    "disability notice within 30 days": [(TOLD, 'told <= day(ssa["determination_date"]) + timedelta(days=30)')],
    "disability notice after 18 months allowed": [("and told <= last_day(start + 17)", "")],
    "extension only for the disabled person": [("final = start + months - 1",
                                                "final = start + (18 if months == 29 and p not in disabled else months) - 1")],
    "no 150% premium": [(PCT, "percent = 102")],
    "150% for the whole family": [(PCT, "percent = 150 if disabled and start + 18 <= k <= start + 28 else 102")],
    "150% from month 18": [(PCT, "percent = 150 if p in disabled and start + 17 <= k <= start + 28 else 102")],
    # ---- second qualifying events (54.4980B-7 Q/A-6)
    "second events ignored": [("final = max(final, start + 35)", "pass")],
    "second-event notice not required": [("told and told <= when + timedelta(days=60)", "True")],
    "second-event notice 30 days": [("told and told <= when + timedelta(days=60)", "told and told <= when + timedelta(days=30)")],
    "36 months counted from the second event": [("final = max(final, start + 35)", "final = max(final, month_index(when) + 36)")],
    "second event window is always 18 months": [("window_end = last_day(final)", "window_end = last_day(start + 17)")],
    "employee Medicare is a second event": [('"spouse": {"death", "divorce"}, "child": {"death", "child_reaches_26"}',
                                             '"spouse": {"death", "divorce", "employee_medicare_entitlement"}, "child": {"death", "child_reaches_26", "employee_medicare_entitlement"}')],
    "divorce extends the children": [('"child": {"death", "child_reaches_26"}', '"child": {"death", "child_reaches_26", "divorce"}')],
    "death extends only the spouse": [('"child": {"death", "child_reaches_26"}', '"child": {"child_reaches_26"}')],
    "termination after reduction of hours is a second event": [('"spouse": {"death", "divorce"}', '"spouse": {"death", "divorce", "termination"}')],
    # ---- Medicare before a termination (54.4980B-7 Q/A-7)
    "Medicare-before rule ignored": [("if medicare and medicare < qe_day:", "if False:")],
    "Medicare-before: 36 months from the qualifying event": [("final = max(final, month_index(medicare) + 35)", "final = max(final, start + 35)")],
    "Medicare-before: 36 months after the Medicare month": [("final = max(final, month_index(medicare) + 35)", "final = max(final, month_index(medicare) + 36)")],
    # ---- early termination (54.4980B-7 Q/A-1, Q/A-2, Q/A-3)
    "early termination ignored": [("final = min(final, month_index(begins) - 1)", "pass")],
    "other coverage before the election still ends COBRA": [(EARLY, "if begins:")],
    "coverage through the month other coverage begins": [("final = min(final, month_index(begins) - 1)", "final = min(final, month_index(begins))")],
    "Medicare ends the employee's COBRA only, others too": [
        ('for key in ("other_group_health_coverage_start", "medicare_entitlement_date"):\n                begins = day(people[p][key])',
         'for key in ("other_group_health_coverage_start", "medicare_entitlement_date"):\n                begins = day(people[p][key]) or (day(people[employee][key]) if key == "medicare_entitlement_date" else None)')],
    # ---- premiums (54.4980B-8)
    "no 45-day first payment period": [(DEAD, "deadline = first_day(k) + timedelta(days=30)")],
    "45 days from the election notice": [(DEAD, 'deadline = max(first_day(k) + timedelta(days=30), day(elections[p]["election_notice_date"]) + timedelta(days=45))')],
    "first payment period 44 days": [(DEAD, "deadline = max(first_day(k) + timedelta(days=30), elected + timedelta(days=44))")],
    "grace period 29 days": [(DEAD, "deadline = max(first_day(k) + timedelta(days=29), elected + timedelta(days=45))")],
    "grace period 31 days": [(DEAD, "deadline = max(first_day(k) + timedelta(days=31), elected + timedelta(days=45))")],
    "grace period ends with the month": [(DEAD, "deadline = max(last_day(k), elected + timedelta(days=45))")],
    "any shortfall is nonpayment": [(SHORT, "if True:")],
    "shortfall: greater of $50 and 10%": [(SHORT, "if gap > 5000 and gap * 10 > owed:")],
    "shortfall: $50 only": [(SHORT, "if gap > 5000:")],
    "shortfall: 10% only": [(SHORT, "if gap * 10 > owed:")],
    "shortfall notice ignored": [('if pay["shortfall_notice_date"]:', "if False:")],
    "shortfall cure by the grace deadline": [('cured > day(pay["shortfall_notice_date"]) + timedelta(days=30)', "cured > deadline")],
    "shortfall cure 30 days from the payment": [('cured > day(pay["shortfall_notice_date"]) + timedelta(days=30)', 'cured > day(pay["sent_on"]) + timedelta(days=30)')],
    "a missed month loses only that month": [("if pay is None:\n                    break", "if pay is None:\n                    k += 1\n                    continue")],
    "premium of the year COBRA began": [("base = Decimal(rates[option][str(k // 12)])", "base = Decimal(rates[option][str(start // 12)])")],
    "premium at 100%": [("else 102", "else 100")],
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
