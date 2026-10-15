#!/usr/bin/env python3
"""Generate the ssdi-work-review inputs (dev only, never shipped).

A disability claims unit runs work continuing disability reviews for SSDI beneficiaries who returned to work.
For each beneficiary and each month from the first month of entitlement through December 2025 it must decide
whether a benefit is payable and whether the month is a trial work month. Rules: 20 CFR 404.315 (waiting period),
404.621 (12 months of retroactivity), 404.1592 (trial work period: 9 service months in a rolling 60-month
window, not before the month of filing), 404.1592a (36-month extended period of eligibility, cessation month and
two grace months, termination by work after the extended period), 404.1574 and 404.1576 (countable earnings net
of subsidies and impairment-related work expenses). Planted beneficiaries carry hand-worked answers.
"""
import json
import random
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "tasks" / "ssdi-work-review"
ENV, TST = ROOT / "environment" / "data", ROOT / "tests" / "data"
rng = random.Random(15920)
END = (2025, 12)
# published monthly amounts in dollars: trial work service month, SGA (non-blind), SGA (statutorily blind)
AMOUNTS = {2018: (850, 1180, 1970), 2019: (880, 1220, 2040), 2020: (910, 1260, 2110), 2021: (940, 1310, 2190),
           2022: (970, 1350, 2260), 2023: (1050, 1470, 2460), 2024: (1110, 1550, 2590), 2025: (1160, 1620, 2700)}
NAMES = ["A. Okafor", "B. Lindqvist", "C. Ramirez", "D. Chen", "E. Novak", "F. Haddad", "G. Moreau", "H. Tanaka",
         "I. Kowalski", "J. Mensah", "K. Patel", "L. Rossi", "M. Byrne", "N. Silva", "O. Ahmed", "P. Schultz"]


class Reject(Exception):
    pass


def mi(y, m):                       # month index
    return y * 12 + m - 1


def ym(i):
    return i // 12, i % 12 + 1


def mstr(i):
    y, m = ym(i)
    return f"{y:04d}-{m:02d}"


def parse(s):                       # "YYYY-MM-DD" -> (month index, day)
    y, m, d = (int(x) for x in s.split("-"))
    return mi(y, m), d


def sim(b, strict=True):
    """Third implementation: {month index: (payable, trial_work_month)} from entitlement through END."""
    onset_m, onset_d = parse(b["onset"])
    app_m, _ = parse(b["application"])
    first_full = onset_m if onset_d == 1 else onset_m + 1
    ent = max(first_full + 5, app_m - 12)                      # 5 full months waited; 12 months retroactive
    end = mi(*END)
    earn = b["earnings"]                                       # month index -> (gross, subsidy, irwe) dollars
    if strict:
        for m, (g, sub, irwe) in earn.items():
            lim = AMOUNTS[ym(m)[0]][2 if b["blind"] else 1]
            if m < app_m and g - sub - irwe > lim:
                raise Reject("SGA before the month of filing")
            if m < onset_m + 12:
                raise Reject("work within 12 months of onset")
    out = {}
    service = []
    twp_end = None
    cessation = None
    terminated = False
    for m in range(ent, end + 1):
        y = ym(m)[0]
        twp_amt, sga, sga_blind = AMOUNTS[y]
        limit = sga_blind if b["blind"] else sga
        g, sub, irwe = earn.get(m, (0, 0, 0))
        countable = g - sub - irwe
        sga_month = countable > limit
        if strict and m < onset_m + 12 and g:
            raise Reject("work within 12 months of onset")
        if strict and m < app_m and sga_month:
            raise Reject("SGA before the month of filing")
        twm = False
        if twp_end is None:
            if m >= app_m and g > twp_amt:
                twm = True
                service.append(m)
                if sum(1 for s in service if s > m - 60) >= 9:
                    twp_end = m
            out[m] = (True, twm)
            continue
        epe_end = twp_end + 36
        if terminated:
            out[m] = (False, False)
            continue
        if m <= epe_end:
            if cessation is None and sga_month:
                cessation = m
                if strict and cessation > epe_end - 2:
                    raise Reject("grace period runs past the extended period")
            if cessation is not None and m <= cessation + 2:
                out[m] = (True, False)
            else:
                out[m] = (not sga_month, False)
        else:
            if sga_month:
                if strict and cessation is None:
                    raise Reject("first SGA after the extended period")
                terminated = True
                out[m] = (False, False)
            else:
                out[m] = (True, False)
    return out


class World:
    def __init__(self):
        self.bens = []

    def add(self, onset, application, earnings, tags, expected=None, blind=False):
        b = dict(onset=onset, application=application, earnings=earnings, tags=tags, expected=expected, blind=blind)
        self.bens.append(b)
        return b


def run(start, end, gross, sub=0, irwe=0):
    """earnings for every month from start to end ("YYYY-MM") inclusive."""
    a, b = mi(*map(int, start.split("-"))), mi(*map(int, end.split("-")))
    return {m: (gross, sub, irwe) for m in range(a, b + 1)}


def months(start, end):
    a, b = mi(*map(int, start.split("-"))), mi(*map(int, end.split("-")))
    return set(range(a, b + 1))


def planted(w):
    # onset Mar 15 2020: full months Apr-Aug are the waiting period; entitled Sep 2020. $1,000 a month from
    # Jun 2021 is above the trial work amount ($940 in 2021, $970 in 2022) but below SGA: 9 service months
    # Jun 2021 - Feb 2022 end the trial work period; every month is payable
    e = run("2021-06", "2025-12", 1000)
    w.add("2020-03-15", "2020-05-10", e, ["waiting-period", "trial-work"],
          {"first": "2020-09", "twm": months("2021-06", "2022-02"), "unpaid": set()})
    # same start, then $1,700 from Jan 2023 (SGA $1,470): cessation Jan 2023, grace Jan-Mar 2023, unpaid Apr-Dec
    # 2023; $1,000 in 2024 is paid; the extended period ends Feb 2025; $1,700 again from Jun 2025 after it ends
    # terminates entitlement from Jun 2025
    e = {**run("2021-06", "2022-12", 1000), **run("2023-01", "2023-12", 1700), **run("2024-01", "2025-05", 1000),
         **run("2025-06", "2025-12", 1700)}
    w.add("2020-03-15", "2020-05-10", e, ["cessation", "grace", "extended-period", "termination"],
          {"first": "2020-09", "twm": months("2021-06", "2022-02"),
           "unpaid": months("2023-04", "2023-12") | months("2025-06", "2025-12")})
    # onset on the first of the month: Mar 2020 is a full month, waiting period Mar-Jul, entitled Aug 2020
    w.add("2020-03-01", "2020-04-02", {}, ["waiting-period", "boundary"],
          {"first": "2020-08", "twm": set(), "unpaid": set()})
    # impairment-related work expenses: $1,700 gross less $300 = $1,400, under SGA ($1,470 in 2023): paid
    e = {**run("2021-06", "2022-12", 1000), **run("2023-01", "2023-12", 1700, irwe=300)}
    w.add("2020-03-15", "2020-05-10", e, ["countable-earnings", "irwe"],
          {"first": "2020-09", "twm": months("2021-06", "2022-02"), "unpaid": set()})
    # employer subsidy: $1,900 gross less $400 = $1,500, under SGA in 2024 ($1,550): paid
    e = {**run("2021-06", "2022-12", 1000), **run("2024-01", "2024-12", 1900, sub=400)}
    w.add("2020-03-15", "2020-05-10", e, ["countable-earnings", "subsidy"],
          {"first": "2020-09", "twm": months("2021-06", "2022-02"), "unpaid": set()})
    # exactly the SGA amount is not SGA ($1,620 in 2025); exactly the trial work amount is not a service month
    e = {**run("2021-06", "2022-12", 1000), **run("2025-01", "2025-12", 1620)}
    w.add("2020-03-15", "2020-05-10", e, ["boundary", "cessation"],
          {"first": "2020-09", "twm": months("2021-06", "2022-02"), "unpaid": set()})
    e = {**run("2022-03", "2022-12", 970), **run("2023-01", "2023-12", 1050)}
    w.add("2020-11-20", "2021-01-05", e, ["boundary", "trial-work"], {"first": "2021-05", "twm": set(), "unpaid": set()})
    # statutorily blind: $2,000 in 2024 is under the blind SGA amount ($2,590) though above the ordinary one
    e = {**run("2021-06", "2022-12", 1000), **run("2024-01", "2024-12", 2000)}
    w.add("2020-03-15", "2020-05-10", e, ["blind", "cessation"],
          {"first": "2020-09", "twm": months("2021-06", "2022-02"), "unpaid": set()}, blind=True)
    # rolling 60 months: 5 service months Aug-Dec 2019 and 4 in Sep-Dec 2024 are not 9 in any 60 months; with 5
    # more in Mar-Jul 2025 the window Aug 2020 - Jul 2025 holds 9: the trial work period ends Jul 2025
    e = {**run("2019-08", "2019-12", 900), **run("2024-09", "2024-12", 1200), **run("2025-03", "2025-07", 1200)}
    w.add("2018-07-03", "2018-09-04", e, ["rolling-window", "trial-work"],
          {"first": "2019-01", "twm": months("2019-08", "2019-12") | months("2024-09", "2024-12")
           | months("2025-03", "2025-07"), "unpaid": set()})
    # trial work cannot begin before the month of filing: onset Jan 20 2020, filed Sep 15 2021, entitled from Sep
    # 2020 (12 months back); $1,000 from Feb 2021 counts only from Sep 2021: 9th service month May 2022
    e = run("2021-02", "2025-12", 1000)
    w.add("2020-01-20", "2021-09-15", e, ["filing-month", "retroactivity", "trial-work"],
          {"first": "2020-09", "twm": months("2021-09", "2022-05"), "unpaid": set()})
    # retroactivity: onset Jun 10 2019, filed Nov 2021: waiting period Jul-Nov 2019, but benefits reach back only
    # to Nov 2020
    w.add("2019-06-10", "2021-11-08", {}, ["retroactivity"], {"first": "2020-11", "twm": set(), "unpaid": set()})
    # SGA during the trial work period does not stop payment; the first SGA month after it does (with grace):
    # $2,000 Jun 2021 - Feb 2022 (9 service months), then $2,000 on: cessation Mar 2022, grace Mar-May, unpaid
    # Jun 2022 - Feb 2025 (extended period ends Feb 2025) and terminated from Mar 2025
    e = run("2021-06", "2025-12", 2000)
    w.add("2020-03-15", "2020-05-10", e, ["cessation", "grace", "termination"],
          {"first": "2020-09", "twm": months("2021-06", "2022-02"), "unpaid": months("2022-06", "2025-12")})
    # the first SGA month after the extended period (Mar 2025, the month after it ends in Feb 2025) terminates
    # entitlement, so the later $1,000 months stay unpaid
    e = {**run("2021-06", "2022-12", 1000), **run("2023-01", "2023-12", 1700), **run("2024-01", "2025-02", 1000),
         **run("2025-03", "2025-03", 1700), **run("2025-04", "2025-12", 1000)}
    w.add("2020-03-15", "2020-05-10", e, ["extended-period", "termination", "boundary"],
          {"first": "2020-09", "twm": months("2021-06", "2022-02"),
           "unpaid": months("2023-04", "2023-12") | months("2025-03", "2025-12")})
    # exactly 60 months apart: Aug 2019 and Jan - Aug 2024 are 9 service months, but Aug 2019 is not within the 60
    # consecutive months ending Aug 2024 (Sep 2019 - Aug 2024), so only 8 count; Sep 2024 is the 9th of Jan - Sep 2024
    e = {**run("2019-08", "2019-08", 900), **run("2024-01", "2024-09", 1200)}
    w.add("2018-07-03", "2018-09-04", e, ["rolling-window", "trial-work", "boundary"],
          {"first": "2019-01", "twm": months("2019-08", "2019-08") | months("2024-01", "2024-09"), "unpaid": set()})
    # trial work months use gross wages: $1,100 with $200 of impairment-related work expenses in 2022 is a service
    # month (over $970) although only $900 counts toward SGA. Onset Jan 10 2021, entitled Jul 2021; Feb - Oct 2022
    # are the 9 service months; every month is payable
    e = run("2022-02", "2025-12", 1100, irwe=200)
    w.add("2021-01-10", "2021-03-02", e, ["trial-work", "irwe", "countable-earnings"],
          {"first": "2021-07", "twm": months("2022-02", "2022-10"), "unpaid": set()})


def sparse_or_returner(profile):
    """Long histories: scattered trial work bursts over more than 60 months, or a quick trial work period, work
    at SGA in the extended period, and a return to SGA after it ends."""
    onset_m = mi(2018, 8) + rng.randrange(0, 14)
    earn = {}
    if profile == "sparse":
        m = onset_m + 12 + rng.randrange(0, 6)
        while m <= mi(*END):
            for k in range(rng.choice([1, 1, 2, 3])):
                if m + k <= mi(*END):
                    ta = AMOUNTS[ym(m + k)[0]][0]
                    earn[m + k] = (ta + rng.choice([1, 40, 120]), 0, 0)
            m += rng.choice([6, 9, 12, 14, 18, 24])
    else:
        m = onset_m + 12 + rng.randrange(0, 4)
        for k in range(9):
            earn[m + k] = (AMOUNTS[ym(m + k)[0]][0] + 100, 0, 0)
        m += 9 + rng.choice([0, 2, 5])
        for k in range(rng.choice([2, 4, 8])):
            earn[m + k] = (AMOUNTS[ym(m + k)[0]][1] + rng.choice([1, 60, 300]), 0, 0)
        m += rng.choice([6, 10]) + 8
        while m <= mi(*END):
            y = ym(m)[0]
            late = m > onset_m + 12 + 9 + 36 + rng.choice([2, 6, 10])
            earn[m] = ((AMOUNTS[y][1] + rng.choice([-1, 0, 1, 50])) if late and rng.random() < 0.5
                       else rng.choice([400, AMOUNTS[y][0] + 30]), 0, 0)
            m += 1
    return onset_m, earn


def filler(w):
    profile = rng.choice(["mixed"] * 3 + ["sparse", "returner"])
    onset_m = mi(2018, 8) + rng.randrange(0, 58)
    if profile != "mixed":
        onset_m, pre = sparse_or_returner(profile)
    onset_d = rng.choice([1, 1, 3, 10, 15, 22, 28])
    app_m = onset_m + rng.choice([0, 1, 2, 4, 8, 13, 17, 20, 26] if profile == "mixed" else [0, 1, 2, 3])
    blind = rng.random() < 0.15
    earn = {} if profile == "mixed" else pre
    m = onset_m + 12 + rng.choice([0, 2, 6, 12, 20])
    end = mi(*END)
    while m <= end and profile == "mixed":
        y = ym(m)[0]
        twp_amt, sga, sga_b = AMOUNTS[y]
        limit = sga_b if blind else sga
        kind = rng.choice(["off", "low", "near_twp", "twp", "near_sga", "sga", "sga", "irwe", "subsidy", "twp_net"])
        span = rng.choice([1, 2, 3, 4, 6, 9, 12])
        for k in range(span):
            mm = m + k
            if mm > end:
                break
            ta, sg, sb = AMOUNTS[ym(mm)[0]]
            lim = sb if blind else sg
            if kind == "off":
                continue
            if kind == "low":
                earn[mm] = (rng.choice([200, 450, 700]), 0, 0)
            elif kind == "near_twp":
                earn[mm] = (ta + rng.choice([-10, 0, 0, 1, 10]), 0, 0)
            elif kind == "twp":
                earn[mm] = (rng.choice([ta + 50, (ta + lim) // 2]), 0, 0)
            elif kind == "near_sga":
                earn[mm] = (lim + rng.choice([-20, -1, 0, 1, 20]), 0, 0)
            elif kind == "sga":
                earn[mm] = (lim + rng.choice([100, 400, 900]), 0, 0)
            elif kind == "twp_net":                       # gross over the trial work amount, net under it
                earn[mm] = (ta + rng.choice([20, 60, 120]), 0, rng.choice([80, 150, 250]))
            elif kind == "irwe":
                g = lim + rng.choice([50, 150, 300])
                earn[mm] = (g, 0, rng.choice([40, 100, 200, 350]))
            else:
                g = lim + rng.choice([50, 150, 300])
                earn[mm] = (g, rng.choice([40, 100, 200, 350]), 0)
        m += span + rng.choice([0, 0, 1, 3, 8, 20])
    b = dict(onset=f"{ym(onset_m)[0]:04d}-{ym(onset_m)[1]:02d}-{onset_d:02d}",
             application=f"{ym(app_m)[0]:04d}-{ym(app_m)[1]:02d}-{rng.randint(1, 28):02d}", earnings=earn, blind=blind)
    if app_m > end - 6:
        return False
    try:
        sim(b)
    except Reject:
        return False
    w.add(b["onset"], b["application"], earn, ["filler"], None, blind)
    return True


def main():
    w = World()
    planted(w)
    for b in w.bens:
        got = sim(b)
        first = min(got)
        want = b["expected"]
        assert mstr(first) == want["first"], (b["tags"], mstr(first), want["first"])
        assert {m for m, v in got.items() if v[1]} == want["twm"], (b["tags"], sorted(mstr(m) for m, v in got.items() if v[1]))
        assert {m for m, v in got.items() if not v[0]} == want["unpaid"], (b["tags"], sorted(mstr(m) for m, v in got.items() if not v[0]))
    n_planted = len(w.bens)
    rejected = 0
    while len(w.bens) < n_planted + 80:
        if not filler(w):
            rejected += 1
    rng.shuffle(w.bens)
    bens, earnings, golden, tags = [], [], {}, {}
    for n, b in enumerate(w.bens, 1):
        bid = f"D{n:03d}"
        bens.append({"beneficiary_id": bid, "name": rng.choice(NAMES), "disability_onset_date": b["onset"],
                     "application_date": b["application"], "statutorily_blind": b["blind"]})
        for m in sorted(b["earnings"]):
            g, s, i = b["earnings"][m]
            earnings.append({"beneficiary_id": bid, "month": mstr(m), "gross_wages": g, "employer_subsidy": s,
                             "impairment_related_work_expenses": i})
        tags[bid] = b["tags"]
        if b["expected"] is not None:
            got = sim(b)
            golden[bid] = [[mstr(m), "yes" if got[m][0] else "no", "yes" if got[m][1] else "no"] for m in sorted(got)]
    ENV.mkdir(parents=True, exist_ok=True)
    for old in ENV.iterdir():
        old.unlink()
    dump = lambda n, o: (ENV / n).write_text(json.dumps(o, indent=1) + "\n")  # noqa: E731
    dump("beneficiaries.json", bens)
    dump("earnings.json", earnings)
    dump("annual_amounts.json", {"source": "Social Security Administration, annual SGA and trial work period amounts",
                                 "unit": "dollars per month",
                                 "by_year": {str(y): {"trial_work_period_service_month": a[0],
                                                      "substantial_gainful_activity_non_blind": a[1],
                                                      "substantial_gainful_activity_blind": a[2]}
                                             for y, a in AMOUNTS.items()}})
    if TST.exists():
        shutil.rmtree(TST)
    shutil.copytree(ENV, TST)
    (ROOT / "tests" / "case_tags.json").write_text(json.dumps(tags, indent=1, sort_keys=True) + "\n")
    (ROOT / "tests" / "golden.json").write_text(json.dumps(golden, indent=1, sort_keys=True) + "\n")
    rows = sum(len(sim(b)) for b in w.bens)
    print(len(bens), "beneficiaries,", len(earnings), "earnings months,", rows, "output rows,", len(golden),
          "hand-worked beneficiaries,", rejected, "rejected")


if __name__ == "__main__":
    main()
