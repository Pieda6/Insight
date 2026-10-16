"""Verifier-side model of FECA continuation of pay and wage-loss compensation (5 U.S.C. 8110, 8114, 8117, 8118;
20 CFR 10.5(s), 10.205, 10.207, 10.215, 10.220, 10.401, 10.405, 10.420), written independently of the reference
solution: days are ordinal integers, absences and disability are sets, the 45 COP days are taken from a sorted list of
chargeable days, and pay loss is grouped into spells by gaps of scheduled workdays."""
import json
from datetime import date, datetime
from fractions import Fraction
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
WEEK = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
LAST = date(2026, 9, 30).toordinal()


def load(name):
    return json.loads((DATA / name).read_text())


def o(s):
    return date.fromisoformat(s).toordinal()


def months_on(n, k):
    d = date.fromordinal(n)
    t = d.year * 12 + d.month - 1 + k
    y, m = t // 12, t % 12 + 1
    for dd in (d.day, 30, 29, 28):
        try:
            return date(y, m, dd).toordinal()
        except ValueError:
            continue


def expected():
    emps = {e["employee_id"]: e for e in load("employees.json")}
    ta, med = {}, {}
    for r in load("time_and_attendance.json"):
        ta.setdefault(r["claim_id"], []).append(r)
    for m in load("medical_evidence.json"):
        med.setdefault(m["claim_id"], set()).update(range(o(m["totally_disabled_from"]), o(m["totally_disabled_to"]) + 1))
    colas = [(o(c["effective"]), Fraction(c["percent"])) for c in load("cost_of_living_adjustments.json")]
    out = {}
    for cl in load("claims.json"):
        cid = cl["claim_id"]
        e = emps[cl["employee_id"]]
        pt = e["work_schedule"] == "part-time"
        work = {i for i, w in enumerate(WEEK) if e["scheduled_hours"][w] > 0}
        is_work = lambda n: date.fromordinal(n).weekday() in work  # noqa: E731
        dis = med.get(cid, set())
        inj = datetime.fromisoformat(cl["injury_date_time"])
        inj_n = inj.date().toordinal()
        early = is_work(inj_n) and inj.time() < datetime.strptime(e["shift_start"], "%H:%M").time()
        absent = {}
        for r in ta.get(cid, []):
            for n in range(o(r["from"]), o(r["to"]) + 1):
                if pt or is_work(n):
                    absent[n] = (r["absence_requested_as"], r["hours_absent_per_day"])
        lost = sorted(n for n in absent if n > inj_n or (n == inj_n and early))
        start = lost[0]
        ok = (cl["claim_type"].startswith("traumatic") and o(cl["notice_filed_with_supervisor"]) - inj_n <= 30
              and start - inj_n <= 45)
        on_job = lambda n: is_work(n) and n > inj_n and n not in absent  # noqa: E731
        back = next((n for n in range(start, LAST + 1) if on_job(n)), None)

        def spell_begin(n):
            while n - 1 >= start and not on_job(n - 1):
                n -= 1
            while n not in absent:
                n += 1
            return n

        def chargeable(n):
            if not ok or n not in absent or absent[n][0] == "leave without pay":
                return False
            if pt and n not in dis and not absent[n][1]:
                return False
            return back is None or n < back or spell_begin(n) - back <= 45

        def neighbor(n, step):
            n += step
            while not is_work(n):
                n += step
            return n

        cop = []
        for n in range(inj_n if early else inj_n + 1, LAST + 1):
            if len(cop) == 45 or not ok:
                break
            if chargeable(n) or (not pt and not is_work(n) and n in dis and (chargeable(neighbor(n, -1)) or chargeable(neighbor(n, 1)))):
                cop.append(n)
        cop_set = set(cop)
        pay_loss = [n for n in sorted(absent) if not pt and n >= start and
                    (absent[n][0] == "leave without pay" or (absent[n][0] == "continuation of pay" and n not in cop_set))]
        spells = []
        for n in pay_loss:
            if spells and not any(is_work(k) for k in range(spells[-1][1] + 1, n)):
                spells[-1][1] = n
            else:
                spells.append([n, n])

        def pay_on(n):
            hist = [p for p in e["pay_history"] if o(p["effective"]) <= n]
            p = hist[-1]
            if e["pay_plan"] == "GS":
                return Fraction(p["annual_rate_of_basic_pay_cents"] * (100 + p["standby_duty_premium_percent_5545c1"]), 100)
            return Fraction(p["daily_wage_cents"] * {"5": 260, "5.5": 280, "6": 300}[e["workweek_days"]])

        def has_dependent(n):
            for dp in e["dependents"]:
                if dp["relationship"] == "spouse":
                    if o(dp["date_of_marriage"]) <= n:
                        return True
                    continue
                b = o(dp["date_of_birth"])
                if n < months_on(b, 18 * 12) or dp["incapable_of_self_support"]:
                    return True
                if n < months_on(b, 23 * 12) and any(o(s["from"]) <= n <= o(s["to"]) for s in dp["full_time_school_enrollment"]):
                    return True
            return False

        money, ndays = Fraction(0), 0
        for a, z in spells:
            length = z - a + 1
            rate, began = max(pay_on(inj_n), pay_on(start)), start
            sb = spell_begin(a)
            if back is not None and sb > back:
                last_full = max(n for n, v in absent.items() if n < sb and not v[1])
                resumed = next(n for n in range(last_full + 1, sb) if on_job(n))
                if sb > months_on(resumed, 6) and pay_on(sb) > rate:
                    rate, began = pay_on(sb), sb
            for n in range(a + (3 if length <= 14 else 0), z + 1):
                f = Fraction(1)
                for when, pct in colas:
                    if when <= n and began < months_on(when, -12):
                        f *= 1 + pct / 100
                money += rate * (Fraction(3, 4) if has_dependent(n) else Fraction(2, 3)) * f / 364
                ndays += 1
        cents = int(money + Fraction(1, 2))
        out[cid] = {"cop_days": str(len(cop)), "last_cop_day": date.fromordinal(max(cop)).isoformat() if cop else "none",
                    "compensation_days": str(ndays), "compensation": f"{cents // 100}.{cents % 100:02d}"}
    return out
