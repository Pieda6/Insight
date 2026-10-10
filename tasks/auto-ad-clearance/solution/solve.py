#!/usr/bin/env python3
"""Reference solution: clear auto financing ads under Regulation Z (12 CFR Part 1026).

For each ad's offer: classify every worksheet charge under 12 CFR 1026.4 and its commentary,
compute the amount financed (1026.18(b)) and finance charge (total of payments minus amount
financed), solve the Appendix J actuarial equation for the APR, judge the ad's stated rate under the
1026.22(a) tolerance, and check 1026.24(c), (d) and (g) for the ad copy.
"""
import csv
import json
import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, getcontext
from pathlib import Path

getcontext().prec = 40
DATA = Path("/app/data")
OUT = Path("/app/output")
TOLL_FREE = {"800", "888", "877", "866", "855", "844", "833"}


def add_months(d, n):
    y, m = divmod(d.month - 1 + n, 12)
    return date(d.year + y, m + 1, d.day)


def insurance_excluded(c, n_payments):
    """1026.4(d)(1) credit insurance / (d)(3) debt cancellation (GAP)."""
    term_ok = c["coverage_term_months"] == "full contract term" or c["coverage_term_disclosed"]
    return (not c["required_by_creditor"] and c["not_required_disclosed_in_writing"]
            and c["premium_disclosed_in_writing"] and term_ok
            and c["signed_affirmative_request_after_disclosures"])


def finance_charge_part(c, n_payments):
    k, a = c["kind"], c["amount"]
    if k in ("sales_tax", "title_and_registration"):
        return 0 if c["cash_buyers_pay_same"] else a                 # comment 4(a)-1.i.A
    if k == "documentation_fee":
        return max(0, a - c["amount_charged_to_cash_buyers"])        # comment 4(a)-1.iii
    if k in ("lender_acquisition_fee", "credit_processing_fee", "lender_required_inspection"):
        return a                                                     # 4(b)(3), 4(a)(1)(i)
    if k == "lien_recording_fee":                                    # 4(e)(1), comment 4(e)-1
        public = "public official" in c["paid_to"]
        return 0 if public and c["itemized_and_disclosed"] else a
    if k == "nonfiling_insurance":                                   # 4(e)(2), comment 4(e)-4
        return max(0, a - c["filing_fees_otherwise_payable"]) if c["itemized_and_disclosed"] else a
    if k == "service_contract":                                      # comment 4(a)-1.i.D / ii.C
        return 0 if (c["sold_to_cash_buyers_at_same_price"] and not c["required_by_creditor"]) else a
    if k == "credit_application_fee":                                # 4(c)(1)
        return 0 if c["charged_to_all_applicants"] else a
    if k in ("credit_life_insurance", "gap_waiver"):
        return 0 if insurance_excluded(c, n_payments) else a
    if k == "physical_damage_insurance":                             # 4(d)(2)
        ok = c["insurer_choice_disclosed"]
        if c["obtained_through_creditor"]:
            ok = ok and c["premium_disclosed"] and (c["coverage_term_months"] == "full contract term"
                                                    or c["coverage_term_disclosed"])
        return 0 if ok else a
    raise ValueError(k)


def unit_periods(contract, first):
    full = 0
    while add_months(first, -(full + 1)) >= contract:
        full += 1
    return full, Decimal((add_months(first, -full) - contract).days) / 30


def apr(af, payments, contract, first):
    m0, f = unit_periods(contract, first)
    af = Decimal(af)

    def pv(i):
        tot, disc = Decimal(0), (1 + f * i) * (1 + i) ** m0
        for p in payments:
            tot += Decimal(p) / disc
            disc *= 1 + i
        return tot

    lo, hi = Decimal(0), Decimal("0.05")
    for _ in range(120):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if pv(mid) > af else (lo, mid)
    return lo * 1200


def analyze(offer):
    pays = [s["amount"] for s in offer["payment_schedule"] for _ in range(s["count"])]
    n = len(pays)
    fc_items = sum(finance_charge_part(c, n) for c in offer["charges"])
    af = offer["cash_price"] - offer["downpayment"] + sum(c["amount"] for c in offer["charges"]) - fc_items
    fc = sum(pays) - af
    rate = apr(af, pays, date.fromisoformat(offer["contract_date"]), date.fromisoformat(offer["first_payment_date"]))
    amounts = {s["amount"] for s in offer["payment_schedule"]}
    irregular = len(amounts) > 1         # irregular payment amounts beyond first/final -> 1026.22(a)(3)
    return dict(af=af, fc=fc, apr=rate, tol=Decimal("0.25") if irregular else Decimal("0.125"), n=n)


RATE = re.compile(r"(\d+\.\d+)% (APR|Annual Percentage Rate|financing|interest)")
PAYMENT = re.compile(r"\$[\d,]+(?:\.\d\d)?(?:/mo| a month| per month)|monthly payments of \$")
PERIOD = re.compile(r"\d+-month financing|Finance for \d+ months|as many as \d+ monthly installments|"
                    r"\d+ monthly payments")
DOWN = re.compile(r"\$(?!0 )[\d,]+(?:\.\d\d)? down|cash required from buyer|(?<![\d.])\d+% financing available")
FC = re.compile(r"total finance charge")
SERIES = re.compile(r"(\d+) monthly payments of \$")


def review(ad, offer, a):
    copy = ad["copy"]
    m = RATE.search(copy)
    labelled = bool(re.search(r"\d% (APR|Annual Percentage Rate)", copy))
    stated = Decimal(m.group(1)) if m else None
    triggered = any(r.search(copy) for r in (PAYMENT, PERIOD, DOWN, FC))
    missing = set()
    if m and not labelled:
        missing.add("apr")                                            # 1026.24(c)
    if offer["rate_may_increase_after_consummation"] and (m or triggered) and "APR may increase" not in copy:
        missing.add("rate_increase")
    if triggered:
        if not labelled:
            missing.add("apr")
        phone = re.search(r"Call (?:1-)?(\d{3})-\d{3}-\d{4} for details about credit costs and terms", copy)
        alternative = ad["medium"] in ("radio", "tv") and phone and phone.group(1) in TOLL_FREE
        if not alternative:
            if offer["downpayment"] > 0 and not DOWN.search(copy):
                missing.add("downpayment")
            covered = sum(int(x) for x in SERIES.findall(copy) if not re.search(rf"First {x} monthly", copy))
            if covered != a["n"]:
                missing.add("repayment_terms")
    if stated is None:
        acc = "n/a"
    else:
        acc = "true" if abs(stated - a["apr"]) <= a["tol"] else "false"
    miss = ";".join(sorted(missing)) or "none"
    return acc, miss, "true" if acc != "false" and miss == "none" else "false"


def main():
    offers = {o["offer_id"]: o for o in json.loads((DATA / "deal_worksheets.json").read_text())}
    cache = {k: analyze(o) for k, o in offers.items()}
    OUT.mkdir(parents=True, exist_ok=True)
    with open(DATA / "ads.csv", newline="") as f, open(OUT / "ad_clearance.csv", "w", newline="") as g:
        w = csv.writer(g, lineterminator="\n")
        w.writerow(["ad_id", "finance_charge", "amount_financed", "apr", "apr_accurate",
                    "missing_disclosures", "cleared"])
        for ad in csv.DictReader(f):
            a = cache[ad["offer_id"]]
            acc, miss, ok = review(ad, offers[ad["offer_id"]], a)
            w.writerow([ad["ad_id"], f"{a['fc'] / 100:.2f}", f"{a['af'] / 100:.2f}",
                        str(a["apr"].quantize(Decimal("0.01"), ROUND_HALF_UP)), acc, miss, ok])


if __name__ == "__main__":
    main()
