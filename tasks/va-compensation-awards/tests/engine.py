"""Verifier-side model of VA disability compensation awards (38 CFR 3.31, 3.4(b)(2), 3.105(e), 3.400(b)(2) and (o),
3.401(b), 3.700(a)(5), 4.25, 4.26, 4.29, 4.30), written independently of the reference solution: limbs come from
diagnostic codes, the bilateral exclusions of 4.26(d) are searched as bit masks, hospital days are walked one by
one, and every month is read from a list of dated rating periods."""
import json
from datetime import date, timedelta
from fractions import Fraction
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
LEG_CODES = {"5260", "5271", "5252", "5284", "8520"}
ARM_CODES = {"5201", "5206", "5215", "8515"}
DAY = timedelta(days=1)


def load(name):
    return json.loads((DATA / name).read_text())


def iso(s):
    return date.fromisoformat(s) if s else None


def plus_year(d):
    return date(d.year + 1, d.month, 28 if (d.month, d.day) == (2, 29) else d.day)


def month_after(d):
    return date(d.year + (d.month == 12), d.month % 12 + 1, 1)


def nearest(x):
    return int(Fraction(x) + Fraction(1, 2))


def table_value(values):
    vals = sorted(values, reverse=True)
    if not vals:
        return 0
    acc = vals[0]
    for v in vals[1:]:
        acc = nearest(acc + Fraction(v * (100 - acc), 100))
    return acc


def degree(entries):
    """entries: [(percent, limb, side)] for compensable disabilities -> final degree under 4.25 and 4.26."""
    limb_idx = [i for i, e in enumerate(entries) if e[1]]
    best = 0
    for mask in range(1 << len(limb_idx)):
        out = {limb_idx[j] for j in range(len(limb_idx)) if mask >> j & 1}
        sides = {"arm": set(), "leg": set()}
        for i, e in enumerate(entries):
            if e[1] and i not in out:
                sides[e[1]].add(e[2])
        paired = {k for k, v in sides.items() if v == {"left", "right"}}
        bil = [e[0] for i, e in enumerate(entries) if i not in out and e[1] in paired]
        rest = [e[0] for i, e in enumerate(entries) if i in out or e[1] not in paired]
        if bil:
            v = table_value(bil)
            rest.append(nearest(Fraction(v * 11, 10)))
        total = table_value(rest)
        best = max(best, (total // 10 + (1 if total % 10 >= 5 else 0)) * 10)
    return best


def hospital_total(rec):
    adm, begin, dis = iso(rec["admitted"]), iso(rec["treatment_for_this_disability_began"]), iso(rec["discharged"])
    n = rec["convalescence_months_granted"]

    def end_after(d, k):
        m = date(d.year, d.month, 1)
        for _ in range(k + 1):
            m = month_after(m)
        return m - DAY

    if rec["kind"] != "hospital treatment":
        return begin, end_after(dis, n), False
    absent_days = []
    for a in rec["authorized_absences"]:
        d = iso(a["first_day_absent"])
        while d <= iso(a["last_day_absent"]):
            absent_days.append((d, a))
            d += DAY
    release = dis
    count = 0
    for d, a in sorted(absent_days, key=lambda x: x[0]):
        if (iso(a["first_day_absent"]) - adm).days >= 21:
            continue
        span = (iso(a["last_day_absent"]) - iso(a["first_day_absent"])).days + 1
        if span > 4:
            release = min(release, iso(a["first_day_absent"]))
            break
        count += 1
        if count == 9:
            release = min(release, d)
            break
    if (release - begin).days < 22:
        return None
    end = end_after(release, n)
    for a in rec["authorized_absences"]:
        f = iso(a["first_day_absent"])
        if (f - adm).days >= 21 and (iso(a["last_day_absent"]) - f).days >= 14:
            end = min(end, month_after(f) - DAY)
    return begin, end, (begin.year, begin.month) == (end.year, end.month)


def expected():
    vets = load("veterans.json")
    dis = {d["disability_id"]: d for d in load("disabilities.json")}
    decisions = load("rating_decisions.json")
    deps = load("dependents.json")
    recs = load("hospital_and_convalescence.json")
    tables = sorted(load("compensation_rates.json"), key=lambda t: t["effective_date"])
    result = {}
    for v in vets:
        vid = v["veteran_id"]
        sep = iso(v["last_day_of_active_service"])
        periods = {}                                     # disability -> [(first payable month, percent)]
        start = None
        for r in sorted((r for r in decisions if dis[r["disability_id"]]["veteran_id"] == vid),
                        key=lambda r: r["claim_received"] or r["notice_of_final_reduction_sent"]):
            if r["decision"] == "reduction":
                n = iso(r["notice_of_final_reduction_sent"]) + timedelta(days=60)
                payable = month_after(n)                 # effective last day of that month; paid lower next month
            else:
                got, shows = iso(r["claim_received"]), iso(r["evidence_first_shows_on"])
                if r["decision"] == "original":
                    eff = sep + DAY if got <= plus_year(sep) else max(got, shows)
                else:
                    eff = shows if (shows > got or got <= plus_year(shows)) else got
                start = eff if start is None or eff < start else start
                payable = month_after(eff)               # 3.31
            periods.setdefault(r["disability_id"], []).append((payable, r["rating_percent"]))
        totals = [t for t in (hospital_total(x) for x in recs if x["veteran_id"] == vid) if t]

        def rating_for(month):
            for s, e, same in totals:
                if month_after(s) <= month <= e or (same and (s.year, s.month) == (month.year, month.month)):
                    return 100
            entries = []
            for did, ps in periods.items():
                cur = None
                for payable, pct in sorted(ps):
                    if payable <= month:
                        cur = pct
                if cur:
                    d = dis[did]
                    limb = "leg" if d["diagnostic_code"] in LEG_CODES else "arm" if d["diagnostic_code"] in ARM_CODES else None
                    desc = d["description"].lower()
                    side = "left" if "left" in desc else "right" if "right" in desc else None
                    entries.append((cur, limb, side))
            return degree(entries)

        counted = []
        for d in deps:
            if d["veteran_id"] == vid:
                ev, told = iso(d["date_of_marriage_or_birth"]), iso(d["reported_to_va_on"])
                counted.append((month_after(max(ev if told <= plus_year(ev) else told, start)), d["relationship"]))
        sp = v["separation_pay"]
        balance = Fraction(sp["gross_cents"] - sp["federal_income_tax_withheld_cents"]) if sp else Fraction(0)
        month = month_after(start)
        while month <= date(2026, 9, 1):
            pct = rating_for(month)
            due = 0
            if pct:
                row = [t for t in tables if iso(t["effective_date"]) <= month][-1]["monthly_rates_cents"][str(pct)]
                spouse = pct >= 30 and any(rel == "spouse" and m <= month for m, rel in counted)
                children = sum(rel == "child" and m <= month for m, rel in counted) if pct >= 30 else 0
                if spouse and children:
                    due = row["veteran_with_spouse_and_one_child"] + (children - 1) * row["each_additional_child"]
                elif spouse:
                    due = row["veteran_with_spouse"]
                elif children:
                    due = row["veteran_with_one_child"] + (children - 1) * row["each_additional_child"]
                else:
                    due = row["veteran_alone"]
            take = min(Fraction(due), balance)
            balance -= take
            paid = int(due - take)
            if month >= date(2023, 1, 1):
                result[f"{vid},{month.isoformat()[:7]}"] = {"combined_rating": str(pct), "payment": f"{paid // 100}.{paid % 100:02d}"}
            month = month_after(month)
        month = date(2023, 1, 1)
        while month < month_after(start):
            result[f"{vid},{month.isoformat()[:7]}"] = {"combined_rating": "0", "payment": "0.00"}
            month = month_after(month)
    return result
