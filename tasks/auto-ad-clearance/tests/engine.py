"""Verifier-side model of Regulation Z ad clearance, written independently of the reference
solution. It reads only the verifier's private copy of the inputs in /tests/data.

Finance charge: 12 CFR 1026.4 with its official interpretations. Amount financed: 1026.18(b).
APR: Appendix J actuarial method, evaluated by rolling the balance forward (fractional first
unit-period at simple interest, then whole months) and bisecting on the periodic rate.
Ads: 1026.24(c), (d)(1)-(2) with comments 24(d)(1)-1..4, 24(d)(2)-1..2, and the (g) alternative.
"""
import csv
import json
import re
from datetime import date
from fractions import Fraction
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
FULL_TERM = "full contract term"


def month_shift(d, k):
    m = d.month - 1 + k
    return d.replace(year=d.year + m // 12, month=m % 12 + 1)


# --------------------------------------------------------------------------- finance charge
def fc_portion(ch):
    kind, amt = ch["kind"], ch["amount"]
    rules = {
        "sales_tax": lambda: 0 if ch["cash_buyers_pay_same"] else amt,
        "title_and_registration": lambda: 0 if ch["cash_buyers_pay_same"] else amt,
        "documentation_fee": lambda: max(amt - ch["amount_charged_to_cash_buyers"], 0),
        "lender_acquisition_fee": lambda: amt,
        "credit_processing_fee": lambda: 0 if ch["charged_to_cash_buyers"] else amt,
        "lender_required_inspection": lambda: amt if ch["required_by_creditor"] else 0,
        "lien_recording_fee": lambda: 0 if (ch["itemized_and_disclosed"]
                                            and "public official" in ch["paid_to"]) else amt,
        "nonfiling_insurance": lambda: (max(amt - ch["filing_fees_otherwise_payable"], 0)
                                        if ch["itemized_and_disclosed"] else amt),
        "service_contract": lambda: amt if (ch["required_by_creditor"]
                                            or not ch["sold_to_cash_buyers_at_same_price"]) else 0,
        "credit_application_fee": lambda: 0 if ch["charged_to_all_applicants"] else amt,
    }
    if kind in rules:
        return rules[kind]()
    shorter = ch["coverage_term_months"] != FULL_TERM
    if kind in ("credit_life_insurance", "gap_waiver"):            # 4(d)(1), 4(d)(3)
        conditions = [not ch["required_by_creditor"], ch["not_required_disclosed_in_writing"],
                      ch["premium_disclosed_in_writing"],
                      (not shorter) or ch["coverage_term_disclosed"],
                      ch["signed_affirmative_request_after_disclosures"]]
        return 0 if all(conditions) else amt
    if kind == "physical_damage_insurance":                         # 4(d)(2)
        conditions = [ch["insurer_choice_disclosed"]]
        if ch["obtained_through_creditor"]:
            conditions += [ch["premium_disclosed"], (not shorter) or ch["coverage_term_disclosed"]]
        return 0 if all(conditions) else amt
    raise KeyError(kind)


# --------------------------------------------------------------------------- APR (Appendix J)
def first_period(start, first_due):
    whole = 0
    while month_shift(first_due, -(whole + 1)) >= start:
        whole += 1
    days = (month_shift(first_due, -whole) - start).days
    return whole, Fraction(days, 30)


def residual(rate, amount_financed, payments, whole, frac):
    """Balance after the last payment when interest accrues at `rate` per month."""
    bal = amount_financed * (1 + frac * rate)
    for _ in range(whole):
        bal *= 1 + rate
    for k, p in enumerate(payments):
        if k:
            bal *= 1 + rate
        bal -= p
    return bal


def solve_apr(amount_financed, payments, start, first_due):
    whole, frac = first_period(start, first_due)
    lo, hi = 0.0, 0.05
    for _ in range(100):
        mid = (lo + hi) / 2
        if residual(mid, amount_financed, payments, whole, frac) > 0:
            hi = mid                       # balance left over: the rate is too high
        else:
            lo = mid
    return 1200 * (lo + hi) / 2


# --------------------------------------------------------------------------- ad copy
TOLL_FREE = ("800", "888", "877", "866", "855", "844", "833")


def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!])\s+", text) if s.strip()]


def classify(sentence):
    s = sentence.lower()
    found = set()
    rate = re.search(r"(\d+\.\d+)%\s+(apr|annual percentage rate|financing|interest)", s)
    if rate:
        found.add("rate")
        if rate.group(2) in ("apr", "annual percentage rate"):
            found.add("apr_term")
    if re.search(r"(?<![\d.])\d{1,2}% financing", s):
        found |= {"trigger", "down_stated"}                          # comment 24(d)-1
    dollars_down = re.search(r"\$([\d,]+(?:\.\d\d)?) down", s)
    if dollars_down and dollars_down.group(1) not in ("0", "0.00"):
        found |= {"trigger", "down_stated"}                          # comment 24(d)(1)-1
    if "cash required from buyer" in s:
        found |= {"trigger", "down_stated"}
    if re.search(r"\$[\d,.]+\s*(/mo\b|a month|per month)", s) or "monthly payments of $" in s:
        found.add("trigger")                                         # comment 24(d)(1)-3
    if re.search(r"\d+-month financing|finance for \d+ months|as many as \d+ monthly", s) or \
            re.search(r"\d+ monthly payments", s):
        found.add("trigger")                                         # comment 24(d)(1)-2
    if "total finance charge" in s:
        found.add("trigger")                                         # comment 24(d)(1)-4
    if "apr may increase" in s:
        found.add("increase_noted")
    return found


def schedule_months_stated(text, schedule):
    """Comment 24(d)(2)-2: repayment terms are the full payment schedule (number and amount)."""
    stated = []
    for count, amount in re.findall(r"(?<!first )(\d+) monthly payments of \$([\d,]+(?:\.\d\d)?)", text, re.I):
        stated.append((int(count), round(float(amount.replace(",", "")) * 100)))
    return sorted(stated) == sorted((s["count"], s["amount"]) for s in schedule)


def expected():
    offers = {o["offer_id"]: o for o in json.loads((DATA / "deal_worksheets.json").read_text())}
    figures = {}
    for oid, o in offers.items():
        payments = [s["amount"] for s in o["payment_schedule"] for _ in range(s["count"])]
        prepaid = sum(fc_portion(c) for c in o["charges"])
        financed = o["cash_price"] - o["downpayment"] + sum(c["amount"] for c in o["charges"]) - prepaid
        rate = solve_apr(financed, payments, date.fromisoformat(o["contract_date"]),
                         date.fromisoformat(o["first_payment_date"]))
        irregular = len({s["amount"] for s in o["payment_schedule"]}) > 1      # 1026.22(a)(3)
        figures[oid] = dict(af=financed, fc=sum(payments) - financed, apr=rate,
                            tol=0.25 if irregular else 0.125)

    out = {}
    with open(DATA / "ads.csv", newline="") as fh:
        for ad in csv.DictReader(fh):
            o, f = offers[ad["offer_id"]], figures[ad["offer_id"]]
            feats = set()
            for s in sentences(ad["copy"]):
                feats |= classify(s)
            stated = re.search(r"(\d+\.\d+)%\s+(?:APR|Annual Percentage Rate|financing|interest)", ad["copy"])
            gaps = []
            if "rate" in feats and "apr_term" not in feats:
                gaps.append("apr")
            if o["rate_may_increase_after_consummation"] and ("rate" in feats or "trigger" in feats) \
                    and "increase_noted" not in feats:
                gaps.append("rate_increase")
            if "trigger" in feats:
                if "apr_term" not in feats and "apr" not in gaps:
                    gaps.append("apr")
                phone = re.search(r"Call (?:1-)?(\d{3})-\d{3}-\d{4} for details about credit costs and terms",
                                  ad["copy"])
                broadcast = ad["medium"] in ("radio", "tv") and phone is not None and phone.group(1) in TOLL_FREE
                if not broadcast:
                    if o["downpayment"] and "down_stated" not in feats:
                        gaps.append("downpayment")
                    if not schedule_months_stated(ad["copy"], o["payment_schedule"]):
                        gaps.append("repayment_terms")
            if stated is None:
                accurate = "n/a"
            else:
                accurate = "true" if abs(float(stated.group(1)) - f["apr"]) <= f["tol"] + 1e-9 else "false"
            missing = ";".join(sorted(gaps)) or "none"
            out[ad["ad_id"]] = {
                "finance_charge": f"{f['fc'] / 100:.2f}", "amount_financed": f"{f['af'] / 100:.2f}",
                "apr": f["apr"], "apr_accurate": accurate, "missing_disclosures": missing,
                "cleared": "true" if accurate != "false" and missing == "none" else "false"}
    return out
