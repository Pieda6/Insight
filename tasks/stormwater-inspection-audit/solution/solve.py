#!/usr/bin/env python3
"""Reference solution for stormwater-inspection-audit (EPA 2022 Construction General Permit, as modified April 8, 2025).

For each site and area, walk the calendar day by day from the area's first logged day to September 30, 2026, keeping
the inspection schedule in force (Parts 4.2, 4.3.1, 4.4.1), the next routine deadline, and the disturbed acreage;
derive storm inspections from the gauge (Part 4.2.2, footnotes 67-69), then the deadlines that come from records:
inspection reports (4.7.1), maintenance and corrective actions (2.1.4, 5.1, 5.2.1, 5.4.1), track-out (2.2.4) and
stabilization (2.2.14, footnotes 38-41). Business days follow Appendix A: days on which construction activities
take place, which here are the days in the construction log.
"""
import bisect
import csv
import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

DATA = Path("/app/data")
OUT = Path("/app/output")
LAST_DAY = date(2026, 9, 30)
CUTOFF = datetime(2026, 9, 30, 23, 59)
ONE = timedelta(days=1)
SENSITIVE_IMPAIRMENTS = {"sedimentation/siltation", "total phosphorus", "total nitrogen"}   # sediment or nutrients
SENSITIVE_TIERS = {"2", "2.5", "3"}


def ts(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M") if s else None


def end_of(d):
    return datetime(d.year, d.month, d.day, 23, 59)


def plus_month(d):
    y, m = divmod(d.year * 12 + d.month, 12)       # month after d
    m += 1
    for day in range(d.day, 27, -1):
        try:
            return date(y, m, day)
        except ValueError:
            pass
    return date(y, m, d.day)


def load(name):
    return json.loads((DATA / name).read_text())


def main():
    sites = load("sites.json")
    by_site = defaultdict(lambda: defaultdict(list))
    for name, key in [("rain_gauge.json", "rain"), ("construction_log.json", "log"),
                      ("stabilization_records.json", "stab"), ("inspections.json", "insp"),
                      ("findings.json", "find"), ("trackout.json", "track")]:
        for rec in load(name):
            by_site[rec["site_id"]][key].append(rec)
    rows = []
    for site in sites:
        rows += audit_site(site, by_site[site["site_id"]])
    rows.sort(key=lambda r: (r[0], r[1], r[3], r[2], r[4]))
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "violations.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["site_id", "area_id", "requirement", "due", "met"])
        w.writerows(rows)


def audit_site(site, rec):
    sid = site["site_id"]
    out = []
    worked = defaultdict(set)
    for e in rec["log"]:
        worked[e["area_id"]].add(date.fromisoformat(e["date"]))
    business = sorted(set().union(*worked.values()))           # Appendix A "business day"

    def business_day_after(d):                                  # first business day strictly after d
        i = bisect.bisect_right(business, d)
        return business[i] if i < len(business) else None

    def business_day_from(d):                                   # first business day on or after d
        i = bisect.bisect_left(business, d)
        return business[i] if i < len(business) else None

    def emit(area, what, due, met):
        if due <= CUTOFF and (met is None or met > due):
            out.append([sid, area, what, due.strftime("%Y-%m-%dT%H:%M"),
                        met.strftime("%Y-%m-%dT%H:%M") if met else "none"])

    waters = {w["water_id"]: w for w in site["receiving_waters"]}

    def is_sensitive(area):                                     # Parts 3.2, 4.3.1, 2.2.14b.iii
        w = waters[area["discharges_to"]]
        return bool({p.lower() for p in w["impaired_for"]} & SENSITIVE_IMPAIRMENTS) or \
            w["antidegradation_tier"] in SENSITIVE_TIERS

    weekly_only = site["inspection_schedule"] == "Part 4.2.1"
    completions = defaultdict(set)
    for s in rec["stab"]:
        if s["completed"]:
            completions[s["area_id"]].add(ts(s["completed"]).date())
    seen_by = defaultdict(list)
    for i in rec["insp"]:
        t = ts(i["completed"])
        for a in i["areas_inspected"]:
            seen_by[a].append(t)
    for a in seen_by:
        seen_by[a].sort()

    # ---- storms from the gauge: first and last day with 0.25 inches or more in each run of wet days
    rain = {date.fromisoformat(r["date"]): round(float(r["rain_inches"]) * 100) for r in rec["rain"]}
    storm_days = []
    run = []
    for d in sorted(rain) + [None]:
        if d is not None and rain[d] >= 1 and run and d - run[-1] == ONE:
            run.append(d)
            continue
        heavy = [x for x in run if rain[x] >= 25]
        if heavy:
            storm_days.append(heavy[0])
            if heavy[-1] != heavy[0]:
                storm_days.append(heavy[-1])
        run = [d] if d is not None and rain[d] >= 1 else []

    # ---- day walk per area: schedule modes, routine deadlines, disturbed acreage
    disturbed = defaultdict(int)                                # hundredths of an acre per day
    regular_on = {}
    for area in site["areas"]:
        aid = area["area_id"]
        if not worked[aid]:
            continue
        acres = round(float(area["acres"]) * 100)
        start = min(worked[aid])
        interval = timedelta(days=7 if weekly_only or is_sensitive(area) else 14)
        mode, stab_day = "regular", None
        latest = start
        due = end_of(start + interval)
        open_due = True
        exposed = False
        d = date(2026, 1, 1)
        regular_on[aid] = set()
        while d <= LAST_DAY:
            if d in worked[aid]:
                exposed = True
            if exposed:
                disturbed[d] += acres
            if d in completions[aid]:
                exposed = False
            if d >= start:
                new = mode
                if d in worked[aid] and stab_day is not None and d > stab_day:
                    new, stab_day = "regular", None
                if d in completions[aid]:
                    new, stab_day = "first", d
                if new == "first" and d == plus_month(stab_day):
                    new = "monthly"
                if new != mode:                                  # schedule change: count from the later day
                    mode = new
                    base = max(latest, d)
                    due = end_of(base + (interval if mode == "regular" else timedelta(days=14)
                                         if mode == "first" else timedelta(0)))
                    if mode == "monthly":
                        due = end_of(plus_month(base))
                    open_due = True
                if mode == "regular":
                    regular_on[aid].add(d)
                for t in seen_by[aid]:
                    if t.date() != d:
                        continue
                    if open_due and t > due:
                        emit(aid, "routine_inspection", due, t)
                    latest = d
                    if mode == "regular":
                        due = end_of(d + interval)
                    elif mode == "first":
                        due = end_of(d + timedelta(days=14))
                    else:
                        due = end_of(plus_month(d))
                    open_due = True
            d += ONE
        if open_due:
            emit(aid, "routine_inspection", due, None)

        # storm inspections: 4.2.2 sites and areas draining to sensitive waters, while on the regular schedule
        if weekly_only and not is_sensitive(area):
            continue
        for day in storm_days:
            if day < start or day not in regular_on[aid]:
                continue
            deadline_day = business_day_from(day + ONE)          # 24 hours, or next business day (fn. 68)
            if deadline_day is None:
                continue
            met = next((t for t in seen_by[aid] if t.date() > day), None)
            emit(aid, "storm_inspection", end_of(deadline_day), met)

    # ---- inspection reports
    for i in rec["insp"]:
        emit(i["areas_inspected"][0], "inspection_report", ts(i["completed"]) + timedelta(hours=24),
             ts(i["report_completed"]))

    # ---- maintenance and corrective actions
    times_fixed = defaultdict(int)
    for f in sorted(rec["find"], key=lambda f: (f["discovered"], f["finding_id"])):
        found = ts(f["discovered"])
        aid = f["area_id"]
        done = ts(f["completed"])
        nbd = business_day_after(found.date())
        if f["needs"] == "routine maintenance":
            times_fixed[(f["control_id"], f["location"], f["fix"])] += 1
            repeat = times_fixed[(f["control_id"], f["location"], f["fix"])] >= 4      # 2.1.4c
            if not repeat:
                if f["infeasibility_documented"]:
                    emit(aid, "routine_maintenance", found + timedelta(days=7), done)
                elif nbd:
                    emit(aid, "routine_maintenance", end_of(nbd), done)
                continue
            if nbd:
                emit(aid, "corrective_action", end_of(nbd), done)                        # 5.2.1b
        else:
            emit(aid, "corrective_action", found + timedelta(days=7), done)              # 5.2.1c
        emit(aid, "ca_log_identified", found + timedelta(hours=24), ts(f["log_entry_identified"]))
        if done:
            emit(aid, "ca_log_completed", done + timedelta(hours=24), ts(f["log_entry_completed"]))
            if f["swppp_change_needed"]:
                emit(aid, "swppp_update", done + timedelta(days=7), ts(f["swppp_updated"]))

    # ---- track-out removal
    for t in rec["track"]:
        happened = ts(t["occurred"])
        day = business_day_from(happened.date())
        if day:
            emit(t["area_id"], "trackout_removal", end_of(day), ts(t["removed"]))

    # ---- stabilization after work stops for 14 days or more, or for good
    over_five = max(disturbed.values(), default=0) > 500
    for area in site["areas"]:
        aid = area["area_id"]
        days = sorted(worked[aid])
        for k, last in enumerate(days):
            nxt = days[k + 1] if k + 1 < len(days) else None
            if nxt is None:
                if area["work_completed_on"] != last.isoformat():
                    continue
            elif (nxt - last).days - 1 < 14:
                continue
            nbd = business_day_after(last)
            if nbd is None:
                continue
            starts = sorted((s for s in rec["stab"] if s["area_id"] == aid and ts(s["initiated"]).date() >= last
                             and (nxt is None or ts(s["initiated"]).date() < nxt)), key=lambda s: s["initiated"])
            first = starts[0] if starts else None
            emit(aid, "stabilization_initiation", end_of(nbd), ts(first["initiated"]) if first else None)
            if first:
                days_allowed = 7 if is_sensitive(area) or over_five else 14
                emit(aid, "stabilization_completion", ts(first["initiated"]) + timedelta(days=days_allowed),
                     ts(first["completed"]))
    return out


if __name__ == "__main__":
    main()
