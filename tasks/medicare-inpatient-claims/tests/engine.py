"""Verifier-side model of Medicare Part A inpatient cost sharing (42 CFR 409.30, 409.60-409.65, 409.80-409.87),
written independently of the reference solution: benefit periods come from merging inpatient intervals, and
each stay is priced in blocks of days rather than one day at a time. Reads only the verifier's private inputs."""
import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"


def load(name):
    return json.loads((DATA / name).read_text())


def iso(s):
    return date.fromisoformat(s)


class Facility:
    def __init__(self, rec):
        self.kind = rec["type"]
        self.hospital = rec["type"] != "skilled_nursing_facility"
        self.psychiatric = rec["type"] == "psychiatric_hospital"
        self.acute = rec["type"] in ("general_hospital", "critical_access_hospital")


class Stay:
    def __init__(self, rec, fac, entitled):
        self.id, self.fac = rec["stay_id"], fac
        self.admit, self.leave = iso(rec["inpatient_admission_date"]), iso(rec["discharge_date"])
        self.start = max(self.admit, entitled)                    # nothing before entitlement is a benefit day
        self.mental = fac.psychiatric or rec.get("treated_for_mental_illness", False)
        self.skilled_end = (iso(rec["skilled_level_of_care_through"]) + timedelta(days=1)
                            if not fac.hospital else self.leave)  # exclusive
        self.blood = rec["blood_furnished"]

    def counted_interval(self):
        """Days on which the beneficiary is an inpatient for benefit-period purposes (409.60(b))."""
        return self.start, (self.leave if self.fac.hospital else min(self.leave, self.skilled_end))


def periods(stays):
    """Merge inpatient intervals; a gap of 60 or more non-inpatient days ends a benefit period."""
    spans = sorted(s.counted_interval() for s in stays if s.counted_interval()[0] < s.counted_interval()[1])
    out = []
    for a, b in spans:
        if out and (a - out[-1][1]).days < 60:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def rates(amounts, day):
    return amounts.get(str(day.year)) or defaultdict(int)


def price_hospital(stay, period, life, initial_cap, amounts):
    length = (stay.leave - stay.start).days
    room = (90 - period["hospital"]) + life["reserve"]
    limit = length
    if stay.fac.psychiatric:
        limit = min(limit, 190 - life["psych"])
    if initial_cap is not None and period["index"] == 0 and stay.mental:
        limit = min(limit, initial_cap - life["initial_psych"])
    covered = max(0, min(limit, room))
    regular = min(covered, 90 - period["hospital"])
    full = min(regular, max(0, 60 - period["hospital"]))
    reserve = covered - regular
    coins = 0
    for k in range(full, covered):
        day = stay.start + timedelta(days=k)
        coins += rates(amounts, day)["hospital_coinsurance_days_61_90" if k < regular
                                     else "hospital_coinsurance_lifetime_reserve_days"]
    period["hospital"] += regular
    life["reserve"] -= reserve
    if stay.fac.psychiatric:
        life["psych"] += covered
    if initial_cap is not None and period["index"] == 0 and stay.mental:
        life["initial_psych"] += covered
    deductible = 0
    if covered and not period["deductible"]:
        period["deductible"] = True
        deductible = rates(amounts, stay.start)["inpatient_hospital_deductible"]
    return covered, reserve, deductible, coins, set(stay.start + timedelta(days=k) for k in range(covered))


def price_snf(stay, prior, period, amounts):
    if prior is None:
        return 0, 0, 0, 0, set()
    stayed = (prior.leave - prior.admit).days
    waited = (stay.admit - prior.leave).days
    if stayed < 3 or waited > 30:
        return 0, 0, 0, 0, set()
    skilled = (min(stay.leave, stay.skilled_end) - stay.start).days
    covered = max(0, min(skilled, 100 - period["snf"]))
    coins = 0
    for k in range(covered):
        if period["snf"] + k + 1 > 20:
            coins += rates(amounts, stay.start + timedelta(days=k))["snf_coinsurance_days_21_100"]
    period["snf"] += covered
    return covered, 0, 0, coins, set(stay.start + timedelta(days=k) for k in range(covered))


def beneficiary(ben, recs, partb, facilities, amounts):
    entitled = iso(ben["part_a_entitlement_date"])
    stays = sorted((Stay(r, facilities[r["facility_id"]], entitled) for r in recs), key=lambda s: s.admit)
    bps = periods(stays)
    initial_cap = None
    on_day_one = [s for s in stays if s.admit <= entitled < s.leave and s.fac.psychiatric]
    if on_day_one:
        window_start = entitled - timedelta(days=150)
        before = sum(max(0, (min(s.leave, entitled) - max(s.admit, window_start)).days)
                     for s in stays if s.fac.psychiatric)
        initial_cap = 150 - before
    life = {"reserve": 60, "psych": 0, "initial_psych": 0}
    state = [{"index": i, "hospital": 0, "snf": 0, "deductible": False} for i in range(len(bps))]
    result, covered_days = {}, {}
    for s in stays:
        idx = next(i for i, (a, b) in enumerate(bps) if a <= s.start < b + timedelta(days=60))
        if s.fac.hospital:
            cov, res, ded, coins, paid = price_hospital(s, state[idx], life, initial_cap, amounts)
        else:
            earlier = [p for p in stays if p.fac.acute and p.leave <= s.admit]
            prior = max(earlier, key=lambda p: p.leave) if earlier else None
            cov, res, ded, coins, paid = price_snf(s, prior, state[idx], amounts)
        result[s.id] = {"bp": bps[idx][0], "covered": cov, "reserve": res, "deductible": ded, "coinsurance": coins,
                        "blood": 0}
        covered_days[s.id] = paid
    transfusions = [(iso(u["date"]), 1, s.id, u) for s in stays for u in s.blood] + \
                   [(iso(u["date"]), 0, None, u) for u in partb]
    used = defaultdict(int)
    for when, _, sid, u in sorted(transfusions, key=lambda t: (t[0], t[1])):
        if u["product"] not in ("whole_blood", "packed_red_cells"):
            continue
        deductible_units = min(u["units"], max(0, 3 - used[when.year]))
        used[when.year] += u["units"]
        if sid is not None and not u["replaced_or_obtained_free"]:
            result[sid]["blood"] += deductible_units * u["charge_per_unit_cents"]
    return result


def cents(v):
    return f"{v // 100}.{v % 100:02d}"


def expected():
    facilities = {f["facility_id"]: Facility(f) for f in load("facilities.json")}
    amounts = load("part_a_amounts.json")["by_calendar_year"]
    by_ben = defaultdict(list)
    for r in load("stays.json"):
        by_ben[r["beneficiary_id"]].append(r)
    partb = defaultdict(list)
    for u in load("part_b_blood.json"):
        partb[u["beneficiary_id"]].append(u)
    priced = {}
    for ben in load("beneficiaries.json"):
        priced.update(beneficiary(ben, by_ben[ben["beneficiary_id"]], partb[ben["beneficiary_id"]], facilities,
                                  amounts))
    out = {}
    for c in load("claims.json"):
        p = priced[c["stay_id"]]
        out[c["claim_id"]] = {"benefit_period_start": p["bp"].isoformat(), "covered_days": str(p["covered"]),
                              "reserve_days": str(p["reserve"]), "deductible": cents(p["deductible"]),
                              "coinsurance": cents(p["coinsurance"]), "blood": cents(p["blood"])}
    return out
