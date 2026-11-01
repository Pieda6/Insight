#!/usr/bin/env python3
"""Reference solution for kdigo-aki-staging.

KDIGO 2012 acute kidney injury (Kidney Int Suppl 2012;2:1-138), Recommendations 2.1.1 and 2.1.2 (Table 2). For each
admission: creatinine criteria at every result (1.5, 2.0 and 3.0 times baseline; a rise of 0.3 mg/dl within 48 hours;
a rise to 4.0 mg/dl or more), initiation of renal replacement therapy, and the urine output criteria (below 0.5
ml/kg/h for 6 and 12 hours, below 0.3 ml/kg/h for 24 hours, anuria for 12 hours) judged over every period of that
length within the charted record. The admission's stage is the highest any criterion gives.
"""
import csv
import datetime as dt
import json
from pathlib import Path

DATA = Path("/app/data")
OUT = Path("/app/output")
UMOL_PER_MG = 88.4


def nth_sunday(year, month, n):
    first = dt.date(year, month, 1)
    return first + dt.timedelta(days=(6 - first.weekday()) % 7 + 7 * (n - 1))


def minutes(text):
    wall = dt.datetime.strptime(text.strip(), "%Y-%m-%d %H:%M")
    start = dt.datetime.combine(nth_sunday(wall.year, 3, 2), dt.time(2, 0))
    end = dt.datetime.combine(nth_sunday(wall.year, 11, 1), dt.time(1, 0))
    offset_h = 4 if start <= wall < end else 5
    return (wall - dt.datetime(2000, 1, 1)).total_seconds() / 60.0 + 60 * offset_h


def local(m):
    m = round(m)
    for off in (4, 5):
        txt = (dt.datetime(2000, 1, 1) + dt.timedelta(minutes=m - 60 * off)).strftime("%Y-%m-%d %H:%M")
        if minutes(txt) == m:
            return txt
    return (dt.datetime(2000, 1, 1) + dt.timedelta(minutes=m - 300)).strftime("%Y-%m-%d %H:%M")


def read_csv(name):
    with open(DATA / name, newline="") as fh:
        return list(csv.DictReader(fh))


def first_low(knots, span, limit, zero):
    """Earliest end x of a period (x - span, x] inside the record whose volume is below limit (or zero)."""
    ts = [t for t, _ in knots]

    def vol(x):
        for (t0, v0), (t1, v1) in zip(knots, knots[1:]):
            if x <= t1:
                return v0 + (v1 - v0) * (x - t0) / (t1 - t0) if x > t0 else v0
        return knots[-1][1]
    lo, hi = ts[0] + span, ts[-1]
    if lo > hi:
        return None
    pts = sorted({lo, hi} | {t for t in ts if lo < t < hi} | {t + span for t in ts if lo < t + span < hi})
    prev = None
    for x in pts:
        g = vol(x) - vol(x - span)
        if zero:
            if g <= 1e-9:
                return x
        elif g < limit:
            if prev is None:
                return x
            px, pg = prev
            return px + (pg - limit) / (pg - g) * (x - px)     # g is linear between consecutive points
        prev = (x, g)
    return None


def main():
    patients = json.loads((DATA / "patients.json").read_text())
    groups = {}
    for name in ("creatinine.csv", "urine.csv", "rrt.csv"):
        for r in read_csv(name):
            groups.setdefault((name, r["patient_id"]), []).append(r)

    rows = []
    for p in patients:
        pid = p["patient_id"]
        baseline = float(p["baseline_creatinine_mg_dl"])
        reports = {}
        for r in groups.get(("creatinine.csv", pid), []):      # a corrected result replaces the original
            if r["accession"] not in reports or r["status"] == "corrected":
                reports[r["accession"]] = r
        results = []
        for r in reports.values():
            try:
                x = float(r["result"])
            except ValueError:
                continue                                       # rejected or cancelled specimen
            results.append((minutes(r["collected"]), x / UMOL_PER_MG if r["units"] == "umol/L" else x))
        results.sort()
        events = []
        for i, (t, c) in enumerate(results):
            ratio = c / baseline
            rise = any(t - t0 <= 48 * 60 and c - c0 >= 0.3 for t0, c0 in results[:i])
            s = 3 if ratio >= 3.0 else 2 if ratio >= 2.0 else 1 if (ratio >= 1.5 or rise) else 0
            if c >= 4.0 and (rise or ratio >= 1.5):
                s = 3
            if s:
                events.append((t, s))
        for r in groups.get(("rrt.csv", pid), []):
            events.append((minutes(r["started"]), 3))
        w = float(p["weight_kg"])
        knots, total = [(minutes(p["admitted"]), 0.0)], 0.0
        for r in sorted(groups.get(("urine.csv", pid), []), key=lambda r: minutes(r["charted"])):
            total += float(r["volume_ml"])
            knots.append((minutes(r["charted"]), total))
        for hours, rate, s, zero in ((6, 0.5, 1, False), (12, 0.5, 2, False), (24, 0.3, 3, False), (12, 0.0, 3, True)):
            x = first_low(knots, hours * 60, rate * w * hours, zero)
            if x is not None:
                events.append((x, s))
        if events:
            top = max(s for _, s in events)
            onset = min(t for t, _ in events)
            reached = min(t for t, s in events if s == top)
            rows.append([pid, top, local(onset), local(reached)])
        else:
            rows.append([pid, 0, "none", "none"])

    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "aki_staging.csv", "w", newline="") as fh:
        wr = csv.writer(fh, lineterminator="\n")
        wr.writerow(["patient_id", "max_stage", "aki_onset", "stage_reached"])
        wr.writerows(rows)


if __name__ == "__main__":
    main()
