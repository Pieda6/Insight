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
    # ---- effective dates (3.400) and payment start (3.31)
    "paid from the month the award takes effect": [
        ("first_paid = (award_start.year + award_start.month // 12, award_start.month % 12 + 1)", "first_paid = (award_start.year, award_start.month)"),
        ("prior_end = date(y, m, 1) - timedelta(days=1)", "prior_end = month_end(y, m)")],
    "changes paid from their own month": [("prior_end = date(y, m, 1) - timedelta(days=1)", "prior_end = month_end(y, m)")],
    "original claim always effective on receipt": [
        ("effective = separated + timedelta(days=1) if received <= anniversary(separated) else max(received, shown)", "effective = max(received, shown)")],
    "original claim within a year: effective on the day of separation": [
        ("effective = separated + timedelta(days=1) if received", "effective = separated if received")],
    "increase always effective on the claim date": [
        ("elif anniversary(shown) >= received:  # 3.400(o)(2): increase shown within the year before\n                    effective = shown",
         "elif False:\n                    effective = shown")],
    "increase effective when first shown, however early": [("elif anniversary(shown) >= received:", "elif True:")],
    "increase effective on the claim date even when shown later": [
        ("elif shown > received:                # 3.400(o): entitlement arose after the claim\n                    effective = shown",
         "elif shown > received:\n                    effective = received")],
    # ---- combined ratings (4.25) and the bilateral factor (4.26)
    "ratings added instead of combined": [("exact = total + v * (100 - total) / 100", "exact = min(100, total + v)")],
    "final value rounded down": [("return (value + 5) // 10 * 10", "return value // 10 * 10")],
    "5 rounds down": [("return (value + 5) // 10 * 10", "return (value + 4) // 10 * 10")],
    "no bilateral factor": [('if {r[2] for r in group} == {"left", "right"}:', "if False:")],
    "bilateral factor combined instead of added": [("rest.append((value * 11 + 5) // 10)", "rest.append(table_combine([value, 10]))")],
    "bilateral factor for any arm and leg": [
        ('for limb in ("arm", "leg"):\n        group = [r for r in comp if r[1] == limb]',
         'for limb in ("limb",):\n        group = [r for r in comp if r[1] is not None]')],
    "bilateral factor counts a 0% side": [("comp = [r for r in ratings if r[0] > 0]", "comp = list(ratings)")],
    "bilateral factor only for the same joint": [
        ('if {r[2] for r in group} == {"left", "right"}:', 'if {r[2] for r in group} == {"left", "right"} and len({r[3] for r in group}) == 1:'),
        ('return combined([(pct,) + limb_of(disabilities[did]["description"]) for did, pct in current.items()]) if current else 0',
         'return combined([(pct,) + limb_of(disabilities[did]["description"]) + (disabilities[did]["diagnostic_code"],) for did, pct in current.items()]) if current else 0')],
    "nerve disabilities not part of a limb": [('"foot", "lower extremity"', '"foot"'), ('"upper extremity", "hand"', '"hand"')],
    # ---- dependents (3.4(b)(2), 3.401(b))
    "dependents paid below 30%": [("if pct < 30 or not (spouse or kids):", "if not (spouse or kids):")],
    "dependents always from the event": [("basis = event if told <= anniversary(event) else told", "basis = event")],
    "dependents always from the report": [("basis = event if told <= anniversary(event) else told", "basis = told")],
    "dependents from their own month, not the next": [
        ('spouse = any(rel == "spouse" and e <= prior_end for e, rel in dep_from)', 'spouse = any(rel == "spouse" and e <= month_end(y, m) for e, rel in dep_from)'),
        ('kids = sum(1 for e, rel in dep_from if rel == "child" and e <= prior_end)', 'kids = sum(1 for e, rel in dep_from if rel == "child" and e <= month_end(y, m))')],
    "every child at the one-child rate": [('(kids - 1) * rates["each_additional_child"]', "0")],
    # ---- rates and separation pay (3.700)
    "rates by calendar year, not from December 1": [("if eff <= date(y, m, 1)][-1]", "if eff.year < y][-1]")],
    "separation pay recovered in full, tax ignored": [
        ('owed = pay["gross_cents"] - pay["federal_income_tax_withheld_cents"] if pay else 0', 'owed = pay["gross_cents"] if pay else 0')],
    "separation pay ignored": [("withheld = min(amount, owed)", "withheld = 0")],
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

