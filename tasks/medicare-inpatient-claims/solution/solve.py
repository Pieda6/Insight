#!/usr/bin/env python3
"""Reference solution: Medicare Part A inpatient claims under 42 CFR 409.30, 409.60-409.65 and 409.80-409.87.

Walks each beneficiary's history one calendar day at a time from the first day of entitlement, keeping the
benefit-period state and the lifetime counters, and prices every day of every claim in the queue."""
import csv
import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

DATA = Path("/app/data")
OUT = Path("/app/output")
ONE = timedelta(days=1)
HOSPITALS = {"general_hospital", "critical_access_hospital", "psychiatric_hospital"}


def j(name):
    return json.loads((DATA / name).read_text())


def d(s):
    return date.fromisoformat(s)


def days(a, b):
    """Inpatient days of a stay: admission day up to, not including, the discharge day."""
    x = a
    while x < b:
        yield x
        x += ONE


def qualifying_hospital_stay(stays, snf, ftype):
    """409.30: the hospital or CAH stay before the SNF admission lasted 3 days (discharge day not counted) and
    the SNF admission came within 30 days of that discharge."""
    prior = [s for s in stays if ftype[s["facility_id"]] in ("general_hospital", "critical_access_hospital")
             and d(s["discharge_date"]) <= d(snf["inpatient_admission_date"])]
    if not prior:
        return False
    h = max(prior, key=lambda s: s["discharge_date"])
    los = (d(h["discharge_date"]) - d(h["inpatient_admission_date"])).days
    wait = (d(snf["inpatient_admission_date"]) - d(h["discharge_date"])).days
    return los >= 3 and wait <= 30


def beneficiary(ben, stays, partb, ftype, amounts):
    ent = d(ben["part_a_entitlement_date"])
    stays = sorted(stays, key=lambda s: s["inpatient_admission_date"])
    hosp, snf_day, skilled = {}, {}, set()
    for s in stays:
        for x in days(d(s["inpatient_admission_date"]), d(s["discharge_date"])):
            if ftype[s["facility_id"]] in HOSPITALS:
                hosp[x] = s
            else:
                snf_day[x] = s
                if x <= d(s["skilled_level_of_care_through"]):
                    skilled.add(x)
    # 409.63: in a participating psychiatric hospital on the first day of entitlement
    cap = None
    if ent in hosp and ftype[hosp[ent]["facility_id"]] == "psychiatric_hospital":
        before = sum(1 for k in range(1, 151) if ent - timedelta(days=k) in hosp
                     and ftype[hosp[ent - timedelta(days=k)]["facility_id"]] == "psychiatric_hospital")
        cap = 150 - before
    qual = {s["stay_id"]: qualifying_hospital_stay(stays, s, ftype) for s in stays
            if ftype[s["facility_id"]] == "skilled_nursing_facility"}
    blood = defaultdict(list)
    for s in stays:
        for u in s["blood_furnished"]:
            blood[d(u["date"])].append((s["stay_id"], u))
    for u in partb:
        blood[d(u["date"])].append((None, u))
    out = defaultdict(lambda: {"bp": None, "cov": 0, "res": 0, "ded": 0, "coins": 0, "blood": 0})
    bp = None
    idle = 0
    period_no = 0
    lifetime_reserve = 60
    psych_hospital_days = 0
    initial_psych = 0
    year_units = defaultdict(int)
    paid = set()
    first = min([ent] + [d(s["inpatient_admission_date"]) for s in stays])
    last = max(d(s["discharge_date"]) for s in stays)
    x = first
    while x <= last:
        if x >= ent:
            inpatient = x in hosp or x in skilled                       # 409.60(b): SNF only at skilled level
            if inpatient:
                if bp is None:                                          # 409.60(a)
                    bp, period_no, hosp_used, snf_used, deductible_taken = x, period_no + 1, 0, 0, False
                idle = 0
            elif bp is not None:
                idle += 1
                if idle == 60:                                          # 409.60(b)(1)
                    bp = None
            for table in (hosp, snf_day):
                if x in table and out[table[x]["stay_id"]]["bp"] is None:
                    out[table[x]["stay_id"]]["bp"] = bp
            amt = amounts.get(str(x.year))
            if x in hosp:
                s = hosp[x]
                o = out[s["stay_id"]]
                psych_hospital = ftype[s["facility_id"]] == "psychiatric_hospital"
                psych = psych_hospital or s.get("treated_for_mental_illness", False)
                allowed = not (psych_hospital and psych_hospital_days >= 190)                  # 409.62
                if cap is not None and period_no == 1 and psych and initial_psych >= cap:     # 409.63
                    allowed = False
                kind = None
                if allowed:
                    if hosp_used < 90:                                  # 409.61(a)(1)
                        hosp_used += 1
                        kind = "full" if hosp_used <= 60 else "coins"
                    elif lifetime_reserve > 0:                          # 409.61(a)(2), 409.65
                        lifetime_reserve -= 1
                        kind = "reserve"
                if kind:
                    paid.add(x)
                    o["cov"] += 1
                    if kind == "coins":                                 # 409.83(a)(2), (a)(5)
                        o["coins"] += amt["hospital_coinsurance_days_61_90"] if amt else 0
                    if kind == "reserve":
                        o["res"] += 1
                        o["coins"] += amt["hospital_coinsurance_lifetime_reserve_days"] if amt else 0
                    if psych_hospital:
                        psych_hospital_days += 1
                    if cap is not None and period_no == 1 and psych:
                        initial_psych += 1
                    if not deductible_taken:                            # 409.82(a)
                        deductible_taken = True
                        o["ded"] = amt["inpatient_hospital_deductible"] if amt else 0
            if x in snf_day:
                s = snf_day[x]
                o = out[s["stay_id"]]
                if x in skilled and qual[s["stay_id"]] and snf_used < 100:                  # 409.30, 409.61(b)
                    snf_used += 1
                    paid.add(x)
                    o["cov"] += 1
                    if snf_used > 20:                                   # 409.85
                        o["coins"] += amt["snf_coinsurance_days_21_100"] if amt else 0
        for sid, u in sorted(blood.get(x, ()), key=lambda t: t[0] is not None):              # 409.87
            if u["product"] not in ("whole_blood", "packed_red_cells"):
                continue
            left = max(0, 3 - year_units[x.year])
            if sid is not None and not u["replaced_or_obtained_free"]:
                out[sid]["blood"] += min(u["units"], left) * u["charge_per_unit_cents"]
            year_units[x.year] += u["units"]
        x += ONE
    return out


def money(c):
    return f"{c // 100}.{c % 100:02d}"


def main():
    ftype = {f["facility_id"]: f["type"] for f in j("facilities.json")}
    amounts = j("part_a_amounts.json")["by_calendar_year"]
    stays = defaultdict(list)
    for s in j("stays.json"):
        stays[s["beneficiary_id"]].append(s)
    partb = defaultdict(list)
    for u in j("part_b_blood.json"):
        partb[u["beneficiary_id"]].append(u)
    result = {}
    for ben in j("beneficiaries.json"):
        result.update(beneficiary(ben, stays[ben["beneficiary_id"]], partb[ben["beneficiary_id"]], ftype, amounts))
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "claim_determinations.csv", "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["claim_id", "benefit_period_start", "covered_days", "reserve_days", "deductible", "coinsurance",
                    "blood"])
        for c in j("claims.json"):
            o = result[c["stay_id"]]
            w.writerow([c["claim_id"], o["bp"].isoformat(), o["cov"], o["res"], money(o["ded"]), money(o["coins"]),
                        money(o["blood"])])


if __name__ == "__main__":
    main()
