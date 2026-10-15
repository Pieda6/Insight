#!/usr/bin/env python3
"""Reference solution for va-compensation-awards (38 CFR 3.31, 3.4, 3.400, 3.401, 3.700, 4.25, 4.26).

For each veteran: fix the effective date of every rating decision, build the combined rating with the bilateral
factor on each day a rating changes, fix the date each dependent counts from, then walk the months from the first
payment: each month is paid at the rating and dependents in effect at the end of the previous month, at the rates
in effect for the month, less whatever is still owed for separation pay."""
import csv
import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

DATA = Path("/app/data")
OUT = Path("/app/output")
FIRST, LAST = (2023, 1), (2026, 9)


def day(s):
    return date.fromisoformat(s)


def anniversary(d, years=1):
    try:
        return d.replace(year=d.year + years)
    except ValueError:                                # February 29
        return d.replace(year=d.year + years, day=28)


def months(start, stop):
    y, m = start
    while (y, m) <= stop:
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def month_end(y, m):
    return (date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)) - timedelta(days=1)


def load(name):
    return json.loads((DATA / name).read_text())


def table_combine(values):
    """38 CFR 4.25 Table I: largest first, each step rounded to the nearest whole number."""
    total = None
    for v in sorted(values, reverse=True):
        if total is None:
            total = v
        else:
            exact = total + v * (100 - total) / 100
            total = int(exact + 0.5 + 1e-9)
    return total or 0


def limb_of(description):
    d = description.lower()
    side = "left" if "left" in d else "right" if "right" in d else None
    if side is None:
        return None, None
    if any(w in d for w in ("knee", "ankle", "hip", "foot", "lower extremity")):
        return "leg", side
    if any(w in d for w in ("shoulder", "elbow", "wrist", "arm", "upper extremity", "hand")):
        return "arm", side
    return None, None


def combined(ratings):
    """ratings: list of (percent, limb, side). 4.26: compensable disabilities of both arms (or both legs) are
    combined, 10% of that value is added, and the result is one disability for the remaining combination."""
    comp = [r for r in ratings if r[0] > 0]
    rest = [r[0] for r in comp]
    for limb in ("arm", "leg"):
        group = [r for r in comp if r[1] == limb]
        if {r[2] for r in group} == {"left", "right"}:
            for r in group:
                rest.remove(r[0])
            value = table_combine([r[0] for r in group])
            rest.append((value * 11 + 5) // 10)                   # value plus 10%, nearest whole number
    value = table_combine(rest)
    return (value + 5) // 10 * 10


def main():
    vets = {v["veteran_id"]: v for v in load("veterans.json")}
    disabilities = {d["disability_id"]: d for d in load("disabilities.json")}
    decisions = defaultdict(list)
    for r in load("rating_decisions.json"):
        decisions[r["disability_id"]].append(r)
    dependents = defaultdict(list)
    for d in load("dependents.json"):
        dependents[d["veteran_id"]].append(d)
    tables = sorted((day(t["effective_date"]), t["monthly_rates_cents"]) for t in load("compensation_rates.json"))

    by_vet = defaultdict(list)
    for did, dsb in disabilities.items():
        by_vet[dsb["veteran_id"]].append(did)

    rows = []
    for vid in sorted(vets):
        separated = day(vets[vid]["last_day_of_active_service"])
        changes = []                                  # (effective date, disability, percent)
        for did in by_vet[vid]:
            previous = None
            for r in sorted(decisions[did], key=lambda r: r["claim_received"]):
                received, shown = day(r["claim_received"]), day(r["evidence_first_shows_on"])
                if r["claim"] == "original":          # 3.400(b)(2)(i)
                    effective = separated + timedelta(days=1) if received <= anniversary(separated) else max(received, shown)
                elif shown > received:                # 3.400(o): entitlement arose after the claim
                    effective = shown
                elif anniversary(shown) >= received:  # 3.400(o)(2): increase shown within the year before
                    effective = shown
                else:
                    effective = received
                changes.append((effective, did, r["rating_percent"]))
                previous = effective
        changes.sort()
        award_start = changes[0][0]

        def rating_on(when):
            current = {}
            for eff, did, pct in changes:
                if eff <= when:
                    current[did] = pct
            return combined([(pct,) + limb_of(disabilities[did]["description"]) for did, pct in current.items()]) if current else 0

        dep_from = []                                 # 3.401(b)
        for d in dependents[vid]:
            event, told = day(d["date_of_marriage_or_birth"]), day(d["reported_to_va_on"])
            basis = event if told <= anniversary(event) else told
            dep_from.append((max(basis, award_start), d["relationship"]))

        pay = vets[vid]["separation_pay"]
        owed = pay["gross_cents"] - pay["federal_income_tax_withheld_cents"] if pay else 0
        first_paid = (award_start.year + award_start.month // 12, award_start.month % 12 + 1)   # 3.31
        for y, m in months(min(first_paid, FIRST), LAST):
            amount = 0
            if (y, m) >= first_paid:
                prior_end = date(y, m, 1) - timedelta(days=1)
                pct = rating_on(prior_end)
                if pct:
                    rates = [t for eff, t in tables if eff <= date(y, m, 1)][-1][str(pct)]
                    spouse = any(rel == "spouse" and e <= prior_end for e, rel in dep_from)
                    kids = sum(1 for e, rel in dep_from if rel == "child" and e <= prior_end)
                    if pct < 30 or not (spouse or kids):
                        amount = rates["veteran_alone"]
                    elif spouse and kids:
                        amount = rates["veteran_with_spouse_and_one_child"] + (kids - 1) * rates["each_additional_child"]
                    elif spouse:
                        amount = rates["veteran_with_spouse"]
                    else:
                        amount = rates["veteran_with_one_child"] + (kids - 1) * rates["each_additional_child"]
            withheld = min(amount, owed)              # 3.700(a)(5): separation pay less federal tax
            owed -= withheld
            if (y, m) >= FIRST:
                rows.append((vid, f"{y:04d}-{m:02d}", rating_on(month_end(y, m)), amount - withheld))

    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "monthly_payments.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["veteran_id", "month", "combined_rating", "payment"])
        for vid, month, pct, cents in rows:
            w.writerow([vid, month, pct, f"{cents // 100}.{cents % 100:02d}"])


if __name__ == "__main__":
    main()
