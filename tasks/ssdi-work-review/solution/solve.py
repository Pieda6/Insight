#!/usr/bin/env python3
"""Reference solution: SSDI work continuing disability review under 20 CFR 404.315, 404.621, 404.1592, 404.1592a,
404.1574 and 404.1576. Walks each beneficiary month by month through the trial work period, the extended period
of eligibility and afterwards."""
import csv
import json
from collections import defaultdict
from pathlib import Path

DATA = Path("/app/data")
OUT = Path("/app/output")
LAST = (2025, 12)


def j(name):
    return json.loads((DATA / name).read_text())


def idx(y, m):
    return y * 12 + (m - 1)


def label(i):
    return f"{i // 12:04d}-{i % 12 + 1:02d}"


def first_month(onset, filed):
    """404.315: 5 full calendar months of disability; 404.621: at most 12 months before the month of filing."""
    y, m, dd = (int(x) for x in onset.split("-"))
    full = idx(y, m) if dd == 1 else idx(y, m) + 1
    fy, fm, _ = (int(x) for x in filed.split("-"))
    return max(full + 5, idx(fy, fm) - 12), idx(fy, fm)


def review(ben, earnings, amounts):
    start, filed = first_month(ben["disability_onset_date"], ben["application_date"])
    rows = []
    services = []
    twp_end = cessation = None
    ended = False
    for i in range(start, idx(*LAST) + 1):
        a = amounts[str(i // 12)]
        e = earnings.get(i, {"gross_wages": 0, "employer_subsidy": 0, "impairment_related_work_expenses": 0})
        gross = e["gross_wages"]
        countable = gross - e["employer_subsidy"] - e["impairment_related_work_expenses"]       # 404.1574
        sga = countable > (a["substantial_gainful_activity_blind"] if ben["statutorily_blind"]
                           else a["substantial_gainful_activity_non_blind"])
        if twp_end is None:                                                                  # 404.1592
            service = i >= filed and gross > a["trial_work_period_service_month"]
            if service:
                services.append(i)
                if len([s for s in services if s >= i - 59]) == 9:
                    twp_end = i
            rows.append((i, True, service))
            continue
        if ended:
            rows.append((i, False, False))
            continue
        if i <= twp_end + 36:                                                                # 404.1592a(a)
            if cessation is None and sga:
                cessation = i
            grace = cessation is not None and i <= cessation + 2
            rows.append((i, grace or not sga, False))
        else:
            if sga:
                ended = True
            rows.append((i, not sga, False))
    return rows


def main():
    amounts = j("annual_amounts.json")["by_year"]
    earn = defaultdict(dict)
    for e in j("earnings.json"):
        y, m = (int(x) for x in e["month"].split("-"))
        earn[e["beneficiary_id"]][idx(y, m)] = e
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "monthly_determinations.csv", "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["beneficiary_id", "month", "benefit_payable", "trial_work_month"])
        for ben in sorted(j("beneficiaries.json"), key=lambda b: b["beneficiary_id"]):
            for i, paid, twm in review(ben, earn[ben["beneficiary_id"]], amounts):
                w.writerow([ben["beneficiary_id"], label(i), "yes" if paid else "no", "yes" if twm else "no"])


if __name__ == "__main__":
    main()
