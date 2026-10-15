#!/usr/bin/env python3
"""Dev-only calibration for va-compensation-awards (never uploaded): oracle passes, empty output fails, and each
common misreading of 38 CFR Parts 3 and 4 fails at least one test. Each misreading is a small source edit of the
reference solution. Needs a writable /app."""
import csv
import shutil
import subprocess
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TASK = ROOT / "tasks" / "va-compensation-awards"
OUT = Path("/app/output/monthly_payments.csv")
SRC = (TASK / "solution" / "solve.py").read_text()
SHORTCUTS = {
    # ---- effective dates (3.400, 3.110) and payment start (3.31)
    "paid from the month the award takes effect": [("first_paid = following(award_start.year, award_start.month)", "first_paid = (award_start.year, award_start.month)"),
                                                ('if (kind == "up" and when <= before)', 'if (kind == "up" and when <= last_of(y, m))')],
    "increases paid from their own month": [('if (kind == "up" and when <= before)', 'if (kind == "up" and when <= last_of(y, m))')],
    "reductions paid from their own month": [("or (kind == \"down\" and when <= begin)", "or (kind == \"down\" and when <= last_of(y, m) - timedelta(days=31) + timedelta(days=0) if False else when < begin)")],
    "original claim always effective on receipt": [("eff = separated + ONE if received <= anniversary(separated) else max(received, shown)", "eff = max(received, shown)")],
    "one year excludes the anniversary": [("eff = separated + ONE if received <= anniversary(separated)", "eff = separated + ONE if received < anniversary(separated)"),
                                          ("elif shown > received or received <= anniversary(shown):", "elif shown > received or received < anniversary(shown):"),
                                          ("counted.append((max(event if told <= anniversary(event) else told", "counted.append((max(event if told < anniversary(event) else told")],
    "increase always effective on the claim date": [("elif shown > received or received <= anniversary(shown):", "elif shown > received:")],
    "increase effective when first shown, however early": [("elif shown > received or received <= anniversary(shown):", "elif True:")],
    # ---- reductions (3.105(e))
    "reduction effective on the notice date": [('items.append((date(*following(expires.year, expires.month), 1), r["rating_percent"], "down"))',
                                                'items.append((date(*following(expires.year, expires.month), 1) - timedelta(days=0) if False else day(r["notice_of_final_reduction_sent"]), r["rating_percent"], "down"))')],
    "reduction paid lower a month late": [('items.append((date(*following(expires.year, expires.month), 1), r["rating_percent"], "down"))',
                                           'items.append((date(*following(*following(expires.year, expires.month)), 1), r["rating_percent"], "down"))')],
    "reduction treated like an increase (3.31 lag)": [('or (kind == "down" and when <= begin)', 'or (kind == "down" and when <= before - timedelta(days=31))')],
    # ---- combined ratings (4.25) and bilateral factor (4.26)
    "exact arithmetic instead of the table": [("total = v if total is None else (2 * total * 100 + 2 * v * (100 - total) + 100) // 200",
                                              "total = v if total is None else total + v * (100 - total) / 100"),
                                             ("return (table(others) + 5) // 10 * 10", "return int((table(others) + 5) // 10 * 10)"),
                                             ("others.append((v * 11 + 5) // 10)", "others.append(v * 1.1)")],
    "5 rounds down": [("return (table(others) + 5) // 10 * 10", "return (table(others) + 4) // 10 * 10")],
    "no bilateral factor": [("group = (arms if paired_arms else []) + (legs if paired_legs else [])", "group = []")],
    "bilateral factor not rounded before combining": [("others.append((v * 11 + 5) // 10)", "others.append(v * 11 / 10)"),
                                                     ("total = v if total is None else (2 * total * 100 + 2 * v * (100 - total) + 100) // 200",
                                                      "total = v if total is None else int(total + v * (100 - total) / 100 + 0.5)")],
    "bilateral factor combined instead of added": [("others.append((v * 11 + 5) // 10)", "others.append(table([v, 10]))")],
    "two factors for four extremities": [("group = (arms if paired_arms else []) + (legs if paired_legs else [])\n        others = [r[0] for r in kept if r not in group] + [comp[i][0] for i in skip]\n        if group:\n            v = table([r[0] for r in group])\n            others.append((v * 11 + 5) // 10)",
                                          "group = (arms if paired_arms else []) + (legs if paired_legs else [])\n        others = [r[0] for r in kept if r not in group] + [comp[i][0] for i in skip]\n        for g in ([arms] if paired_arms else []) + ([legs] if paired_legs else []):\n            v = table([r[0] for r in g])\n            others.append((v * 11 + 5) // 10)")],
    "no 4.26(d) exclusions": [("for k in range(1, len(limbs) + 1):", "for k in range(1, 1):")],
    "bilateral factor counts a 0% side": [("comp = [r for r in ratings if r[0] > 0]", "comp = list(ratings)")],
    "bilateral factor for any arm and leg": [("paired_arms = {r[2] for r in arms} == {\"left\", \"right\"}", "paired_arms = bool(arms) and bool(legs)"),
                                            ("paired_legs = {r[2] for r in legs} == {\"left\", \"right\"}", "paired_legs = bool(arms) and bool(legs)")],
    "nerve disabilities not part of a limb": [('"foot", "lower extremity"', '"foot"'), ('"upper extremity", "hand"', '"hand"')],
    # ---- temporary totals (4.29, 4.30, 3.31(c)(5))
    "temporary totals ignored": [("totals = [t for t in (temporary_total(s) for s in stays[vid]) if t]", "totals = []")],
    "no same-month exception (3.31(c)(5))": [("or (same and (s.year, s.month) == (y, m))", "")],
    "temporary totals paid from their own month": [("if (s <= before and begin <= e)", "if (s <= last_of(y, m) and begin <= e)")],
    "absences ignored": [("for a in sorted(stay[\"authorized_absences\"], key=lambda a: a[\"first_day_absent\"]):", "for a in []:"),
                         ("    for a in stay[\"authorized_absences\"]:              # 4.29(a)(2)", "    for a in []:")],
    "absence rule of 4.29(a)(1) ignored": [("for a in sorted(stay[\"authorized_absences\"], key=lambda a: a[\"first_day_absent\"]):", "for a in []:")],
    "long absence rule of 4.29(a)(2) ignored": [("    for a in stay[\"authorized_absences\"]:              # 4.29(a)(2)", "    for a in []:")],
    "absences of 8 days already discharge": [("if used + length > 8:", "if used + length >= 8:")],
    "21 days enough for a hospital rating": [("if (released - began).days <= 21:", "if (released - began).days < 15:")],
    "4.29(b) ignored: total from admission": [('admitted, began, out = day(stay["admitted"]), day(stay["treatment_for_this_disability_began"]), day(stay["discharged"])',
                                               'admitted, began, out = day(stay["admitted"]), day(stay["admitted"]), day(stay["discharged"])')],
    "convalescence months ignored": [("    for _ in range(extra):                             # 4.29(e)", "    for _ in range(0):")],
    "4.30 months counted from the release month": [("        y, m = following(out.year, out.month)\n        for _ in range(extra - 1):", "        y, m = out.year, out.month\n        for _ in range(extra - 1):")],
    # ---- dependents (3.4(b)(2), 3.401(b))
    "dependents paid below 30%": [("spouse = pct >= 30 and any(", "spouse = any("), ("and e <= before) if pct >= 30 else 0", "and e <= before)")],
    "dependents always from the event": [("counted.append((max(event if told <= anniversary(event) else told, award_start)", "counted.append((max(event, award_start)")],
    "dependents always from the report": [("counted.append((max(event if told <= anniversary(event) else told, award_start)", "counted.append((max(told, award_start)")],
    "every child at the one-child rate": [('(kids - 1) * rates["each_additional_child"]', "0")],
    # ---- rates and separation pay (3.700)
    "rates by calendar year, not from December 1": [("if eff <= first_of(y, m)][-1]", "if eff.year < y][-1]")],
    "separation pay recovered in full, tax ignored": [('owed = pay["gross_cents"] - pay["federal_income_tax_withheld_cents"] if pay else 0', 'owed = pay["gross_cents"] if pay else 0')],
    "recovery counted only from 2023": [("for y, m in months(min(first_paid, FIRST), LAST):", "for y, m in months(max(first_paid, FIRST), LAST):")],
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
    truth = {(r["veteran_id"], r["month"]): r for r in csv.DictReader(open(OUT))}
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
        got = {(r["veteran_id"], r["month"]): r for r in csv.DictReader(open(OUT))}
        wrong = sum(1 for c, v in truth.items() if got.get(c) != v)
        rc, failed = tests()
        ok &= bool(rc)
        fams = [f.split("[")[1].rstrip("]") for f in failed if "family" in f]
        print(f"{'ok ' if rc else '!! PASSES'} {name:58s} wrong={wrong:3d} {fams}")
    run(SRC)
    print("ALL SHORTCUTS FAIL" if ok else "SOME SHORTCUT PASSES")


if __name__ == "__main__":
    main()

