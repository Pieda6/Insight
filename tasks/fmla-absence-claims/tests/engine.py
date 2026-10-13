"""Verifier-side model of FMLA leave accounting (29 CFR 825.110, 825.120, 825.127, 825.200, 825.205), written
independently of the reference solution: hours are exact fractions, each employee's leave is first expanded into
chargeable slots per workweek, and entitlements are read from running ledgers by window predicates."""
import json
from collections import defaultdict
from datetime import date, timedelta
from fractions import Fraction
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
WEEKDAY = {"Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3, "Friday": 4, "Saturday": 5, "Sunday": 6}


def load(name):
    return json.loads((DATA / name).read_text())


def iso(s):
    return date.fromisoformat(s)


def anniversary(x):
    return date(x.year + 1, x.month, x.day)


def span(a, b):
    return [a + timedelta(days=k) for k in range((b - a).days + 1)]


class Employer:
    def __init__(self, rec):
        self.method = rec["twelve_month_period_method"]
        self.year_start = tuple(int(p) for p in rec["leave_year_starts"].split("-")) if rec["leave_year_starts"] else None
        self.holidays = {iso(h) for h in rec["holidays"]}
        self.closed = {x for c in rec["business_closures"] for x in span(iso(c["first_day"]), iso(c["last_day"]))}

    def same_period(self, a, b, anchor):
        if self.method == "calendar_year":
            return a.year == b.year
        if self.method == "fixed_leave_year":
            key = lambda x: x.year - (0 if (x.month, x.day) >= self.year_start else 1)  # noqa: E731
            return key(a) == key(b)
        if self.method == "rolling_backward":                  # the 12 months before the day of leave
            return b.replace(year=b.year - 1) < a < b
        return anchor <= a < anniversary(anchor)               # forward from the first leave of the period


def slots(emp, absences, er):
    """(day, hours off, absence) for every day an absence could be charged, in date order."""
    hours = {WEEKDAY[k]: Fraction(str(v)) for k, v in emp["weekly_schedule_hours"].items()}
    cont = {}
    for a in absences:
        if a["type"] == "continuous":
            for x in span(iso(a["start_date"]), iso(a["end_date"])):
                cont[x] = a
    weeks_full = set()
    for x in cont:
        start = x - timedelta(days=(x.weekday() + 1) % 7)
        workdays = [y for y in span(start, start + timedelta(days=6)) if y.weekday() in hours]
        if all(y in cont and y not in er.closed for y in workdays):
            weeks_full.add(start)
    out = []
    for x, a in cont.items():
        h = hours.get(x.weekday(), Fraction(0))
        start = x - timedelta(days=(x.weekday() + 1) % 7)
        if x in er.holidays and start not in weeks_full and not emp["scheduled_to_work_on_holidays"]:
            h = Fraction(0)
        out.append((x, h, a))
    for a in absences:
        if a["type"] == "intermittent":
            out.append((iso(a["start_date"]), Fraction(str(a["hours_absent"])), a))
    return sorted(out, key=lambda t: t[0])


def account(emp, absences, er):
    weekly = sum(Fraction(str(v)) for v in emp["weekly_schedule_hours"].values())
    eligible_from = anniversary(iso(emp["hire_date"]))
    charged = defaultdict(Fraction)
    other_ledger, all_ledger = [], []
    caregiver_start, anchor = None, None
    for day, h, a in slots(emp, absences, er):
        if h == 0 or day in er.closed or day < eligible_from:
            continue
        if a["reason"] == "bonding" and day >= anniversary(iso(a["child_birth_date"])):
            continue
        is_care = a["reason"] == "military_caregiver"
        if is_care and caregiver_start is None:
            caregiver_start = day
        in_single = caregiver_start is not None and caregiver_start <= day < anniversary(caregiver_start)
        combined = 26 * weekly - sum((m for y, m in all_ledger
                                      if caregiver_start and caregiver_start <= y < anniversary(caregiver_start)),
                                     Fraction(0))
        if is_care:
            limit = combined
        else:
            if er.method == "forward_from_first_leave" and (anchor is None or day >= anniversary(anchor)):
                anchor = day
            limit = 12 * weekly - sum((m for y, m in other_ledger if er.same_period(y, day, anchor)), Fraction(0))
            if in_single:
                limit = min(limit, combined)
        take = max(Fraction(0), min(h, limit))
        if take:
            all_ledger.append((day, take))
            if not is_care:
                other_ledger.append((day, take))
            charged[a["absence_id"]] += take
    return charged


def expected():
    employers = {e["employer_id"]: Employer(e) for e in load("employers.json")}
    absences = load("absences.json")
    by_emp = defaultdict(list)
    for a in absences:
        by_emp[a["employee_id"]].append(a)
    charged = {}
    for emp in load("employees.json"):
        charged.update(account(emp, by_emp[emp["employee_id"]], employers[emp["employer_id"]]))
    return {a["absence_id"]: {"fmla_hours": f"{float(charged.get(a['absence_id'], 0)):.2f}"} for a in absences}
