#!/usr/bin/env python3
"""Dev-only calibration for auto-ad-clearance (never uploaded).

oracle == engine == golden, oracle passes, empty output fails, and each common misreading of
Regulation Z (a patched copy of the reference solution) fails at least one test.
"""
import contextlib
import csv
import importlib.util
import re
import shutil
import subprocess
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TASK = ROOT / "tasks" / "auto-ad-clearance"
OUT = Path("/app/output/ad_clearance.csv")


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


S = load("solve", TASK / "solution" / "solve.py")
E = load("engine", TASK / "tests" / "engine.py")
O = {k: getattr(S, k) for k in ("finance_charge_part", "apr", "analyze", "review", "insurance_excluded",
                                "PAYMENT", "PERIOD", "DOWN", "TOLL_FREE", "unit_periods")}


@contextlib.contextmanager
def patched(**kw):
    old = {k: getattr(S, k) for k in kw}
    for k, v in kw.items():
        setattr(S, k, v)
    try:
        yield
    finally:
        for k, v in old.items():
            setattr(S, k, v)


def tests():
    p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                        str(TASK / "tests" / "test_outputs.py")], capture_output=True, text=True)
    return p.returncode, [ln.split("::", 1)[1].split(" ")[0] for ln in p.stdout.splitlines() if ln.startswith("FAILED")]


def fcp(fn):
    return dict(finance_charge_part=fn)


def all_fees_fc(c, n):
    return 0 if c["kind"] in ("sales_tax", "title_and_registration") else c["amount"]


def no_fees_fc(c, n):
    return 0


def optional_insurance_excluded(c, n):
    if c["kind"] in ("credit_life_insurance", "gap_waiver"):
        return 0 if not c["required_by_creditor"] else c["amount"]
    return O["finance_charge_part"](c, n)


def required_property_is_fc(c, n):
    if c["kind"] == "physical_damage_insurance" and c["required_by_creditor"]:
        return c["amount"]
    return O["finance_charge_part"](c, n)


def doc_whole(c, n):
    if c["kind"] == "documentation_fee" and c["amount_charged_to_cash_buyers"] < c["amount"]:
        return c["amount"]
    return O["finance_charge_part"](c, n)


def lien_always_excluded(c, n):
    return 0 if c["kind"] == "lien_recording_fee" else O["finance_charge_part"](c, n)


def nonfiling_whole(c, n):
    return 0 if c["kind"] == "nonfiling_insurance" else O["finance_charge_part"](c, n)


def application_excluded(c, n):
    return 0 if c["kind"] == "credit_application_fee" else O["finance_charge_part"](c, n)


def service_excluded(c, n):
    return 0 if c["kind"] == "service_contract" else O["finance_charge_part"](c, n)


def rate_apr(af, pays, contract, first):
    """Spreadsheet RATE(): ignores the odd first period."""
    return O["apr"](af, pays, contract, S.add_months(contract, 1))


def actual_day_fraction(contract, first):
    full = 0
    while S.add_months(first, -(full + 1)) >= contract:
        full += 1
    back = S.add_months(first, -full)
    prev = S.add_months(back, -1)
    return full, Decimal((back - contract).days) / Decimal((back - prev).days)


def tol_quarter_for_odd(offer):
    a = O["analyze"](offer)
    if offer["contract_date"][8:] != offer["first_payment_date"][8:]:
        a["tol"] = Decimal("0.25")
    return a


def tol_eighth_always(offer):
    a = O["analyze"](offer)
    a["tol"] = Decimal("0.125")
    return a


def tol_quarter_always(offer):
    a = O["analyze"](offer)
    a["tol"] = Decimal("0.25")
    return a


ZERO_DOWN_TRIGGERS = re.compile(r"\$[\d,]+(?:\.\d\d)? down|No down payment|cash required from buyer|"
                                r"(?<![\d.])\d+% financing available")
VAGUE_TRIGGERS = re.compile(O["PAYMENT"].pattern + r"|[Ll]ow monthly payments|[Mm]onthly payment terms")
VAGUE_PERIOD = re.compile(O["PERIOD"].pattern + r"|[Tt]ake years to repay")


def review_with(copy_fn=None, **flags):
    def rv(ad, offer, a):
        ad2 = dict(ad, copy=copy_fn(ad["copy"]) if copy_fn else ad["copy"])
        if flags.get("no_increase"):
            offer = dict(offer, rate_may_increase_after_consummation=False)
        if flags.get("any_medium"):
            ad2["medium"] = "radio"
        if flags.get("no_alternative"):
            ad2["medium"] = "print"
        acc, miss, ok = O["review"](ad2, offer, a)
        if flags.get("any_series") and "monthly payments of" in ad["copy"]:
            miss = ";".join(sorted(set(miss.split(";")) - {"none", "repayment_terms"})) or "none"
            ok = "true" if acc != "false" and miss == "none" else "false"
        if flags.get("label_ok"):
            m = set(miss.split(";")) - {"none"}
            if re.search(r"\d% (financing|interest)", ad["copy"]) and not re.search(r"\d% (APR|Annual)", ad["copy"]):
                trig = any(r.search(ad["copy"]) for r in (O["PAYMENT"], O["PERIOD"], O["DOWN"]))
                if not trig:
                    m.discard("apr")
            miss = ";".join(sorted(m)) or "none"
            ok = "true" if acc != "false" and miss == "none" else "false"
        return acc, miss, ok
    return rv


SHORTCUTS = {
    "every dealer/lender fee is a finance charge": fcp(all_fees_fc),
    "no fee is a finance charge (APR = contract rate)": fcp(no_fees_fc),
    "optional credit insurance/GAP excluded without the written conditions": fcp(optional_insurance_excluded),
    "required physical damage insurance treated as finance charge": fcp(required_property_is_fc),
    "whole doc fee counted when credit buyers pay more": fcp(doc_whole),
    "lien fee always excluded": fcp(lien_always_excluded),
    "non-filing insurance always excluded": fcp(nonfiling_whole),
    "application fee always excluded": fcp(application_excluded),
    "service contract always excluded": fcp(service_excluded),
    "spreadsheet RATE() ignoring the odd first period": dict(apr=rate_apr),
    "odd days divided by actual month length": dict(unit_periods=actual_day_fraction),
    "1/4 point tolerance for an odd first period": dict(analyze=tol_quarter_for_odd),
    "1/8 point tolerance for step payments": dict(analyze=tol_eighth_always),
    "1/4 point tolerance everywhere": dict(analyze=tol_quarter_always),
    "$0 down / no down payment treated as a trigger": dict(DOWN=ZERO_DOWN_TRIGGERS),
    "vague payment phrases treated as triggers": dict(PAYMENT=VAGUE_TRIGGERS, PERIOD=VAGUE_PERIOD),
    "rate stated without the term APR accepted": dict(review=review_with(label_ok=True)),
    "rate-increase disclosure ignored": dict(review=review_with(no_increase=True)),
    "broadcast alternative ignored": dict(review=review_with(no_alternative=True)),
    "broadcast alternative for any medium": dict(review=review_with(any_medium=True)),
    "toll-free number not required for the alternative": dict(TOLL_FREE={"800", "888", "877", "866", "855",
                                                                         "844", "833", "614"}),
    "any stated payment series counts as repayment terms": dict(review=review_with(any_series=True)),
}


def main():
    Path("/app/data").mkdir(parents=True, exist_ok=True)
    for f in Path("/app/data").iterdir():
        f.unlink()
    for f in (TASK / "environment" / "data").iterdir():
        shutil.copy(f, Path("/app/data") / f.name)
    S.main()
    rc, failed = tests()
    print(f"oracle rc={rc} failed={failed}")
    truth = E.expected()
    OUT.unlink()
    print(f"nop rc={tests()[0]} (must be non-zero)")
    ok = True
    for name, patch in SHORTCUTS.items():
        with patched(**patch):
            S.main()
        got = {r["ad_id"]: r for r in csv.DictReader(open(OUT))}
        wrong = sum(1 for a, v in truth.items() if any(got[a][f] != v[f] for f in
                    ("finance_charge", "amount_financed", "apr_accurate", "missing_disclosures", "cleared")))
        rc, failed = tests()
        ok &= bool(rc)
        fams = [f.split("[")[1].rstrip("]") for f in failed if "family" in f]
        print(f"{'ok ' if rc else '!! PASSES'} {name:70s} wrong={wrong:3d} {fams}")
    S.main()
    print("ALL SHORTCUTS FAIL" if ok else "SOME SHORTCUT PASSES")


if __name__ == "__main__":
    main()
