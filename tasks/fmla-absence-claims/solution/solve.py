#!/usr/bin/env python3
"""Reference solution: FMLA leave hours under 29 CFR 825.110, 825.120, 825.127, 825.200 and 825.205.

Walks each employee's absences one day at a time in date order, in minutes, and charges each day against the
employer's 12-month entitlement and, inside a military caregiver single 12-month period, the combined limit."""
import csv
import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

DATA = Path("/app/data")
OUT = Path("/app/output")
NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def j(name):
    return json.loads((DATA / name).read_text())


def d(s):
    return date.fromisoformat(s)


def year_later(x):
    return x.replace(year=x.year + 1)


def sunday(x):
    return x - timedelta(days=(x.weekday() + 1) % 7)


def employee(emp, absences, er):
    sched = {k: round(v * 60) for k, v in emp["weekly_schedule_hours"].items()}
    weekly = sum(sched.values())
    eligible = year_later(d(emp["hire_date"]))                             # 825.110(a)(1)
    holidays = {d(x) for x in er["holidays"]}
    closed = set()
    for c in er["business_closures"]:
        x = d(c["first_day"])
        while x <= d(c["last_day"]):
            closed.add(x)
            x += timedelta(days=1)
    leave_days = []
    continuous = set()
    for a in absences:
        if a["type"] == "continuous":
            x = d(a["start_date"])
            while x <= d(a["end_date"]):
                continuous.add(x)
                leave_days.append((x, a, None))
                x += timedelta(days=1)
        else:
            leave_days.append((d(a["start_date"]), a, round(a["hours_absent"] * 60)))
    leave_days.sort(key=lambda t: t[0])

    def full_week(x):                                                       # 825.200(h)
        ws = sunday(x)
        work = [ws + timedelta(days=k) for k in range(7) if NAMES[(ws + timedelta(days=k)).weekday()] in sched]
        return all(y in continuous for y in work) and not any(y in closed for y in work)

    result = defaultdict(int)
    ledger = []                                        # (date, minutes, caregiver)
    single = None
    period = None
    method = er["twelve_month_period_method"]
    for x, a, minutes in leave_days:
        day_sched = sched.get(NAMES[x.weekday()], 0)
        off = day_sched if minutes is None else minutes
        if x in holidays and not emp["scheduled_to_work_on_holidays"] and (minutes is not None or not full_week(x)):
            off = 0                                    # 825.200(h): a holiday counts only inside a full week of leave
        if x in closed or off == 0 or x < eligible:
            continue
        if a["reason"] == "bonding" and x >= year_later(d(a["child_birth_date"])):   # 825.120(a)(2)
            continue
        caregiver = a["reason"] == "military_caregiver"
        if caregiver and single is None:
            single = x                                                     # 825.127(e)(1)
        inside = single is not None and single <= x < year_later(single)
        combined_left = 26 * weekly - sum(m for y, m, c in ledger if inside and single <= y < year_later(single))
        if caregiver:
            room = combined_left
        else:
            if method == "calendar_year":
                window = lambda y: y.year == x.year  # noqa: E731
            elif method == "fixed_leave_year":
                mm, dd = (int(p) for p in er["leave_year_starts"].split("-"))
                ly = lambda y: y.year if (y.month, y.day) >= (mm, dd) else y.year - 1  # noqa: E731
                window = lambda y: ly(y) == ly(x)  # noqa: E731
            elif method == "rolling_backward":
                start = x.replace(year=x.year - 1)
                window = lambda y: start < y < x  # noqa: E731
            else:
                if period is None or x >= year_later(period):
                    period = x
                window = lambda y: period <= y < year_later(period)  # noqa: E731
            room = 12 * weekly - sum(m for y, m, c in ledger if not c and window(y))
            if inside:
                room = min(room, combined_left)
        take = max(0, min(off, room))
        if take:
            ledger.append((x, take, caregiver))
            result[a["absence_id"]] += take
    return result


def main():
    employers = {e["employer_id"]: e for e in j("employers.json")}
    by_emp = defaultdict(list)
    absences = j("absences.json")
    for a in absences:
        by_emp[a["employee_id"]].append(a)
    total = {}
    for emp in j("employees.json"):
        total.update(employee(emp, by_emp[emp["employee_id"]], employers[emp["employer_id"]]))
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "fmla_hours.csv", "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["absence_id", "fmla_hours"])
        for a in absences:
            m = total.get(a["absence_id"], 0)
            w.writerow([a["absence_id"], f"{m // 60}.{(m % 60) * 100 // 60:02d}"])


if __name__ == "__main__":
    main()
