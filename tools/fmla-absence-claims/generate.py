#!/usr/bin/env python3
"""Generate the fmla-absence-claims inputs (dev only, never shipped).

An absence-management firm administers FMLA leave (29 CFR Part 825) for four client employers, each using a
different 12-month method (825.200(b)). For every absence the claims examiner must say how many hours are
FMLA leave. Hours interact across: the employer's 12-month method, the military caregiver single 12-month
period and its 26-week combined limit (825.127(e)), full weeks containing holidays and business closures
(825.200(h)), the 12-month employment requirement reached during a continuous leave (825.110), and the end of
bonding entitlement 12 months after birth (825.120(a)(2)). Planted employees carry hand-worked answers.
"""
import json
import random
import shutil
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "tasks" / "fmla-absence-claims"
ENV, TST = ROOT / "environment" / "data", ROOT / "tests" / "data"
rng = random.Random(82500)
DAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
ONE = timedelta(days=1)


def D(s):
    return date.fromisoformat(s)


def plus_year(d):
    return d.replace(year=d.year + 1)


HOLI = {2024: ["2024-07-04", "2024-09-02", "2024-11-28", "2024-12-25"],
        2025: ["2025-01-01", "2025-05-26", "2025-07-04", "2025-09-01", "2025-11-27", "2025-12-25"],
        2026: ["2026-01-01", "2026-05-25", "2026-07-03", "2026-09-07"]}
HOLIDAYS = sorted(D(x) for v in HOLI.values() for x in v)
EMPLOYERS = {
    "NORTHWIND": dict(name="Northwind Logistics", method="calendar_year", leave_year_start=None,
                      closures=[("2025-12-21", "2026-01-03")]),
    "BRIGHTWATER": dict(name="Brightwater Health System", method="rolling_backward", leave_year_start=None,
                        closures=[]),
    "IRONGATE": dict(name="Irongate Manufacturing", method="fixed_leave_year", leave_year_start="07-01",
                     closures=[("2025-06-29", "2025-07-05")]),
    "SUMMIT": dict(name="Summit Insurance Group", method="forward_from_first_leave", leave_year_start=None,
                   closures=[]),
}
CLOSED = {k: {D(a) + timedelta(days=i) for a, b in v["closures"] for i in range((D(b) - D(a)).days + 1)}
          for k, v in EMPLOYERS.items()}
PATTERNS = {
    "5x8": {"Monday": 480, "Tuesday": 480, "Wednesday": 480, "Thursday": 480, "Friday": 480},
    "4x10": {"Monday": 600, "Tuesday": 600, "Wednesday": 600, "Thursday": 600},
    "5x7.5": {"Monday": 450, "Tuesday": 450, "Wednesday": 450, "Thursday": 450, "Friday": 450},
    "3x12": {"Sunday": 720, "Wednesday": 720, "Thursday": 720},
    "4x6": {"Tuesday": 360, "Wednesday": 360, "Thursday": 360, "Friday": 360},
}


class Reject(Exception):
    pass


def dname(d):
    return DAYS[(d.weekday() + 1) % 7]


def week_start(d):
    return d - timedelta(days=(d.weekday() + 1) % 7)                 # Sunday


def sim(emp, absences, strict=True):
    """Third implementation, used to reject contested filler and to check planted answers.
    Returns {absence index: minutes of FMLA leave}."""
    er = EMPLOYERS[emp["employer"]]
    pat = PATTERNS[emp["pattern"]]
    weekly = sum(pat.values())
    elig = plus_year(emp["hire"])
    days = []                                    # (date, absence index, minutes off)
    cont = {}
    for i, a in enumerate(absences):
        if a["type"] == "continuous":
            d = a["start"]
            while d <= a["end"]:
                cont[d] = i
                days.append((d, i, None))
                d += ONE
        else:
            if strict and a["start"] < elig:
                raise Reject("intermittent leave before eligibility")
            days.append((a["start"], i, a["minutes"]))
    if strict and len({d for d, _, _ in days}) != len(days):
        raise Reject("two absences on one day")
    days.sort()
    full_weeks = set()
    for d in cont:
        ws = week_start(d)
        wd = [ws + timedelta(days=k) for k in range(7) if dname(ws + timedelta(days=k)) in pat]
        if all(x in cont for x in wd) and not any(x in CLOSED[emp["employer"]] for x in wd):
            if strict and len({absences[cont[x]]["reason"] for x in wd}) > 1:
                raise Reject("full week with two reasons")
            full_weeks.add(ws)
    out = {i: 0 for i in range(len(absences))}
    charged = []                                  # (date, minutes, caregiver?)
    single = None
    period = None                                 # forward-from-first-leave period start
    for d, i, mins in days:
        a = absences[i]
        sched = pat.get(dname(d), 0)
        if mins is None:
            h = sched
            if d in HOLIDAYS and week_start(d) not in full_weeks and not emp["holidays"]:
                h = 0
        else:
            h = mins
            if strict and mins > sched:
                raise Reject("more hours than scheduled")
        if d in CLOSED[emp["employer"]]:
            h = 0
        if h == 0 or d < elig:
            continue
        if a["reason"] == "bonding" and d >= plus_year(a["birth"]):
            continue
        care = a["reason"] == "military_caregiver"
        if care and single is None:
            single = d
        in_single = single is not None and single <= d < plus_year(single)
        if strict and care and not in_single:
            raise Reject("caregiver leave after the single period")
        if strict and care and er["method"] == "forward_from_first_leave":
            raise Reject("caregiver leave at a forward-from-first-leave employer")
        combined_left = 26 * weekly - sum(m for x, m, c in charged if single and single <= x < plus_year(single))
        if care:
            avail = combined_left
        else:
            m = er["method"]
            if m == "calendar_year":
                used = sum(mm for x, mm, c in charged if not c and x.year == d.year)
            elif m == "fixed_leave_year":
                ly = lambda x: x.year if (x.month, x.day) >= (7, 1) else x.year - 1  # noqa: E731
                used = sum(mm for x, mm, c in charged if not c and ly(x) == ly(d))
            elif m == "rolling_backward":
                lo = d.replace(year=d.year - 1)
                used = sum(mm for x, mm, c in charged if not c and lo < x < d)
            else:
                if period is None or d >= plus_year(period):
                    period = d
                used = sum(mm for x, mm, c in charged if not c and period <= x < plus_year(period))
            avail = 12 * weekly - used
            if in_single:
                avail = min(avail, combined_left)
        take = max(0, min(h, avail))
        if strict and 0 < take < h and week_start(d) in full_weeks and any(
                x in HOLIDAYS for x in [week_start(d) + timedelta(days=k) for k in range(7)]):
            raise Reject("entitlement runs out in a full week with a holiday")
        if take:
            charged.append((d, take, care))
            out[i] += take
    return out


class World:
    def __init__(self):
        self.emps = []

    def add(self, employer, pattern, hire, absences, tags, expected=None, holidays=False):
        e = {"employer": employer, "pattern": pattern, "hire": D(hire) if isinstance(hire, str) else hire,
             "absences": absences, "tags": tags, "expected": expected, "holidays": holidays}
        self.emps.append(e)
        return e


def C(reason, start, end, **kw):
    return dict(reason=reason, type="continuous", start=D(start), end=D(end),
                birth=D(kw["birth"]) if "birth" in kw else None)


def I(reason, day, hours, **kw):
    return dict(reason=reason, type="intermittent", start=D(day), end=D(day), minutes=int(hours * 60),
                birth=D(kw["birth"]) if "birth" in kw else None)


H = 60


def planted(w):
    own, fam, bond, care = "own_serious_health_condition", "family_member_serious_health_condition", "bonding", \
        "military_caregiver"
    # calendar year, 5 x 8 (12 weeks = 480 h). 10 weeks in 2025 (400 h), then 3 weeks Nov 30 - Dec 20:
    # only 80 h left (2 weeks); Jan 5 2026 starts a new year: 40 h
    w.add("NORTHWIND", "5x8", "2020-03-02",
          [C(own, "2025-02-02", "2025-04-12"), C(own, "2025-11-30", "2025-12-20"), C(own, "2026-01-04", "2026-01-10")],
          ["calendar-year", "exhaustion"], {0: 400 * H, 1: 80 * H, 2: 40 * H})
    # full week with a holiday counts as a week (Nov 23-29 2025 includes Nov 27): 40 h; a partial week with the
    # holiday (Mon-Thu Nov 24-27) counts only the 3 non-holiday days: 24 h
    w.add("NORTHWIND", "5x8", "2020-03-02", [C(own, "2025-11-23", "2025-11-29")], ["holiday", "full-week"], {0: 40 * H})
    w.add("NORTHWIND", "5x8", "2020-03-02", [C(fam, "2025-11-24", "2025-11-27")], ["holiday"], {0: 24 * H})
    # business closure Dec 21 - Jan 3: leave Dec 14 - Jan 10 is charged only Dec 15-19 and Jan 5-9: 80 h
    w.add("NORTHWIND", "5x8", "2020-03-02", [C(own, "2025-12-14", "2026-01-10")], ["closure"], {0: 80 * H})
    # rolling backward, 4 x 10 (12 weeks = 480 h). 4 weeks from Feb 1 2025 (Feb 2 - Mar 1: 160 h), 4 weeks from
    # Jun 1 (Jun 1-28: 160 h), 4 weeks from Nov 2 (Nov 2-29: 160 h, Thanksgiving in a full week). On Jan 20 2026
    # all 480 h of the past 12 months are used: 0. On Feb 10 2026 the window is Feb 11 2025 - Feb 9 2026, so
    # Feb 3, 4, 5, 6 and 10 2025 (50 h) have dropped out: 50 h available, the 10 h are FMLA
    w.add("BRIGHTWATER", "4x10", "2019-05-06",
          [C(own, "2025-02-02", "2025-03-01"), C(own, "2025-06-01", "2025-06-28"), C(own, "2025-11-02", "2025-11-29"),
           I(own, "2026-01-20", 10), I(own, "2026-02-10", 10)],
          ["rolling", "exhaustion"], {0: 160 * H, 1: 160 * H, 2: 160 * H, 3: 0, 4: 10 * H})
    # forward from first leave, 5 x 7.5 (12 weeks = 450 h). Period from Mar 3 2025 (the first leave day): 6 weeks
    # (225 h), then 7 weeks Aug 3 - Sep 20 of which 6 remain (225 h; Labor Day sits in a full week and counts).
    # The period ran to Mar 2 2026; the next begins with the next leave, Mar 4 2026: 7.5 h
    w.add("SUMMIT", "5x7.5", "2018-01-08",
          [C(own, "2025-03-02", "2025-04-12"), C(own, "2025-08-03", "2025-09-20"), I(own, "2026-03-04", 7.5)],
          ["forward", "exhaustion"], {0: 225 * H, 1: 225 * H, 2: int(7.5 * H)})
    # 12 months of employment reached during a continuous leave (hired Mar 10 2025, eligible Mar 10 2026):
    # leave Mar 1 - Mar 21 2026 counts Mar 10-13 and Mar 16-20 only: 9 days x 8 h
    w.add("NORTHWIND", "5x8", "2025-03-10", [C(own, "2026-03-01", "2026-03-21")], ["eligibility"], {0: 72 * H})
    # bonding ends 12 months after the birth (Apr 15 2025): leave Apr 5 - Apr 25 2026 counts Apr 6-10 and
    # Apr 13-14 only: 7 days x 8 h
    w.add("IRONGATE", "5x8", "2017-09-11", [C(bond, "2026-04-05", "2026-04-25", birth="2025-04-15")],
          ["bonding"], {0: 56 * H})
    # fixed leave year from Jul 1. 11 weeks May 4 - Jul 18 2025 straddle the leave year: closure Jun 29 - Jul 5
    # is not charged; May 4 - Jun 28 is 8 weeks (320 h) in the 2024 year, Jul 6-18 is 2 weeks (80 h) in 2025
    w.add("IRONGATE", "5x8", "2017-09-11", [C(own, "2025-05-04", "2025-07-19")], ["fixed-year", "closure"],
          {0: 400 * H})
    # military caregiver: single period from Jan 6 2025 (first leave day) to Jan 5 2026; 20 weeks of caregiver leave (800 h),
    # then 8 weeks for her own condition Aug 3 - Sep 26 (calendar year: 12 weeks free, but only 6 weeks of the
    # combined 26 remain = 240 h); Jan 11 2026 is outside the single period: a week of own leave counts fully
    # under the calendar-year method (Labor Day Sep 1 2025 falls in a full week)
    w.add("NORTHWIND", "5x8", "2015-06-01",
          [C(care, "2025-01-05", "2025-05-24"), C(own, "2025-08-03", "2025-09-27"), C(own, "2026-01-11", "2026-01-17")],
          ["caregiver"], {0: 800 * H, 1: 240 * H, 2: 40 * H})
    # caregiver at a rolling employer: 10 weeks of own leave first (Mar 2 - May 9 2025, 400 h); caregiver leave
    # from Jun 1 for 20 weeks (Jun 1 - Oct 18, 800 h); own leave Nov 2-15 2025: the 12-week limit leaves 80 h
    # (the 400 h of Mar-May are in the past 12 months), and the combined 26 weeks (only leave inside the single
    # period counts: 800 h) leaves 240 h: 80 h
    w.add("BRIGHTWATER", "5x8", "2016-02-01",
          [C(own, "2025-03-02", "2025-05-10"), C(care, "2025-06-01", "2025-10-18"), C(own, "2025-11-02", "2025-11-15")],
          ["caregiver", "rolling"], {0: 400 * H, 1: 800 * H, 2: 80 * H})
    # a nurse scheduled on holidays (3 x 12): Thursday Nov 27 2025 taken as a single day still counts 12 h
    w.add("BRIGHTWATER", "3x12", "2019-05-06", [C(fam, "2025-11-27", "2025-11-27")], ["holiday"], {0: 12 * H},
          holidays=True)


def filler(w):
    er = rng.choice(list(EMPLOYERS))
    pat = rng.choice(list(PATTERNS))
    hire = D("2014-01-06") + timedelta(days=rng.randrange(0, 4200))
    if hire.month == 2 and hire.day == 29:
        return False
    holidays = pat == "3x12" and rng.random() < 0.7
    reasons = ["own_serious_health_condition", "family_member_serious_health_condition", "qualifying_exigency"]
    abs_, t = [], max(D("2024-07-01"), hire + timedelta(days=rng.choice([100, 300, 360])))
    caregiver_done = er == "SUMMIT" or rng.random() < 0.75
    birth = None
    while t < D("2026-09-01"):
        kind = rng.random()
        if not caregiver_done and kind < 0.15:
            weeks = rng.choice([8, 12, 16, 20, 24])
            s = week_start(t) + timedelta(days=rng.choice([0, 1, 3]))
            abs_.append(C("military_caregiver", str(s), str(s + timedelta(days=7 * weeks - 1))))
            caregiver_done = True
            t = s + timedelta(days=7 * weeks + rng.choice([10, 30, 60]))
            continue
        if birth is None and kind < 0.25:
            birth = t - timedelta(days=rng.choice([0, 20, 200, 340, 365]))
            s = t
            e = s + timedelta(days=rng.choice([13, 27, 41, 55, 83]))
            abs_.append(C("bonding", str(s), str(e), birth=str(birth)))
            t = e + timedelta(days=rng.choice([20, 90]))
            continue
        if kind < 0.6:
            s = t + timedelta(days=rng.choice([0, 1, 2, 3]))
            e = s + timedelta(days=rng.choice([3, 6, 13, 20, 27, 34, 48, 62, 76]))
            abs_.append(C(rng.choice(reasons), str(s), str(e)))
            t = e + timedelta(days=rng.choice([5, 30, 60, 120, 200]))
        else:
            reason = rng.choice(reasons)
            for _ in range(rng.choice([3, 6, 10, 15])):
                d = t + timedelta(days=rng.randrange(1, 12))
                sched = PATTERNS[pat].get(dname(d), 0)
                if sched:
                    abs_.append(I(reason, str(d), rng.choice([sched, sched, sched / 2, 120, 240]) / 60))
                t = d + ONE
            t += timedelta(days=rng.choice([10, 40, 90]))
    abs_ = [a for a in abs_ if a["end"] <= D("2026-09-30")]
    if not abs_:
        return False
    e = {"employer": er, "pattern": pat, "hire": hire, "holidays": holidays}
    try:
        sim(e, abs_, strict=True)
    except (Reject, ValueError):                 # ValueError: a February 29 anchor date, kept out of the data
        return False
    w.add(er, pat, hire, abs_, ["filler"], None, holidays)
    return True


def main():
    w = World()
    planted(w)
    for e in w.emps:
        got = sim(e, e["absences"], strict=True)
        assert got == e["expected"], (e["tags"], got, e["expected"])
    n_planted = len(w.emps)
    rejected = 0
    while len(w.emps) < n_planted + 75:
        if not filler(w):
            rejected += 1
    rng.shuffle(w.emps)
    emps, absences, golden, tags = [], [], {}, {}
    rows = []
    for n, e in enumerate(w.emps, 1):
        eid = f"E{n:03d}"
        emps.append({"employee_id": eid, "employer_id": e["employer"], "hire_date": e["hire"].isoformat(),
                     "weekly_schedule_hours": {k: v / 60 for k, v in PATTERNS[e["pattern"]].items()},
                     "scheduled_to_work_on_holidays": e["holidays"]})
        for i, a in enumerate(e["absences"]):
            rows.append((eid, e, i, a))
    rng.shuffle(rows)
    for n, (eid, e, i, a) in enumerate(rows, 1):
        aid = f"A{n:04d}"
        rec = {"absence_id": aid, "employee_id": eid, "reason": a["reason"], "type": a["type"],
               "start_date": a["start"].isoformat(), "end_date": a["end"].isoformat()}
        if a["type"] == "intermittent":
            rec["hours_absent"] = a["minutes"] / 60
        if a["reason"] == "bonding":
            rec["child_birth_date"] = a["birth"].isoformat()
        absences.append(rec)
        tags[aid] = e["tags"]
        if e["expected"] is not None:
            golden[aid] = f"{e['expected'][i] / 60:.2f}"
    absences.sort(key=lambda r: r["absence_id"])
    ENV.mkdir(parents=True, exist_ok=True)
    for old in ENV.iterdir():
        old.unlink()
    dump = lambda n, o: (ENV / n).write_text(json.dumps(o, indent=1) + "\n")  # noqa: E731
    dump("employers.json", [{"employer_id": k, "name": v["name"], "twelve_month_period_method": v["method"],
                             "leave_year_starts": v["leave_year_start"], "workweek": "Sunday through Saturday",
                             "holidays": [d.isoformat() for d in HOLIDAYS],
                             "business_closures": [{"first_day": a, "last_day": b} for a, b in v["closures"]]}
                            for k, v in EMPLOYERS.items()])
    dump("employees.json", emps)
    dump("absences.json", absences)
    if TST.exists():
        shutil.rmtree(TST)
    shutil.copytree(ENV, TST)
    (ROOT / "tests" / "case_tags.json").write_text(json.dumps(tags, indent=1, sort_keys=True) + "\n")
    (ROOT / "tests" / "golden.json").write_text(json.dumps(golden, indent=1, sort_keys=True) + "\n")
    print(len(emps), "employees,", len(absences), "absences,", len(golden), "hand-worked,", rejected, "rejected")


if __name__ == "__main__":
    main()
