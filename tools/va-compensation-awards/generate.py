#!/usr/bin/env python3
"""Generate the va-compensation-awards inputs (dev only, never shipped).

A VA regional office's awards team must state, for each veteran and each month from January 2023 to September
2026, the combined disability rating in effect at the end of the month and the compensation actually paid for the
month. That depends on: effective dates of original awards (38 CFR 3.400(b)(2): day after separation for a claim
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


# ---------------------------------------------------------------- disabilities
CATALOG = [
    # description template, diagnostic code, limb, ratings
    ("{side} knee strain with limitation of flexion", "5260", "leg", [0, 10, 20, 30]),
    ("{side} ankle, limited motion", "5271", "leg", [10, 20]),
    ("{side} hip, limitation of flexion", "5252", "leg", [10, 20, 30]),
    ("plantar fasciitis, {side} foot", "5269", "leg", [10, 20, 30]),
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


class Reject(Exception):
    pass


def round_half_up(x):
    return int(Fraction(x) + Fraction(1, 2))


def combine(values, mode):
    """Combine values (largest first) with the combined ratings table: 'table' rounds each step to the nearest
    whole number, 'exact' keeps fractions."""
    vals = sorted(values, reverse=True)
    if not vals:
        return Fraction(0)
    acc = Fraction(vals[0])
    for v in vals[1:]:
        acc = acc + Fraction(v) * (100 - acc) / 100
        if mode == "table":
            acc = Fraction(round_half_up(acc))
    return acc


def to_ten(x):
    return int((Fraction(x) + 5) // 10) * 10


def combined_rating(dis, strict=True):
    """dis: list of (rating, limb, side) in effect. Returns the combined rating; strict rejects open readings."""
    comp = [d for d in dis if d[0] > 0]
    results = set()
    for step, bil in (("table", "round"), ("exact", "exact"), ("table", "exact"), ("exact", "round")):
        groups = {}
        for limb in ("arm", "leg"):
            sides = {d[2] for d in comp if d[1] == limb}
            if sides == {"left", "right"}:
                groups[limb] = [d[0] for d in comp if d[1] == limb]
        if len(groups) == 2 and strict:
            raise Reject("both arms and both legs")
        values = [d[0] for d in comp if d[1] not in groups]
        for g in groups.values():
            v = combine(g, step)
            v = v + v / 10
            values.append(Fraction(round_half_up(v)) if bil == "round" else v)
        results.add(to_ten(combine(values, step)))
    if strict and len(results) > 1:
        raise Reject("rounding readings differ")
    return min(results)


def effective_dates(vet, strict=True):
    """[(effective date, disability key, rating)] in effect order."""
    sep = vet["separation"]
    out = []
    for k, dsb in vet["disabilities"].items():
        prev = None
        for a in dsb["actions"]:
            rec, shown = a["received"], a["shown"]
            if a["type"] == "original":
                if strict and abs((rec - year_after(sep)).days) <= 7:
                    raise Reject("claim near the end of the year after separation")
                if rec <= year_after(sep):
                    if strict and shown > sep:
                        raise Reject("shown after separation, claim within the year")
                    eff = sep + DAY
                else:
                    eff = max(rec, shown)
            else:
                if strict and (abs((shown - year_before(rec)).days) <= 7 or (prev is not None and shown <= prev)):
                    raise Reject("increase shown about a year before the claim, or before the earlier rating")
                if shown > rec:
                    eff = shown
                elif year_after(shown) >= rec:
                    eff = shown
                else:
                    eff = rec
                if strict and (prev is None or eff <= prev):
                    raise Reject("increase not after the earlier effective date")
            prev = eff
            out.append((eff, k, a["rating"]))
    return sorted(out, key=lambda x: x[0])


def sim(vet, strict=True):
    """Third implementation: {month first day: (combined at end of month, paid rating, spouse, children, cents)}."""
    effs = effective_dates(vet, strict)
    if not effs:
        raise Reject("no award")
    start = effs[0][0]

    def state(day):
        cur = {}
        for eff, k, r in effs:
            if eff <= day:
                cur[k] = r
        dis = [(r, vet["disabilities"][k]["limb"], vet["disabilities"][k]["side"]) for k, r in cur.items()]
        return combined_rating(dis, strict) if dis else 0

    # dependents (3.401(b)): event date if notice within a year of it, else the notice date; never before the award
    deps = []
    for dp in vet["dependents"]:
        ev, rec = dp["event"], dp["received"]
        if strict and abs((rec - year_after(ev)).days) <= 7:
            raise Reject("dependent notice about a year after the event")
        basis = ev if rec <= year_after(ev) else rec
        if strict and ev < start and not (rec == vet["first_claim"] == start):
            raise Reject("dependent before an award that starts before its claim")
        deps.append((max(basis, start), dp["rel"]))
    remaining = vet["sep_pay"][0] - vet["sep_pay"][1] if vet["sep_pay"] else 0
    out = {}
    m = next_month(start)
    while m <= LASTM:
        d = m - DAY
        r = state(d)
        spouse = sum(1 for e, rel in deps if rel == "spouse" and e <= d)
        kids = sum(1 for e, rel in deps if rel == "child" and e <= d)
        amt = rate(m, r, spouse, kids) if r else 0
        held = min(amt, remaining)
        remaining -= held
        out[m] = (state(next_month(m) - DAY), r, spouse if r >= 30 else 0, kids if r >= 30 else 0, amt - held)
        m = next_month(m)
    m = FIRST
    while m < next_month(start):
        out[m] = (state(next_month(m) - DAY), 0, 0, 0, 0)
        m = next_month(m)
    return out


# ---------------------------------------------------------------- building veterans
def V(sep, disabilities, dependents=(), sep_pay=None):
    vet = {"separation": D(sep), "disabilities": {}, "dependents": [], "sep_pay": sep_pay}
    for i, (desc, code, limb, side, actions) in enumerate(disabilities):
        vet["disabilities"][f"D{i + 1}"] = {
            "desc": desc, "code": code, "limb": limb, "side": side,
            "actions": [{"type": t, "received": D(r), "shown": D(s), "rating": g} for t, r, s, g in actions]}
    vet["dependents"] = [{"rel": rel, "event": D(e), "received": D(r)} for rel, e, r in dependents]
    vet["first_claim"] = min(a["received"] for x in vet["disabilities"].values() for a in x["actions"])
    return vet


def planted():
    out = []
    # 3.400(b)(2) and 3.31: separated Jun 30 2023, claim Mar 15 2024 (within the year): effective Jul 1 2023, paid
    # from August 2023
    out.append((V("2023-06-30", [("tinnitus, recurrent", "6260", None, None, [("original", "2024-03-15", "2023-03-01", 10)])]),
                ["original-claim", "payment-start"],
                {"2023-06": (0, 0, 0, 0), "2023-07": (10, 0, 0, 0), "2023-08": (10, 10, 0, 0)}))
    # claim more than a year after separation: effective on receipt (Jan 10 2023), paid from February. The spouse
    # (married 2015, reported with the claim) adds nothing below 30%. Knee increase claimed May 20 2024, first shown
    # Feb 2 2024 (within the year before): 30% from Feb 2 2024, paid with the spouse from March 2024
    out.append((V("2021-08-15", [("right knee strain with limitation of flexion", "5260", "leg", "right",
                                  [("original", "2023-01-10", "2021-05-01", 20), ("increase", "2024-05-20", "2024-02-02", 30)])],
                  [("spouse", "2015-06-20", "2023-01-10")]),
                ["original-claim", "increase", "dependents", "payment-start"],
                {"2023-01": (20, 0, 0, 0), "2023-02": (20, 20, 0, 0), "2024-02": (30, 20, 0, 0), "2024-03": (30, 30, 1, 0)}))
    # increase shown more than a year before the claim: effective on the claim date (May 20 2025), paid from June;
    # a later increase shown after its claim (Mar 3 2026) is effective when shown, paid from April 2026
    out.append((V("2020-09-30", [("posttraumatic stress disorder", "9411", None, None,
                                  [("original", "2022-06-01", "2020-01-01", 30), ("increase", "2025-05-20", "2024-04-01", 50),
                                   ("increase", "2026-01-12", "2026-03-03", 70)])]),
                ["increase", "payment-start"],
                {"2025-05": (50, 30, 0, 0), "2025-06": (50, 50, 0, 0), "2026-03": (70, 50, 0, 0), "2026-04": (70, 70, 0, 0)}))
    # bilateral factor across different joints: right knee 30 and left ankle 10 combine to 37, plus 3.7 = 40.7;
    # with tinnitus 10: 46.6, rated 50. Without the factor it would be 40
    out.append((V("2022-03-31", [("right knee strain with limitation of flexion", "5260", "leg", "right", [("original", "2022-12-01", "2021-11-01", 30)]),
                                 ("left ankle, limited motion", "5271", "leg", "left", [("original", "2022-12-01", "2022-01-15", 10)]),
                                 ("tinnitus, recurrent", "6260", None, None, [("original", "2022-12-01", "2021-06-01", 10)])]),
                ["bilateral", "combined-ratings"], {"2023-01": (50, 50, 0, 0)}))
    # an arm and a leg are not bilateral: right shoulder 30 and left knee 20 combine to 44, rated 40
    out.append((V("2022-10-15", [("right shoulder impingement, limitation of motion of the arm", "5201", "arm", "right", [("original", "2023-02-10", "2022-04-01", 30)]),
                                 ("left knee strain with limitation of flexion", "5260", "leg", "left", [("original", "2023-02-10", "2022-06-01", 20)])]),
                ["bilateral", "combined-ratings"], {"2023-01": (40, 40, 0, 0)}))
    # a 0% left knee is not a compensable disability, so no bilateral factor: 30 and 20 combine to 44, rated 40
    out.append((V("2022-05-20", [("left knee strain with limitation of flexion", "5260", "leg", "left", [("original", "2022-11-01", "2022-02-01", 0)]),
                                 ("right knee strain with limitation of flexion", "5260", "leg", "right", [("original", "2022-11-01", "2022-02-01", 30)]),
                                 ("lumbosacral strain", "5237", None, None, [("original", "2022-11-01", "2022-03-01", 20)])]),
                ["bilateral", "combined-ratings"], {"2023-01": (40, 40, 0, 0)}))
    # bilateral radiculopathy of the legs: 40 and 20 combine to 52, plus 5.2 = 57.2; with the back at 20: 65.8,
    # rated 70 (60 without the factor)
    out.append((V("2022-07-31", [("radiculopathy, left lower extremity (sciatic nerve)", "8520", "leg", "left", [("original", "2023-03-01", "2022-05-01", 40)]),
                                 ("radiculopathy, right lower extremity (sciatic nerve)", "8520", "leg", "right", [("original", "2023-03-01", "2022-05-01", 20)]),
                                 ("lumbosacral strain", "5237", None, None, [("original", "2023-03-01", "2022-02-01", 20)])],
                  [("spouse", "2023-12-20", "2024-01-15")]),
                ["bilateral", "combined-ratings", "dependents"], {"2023-01": (70, 70, 0, 0), "2023-12": (70, 70, 0, 0),
                                                                  "2024-01": (70, 70, 1, 0)}))
    # dependents (3.401(b)): a child born Mar 10 2024 and reported Dec 1 2024 counts from birth, paid from April
    # 2024; a child born Jan 5 2023 but reported Jun 3 2024 (more than a year later) counts from Jun 3, paid from
    # July; a marriage Jun 14 2025 reported Jul 1 counts from Jun 14, paid from July 2025
    out.append((V("2022-01-31", [("posttraumatic stress disorder", "9411", None, None, [("original", "2022-06-01", "2021-10-01", 50)])],
                  [("child", "2024-03-10", "2024-12-01"), ("child", "2023-01-05", "2024-06-03"), ("spouse", "2025-06-14", "2025-07-01")]),
                ["dependents", "payment-start"],
                {"2024-03": (50, 50, 0, 0), "2024-04": (50, 50, 0, 1), "2024-06": (50, 50, 0, 1), "2024-07": (50, 50, 0, 2),
                 "2025-07": (50, 50, 1, 2)}))
    # separation pay of 15,000.00 less 3,300.00 federal tax withheld: 11,700.00 is withheld from compensation
    out.append((V("2023-02-28", [("obstructive sleep apnea", "6847", None, None, [("original", "2023-09-05", "2022-12-01", 50)])],
                  sep_pay=(1500000, 330000)), ["separation-pay"], {"2023-03": (50, 0, 0, 0), "2023-04": (50, 50, 0, 0)}))
    # 50 and 30 combine to 65, rated 70 (5 rounds up)
    out.append((V("2022-11-30", [("posttraumatic stress disorder", "9411", None, None, [("original", "2023-01-20", "2022-08-01", 50)]),
                                 ("migraine headaches", "8100", None, None, [("original", "2023-01-20", "2022-03-01", 30)])]),
                ["combined-ratings", "payment-start"], {"2023-01": (70, 70, 0, 0)}))
    return out


SIDES = ("left", "right")


def filler(n):
    sep = date(2019, 7, 1) + days(rng.randrange(0, 2190))
    if rng.random() < 0.3:
        sep = next_month(sep) - DAY
    if sep > date(2025, 6, 30):
        return None
    within = rng.random() < 0.65
    r0 = sep + days(rng.randrange(20, 340)) if within else year_after(sep) + days(rng.randrange(20, 900))
    if r0 > date(2026, 6, 30):
        return None
    k = rng.choice([1, 2, 2, 3, 3, 4, 5])
    picks, dis = [], []
    used_codes = set()
    for _ in range(k):
        desc, code, limb, ratings = rng.choice(CATALOG)
        side = rng.choice(SIDES) if limb else None
        key = (desc, side)
        if key in used_codes:
            continue
        used_codes.add(key)
        if limb is None and any(p[0] == desc for p in picks):
            continue
        picks.append((desc, code, limb, side, ratings))
    if rng.random() < 0.45:                            # add the paired side of a limb disability
        limbs = [p for p in picks if p[2]]
        if limbs:
            desc, code, limb, side, ratings = rng.choice(limbs)
            other = "left" if side == "right" else "right"
            c = rng.choice([x for x in CATALOG if x[2] == limb])
            if (c[0], other) not in used_codes:
                used_codes.add((c[0], other))
                picks.append((c[0], c[1], c[2], other, c[3]))
    for desc, code, limb, side, ratings in picks:
        rec = r0 if rng.random() < 0.75 else r0 + days(rng.randrange(60, 700))
        if rec > date(2026, 7, 31):
            continue
        if rec <= year_after(sep):
            shown = sep - days(rng.randrange(10, 700))
        else:
            shown = rng.choice([sep - days(rng.randrange(10, 700)), sep + days(rng.randrange(10, 300)),
                                rec + days(rng.randrange(5, 90))])
        g = rng.choice(ratings[:-1] if len(ratings) > 1 else ratings)
        actions = [("original", rec, shown, g)]
        eff_guess = sep + DAY if rec <= year_after(sep) else max(rec, shown)
        higher = [x for x in ratings if x > g]
        cur = max(rec, eff_guess)
        while higher and rng.random() < 0.5:
            ri = cur + days(rng.randrange(120, 700))
            if ri > date(2026, 8, 10):
                break
            si = rng.choice([ri - days(rng.randrange(20, 330)), ri - days(rng.randrange(400, 800)), ri + days(rng.randrange(5, 60))])
            gi = rng.choice(higher)
            actions.append(("increase", ri, si, gi))
            higher = [x for x in ratings if x > gi]
            cur = max(ri, si)
        desc_full = desc.format(side=side) if "{side}" in desc else desc
        dis.append((desc_full[0].upper() + desc_full[1:], code, limb, side, actions))
    if not dis:
        return None
    deps = []
    late_start = rec_first = min(a[1] for x in dis for a in x[4])
    first_eff = sep + DAY if rec_first <= year_after(sep) else None
    if rng.random() < 0.55:
        if first_eff is None and rng.random() < 0.6:     # married before, reported with a late first claim
            deps.append(("spouse", sep - days(rng.randrange(200, 4000)), rec_first))
        else:
            ev = r0 + days(rng.randrange(30, 1000))
            rec = ev + days(rng.choice([rng.randrange(10, 330), rng.randrange(380, 700)]))
            if rec < date(2026, 8, 31):
                deps.append(("spouse", ev, rec))
    for _ in range(rng.choice([0, 0, 1, 1, 2, 3])):
        if first_eff is None and rng.random() < 0.5:
            ev = max(date(2009, 1, 1), sep - days(rng.randrange(100, 3500)))
            deps.append(("child", ev, rec_first))
        else:
            ev = r0 + days(rng.randrange(30, 1100))
            rec = ev + days(rng.choice([rng.randrange(10, 330), rng.randrange(380, 700)]))
            if rec < date(2026, 8, 31):
                deps.append(("child", ev, rec))
    sep_pay = None
    if rng.random() < 0.2:
        g = rng.randrange(400000, 2600000)
        sep_pay = (g, g * 22 // 100)
    vet = V(sep, dis, deps, sep_pay)
    try:
        res = sim(vet)
    except Reject:
        return None
    if not any(v[4] for v in res.values()):
        return None
    return vet, res


def main():
    vets = []
    for vet, tags, expect in planted():
        res = sim(vet)
        for mk, (comb, paid_r, sp, kids) in expect.items():
            m = date(int(mk[:4]), int(mk[5:]), 1)
            got = res[m]
            assert got[:4] == (comb, paid_r, sp, kids), (tags, mk, got)
        vets.append((vet, tags, True))
    rejected = 0
    while len(vets) < len(planted()) + 150:
        x = filler(len(vets))
        if x is None:
            rejected += 1
            continue
        vets.append((x[0], ["filler"], False))
    rng.shuffle(vets)
    vet_out, dis_out, dec_out, dep_out, golden, tags_out, sim_all = [], [], [], [], {}, {}, {}
    n_dis = n_dec = 0
    for i, (vet, tags, planted_) in enumerate(vets, 1):
        vid = f"V{i:04d}"
        vet_out.append({"veteran_id": vid, "last_day_of_active_service": vet["separation"].isoformat(),
                        "separation_pay": None if not vet["sep_pay"] else {
                            "kind": "nondisability separation pay", "gross_cents": vet["sep_pay"][0],
                            "federal_income_tax_withheld_cents": vet["sep_pay"][1]}})
        for k, dsb in vet["disabilities"].items():
            n_dis += 1
            did = f"DX{n_dis:05d}"
            dis_out.append({"disability_id": did, "veteran_id": vid, "description": dsb["desc"][0].upper() + dsb["desc"][1:],
                            "diagnostic_code": dsb["code"]})
            for a in dsb["actions"]:
                n_dec += 1
                dec_out.append({"decision_id": f"RD{n_dec:05d}", "disability_id": did, "claim": a["type"],
                                "claim_received": a["received"].isoformat(),
                                "evidence_first_shows_on": a["shown"].isoformat(), "rating_percent": a["rating"]})
        for dp in vet["dependents"]:
            dep_out.append({"veteran_id": vid, "relationship": dp["rel"], "date_of_marriage_or_birth": dp["event"].isoformat(),
                            "reported_to_va_on": dp["received"].isoformat()})
        res = sim(vet, strict=False)
        m = FIRST
        while m <= LASTM:
            comb, _, _, _, paid = res[m]
            key = f"{vid},{m.year:04d}-{m.month:02d}"
            row = {"combined_rating": str(comb), "payment": f"{paid // 100}.{paid % 100:02d}"}
            sim_all[key] = row
            tags_out[key] = tags
            if planted_:
                golden[key] = row
            m = next_month(m)
    rng.shuffle(dec_out)
    dec_out.sort(key=lambda d: d["claim_received"])
    ENV.mkdir(parents=True, exist_ok=True)
    for old in ENV.iterdir():
        old.unlink()
    dump = lambda name, o: (ENV / name).write_text(json.dumps(o, indent=1) + "\n")  # noqa: E731
    dump("veterans.json", vet_out)
    dump("disabilities.json", dis_out)
    dump("rating_decisions.json", dec_out)
    dump("dependents.json", dep_out)
    dump("compensation_rates.json", [{"effective_date": eff.isoformat(),
                                      "monthly_rates_cents": {str(r): row for r, row in t.items()}} for eff, t in TABLES])
    if TST.exists():
        shutil.rmtree(TST)
    shutil.copytree(ENV, TST)
    (ROOT / "tests" / "case_tags.json").write_text(json.dumps(tags_out, indent=0, sort_keys=True) + "\n")
    (ROOT / "tests" / "golden.json").write_text(json.dumps(golden, indent=0, sort_keys=True) + "\n")
    (Path(__file__).resolve().parent / "sim_answers.json").write_text(json.dumps(sim_all, indent=0) + "\n")
    print(len(vets), "veterans,", len(dis_out), "disabilities,", len(dec_out), "decisions,", len(dep_out), "dependents,",
          len(sim_all), "rows,", len(golden), "planted rows,", rejected, "rejected")


if __name__ == "__main__":
    main()
