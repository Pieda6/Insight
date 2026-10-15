#!/usr/bin/env python3
"""Reference solution for va-compensation-awards (38 CFR 3.31, 3.4, 3.105(e), 3.110, 3.400, 3.401, 3.700, 4.25,
4.26, 4.29, 4.30).

For each veteran: date every rating decision (3.400 for original and increased ratings, 3.105(e) for reductions),
date every temporary total rating (4.29 with its absence rules, 4.30), date each dependent (3.401(b)). Each month is
then paid on the ratings payable for it: increases (and temporary totals) from the month after the month they take
effect (3.31, with the same-month exception of 3.31(c)(5)), reductions and ends of temporary totals from the month
after the month whose last day they take effect. The combined rating follows Table I and the bilateral factor with
its most favorable exclusions (4.25, 4.26), and nondisability separation pay less tax is withheld first (3.700)."""
import csv
import json
from collections import defaultdict
from datetime import date, timedelta
from itertools import combinations
from pathlib import Path

DATA = Path("/app/data")
OUT = Path("/app/output")
FIRST, LAST = (2023, 1), (2026, 9)
ONE = timedelta(days=1)


def day(s):
    return date.fromisoformat(s) if s else None


def anniversary(d):
    try:
        return d.replace(year=d.year + 1)
    except ValueError:
        return d.replace(year=d.year + 1, day=28)


def first_of(y, m):
    return date(y, m, 1)


def following(y, m):
    return (y + 1, 1) if m == 12 else (y, m + 1)


def last_of(y, m):
    return date(*following(y, m), 1) - ONE


def months(start, stop):
    ym = start
    while ym <= stop:
        yield ym
        ym = following(*ym)


def load(name):
    return json.loads((DATA / name).read_text())


def table(values):
    """38 CFR 4.25 Table I: largest first; every combined value is the table's (nearest whole number, .5 up)."""
    total = None
    for v in sorted(values, reverse=True):
        total = v if total is None else (2 * total * 100 + 2 * v * (100 - total) + 100) // 200
    return total or 0


def limb_of(description):
    d = description.lower()
    side = "left" if "left" in d else "right" if "right" in d else None
    if side and any(w in d for w in ("knee", "ankle", "hip", "foot", "lower extremity")):
        return "leg", side
    if side and any(w in d for w in ("shoulder", "elbow", "wrist", "arm", "upper extremity", "hand")):
        return "arm", side
    return None, None


def combined(ratings):
    """ratings: [(percent, limb, side)] -> final degree. 4.26: the paired extremities (all four if both pairs) are
    combined and 10% of the value is added; 4.26(d): leave out whichever bilateral disabilities gives the most."""
    comp = [r for r in ratings if r[0] > 0]
    limbs = [i for i, r in enumerate(comp) if r[1]]

    def value(skip):
        kept = [r for i, r in enumerate(comp) if i not in skip]
        arms = [r for r in kept if r[1] == "arm"]
        legs = [r for r in kept if r[1] == "leg"]
        paired_arms = {r[2] for r in arms} == {"left", "right"}
        paired_legs = {r[2] for r in legs} == {"left", "right"}
        group = (arms if paired_arms else []) + (legs if paired_legs else [])
        others = [r[0] for r in kept if r not in group] + [comp[i][0] for i in skip]
        if group:
            v = table([r[0] for r in group])
            others.append((v * 11 + 5) // 10)
        return (table(others) + 5) // 10 * 10

    best = value(set())
    for k in range(1, len(limbs) + 1):
        for skip in combinations(limbs, k):
            best = max(best, value(set(skip)))
    return best


def temporary_total(stay):
    """(start, last day, same-month rule) of a 4.29 or 4.30 total rating, or None."""
    admitted, began, out = day(stay["admitted"]), day(stay["treatment_for_this_disability_began"]), day(stay["discharged"])
    extra = stay["convalescence_months_granted"]
    if stay["kind"] != "hospital treatment":           # 4.30: 1-3 months from the first of the month after release
        y, m = following(out.year, out.month)
        for _ in range(extra - 1):
            y, m = following(y, m)
        return began, last_of(y, m), False
    released = out
    used = 0
    for a in sorted(stay["authorized_absences"], key=lambda a: a["first_day_absent"]):
        first, last = day(a["first_day_absent"]), day(a["last_day_absent"])
        length = (last - first).days + 1
        if (first - admitted).days + 1 <= 21:          # 4.29(a)(1)
            if length > 4:
                released = min(released, first)
                break
            if used + length > 8:
                released = min(released, first + timedelta(days=8 - used))
                break
            used += length
    if (released - began).days <= 21:
        return None
    y, m = released.year, released.month
    for _ in range(extra):                             # 4.29(e)
        y, m = following(y, m)
    end = last_of(y, m)
    for a in stay["authorized_absences"]:              # 4.29(a)(2)
        first, last = day(a["first_day_absent"]), day(a["last_day_absent"])
        if (first - admitted).days + 1 > 21 and (last - first).days + 1 > 14:
            end = min(end, last_of(first.year, first.month))
    same = (began.year, began.month) == (end.year, end.month)
    return began, end, same


def main():
    vets = [v for v in load("veterans.json")]
    disabilities = {d["disability_id"]: d for d in load("disabilities.json")}
    decisions = defaultdict(list)
    for r in load("rating_decisions.json"):
        decisions[r["disability_id"]].append(r)
    dependents = defaultdict(list)
    for d in load("dependents.json"):
        dependents[d["veteran_id"]].append(d)
    stays = defaultdict(list)
    for s in load("hospital_and_convalescence.json"):
        stays[s["veteran_id"]].append(s)
    tables = sorted((day(t["effective_date"]), t["monthly_rates_cents"]) for t in load("compensation_rates.json"))
    by_vet = defaultdict(list)
    for did, dsb in disabilities.items():
        by_vet[dsb["veteran_id"]].append(did)

    rows = []
    for vet in vets:
        vid = vet["veteran_id"]
        separated = day(vet["last_day_of_active_service"])
        history = {}                                   # disability -> [(date, percent, "up"/"down")]
        for did in by_vet[vid]:
            items = []
            for r in sorted(decisions[did], key=lambda r: r["claim_received"] or r["notice_of_final_reduction_sent"]):
                if r["decision"] == "reduction":       # 3.105(e): effective the last day of that month
                    expires = day(r["notice_of_final_reduction_sent"]) + timedelta(days=60)
                    items.append((date(*following(expires.year, expires.month), 1), r["rating_percent"], "down"))
                    continue
                received, shown = day(r["claim_received"]), day(r["evidence_first_shows_on"])
                if r["decision"] == "original":        # 3.400(b)(2)(i)
                    eff = separated + ONE if received <= anniversary(separated) else max(received, shown)
                elif shown > received or received <= anniversary(shown):
                    eff = shown                        # 3.400(o)(1) and (o)(2)
                else:
                    eff = received
                items.append((eff, r["rating_percent"], "up"))
            history[did] = items
        award_start = min(i[0] for items in history.values() for i in items)
        totals = [t for t in (temporary_total(s) for s in stays[vid]) if t]

        def basis(y, m):
            begin = first_of(y, m)
            before = begin - ONE
            for s, e, same in totals:
                if (s <= before and begin <= e) or (same and (s.year, s.month) == (y, m)):
                    return 100
            current = []
            for did, items in history.items():
                pct = None
                for when, p, kind in sorted(items):
                    if (kind == "up" and when <= before) or (kind == "down" and when <= begin):
                        pct = p
                if pct is not None:
                    current.append((pct,) + limb_of(disabilities[did]["description"]))
            return combined(current) if current else 0

        counted = []                                   # 3.401(b)
        for d in dependents[vid]:
            event, told = day(d["date_of_marriage_or_birth"]), day(d["reported_to_va_on"])
            counted.append((max(event if told <= anniversary(event) else told, award_start), d["relationship"]))

        pay = vet["separation_pay"]
        owed = pay["gross_cents"] - pay["federal_income_tax_withheld_cents"] if pay else 0
        first_paid = following(award_start.year, award_start.month)
        for y, m in months(min(first_paid, FIRST), LAST):
            pct = basis(y, m) if (y, m) >= first_paid else 0
            amount = 0
            if pct:
                before = first_of(y, m) - ONE
                rates = [t for eff, t in tables if eff <= first_of(y, m)][-1][str(pct)]
                spouse = pct >= 30 and any(rel == "spouse" and e <= before for e, rel in counted)
                kids = sum(1 for e, rel in counted if rel == "child" and e <= before) if pct >= 30 else 0
                if spouse and kids:
                    amount = rates["veteran_with_spouse_and_one_child"] + (kids - 1) * rates["each_additional_child"]
                elif spouse:
                    amount = rates["veteran_with_spouse"]
                elif kids:
                    amount = rates["veteran_with_one_child"] + (kids - 1) * rates["each_additional_child"]
                else:
                    amount = rates["veteran_alone"]
            withheld = min(amount, owed)               # 3.700(a)(5)
            owed -= withheld
            if (y, m) >= FIRST:
                rows.append((vid, f"{y:04d}-{m:02d}", pct, amount - withheld))

    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "monthly_payments.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["veteran_id", "month", "combined_rating", "payment"])
        for vid, month, pct, cents in rows:
            w.writerow([vid, month, pct, f"{cents // 100}.{cents % 100:02d}"])


if __name__ == "__main__":
    main()
