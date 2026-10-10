#!/usr/bin/env python3
"""Generate the auto-ad-clearance inputs (dev only, never shipped).

A dealer group's fall sales event: one deal worksheet per advertised financing offer (cash price,
down payment, itemized charges with the facts that decide their Regulation Z treatment, payment
schedule, dates) and the ads that promote them (print, web, mailer, radio, TV copy).
Planted cases cover each charge type on both sides of its exclusion test, odd first periods,
step-payment schedules, stated rates near each tolerance, trigger and non-trigger phrases, and the
broadcast alternative. Writes environment/data/*, a tests/data copy, tests/case_tags.json and
tests/golden.json (expected outcome for planted ads, derived from the scenario intent).
"""
import csv
import json
import random
import shutil
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "tasks" / "auto-ad-clearance"
ENV, TST = ROOT / "environment" / "data", ROOT / "tests" / "data"
rng = random.Random(1026)

STORES = ["Riverbend Motors North", "Riverbend Motors Eastgate", "Riverbend Truck Center",
          "Riverbend Pre-Owned Outlet"]
MODELS = ["Corvan LX", "Corvan Sport", "Halden SUV", "Halden SUV Hybrid", "Pike 1500 Crew Cab",
          "Pike 2500 Work Truck", "Astra Compact", "Astra Compact SE", "Marlow Minivan", "Kestrel EV"]
REG, STEP = 0.125, 0.25


def add_months(d, n):
    y, m = divmod(d.month - 1 + n, 12)
    return date(d.year + y, m + 1, d.day)


def periods(contract, first_pay):
    """Appendix J (b)(5)(ii): full months measured back from first payment, remaining days / 30."""
    full, back = 0, first_pay
    while add_months(first_pay, -(full + 1)) >= contract:
        full += 1
    back = add_months(first_pay, -full)
    return full, (back - contract).days / 30


def apr_of(af, pays, contract, first_pay):
    """Newton iteration on the Appendix J single-advance equation (generator's own solver)."""
    m0, f = periods(contract, first_pay)
    i = 0.005
    for _ in range(200):
        pv = d = 0.0
        for k, p in enumerate(pays):
            t = m0 + k
            den = (1 + f * i) * (1 + i) ** t
            pv += p / den
            d += -p * (f / (1 + f * i) + t / (1 + i)) / den
        step = (pv - af) / d
        i -= step
        if abs(step) < 1e-15:
            break
    return 1200 * i


def rate_apr(af, pays):
    """Spreadsheet RATE(): level payments one month apart, first one a month after consummation."""
    lo, hi = 0.0, 0.05
    for _ in range(200):
        mid = (lo + hi) / 2
        pv = sum(p / (1 + mid) ** (k + 1) for k, p in enumerate(pays))
        lo, hi = (mid, hi) if pv > af else (lo, mid)
    return 1200 * lo


def level_payment(principal, rate_pct, n):
    r = rate_pct / 1200
    return principal / n if r == 0 else principal * r / (1 - (1 + r) ** -n)


def cents(x):
    return int(round(x))


class Charge:
    """A worksheet charge plus the finance-charge portion the scenario intends (generator truth)."""

    def __init__(self, rec, fc_part, tag):
        self.rec, self.fc_part, self.tag = rec, fc_part, tag


def make_charges(price, n, plant=None):
    out = []
    tax = cents(price * rng.choice([0.0575, 0.0625, 0.07, 0.0725]))
    out.append(Charge({"kind": "sales_tax", "amount": tax, "cash_buyers_pay_same": True}, 0, "fc-tax"))
    out.append(Charge({"kind": "title_and_registration", "amount": rng.choice([18900, 24650, 31200]),
                       "cash_buyers_pay_same": True}, 0, "fc-title"))
    doc = rng.choice([49900, 59900, 69900])
    if plant == "doc-higher" or (plant is None and rng.random() < 0.25):
        cash = doc - rng.choice([10000, 15000, 20000])
        out.append(Charge({"kind": "documentation_fee", "amount": doc, "amount_charged_to_cash_buyers": cash},
                          doc - cash, "fc-doc-difference"))
    elif plant == "doc-cash-none":
        out.append(Charge({"kind": "documentation_fee", "amount": doc, "amount_charged_to_cash_buyers": 0},
                          doc, "fc-doc-credit-only"))
    else:
        out.append(Charge({"kind": "documentation_fee", "amount": doc, "amount_charged_to_cash_buyers": doc},
                          0, "fc-doc-same"))
    kinds = [plant] if plant and not plant.startswith("doc") else []
    if plant is None:
        kinds = rng.sample(["acq", "lien", "svc", "life", "gap", "phys", "app", "nonfiling", "insp",
                            "proc"], rng.randint(1, 4))
    for k in kinds:
        out.extend(extra_charge(k, n))
    return out


def ins_record(kind, premium, n, ok, why=None):
    shorter = [m for m in (12, 24) if m < n - 6]
    term = "full contract term" if rng.random() < 0.6 or not shorter else rng.choice(shorter)
    rec = {"kind": kind, "amount": premium, "required_by_creditor": False,
           "not_required_disclosed_in_writing": True, "premium_disclosed_in_writing": True,
           "coverage_term_months": term, "coverage_term_disclosed": True,
           "signed_affirmative_request_after_disclosures": True}
    if not ok:
        why = why or rng.choice(["required", "not_disclosed", "premium", "term", "unsigned"])
        if why == "term":
            rec["coverage_term_months"] = 12
            rec["coverage_term_disclosed"] = False
        else:
            rec[{"required": "required_by_creditor", "not_disclosed": "not_required_disclosed_in_writing",
                 "premium": "premium_disclosed_in_writing",
                 "unsigned": "signed_affirmative_request_after_disclosures"}[why]] = (why == "required")
    elif rec["coverage_term_months"] == "full contract term" and rng.random() < 0.5:
        rec["coverage_term_disclosed"] = False        # not needed when coverage runs the full term
    return rec, why


def extra_charge(k, n):
    ok = rng.random() < 0.5
    if k.endswith("-ok"):
        k, ok = k[:-3], True
    elif k.endswith("-bad"):
        k, ok = k[:-4], False
    if k == "acq":
        a = rng.choice([59500, 69500, 79500, 89500])
        return [Charge({"kind": "lender_acquisition_fee", "amount": a}, a, "fc-acquisition")]
    if k == "proc":
        a = rng.choice([19900, 29900, 34900])
        return [Charge({"kind": "credit_processing_fee", "amount": a, "charged_to_cash_buyers": False},
                       a, "fc-credit-processing")]
    if k == "insp":
        a = rng.choice([8900, 12500])
        return [Charge({"kind": "lender_required_inspection", "amount": a, "provider": "independent inspection firm",
                        "required_by_creditor": True, "charged_to_cash_buyers": False}, a, "fc-required-third-party")]
    if k == "lien":
        a = rng.choice([1500, 2300, 3300])
        if ok:
            rec = {"kind": "lien_recording_fee", "amount": a, "paid_to": "state motor vehicle agency (public official)",
                   "itemized_and_disclosed": True}
            return [Charge(rec, 0, "fc-lien-excluded")]
        if rng.random() < 0.5:
            rec = {"kind": "lien_recording_fee", "amount": a + 4500,
                   "paid_to": "electronic lien service vendor (private company)", "itemized_and_disclosed": True}
            return [Charge(rec, a + 4500, "fc-lien-vendor")]
        rec = {"kind": "lien_recording_fee", "amount": a, "paid_to": "state motor vehicle agency (public official)",
               "itemized_and_disclosed": False}
        return [Charge(rec, a, "fc-lien-not-itemized")]
    if k == "nonfiling":
        prem, fees = rng.choice([(2500, 1800), (3000, 3300), (4500, 2000)])
        rec = {"kind": "nonfiling_insurance", "amount": prem, "filing_fees_otherwise_payable": fees,
               "itemized_and_disclosed": True}
        return [Charge(rec, max(0, prem - fees), "fc-nonfiling")]
    if k == "svc":
        a = rng.choice([149500, 189500, 229500])
        if ok:
            rec = {"kind": "service_contract", "amount": a, "required_by_creditor": False,
                   "sold_to_cash_buyers_at_same_price": True}
            return [Charge(rec, 0, "fc-service-optional")]
        rec = {"kind": "service_contract", "amount": a, "required_by_creditor": True,
               "sold_to_cash_buyers_at_same_price": False}
        return [Charge(rec, a, "fc-service-required")]
    if k == "app":
        a = rng.choice([5000, 7500, 9900])
        rec = {"kind": "credit_application_fee", "amount": a, "charged_to_all_applicants": ok}
        return [Charge(rec, 0 if ok else a, "fc-application-" + ("all" if ok else "approved-only"))]
    if k in ("life", "gap"):
        prem = rng.choice([39500, 49500, 59500, 69500, 79500])
        kind = "credit_life_insurance" if k == "life" else "gap_waiver"
        rec, why = ins_record(kind, prem, n, ok)
        return [Charge(rec, 0 if ok else prem, f"fc-{k}-" + ("excluded" if ok else why))]
    if k == "phys":
        prem = rng.choice([89500, 112000, 134500])
        rec = {"kind": "physical_damage_insurance", "amount": prem, "obtained_through_creditor": True,
               "required_by_creditor": rng.random() < 0.7, "insurer_choice_disclosed": True,
               "premium_disclosed": True, "coverage_term_months": 12, "coverage_term_disclosed": True}
        if not ok:
            why = rng.choice(["insurer_choice_disclosed", "premium_disclosed", "coverage_term_disclosed"])
            rec[why] = False
            return [Charge(rec, prem, "fc-property-" + why)]
        return [Charge(rec, 0, "fc-property-excluded" + ("-required" if rec["required_by_creditor"] else ""))]
    raise ValueError(k)


def build_offer(i, plant=None, step=False, variable=False, n=None, first_gap=None, rate=None):
    price = rng.randrange(1800000, 5200000, 5000)
    n = n or rng.choice([36, 48, 60, 60, 72, 72, 84])
    down = 0 if rng.random() < 0.2 else rng.randrange(100000, 600000, 25000)
    rate = rate if rate is not None else rng.choice([0.9, 1.9, 2.9, 3.9, 4.9, 5.9, 6.9, 7.9, 8.9, 9.9])
    contract = date(2026, 10, 1) + timedelta(days=rng.randint(0, 28))
    gap = first_gap or rng.choice([16, 21, 25, 30, 30, 34, 38, 41, 45, 52])
    first = contract + timedelta(days=gap)
    if first.day > 28:
        first = first.replace(day=28)
    charges = make_charges(price, n, plant)
    note = price - down + sum(c.rec["amount"] for c in charges)
    if step:
        lvl = level_payment(note, rate, n)
        p1 = cents(lvl * 0.82)
        r = rate / 1200
        pv1 = sum(p1 / (1 + r) ** (k + 1) for k in range(12))
        rem = note - pv1
        p2 = cents(level_payment(rem * (1 + r) ** 12, rate, n - 12)) if r else cents(rem / (n - 12))
        schedule = [{"count": 12, "amount": p1}, {"count": n - 12, "amount": p2}]
    else:
        schedule = [{"count": n, "amount": cents(level_payment(note, rate, n))}]
    pays = [s["amount"] for s in schedule for _ in range(s["count"])]
    fc_items = sum(c.fc_part for c in charges)
    af = note - fc_items
    fc = sum(pays) - af
    offer = {"offer_id": f"OF{i:03d}", "store": rng.choice(STORES), "vehicle": f"2026 {rng.choice(MODELS)}",
             "cash_price": price, "downpayment": down, "contract_rate_percent": rate,
             "rate_may_increase_after_consummation": variable, "contract_date": contract.isoformat(),
             "first_payment_date": first.isoformat(), "payment_frequency": "monthly",
             "payment_schedule": schedule, "charges": [c.rec for c in charges]}
    truth = {"af": af, "fc": fc, "apr": apr_of(af, pays, contract, first),
             "rate_apr": rate_apr(af, pays), "tol": STEP if step else REG, "step": step,
             "variable": variable, "tags": sorted({c.tag for c in charges if c.tag not in ("fc-tax", "fc-title")}),
             "pays": pays, "n": n, "down": down, "note_rate": rate}
    return offer, truth


def money(c):
    return f"${c / 100:,.2f}" if c % 100 else f"${c // 100:,}"


def pick_stated(t, want_ok, avoid_rate_shortcut=False):
    """A stated rate (1 or 2 decimals) whose accuracy is unambiguous (>= 0.02 from the boundary)."""
    true, tol = t["apr"], t["tol"]
    cands = []
    for d in (1, 2):
        step = 10 ** -d
        base = round(true, d)
        for k in range(-60, 61):
            s = round(base + k * step, d)
            if s <= 0:
                continue
            diff = abs(s - true)
            if abs(diff - tol) < 0.02:
                continue
            if (diff <= tol) != want_ok:
                continue
            if avoid_rate_shortcut is not None and avoid_rate_shortcut:
                rdiff = abs(s - t["rate_apr"])
                if abs(rdiff - tol) < 0.02 or (rdiff <= tol) == want_ok:
                    continue
            cands.append((abs(diff - tol), d, s))
    if not cands:
        return None
    cands.sort()
    best = cands[: max(1, len(cands) // 3)]
    _, d, s = rng.choice(best)
    return f"{s:.{d}f}"


def ad_copy(offer, t, spec):
    """spec keys: rate (None|'apr'|'apr_long'|'financing'|'interest'), stated, triggers [..], disclose {..},
    nontrigger [..], medium, phone (None|'tollfree_ref'|'tollfree_noref'|'local_ref'), variable_note"""
    parts = [f"{offer['store']}: Drive home the {offer['vehicle']}!"]
    sched = offer["payment_schedule"]
    p1 = sched[0]["amount"]
    for nt in spec.get("nontrigger", []):
        parts.append({"low": "Low monthly payments!", "years": "Take years to repay.",
                      "arranged": "Monthly payment terms arranged.", "zero_down": "$0 down!",
                      "no_down": "No down payment required.", "easy": "Easy financing for every budget."}[nt])
    r = spec.get("rate")
    if r:
        s = spec["stated"]
        parts.append({"apr": f"Just {s}% APR financing.", "apr_long": f"{s}% Annual Percentage Rate.",
                      "financing": f"{s}% financing available.", "interest": f"Only {s}% interest!"}[r])
    for tr in spec.get("triggers", []):
        if tr == "payment":
            parts.append(rng.choice([f"Only {money(p1)}/mo!", f"Payments as low as {money(p1)} a month.",
                                     f"{money(p1)} per month."]))
        elif tr == "period":
            parts.append(rng.choice([f"{t['n']}-month financing.", f"Finance for {t['n']} months.",
                                     f"Repay in as many as {t['n']} monthly installments."]))
        elif tr == "down":
            parts.append(f"Only {money(t['down'])} down!")
        elif tr == "down_pct":
            pct = round(100 * t["down"] / offer["cash_price"])
            parts.append(f"{100 - pct}% financing available.")
        elif tr == "fc":
            parts.append(f"Just {money(t['fc'])} total finance charge.")
    d = spec.get("disclose", {})
    if d.get("down"):
        if t["down"] == 0:
            parts.append("No down payment required.")
        else:
            parts.append(rng.choice([f"With {money(t['down'])} down.", f"{money(t['down'])} cash required from buyer."]))
    if d.get("repay"):
        if len(sched) == 1:
            parts.append(f"{sched[0]['count']} monthly payments of {money(p1)}.")
        else:
            parts.append(f"{sched[0]['count']} monthly payments of {money(sched[0]['amount'])}, then "
                         f"{sched[1]['count']} monthly payments of {money(sched[1]['amount'])}.")
    if d.get("repay_partial"):
        parts.append(f"First {sched[0]['count']} monthly payments of {money(sched[0]['amount'])}.")
    if d.get("apr_text"):
        parts.append(f"{spec['stated']}% APR.")
    if spec.get("variable_note"):
        parts.append("APR may increase after consummation.")
    ph = spec.get("phone")
    if ph:
        num = {"tollfree_ref": "1-800-555-0142", "tollfree_noref": "1-888-555-0177",
               "local_ref": "614-555-0199"}[ph]
        parts.append(f"Call {num} for details about credit costs and terms." if ph != "tollfree_noref"
                     else f"Call {num} today!")
    parts.append("With approved credit. Offer ends 10/31/2026.")
    return " ".join(parts)


def expected(offer, t, spec):
    """Scenario intent -> (apr_accurate, missing, cleared)."""
    rate = spec.get("rate")
    triggers = spec.get("triggers", [])
    d = spec.get("disclose", {})
    if rate:
        acc = "true" if abs(float(spec["stated"]) - t["apr"]) <= t["tol"] else "false"
    else:
        acc = "n/a"
    labelled = rate in ("apr", "apr_long") or d.get("apr_text")
    missing = set()
    if rate in ("financing", "interest") and not d.get("apr_text"):
        missing.add("apr")
    if t["variable"] and (rate or triggers) and not spec.get("variable_note"):
        missing.add("rate_increase")
    if triggers:
        broadcast_alt = spec["medium"] in ("radio", "tv") and spec.get("phone") == "tollfree_ref"
        if not labelled:
            missing.add("apr")
        if not broadcast_alt:
            if t["down"] > 0 and not (d.get("down") or "down" in triggers):
                missing.add("downpayment")
            if not d.get("repay"):
                missing.add("repayment_terms")
    miss = ";".join(sorted(missing)) or "none"
    return acc, miss, "true" if acc != "false" and miss == "none" else "false"


def main():
    offers, truths, ads, tags, golden = [], {}, [], {}, {}
    n_ad = 0

    def add_ad(offer, t, spec, extra_tags, gold=True):
        nonlocal n_ad
        n_ad += 1
        aid = f"AD{n_ad:03d}"
        if spec.get("rate") or spec.get("disclose", {}).get("apr_text"):
            if "stated" not in spec:
                spec["stated"] = pick_stated(t, spec.pop("want_ok", True))
        medium = spec.setdefault("medium", rng.choice(["print", "web_banner", "direct_mail"]))
        ads.append({"ad_id": aid, "offer_id": offer["offer_id"], "medium": medium,
                    "copy": ad_copy(offer, t, spec)})
        tags[aid] = sorted(set(extra_tags) | set(t["tags"]) | ({"step-payments"} if t["step"] else set()))
        if gold:
            acc, miss, ok = expected(offer, t, spec)
            golden[aid] = {"finance_charge": f"{t['fc'] / 100:.2f}", "amount_financed": f"{t['af'] / 100:.2f}",
                           "apr_accurate": acc, "missing_disclosures": miss, "cleared": ok}
        return aid

    def new_offer(**kw):
        offer, t = build_offer(len(offers) + 1, **kw)
        offers.append(offer)
        truths[offer["offer_id"]] = t
        return offer, t

    full = {"down": True, "repay": True}
    # --- finance charge classification: each charge type on both sides, APR-only ads ----------
    plants = ["doc-higher", "doc-cash-none", "acq", "proc", "insp", "lien-ok", "lien-bad", "lien-bad",
              "nonfiling", "nonfiling", "svc-ok", "svc-bad", "app-ok", "app-bad", "life-ok", "life-bad",
              "life-bad", "gap-ok", "gap-bad", "gap-bad", "phys-ok", "phys-ok", "phys-bad", "phys-bad"]
    for p in plants:
        offer, t = new_offer(plant=p)
        add_ad(offer, t, {"rate": "apr", "want_ok": rng.random() < 0.5}, ["finance-charge"])
    # contract rate advertised as APR although finance-charge items push the APR up
    for p in ["acq", "life-bad", "gap-bad", "svc-bad", "doc-higher", "proc"]:
        offer, t = new_offer(plant=p, n=rng.choice([36, 48]))
        s = f"{t['note_rate']:.1f}"
        if abs(abs(float(s) - t["apr"]) - t["tol"]) >= 0.02:
            add_ad(offer, t, {"rate": "apr", "stated": s}, ["finance-charge", "contract-rate-as-apr"])
    # --- odd first period: Appendix J vs spreadsheet RATE() ------------------------------------
    made = 0
    while made < 10:
        gap = rng.choice([15, 16, 17, 18, 50, 52, 54, 55])
        offer, t = new_offer(n=rng.choice([24, 36]), first_gap=gap, rate=rng.choice([0.9, 1.9, 2.9, 3.9]))
        want = made % 2 == 0
        s = pick_stated(t, want, avoid_rate_shortcut=True)
        if s is None:
            offers.pop()
            continue
        add_ad(offer, t, {"rate": "apr", "stated": s}, ["apr-method", "odd-first-period"])
        made += 1
    # --- tolerance: regular vs irregular (step payments); odd first period stays regular ------
    made = 0
    while made < 8:
        offer, t = new_offer(step=True)
        diff = rng.choice([0.17, 0.19, 0.21, -0.17, -0.2]) if made < 5 else rng.choice([0.29, -0.3])
        s = round(t["apr"] + diff, 2)
        if abs(abs(s - t["apr"]) - STEP) < 0.02 or abs(abs(s - t["apr"]) - REG) < 0.02:
            offers.pop()
            continue
        add_ad(offer, t, {"rate": "apr", "stated": f"{s:.2f}", "triggers": ["payment"],
                          "disclose": {"down": True, "repay": True}}, ["tolerance", "irregular"])
        made += 1
    made = 0
    while made < 6:
        offer, t = new_offer(first_gap=rng.choice([17, 48, 52]))
        s = round(t["apr"] + rng.choice([0.17, 0.2, -0.18, -0.21]), 2)
        add_ad(offer, t, {"rate": "apr", "stated": f"{s:.2f}"}, ["tolerance", "odd-period-is-regular"])
        made += 1
    # --- triggering terms and required disclosures ---------------------------------------------
    for trig in (["payment"], ["period"], ["down"], ["down_pct"], ["fc"], ["payment", "period"]):
        for disc, tg in ((full, "complete"), ({"repay": True}, "no-down"), ({"down": True}, "no-repay"),
                         ({}, "bare")):
            if "down_pct" in trig:          # "80% financing" ads always state the down payment too
                disc = dict(disc, down=True)
            offer, t = new_offer()
            if t["down"] == 0 and ("down" in trig or "down_pct" in trig):
                offers.pop()
                offer, t = new_offer()
                while t["down"] == 0:
                    offers.pop()
                    offer, t = new_offer()
            rate = rng.choice(["apr", "apr", None])
            spec = {"rate": rate, "triggers": trig, "disclose": dict(disc)}
            if rate is None and tg == "complete":
                spec["rate"] = "apr"
            add_ad(offer, t, spec, ["trigger-" + "+".join(trig), "disclosure-" + tg])
    for nt in (["low"], ["years"], ["arranged"], ["easy"], ["low", "years"]):
        offer, t = new_offer()
        add_ad(offer, t, {"rate": rng.choice(["apr", None]), "nontrigger": nt}, ["non-trigger"])
    for _ in range(3):
        offer, t = new_offer()
        while t["down"] != 0:
            offers.pop()
            offer, t = new_offer()
        add_ad(offer, t, {"rate": "apr", "nontrigger": [rng.choice(["zero_down", "no_down"])]},
               ["non-trigger", "zero-down"])
    # step schedule with only the first series disclosed
    for _ in range(3):
        offer, t = new_offer(step=True)
        add_ad(offer, t, {"rate": "apr", "triggers": ["payment"], "disclose": {"down": True, "repay_partial": True}},
               ["disclosure-partial-repayment", "irregular"])
    # rate stated without the term APR
    for r in ("financing", "interest", "financing", "interest"):
        offer, t = new_offer()
        add_ad(offer, t, {"rate": r, "want_ok": True}, ["rate-label"])
    # variable rate
    for vn in (True, False, True, False):
        offer, t = new_offer(variable=True)
        add_ad(offer, t, {"rate": "apr", "triggers": ["payment"], "disclose": full, "variable_note": vn},
               ["rate-increase"])
    # broadcast alternative
    for ph, med in (("tollfree_ref", "radio"), ("tollfree_ref", "tv"), ("tollfree_noref", "radio"),
                    ("local_ref", "radio"), ("tollfree_ref", "radio"), ("local_ref", "tv")):
        offer, t = new_offer()
        while t["down"] == 0:
            offers.pop()
            offer, t = new_offer()
        add_ad(offer, t, {"rate": "apr", "triggers": ["payment", "period"], "disclose": {},
                          "phone": ph, "medium": med}, ["broadcast", "broadcast-" + ph])
    # print ad with toll-free reference does not get the broadcast alternative
    offer, t = new_offer()
    while t["down"] == 0:
        offers.pop()
        offer, t = new_offer()
    add_ad(offer, t, {"rate": "apr", "triggers": ["payment"], "disclose": {}, "phone": "tollfree_ref",
                      "medium": "print"}, ["broadcast", "broadcast-print"])
    # --- filler: second ads on existing offers ----------------------------------------------------
    for offer in rng.sample(offers, 25):
        t = truths[offer["offer_id"]]
        spec = {"rate": "apr", "triggers": rng.choice([["payment"], ["period"], []]),
                "disclose": rng.choice([full, {}]), "variable_note": t["variable"],
                "medium": rng.choice(["web_banner", "direct_mail", "print"]), "want_ok": rng.random() < 0.7}
        if t["down"] == 0:
            spec["disclose"] = {"repay": True} if spec["disclose"] else {}
        add_ad(offer, t, spec, ["filler"])

    ENV.mkdir(parents=True, exist_ok=True)
    (ENV / "deal_worksheets.json").write_text(json.dumps(offers, indent=1) + "\n")
    order = list(range(len(ads)))
    rng.shuffle(order)
    remap = {}
    shuffled = []
    for new_i, old_i in enumerate(order, 1):
        a = dict(ads[old_i])
        remap[a["ad_id"]] = f"AD{new_i:03d}"
        a["ad_id"] = remap[a["ad_id"]]
        shuffled.append(a)
    with open(ENV / "ads.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["ad_id", "offer_id", "medium", "copy"], lineterminator="\n")
        w.writeheader()
        w.writerows(shuffled)
    (ENV / "dealer_group.json").write_text(json.dumps({
        "dealer_group": "Riverbend Auto Group", "stores": STORES, "creditor": "each store, as seller-creditor "
        "on a retail installment sale contract later assigned to a finance company",
        "money_unit": "cents", "event": "Fall Sales Event, October 2026"}, indent=1) + "\n")
    if TST.exists():
        shutil.rmtree(TST)
    shutil.copytree(ENV, TST)
    (ROOT / "tests" / "case_tags.json").write_text(json.dumps({remap[k]: v for k, v in tags.items()},
                                                              indent=1, sort_keys=True) + "\n")
    (ROOT / "tests" / "golden.json").write_text(json.dumps({remap[k]: v for k, v in golden.items()},
                                                           indent=1, sort_keys=True) + "\n")
    print(len(offers), "offers,", len(ads), "ads,", len(golden), "golden")


if __name__ == "__main__":
    main()
