#!/usr/bin/env python3
"""Generate the feca-wage-loss-claims inputs (dev only, never shipped).

An agency's injury compensation office audits traumatic injury and occupational disease claims of its employees under the
FECA (5 U.S.C. 8105, 8110, 8114, 8117, 8118; 20 CFR 10.5, 10.200-10.224, 10.400-10.425). For each claim it needs the
days charged to continuation of pay (COP), the last COP day, the days of wage-loss compensation payable and the amount.
`sim` is the third implementation; in strict mode it rejects any claim whose answer would depend on an open reading.
"""
import json
import random
import shutil
from datetime import date, datetime, time, timedelta
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "tasks" / "feca-wage-loss-claims"
ENV, TST = ROOT / "environment" / "data", ROOT / "tests" / "data"
rng = random.Random(81180)
DAY = timedelta(days=1)
LAST = date(2026, 9, 30)
COLAS = [(date(2023, 3, 1), Fraction("8.7")), (date(2024, 3, 1), Fraction("3.2")), (date(2025, 3, 1), Fraction("2.5")),
         (date(2026, 3, 1), Fraction("2.8"))]
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MULT = {"5": 260, "5.5": 280, "6": 300}


def days(n):
    return timedelta(days=n)


def D(s):
    return date.fromisoformat(s) if isinstance(s, str) else s


def add_months(d, n):
    k = d.year * 12 + d.month - 1 + n
    y, m = k // 12, k % 12 + 1
    import calendar
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def year_before(d):
    return add_months(d, -12)


def federal_holidays(y):
    def nth(month, weekday, n):
        d = date(y, month, 1)
        d += days((weekday - d.weekday()) % 7)
        return d + days(7 * (n - 1))

    def last(month, weekday):
        d = date(y + (month == 12), month % 12 + 1, 1) - DAY
        return d - days((d.weekday() - weekday) % 7)

    out = set()
    for h in (date(y, 1, 1), date(y, 6, 19), date(y, 7, 4), date(y, 11, 11), date(y, 12, 25)):
        out.add(h - DAY if h.weekday() == 5 else h + DAY if h.weekday() == 6 else h)
    out |= {nth(1, 0, 3), nth(2, 0, 3), last(5, 0), nth(9, 0, 1), nth(10, 0, 2), nth(11, 3, 4)}
    return out


HOLIDAYS = set().union(*(federal_holidays(y) for y in range(2022, 2028)))


class Reject(Exception):
    pass


# ---------------------------------------------------------------- the third implementation
def annual_pay(emp, d):
    cur = [p for p in emp["pay"] if p["effective"] <= d][-1]
    if emp["plan"] == "GS":
        return Fraction(cur["base"]) * (100 + cur["standby"]) / 100
    return Fraction(cur["daily"]) * MULT[emp["workweek"]]


def dependent_on(emp, d):
    for dp in emp["dependents"]:
        if dp["rel"] == "spouse" and dp["married"] <= d:
            return True
        if dp["rel"] == "child":
            b = dp["born"]
            if d < add_months(b, 12 * 18) or dp.get("incapable"):
                return True
            if d < add_months(b, 12 * 23) and any(a <= d <= z for a, z in dp.get("school", [])):
                return True
    return False


def sim(c, strict=True):
    """Third implementation: (cop_days, last_cop_day or None, compensation_days, compensation in exact cents)."""
    emp = c["emp"]
    inj_day, inj_time = c["injury"].date(), c["injury"].time()
    part_time = emp["part_time"]
    sched = emp["hours"]                                   # weekday -> hours

    def workday(d):
        return WEEKDAYS[d.weekday()] in sched

    def rec_on(d):
        for r in c["records"]:
            if r["from"] <= d <= r["to"] and (workday(d) or part_time):
                return r
        return None

    def disabled(d):
        return any(a <= d <= b for a, b in c["medical"])

    shift = emp["shift_start"]
    before_shift = workday(inj_day) and inj_time < shift
    if strict and abs((datetime.combine(inj_day, inj_time) - datetime.combine(inj_day, shift)).total_seconds()) < 60:
        raise Reject("injury at the start of the shift")
    first_loss = None
    d = inj_day if before_shift else inj_day + DAY
    while d <= LAST:
        if rec_on(d):
            first_loss = d
            break
        d += DAY
    if first_loss is None:
        raise Reject("no lost time")
    eligible = (c["kind"] == "traumatic" and c["filed"] <= inj_day + days(30) and first_loss <= inj_day + days(45))
    if strict and before_shift and rec_on(inj_day) is None:
        raise Reject("injured before the shift but worked it")

    # episodes: absences separated by days worked
    worked = lambda d: workday(d) and rec_on(d) is None and d > inj_day  # noqa: E731
    first_return = None
    d = first_loss
    while d <= LAST:
        if worked(d):
            first_return = d
            break
        d += DAY

    def episode_start(d):
        """First absence day of the episode that contains absence day d."""
        x = d
        while x > first_loss:
            y = x - DAY
            if worked(y):
                break
            x = y
        while not rec_on(x):
            x += DAY
        return x

    def cop_window(d):
        if d < (first_return or LAST + DAY):
            return True
        return episode_start(d) <= first_return + days(45)

    # COP-chargeable workdays (ignoring the 45-day cap)
    cand = set()
    span_end = LAST
    d = first_loss
    while d <= span_end:
        r = rec_on(d)
        if eligible and r and r["code"] in ("cop", "sick_leave", "annual_leave") and cop_window(d):
            if part_time:
                if disabled(d) or r.get("hours"):
                    cand.add(d)
            elif workday(d):
                cand.add(d)
        d += DAY

    def prev_work(d):
        x = d - DAY
        while not workday(x):
            x -= DAY
        return x

    def next_work(d):
        x = d + DAY
        while not workday(x):
            x += DAY
        return x

    counted, leave_counted = [], set()
    d = inj_day if before_shift else inj_day + DAY                # the first day disability begins (10.215(b))
    while d <= LAST and len(counted) < 45 and eligible:
        if d in cand:
            counted.append(d)
        elif not part_time and not workday(d) and disabled(d) and (prev_work(d) in cand or next_work(d) in cand):
            if strict and not any(x in cand and rec_on(x)["code"] == "cop" for x in (prev_work(d), next_work(d))):
                raise Reject("day off next to leave only (10.215(d) against (e))")
            if strict and prev_work(d) not in cand and len(counted) >= 44:
                raise Reject("day off counted only through a workday past the cap")
            if strict and not (prev_work(d) in cand and next_work(d) in cand) and any(abs((d - h).days) <= 1 for h in HOLIDAYS):
                raise Reject("holiday next to a day off at the edge")
            counted.append(d)
        d += DAY
    counted_set = set(counted)
    if strict and counted:                                 # a pay change between the first disabled day and the first absence
        if any(counted[0] < p["effective"] <= first_loss for p in emp["pay"]):
            raise Reject("pay change between the first day of disability and the first absence")
    if strict:
        for x in counted:                                  # holidays next to the edges of COP stretches
            if (x - DAY not in counted_set or x + DAY not in counted_set) and any(abs((x - h).days) <= 2 for h in HOLIDAYS):
                raise Reject("holiday at the edge of a COP stretch")
        for r in c["records"]:                             # appointment days only inside the 10.207 window
            if r.get("hours") and first_return and r["from"] > first_return + days(45):
                raise Reject("partial day after the 45-day window")
    last_cop = max(counted) if counted else None

    # pay loss: LWOP and requested COP that is not payable; days off between them
    if part_time:
        if strict and any(r["code"] == "lwop" or (r["code"] == "cop" and not all(
                x in counted_set for x in daterange(r["from"], min(r["to"], LAST)) if disabled(x) or r.get("hours"))) for r in c["records"]):
            raise Reject("part-time pay loss")
        return len(counted), last_cop, 0, Fraction(0)
    loss = set()
    d = first_loss
    while d <= LAST:
        r = rec_on(d)
        if workday(d) and r and (r["code"] == "lwop" or (r["code"] == "cop" and d not in counted_set)):
            if strict and r.get("hours"):
                raise Reject("partial day of pay loss")
            loss.add(d)
        d += DAY
    stretches = []
    for d in sorted(loss):
        if stretches and all((not workday(x)) for x in daterange(stretches[-1][-1] + DAY, d - DAY)):
            stretches[-1].extend(list(daterange(stretches[-1][-1] + DAY, d)))
        else:
            stretches.append([d])
    if strict:
        for st in stretches:                               # pay loss must not end or start next to days off
            if any(not workday(x) and disabled(x) for x in (st[0] - DAY, st[-1] + DAY)):
                raise Reject("pay loss next to days off of disability")
            if not all(disabled(x) for x in st):
                raise Reject("pay loss without medical evidence")
            if any(abs((x - h).days) <= 1 for h in HOLIDAYS for x in (st[0], st[-1])):
                raise Reject("holiday at the edge of pay loss")
    total = Fraction(0)
    comp_days = 0
    rate_cache = {}
    for i, st in enumerate(stretches):
        unpaid = 0
        if len(st) <= 14:
            if strict and (eligible or i > 0 or any(rec_on(x) and rec_on(x)["code"] in ("sick_leave", "annual_leave")
                                                   for x in daterange(first_loss, st[0]))):
                raise Reject("short pay loss after COP, leave or earlier pay loss (8117 against 8118(c))")
            if strict and st[-1] == LAST:
                raise Reject("pay loss still running at the end")
            unpaid = 3
        ep = episode_start(st[0])
        # pay rate (10.5(s)): injury, disability began, recurrence more than six months after the return to full-time work
        base_rate, anchor = max(annual_pay(emp, inj_day), annual_pay(emp, first_loss)), first_loss
        if first_return and ep > first_return:
            last_out = max(x for x in daterange(first_loss, ep - DAY) if rec_on(x) and not rec_on(x).get("hours"))
            back = last_out + DAY
            while not worked(back):
                back += DAY
            limit = add_months(back, 6)
            if strict and abs((ep - limit).days) <= 3:
                raise Reject("recurrence about six months after the return")
            if ep > limit and annual_pay(emp, ep) > base_rate:
                base_rate, anchor = annual_pay(emp, ep), ep
        for c_date, _ in COLAS:
            if strict and st[-1] >= c_date and abs((anchor - year_before(c_date)).days) <= 3:
                raise Reject("disability about a year before a COLA")
        for x in st[unpaid:]:
            pct = Fraction(3, 4) if dependent_on(emp, x) else Fraction(2, 3)
            f = Fraction(1)
            for c_date, p in COLAS:
                if c_date <= x and anchor < year_before(c_date):
                    f *= 1 + p / 100
            total += base_rate / 52 * pct * f / 7
            comp_days += 1
    return len(counted), last_cop, comp_days, total


def daterange(a, b):
    d = a
    while d <= b:
        yield d
        d += DAY


# ---------------------------------------------------------------- building claims
SCHEDULES = {
    "MF": {w: 8 for w in WEEKDAYS[:5]},
    "TS": {w: 8 for w in WEEKDAYS[1:6]},                 # Tuesday to Saturday, off Sunday and Monday
    "MF55": {**{w: 8 for w in WEEKDAYS[:5]}, "Saturday": 4},
    "MS6": {w: 8 for w in WEEKDAYS[:6]},
    "PT": {"Monday": 6, "Wednesday": 6, "Friday": 6},
}


def emp_(plan, sched, shift="07:00", pay=(), deps=(), workweek="5", part_time=False):
    return {"plan": plan, "hours": SCHEDULES[sched], "sched": sched, "shift_start": time.fromisoformat(shift),
            "workweek": workweek, "part_time": part_time,
            "pay": [dict(p, effective=D(p["effective"])) for p in pay],
            "dependents": [dict(x, **{k: D(v) for k, v in x.items() if k in ("married", "born")},
                                school=[(D(a), D(b)) for a, b in x.get("school", [])]) for x in deps]}


def claim_(emp, kind, injury, filed, records, medical):
    return {"emp": emp, "kind": kind, "injury": datetime.fromisoformat(injury), "filed": D(filed),
            "records": [{"from": D(r[0]), "to": D(r[1]), "code": r[2], **({"hours": r[3]} if len(r) > 3 else {})} for r in records],
            "medical": [(D(a), D(b)) for a, b in medical]}


GS = [{"effective": "2022-01-02", "base": 6200000, "standby": 0}]


def planted():
    out = []
    # injured Tuesday Mar 4 2025 at 10:15, during the shift: the injury day is not charged; COP Mar 5 to Fri Mar 21 with the
    # weekends between: 17 days. Medical evidence ends Mar 21, so the weekend after is not charged
    out.append((claim_(emp_("GS", "MF", pay=GS), "traumatic", "2025-03-04T10:15", "2025-03-05",
                       [("2025-03-05", "2025-03-21", "cop")], [("2025-03-05", "2025-03-21")]),
                ["cop-days", "days-off"], (17, "2025-03-21", 0, None)))
    # injured 06:40 before a 07:00 shift (Wed Apr 9 2025) and out that day: the injury day is charged; COP to Fri Apr 11 and
    # medical evidence through Sun Apr 13: the weekend counts: 5 days, last Apr 13
    out.append((claim_(emp_("GS", "MF", pay=GS), "traumatic", "2025-04-09T06:40", "2025-04-09",
                       [("2025-04-09", "2025-04-11", "cop")], [("2025-04-09", "2025-04-13")]),
                ["cop-days", "injury-day", "days-off"], (5, "2025-04-13", 0, None)))
    # injured 07:20 after the shift began, same dates: 2 days (Apr 10-11), weekend counts: 4, last Apr 13
    out.append((claim_(emp_("GS", "MF", pay=GS), "traumatic", "2025-04-09T07:20", "2025-04-09",
                       [("2025-04-10", "2025-04-11", "cop")], [("2025-04-10", "2025-04-13")]),
                ["cop-days", "injury-day"], (4, "2025-04-13", 0, None)))
    # two hours for medical appointments on three later days each count as a full COP day (10.215(c)): 3 + 3
    out.append((claim_(emp_("GS", "MF", pay=GS), "traumatic", "2025-05-06T13:00", "2025-05-07",
                       [("2025-05-07", "2025-05-09", "cop"), ("2025-05-20", "2025-05-20", "cop", 2),
                        ("2025-05-29", "2025-05-29", "cop", 2), ("2025-06-04", "2025-06-04", "cop", 2)],
                       [("2025-05-07", "2025-05-09")]),
                ["cop-days", "partial-days"], (6, "2025-06-04", 0, None)))
    # COP limited to 45 days: Mon Jan 6 2025 to Sun Mar 16 is 70 days of disability with COP requested; days 1-45 (Jan 7 to
    # Feb 20) are COP, Feb 21 to Mar 14 (22 days, more than 14) is pay loss, all compensable. GS 62,000: 2/3 of 62,000/52/7
    # per day, x 22 days, COLA of Mar 1 2025 not applicable (disability began Jan 7 2025)
    out.append((claim_(emp_("GS", "MF", pay=GS), "traumatic", "2025-01-06T09:00", "2025-01-06",
                       [("2025-01-07", "2025-03-14", "cop")], [("2025-01-07", "2025-03-14")]),
                ["cop-cap", "compensation"], (45, "2025-02-20", 22, Fraction(62000_00) / 52 * Fraction(2, 3) / 7 * 22)))
    # sick leave first (Jan 7-10) counts toward the 45 days: COP from Jan 13 ends after 45 days in all, Feb 20 again
    out.append((claim_(emp_("GS", "MF", pay=GS), "traumatic", "2025-01-06T09:00", "2025-01-06",
                       [("2025-01-07", "2025-01-10", "sick_leave"), ("2025-01-13", "2025-03-14", "cop")], [("2025-01-07", "2025-03-14")]),
                ["cop-cap", "leave-counted"], (45, "2025-02-20", 22, None)))
    # CA-1 filed on day 30 (Apr 3 for an injury on Mar 4 2025): COP; filed on day 31: no COP, 10 days of pay loss (Mar 5-14),
    # 3 waiting days unpaid, 7 paid
    out.append((claim_(emp_("GS", "MF", pay=GS), "traumatic", "2025-03-04T10:15", "2025-04-03",
                       [("2025-03-05", "2025-03-13", "cop")], [("2025-03-05", "2025-03-13")]),
                ["eligibility", "boundary"], (9, "2025-03-13", 0, None)))
    out.append((claim_(emp_("GS", "MF", pay=GS), "traumatic", "2025-03-04T10:15", "2025-04-04",
                       [("2025-03-05", "2025-03-13", "cop")], [("2025-03-05", "2025-03-13")]),
                ["eligibility", "boundary", "waiting-period"], (0, None, 6, Fraction(62000_00) / 52 * Fraction(2, 3) / 7 * 6)))
    # time lost first on day 46 after the injury (Jan 6 -> Feb 21 2025): no COP; 22 days of pay loss, all paid
    out.append((claim_(emp_("GS", "MF", pay=GS), "traumatic", "2025-01-06T09:00", "2025-01-06",
                       [("2025-02-21", "2025-03-14", "cop")], [("2025-02-21", "2025-03-14")]),
                ["eligibility", "boundary"], (0, None, 22, None)))
    # occupational disease: no COP; pay loss of 14 days: 3 unpaid; of 15 days: all paid
    for to, n in (("2025-03-17", 11), ("2025-03-18", 15)):
        out.append((claim_(emp_("GS", "MF", pay=GS), "occupational", "2025-03-03T10:00", "2025-03-03",
                           [("2025-03-04", to, "lwop")], [("2025-03-04", to)]),
                    ["waiting-period", "boundary"], (0, None, n, None)))
    # return Mon Mar 24 2025, stopped again Tue May 6 (43 days after the first return): COP resumes for the rest of 45;
    # stopped again Fri May 9 (46 days): no COP, pay loss May 9 to Jun 5 (28 days)
    for start, end, want in (("2025-05-06", "2025-06-24", (45, "2025-06-02", 22, None)), ("2025-05-09", "2025-06-05", (17, "2025-03-21", 28, None)),
                             ("2025-05-08", "2025-06-27", (45, "2025-06-04", 23, None))):
        out.append((claim_(emp_("GS", "MF", pay=GS), "traumatic", "2025-03-04T10:15", "2025-03-05",
                           [("2025-03-05", "2025-03-21", "cop"), (start, end, "cop")],
                           [("2025-03-05", "2025-03-21"), (start, end)]),
                    ["recurrence", "boundary"], want))
    # part-time (Mon, Wed, Fri): every calendar day of disability counts (10.215(f)): Apr 1 to May 20 2025 is 50 days; COP
    # ends after 45, May 15
    out.append((claim_(emp_("GS", "PT", pay=[{"effective": "2022-01-02", "base": 3100000, "standby": 0}], part_time=True),
                       "traumatic", "2025-03-31T11:00", "2025-04-01", [("2025-04-01", "2025-05-15", "cop")], [("2025-04-01", "2025-05-15")]),
                ["part-time", "cop-cap"], (45, "2025-05-15", 0, None)))
    # Tuesday-Saturday schedule: COP Wed Jun 4 to Sat Jun 7 2025, medical through Mon Jun 9: Sun and Mon off count: 6
    out.append((claim_(emp_("GS", "TS", pay=GS), "traumatic", "2025-06-03T10:00", "2025-06-03",
                       [("2025-06-04", "2025-06-07", "cop")], [("2025-06-04", "2025-06-09")]),
                ["days-off"], (6, "2025-06-09", 0, None)))
    # pay rate: a within-grade increase between the injury (Jan 6 2025) and the first day of pay loss is used. Occupational
    # disease, pay loss Feb 3 to Mar 3 2025 (29 days); 62,000 at injury, 64,000 from Jan 26
    out.append((claim_(emp_("GS", "MF", pay=GS + [{"effective": "2025-01-26", "base": 6400000, "standby": 0}]), "occupational",
                       "2025-01-06T09:00", "2025-01-06", [("2025-02-03", "2025-03-03", "lwop")], [("2025-02-03", "2025-03-03")]),
                ["pay-rate"], (0, None, 29, Fraction(64000_00) / 52 * Fraction(2, 3) / 7 * 29)))
    # injured Friday Jun 6 2025 at 14:00, disabled from Saturday, COP from Monday Jun 9 to Fri Jun 13: the weekend before
    # counts because COP follows it (10.215(d)): 7 days
    out.append((claim_(emp_("GS", "MF", pay=GS), "traumatic", "2025-06-06T14:00", "2025-06-06",
                       [("2025-06-09", "2025-06-13", "cop")], [("2025-06-07", "2025-06-13")]),
                ["days-off", "cop-days"], (7, "2025-06-13", 0, None)))
    # COLA: disability began Mar 5 2025, less than a year before Mar 1 2026: no adjustment on a pay loss into 2026
    out.append((claim_(emp_("GS", "MF", pay=GS), "occupational", "2025-03-04T09:00", "2025-03-04",
                       [("2025-03-05", "2026-03-31", "lwop")], [("2025-03-05", "2026-03-31")]),
                ["cola"], (0, None, (date(2026, 3, 31) - date(2025, 3, 5)).days + 1,
                           Fraction(62000_00) / 52 * Fraction(2, 3) / 7 * ((date(2026, 3, 31) - date(2025, 3, 5)).days + 1))))
    # standby premium (5545(c)(1)) is part of pay: 25% of 58,000; wage grade 5 1/2-day week: daily wage x 280
    out.append((claim_(emp_("GS", "MF", pay=[{"effective": "2022-01-02", "base": 5800000, "standby": 25}]), "occupational",
                       "2025-01-06T09:00", "2025-01-06", [("2025-02-03", "2025-03-03", "lwop")], [("2025-02-03", "2025-03-03")]),
                ["pay-rate"], (0, None, 29, Fraction(58000_00 * 125, 100) / 52 * Fraction(2, 3) / 7 * 29)))
    out.append((claim_(emp_("WG", "MF55", pay=[{"effective": "2022-01-02", "daily": 24800}], workweek="5.5"), "occupational",
                       "2025-01-06T09:00", "2025-01-06", [("2025-02-03", "2025-03-03", "lwop")], [("2025-02-03", "2025-03-03")]),
                ["pay-rate"], (0, None, 29, Fraction(248_00 * 280) / 52 * Fraction(2, 3) / 7 * 29)))
    # dependents: a child turns 18 on Feb 17 2025 during pay loss Feb 3 to Mar 3: 75% for 14 days, then 66 2/3% for 15
    out.append((claim_(emp_("GS", "MF", pay=GS, deps=[{"rel": "child", "born": "2007-02-17"}]), "occupational",
                       "2025-01-06T09:00", "2025-01-06", [("2025-02-03", "2025-03-03", "lwop")], [("2025-02-03", "2025-03-03")]),
                ["dependents"], (0, None, 29, Fraction(62000_00) / 52 / 7 * (Fraction(3, 4) * 14 + Fraction(2, 3) * 15))))
    # COLA: disability began Feb 3 2025 (more than a year before Mar 1 2026): +2.8% from Mar 1 2026 on a long pay loss
    out.append((claim_(emp_("GS", "MF", pay=GS), "occupational", "2025-01-06T09:00", "2025-01-06",
                       [("2025-02-03", "2026-03-31", "lwop")], [("2025-02-03", "2026-03-31")]),
                ["cola"], (0, None, (date(2026, 3, 31) - date(2025, 2, 3)).days + 1,
                           Fraction(62000_00) / 52 * Fraction(2, 3) / 7 * ((date(2026, 3, 1) - date(2025, 2, 3)).days + 31 * Fraction(1028, 1000)))))
    return out


def filler():
    sched = rng.choice(["MF"] * 6 + ["TS", "MF55", "MS6", "PT"])
    plan = "WG" if sched in ("MF55", "MS6") or rng.random() < 0.2 else "GS"
    workweek = {"MF55": "5.5", "MS6": "6"}.get(sched, "5")
    part_time = sched == "PT"
    inj = date(2023, 2, 1) + days(rng.randrange(0, 1200))
    if inj > date(2026, 7, 31):
        return None
    hours = SCHEDULES[sched]
    while WEEKDAYS[inj.weekday()] not in hours:
        inj += DAY
    shift = rng.choice(["06:30", "07:00", "07:30", "08:00"])
    st = datetime.combine(inj, time.fromisoformat(shift))
    if rng.random() < 0.3:
        injury = st - timedelta(minutes=rng.choice([2, 5, 15, 40]))
    else:
        injury = st + timedelta(minutes=rng.choice([3, 20, 95, 240, 330]))
    kind = "occupational" if rng.random() < 0.2 else "traumatic"
    r = rng.random()
    filed = inj + days(rng.choice([30, 31]) if r < 0.25 else rng.randrange(0, 20))
    # pay
    if plan == "GS":
        base = rng.randrange(3600000, 11000000, 100)
        pay = [{"effective": inj - days(rng.randrange(30, 600)), "base": base, "standby": rng.choice([0, 0, 0, 10, 25])}]
        if rng.random() < 0.4:
            pay.append({"effective": inj + days(rng.randrange(-20, 120)), "base": base + rng.randrange(80000, 400000, 100),
                        "standby": pay[0]["standby"]})
    else:
        daily = rng.randrange(16000, 36000, 4)
        pay = [{"effective": inj - days(rng.randrange(30, 600)), "daily": daily}]
        if rng.random() < 0.4:
            pay.append({"effective": inj + days(rng.randrange(-20, 120)), "daily": daily + rng.randrange(400, 2400, 4)})
    pay.sort(key=lambda p: p["effective"])
    deps = []
    if rng.random() < 0.5:
        deps.append({"rel": "spouse", "married": inj - days(rng.randrange(-300, 4000))})
    for _ in range(rng.choice([0, 0, 1, 2])):
        b = inj - days(rng.randrange(365 * 15, 365 * 19))
        dp = {"rel": "child", "born": b}
        if rng.random() < 0.3:
            s = add_months(b, 12 * 18) - days(rng.randrange(0, 90))
            dp["school"] = [(s, s + days(rng.randrange(200, 1200)))]
        deps.append(dp)
    emp = {"plan": plan, "hours": hours, "sched": sched, "shift_start": time.fromisoformat(shift), "workweek": workweek,
           "part_time": part_time, "pay": pay, "dependents": deps}

    def nxt_work(d):
        while WEEKDAYS[d.weekday()] not in hours:
            d += DAY
        return d

    def prv_work(d):
        while WEEKDAYS[d.weekday()] not in hours:
            d -= DAY
        return d

    records, medical = [], []
    before = injury < st
    start = inj if before else nxt_work(inj + DAY)
    if rng.random() < 0.15:
        start = nxt_work(inj + days(rng.choice([44, 45, 46, 47, 60])))
    mode = rng.random()
    length = rng.choice([5, 10, 16, 30, 44, 45, 46, 52, 60, 75, 120, 300]) if mode < 0.75 else rng.randrange(330, 760)
    end = prv_work(start + days(length - 1))
    if end < start:
        end = start
    if kind == "occupational" or rng.random() < 0.15:
        code = "lwop" if kind == "occupational" or rng.random() < 0.5 else "cop"
        if code == "lwop" and rng.random() < 0.5:
            end = prv_work(start + days(rng.choice([9, 12, 13, 14, 15, 16, 20])))
        records.append({"from": start, "to": end, "code": code})
    else:
        lead = 0
        if rng.random() < 0.25:                              # leave first
            lead_end = prv_work(start + days(rng.randrange(2, 20)))
            if lead_end < end:
                records.append({"from": start, "to": lead_end, "code": rng.choice(["sick_leave", "annual_leave"])})
                start2 = nxt_work(lead_end + DAY)
                lead = 1
        records.append({"from": start2 if lead else start, "to": end, "code": "cop" if rng.random() < 0.7 else "cop"})
    med_end = end
    if rng.random() < 0.4 and not part_time:
        nd = nxt_work(end + DAY)
        if (nd - end).days > 1:
            med_end = nd - DAY if rng.random() < 0.6 else end
    medical.append((start, med_end))
    if end > LAST:
        return None
    ret = nxt_work(med_end + DAY)
    # later partial days and a possible recurrence
    t = ret + days(rng.randrange(3, 15))
    for _ in range(rng.choice([0, 0, 1, 2, 3])):
        t = nxt_work(t)
        if t > LAST:
            break
        records.append({"from": t, "to": t, "code": "cop", "hours": rng.choice([1, 2, 3, 4])})
        t += days(rng.randrange(3, 12))
    if rng.random() < 0.45 and not part_time:
        off = rng.choice([20, 40, 44, 45, 46, 47, 60, 120, 175, 190, 200, 260])
        rs = nxt_work(ret + days(off))
        rl = rng.choice([10, 20, 30, 40, 60, 90])
        re_ = prv_work(rs + days(rl))
        if re_ <= LAST and rs > max(x["to"] for x in records):
            records.append({"from": rs, "to": re_, "code": rng.choice(["cop", "cop", "lwop"])})
            medical.append((rs, re_))
            if plan == "GS" and rng.random() < 0.5:
                pay.append({"effective": rs - days(rng.randrange(1, 60)), "base": pay[-1]["base"] + rng.randrange(150000, 500000, 100),
                            "standby": pay[-1]["standby"]})
                pay.sort(key=lambda p: p["effective"])
    records.sort(key=lambda x: x["from"])
    for a, b in zip(records, records[1:]):
        if b["from"] <= a["to"]:
            return None
    c = {"emp": emp, "kind": kind, "injury": injury, "filed": filed, "records": records, "medical": medical}
    try:
        res = sim(c)
    except Reject:
        return None
    return c, res


def main():
    claims = []
    for c, tags, want in planted():
        got = sim(c)
        cop, last, ndays, amt = want
        assert got[0] == cop and (got[1].isoformat() if got[1] else None) == last and got[2] == ndays, (tags, got, want)
        if amt is not None:
            assert got[3] == amt, (tags, float(got[3]), float(amt))
        claims.append((c, tags, True))
    n_planted = len(claims)
    rejected = 0
    while len(claims) < n_planted + 300:
        x = filler()
        if x is None:
            rejected += 1
            continue
        claims.append((x[0], ["filler"], False))
    rng.shuffle(claims)
    emps, injuries, ta, med, golden, tags_out, sim_all = [], [], [], [], {}, {}, {}
    for i, (c, tags, planted_) in enumerate(claims, 1):
        eid, cid = f"E{i:04d}", f"C{i:04d}"
        e = c["emp"]
        emps.append({"employee_id": eid, "pay_plan": e["plan"], "postal_service": False,
                     "work_schedule": "part-time" if e["part_time"] else "full-time",
                     "scheduled_hours": {w: e["hours"].get(w, 0) for w in WEEKDAYS},
                     "shift_start": e["shift_start"].strftime("%H:%M"),
                     "workweek_days": e["workweek"] if e["plan"] == "WG" else None,
                     "pay_history": [({"effective": p["effective"].isoformat(), "annual_rate_of_basic_pay_cents": p["base"],
                                       "standby_duty_premium_percent_5545c1": p["standby"]} if e["plan"] == "GS" else
                                      {"effective": p["effective"].isoformat(), "daily_wage_cents": p["daily"]}) for p in e["pay"]],
                     "overtime_pay_last_12_months_cents": rng.randrange(0, 900000, 100),
                     "dependents": [{"relationship": d["rel"],
                                     **({"date_of_marriage": d["married"].isoformat(), "lives_with_employee": True} if d["rel"] == "spouse" else
                                        {"date_of_birth": d["born"].isoformat(), "unmarried": True, "lives_with_employee": True,
                                         "incapable_of_self_support": bool(d.get("incapable")),
                                         "full_time_school_enrollment": [{"from": a.isoformat(), "to": b.isoformat()} for a, b in d.get("school", [])]})}
                                    for d in e["dependents"]]})
        injuries.append({"claim_id": cid, "employee_id": eid,
                         "claim_type": "traumatic injury (CA-1)" if c["kind"] == "traumatic" else "occupational disease (CA-2)",
                         "injury_date_time": c["injury"].strftime("%Y-%m-%dT%H:%M"), "notice_filed_with_supervisor": c["filed"].isoformat()})
        for r in c["records"]:
            ta.append({"claim_id": cid, "from": r["from"].isoformat(), "to": r["to"].isoformat(),
                       "absence_requested_as": {"cop": "continuation of pay", "sick_leave": "sick leave", "annual_leave": "annual leave",
                                                "lwop": "leave without pay"}[r["code"]],
                       "hours_absent_per_day": r.get("hours")})
        for a, b in c["medical"]:
            med.append({"claim_id": cid, "totally_disabled_from": a.isoformat(), "totally_disabled_to": b.isoformat()})
        cop, last, nd, amt = sim(c, strict=False)
        cents = int(amt + Fraction(1, 2))
        row = {"cop_days": str(cop), "last_cop_day": last.isoformat() if last else "none", "compensation_days": str(nd),
               "compensation": f"{cents // 100}.{cents % 100:02d}"}
        sim_all[cid] = row
        tags_out[cid] = tags
        if planted_:
            golden[cid] = row
    ENV.mkdir(parents=True, exist_ok=True)
    for old in ENV.iterdir():
        old.unlink()
    dump = lambda name, o: (ENV / name).write_text(json.dumps(o, indent=1) + "\n")  # noqa: E731
    dump("employees.json", emps)
    dump("claims.json", injuries)
    dump("time_and_attendance.json", ta)
    dump("medical_evidence.json", med)
    dump("cost_of_living_adjustments.json", [{"effective": c.isoformat(), "percent": str(p)} for c, p in COLAS])
    if TST.exists():
        shutil.rmtree(TST)
    shutil.copytree(ENV, TST)
    (ROOT / "tests" / "case_tags.json").write_text(json.dumps(tags_out, indent=0, sort_keys=True) + "\n")
    (ROOT / "tests" / "golden.json").write_text(json.dumps(golden, indent=0, sort_keys=True) + "\n")
    (Path(__file__).resolve().parent / "sim_answers.json").write_text(json.dumps(sim_all, indent=0) + "\n")
    print(len(claims), "claims,", len(ta), "absence records,", len(med), "medical records,", len(golden), "planted,", rejected, "rejected")


if __name__ == "__main__":
    main()
