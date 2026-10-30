#!/usr/bin/env python3
"""Reference solution for vancomycin-hemodialysis-monitoring.

Vancomycin dosing at each hemodialysis session by predialysis-concentration monitoring, following the 2020
ASHP/IDSA/PIDS/SIDP guideline (Recommendations 13 and 14; sampling rule on page 846; loading cap on page 845) and the
unit's protocol in the instruction. Sessions are processed in time order per patient, carrying the current
maintenance dose from one session to the next.
"""
import csv
import datetime as dt
import math
from pathlib import Path

DATA = Path("/app/data")
OUT = Path("/app/output")
MG_PER_UMOL = 1.4493                 # vancomycin 1449.3 g/mol
TARGET, LOW, HIGH, HOLD = 17.5, 15.0, 20.0, 25.0
LOADING = {("after_dialysis", "low"): 25.0, ("after_dialysis", "high"): 25.0,
           ("intradialytic", "low"): 30.0, ("intradialytic", "high"): 35.0}
MAINTENANCE = {("after_dialysis", "low"): 7.5, ("after_dialysis", "high"): 10.0,
               ("intradialytic", "low"): 8.75, ("intradialytic", "high"): 12.5}     # midpoints of 7.5-10, 10-15


def nth_sunday(year, month, n):
    first = dt.date(year, month, 1)
    return first + dt.timedelta(days=(6 - first.weekday()) % 7 + 7 * (n - 1))


def minutes(text):
    """Minutes on a continuous clock from a New York local time."""
    wall = dt.datetime.strptime(text.strip(), "%Y-%m-%d %H:%M")
    start = dt.datetime.combine(nth_sunday(wall.year, 3, 2), dt.time(2, 0))
    end = dt.datetime.combine(nth_sunday(wall.year, 11, 1), dt.time(1, 0))
    offset_h = 4 if start <= wall < end else 5
    return (wall - dt.datetime(2000, 1, 1)).total_seconds() / 60.0 + 60 * offset_h


def to_250(x):
    return int(math.floor(x / 250.0 + 0.5) * 250)


def read_csv(name):
    with open(DATA / name, newline="") as fh:
        return list(csv.DictReader(fh))


def main():
    sessions, levels = {}, {}
    for s in read_csv("sessions.csv"):
        sessions.setdefault(s["patient_id"], []).append(s)
    for r in read_csv("levels.csv"):
        levels.setdefault(r["patient_id"], []).append(r)

    out = []
    for pid in sorted(sessions):
        ss = sorted(sessions[pid], key=lambda s: minutes(s["start"]))
        reports = {}
        for r in levels.get(pid, []):                     # a corrected result replaces the original
            if r["accession"] not in reports or r["status"] == "corrected":
                reports[r["accession"]] = r
        draws = []
        for r in reports.values():
            try:
                x = float(r["result"])
            except ValueError:
                continue                                   # rejected, cancelled or below the reporting limit
            draws.append((minutes(r["collected"]), x * (MG_PER_UMOL if r["units"] == "umol/L" else 1.0)))
        spans = [(minutes(s["start"]), minutes(s["stop"])) for s in ss]
        current = None
        for k, s in enumerate(ss):
            start = spans[k][0]
            ok = [(t, x) for t, x in draws if start - 120 <= t < start
                  and not any(a <= t < b + 120 for a, b in spans[:k])]
            level = max(ok)[1] if ok else None
            if level is None:
                status = "none"
            elif level < LOW:
                status = "below"
            elif level > HIGH:
                status = "above"
            else:
                status = "within"
            key = (s["vancomycin_timing"], s["dialyzer"])
            w = float(s["pre_weight_kg"])
            if k == 0:
                dose = to_250(min(w * LOADING[key], 3000.0))
            elif key != (ss[k - 1]["vancomycin_timing"], ss[k - 1]["dialyzer"]):
                current = to_250(w * MAINTENANCE[key])
                dose = current
            else:
                if current is None:
                    current = to_250(w * MAINTENANCE[key])
                if status in ("below", "above"):
                    current = to_250(current * TARGET / level)
                    dose = 0 if level > HOLD else current
                else:
                    dose = current
            out.append([pid, s["session_id"], "" if level is None else f"{level:.1f}", status, dose])

    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "session_doses.csv", "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["patient_id", "session_id", "predialysis_level_mg_l", "status", "dose_mg"])
        w.writerows(out)


if __name__ == "__main__":
    main()
