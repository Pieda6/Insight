#!/usr/bin/env python3
"""Dev-only calibration for medicare-inpatient-claims (never uploaded): oracle passes, empty output fails, and each
common misreading of 42 CFR 409 fails at least one test. Each misreading is a small source edit of the reference
solution. Needs a writable /app."""
import csv
import shutil
import subprocess
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TASK = ROOT / "tasks" / "medicare-inpatient-claims"
OUT = Path("/app/output/claim_determinations.csv")
SRC = (TASK / "solution" / "solve.py").read_text()

SHORTCUTS = {
    # ---- day counting and benefit periods (409.60)
    "discharge day counted as a day of care": [("    while x < b:\n        yield x", "    while x <= b:\n        yield x")],
    "benefit period ends after 59 days": [("if idle == 60:", "if idle == 59:")],
    "benefit period ends only after 61 days": [("if idle == 60:", "if idle == 61:")],
    "custodial nursing-facility days keep a period open": [
        ("inpatient = x in hosp or x in skilled", "inpatient = x in hosp or x in snf_day")],
    "history before 2025 ignored": [("    x = first\n", "    x = max(first, date(2025, 1, 1))\n")],
    "days before entitlement treated as covered": [("        if x >= ent:\n", "        if True:\n")],
    # ---- hospital days, reserve days, deductible (409.61, 409.65, 409.82, 409.83)
    "coinsurance from day 60": [('kind = "full" if hosp_used <= 60 else "coins"', 'kind = "full" if hosp_used < 60 else "coins"')],
    "coinsurance from day 62": [('kind = "full" if hosp_used <= 60 else "coins"', 'kind = "full" if hosp_used <= 61 else "coins"')],
    "lifetime reserve days never used": [("lifetime_reserve = 60\n", "lifetime_reserve = 0\n")],
    "lifetime reserve days renewed each period": [
        ("bp, period_no, hosp_used, snf_used, deductible_taken = x, period_no + 1, 0, 0, False",
         "bp, period_no, hosp_used, snf_used, deductible_taken, lifetime_reserve = x, period_no + 1, 0, 0, False, 60")],
    "120 regular days instead of 90 plus reserve": [("if hosp_used < 90:", "if hosp_used < 150:")],
    "amounts of the year the period began": [('amt = amounts.get(str(x.year))', 'amt = amounts.get(str(bp.year)) if bp else None')],
    "amounts of the year of admission": [
        ('amt = amounts.get(str(x.year))',
         'amt = amounts.get(str(d((hosp.get(x) or snf_day.get(x) or {"inpatient_admission_date": str(x)})["inpatient_admission_date"]).year))')],
    "deductible on every claim": [("if not deductible_taken:                            # 409.82(a)\n                        deductible_taken = True",
                                   "if o[\"cov\"] == 1:\n                        deductible_taken = True")],
    "deductible once per calendar year": [("    paid = set()\n", "    paid = set()\n    charged_years = set()\n"),
                                          ("if not deductible_taken:                            # 409.82(a)\n                        deductible_taken = True",
                                           "if x.year not in charged_years:\n                        charged_years.add(x.year)")],
    # ---- skilled nursing facility (409.30, 409.61(b), 409.85)
    "observation days count toward the 3 days": [
        ('los = (d(h["discharge_date"]) - d(h["inpatient_admission_date"])).days',
         'los = (d(h["discharge_date"]) - d(h["outpatient_observation_start_date"] or h["inpatient_admission_date"])).days')],
    "3 days means more than 3": [("return los >= 3 and", "return los > 3 and")],
    "2 days are enough": [("return los >= 3 and", "return los >= 2 and")],
    "30-day window exclusive": [("and wait <= 30", "and wait < 30")],
    "30-day window ignored": [("and wait <= 30", "")],
    "SNF days after skilled care still covered": [("if x in skilled and qual[s[\"stay_id\"]]", "if qual[s[\"stay_id\"]]")],
    "no 100-day limit": [("and snf_used < 100:", ":")],
    "SNF coinsurance from day 20": [("if snf_used > 20 and amt:", "if snf_used >= 20 and amt:")],
    "SNF coinsurance from day 22": [("if snf_used > 20 and amt:", "if snf_used > 21 and amt:")],
    "SNF coinsurance never limited by the facility's charge": [
        ('o["coins"] += min(amt["snf_coinsurance_days_21_100"], snf_rate[s["facility_id"]][str(x.year)])',
         'o["coins"] += amt["snf_coinsurance_days_21_100"]')],
    "SNF coinsurance capped by the charge at the period's first-year rate": [
        ('snf_rate[s["facility_id"]][str(x.year)])', 'snf_rate[s["facility_id"]].get(str(bp.year), snf_rate[s["facility_id"]][str(x.year)]))')],
    "days before entitlement do not count toward the 3 days": [
        ('los = (d(h["discharge_date"]) - d(h["inpatient_admission_date"])).days',
         'los = (d(h["discharge_date"]) - max(d(h["inpatient_admission_date"]), date(turned_65[0], turned_65[1], 1))).days')],
    # ---- psychiatric limits (409.62, 409.63)
    "190-day psychiatric limit ignored": [("allowed = not (psych_hospital and psych_hospital_days >= 190)", "allowed = True")],
    "190-day limit counts general-hospital psychiatric care": [
        ("                    if psych_hospital:\n                        psych_hospital_days += 1",
         "                    if psych:\n                        psych_hospital_days += 1"),
        ("allowed = not (psych_hospital and psych_hospital_days >= 190)", "allowed = not (psych and psych_hospital_days >= 190)")],
    "initial-period reduction ignored": [("cap = 150 - before", "cap = None")],
    "initial-period reduction only for psychiatric hospital days": [
        ("if cap is not None and period_no == 1 and psych and initial_psych >= cap:",
         "if cap is not None and period_no == 1 and psych_hospital and initial_psych >= cap:"),
        ("if cap is not None and period_no == 1 and psych:\n", "if cap is not None and period_no == 1 and psych_hospital:\n")],
    "initial-period limit applied to every period": [
        ("and period_no == 1 and psych and initial_psych >= cap", "and psych and initial_psych >= cap")],
    # ---- blood (409.87)
    "replaced units do not use up the blood deductible": [
        ('            year_units[x.year] += u["units"]', '            year_units[x.year] += 0 if u.get("replaced_or_obtained_free") else u["units"]')],
    "Part B blood ignored": [("    for u in partb:\n        blood[d(u[\"date\"])].append((None, u))", "")],
    "every blood product counts": [('if u["product"] not in ("whole_blood", "packed_red_cells"):', 'if False:')],
    "blood deductible per benefit period": [('year_units[x.year]', 'year_units[bp]')],
    "blood deductible per stay": [('year_units[x.year]', 'year_units[sid]')],
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
