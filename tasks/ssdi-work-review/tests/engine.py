"""Verifier-side model of an SSDI work continuing disability review (20 CFR 404.315, 404.621, 404.1574, 404.1576,
404.1592, 404.1592a), written independently of the reference solution: it first locates the milestones (first
month of entitlement, end of the trial work period by a sliding 60-month window over service months, cessation
month, end of the extended period, termination) and then derives every month's answer from them."""
import json
from collections import defaultdict
from datetime import date
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
THROUGH = date(2025, 12, 1)


def load(name):
    return json.loads((DATA / name).read_text())


def add(d, n):
    k = d.year * 12 + d.month - 1 + n
    return date(k // 12, k % 12 + 1, 1)


def month_of(s):
    y, m = int(s[:4]), int(s[5:7])
    return date(y, m, 1)


def between(a, b):
    out, d = [], a
    while d <= b:
        out.append(d)
        d = add(d, 1)
    return out


def milestones(ben, earn, amounts):
    onset = date.fromisoformat(ben["disability_onset_date"])
    filed = month_of(ben["application_date"])
    waiting_start = month_of(ben["disability_onset_date"]) if onset.day == 1 else add(month_of(ben["disability_onset_date"]), 1)
    entitled = max(add(waiting_start, 5), add(filed, -12))
    span = between(entitled, THROUGH)

    def amt(d, key):
        return amounts[str(d.year)][key]

    def countable(d):
        e = earn.get(d)
        if not e:
            return 0
        return e["gross_wages"] - e["employer_subsidy"] - e["impairment_related_work_expenses"]

    def substantial(d):
        key = "substantial_gainful_activity_blind" if ben["statutorily_blind"] else "substantial_gainful_activity_non_blind"
        return countable(d) > amt(d, key)

    service = [d for d in span if d >= filed and earn.get(d) and earn[d]["gross_wages"] > amt(d, "trial_work_period_service_month")]
    twp_end = None
    for k in range(8, len(service)):
        if service[k - 8] > add(service[k], -60):          # 9 service months inside 60 consecutive months
            twp_end = service[k]
            break
    if twp_end is not None:
        service = [d for d in service if d <= twp_end]
    epe_last = add(twp_end, 36) if twp_end else None
    cessation = next((d for d in span if twp_end and twp_end < d <= epe_last and substantial(d)), None)
    termination = next((d for d in span if epe_last and d > epe_last and substantial(d)), None)
    return span, set(service), twp_end, epe_last, cessation, termination, substantial


def expected():
    amounts = load("annual_amounts.json")["by_year"]
    earn = defaultdict(dict)
    for e in load("earnings.json"):
        earn[e["beneficiary_id"]][month_of(e["month"])] = e
    rows = []
    for ben in sorted(load("beneficiaries.json"), key=lambda b: b["beneficiary_id"]):
        span, service, twp_end, epe_last, cessation, termination, substantial = milestones(ben, earn[ben["beneficiary_id"]], amounts)
        for d in span:
            if twp_end is None or d <= twp_end:
                paid = True
            elif termination is not None and d >= termination:
                paid = False
            elif cessation is not None and cessation <= d <= add(cessation, 2):
                paid = True
            else:
                paid = not substantial(d)
            rows.append([ben["beneficiary_id"], f"{d.year:04d}-{d.month:02d}", "yes" if paid else "no",
                         "yes" if d in service else "no"])
    return rows
