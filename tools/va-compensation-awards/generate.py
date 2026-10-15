#!/usr/bin/env python3
"""Generate the va-compensation-awards inputs (dev only, never shipped).

A VA regional office's awards team must state, for each veteran and each month from January 2023 to September
2026, the combined disability rating on which the month is paid and the compensation actually paid for the month. That depends on: effective dates of original awards (38 CFR 3.400(b)(2): day after separation for a claim
within a year, else the later of the claim and the date entitlement arose) and of increases (3.400(o)(2): back to
the date the increase is first shown if that is within a year before the claim); the combined ratings table
(4.25, final value rounded to the nearest 10 with 5 rounding up); the bilateral factor (4.26: compensable
disabilities of both arms or both legs are combined first and 10% of that value is added); payment from the first
day of the month after the effective date (3.31); additional amounts for dependents only at 30% or more (3.4(b)(2))
from the date fixed by 3.401(b); the December 1 rate tables; and recovery of nondisability separation pay less
federal income tax withheld (3.700(a)(5)). `sim` is the third implementation; in strict mode it rejects any
veteran whose answer would depend on an open reading.
"""
import json
import random
import shutil
from datetime import date, timedelta
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "tasks" / "va-compensation-awards"
ENV, TST = ROOT / "environment" / "data", ROOT / "tests" / "data"
rng = random.Random(38400)
FIRST, LASTM = date(2023, 1, 1), date(2026, 9, 1)
ASOF = date(2026, 10, 15)
DAY = timedelta(days=1)


def days(n):
    return timedelta(days=n)


def D(s):
    return date.fromisoformat(s) if isinstance(s, str) else s


def next_month(d):
    return date(d.year + d.month // 12, d.month % 12 + 1, 1)


def year_before(d):
    return date(d.year - 1, d.month, 28 if (d.month == 2 and d.day == 29) else d.day)


def year_after(d):
    return date(d.year + 1, d.month, 28 if (d.month == 2 and d.day == 29) else d.day)


# ---------------------------------------------------------------- rate tables (monthly, cents)
BASE = {10: 17123, 20: 33849, 30: 52431, 40: 75528, 50: 107516, 60: 136188, 70: 171628, 80: 199501, 90: 224191,
        100: 373785}                                   # veteran alone, table effective December 1, 2023
COLA = {2018: 2.8, 2019: 1.6, 2020: 1.3, 2021: 5.9, 2022: 8.7, 2023: 3.2, 2024: 2.5, 2025: 2.8}


def factor(year):
    f = Fraction(1)
    if year > 2023:
        for y in range(2024, year + 1):
            f *= 1 + Fraction(str(COLA[y])) / 100
    else:
        for y in range(year + 1, 2024):
            f /= 1 + Fraction(str(COLA[y])) / 100
    return f


def cents(x):
    return int(Fraction(x) + Fraction(1, 2)) if x >= 0 else -cents(-x)


TABLES = []
for y in range(2018, 2026):
    f = factor(y)
    t = {}
    for r, a in BASE.items():
        row = {"veteran_alone": cents(a * f)}
        if r >= 30:
            row["veteran_with_spouse"] = cents((a + 2067 * r // 10) * f)
            row["veteran_with_spouse_and_one_child"] = cents((a + 2067 * r // 10 + 1533 * r // 10) * f)
            row["veteran_with_one_child"] = cents((a + 1367 * r // 10) * f)
            row["each_additional_child"] = cents(1035 * r // 10 * f)
        t[r] = row
    TABLES.append((date(y, 12, 1), t))


def table_for(month_first):
    return [t for eff, t in TABLES if eff <= month_first][-1]


def rate(month_first, rating, spouse, children):
    row = table_for(month_first)[rating]
    if rating < 30 or (not spouse and not children):
        return row["veteran_alone"]
    if spouse and children:
        return row["veteran_with_spouse_and_one_child"] + (children - 1) * row["each_additional_child"]
    if spouse:
        return row["veteran_with_spouse"]
    return row["veteran_with_one_child"] + (children - 1) * row["each_additional_child"]


# ---------------------------------------------------------------- calendar (38 CFR 3.110)
def federal_holidays(y):
    def nth(month, weekday, n):
        d = date(y, month, 1)
        d += days((weekday - d.weekday()) % 7)
        return d + days(7 * (n - 1))

    def last(month, weekday):
        d = next_month(date(y, month, 1)) - DAY
        return d - days((d.weekday() - weekday) % 7)

    fixed = [date(y, 1, 1), date(y, 6, 19), date(y, 7, 4), date(y, 11, 11), date(y, 12, 25)]
    out = set()
    for h in fixed:
        out.add(h - DAY if h.weekday() == 5 else h + DAY if h.weekday() == 6 else h)
    out |= {nth(1, 0, 3), nth(2, 0, 3), last(5, 0), nth(9, 0, 1), nth(10, 0, 2), nth(11, 3, 4)}
    return out


HOLIDAYS = set().union(*(federal_holidays(y) for y in range(2017, 2029)))


def workday(d):
    return d.weekday() < 5 and d not in HOLIDAYS


def next_workday(d):
    while not workday(d):
        d += DAY
    return d


class Reject(Exception):
    pass


def check_limit(limit, received):
    """3.110(b) moves a limit that ends on a weekend or holiday to the next workday; whether that applies to these
    one-year limits is left open, so no receipt may fall in the gap."""
    if not workday(limit) and limit < received <= next_workday(limit):
        raise Reject("receipt inside a weekend or holiday extension")


def month_end(d):
    return next_month(d) - DAY


def add_months_end(d, n):
    """Last day of the month n months after the month of d."""
    m = date(d.year, d.month, 1)
    for _ in range(n):
        m = next_month(m)
    return month_end(m)


# ---------------------------------------------------------------- disabilities
CATALOG = [
    # description template, diagnostic code, limb, ratings
    ("{side} knee strain with limitation of flexion", "5260", "leg", [0, 10, 20, 30]),
    ("{side} ankle, limited motion", "5271", "leg", [10, 20]),
    ("{side} hip, limitation of flexion", "5252", "leg", [10, 20, 30]),
    ("{side} foot injury", "5284", "leg", [10, 20, 30]),
    ("radiculopathy, {side} lower extremity (sciatic nerve)", "8520", "leg", [10, 20, 40]),
    ("{side} shoulder impingement, limitation of motion of the arm", "5201", "arm", [20, 30]),
    ("{side} elbow tendinitis, limitation of flexion", "5206", "arm", [10, 20]),
    ("{side} wrist strain, limitation of motion", "5215", "arm", [10]),
    ("carpal tunnel syndrome, {side} upper extremity (median nerve)", "8515", "arm", [10, 30]),
    ("tinnitus, recurrent", "6260", None, [10]),
    ("posttraumatic stress disorder", "9411", None, [30, 50, 70]),
    ("lumbosacral strain", "5237", None, [10, 20, 40]),
    ("cervical strain", "5237", None, [10, 20, 30]),
    ("migraine headaches", "8100", None, [0, 10, 30, 50]),
    ("hypertension", "7101", None, [10, 20]),
    ("obstructive sleep apnea", "6847", None, [30, 50]),
    ("scar of the chest wall", "7804", None, [0, 10]),
]


# ---------------------------------------------------------------- combined ratings (4.25, 4.26)
def rh(x):
    return int(Fraction(x) + Fraction(1, 2))


def table(values):
    """Table I: largest first, each combined value as found in the table (a + b(100 - a)/100, half up)."""
    vals = sorted(values, reverse=True)
    if not vals:
        return 0
    acc = vals[0]
    for v in vals[1:]:
        acc = rh(Fraction(acc) + Fraction(v) * (100 - acc) / 100)
    return acc


def to_ten(x):
    return (x + 5) // 10 * 10


def groups_for(comp):
    arms = [d for d in comp if d[1] == "arm"]
    legs = [d for d in comp if d[1] == "leg"]
    ab, lb = {d[2] for d in arms} == {"left", "right"}, {d[2] for d in legs} == {"left", "right"}
    if ab and lb:
        return [arms + legs]                           # 4.26(b): all four extremities, one factor
    return ([arms] if ab else []) + ([legs] if lb else [])


def evaluate(comp, removed, half_up=True):
    groups = groups_for(comp)
    used = {id(d) for g in groups for d in g}
    vals = [d[0] for d in comp if id(d) not in used] + [d[0] for d in removed]
    for g in groups:
        v = Fraction(table([d[0] for d in g])) * Fraction(11, 10)
        vals.append(rh(v) if half_up or v.denominator == 1 or v - int(v) != Fraction(1, 2) else int(v))
    return table(vals)


def combined_rating(dis, strict=True):
    """dis: [(rating, limb, side)]. 4.26(d): the most favorable choice of bilateral disabilities to leave out. Strict
    rejects a rating that depends on how a bilateral value ending in .5 is rounded."""
    comp = [d for d in dis if d[0] > 0]
    limbs = [d for d in comp if d[1]]
    n = len(limbs)
    results = set()
    for half_up in (True, False) if strict else (True,):
        best = 0
        for mask in range(0, 1 << n):
            removed = [limbs[i] for i in range(n) if mask >> i & 1]
            rest = [d for d in comp if all(d is not r for r in removed)]
            best = max(best, to_ten(evaluate(rest, removed, half_up)))
        results.add(best)
    if len(results) > 1:
        raise Reject("bilateral value ending in .5 decides the rating")
    return results.pop()


# ---------------------------------------------------------------- effective dates (3.400, 3.105(e))
def segments(vet, strict=True):
    """Per disability: [(start, rating, kind)] where kind 'up' starts on its effective date and 'down' (a reduction
    effective the last day of a month) starts on the first day of the next month."""
    sep = vet["separation"]
    out = {}
    for k, dsb in vet["disabilities"].items():
        segs = []
        for a in dsb["actions"]:
            rec, shown = a["received"], a["shown"]
            if a["type"] == "original":
                lim = year_after(sep)
                if strict:
                    check_limit(lim, rec)
                if rec <= lim:
                    if strict and shown > sep:
                        raise Reject("shown after separation, claim within the year")
                    eff = sep + DAY
                else:
                    eff = max(rec, shown)
                segs.append((eff, a["rating"], "up"))
            elif a["type"] == "increase":
                lim = year_after(shown)
                if strict:
                    check_limit(lim, rec)
                    if shown <= segs[-1][0]:
                        raise Reject("increase shown before the earlier rating")
                eff = shown if (shown > rec or rec <= lim) else rec
                if strict and eff <= segs[-1][0]:
                    raise Reject("increase not after the earlier effective date")
                segs.append((eff, a["rating"], "up"))
            else:                                       # reduction, 3.105(e)
                notice = a["notice"]
                months = {(x.year, x.month) for x in (notice + days(59), notice + days(60), notice + days(61),
                                                        next_workday(notice + days(60)))}
                if strict and len(months) > 1:
                    raise Reject("60-day period ends near a month boundary")
                start = next_month(notice + days(60))
                if strict and start <= segs[-1][0]:
                    raise Reject("reduction before the earlier rating")
                segs.append((start, a["rating"], "down"))
        out[k] = segs
    return out


def temp_totals(vet, strict=True):
    """[(start, end, same_month_rule)]: 4.29 hospital ratings and 4.30 convalescent ratings."""
    out = []
    for st in vet["stays"]:
        if st["kind"] == "convalescence":              # 4.30
            out.append((st["start"], add_months_end(st["released"], st["months"]), False))
            continue
        adm, sc_from, dis = st["admitted"], st["sc_from"], st["discharged"]
        disch = dis
        absent = 0
        for a, b in sorted(st["absences"]):
            first_day_no, last_day_no = (a - adm).days + 1, (b - adm).days + 1
            if strict and not (last_day_no < 19 or first_day_no > 24):
                raise Reject("absence near the 21st day")
            if first_day_no <= 21:                     # 4.29(a)(1)
                length = (b - a).days + 1
                if length > 4:
                    disch = min(disch, a)
                    break
                if absent + length > 8:
                    disch = min(disch, a + days(8 - absent))
                    break
                absent += length
        length = (disch - sc_from).days
        if strict and 19 < length < 24:
            raise Reject("hospitalization of about 21 days")
        if length < 21:
            continue
        end = add_months_end(disch, st["months"])
        long_absences = [(a, b) for a, b in st["absences"] if (a - adm).days + 1 > 21 and (b - a).days + 1 >= 14]
        if strict and len(long_absences) > 1:
            raise Reject("more than one long absence (third consecutive 14-day reading)")
        for a, b in long_absences:                     # 4.29(a)(2)
            if (b - a).days + 1 > 14:
                if strict and st["months"]:
                    raise Reject("long absence with convalescence")
                end = min(end, month_end(a))
        same = (sc_from.year, sc_from.month) == (end.year, end.month)
        out.append((sc_from, end, same))
    return sorted(out)


# ---------------------------------------------------------------- monthly payments
def month_basis(vet, segs, totals, m, strict=True):
    """Rating VA pays for month m (first day): increases count from the month after their effective date (3.31),
    reductions from the month after the month they take effect; temporary totals likewise, with 3.31(c)(5)."""
    p = m - DAY
    for s, e, same in totals:
        if (s <= p and m <= e) or (same and (s.year, s.month) == (m.year, m.month)):
            return 100
    dis = []
    for k, sg in segs.items():
        cur = None
        for start, rating, kind in sg:
            if (kind == "up" and start <= p) or (kind == "down" and start <= m):
                cur = rating
        if cur is not None:
            d = vet["disabilities"][k]
            dis.append((cur, d["limb"], d["side"]))
    return combined_rating(dis, strict) if dis else None


def sim(vet, strict=True):
    """Third implementation: {month first day: (basis rating, spouse, children, cents paid)}."""
    segs = segments(vet, strict)
    totals = temp_totals(vet, strict)
    start = min(sg[0][0] for sg in segs.values())
    months, m = [], next_month(start)
    while m <= LASTM:
        months.append(m)
        m = next_month(m)
    basis = {m: month_basis(vet, segs, totals, m, strict) or 0 for m in months}
    if strict:
        for s, e, same in totals:
            if s <= start + days(40):
                raise Reject("temporary total at the start of the award")
        for k, sg in segs.items():                     # 3.105(e) needs a payment actually reduced
            for i, (st, r, kind) in enumerate(sg):
                if kind == "down":
                    prev_m = date((st - DAY).year, (st - DAY).month, 1)
                    if basis.get(prev_m, 0) <= basis.get(st, 0) or basis.get(prev_m, 0) == 100:
                        raise Reject("reduction that does not reduce the payment")
    deps = []
    for dp in vet["dependents"]:
        ev, rec = dp["event"], dp["received"]
        lim = year_after(ev)
        if strict:
            check_limit(lim, rec)
            if ev < start and not (rec == vet["first_claim"] == start):
                raise Reject("dependent before an award that starts before its claim")
        basis_d = ev if rec <= lim else rec
        if strict and rec > lim:                       # a qualifying rating established between event and report
            changes = [st for sg in segs.values() for st, _, _ in sg] + [t[0] for t in totals]
            for c in changes:
                if ev <= c < rec and basis.get(next_month(c), 0) >= 30:
                    raise Reject("late report after a newly established rating (3.401(b)(3) against 5110(f))")
        deps.append((max(basis_d, start), dp["rel"]))
    remaining = vet["sep_pay"][0] - vet["sep_pay"][1] if vet["sep_pay"] else 0
    if strict and remaining:
        for k, sg in segs.items():
            for st, r, kind in sg:
                if kind == "down":
                    raise Reject("reduction for a veteran with separation pay")
    out = {}
    for m in months:
        p, r = m - DAY, basis[m]
        spouse = sum(1 for e, rel in deps if rel == "spouse" and e <= p) if r >= 30 else 0
        kids = sum(1 for e, rel in deps if rel == "child" and e <= p) if r >= 30 else 0
        amt = rate(m, r, spouse, kids) if r else 0
        held = min(amt, remaining)
        remaining -= held
        out[m] = (r, spouse, kids, amt - held)
    m = FIRST
    while m < next_month(start):
        out[m] = (0, 0, 0, 0)
        m = next_month(m)
    return out


# ---------------------------------------------------------------- building veterans
def V(sep, disabilities, dependents=(), sep_pay=None, stays=()):
    vet = {"separation": D(sep), "disabilities": {}, "dependents": [], "sep_pay": sep_pay, "stays": []}
    for i, (desc, code, limb, side, actions) in enumerate(disabilities):
        acts = []
        for t, r, s, g in actions:
            if t == "reduction":
                acts.append({"type": t, "notice": D(r), "rating": g, "received": None, "shown": None})
            else:
                acts.append({"type": t, "received": D(r), "shown": D(s), "rating": g})
        vet["disabilities"][f"D{i + 1}"] = {"desc": desc, "code": code, "limb": limb, "side": side, "actions": acts}
    vet["dependents"] = [{"rel": rel, "event": D(e), "received": D(r)} for rel, e, r in dependents]
    for st in stays:
        st = dict(st)
        for key in ("admitted", "sc_from", "discharged", "start", "released"):
            if key in st:
                st[key] = D(st[key])
        st["absences"] = [(D(a), D(b)) for a, b in st.get("absences", [])]
        if st["kind"] == "hospital":
            st.setdefault("sc_from", st["admitted"])
        st.setdefault("months", 0)
        vet["stays"].append(st)
    vet["first_claim"] = min(a["received"] for x in vet["disabilities"].values() for a in x["actions"] if a["received"])
    return vet


def H(dkey, admitted, discharged, absences=(), months=0, sc_from=None):
    return {"kind": "hospital", "disability": dkey, "admitted": admitted, "discharged": discharged,
            "absences": list(absences), "months": months, **({"sc_from": sc_from} if sc_from else {})}


def C(dkey, start, released, months):
    return {"kind": "convalescence", "disability": dkey, "start": start, "released": released, "months": months}


PTSD = ("posttraumatic stress disorder", "9411", None, None)
BACK = ("lumbosacral strain", "5237", None, None)
TIN = ("tinnitus, recurrent", "6260", None, None)


def leg(desc, code, side):
    return (desc.format(side=side), code, "leg", side)


def arm(desc, code, side):
    return (desc.format(side=side), code, "arm", side)


def planted():
    out = []
    # one year after separation (3.110: the last day counts): separated May 9 2023, claim May 9 2024: effective May
    # 10 2023, paid from June 2023. A claim on May 10 2024 is effective that day, paid from June 2024
    for rec, first in (("2024-05-09", "2023-06"), ("2024-05-10", "2024-06")):
        out.append((V("2023-05-09", [TIN + ([("original", rec, "2022-11-01", 10)],)]), ["original-claim", "payment-start", "boundary"],
                    {first: (10, 0, 0)}))
    # late claim, spouse below 30%, increase shown within the year: 30% from Feb 2 2024, paid with the spouse from March
    out.append((V("2021-08-15", [leg("{side} knee strain with limitation of flexion", "5260", "right") +
                                 ([("original", "2023-01-10", "2021-05-01", 20), ("increase", "2024-05-20", "2024-02-02", 30)],)],
                  [("spouse", "2015-06-20", "2023-01-10")]),
                ["original-claim", "increase", "dependents", "payment-start"],
                {"2023-01": (0, 0, 0), "2023-02": (20, 0, 0), "2024-02": (20, 0, 0), "2024-03": (30, 1, 0)}))
    # increase shown exactly a year before the claim (Apr 15 2024, claim Apr 15 2025): effective Apr 15 2024; shown a
    # day earlier: effective on the claim date
    for shown, first in (("2024-04-15", "2024-05"), ("2024-04-14", "2025-05")):
        out.append((V("2020-09-30", [PTSD + ([("original", "2022-06-01", "2020-01-01", 30), ("increase", "2025-04-15", shown, 50)],)]),
                    ["increase", "boundary"], {first: (50, 0, 0)}))
    # increase shown after its claim: effective when shown (Mar 3 2026), paid from April 2026
    out.append((V("2020-09-30", [PTSD + ([("original", "2022-06-01", "2020-01-01", 50), ("increase", "2026-01-12", "2026-03-03", 70)],)]),
                ["increase", "payment-start"], {"2026-03": (50, 0, 0), "2026-04": (70, 0, 0)}))
    # bilateral factor across joints: 30 and 10 combine to 37, plus 3.7 = 41 (rounded); with 10: 47, rated 50
    out.append((V("2022-03-31", [leg("{side} knee strain with limitation of flexion", "5260", "right") + ([("original", "2022-12-01", "2021-11-01", 30)],),
                                 leg("{side} ankle, limited motion", "5271", "left") + ([("original", "2022-12-01", "2022-01-15", 10)],),
                                 TIN + ([("original", "2022-12-01", "2021-06-01", 10)],)]),
                ["bilateral", "combined-ratings"], {"2023-01": (50, 0, 0)}))
    # an arm and a leg are not paired: 30 and 20 combine to 44, rated 40
    out.append((V("2022-10-15", [arm("{side} shoulder impingement, limitation of motion of the arm", "5201", "right") + ([("original", "2023-02-10", "2022-04-01", 30)],),
                                 leg("{side} knee strain with limitation of flexion", "5260", "left") + ([("original", "2023-02-10", "2022-06-01", 20)],)]),
                ["bilateral", "combined-ratings"], {"2023-01": (40, 0, 0)}))
    # 0% on one side is not compensable (4.26(c)): 30 and 20 combine to 44, rated 40
    out.append((V("2022-05-20", [leg("{side} knee strain with limitation of flexion", "5260", "left") + ([("original", "2022-11-01", "2022-02-01", 0)],),
                                 leg("{side} knee strain with limitation of flexion", "5260", "right") + ([("original", "2022-11-01", "2022-02-01", 30)],),
                                 BACK + ([("original", "2022-11-01", "2022-03-01", 20)],)]),
                ["bilateral", "combined-ratings"], {"2023-01": (40, 0, 0)}))
    # the table, not exact arithmetic: legs 10 and 10 combine to 19, plus 1.9 = 21; with 30: 30 and 21 give 45 (44.7
    # exactly), rated 50 (40 by exact arithmetic)
    out.append((V("2022-06-30", [leg("{side} knee strain with limitation of flexion", "5260", "left") + ([("original", "2023-01-05", "2022-01-01", 10)],),
                                 leg("{side} knee strain with limitation of flexion", "5260", "right") + ([("original", "2023-01-05", "2022-01-01", 10)],),
                                 PTSD + ([("original", "2023-01-05", "2022-02-01", 30)],)]),
                ["combined-ratings", "bilateral"], {"2023-01": (50, 0, 0)}))
    # four extremities (4.26(b)): one factor over all four: 40, 20, 20 and 10 combine to 73, plus 7.3 = 80; with
    # tinnitus 10: 82, rated 80 (two separate factors would give 70)
    out.append((V("2022-02-28", [arm("{side} elbow tendinitis, limitation of flexion", "5206", "left") + ([("original", "2022-09-01", "2021-08-01", 10)],),
                                 arm("{side} shoulder impingement, limitation of motion of the arm", "5201", "right") + ([("original", "2022-09-01", "2021-08-01", 20)],),
                                 leg("{side} hip, limitation of flexion", "5252", "left") + ([("original", "2022-09-01", "2021-08-01", 20)],),
                                 leg("radiculopathy, {side} lower extremity (sciatic nerve)", "8520", "right") + ([("original", "2022-09-01", "2021-08-01", 40)],),
                                 TIN + ([("original", "2022-09-01", "2021-08-01", 10)],)]),
                ["bilateral", "combined-ratings"], {"2023-01": (80, 0, 0)}))
    # 4.26(d): with two 10% disabilities on each leg and two 50% ratings, all four in the factor give 80; leaving one
    # left-leg 10% out gives 90, the most favorable
    out.append((V("2022-08-31", [leg("{side} knee strain with limitation of flexion", "5260", "left") + ([("original", "2023-03-01", "2022-01-01", 10)],),
                                 leg("{side} ankle, limited motion", "5271", "left") + ([("original", "2023-03-01", "2022-01-01", 10)],),
                                 leg("{side} knee strain with limitation of flexion", "5260", "right") + ([("original", "2023-03-01", "2022-01-01", 10)],),
                                 leg("{side} hip, limitation of flexion", "5252", "right") + ([("original", "2023-03-01", "2022-01-01", 10)],),
                                 PTSD + ([("original", "2023-03-01", "2022-01-01", 50)],),
                                 ("obstructive sleep apnea", "6847", None, None, [("original", "2023-03-01", "2022-01-01", 50)])]),
                ["bilateral", "combined-ratings"], {"2023-01": (90, 0, 0)}))
    # dependents (3.401(b)): reported within the year counts from the birth; reported later counts from the report;
    # a marriage reported on its anniversary counts from the marriage, a day later from the report
    out.append((V("2022-01-31", [PTSD + ([("original", "2022-06-01", "2021-10-01", 50)],)],
                  [("child", "2024-03-10", "2024-12-01"), ("child", "2023-01-05", "2024-06-03"), ("spouse", "2024-09-10", "2025-09-10")]),
                ["dependents", "payment-start", "boundary"],
                {"2024-03": (50, 0, 0), "2024-04": (50, 0, 1), "2024-07": (50, 0, 2), "2024-10": (50, 1, 2)}))
    out.append((V("2022-01-31", [PTSD + ([("original", "2022-06-01", "2021-10-01", 50)],)], [("spouse", "2024-09-10", "2025-09-11")]),
                ["dependents", "boundary"], {"2025-09": (50, 0, 0), "2025-10": (50, 1, 0)}))
    # separation pay of 15,000.00 less 3,300.00 tax is withheld from compensation
    out.append((V("2023-02-28", [("obstructive sleep apnea", "6847", None, None, [("original", "2023-09-05", "2022-12-01", 50)])],
                  sep_pay=(1500000, 330000)), ["separation-pay"], {"2023-03": (0, 0, 0), "2023-04": (50, 0, 0)}))
    # 3.105(e): reduction from 70 to 50 with final notice Mar 3 2025: 60 days end May 2, effective May 31: June at 50
    out.append((V("2021-12-31", [PTSD + ([("original", "2022-04-01", "2021-06-01", 70), ("reduction", "2025-03-03", None, 50)],)]),
                ["reduction"], {"2025-05": (70, 0, 0), "2025-06": (50, 0, 0)}))
    # a reduction of the left knee to 0% removes the bilateral factor: 20, 20 and 10 give 50 (36 + 3.6 = 40; 46), then
    # 20 and 10 give 30 from October 2025 (notice Jul 15 2025, 60 days end Sep 13, effective Sep 30)
    out.append((V("2021-10-31", [leg("{side} knee strain with limitation of flexion", "5260", "left") + ([("original", "2022-03-01", "2021-06-01", 20), ("reduction", "2025-07-15", None, 0)],),
                                 leg("{side} knee strain with limitation of flexion", "5260", "right") + ([("original", "2022-03-01", "2021-06-01", 20)],),
                                 TIN + ([("original", "2022-03-01", "2021-06-01", 10)],)]),
                ["reduction", "bilateral"], {"2025-09": (50, 0, 0), "2025-10": (30, 0, 0)}))
    # 4.29 hospital ratings for one veteran (PTSD 50): Feb 5 to Mar 20 2024: 100% paid for March only; Jul 2 to Jul 29
    # 2024 (one calendar month): 3.31(c)(5), July paid at 100%; Sep 3 2024 with an absence Sep 10-15 (more than 4
    # days in the first 21): treated as discharged Sep 10, no total rating; Nov 4 2024 with absences of 4, 4 and 1
    # days: discharged on the ninth day of absence (Nov 18), no total rating
    out.append((V("2021-11-30", [PTSD + ([("original", "2022-05-02", "2021-06-01", 50)],)],
                  stays=[H("D1", "2024-02-05", "2024-03-20"), H("D1", "2024-07-02", "2024-07-29"),
                         H("D1", "2024-09-03", "2024-10-20", [("2024-09-10", "2024-09-15")]),
                         H("D1", "2024-11-04", "2024-12-20", [("2024-11-06", "2024-11-09"), ("2024-11-12", "2024-11-15"), ("2024-11-18", "2024-11-18")])]),
                ["temporary-total", "payment-start"],
                {"2024-02": (50, 0, 0), "2024-03": (100, 0, 0), "2024-04": (50, 0, 0), "2024-06": (50, 0, 0), "2024-07": (100, 0, 0),
                 "2024-08": (50, 0, 0), "2024-10": (50, 0, 0), "2024-12": (50, 0, 0)}))
    # absences totalling exactly 8 days are not more than 8: total from Nov 4 2024, paid for December
    out.append((V("2021-11-30", [PTSD + ([("original", "2022-05-02", "2021-06-01", 50)],)],
                  stays=[H("D1", "2024-11-04", "2024-12-20", [("2024-11-06", "2024-11-09"), ("2024-11-12", "2024-11-15")])]),
                ["temporary-total", "boundary"], {"2024-11": (50, 0, 0), "2024-12": (100, 0, 0), "2025-01": (50, 0, 0)}))
    # back 40: absence Feb 10-28 2025 after day 21 (19 days): interrupted Feb 28, February at 100%; admitted May 1 2025
    # for another condition, service-connected treatment from May 20 (4.29(b)): June at 100%; outpatient surgery Aug 14
    # 2025 with 2 months (4.30): September and October at 100%; Oct 1 to Nov 10 2025 plus 1 month (4.29(e)): November
    # and December at 100%
    out.append((V("2021-07-31", [BACK + ([("original", "2022-01-14", "2021-03-01", 40)],)],
                  stays=[H("D1", "2025-01-06", "2025-03-01", [("2025-02-10", "2025-02-28")]),
                         H("D1", "2025-05-01", "2025-06-25", sc_from="2025-05-20"), C("D1", "2025-08-14", "2025-08-14", 2),
                         H("D1", "2025-10-01", "2025-11-10", months=1)]),
                ["temporary-total"],
                {"2025-01": (40, 0, 0), "2025-02": (100, 0, 0), "2025-03": (40, 0, 0), "2025-05": (40, 0, 0), "2025-06": (100, 0, 0),
                 "2025-07": (40, 0, 0), "2025-08": (40, 0, 0), "2025-09": (100, 0, 0), "2025-10": (100, 0, 0), "2025-11": (100, 0, 0),
                 "2025-12": (100, 0, 0), "2026-01": (40, 0, 0)}))
    # a spouse of a veteran rated 20% is paid only during a convalescent total (Mar 5-7 2024, 3 months: April-June)
    out.append((V("2022-04-30", [BACK + ([("original", "2022-10-03", "2021-12-01", 20)],)], [("spouse", "2023-06-10", "2023-07-01")],
                  stays=[C("D1", "2024-03-05", "2024-03-07", 3)]),
                ["temporary-total", "dependents"],
                {"2024-03": (20, 0, 0), "2024-04": (100, 1, 0), "2024-06": (100, 1, 0), "2024-07": (20, 0, 0)}))
    # 50 and 30 combine to 65, rated 70 (5 rounds up)
    out.append((V("2022-11-30", [PTSD + ([("original", "2023-01-20", "2022-08-01", 50)],),
                                 ("migraine headaches", "8100", None, None, [("original", "2023-01-20", "2022-03-01", 30)])]),
                ["combined-ratings"], {"2023-01": (70, 0, 0)}))
    return out


SIDES = ("left", "right")


def boundary_after(limit):
    """A receipt on the last day or the day after, with the last day a workday."""
    if not workday(limit):
        return None
    return limit + (DAY if rng.random() < 0.5 else timedelta(0))


def filler():
    sep = date(2019, 7, 1) + days(rng.randrange(0, 2190))
    if rng.random() < 0.3:
        sep = month_end(sep)
    if sep > date(2025, 6, 30):
        return None
    mode = rng.random()
    if mode < 0.25:
        r0 = boundary_after(year_after(sep))
        if r0 is None:
            return None
    elif mode < 0.65:
        r0 = sep + days(rng.randrange(20, 340))
    else:
        r0 = year_after(sep) + days(rng.randrange(20, 900))
    if r0 > date(2026, 6, 30):
        return None
    k = rng.choice([1, 2, 3, 3, 4, 5, 6])
    picks, used = [], set()
    for _ in range(k):
        desc, code, limb, ratings = rng.choice(CATALOG)
        side = rng.choice(SIDES) if limb else None
        if (desc, side) in used or (limb is None and any(p[0] == desc for p in picks)):
            continue
        used.add((desc, side))
        picks.append((desc, code, limb, side, ratings))
    for _ in range(rng.choice([0, 1, 1, 2, 3])):          # more limb disabilities, often on the other side
        limbs = [p for p in picks if p[2]]
        if not limbs:
            break
        desc, code, limb, side, ratings = rng.choice(limbs)
        other = rng.choice(["left", "right"] if rng.random() < 0.3 else ["left" if side == "right" else "right"])
        c = rng.choice([x for x in CATALOG if x[2] == limb])
        if (c[0], other) not in used:
            used.add((c[0], other))
            picks.append((c[0], c[1], c[2], other, c[3]))
    dis = []
    for desc, code, limb, side, ratings in picks:
        rec = r0 if rng.random() < 0.8 else r0 + days(rng.randrange(60, 700))
        if rec > date(2026, 7, 31):
            continue
        if rec <= year_after(sep):
            shown = sep - days(rng.randrange(10, 700))
        else:
            shown = rng.choice([sep - days(rng.randrange(10, 700)), sep + days(rng.randrange(10, 300)),
                                rec + days(rng.randrange(5, 90))])
        g = rng.choice(ratings[:-1] if len(ratings) > 1 else ratings)
        actions = [("original", rec, shown, g)]
        cur = max(rec, shown) if rec > year_after(sep) else rec
        higher = [x for x in ratings if x > g]
        while higher and rng.random() < 0.5:
            ri = cur + days(rng.randrange(150, 700))
            if ri > date(2026, 8, 10):
                break
            pick = rng.random()
            if pick < 0.35:
                lim_shown = year_before(ri) - (DAY if rng.random() < 0.5 else timedelta(0))
                si = lim_shown
            elif pick < 0.6:
                si = ri - days(rng.randrange(20, 330))
            elif pick < 0.85:
                si = ri - days(rng.randrange(400, 800))
            else:
                si = ri + days(rng.randrange(5, 60))
            gi = rng.choice(higher)
            actions.append(("increase", ri, si, gi))
            higher = [x for x in ratings if x > gi]
            cur = max(ri, si)
        lower = [x for x in ratings if x < actions[-1][3]]
        if lower and rng.random() < 0.4:
            n = cur + days(rng.randrange(200, 700))
            if n < date(2026, 7, 1):
                actions.append(("reduction", n, None, rng.choice(lower)))
        desc_full = desc.format(side=side) if "{side}" in desc else desc
        dis.append((desc_full, code, limb, side, actions))
    if not dis:
        return None
    deps = []
    rec_first = min(a[1] for x in dis for a in x[4] if a[0] != "reduction")
    late = rec_first > year_after(sep)
    for rel, count in (("spouse", 1 if rng.random() < 0.55 else 0), ("child", rng.choice([0, 0, 1, 1, 2, 3]))):
        for _ in range(count):
            if late and rng.random() < 0.5:
                ev = sep - days(rng.randrange(200, 3500)) if rel == "spouse" else max(date(2009, 1, 1), sep - days(rng.randrange(100, 3500)))
                deps.append((rel, ev, rec_first))
                continue
            ev = r0 + days(rng.randrange(30, 1000))
            x = rng.random()
            if x < 0.3:
                rec = boundary_after(year_after(ev))
                if rec is None:
                    continue
            elif x < 0.7:
                rec = ev + days(rng.randrange(10, 330))
            else:
                rec = ev + days(rng.randrange(380, 700))
            if rec < date(2026, 8, 31):
                deps.append((rel, ev, rec))
    stays = []
    keys = [f"D{i + 1}" for i in range(len(dis))]
    t = r0 + days(rng.randrange(120, 400))
    while rng.random() < 0.75 and t < date(2026, 6, 1):
        kind = rng.random()
        if kind < 0.3:
            stays.append(C(rng.choice(keys), t, t + days(rng.choice([0, 0, 2, 5])), rng.choice([1, 2, 3])))
            t = t + days(rng.randrange(150, 400))
            continue
        adm = t
        length = rng.choice([10, 15, 18, 24, 26, 30, 45, 60]) if rng.random() < 0.8 else rng.randrange(24, 90)
        absences = []
        z = rng.random()
        if z < 0.25:                                   # short absences in the first 21 days
            total_target = rng.choice([8, 9])
            d0 = adm + days(2)
            remain = total_target
            while remain > 0:
                ln = min(remain, rng.choice([2, 3, 4]))
                absences.append((d0, d0 + days(ln - 1)))
                remain -= ln
                d0 = d0 + days(ln + 1)
            if (absences[-1][1] - adm).days + 1 >= 19:
                absences = []
        elif z < 0.38:
            a = adm + days(rng.randrange(3, 12))
            absences.append((a, a + days(rng.choice([4, 5, 7]) - 1)))
        elif z < 0.55 and length >= 45:
            a = adm + days(rng.randrange(25, 30))
            ln = rng.choice([14, 15, 20])
            absences.append((a, a + days(ln - 1)))
            length = max(length, (a + days(ln) - adm).days)
        sc_from = adm + days(rng.choice([5, 10, 18])) if (rng.random() < 0.15 and not absences) else None
        months = rng.choice([0, 0, 0, 1, 2, 3]) if not any((b - a).days >= 13 for a, b in absences) else 0
        stays.append(H(rng.choice(keys), adm, adm + days(length), absences, months, sc_from))
        t = adm + days(length) + days(rng.randrange(150, 400))
    sep_pay = None
    if rng.random() < 0.2:
        g = rng.randrange(400000, 2600000)
        sep_pay = (g, g * 22 // 100)
    vet = V(sep, dis, deps, sep_pay, stays)
    try:
        res = sim(vet)
    except Reject:
        return None
    if strict_overlap(vet):
        return None
    if not any(v[3] for v in res.values()):
        return None
    return vet, res


def strict_overlap(vet):
    """Temporary totals must not overlap each other or a rating change."""
    tt = temp_totals(vet, strict=False)
    for (s1, e1, _), (s2, e2, _) in zip(tt, tt[1:]):
        if s2 <= next_month(e1):
            return True
    changes = [st for sg in segments(vet, strict=False).values() for st, _, _ in sg]
    for s, e, _ in tt:
        if any(date(s.year, s.month, 1) - days(31) <= c <= next_month(e) for c in changes):
            return True
    return False


def main():
    vets = []
    for vet, tags, expect in planted():
        res = sim(vet)
        for mk, want in expect.items():
            m = date(int(mk[:4]), int(mk[5:]), 1)
            assert res[m][:3] == want, (tags, mk, res[m], want)
        vets.append((vet, tags, True))
    rejected = 0
    n_planted = len(vets)
    while len(vets) < n_planted + 200:
        x = filler()
        if x is None:
            rejected += 1
            continue
        vets.append((x[0], ["filler"], False))
    rng.shuffle(vets)
    vet_out, dis_out, dec_out, dep_out, stay_out, golden, tags_out, sim_all = [], [], [], [], [], {}, {}, {}
    n_dis = n_dec = n_stay = 0
    for i, (vet, tags, planted_) in enumerate(vets, 1):
        vid = f"V{i:04d}"
        vet_out.append({"veteran_id": vid, "last_day_of_active_service": vet["separation"].isoformat(),
                        "separation_pay": None if not vet["sep_pay"] else {
                            "kind": "nondisability separation pay", "gross_cents": vet["sep_pay"][0],
                            "federal_income_tax_withheld_cents": vet["sep_pay"][1]}})
        ids = {}
        for k, dsb in vet["disabilities"].items():
            n_dis += 1
            did = ids[k] = f"DX{n_dis:05d}"
            dis_out.append({"disability_id": did, "veteran_id": vid, "description": dsb["desc"][0].upper() + dsb["desc"][1:],
                            "diagnostic_code": dsb["code"]})
            for a in dsb["actions"]:
                n_dec += 1
                rec = {"decision_id": f"RD{n_dec:05d}", "disability_id": did, "decision": a["type"],
                       "claim_received": a["received"] and a["received"].isoformat(),
                       "evidence_first_shows_on": a["shown"] and a["shown"].isoformat(),
                       "notice_of_final_reduction_sent": a.get("notice") and a["notice"].isoformat(),
                       "rating_percent": a["rating"]}
                dec_out.append(rec)
        for dp in vet["dependents"]:
            dep_out.append({"veteran_id": vid, "relationship": dp["rel"], "date_of_marriage_or_birth": dp["event"].isoformat(),
                            "reported_to_va_on": dp["received"].isoformat()})
        for st in vet["stays"]:
            n_stay += 1
            if st["kind"] == "hospital":
                stay_out.append({"record_id": f"H{n_stay:05d}", "veteran_id": vid, "disability_id": ids[st["disability"]],
                                 "kind": "hospital treatment", "admitted": st["admitted"].isoformat(),
                                 "treatment_for_this_disability_began": st["sc_from"].isoformat(),
                                 "discharged": st["discharged"].isoformat(),
                                 "authorized_absences": [{"first_day_absent": a.isoformat(), "last_day_absent": b.isoformat()}
                                                         for a, b in st["absences"]],
                                 "convalescence_months_granted": st["months"]})
            else:
                stay_out.append({"record_id": f"H{n_stay:05d}", "veteran_id": vid, "disability_id": ids[st["disability"]],
                                 "kind": "surgery or cast", "admitted": st["start"].isoformat(),
                                 "treatment_for_this_disability_began": st["start"].isoformat(),
                                 "discharged": st["released"].isoformat(), "authorized_absences": [],
                                 "convalescence_months_granted": st["months"]})
        res = sim(vet, strict=False)
        m = FIRST
        while m <= LASTM:
            r, _, _, paid = res[m]
            key = f"{vid},{m.year:04d}-{m.month:02d}"
            row = {"combined_rating": str(r), "payment": f"{paid // 100}.{paid % 100:02d}"}
            sim_all[key] = row
            tags_out[key] = tags
            if planted_:
                golden[key] = row
            m = next_month(m)
    dec_out.sort(key=lambda d: (d["claim_received"] or d["notice_of_final_reduction_sent"], d["decision_id"]))
    stay_out.sort(key=lambda s: (s["admitted"], s["record_id"]))
    ENV.mkdir(parents=True, exist_ok=True)
    for old in ENV.iterdir():
        old.unlink()
    dump = lambda name, o: (ENV / name).write_text(json.dumps(o, indent=1) + "\n")  # noqa: E731
    dump("veterans.json", vet_out)
    dump("disabilities.json", dis_out)
    dump("rating_decisions.json", dec_out)
    dump("dependents.json", dep_out)
    dump("hospital_and_convalescence.json", stay_out)
    dump("compensation_rates.json", [{"effective_date": eff.isoformat(),
                                      "monthly_rates_cents": {str(r): row for r, row in t.items()}} for eff, t in TABLES])
    if TST.exists():
        shutil.rmtree(TST)
    shutil.copytree(ENV, TST)
    (ROOT / "tests" / "case_tags.json").write_text(json.dumps(tags_out, indent=0, sort_keys=True) + "\n")
    (ROOT / "tests" / "golden.json").write_text(json.dumps(golden, indent=0, sort_keys=True) + "\n")
    (Path(__file__).resolve().parent / "sim_answers.json").write_text(json.dumps(sim_all, indent=0) + "\n")
    print(len(vets), "veterans,", len(dis_out), "disabilities,", len(dec_out), "decisions,", len(dep_out), "dependents,",
          len(stay_out), "hospital/convalescence records,", len(sim_all), "rows,", len(golden), "planted rows,", rejected, "rejected")


if __name__ == "__main__":
    main()
