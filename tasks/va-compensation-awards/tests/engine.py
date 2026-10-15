"""Verifier-side model of VA disability compensation awards (38 CFR 3.31, 3.4(b)(2), 3.400(b)(2) and (o), 3.401(b),
3.700(a)(5), 4.25, 4.26), written independently of the reference solution: combined values are exact fractions
with the bilateral factor added exactly, limbs come from the diagnostic code, and each veteran's history is a list
of dated segments read by the payment ledger."""
import json
from datetime import date, timedelta
from fractions import Fraction
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
LEG_CODES = {"5260", "5271", "5252", "5269", "8520"}
ARM_CODES = {"5201", "5206", "5215", "8515"}


def load(name):
    return json.loads((DATA / name).read_text())


def iso(s):
    return date.fromisoformat(s)


def plus_year(d):
    return date(d.year + 1, d.month, min(d.day, 28) if d.month == 2 else d.day)


def first_of_next(d):
    return date(d.year + (d.month == 12), d.month % 12 + 1, 1)


def exact_combined(values):
    remaining = Fraction(1)
    for v in values:
        remaining *= 1 - Fraction(v) / 100
    return 100 * (1 - remaining)


def rating(entries):
    """entries: [(percent, diagnostic code, description)] -> combined rating (multiple of 10)."""
    values, paired = [], {"arm": [], "leg": []}
    for pct, code, desc in entries:
        if pct == 0:
            continue
        limb = "leg" if code in LEG_CODES else "arm" if code in ARM_CODES else None
        side = "left" if "left " in desc.lower() + " " else "right" if "right" in desc.lower() else None
        if limb:
            paired[limb].append((pct, side))
        else:
            values.append(pct)
    for limb, items in paired.items():
        if {s for _, s in items} == {"left", "right"}:
            v = exact_combined([p for p, _ in items])
            values.append(v * Fraction(11, 10))
        else:
            values.extend(p for p, _ in items)
    total = exact_combined(values)
    tens, rest = divmod(total, 10)
    return int(tens) * 10 + (10 if rest >= 5 else 0)


def expected():
    vets = load("veterans.json")
    dis = {d["disability_id"]: d for d in load("disabilities.json")}
    decisions = load("rating_decisions.json")
    deps = load("dependents.json")
    tables = sorted(load("compensation_rates.json"), key=lambda t: t["effective_date"])
    result = {}
    for v in vets:
        vid = v["veteran_id"]
        sep = iso(v["last_day_of_active_service"])
        mine = sorted((r for r in decisions if dis[r["disability_id"]]["veteran_id"] == vid),
                      key=lambda r: (r["disability_id"], r["claim_received"]))
        dated = []
        for r in mine:
            got, shows = iso(r["claim_received"]), iso(r["evidence_first_shows_on"])
            if r["claim"] == "original":
                eff = sep + timedelta(days=1) if (got - sep).days <= (plus_year(sep) - sep).days else max(got, shows)
            else:
                eff = shows if (shows > got or plus_year(shows) >= got) else got
            dated.append((eff, r["disability_id"], r["rating_percent"]))
        start = min(e for e, _, _ in dated)

        def combined_on(when):
            latest = {}
            for eff, did, pct in sorted(dated):
                if eff <= when:
                    latest[did] = pct
            return rating([(pct, dis[did]["diagnostic_code"], dis[did]["description"]) for did, pct in latest.items()])

        counted = []
        for d in deps:
            if d["veteran_id"] != vid:
                continue
            ev, told = iso(d["date_of_marriage_or_birth"]), iso(d["reported_to_va_on"])
            counted.append((max(ev if told <= plus_year(ev) else told, start), d["relationship"]))
        sp = v["separation_pay"]
        balance = Fraction(sp["gross_cents"] - sp["federal_income_tax_withheld_cents"]) if sp else Fraction(0)
        month = first_of_next(start)
        while month <= date(2026, 9, 1):
            before = month - timedelta(days=1)
            pct = combined_on(before)
            due = 0
            if pct:
                row = [t for t in tables if iso(t["effective_date"]) <= month][-1]["monthly_rates_cents"][str(pct)]
                spouse = any(rel == "spouse" and e <= before for e, rel in counted)
                children = sum(rel == "child" and e <= before for e, rel in counted)
                if pct >= 30 and spouse and children:
                    due = row["veteran_with_spouse_and_one_child"] + (children - 1) * row["each_additional_child"]
                elif pct >= 30 and spouse:
                    due = row["veteran_with_spouse"]
                elif pct >= 30 and children:
                    due = row["veteran_with_one_child"] + (children - 1) * row["each_additional_child"]
                else:
                    due = row["veteran_alone"]
            take = min(Fraction(due), balance)
            balance -= take
            paid = int(due - take)
            if month >= date(2023, 1, 1):
                end = first_of_next(month) - timedelta(days=1)
                result[f"{vid},{month.isoformat()[:7]}"] = {"combined_rating": str(combined_on(end)),
                                                             "payment": f"{paid // 100}.{paid % 100:02d}"}
            month = first_of_next(month)
        month = date(2023, 1, 1)
        while month < first_of_next(start):
            end = first_of_next(month) - timedelta(days=1)
            result[f"{vid},{month.isoformat()[:7]}"] = {"combined_rating": str(combined_on(end)), "payment": "0.00"}
            month = first_of_next(month)
    return result
