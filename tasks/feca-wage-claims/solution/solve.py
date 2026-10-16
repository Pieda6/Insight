#!/usr/bin/env python3
"""Reference solution for feca-wage-claims (5 U.S.C. 8105, 8110, 8114, 8117, 8118; 20 CFR 10.5, 10.200-10.224,
10.400-10.425).

Per claim: decide COP eligibility (traumatic injury, notice within 30 days, time lost within 45 days), walk the days
from the first lost time charging days to COP (10.215: the injury day only if injured before the shift, any part of a
day as a full day, leave as if COP, regular days off next to charged workdays when medically disabled, every
disabled calendar day for part-time workers; 10.207 for returns) up to 45; then pay wage-loss compensation for days of
pay loss (8117 waiting period, 8114 pay rate with the 10.5(s) choice, 8110 augmentation, 8146a cost-of-living
adjustments under 10.420)."""
import csv
import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from fractions import Fraction
from pathlib import Path

DATA = Path("/app/data")
OUT = Path("/app/output")
END = date(2026, 9, 30)
ONE = timedelta(days=1)
NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def day(s):
    return date.fromisoformat(s)


def shift_months(d, n):
    k = d.year * 12 + d.month - 1 + n
    y, m = divmod(k, 12)
    m += 1
    last = (date(y + (m == 12), m % 12 + 1, 1) - ONE).day
    return date(y, m, min(d.day, last))


def load(name):
    return json.loads((DATA / name).read_text())


def main():
    employees = {e["employee_id"]: e for e in load("employees.json")}
    absences = defaultdict(list)
    for r in load("time_and_attendance.json"):
        absences[r["claim_id"]].append(r)
    medical = defaultdict(list)
    for m in load("medical_evidence.json"):
        medical[m["claim_id"]].append((day(m["totally_disabled_from"]), day(m["totally_disabled_to"])))
    colas = [(day(c["effective"]), Fraction(c["percent"])) for c in load("cost_of_living_adjustments.json")]

    rows = []
    for claim in load("claims.json"):
        emp = employees[claim["employee_id"]]
        hurt = datetime.strptime(claim["injury_date_time"], "%Y-%m-%dT%H:%M")
        hurt_day = hurt.date()
        part_time = emp["work_schedule"] == "part-time"
        scheduled = {i for i, n in enumerate(NAMES) if emp["scheduled_hours"][n]}
        is_work = lambda d: d.weekday() in scheduled  # noqa: E731
        sick = medical[claim["claim_id"]]
        is_disabled = lambda d: any(a <= d <= b for a, b in sick)  # noqa: E731

        status = {}                                   # date -> absence record (scheduled workdays; all days part-time)
        for r in absences[claim["claim_id"]]:
            d = day(r["from"])
            while d <= day(r["to"]):
                if part_time or is_work(d):
                    status[d] = r
                d += ONE
        before_shift = is_work(hurt_day) and hurt.strftime("%H:%M") < emp["shift_start"]
        first = min(d for d in status if d > hurt_day or (d == hurt_day and before_shift))
        traumatic = claim["claim_type"].startswith("traumatic")
        eligible = (traumatic and day(claim["notice_filed_with_supervisor"]) <= hurt_day + timedelta(days=30)
                    and first <= hurt_day + timedelta(days=45))

        def worked(d):
            return is_work(d) and d > hurt_day and d not in status

        first_back = next((d for d in (first + ONE * k for k in range((END - first).days + 1)) if worked(d)), None)

        def stop_date(d):                             # first day of the absence spell containing d
            while d - ONE >= first and not worked(d - ONE):
                d -= ONE
            while d not in status:
                d += ONE
            return d

        def chargeable_workday(d):
            r = status.get(d)
            if not eligible or r is None or r["absence_requested_as"] == "leave without pay":
                return False
            if part_time and not (is_disabled(d) or r["hours_absent_per_day"]):
                return False
            if first_back is None or d < first_back:
                return True
            return stop_date(d) <= first_back + timedelta(days=45)     # 10.207(c)

        charged = []
        d = hurt_day if before_shift else hurt_day + ONE      # the first day disability begins (10.215(b))
        while eligible and d <= END and len(charged) < 45:
            if chargeable_workday(d):
                charged.append(d)
            elif not part_time and not is_work(d) and is_disabled(d):
                p = d - ONE
                while not is_work(p):
                    p -= ONE
                n = d + ONE
                while not is_work(n):
                    n += ONE
                if chargeable_workday(p) or chargeable_workday(n):              # 10.215(d)
                    charged.append(d)
            d += ONE
        charged_set = set(charged)

        # pay loss: leave without pay, and COP requested where COP is not payable
        loss = sorted(d for d, r in status.items() if not part_time and d >= first and
                      (r["absence_requested_as"] == "leave without pay" or
                       (r["absence_requested_as"] == "continuation of pay" and d not in charged_set)))
        spells = []
        for d in loss:
            if spells and all(not is_work(x) for x in (spells[-1][-1] + ONE * k for k in range(1, (d - spells[-1][-1]).days))):
                spells[-1] += [spells[-1][-1] + ONE * k for k in range(1, (d - spells[-1][-1]).days + 1)]
            else:
                spells.append([d])

        def annual(on):
            pay = [p for p in emp["pay_history"] if day(p["effective"]) <= on][-1]
            if emp["pay_plan"] == "GS":
                return Fraction(pay["annual_rate_of_basic_pay_cents"]) * (100 + pay["standby_duty_premium_percent_5545c1"]) / 100
            return Fraction(pay["daily_wage_cents"]) * {"5": 260, "5.5": 280, "6": 300}[emp["workweek_days"]]

        def dependent(on):
            for dp in emp["dependents"]:
                if dp["relationship"] == "spouse" and day(dp["date_of_marriage"]) <= on:
                    return True
                if dp["relationship"] == "child":
                    born = day(dp["date_of_birth"])
                    if on < shift_months(born, 216) or dp["incapable_of_self_support"]:
                        return True
                    if on < shift_months(born, 276) and any(day(s["from"]) <= on <= day(s["to"]) for s in dp["full_time_school_enrollment"]):
                        return True
            return False

        total, paid_days = Fraction(0), 0
        for i, spell in enumerate(spells):
            waiting = 3 if len(spell) <= 14 else 0    # 8117(a), 10.401(a)
            rate, since = max(annual(hurt_day), annual(first)), first
            start = stop_date(spell[0])
            if first_back and start > first_back:     # recurrence: 10.5(s)
                gone = max(x for x in status if x < start and not status[x]["hours_absent_per_day"])
                back = gone + ONE
                while not worked(back):
                    back += ONE
                if start > shift_months(back, 6) and annual(start) > rate:
                    rate, since = annual(start), start
            for d in spell[waiting:]:
                factor = Fraction(1)
                for when, pct in colas:               # 10.420
                    if when <= d and since < shift_months(when, -12):
                        factor *= 1 + pct / 100
                share = Fraction(3, 4) if dependent(d) else Fraction(2, 3)
                total += rate / 52 * share * factor / 7
                paid_days += 1
        cents = int(total + Fraction(1, 2))
        rows.append([claim["claim_id"], len(charged), max(charged).isoformat() if charged else "none", paid_days,
                     f"{cents // 100}.{cents % 100:02d}"])

    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "claim_determinations.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["claim_id", "cop_days", "last_cop_day", "compensation_days", "compensation"])
        w.writerows(rows)


if __name__ == "__main__":
    main()
