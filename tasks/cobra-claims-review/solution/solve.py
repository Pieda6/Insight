#!/usr/bin/env python3
"""Reference solution for cobra-claims-review (26 CFR 54.4980B-1 through -10).

For every qualified beneficiary, work out the last month of COBRA continuation coverage: the maximum coverage
period (18 or 36 months, 29 with the disability extension, 36 after a timely reported second qualifying event,
the later of 36 months from Medicare and the regular period for dependents of an employee entitled to Medicare
before a termination), cut short by other group coverage or Medicare that begins after the election, then by the
first month whose premium is not paid in time and in full. Months are integer indexes (year * 12 + month - 1)."""
import csv
import json
from collections import defaultdict
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

DATA = Path("/app/data")
OUT = Path("/app/output")
EIGHTEEN_MONTH_EVENTS = {"termination", "reduction_of_hours"}
SECOND_EVENTS = {"spouse": {"death", "divorce"}, "child": {"death", "child_reaches_26"}}


def day(s):
    return date.fromisoformat(s) if s else None


def month_index(x):
    return x.year * 12 + x.month - 1


def first_day(k):
    return date(k // 12, k % 12 + 1, 1)


def last_day(k):
    return first_day(k + 1) - timedelta(days=1)


def load(name):
    return json.loads((DATA / name).read_text())


def main():
    plan = load("plan.json")
    people = {p["person_id"]: p for p in load("people.json")}
    elections = {e["person_id"]: e for e in load("elections.json")}
    family = defaultdict(list)
    for p in people.values():
        family[p["family_id"]].append(p["person_id"])
    events = defaultdict(list)
    for e in load("events.json"):
        events[e["family_id"]].append(e)
    payments = {}
    for x in load("premium_payments.json"):
        y, m = map(int, x["coverage_month"].split("-"))
        payments[(x["person_id"], y * 12 + m - 1)] = x
    rates = plan["applicable_premium_single_coverage_cents"]

    def premium(option, k, percent):
        base = Decimal(rates[option][str(k // 12)])
        return int((base * percent / 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))

    last_month = {}                                   # person -> (first month, last covered month) or None
    for fid, members in family.items():
        evs = sorted(events[fid], key=lambda e: e["date"])
        qe = evs[0]
        qe_day = day(qe["date"])
        start = month_index(qe_day) + 1               # coverage ends with the month of the event
        start_day = first_day(start)
        employee = next(p for p in members if people[p]["relationship"] == "employee")
        short_period = qe["event"] in EIGHTEEN_MONTH_EVENTS

        def elected_in_time(pid):
            e = elections.get(pid)
            if not e or not e["elected_on"]:
                return False
            opens = max(start_day, day(e["election_notice_date"]))
            return day(e["elected_on"]) <= opens + timedelta(days=60)

        beneficiaries = [p for p in members if p in elections]
        disabled = set()
        if short_period:
            for p in beneficiaries:
                ssa = people[p]["ssa_disability_determination"]
                if not ssa:
                    continue
                within_first_60 = day(ssa["disabled_since"]) <= start_day + timedelta(days=59)
                told = day(ssa["notice_to_plan_date"])
                if within_first_60 and told <= day(ssa["determination_date"]) + timedelta(days=60) \
                        and told <= last_day(start + 17):
                    disabled.add(p)
        months = 36 if not short_period else (29 if disabled else 18)

        for p in beneficiaries:
            if not elected_in_time(p):
                last_month[p] = None
                continue
            role = people[p]["relationship"]
            final = start + months - 1
            if short_period and role != "employee":
                window_end = last_day(final)
                for e in evs[1:]:
                    if e["event"] not in SECOND_EVENTS[role]:
                        continue
                    if e["event"] == "child_reaches_26" and e["person_id"] != p:
                        continue
                    when = day(e["date"])
                    told = day(elections[p]["second_event_notice_date"])
                    if start_day <= when <= window_end and told and told <= when + timedelta(days=60):
                        final = max(final, start + 35)
                medicare = day(people[employee]["medicare_entitlement_date"])
                if medicare and medicare < qe_day:
                    final = max(final, month_index(medicare) + 35)
            elected = day(elections[p]["elected_on"])
            for key in ("other_group_health_coverage_start", "medicare_entitlement_date"):
                begins = day(people[p][key])
                if begins and begins > elected:
                    final = min(final, month_index(begins) - 1)

            option = elections[p]["coverage_option"]
            covered_to = None
            k = start
            while k <= final and first_day(k) <= date(2026, 9, 30):
                percent = 150 if p in disabled and start + 18 <= k <= start + 28 else 102
                owed = premium(option, k, percent)
                pay = payments.get((p, k))
                if pay is None:
                    break
                deadline = max(first_day(k) + timedelta(days=30), elected + timedelta(days=45))
                if day(pay["sent_on"]) > deadline:
                    break
                gap = owed - pay["amount_cents"]
                if gap > 0:
                    if gap > 5000 or gap * 10 > owed:
                        break
                    if pay["shortfall_notice_date"]:
                        cured = day(pay["deficiency_sent_on"])
                        if not cured or cured > day(pay["shortfall_notice_date"]) + timedelta(days=30):
                            break
                covered_to = k
                k += 1
            if covered_to is None:
                last_month[p] = None
            elif k > final:
                last_month[p] = (start, final)
            else:
                last_month[p] = (start, covered_to)

    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "claim_determinations.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["claim_id", "covered"])
        for c in load("claims.json"):
            span = last_month.get(c["person_id"])
            k = month_index(day(c["date_of_service"]))
            w.writerow([c["claim_id"], "yes" if span and span[0] <= k <= span[1] else "no"])


if __name__ == "__main__":
    main()
