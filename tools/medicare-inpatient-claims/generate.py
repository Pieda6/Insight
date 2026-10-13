#!/usr/bin/env python3
"""Generate the medicare-inpatient-claims inputs (dev only, never shipped).

Lakeview Health (fictional hospital and nursing-facility system) bills Medicare Part A. Each beneficiary has a
complete history of inpatient hospital, critical access hospital, psychiatric hospital and skilled nursing
facility stays from the first day of Part A entitlement; stays admitted on or after 2025-01-01 are the claims
queue. Rules: 42 CFR 409.30, 409.60-409.65, 409.80-409.87; amounts from the CMS fact sheets for 2025 and 2026.

Planted beneficiaries carry hand-worked expected answers (tests/golden.json); filler beneficiaries are random
and answered by the verifier's engine only. The generator's own simulator (a third implementation) rejects any
filler history that would need one of the open readings listed in contested(), and re-checks the planted answers.
"""
import json
import random
import shutil
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "tasks" / "medicare-inpatient-claims"
ENV, TST = ROOT / "environment" / "data", ROOT / "tests" / "data"
rng = random.Random(40960)
QUEUE_FROM = date(2025, 1, 1)
LAST_DAY = date(2026, 9, 30)
AMOUNTS = {2025: {"inpatient_hospital_deductible": 167600, "hospital_coinsurance_days_61_90": 41900,
                  "hospital_coinsurance_lifetime_reserve_days": 83800, "snf_coinsurance_days_21_100": 20950},
           2026: {"inpatient_hospital_deductible": 173600, "hospital_coinsurance_days_61_90": 43400,
                  "hospital_coinsurance_lifetime_reserve_days": 86800, "snf_coinsurance_days_21_100": 21700}}
ZERO = dict.fromkeys(AMOUNTS[2025], 0)
FACILITIES = {
    "LVH-MAIN": ("Lakeview Hospital, Main Campus", "general_hospital"),
    "LVH-EAST": ("Lakeview Hospital, East", "general_hospital"),
    "LVH-WEST": ("Lakeview Hospital, Westfield", "general_hospital"),
    "LVH-CAH1": ("Pine Ridge Critical Access Hospital", "critical_access_hospital"),
    "LVH-CAH2": ("Clearwater Critical Access Hospital", "critical_access_hospital"),
    "LVH-PSY1": ("Lakeview Behavioral Hospital", "psychiatric_hospital"),
    "LVH-PSY2": ("Harbor Psychiatric Hospital", "psychiatric_hospital"),
    "LVS-OAKS": ("Lakeview Oaks Skilled Nursing", "skilled_nursing_facility"),
    "LVS-MAPL": ("Maple Court Skilled Nursing", "skilled_nursing_facility"),
    "LVS-BIRC": ("Birch Hill Nursing and Rehabilitation", "skilled_nursing_facility"),
    "LVS-CEDR": ("Cedar Lane Care Center", "skilled_nursing_facility"),
}
# a skilled nursing facility's charge for a day of care, by calendar year (409.85(c) compares it with the
# coinsurance): Birch Hill is above the 2025 amount (209.50) but below the 2026 amount (217.00)
SNF_RATE = {"LVS-OAKS": {2025: 26000, 2026: 27500}, "LVS-MAPL": {2025: 24500, 2026: 25500},
            "LVS-BIRC": {2025: 21200, 2026: 21600}, "LVS-CEDR": {2025: 19800, 2026: 20500}}
GENERAL = ["LVH-MAIN", "LVH-EAST", "LVH-WEST"]
CAH = ["LVH-CAH1", "LVH-CAH2"]
PSY = ["LVH-PSY1", "LVH-PSY2"]
SNF = ["LVS-OAKS", "LVS-MAPL", "LVS-BIRC", "LVS-CEDR"]
NAMES = ["A. Okafor", "B. Lindqvist", "C. Ramirez", "D. Chen", "E. Novak", "F. Haddad", "G. Moreau", "H. Tanaka",
         "I. Kowalski", "J. Mensah", "K. Patel", "L. Rossi", "M. Byrne", "N. Silva", "O. Ahmed", "P. Schultz",
         "Q. Nguyen", "R. Dubois", "S. Kim", "T. Oyelaran", "U. Brennan", "V. Ivanova", "W. Garcia", "X. Lopez"]


def D(s):
    return date.fromisoformat(s)


def kind(fid):
    return FACILITIES[fid][1]


class Reject(Exception):
    pass


# ------------------------------------------------------------------ generator-side simulator -----------------
def sim(b, strict=True):
    """Third implementation of the rules, used to reject contested filler and to re-check planted answers.
    Returns {stay index: (bp_start, covered, reserve, deductible, coinsurance, blood)}."""
    E, stays = b["ent"], b["stays"]
    hosp, snf, skilled = {}, {}, set()
    for i, s in enumerate(stays):
        if s["dis"] <= s["adm"]:
            raise Reject("empty stay")
        d = s["adm"]
        while d < s["dis"]:
            if d in hosp or d in snf:
                raise Reject("overlap")
            if kind(s["fac"]) == "skilled_nursing_facility":
                snf[d] = i
                if d <= s["st"]:
                    skilled.add(d)
            else:
                hosp[d] = i
            d += timedelta(days=1)
    reduction = None
    if E in hosp and kind(stays[hosp[E]]["fac"]) == "psychiatric_hospital":
        reduction = sum(1 for k in range(1, 151) if E - timedelta(days=k) in hosp
                        and kind(stays[hosp[E - timedelta(days=k)]]["fac"]) == "psychiatric_hospital")
    blood = {}
    for i, s in enumerate(stays):
        for u in s.get("blood", ()):
            blood.setdefault(u["date"], []).append(("A", i, u))
    for u in b.get("partb", ()):
        blood.setdefault(u["date"], []).append(("B", None, u))
    res = {i: [None, 0, 0, 0, 0, 0] for i in range(len(stays))}
    bp, gap, n_bp, hosp_n, snf_n, ded_done = None, 0, 0, 0, 0, False
    lrd, psy, init_psy = 0, 0, 0
    year_units = {}
    covered_day = set()
    d = min([E] + [s["adm"] for s in stays])
    end = max(s["dis"] for s in stays) + timedelta(days=1)
    while d <= end:
        if d >= E:
            inp = d in hosp or d in skilled
            started = False
            if inp:
                if bp is None:
                    bp, n_bp, hosp_n, snf_n, ded_done, started = d, n_bp + 1, 0, 0, False, True
                gap = 0
            elif bp is not None:
                gap += 1
                if gap >= 60:
                    bp = None
            for table in (hosp, snf):
                if d in table and res[table[d]][0] is None:
                    if bp is None:
                        raise Reject("stay day outside any benefit period")
                    res[table[d]][0] = bp
            if d in hosp:
                i = hosp[d]
                s = stays[i]
                k = kind(s["fac"])
                psych_day = k == "psychiatric_hospital" or s.get("psych", False)
                ok = not (k == "psychiatric_hospital" and psy >= 190)
                if reduction is not None and n_bp == 1 and psych_day and init_psy >= 150 - reduction:
                    ok = False
                if ok:
                    y = AMOUNTS.get(d.year, ZERO)            # history before 2025 is never billed here
                    if hosp_n < 90:
                        hosp_n += 1
                        if hosp_n > 60:
                            res[i][4] += y["hospital_coinsurance_days_61_90"]
                    elif lrd < 60:
                        lrd += 1
                        res[i][2] += 1
                        res[i][4] += y["hospital_coinsurance_lifetime_reserve_days"]
                    else:
                        ok = False
                if ok:
                    res[i][1] += 1
                    covered_day.add(d)
                    if k == "psychiatric_hospital":
                        psy += 1
                    if reduction is not None and n_bp == 1 and psych_day:
                        init_psy += 1
                    if not ded_done:
                        ded_done = True
                        res[i][3] = AMOUNTS.get(d.year, ZERO)["inpatient_hospital_deductible"]
                        if strict and s["adm"] >= QUEUE_FROM and s["adm"].year != (s["dis"] - timedelta(days=1)).year:
                            raise Reject("deductible stay crosses a year boundary")
                elif started and strict:
                    raise Reject("benefit period opened by a day Medicare does not pay for")
            if d in snf:
                i = snf[d]
                s = stays[i]
                if d in skilled and qualifies(b, i, strict):
                    if snf_n < 100:
                        snf_n += 1
                        res[i][1] += 1
                        covered_day.add(d)
                        if snf_n > 20 and d.year in AMOUNTS:
                            res[i][4] += min(AMOUNTS[d.year]["snf_coinsurance_days_21_100"], SNF_RATE[s["fac"]][d.year])
                elif started and strict:
                    raise Reject("benefit period opened by an uncovered nursing-facility day")
        for src, i, u in sorted(blood.get(d, ()), key=lambda x: x[0]):
            if strict and len({x[0] for x in blood[d]}) > 1:
                raise Reject("Part A and Part B blood on the same day")
            if u["product"] not in ("whole_blood", "packed_red_cells"):
                continue
            used = year_units.get(d.year, 0)
            if src == "A":
                if strict and d not in covered_day:
                    raise Reject("blood on a day Medicare does not pay for")
                if not u["replaced_or_obtained_free"]:
                    res[i][5] += min(u["units"], max(0, 3 - used)) * u["charge_per_unit_cents"]
            year_units[d.year] = used + u["units"]
        d += timedelta(days=1)
    return {i: tuple(v) for i, v in res.items()}


def qualifies(b, i, strict):
    """409.30: 3 inpatient days in a hospital or CAH (discharge day not counted), SNF within 30 days."""
    E, stays = b["ent"], b["stays"]
    s = stays[i]
    prior = [p for p in stays if kind(p["fac"]) != "skilled_nursing_facility" and p["dis"] <= s["adm"]]
    if strict:
        if not prior:
            raise Reject("SNF stay with no prior hospital stay")
        last = max(prior, key=lambda p: p["dis"])
        if kind(last["fac"]) == "psychiatric_hospital":
            raise Reject("SNF stay after a psychiatric hospital stay")
        if last["dis"] < E:
            raise Reject("qualifying stay discharged before the month of entitlement")
        if sum(1 for p in prior if (s["adm"] - p["dis"]).days <= 30) > 1:
            raise Reject("two hospital stays in the 30 days before SNF admission")
        if (s["adm"] - last["dis"]).days > 58:
            raise Reject("SNF stay far from any hospital stay")
    last = max(prior, key=lambda p: p["dis"])
    return (last["dis"] - last["adm"]).days >= 3 and (s["adm"] - last["dis"]).days <= 30


def contested(b):
    try:
        sim(b, strict=True)
    except Reject:
        return True
    E = b["ent"]
    for s in b["stays"]:
        if kind(s["fac"]) == "skilled_nursing_facility":
            if s["adm"] < E:
                return True
            if s["dis"] > s["st"] + timedelta(days=61):          # custodial days after a period could end
                return True
        if s.get("obs") and s["obs"] < E:
            return True
    return False


# ------------------------------------------------------------------ world ----------------------------------------
class World:
    def __init__(self):
        self.bens, self.golden, self.tags = [], {}, {}

    def add(self, ent, stays, tags, expected=None, partb=()):
        """stays: dicts fac, adm, dis[, obs, psych, st, blood]; expected: {stay index: (bp, cov, res, ded,
        coins, blood)} for the stays in the queue (hand-worked)."""
        b = {"id": f"B{len(self.bens) + 1:04d}", "ent": ent, "stays": stays, "partb": list(partb),
             "tags": tags, "expected": expected}
        for s in stays:
            if kind(s["fac"]) == "skilled_nursing_facility" and "st" not in s:
                s["st"] = s["dis"] - timedelta(days=1)
        self.bens.append(b)
        return b


def H(fac, adm, dis, **kw):
    return dict(fac=fac, adm=D(adm), dis=D(dis), **kw)


def U(d, product, units, charge, replaced=False):
    return {"date": D(d), "product": product, "units": units, "charge_per_unit_cents": charge,
            "replaced_or_obtained_free": replaced}


def E(bp, cov, res=0, ded=0, coins=0, blood=0):
    return (D(bp), cov, res, ded, coins, blood)


def planted(w):
    G, G2, P1, S1, S2 = "LVH-MAIN", "LVH-EAST", "LVH-PSY1", "LVS-OAKS", "LVS-MAPL"
    d25, d26 = 167600, 173600
    # ---- benefit periods: 60 consecutive days not an inpatient (the discharge day is not an inpatient day)
    # Mar 2-7 is 5 days; non-inpatient Mar 7 to May 4 is 59 days, so a May 5 admission is the same period.
    w.add(D("2020-01-01"), [H(G, "2025-03-02", "2025-03-07"), H(G2, "2025-05-05", "2025-05-09")],
          ["benefit-period", "boundary"], {0: E("2025-03-02", 5, ded=d25), 1: E("2025-03-02", 4)})
    # ... non-inpatient Mar 7 to May 5 is 60 days: May 6 starts a new period and a new deductible
    w.add(D("2020-01-01"), [H(G, "2025-03-02", "2025-03-07"), H(G2, "2025-05-06", "2025-05-09")],
          ["benefit-period", "boundary"], {0: E("2025-03-02", 5, ded=d25), 1: E("2025-05-06", 3, ded=d25)})
    # ---- hospital days: 60 full, then coinsurance. Jan 10 - Mar 14 = 63 days: 3 x 419.00
    w.add(D("2020-01-01"), [H(G, "2025-01-10", "2025-03-14")], ["hospital-days", "boundary"],
          {0: E("2025-01-10", 63, ded=d25, coins=3 * 41900)})
    # Jan 10 - Mar 11 = 60 days exactly: no coinsurance
    w.add(D("2020-01-01"), [H(G, "2025-01-10", "2025-03-11")], ["hospital-days", "boundary"],
          {0: E("2025-01-10", 60, ded=d25)})
    # coinsurance at the rate of the year of each day. Oct 1-6 (5 days); Nov 1 - Jan 10 is 70 days, days 6-75 of
    # the period; day 61 is Dec 26: Dec 26-31 at 419.00 (6) and Jan 1-9 at 434.00 (9) = 6420.00
    w.add(D("2020-01-01"), [H(G, "2025-10-01", "2025-10-06"), H(G, "2025-11-01", "2026-01-10")],
          ["hospital-days", "year-rates"], {0: E("2025-10-01", 5, ded=d25),
                                            1: E("2025-10-01", 70, coins=6 * 41900 + 9 * 43400)})
    # lifetime reserve days. Feb 1 - May 8 = 96 days: 30 x 419.00 + 6 x 838.00
    w.add(D("2020-01-01"), [H(G, "2025-02-01", "2025-05-08")], ["reserve-days"],
          {0: E("2025-02-01", 96, 6, d25, 30 * 41900 + 6 * 83800)})
    # 59 reserve days used in 2019 (149-day stay); a 95-day stay in 2025 has 90 regular + 1 reserve day left
    w.add(D("2018-01-01"), [H(G, "2019-03-01", "2019-07-28"), H(G, "2025-04-01", "2025-07-05")],
          ["reserve-days", "history"], {1: E("2025-04-01", 91, 1, d25, 30 * 41900 + 83800)})
    # a period that began in 2024 (deductible already charged then): Nov 20 - Jan 5 is 46 days; the Feb 1-25
    # stay is days 47-70 of that period: days 61-70 (Feb 15-24) at 419.00, no deductible
    w.add(D("2020-01-01"), [H(G, "2024-11-20", "2025-01-05"), H(G2, "2025-02-01", "2025-02-25")],
          ["hospital-days", "history", "deductible"], {1: E("2024-11-20", 24, coins=10 * 41900)})
    # 2026 amounts: Feb 1 - Apr 10 = 68 days: 8 x 434.00, deductible 1736.00
    w.add(D("2020-01-01"), [H(G, "2026-02-01", "2026-04-10")], ["hospital-days", "year-rates"],
          {0: E("2026-02-01", 68, ded=d26, coins=8 * 43400)})
    # same-day transfer to another hospital continues the period: Jun 1-10 (9) then Jun 10-15 (5)
    w.add(D("2020-01-01"), [H(G, "2025-06-01", "2025-06-10"), H(G2, "2025-06-10", "2025-06-15")],
          ["benefit-period"], {0: E("2025-06-01", 9, ded=d25), 1: E("2025-06-01", 5)})
    # entitlement during a general hospital stay: days from Jul 1 (the first day of entitlement) are covered
    w.add(D("2025-07-01"), [H(G, "2025-06-28", "2025-07-05")], ["entitlement"], {0: E("2025-07-01", 4, ded=d25)})

    # ---- skilled nursing facility (409.30, 409.61(b), 409.85)
    # 3-day stay, SNF the same day, 30 days: days 21-30 at 209.50
    w.add(D("2020-01-01"), [H(G, "2025-03-02", "2025-03-05"), H(S1, "2025-03-05", "2025-04-04")],
          ["snf", "three-day"], {0: E("2025-03-02", 3, ded=d25), 1: E("2025-03-02", 30, coins=10 * 20950)})
    # 2-day stay: the nursing-facility stay is not covered
    w.add(D("2020-01-01"), [H(G, "2025-03-02", "2025-03-04"), H(S1, "2025-03-04", "2025-03-24")],
          ["snf", "three-day"], {0: E("2025-03-02", 2, ded=d25), 1: E("2025-03-02", 0)})
    # observation Mar 1-2 is outpatient: inpatient Mar 3-5 is 2 days, not 4
    w.add(D("2020-01-01"), [H(G, "2025-03-03", "2025-03-05", obs=D("2025-03-01")), H(S1, "2025-03-05", "2025-03-20")],
          ["snf", "three-day", "observation"], {0: E("2025-03-03", 2, ded=d25), 1: E("2025-03-03", 0)})
    # SNF admission 30 days after discharge (Mar 6 -> Apr 5) is in time; 31 days (Apr 6) is not
    w.add(D("2020-01-01"), [H(G, "2025-03-02", "2025-03-06"), H(S2, "2025-04-05", "2025-04-15")],
          ["snf", "thirty-day"], {0: E("2025-03-02", 4, ded=d25), 1: E("2025-03-02", 10)})
    w.add(D("2020-01-01"), [H(G, "2025-03-02", "2025-03-06"), H(S2, "2025-04-06", "2025-04-16")],
          ["snf", "thirty-day"], {0: E("2025-03-02", 4, ded=d25), 1: E("2025-03-02", 0)})
    # 100 SNF days per period across two stays: 70 days (21-70 coinsured), then 40 days of which 30 covered
    w.add(D("2020-01-01"), [H(G, "2025-01-05", "2025-01-10"), H(S1, "2025-01-10", "2025-03-21"),
                            H(G, "2025-04-01", "2025-04-06"), H(S1, "2025-04-06", "2025-05-16")],
          ["snf", "snf-100"], {0: E("2025-01-05", 5, ded=d25), 1: E("2025-01-05", 70, coins=50 * 20950),
                               2: E("2025-01-05", 5), 3: E("2025-01-05", 30, coins=30 * 20950)})
    # custodial care does not keep a period open: skilled care to Feb 20, non-inpatient Feb 21 - Apr 21 = 60
    # days, so the Apr 22 hospital admission starts a new period (SNF covered Jan 10 - Feb 20 = 42 days)
    w.add(D("2020-01-01"), [H(G, "2025-01-05", "2025-01-10"), H(S1, "2025-01-10", "2025-04-22", st=D("2025-02-20")),
                            H(G, "2025-04-22", "2025-04-27")],
          ["snf", "custodial", "benefit-period"], {0: E("2025-01-05", 5, ded=d25),
                                                   1: E("2025-01-05", 42, coins=22 * 20950),
                                                   2: E("2025-04-22", 5, ded=d25)})
    # one more skilled day (Feb 21): only 59 non-inpatient days, same period, no new deductible
    w.add(D("2020-01-01"), [H(G, "2025-01-05", "2025-01-10"), H(S1, "2025-01-10", "2025-04-22", st=D("2025-02-21")),
                            H(G, "2025-04-22", "2025-04-27")],
          ["snf", "custodial", "benefit-period"], {0: E("2025-01-05", 5, ded=d25),
                                                   1: E("2025-01-05", 43, coins=23 * 20950),
                                                   2: E("2025-01-05", 5)})
    # SNF days 21+ across the new year: Nov 25 - Jan 10 is 46 days; day 21 is Dec 15: 17 days at 209.50,
    # 9 days at 217.00
    w.add(D("2020-01-01"), [H(G, "2025-11-20", "2025-11-25"), H(S2, "2025-11-25", "2026-01-10")],
          ["snf", "year-rates"], {0: E("2025-11-20", 5, ded=d25), 1: E("2025-11-20", 46, coins=17 * 20950 + 9 * 21700)})
    # a critical access hospital stay qualifies
    w.add(D("2020-01-01"), [H("LVH-CAH1", "2025-08-01", "2025-08-04"), H(S2, "2025-08-04", "2025-08-14")],
          ["snf", "cah"], {0: E("2025-08-01", 3, ded=d25), 1: E("2025-08-01", 10)})
    # SNF to Feb 9 (skilled throughout); non-inpatient Feb 9 - Apr 9 = 60 days; Apr 10 is a new period
    w.add(D("2020-01-01"), [H(G, "2025-01-05", "2025-01-10"), H(S2, "2025-01-10", "2025-02-09"),
                            H(G, "2025-04-10", "2025-04-12")],
          ["snf", "benefit-period", "boundary"], {0: E("2025-01-05", 5, ded=d25),
                                                  1: E("2025-01-05", 30, coins=10 * 20950),
                                                  2: E("2025-04-10", 2, ded=d25)})

    # 409.85(c): coinsurance is the facility's daily charge when that is lower. Birch Hill charges 212.00 a day
    # in 2025 (above 209.50) and 216.00 in 2026 (below 217.00): days 21-46 are Dec 15-31 (17 x 209.50) and
    # Jan 1-9 (9 x 216.00)
    w.add(D("2020-01-01"), [H(G, "2025-11-20", "2025-11-25"), H("LVS-BIRC", "2025-11-25", "2026-01-10")],
          ["snf", "year-rates", "snf-charge"], {0: E("2025-11-20", 5, ded=d25),
                                                1: E("2025-11-20", 46, coins=17 * 20950 + 9 * 21600)})
    # Cedar Lane charges 198.00 in 2025: days 21-30 at 198.00
    w.add(D("2020-01-01"), [H(G, "2025-04-01", "2025-04-05"), H("LVS-CEDR", "2025-04-05", "2025-05-05")],
          ["snf", "snf-charge"], {0: E("2025-04-01", 4, ded=d25), 1: E("2025-04-01", 30, coins=10 * 19800)})
    # 409.30(a): the 3 days need not fall after entitlement. Admitted Jun 29, entitled Jul 1, discharged Jul 2:
    # 3 inpatient days (1 paid), discharged in the month of entitlement, so the SNF stay is covered
    w.add(D("2025-07-01"), [H(G, "2025-06-29", "2025-07-02"), H(S1, "2025-07-02", "2025-07-12")],
          ["snf", "three-day", "entitlement"], {0: E("2025-07-01", 1, ded=d25), 1: E("2025-07-01", 10)})
    # admitted Jun 30: only 2 inpatient days, no SNF coverage
    w.add(D("2025-07-01"), [H(G, "2025-06-30", "2025-07-02"), H(S1, "2025-07-02", "2025-07-12")],
          ["snf", "three-day", "entitlement"], {0: E("2025-07-01", 1, ded=d25), 1: E("2025-07-01", 0)})

    # ---- psychiatric hospital: 190-day lifetime limit (409.62)
    # 2018: 120 days (90 regular + 30 reserve); 2021: 65 days; 185 used. 2025: only 5 of 20 days are paid.
    w.add(D("2018-01-01"), [H(P1, "2018-03-01", "2018-06-29"), H(P1, "2021-01-10", "2021-03-16"),
                            H(P1, "2025-06-01", "2025-06-21")],
          ["psych-190", "history"], {2: E("2025-06-01", 5, ded=d25)})
    # 190 used by 2021 (120 + 70 of an 81-day stay); psychiatric care in a general hospital is not limited
    # by it (20 days paid); a psychiatric hospital stay in the same period gets nothing
    w.add(D("2018-01-01"), [H(P1, "2018-03-01", "2018-06-29"), H(P1, "2021-01-10", "2021-04-01"),
                            H(G, "2025-06-01", "2025-06-21", psych=True), H(P1, "2025-07-01", "2025-07-11")],
          ["psych-190", "history"], {2: E("2025-06-01", 20, ded=d25), 3: E("2025-06-01", 0)})
    # ---- initial benefit period after entitlement in a psychiatric hospital (409.63)
    # in the hospital from Mar 2; entitled Apr 1: 30 days before entitlement leave 120 psychiatric days:
    # 60 full + 30 coinsured + 30 reserve; a later general-hospital psychiatric stay in the same period gets
    # nothing; a medical stay uses 5 more reserve days
    w.add(D("2025-04-01"), [H("LVH-PSY2", "2025-03-02", "2025-09-30"), H(G, "2025-10-20", "2025-10-30", psych=True),
                            H(G2, "2025-11-15", "2025-11-20")],
          ["initial-period", "psych-190", "reserve-days"],
          {0: E("2025-04-01", 120, 30, d25, 30 * 41900 + 30 * 83800), 1: E("2025-04-01", 0),
           2: E("2025-04-01", 5, 5, 0, 5 * 83800)})

    # in a psychiatric hospital for 100 days before entitlement on Mar 1: only 50 psychiatric days in the initial
    # period (Mar 1 - Apr 19 paid). After a 83-day gap a new period begins and the reduction no longer applies:
    # the 30-day psychiatric stay in August is fully paid, with a new deductible
    w.add(D("2025-03-01"), [H(P1, "2024-11-21", "2025-05-10"), H("LVH-PSY2", "2025-08-01", "2025-08-31")],
          ["initial-period", "psych-190"], {1: E("2025-08-01", 30, ded=d25)})

    # ---- blood deductible (409.87): first 3 units of whole blood or packed red cells in a calendar year
    w.add(D("2020-01-01"), [H(G, "2025-05-01", "2025-05-06", blood=[U("2025-05-02", "packed_red_cells", 4, 42000)])],
          ["blood"], {0: E("2025-05-01", 5, ded=d25, blood=3 * 42000)})
    # one Part B unit in February: 2 deductible units left; platelets never count
    w.add(D("2020-01-01"), [H(G, "2025-05-01", "2025-05-06", blood=[U("2025-05-02", "packed_red_cells", 2, 42000),
                                                                    U("2025-05-03", "platelets", 3, 61000)])],
          ["blood"], {0: E("2025-05-01", 5, ded=d25, blood=2 * 42000)},
          partb=[{"date": D("2025-02-10"), "product": "whole_blood", "units": 1}])
    # 3 replaced units still use up the deductible; the next stay's 2 units in the same year cost nothing
    w.add(D("2020-01-01"), [H(G, "2025-05-01", "2025-05-06", blood=[U("2025-05-02", "packed_red_cells", 3, 42000, True)]),
                            H(G2, "2025-08-01", "2025-08-05", blood=[U("2025-08-02", "whole_blood", 2, 39000)])],
          ["blood"], {0: E("2025-05-01", 5, ded=d25), 1: E("2025-08-01", 4, ded=d25)})
    # a new calendar year starts a new blood deductible
    w.add(D("2020-01-01"), [H(G, "2025-06-01", "2025-06-05", blood=[U("2025-06-02", "whole_blood", 3, 39000)]),
                            H(G2, "2026-03-01", "2026-03-05", blood=[U("2026-03-02", "packed_red_cells", 2, 44000)])],
          ["blood", "year-rates"], {0: E("2025-06-01", 4, ded=d25, blood=3 * 39000),
                                    1: E("2026-03-01", 4, ded=d26, blood=2 * 44000)})
    # Part B units count in date order: 2 in March (Part A, charged), 2 in June (Part B), 2 in August: none left
    w.add(D("2020-01-01"), [H(G, "2025-03-01", "2025-03-05", blood=[U("2025-03-02", "packed_red_cells", 2, 42000)]),
                            H(G2, "2025-08-01", "2025-08-05", blood=[U("2025-08-02", "packed_red_cells", 2, 42000)])],
          ["blood"], {0: E("2025-03-01", 4, ded=d25, blood=2 * 42000), 1: E("2025-08-01", 4, ded=d25)},
          partb=[{"date": D("2025-06-15"), "product": "packed_red_cells", "units": 2}])


# ------------------------------------------------------------------ filler --------------------------------------
def rdate(a, b):
    return a + timedelta(days=rng.randrange((b - a).days + 1))


def filler(w):
    profile = rng.choice(["typical"] * 3 + ["frail"] * 3 + ["snf"] * 3 + ["psych"] * 2 + ["custodial"] * 2 + ["new"])
    if profile == "new":
        ent = rdate(D("2025-01-15"), D("2026-03-01")).replace(day=1)
    else:
        ent = rdate(D("2016-01-01"), D("2024-09-01")).replace(day=1)
    stays, partb = [], []
    t = ent + timedelta(days=rng.randrange(0, 500))
    if profile == "new" and rng.random() < 0.5:                 # in a psychiatric hospital on entitlement day
        adm = ent - timedelta(days=rng.choice([3, 10, 20, 45, 90, 130]))
        dis = ent + timedelta(days=rng.choice([20, 60, 95, 130, 160]))
        stays.append(dict(fac=rng.choice(PSY), adm=adm, dis=dis))
        t = dis + timedelta(days=rng.choice([10, 30, 58, 59, 60, 61, 120]))
    elif profile == "new" and rng.random() < 0.4:               # in a general hospital on entitlement day
        adm = ent - timedelta(days=rng.choice([1, 2, 4]))
        dis = ent + timedelta(days=rng.choice([1, 2, 3, 6, 12]))
        stays.append(dict(fac=rng.choice(GENERAL), adm=adm, dis=dis))
        t = dis + timedelta(days=rng.choice([0, 0, 15, 59, 60]))
        if t == dis:
            st_len = rng.choice([10, 20, 21, 25, 40])
            stays.append(dict(fac=rng.choice(SNF), adm=t, dis=t + timedelta(days=st_len)))
            if rng.random() < 0.5:                                  # qualifying stay begun before entitlement
                stays[-2]["adm"] = ent - timedelta(days=rng.choice([1, 2, 3]))
            t = stays[-1]["dis"] + timedelta(days=rng.choice([30, 59, 60, 61, 90]))
    while t < LAST_DAY - timedelta(days=5):
        if profile == "psych" and rng.random() < 0.6:
            fac = rng.choice(PSY)
            los = rng.choice([12, 20, 30, 45, 60, 75, 90, 110])
            stays.append(dict(fac=fac, adm=t, dis=t + timedelta(days=los)))
            t = stays[-1]["dis"] + timedelta(days=rng.choice([20, 45, 58, 59, 60, 61, 62, 150, 300]))
            continue
        fac = rng.choice(GENERAL * 4 + CAH)
        los = rng.choice({"typical": [1, 2, 3, 4, 5, 7], "frail": [3, 5, 8, 14, 25, 40, 61, 75, 95],
                          "snf": [2, 3, 3, 4, 6, 9], "custodial": [3, 4, 6, 10],
                          "psych": [3, 5, 10], "new": [2, 3, 5, 8, 20]}[profile])
        s = dict(fac=fac, adm=t, dis=t + timedelta(days=los))
        if rng.random() < 0.2:
            s["obs"] = t - timedelta(days=rng.choice([1, 1, 2]))
            if stays and s["obs"] < stays[-1]["dis"]:
                del s["obs"]
        if profile in ("psych",) and rng.random() < 0.3:
            s["psych"] = True
        if rng.random() < 0.18:
            n = rng.choice([1, 2, 2, 3, 4])
            s["blood"] = [U(str(t + timedelta(days=rng.randrange(los))), rng.choice(
                ["packed_red_cells", "packed_red_cells", "whole_blood", "platelets", "plasma"]), n,
                rng.choice([36000, 39000, 42000, 44000, 47500]), rng.random() < 0.25)]
        stays.append(s)
        t = s["dis"]
        p_snf = {"typical": 0.1, "frail": 0.35, "snf": 0.8, "custodial": 0.9, "psych": 0.05, "new": 0.3}[profile]
        if fac not in PSY and rng.random() < p_snf:
            wait = rng.choice([0, 0, 0, 0, 1, 5, 29, 30, 31, 40])
            sl = rng.choice([8, 15, 20, 21, 30, 45, 60, 79, 80, 99, 100, 101])
            adm = t + timedelta(days=wait)
            sn = dict(fac=rng.choice(SNF), adm=adm, dis=adm + timedelta(days=sl))
            if profile == "custodial" and rng.random() < 0.7:
                skilled_days = rng.choice([10, 20, 21, 35, 60])
                sn["st"] = adm + timedelta(days=skilled_days - 1)
                tail = rng.choice([30, 58, 59, 60, 61])
                sn["dis"] = sn["st"] + timedelta(days=tail)
            if rng.random() < 0.08:
                sn["blood"] = [U(str(adm + timedelta(days=1)), "packed_red_cells", rng.choice([1, 2]), 42000)]
            stays.append(sn)
            t = sn["dis"]
            gap = rng.choice([0, 3, 10, 25, 58, 59, 60, 61, 62, 100, 200])
            if "st" in sn and gap == 0:
                gap = 1
        else:
            gap = rng.choice([4, 10, 20, 30, 45, 57, 58, 59, 60, 61, 62, 90, 180, 365])
        t += timedelta(days=gap)
    stays = [s for s in stays if s["dis"] <= LAST_DAY + timedelta(days=5)]
    for s in stays:
        if kind(s["fac"]) == "skilled_nursing_facility" and "st" not in s:
            s["st"] = s["dis"] - timedelta(days=1)
    if rng.random() < 0.3:
        for _ in range(rng.choice([1, 2])):
            partb.append({"date": rdate(D("2025-01-01"), D("2026-09-30")),
                          "product": rng.choice(["whole_blood", "packed_red_cells"]), "units": rng.choice([1, 2])})
    if not any(s["adm"] >= QUEUE_FROM for s in stays):
        return False
    b = {"ent": ent, "stays": stays, "partb": partb}
    if contested(b):
        return False
    w.add(ent, stays, ["filler"], None, partb)
    return True


# ------------------------------------------------------------------ output --------------------------------------
def main():
    w = World()
    planted(w)
    n_planted = len(w.bens)
    for b in w.bens:                                   # hand-worked answers re-checked by the third implementation
        got = sim(b, strict=False)
        assert not contested(b), (b["id"], b["tags"])
        for i, want in b["expected"].items():
            assert got[i] == want, (b["id"], i, got[i], want)
        assert set(b["expected"]) == {i for i, s in enumerate(b["stays"]) if s["adm"] >= QUEUE_FROM}, b["id"]
    rejected = 0
    while len(w.bens) < n_planted + 120:
        if not filler(w):
            rejected += 1
    order = list(range(len(w.bens)))
    rng.shuffle(order)
    bens, stays_out, claims, partb, n_stay = [], [], [], [], 0
    for new_i, j in enumerate(order, 1):
        b = w.bens[j]
        b["id"] = f"B{new_i:04d}"
        assert b["ent"].day == 1, b["id"]
        born = date(b["ent"].year - 65, b["ent"].month, rng.randint(2, 28))
        bens.append({"beneficiary_id": b["id"], "name": rng.choice(NAMES), "date_of_birth": born.isoformat(),
                     "part_a_entitlement_date": b["ent"].isoformat(), "entitlement_basis": "age",
                     "medicare_advantage_enrollment": None})
        for u in b["partb"]:
            partb.append({"beneficiary_id": b["id"], "date": u["date"].isoformat(), "product": u["product"],
                          "units": u["units"]})
        for i, s in enumerate(sorted(range(len(b["stays"])), key=lambda k: b["stays"][k]["adm"])):
            st = b["stays"][s]
            n_stay += 1
            sid = f"S{n_stay:05d}"
            fk = kind(st["fac"])
            rec = {"stay_id": sid, "beneficiary_id": b["id"], "facility_id": st["fac"],
                   "outpatient_observation_start_date": st["obs"].isoformat() if st.get("obs") else None,
                   "inpatient_admission_date": st["adm"].isoformat(), "discharge_date": st["dis"].isoformat()}
            if fk in ("general_hospital", "critical_access_hospital"):
                rec["treated_for_mental_illness"] = bool(st.get("psych"))
            if fk == "skilled_nursing_facility":
                rec["skilled_level_of_care_through"] = st["st"].isoformat()
            rec["blood_furnished"] = [{"date": u["date"].isoformat(), "product": u["product"], "units": u["units"],
                                       "charge_per_unit_cents": u["charge_per_unit_cents"],
                                       "replaced_or_obtained_free": u["replaced_or_obtained_free"]}
                                      for u in st.get("blood", ())]
            stays_out.append(rec)
            if st["adm"] >= QUEUE_FROM:
                claims.append((sid, b, s))
    rng.shuffle(claims)
    claim_rows, golden, tags = [], {}, {}
    for n, (sid, b, s) in enumerate(claims, 1):
        cid = f"C{n:04d}"
        claim_rows.append({"claim_id": cid, "stay_id": sid, "type_of_bill": "inpatient"
                           if kind(b["stays"][s]["fac"]) != "skilled_nursing_facility" else "skilled_nursing"})
        tags[cid] = b["tags"]
        if b["expected"] is not None:
            bp, cov, res, ded, coins, blood = b["expected"][s]
            golden[cid] = {"benefit_period_start": bp.isoformat(), "covered_days": str(cov), "reserve_days": str(res),
                           "deductible": f"{ded / 100:.2f}", "coinsurance": f"{coins / 100:.2f}",
                           "blood": f"{blood / 100:.2f}"}
    ENV.mkdir(parents=True, exist_ok=True)
    for old in ENV.iterdir():
        old.unlink()
    dump = lambda name, obj: (ENV / name).write_text(json.dumps(obj, indent=1) + "\n")  # noqa: E731
    dump("beneficiaries.json", bens)
    dump("facilities.json", [{"facility_id": k, "name": v[0], "type": v[1], "medicare_participating_since": "2001-07-01",
                              "daily_charge_cents_by_year": {str(y): c for y, c in SNF_RATE[k].items()}
                              if k in SNF_RATE else None}
                             for k, v in FACILITIES.items()])
    dump("stays.json", stays_out)
    dump("claims.json", claim_rows)
    dump("part_b_blood.json", partb)
    dump("part_a_amounts.json", {
        "source": "CMS fact sheets, 2025 Medicare Parts A & B Premiums and Deductibles (Nov 8, 2024) and 2026 "
                  "Medicare Parts A & B Premiums and Deductibles (Nov 14, 2025)",
        "unit": "cents (USD)",
        "by_calendar_year": {str(y): v for y, v in AMOUNTS.items()}})
    if TST.exists():
        shutil.rmtree(TST)
    shutil.copytree(ENV, TST)
    (ROOT / "tests" / "case_tags.json").write_text(json.dumps(tags, indent=1, sort_keys=True) + "\n")
    (ROOT / "tests" / "golden.json").write_text(json.dumps(golden, indent=1, sort_keys=True) + "\n")
    print(len(bens), "beneficiaries,", len(stays_out), "stays,", len(claim_rows), "claims,", len(golden),
          "hand-worked claims,", n_planted, "planted beneficiaries,", rejected, "filler histories rejected")


if __name__ == "__main__":
    main()
