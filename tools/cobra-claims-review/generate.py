#!/usr/bin/env python3
"""Generate the cobra-claims-review inputs (dev only, never shipped).

A benefits administrator adjudicates medical claims from COBRA qualified beneficiaries of one group health plan.
Each claim is payable only if the person had COBRA continuation coverage on the date of service, which depends on:
the qualifying event and its maximum coverage period (18 or 36 months), the disability extension (29 months;
disabled within the first 60 days, notice within 60 days of the determination and before the 18 months end, 150%
premium for the disabled person in months 19-29), second qualifying events for spouses and children (36 months from
the start, notice within 60 days, also inside the disability extension), the special period for dependents when the
employee had Medicare before a termination, the election period (60 days after the later of loss of coverage and
the notice, retroactive), premiums (102%, 30-day grace period, 45 days after the election for the first payment,
shortfalls up to the lesser of $50 or 10% treated as full payment unless a shortfall notice gives 30 days to cure,
no reinstatement), and early termination for other group coverage or Medicare that begins after the election.
26 CFR 54.4980B-1 through -10. Planted families carry hand-worked answers; `sim` is the third implementation and
rejects (strict) any filler family that would need an open reading.
"""
import calendar
import json
import random
import shutil
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "tasks" / "cobra-claims-review"
ENV, TST = ROOT / "environment" / "data", ROOT / "tests" / "data"
rng = random.Random(49800)
DAY = timedelta(days=1)
PREMIUM = {"PPO": {2022: 55870, 2023: 58310, 2024: 61240, 2025: 64815, 2026: 68930},
           "HDHP": {2022: 37640, 2023: 39525, 2024: 41380, 2025: 42110, 2026: 44695}}
# benefit design: deductible, coinsurance percent, out-of-pocket maximum (self-only, per calendar year)
BENEFIT = {"PPO": {2021: (50000, 20, 400000), 2022: (50000, 20, 400000), 2023: (50000, 20, 400000),
                   2024: (75000, 20, 450000), 2025: (75000, 20, 500000), 2026: (100000, 20, 550000)},
           "HDHP": {2021: (150000, 10, 650000), 2022: (150000, 10, 650000), 2023: (160000, 10, 700000),
                    2024: (165000, 10, 750000), 2025: (170000, 10, 800000), 2026: (175000, 10, 830000)}}
LAST = date(2026, 9, 30)           # last date of service in the queue
ASOF = date(2026, 10, 15)          # the files are complete as of this date
LATEST_EVENT = ASOF - timedelta(days=60)


def D(s):
    return date.fromisoformat(s) if isinstance(s, str) else s


def days(n):
    return timedelta(days=n)


def add_months(d, n):
    k = d.year * 12 + d.month - 1 + n
    y, m = k // 12, k % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def month_start(d):
    return d.replace(day=1)


def next_month(d):
    return add_months(month_start(d), 1)


def due(option, month, rate):
    return (PREMIUM[option][month.year] * rate + 50) // 100     # rate in percent, nearest cent


class Reject(Exception):
    pass


def qualified(first, people):
    """People who lose coverage because of the first qualifying event."""
    t = first["type"]
    if t in ("termination", "reduction_of_hours"):
        return list(people)
    if t == "death":
        return [p for p in people if people[p]["role"] != "employee"]
    if t == "divorce":
        return [p for p in people if people[p]["role"] == "spouse"]
    return [first["person"]]


SECOND = {"spouse": ("death", "divorce"), "child": ("death", "child_reaches_26")}


def sim(fam, strict=True):
    """Third implementation: {person: (first day, last day) of COBRA coverage, or None}; fam["info"] for filler."""
    first = fam["events"][0]
    qe_day = D(first.get("fmla_last") or first["date"])   # 54.4980B-10: the last day of FMLA leave
    S = next_month(qe_day)                            # coverage lost at the end of the month; COBRA starts next day
    people = fam["people"]
    affected = qualified(first, people)
    base = 18 if first["type"] in ("termination", "reduction_of_hours") else 36
    end18 = add_months(S, 18) - DAY

    def election_ok(q):
        if not q.get("elected"):
            return False
        el, nt = D(q["elected"]), D(q["notice"])
        if strict and max(S - DAY, nt) + days(60) < el <= max(S, nt) + days(60):
            raise Reject("election on the day that depends on the loss-of-coverage date")
        return el <= max(S, nt) + days(60)

    disabled = []
    if base == 18:
        for p in affected:
            s = people[p].get("ssa")
            if not s:
                continue
            on, det, nt = D(s["onset"]), D(s["determination"]), D(s["notice"])
            if strict and (on == S + days(60) or det < S or not election_ok(people[p]) or people[p].get("waived")):
                raise Reject("open disability reading")
            if on <= S + days(59) and nt <= det + days(60) and nt <= end18:
                disabled.append(p)
    ext29 = bool(disabled)
    out = {}
    for p in affected:
        q = people[p]
        if not election_ok(q):
            out[p] = None
            continue
        el = D(q["elected"])
        begin = S
        if q.get("waived"):                           # 54.4980B-6 Q/A-4: a revoked waiver is not retroactive
            assert D(q["waived"]) < el
            begin = el
        end = add_months(S, 29 if ext29 else base) - DAY
        if base == 18 and q["role"] != "employee":
            period_end = end
            for x in fam["events"][1:]:
                if x["type"] not in SECOND[q["role"]] or (x["type"] == "child_reaches_26" and x.get("person") != p):
                    continue
                if not S <= D(x["date"]) <= period_end:
                    continue
                if x["type"] == "child_reaches_26" and q.get("incapable"):
                    continue                          # still eligible under the plan: not a qualifying event
                if strict and p in disabled:
                    raise Reject("second event for a disabled beneficiary (150% through month 36?)")
                n = q.get("second_notice")
                if strict and n and D(x["date"]) + days(60) < D(n) <= next_month(D(x["date"])) + days(60):
                    raise Reject("second-event notice inside the window that depends on the start date")
                if n and D(n) <= D(x["date"]) + days(60):
                    end = max(end, add_months(S, 36) - DAY)
            med = people[fam["employee"]].get("medicare")
            if med and D(med) < qe_day:
                if strict and p in disabled:
                    raise Reject("disabled beneficiary with the Medicare-before period")
                end = max(end, add_months(D(med), 36) - DAY)
        last = end
        for key in ("other_coverage", "medicare"):
            v = q.get(key)
            if v and strict and D(v) == el:
                raise Reject("coverage begins on the election day")
            if v and D(v) > el:
                last = min(last, D(v) - DAY)
        m, paid_through = month_start(begin), None
        while m <= last and m <= LAST:
            rate = 150 if p in disabled and add_months(S, 18) <= m < add_months(S, 29) else 102
            amt = due(q["option"], m, rate)
            pay = q["payments"].get(m)
            ok = False
            if pay:
                short = amt - pay["amount"]
                if strict and short * 10 == amt:
                    raise Reject("shortfall of exactly 10 percent")
                if D(pay["paid_on"]) <= max(m + days(30), el + days(45)):
                    if short <= 0:
                        ok = True
                    elif short <= 5000 and short * 10 <= amt:
                        ok = True
                        if pay.get("shortfall_notice"):
                            cure = pay.get("deficiency_paid_on")
                            ok = bool(cure) and D(cure) <= D(pay["shortfall_notice"]) + days(30)
            if not ok:
                break
            paid_through = add_months(m, 1) - DAY
            m = add_months(m, 1)
        if paid_through is None:
            out[p] = None
        elif m <= last and m <= LAST:
            out[p] = (begin, paid_through)
        else:
            out[p] = (begin, last)
    fam["info"] = {"S": S, "end18": end18, "ext29": ext29, "disabled": disabled,
                   "end29": add_months(S, 29) - DAY}
    return out


def ledger(items, option, S, carry_ded=True, carry_oop=True):
    """Plan payment in cents for each (date, allowed, covered), in date order. Deductible and out-of-pocket
    maximum per person per calendar year; with carry_* False, amounts before COBRA (date < S) are kept apart."""
    acc, out = {}, []
    for d, allowed, cov in items:
        if not cov:
            out.append(0)
            continue
        ded, pct, oop = BENEFIT[option][d.year]
        kd = (d.year, True if carry_ded else d < S)
        ko = (d.year, True if carry_oop else d < S)
        used_d, used_o = acc.get(("d",) + kd, 0), acc.get(("o",) + ko, 0)
        d_part = min(allowed, ded - used_d)
        coins = ((allowed - d_part) * pct + 50) // 100
        share = min(d_part + coins, oop - used_o)
        assert share >= d_part
        acc[("d",) + kd] = used_d + d_part
        acc[("o",) + ko] = used_o + share
        out.append(allowed - share)
    return out


def claim_amount():
    r = rng.random()
    if r < 0.55:
        return rng.randint(6000, 60000)
    if r < 0.9:
        return rng.randint(60000, 600000)
    return rng.randint(1200000, 6000000)


def covered(ranges, person, d):
    r = ranges.get(person)
    return bool(r) and r[0] <= D(d) <= r[1]


class World:
    def __init__(self):
        self.fams = []

    def add(self, fam, tags, expected):
        fam["tags"], fam["expected"] = tags, expected
        self.fams.append(fam)


def pays(option, start, end, day=5, override=None, disabled_months=None):
    """Full payments for every month from start to end (first days), sent on `day` of the month."""
    out, m = {}, D(start)
    while m <= D(end):
        r = 150 if disabled_months and m in disabled_months else 102
        out[m] = {"amount": due(option, m, r), "paid_on": m.replace(day=day)}
        m = add_months(m, 1)
    for k, v in (override or {}).items():
        if v is None:
            out.pop(D(k), None)
        else:
            out[D(k)] = v
    return out


def P(role, born, option="PPO", elected=None, notice=None, payments=None, **kw):
    q = dict(role=role, born=D(born), option=option, elected=elected and D(elected), notice=notice and D(notice),
             payments=payments or {}, **kw)
    for pay in q["payments"].values():          # nothing is paid before the election
        if q["elected"] and D(pay["paid_on"]) < q["elected"]:
            pay["paid_on"] = q["elected"] + days(3)
    return q


def fam_(employee, people, events):
    return {"employee": employee, "people": people, "events": [dict(e, date=D(e["date"])) for e in events]}


def planted(w):
    T = {"type": "termination", "date": "2024-03-15"}
    S, E18, END = "2024-04-01", "2025-09-01", "2026-09-01"
    EL, NT = "2024-04-20", "2024-04-05"
    # 18 months from Apr 1 2024: coverage through Sep 30 2025. Elected Apr 20 (notice Apr 5); April and May paid
    # Jun 1 (within 45 days of the election). Apr 3 2024 is before the election but the election is retroactive.
    w.add(fam_("e", {"e": P("employee", "1970-02-11", elected=EL, notice=NT,
                            payments=pays("PPO", S, END, override={"2024-04-01": {"amount": 62465, "paid_on": D("2024-06-01")},
                                                                   "2024-05-01": {"amount": 62465, "paid_on": D("2024-06-01")}}))},
               [T]), ["maximum-period", "election"],
          [("e", "2024-04-03", True), ("e", "2025-09-30", True), ("e", "2025-10-01", False)])
    # election 61 days after the notice (Apr 5 + 60 = Jun 4; elected Jun 5): no COBRA at all
    w.add(fam_("e", {"e": P("employee", "1970-02-11", elected="2024-06-05", notice=NT,
                            payments=pays("PPO", S, E18, day=10))}, [T]), ["election", "boundary"],
          [("e", "2024-05-10", False), ("e", "2024-08-10", False)])
    # elected on day 60 (Jun 4): covered
    w.add(fam_("e", {"e": P("employee", "1970-02-11", elected="2024-06-04", notice=NT,
                            payments=pays("PPO", S, E18, day=10))}, [T]), ["election", "boundary"],
          [("e", "2024-05-10", True), ("e", "2025-08-10", True)])
    # 30-day grace: January 2025 sent Jan 31 (Jan 1 + 30) is timely; February sent Mar 4 (Feb 1 + 30 = Mar 3) is
    # not: coverage ends Jan 31 2025 and the later months paid on time do not bring it back
    w.add(fam_("e", {"e": P("employee", "1970-02-11", elected=EL, notice=NT,
                            payments=pays("PPO", S, E18, override={"2025-01-01": {"amount": 66111, "paid_on": D("2025-01-31")},
                                                                   "2025-02-01": {"amount": 66111, "paid_on": D("2025-03-04")}}))},
               [T]), ["premiums", "grace", "boundary"],
          [("e", "2025-01-20", True), ("e", "2025-02-10", False), ("e", "2025-06-10", False)])
    # a month never paid: March 2025 missing, coverage ends Feb 28 2025
    w.add(fam_("e", {"e": P("employee", "1970-02-11", "HDHP", elected=EL, notice=NT,
                            payments=pays("HDHP", S, E18, override={"2025-03-01": None}))},
               [T]), ["premiums", "grace"], [("e", "2025-02-28", True), ("e", "2025-04-02", False)])
    # first payment: elected May 20 2024, so April-June may be sent by Jul 4; sent Jul 4: covered. Another family
    # sending it Jul 5 never had coverage
    for paid, ok in (("2024-07-04", True), ("2024-07-05", False)):
        w.add(fam_("e", {"e": P("employee", "1970-02-11", elected="2024-05-20", notice=NT,
                                payments=pays("PPO", S, E18, override={m: {"amount": 62465, "paid_on": D(paid)}
                                                                       for m in ("2024-04-01", "2024-05-01", "2024-06-01")}))},
                   [T]), ["premiums", "initial-payment", "boundary"], [("e", "2024-04-15", ok), ("e", "2024-12-15", ok)])
    # shortfall: HDHP 2025 premium 421.10, COBRA 429.52; 10% is 42.952, under $50. Short by 42.95 in March 2025:
    # treated as full; short by 42.96: not, coverage ends Feb 28 2025
    for short, ok in ((4295, True), (4296, False)):
        w.add(fam_("e", {"e": P("employee", "1970-02-11", "HDHP", elected=EL, notice=NT,
                                payments=pays("HDHP", S, E18, override={"2025-03-01": {"amount": 42952 - short,
                                                                                       "paid_on": D("2025-03-05")}}))},
                   [T]), ["premiums", "shortfall", "boundary"],
              [("e", "2025-03-20", ok), ("e", "2025-07-20", ok), ("e", "2025-02-20", True)])
    # PPO 2025 COBRA premium 661.11: $50 is less than 10% (66.11). Short by 50.00: full; by 50.01: not
    for short, ok in ((5000, True), (5001, False)):
        w.add(fam_("e", {"e": P("employee", "1970-02-11", elected=EL, notice=NT,
                                payments=pays("PPO", S, E18, override={"2025-03-01": {"amount": 66111 - short,
                                                                                      "paid_on": D("2025-03-05")}}))},
                   [T]), ["premiums", "shortfall", "boundary"], [("e", "2025-03-20", ok)])
    # shortfall notice: short by $30 in March 2025, notice Mar 10 gives 30 days: cured Apr 9 (after the grace
    # period, still covered) or Apr 10 (not)
    for cure, ok in (("2025-04-09", True), ("2025-04-10", False)):
        w.add(fam_("e", {"e": P("employee", "1970-02-11", elected=EL, notice=NT,
                                payments=pays("PPO", S, E18, override={"2025-03-01": {
                                    "amount": 66111 - 3000, "paid_on": D("2025-03-05"), "shortfall_notice": D("2025-03-10"),
                                    "deficiency_paid_on": D(cure)}}))}, [T]),
              ["premiums", "shortfall"], [("e", "2025-03-20", ok), ("e", "2025-02-20", True)])
    # disability extension: the spouse is found disabled from May 30 2024 (day 60 of COBRA coverage from Apr 1),
    # determination Oct 1 2024, notice Nov 29 (within 60 days): 29 months for the whole family, to Aug 31 2026.
    # The spouse pays 150% in months 19-29 (Oct 2025 - Aug 2026), the employee and child 102%
    ext = {add_months(D("2025-10-01"), k) for k in range(11)}
    w.add(fam_("e", {"e": P("employee", "1968-07-02", elected=EL, notice=NT, payments=pays("PPO", S, END)),
                     "s": P("spouse", "1969-01-09", elected=EL, notice=NT,
                            payments=pays("PPO", S, END, disabled_months=ext),
                            ssa={"onset": "2024-05-30", "determination": "2024-10-01", "notice": "2024-11-29"}),
                     "c": P("child", "2006-03-03", elected=EL, notice=NT, payments=pays("PPO", S, END))}, [T]),
          ["disability-extension"], [("e", "2026-08-15", True), ("e", "2026-09-01", False), ("s", "2026-08-31", True),
                                     ("c", "2026-02-10", True)])
    # onset Jun 1 2024 is after the first 60 days: no extension, 18 months only
    w.add(fam_("e", {"e": P("employee", "1968-07-02", elected=EL, notice=NT, payments=pays("PPO", S, END)),
                     "s": P("spouse", "1969-01-09", elected=EL, notice=NT,
                            payments=pays("PPO", S, END, disabled_months=ext),
                            ssa={"onset": "2024-06-01", "determination": "2024-10-01", "notice": "2024-11-29"})}, [T]),
          ["disability-extension", "boundary"], [("e", "2025-10-15", False), ("s", "2025-10-15", False),
                                                 ("e", "2025-09-15", True)])
    # notice 61 days after the determination (Dec 1): no extension
    w.add(fam_("e", {"e": P("employee", "1968-07-02", elected=EL, notice=NT, payments=pays("PPO", S, END)),
                     "s": P("spouse", "1969-01-09", elected=EL, notice=NT,
                            payments=pays("PPO", S, END, disabled_months=ext),
                            ssa={"onset": "2024-05-10", "determination": "2024-10-01", "notice": "2024-12-01"})}, [T]),
          ["disability-extension", "boundary"], [("e", "2025-12-15", False), ("s", "2025-12-15", False)])
    # disabled since before the termination (Feb 2024), determination Mar 2 2025, notice Apr 25 2025: extension.
    # The disabled spouse keeps paying 102% in month 19 (October 2025): far short of 150%, coverage ends Sep 30
    # 2025 for her
    w.add(fam_("e", {"s": P("spouse", "1969-01-09", elected=EL, notice=NT, payments=pays("PPO", S, END),
                            ssa={"onset": "2024-02-10", "determination": "2025-03-02", "notice": "2025-04-25"}),
                     "e": P("employee", "1968-07-02", elected=EL, notice=NT, payments=pays("PPO", S, "2025-12-01"))},
               [T]), ["disability-extension", "premiums"], [("s", "2025-09-30", True), ("s", "2025-10-01", False),
                                                            ("e", "2025-09-30", True)])
    # disabled since Nov 2023, before the termination, and paying 150% from month 19: extension to Aug 31 2026
    w.add(fam_("e", {"e": P("employee", "1962-08-08", "HDHP", elected=EL, notice=NT, payments=pays("HDHP", S, END)),
                     "s": P("spouse", "1963-06-06", elected=EL, notice=NT,
                            payments=pays("PPO", S, END, disabled_months=ext),
                            ssa={"onset": "2023-11-01", "determination": "2024-08-01", "notice": "2024-08-20"})}, [T]),
          ["disability-extension"], [("s", "2026-03-15", True), ("e", "2026-03-15", True)])
    # the disability extension makes a later second event count: the child turns 26 on Mar 10 2026 (month 24,
    # inside the 29 months) and notifies Apr 2 2026, so the child gets 36 months, to Mar 31 2027. The employee
    # stops at Aug 31 2026. Without the disability (next family) the birthday is after the 18 months: no extension
    w.add(fam_("e", {"e": P("employee", "1965-05-05", elected=EL, notice=NT, payments=pays("PPO", S, END)),
                     "s": P("spouse", "1966-09-21", elected=EL, notice=NT,
                            payments=pays("PPO", S, END, disabled_months=ext),
                            ssa={"onset": "2024-04-20", "determination": "2024-09-03", "notice": "2024-09-30"}),
                     "c": P("child", "2000-03-10", elected=EL, notice=NT, payments=pays("PPO", S, END),
                            second_notice="2026-04-02")},
               [T, {"type": "child_reaches_26", "date": "2026-03-10", "person": "c"}]),
          ["disability-extension", "second-event"],
          [("c", "2026-09-15", True), ("e", "2026-09-15", False), ("s", "2026-09-15", False), ("s", "2026-08-15", True)])
    w.add(fam_("e", {"e": P("employee", "1965-05-05", elected=EL, notice=NT, payments=pays("PPO", S, END)),
                     "c": P("child", "2000-03-10", elected=EL, notice=NT, payments=pays("PPO", S, END),
                            second_notice="2026-04-02")},
               [T, {"type": "child_reaches_26", "date": "2026-03-10", "person": "c"}]),
          ["second-event"], [("c", "2025-09-30", True), ("c", "2026-04-15", False)])
    # second qualifying event: divorce Nov 20 2024, spouse notifies Jan 15 2025 (within 60 days): spouse 36 months,
    # to Mar 31 2027; the employee keeps 18. Notified Feb 3 2025: too late, 18 months
    for note, ok in (("2025-01-15", True), ("2025-02-03", False)):
        w.add(fam_("e", {"e": P("employee", "1971-05-05", elected=EL, notice=NT, payments=pays("PPO", S, END)),
                         "s": P("spouse", "1972-08-08", elected=EL, notice=NT, payments=pays("PPO", S, END),
                                second_notice=note)},
                   [T, {"type": "divorce", "date": "2024-11-20"}]), ["second-event", "boundary"],
              [("s", "2026-06-01", ok), ("e", "2026-06-01", False), ("s", "2025-09-30", True)])
    # the employee dies Jun 12 2025 (month 15): spouse and child notify Jun 30: both get 36 months
    w.add(fam_("e", {"e": P("employee", "1969-12-01", elected=EL, notice=NT, payments=pays("PPO", S, "2025-06-01")),
                     "s": P("spouse", "1970-02-02", "HDHP", elected=EL, notice=NT, payments=pays("HDHP", S, END),
                            second_notice="2025-06-30"),
                     "c": P("child", "2004-10-10", elected=EL, notice=NT, payments=pays("PPO", S, END),
                            second_notice="2025-06-30")},
               [T, {"type": "death", "date": "2025-06-12"}]), ["second-event"],
          [("s", "2026-09-10", True), ("c", "2026-07-10", True)])
    # a termination after a reduction of hours is not a second qualifying event: 18 months from Apr 1 2024
    w.add(fam_("e", {"e": P("employee", "1971-03-03", elected=EL, notice=NT, payments=pays("PPO", S, END)),
                     "s": P("spouse", "1972-04-04", elected=EL, notice=NT, payments=pays("PPO", S, END),
                            second_notice="2024-09-20")},
               [{"type": "reduction_of_hours", "date": "2024-03-15"}, {"type": "termination", "date": "2024-08-30"}]),
          ["second-event", "maximum-period"], [("s", "2025-09-30", True), ("s", "2025-10-30", False)])
    # the employee's Medicare entitlement (Jan 1 2025) is not a second qualifying event under this plan, and it ends
    # the employee's own COBRA (elected earlier) on Dec 31 2024; the spouse keeps the 18 months
    w.add(fam_("e", {"e": P("employee", "1960-01-03", elected=EL, notice=NT, payments=pays("PPO", S, END),
                            medicare="2025-01-01"),
                     "s": P("spouse", "1961-02-14", elected=EL, notice=NT, payments=pays("PPO", S, END),
                            second_notice="2025-01-20")},
               [T, {"type": "employee_medicare_entitlement", "date": "2025-01-01"}]), ["second-event", "medicare"],
          [("e", "2024-12-31", True), ("e", "2025-01-02", False), ("s", "2025-09-30", True), ("s", "2025-10-01", False)])
    # Medicare before the qualifying event: Medicare from Jan 1 2024, termination Sep 10 2024 (COBRA from Oct 1, 18
    # months to Mar 31 2026); the spouse gets 36 months from Jan 1 2024, to Dec 31 2026. The employee, entitled
    # before the election, keeps the 18 months
    w.add(fam_("e", {"e": P("employee", "1959-01-20", elected="2024-10-05", notice="2024-09-25",
                            payments=pays("PPO", "2024-10-01", END), medicare="2024-01-01"),
                     "s": P("spouse", "1962-04-04", elected="2024-10-05", notice="2024-09-25",
                            payments=pays("PPO", "2024-10-01", END))},
               [{"type": "termination", "date": "2024-09-10"}]), ["medicare-before", "medicare"],
          [("s", "2026-09-15", True), ("e", "2026-01-15", True), ("e", "2026-04-02", False)])
    # Medicare 20 months before the termination (Jul 1 2022): 36 months from then end Jun 30 2025, before the 18
    # months end (Sep 30 2025): the spouse keeps the 18 months
    w.add(fam_("e", {"e": P("employee", "1957-07-15", elected=EL, notice=NT, payments=pays("PPO", S, END),
                            medicare="2022-07-01"),
                     "s": P("spouse", "1959-08-30", elected=EL, notice=NT, payments=pays("PPO", S, END))}, [T]),
          ["medicare-before"], [("s", "2025-09-30", True), ("s", "2025-10-01", False), ("e", "2025-07-15", True)])
    # other group coverage from Mar 1 2025 (after the election) ends COBRA on Feb 28 2025; coverage that began
    # May 1 2024 (before the May 20 election) does not
    w.add(fam_("e", {"e": P("employee", "1975-09-09", elected=EL, notice=NT,
                            payments=pays("PPO", S, E18), other_coverage="2025-03-01"),
                     "s": P("spouse", "1976-10-10", elected="2024-05-20", notice=NT,
                            payments=pays("PPO", S, E18, override={m: {"amount": 62465, "paid_on": D("2024-06-20")}
                                                                   for m in ("2024-04-01", "2024-05-01", "2024-06-01")}),
                            other_coverage="2024-05-01")}, [T]),
          ["early-termination"], [("e", "2025-02-28", True), ("e", "2025-03-05", False), ("s", "2025-03-05", True)])
    # death: the spouse and child get 36 months from Jul 1 2024, to Jun 30 2027
    w.add(fam_("e", {"e": P("employee", "1966-06-06"),
                     "s": P("spouse", "1967-07-07", elected="2024-07-15", notice="2024-07-01",
                            payments=pays("PPO", "2024-07-01", END)),
                     "c": P("child", "2003-03-30", elected="2024-07-15", notice="2024-07-01",
                            payments=pays("PPO", "2024-07-01", END))},
               [{"type": "death", "date": "2024-06-10"}]), ["maximum-period"],
          [("s", "2026-09-20", True), ("c", "2026-01-20", True)])
    # child turning 26 (Aug 14 2024) as the first event: 36 months from Sep 1 2024
    w.add(fam_("e", {"e": P("employee", "1966-06-06"),
                     "c": P("child", "1998-08-14", elected="2024-09-10", notice="2024-09-02",
                            payments=pays("PPO", "2024-09-01", END))},
               [{"type": "child_reaches_26", "date": "2024-08-14", "person": "c"}]), ["maximum-period"],
          [("c", "2026-09-20", True), ("c", "2024-09-03", True)])
    # child turning 26 during COBRA after a termination is a second event for the child: notice Mar 20 2025 (within
    # 60 days of Feb 3): 36 months to Mar 31 2027. A notice on May 5 is too late
    for note, ok in (("2025-03-20", True), ("2025-05-05", False)):
        w.add(fam_("e", {"e": P("employee", "1967-01-01", elected=EL, notice=NT, payments=pays("PPO", S, END)),
                         "c": P("child", "1999-02-03", elected=EL, notice=NT, payments=pays("PPO", S, END),
                                second_notice=note)},
                   [T, {"type": "child_reaches_26", "date": "2025-02-03", "person": "c"}]), ["second-event"],
              [("c", "2026-06-15", ok), ("e", "2026-06-15", False)])

    # the disability notice must also come before the 18 months end (Sep 30 2025): determination Sep 10 2025,
    # notice Sep 29 (extension) or Oct 3 (within 60 days of the determination but too late: no extension)
    for note, ok in (("2025-09-29", True), ("2025-10-03", False)):
        w.add(fam_("e", {"e": P("employee", "1966-02-02", elected=EL, notice=NT, payments=pays("PPO", S, END)),
                         "s": P("spouse", "1967-03-03", elected=EL, notice=NT,
                                payments=pays("PPO", S, END, disabled_months=ext),
                                ssa={"onset": "2024-04-20", "determination": "2025-09-10", "notice": note})}, [T]),
              ["disability-extension", "boundary"], [("e", "2025-11-15", ok), ("s", "2026-03-15", ok)])
    # 36 months end inside the queue: death Jun 10 2023, COBRA Jul 1 2023 to Jun 30 2026
    w.add(fam_("e", {"e": P("employee", "1964-04-04"),
                     "s": P("spouse", "1965-05-05", "HDHP", elected="2023-07-20", notice="2023-07-03",
                            payments=pays("HDHP", "2023-07-01", END))},
               [{"type": "death", "date": "2023-06-10"}]), ["maximum-period", "boundary"],
          [("s", "2026-06-30", True), ("s", "2026-07-01", False)])
    # divorce as a second event: 36 months from the start of COBRA (Apr 1 2023), not from the divorce: to Mar 31
    # 2026. The children are not extended by the divorce, which does not end a child's eligibility
    w.add(fam_("e", {"e": P("employee", "1970-10-10", elected="2023-04-12", notice="2023-04-03",
                            payments=pays("PPO", "2023-04-01", END)),
                     "s": P("spouse", "1971-11-11", elected="2023-04-12", notice="2023-04-03",
                            payments=pays("PPO", "2023-04-01", END), second_notice="2023-12-01"),
                     "c": P("child", "2005-01-21", elected="2023-04-12", notice="2023-04-03",
                            payments=pays("PPO", "2023-04-01", END), second_notice="2023-12-01")},
               [{"type": "termination", "date": "2023-03-15"}, {"type": "divorce", "date": "2023-11-06"}]),
          ["second-event", "boundary"],
          [("s", "2026-03-31", True), ("s", "2026-04-02", False), ("c", "2024-09-30", True), ("c", "2024-10-01", False),
           ("e", "2024-10-01", False)])
    # Medicare Jul 1 2023 before a termination on Feb 12 2024 (COBRA from Mar 1 2024, 18 months to Aug 31 2025):
    # the spouse gets 36 months from Jul 1 2023, to Jun 30 2026
    w.add(fam_("e", {"e": P("employee", "1958-07-19", elected="2024-03-11", notice="2024-02-26",
                            payments=pays("PPO", "2024-03-01", END), medicare="2023-07-01"),
                     "s": P("spouse", "1963-09-09", elected="2024-03-11", notice="2024-02-26",
                            payments=pays("PPO", "2024-03-01", END))},
               [{"type": "termination", "date": "2024-02-12"}]), ["medicare-before", "boundary"],
          [("s", "2026-06-30", True), ("s", "2026-07-02", False), ("e", "2025-09-02", False)])
    # the election period runs from the later of the loss of coverage and the notice: the notice came Mar 20
    # 2024, before coverage was lost on Apr 1, so the deadline is May 31. Elected May 25: covered
    w.add(fam_("e", {"e": P("employee", "1972-12-12", elected="2024-05-25", notice="2024-03-20",
                            payments=pays("PPO", S, END))}, [T]), ["election"],
          [("e", "2024-06-15", True), ("e", "2025-01-15", True)])

    # FMLA leave Feb 20 to Apr 12 2024 without returning; the employer recorded the termination Jun 20. The
    # qualifying event is Apr 12 (54.4980B-10): COBRA from May 1 2024, 18 months to Oct 31 2025
    FM = {"type": "termination", "date": "2024-06-20", "fmla_first": D("2024-02-20"), "fmla_last": D("2024-04-12")}
    w.add(fam_("e", {"e": P("employee", "1969-09-19", elected="2024-07-10", notice="2024-06-25",
                            payments=pays("PPO", "2024-05-01", END)),
                     "s": P("spouse", "1970-03-23", "HDHP", elected="2024-07-10", notice="2024-06-25",
                            payments=pays("HDHP", "2024-05-01", END))}, [FM]),
          ["fmla-leave", "maximum-period"],
          [("e", "2024-05-15", True), ("e", "2025-10-31", True), ("e", "2025-11-15", False), ("s", "2025-12-20", False),
           ("s", "2024-06-03", True)])
    # the same, with no payment for May 2024: the first month is unpaid, so no coverage at all
    w.add(fam_("e", {"e": P("employee", "1969-09-19", elected="2024-07-10", notice="2024-06-25",
                            payments=pays("PPO", "2024-06-01", END))}, [FM]),
          ["fmla-leave", "premiums"], [("e", "2024-06-15", False), ("e", "2025-02-15", False)])
    # waiver Apr 10 2024 revoked May 20 (inside the election period that ends Jun 4): coverage from May 20, not
    # retroactive; May is paid with the June payments. A revocation on Jun 10 is too late
    w.add(fam_("e", {"e": P("employee", "1973-01-13", elected="2024-05-20", notice=NT, waived="2024-04-10",
                            payments=pays("PPO", "2024-05-01", END, override={"2024-05-01": {"amount": 62465, "paid_on": D("2024-07-01")}}))},
               [T]), ["waiver", "election"],
          [("e", "2024-04-20", False), ("e", "2024-05-25", True), ("e", "2025-09-30", True), ("e", "2025-10-01", False)])
    w.add(fam_("e", {"e": P("employee", "1973-01-13", elected="2024-06-10", notice=NT, waived="2024-04-10",
                            payments=pays("PPO", "2024-06-01", END))}, [T]), ["waiver", "election", "boundary"],
          [("e", "2024-06-20", False), ("e", "2024-12-20", False)])
    # a child who cannot support themself because of a disability stays eligible at 26: the birthday (Jun 10 2025)
    # is not a second qualifying event and the 18 months end Sep 30 2025
    w.add(fam_("e", {"e": P("employee", "1968-02-02", elected=EL, notice=NT, payments=pays("PPO", S, END)),
                     "c": P("child", "1999-06-10", elected=EL, notice=NT, payments=pays("PPO", S, END),
                            second_notice="2025-07-01", incapable=True)},
               [T, {"type": "child_reaches_26", "date": "2025-06-10", "person": "c"}]), ["second-event", "incapable-child"],
          [("c", "2025-09-30", True), ("c", "2025-10-15", False), ("c", "2026-06-15", False)])
    # the spouse turns 65 on Feb 14 2025: Medicare from Feb 1 2025, after the election, ends her COBRA Jan 31 2025
    w.add(fam_("e", {"e": P("employee", "1962-05-05", elected=EL, notice=NT, payments=pays("PPO", S, END)),
                     "s": P("spouse", "1960-02-14", elected=EL, notice=NT, payments=pays("PPO", S, END),
                            medicare="2025-02-01")}, [T]), ["medicare", "early-termination"],
          [("s", "2025-01-20", True), ("s", "2025-02-10", False), ("e", "2025-02-10", True)])

    # deductible credit from active coverage (54.4980B-5): PPO 2024 deductible 750.00, 20% coinsurance. Feb 10
    # 2024 under active coverage, 400.00 allowed: all deductible, plan pays 0.00. Apr 20 (COBRA), 1,000.00: 350.00
    # deductible left, 20% of 650.00 = 130.00, the person pays 480.00, the plan 520.00. Jan 15 2025, 300.00: a new
    # deductible, plan pays 0.00
    w.add(fam_("e", {"e": P("employee", "1971-07-07", elected=EL, notice=NT, payments=pays("PPO", S, END))}, [T]),
          ["deductible-credit"],
          [("e", "2024-02-10", True, 40000, 0), ("e", "2024-04-20", True, 100000, 52000),
           ("e", "2025-01-15", True, 30000, 0), ("e", "2025-03-03", True, 85000, 32000)])


def filler(w):
    qe = rng.choice(["termination"] * 6 + ["reduction_of_hours"] * 2 + ["death", "divorce", "child_reaches_26"])
    qd = date(2022, 6, 1) + days(rng.randrange(0, 1180))
    S = next_month(qd)
    born_e = date(rng.randint(1957, 1980), rng.randint(1, 12), rng.randint(1, 28))
    people = {"e": P("employee", born_e)}
    if rng.random() < 0.7 or qe == "divorce":
        people["s"] = P("spouse", born_e + days(rng.randrange(-1500, 1500)))
    for k in range(rng.choice([0, 0, 1, 2]) if qe != "child_reaches_26" else 1):
        people[f"c{k}"] = P("child", date(rng.randint(1996, 2012), rng.randint(1, 12), rng.randint(1, 28)))
        if rng.random() < 0.15 and not (qe == "child_reaches_26" and k == 0):
            people[f"c{k}"]["incapable"] = True
            if rng.random() < 0.5:
                people[f"c{k}"]["born"] = date(rng.randint(1985, 1996), rng.randint(1, 12), rng.randint(1, 28))
    first = {"type": qe, "date": qd}
    if qe == "child_reaches_26":
        b = people["c0"]["born"]
        first["date"] = qd = date(b.year + 26, b.month, b.day)
        first["person"] = "c0"
        S = next_month(qd)
        if not date(2022, 6, 1) <= qd <= date(2025, 9, 1):
            return False
    for c in [p for p in people if p.startswith("c")]:
        b = people[c]["born"]
        if not (qe == "child_reaches_26" and c == "c0") and date(b.year + 26, b.month, b.day) < S \
                and not people[c].get("incapable"):
            return False
    events = [first]
    recorded = qd
    if qe == "termination" and rng.random() < 0.3:     # employee did not return from FMLA leave
        first["fmla_first"] = qd - days(rng.randrange(20, 84))
        first["fmla_last"] = qd
        first["date"] = recorded = qd + days(rng.choice([25, 40, 60, 75, 100]))
        if month_start(recorded) == month_start(qd) or recorded > date(2025, 10, 1):
            return False
    if "s" in people and rng.random() < 0.6:          # Medicare from the month the spouse turns 65
        b = people["s"]["born"].replace(day=rng.randint(2, 28))
        people["s"]["born"] = b
        if date(2020, 1, 1) <= date(b.year + 65, b.month, 1) <= LAST:
            people["s"]["medicare"] = date(b.year + 65, b.month, 1)
    if qe in ("termination", "reduction_of_hours") and rng.random() < 0.2:
        people["e"]["medicare"] = add_months(month_start(qd), -rng.choice([2, 8, 15, 17, 19, 30]))
    elif rng.random() < 0.12 and qe != "death":
        people["e"]["medicare"] = add_months(S, rng.choice([3, 9, 14]))
        events.append({"type": "employee_medicare_entitlement", "date": people["e"]["medicare"]})
    if people["e"].get("medicare"):              # Medicare from the month the employee turns 65
        med = people["e"]["medicare"]
        people["e"]["born"] = date(med.year - 65, med.month, rng.randint(2, 28))
    if qe == "reduction_of_hours" and rng.random() < 0.4:
        events.append({"type": "termination", "date": qd + days(rng.randrange(40, 300))})
    aff = qualified(first, people)
    notice = recorded + days(rng.choice([5, 10, 20, 40, 50]))
    option = rng.choice(["PPO", "HDHP"])
    for p in aff:
        q = people[p]
        q["option"] = rng.choice([option, option, "PPO", "HDHP"])
        q["notice"] = notice
        r = rng.random()
        if r < 0.07:
            q["elected"] = None
            continue
        q["elected"] = max(notice, S) + days(rng.choice([3, 10, 30, 45, 58, 59, 60, 61, 62]) if r < 0.3
                                             else rng.choice([2, 7, 14, 21]))
        if rng.random() < 0.15:                       # waived first, then revoked the waiver
            q["waived"] = notice + days(rng.choice([1, 3, 8]))
            q["elected"] = q["waived"] + days(rng.choice([4, 15, 30, 45, 52]))
            if q["elected"].day == 1 or q["elected"] <= q["waived"]:
                q["elected"] += DAY
            continue
        if rng.random() < 0.18 and p != "e" and qe in ("termination", "reduction_of_hours"):
            on = S + days(rng.choice([-40, 10, 45, 58, 59, 61, 62, 90]))
            det = S + days(rng.choice([90, 150, 300]))
            q["ssa"] = {"onset": on.isoformat(), "determination": det.isoformat(),
                        "notice": (det + days(rng.choice([20, 59, 60, 61, 80]))).isoformat()}
        if rng.random() < 0.12:
            k = rng.choice([0, 0, 1, 4, 10, 16])
            oc = add_months(month_start(D(q["elected"])), k)
            if oc != D(q["elected"]):
                q["other_coverage"] = oc
    death_on = None
    if qe in ("termination", "reduction_of_hours"):
        if "s" in people and rng.random() < 0.3:
            x = {"type": rng.choice(["divorce", "divorce", "death"]),
                 "date": S + days(rng.randrange(30, 900))}
            if x["date"] <= LATEST_EVENT:
                events.append(x)
                if x["type"] == "death":
                    death_on = x["date"]
                    for p in people:
                        if p != "e" and people[p].get("elected"):
                            people[p]["second_notice"] = x["date"] + days(rng.choice([5, 12, 30]))
                elif people["s"].get("elected") and rng.random() < 0.85:
                    people["s"]["second_notice"] = x["date"] + days(rng.choice([10, 45, 59, 60, 95, 130]))
        if death_on is None:
            for c in [p for p in people if p.startswith("c")]:
                b = people[c]["born"]
                turn = date(b.year + 26, b.month, b.day)
                if LATEST_EVENT < turn <= ASOF:
                    return False
                if S <= turn <= LATEST_EVENT:
                    events.append({"type": "child_reaches_26", "date": turn, "person": c})
                    if people[c].get("elected") and rng.random() < 0.8:
                        people[c]["second_notice"] = turn + days(rng.choice([15, 50, 59, 60, 95, 120]))
    events = [events[0]] + sorted(events[1:], key=lambda e: e["date"])
    if any(D(x["date"]) <= recorded for x in events[1:]):
        return False
    for q in people.values():
        if q.get("second_notice") and q["second_notice"] > ASOF:
            q["second_notice"] = None
    # payments: each person pays for a while, with mistakes near every threshold
    for p in aff:
        q = people[p]
        if not q.get("elected"):
            continue
        el = D(q["elected"])
        begin = el if q.get("waived") else S
        initial_paid = el + days(rng.choice([3, 10, 20, 30, 40, 44, 45, 45, 46] if rng.random() < 0.35 else [5, 12, 20]))
        stop = add_months(S, rng.choice([12, 18, 24, 29, 30, 36, 40, 40]))
        m = month_start(begin)
        while m <= LAST and m < stop:
            if p == "e" and death_on and m > death_on:
                break
            rate = 150 if q.get("ssa") and add_months(S, 18) <= m < add_months(S, 29) and rng.random() < 0.85 else 102
            amt = due(q["option"], m, rate)
            pay = None
            if m + days(30) < el + days(45):                     # months due before the first-payment deadline
                pay = {"amount": amt, "paid_on": initial_paid}
            else:
                pay = {"amount": amt, "paid_on": m + days(rng.choice([0, 3, 10, 20, 27]))}
                r = rng.random()
                if r < 0.05:
                    pay["paid_on"] = m + days(rng.choice([29, 30, 31, 32]))
                elif r < 0.10:
                    thr = min(5000, amt // 10)
                    pay["amount"] = amt - rng.choice([thr - 1, thr, thr + 1, 1500])
                elif r < 0.14 and m <= date(2026, 7, 1):
                    pay["amount"] = amt - rng.choice([800, 2000, min(5000, amt // 10) - 1])
                    pay["shortfall_notice"] = D(pay["paid_on"]) + days(rng.choice([5, 12]))
                    pay["deficiency_paid_on"] = pay["shortfall_notice"] + days(rng.choice([10, 29, 30, 31, 45]))
                elif r < 0.16:
                    pay = None
            if pay:
                q["payments"][m] = pay
            m = add_months(m, 1)
    fam = fam_("e", people, events)
    try:
        ranges = sim(fam)
    except Reject:
        return False
    info = fam["info"]
    claims = []
    for p in aff:
        r = ranges.get(p)
        anchors = [S, S + days(40), LAST]
        if r:
            anchors += [r[1], r[1] + DAY, r[1] - days(3)]
        anchors += [info["end18"], info["end18"] + DAY, info["end29"], info["end29"] + DAY,
                    add_months(S, 36) - DAY, add_months(S, 36)]
        for x in events[1:]:
            anchors.append(x["date"] + days(rng.randrange(1, 40)))
        mine = [a for a in anchors if S <= a <= LAST and rng.random() < 0.7]
        mine += [S + days(rng.randrange(0, max(1, (LAST - S).days))) for _ in range(rng.choice([1, 2, 3]))]
        for a in mine:
            if p == "e" and death_on and a >= death_on:
                continue
            # no claim on the first day of other coverage or Medicare, or on the day after a period counted from
            # the employee's Medicare date (the day-before conventions are stated, but keep them out of the data)
            if a in (people[p].get("other_coverage"), people[p].get("medicare"), people[p].get("elected")):
                continue
            med = people["e"].get("medicare")
            if p != "e" and med and med < qd and a == add_months(med, 36):
                continue
            # keep out the open question of whether others keep the 29 months when the disabled person's own
            # coverage ended before then
            if info["ext29"] and p not in info["disabled"] and a > info["end18"]:
                dis_ends = [ranges.get(d) and ranges[d][1] for d in info["disabled"]]
                if any(not e or e < min(info["end29"], LAST) for e in dis_ends):
                    continue
            claims.append((p, a, None))
    if not claims:
        return False
    w.add(fam, ["filler"], sorted(set(claims), key=lambda c: (c[0], c[1])))
    return True


def main():
    w = World()
    planted(w)
    for f in w.fams:
        ranges = sim(f)
        for x in f["expected"]:
            p, d, want = x[:3]
            got = D(d) < f["info"]["S"] or covered(ranges, p, d)
            assert got == want, (f["tags"], p, d, got, want, ranges)
    n_planted = len(w.fams)
    rejected = 0
    while len(w.fams) < n_planted + 170:
        if not filler(w):
            rejected += 1
    rng.shuffle(w.fams)
    people_out, events_out, elections, payments, claims_out, golden, tags = [], [], [], [], [], {}, {}
    rows = []
    for n, f in enumerate(w.fams, 1):
        fid = f"F{n:03d}"
        pid = {k: f"P{n:03d}{k.upper()}" for k in f["people"]}
        for k, q in f["people"].items():
            rec = {"person_id": pid[k], "family_id": fid, "relationship": q["role"], "date_of_birth": q["born"].isoformat(),
                   "medicare_entitlement_date": D(q["medicare"]).isoformat() if q.get("medicare") else None,
                   "other_group_health_coverage_start": D(q["other_coverage"]).isoformat() if q.get("other_coverage") else None,
                   "ssa_disability_determination": None}
            if q["role"] == "child":
                rec["incapable_of_self_support_because_of_disability"] = bool(q.get("incapable"))
            if q.get("ssa"):
                rec["ssa_disability_determination"] = {"disabled_since": q["ssa"]["onset"],
                                                       "determination_date": q["ssa"]["determination"],
                                                       "notice_to_plan_date": q["ssa"]["notice"]}
            people_out.append(rec)
            if q.get("notice"):
                elections.append({"person_id": pid[k], "election_notice_date": q["notice"].isoformat(),
                                  "waived_on": D(q["waived"]).isoformat() if q.get("waived") else None,
                                  "elected_on": q["elected"].isoformat() if q.get("elected") else None,
                                  "coverage_option": q["option"],
                                  "second_event_notice_date": D(q["second_notice"]).isoformat() if q.get("second_notice") else None})
            for m in sorted(q["payments"]):
                pay = q["payments"][m]
                payments.append({"person_id": pid[k], "coverage_month": f"{m.year:04d}-{m.month:02d}",
                                 "amount_cents": pay["amount"], "sent_on": D(pay["paid_on"]).isoformat(),
                                 "shortfall_notice_date": D(pay["shortfall_notice"]).isoformat() if pay.get("shortfall_notice") else None,
                                 "deficiency_sent_on": D(pay["deficiency_paid_on"]).isoformat() if pay.get("deficiency_paid_on") else None})
        for e in f["events"]:
            events_out.append({"family_id": fid, "event": e["type"], "date": D(e["date"]).isoformat(),
                               "person_id": pid[e["person"]] if e.get("person") else None,
                               "fmla_leave": {"first_day": D(e["fmla_first"]).isoformat(),
                                              "last_day": D(e["fmla_last"]).isoformat()} if e.get("fmla_last") else None})
        ranges = sim(f, strict=False)
        S = f["info"]["S"]
        per = {}
        for x in f["expected"]:
            p, d = x[0], D(x[1])
            # planted claims exceed any deductible, so covered or not always shows in the payment
            allowed = x[3] if len(x) > 3 else (rng.randint(250000, 900000) if x[2] is not None else claim_amount())
            per.setdefault(p, {})[d] = [allowed, d < S or covered(ranges, p, d), f["tags"], x[2] is not None,
                                        x[4] if len(x) > 4 else None]
        for p, q in f["people"].items():                   # claims under active coverage before COBRA
            if not q.get("notice") or "deductible-credit" in f["tags"]:
                continue
            lo = date((S - DAY).year, 1, 1) - days(rng.choice([0, 0, 90]))
            for _ in range(rng.choice([0, 1, 2, 2, 3, 4])):
                d = lo + days(rng.randrange(0, max(1, (S - lo).days)))
                if d < S and d not in per.get(p, {}):
                    per.setdefault(p, {})[d] = [claim_amount(), True, ["active"], False, None]
        for p, byday in per.items():
            opt = f["people"][p]["option"]
            dates = sorted(byday)
            items = [(d, byday[d][0], byday[d][1]) for d in dates]
            pays_ = ledger(items, opt, S)
            if pays_ != ledger(items, opt, S, carry_oop=False):   # keep the out-of-pocket carry-over reading out
                for d in dates:
                    if d < S and "active" in byday[d][2]:
                        del byday[d]
                dates = sorted(byday)
                items = [(d, byday[d][0], byday[d][1]) for d in dates]
                pays_ = ledger(items, opt, S)
                assert pays_ == ledger(items, opt, S, carry_oop=False)
            for d, amt in zip(dates, pays_):
                allowed, cov, tg, planted_, want_pay = byday[d]
                if want_pay is not None:
                    assert want_pay == amt, (f["tags"], p, d, amt, want_pay)
                rows.append((pid[p], d, cov, tg, planted_, allowed, amt))
    rng.shuffle(rows)
    for rec in people_out + events_out + elections + payments:
        for v in json.dumps(rec).split('"'):
            if len(v) == 10 and v[4] == "-" and v[7] == "-" and v[:2] == "20":
                assert v <= ASOF.isoformat(), rec
    events_out.sort(key=lambda e: (e["date"], e["family_id"]))
    payments.sort(key=lambda x: (x["sent_on"], x["person_id"], x["coverage_month"]))
    for n, (pid_, d, cov, tg, planted_, allowed, amt) in enumerate(rows, 1):
        cid = f"C{n:05d}"
        claims_out.append({"claim_id": cid, "person_id": pid_, "date_of_service": d.isoformat(),
                           "allowed_amount_cents": allowed})
        tags[cid] = tg
        if planted_:
            golden[cid] = f"{amt // 100}.{amt % 100:02d}"
    ENV.mkdir(parents=True, exist_ok=True)
    for old in ENV.iterdir():
        old.unlink()
    dump = lambda n, o: (ENV / n).write_text(json.dumps(o, indent=1) + "\n")  # noqa: E731
    dump("plan.json", {"plan_name": "Northgate Industries Group Health Plan", "plan_year": "calendar year",
                       "employees_on_a_typical_business_day": 1840, "coverage_options": ["PPO", "HDHP"],
                       "applicable_premium_single_coverage_cents":
                           {o: {str(y): v for y, v in r.items()} for o, r in PREMIUM.items()},
                       "benefits_per_person_per_calendar_year":
                           {o: {str(y): {"deductible_cents": v[0], "coinsurance_percent": v[1],
                                         "out_of_pocket_maximum_cents": v[2]} for y, v in r.items()}
                            for o, r in BENEFIT.items()}})
    dump("people.json", people_out)
    dump("events.json", events_out)
    dump("elections.json", elections)
    dump("premium_payments.json", payments)
    dump("claims.json", claims_out)
    if TST.exists():
        shutil.rmtree(TST)
    shutil.copytree(ENV, TST)
    (ROOT / "tests" / "case_tags.json").write_text(json.dumps(tags, indent=1, sort_keys=True) + "\n")
    (ROOT / "tests" / "golden.json").write_text(json.dumps(golden, indent=1, sort_keys=True) + "\n")
    (Path(__file__).resolve().parent / "sim_answers.json").write_text(
        json.dumps({f"C{n:05d}": f"{r[6] // 100}.{r[6] % 100:02d}" for n, r in enumerate(rows, 1)}, indent=0) + "\n")
    yes = sum(1 for r in rows if r[2])
    print(len(w.fams), "families,", len(people_out), "people,", len(payments), "payments,", len(claims_out), "claims (",
          yes, "yes ),", len(golden), "hand-worked claims,", rejected, "rejected")


if __name__ == "__main__":
    main()
