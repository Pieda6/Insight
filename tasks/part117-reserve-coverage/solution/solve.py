#!/usr/bin/env python3
"""Reference solution: 14 CFR Part 117 legality of short-call reserve call-outs,
then an exact maximum-coverage / minimum-cost assignment of reserves to open trips.

All arithmetic is done in integer UTC minutes. Local times in the input files are
interpreted in the IANA zone of the station they are attached to.
"""
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

DATA = Path("/app/data")
OUT = Path("/app/output")
FMT = "%Y-%m-%d %H:%M"
HOUR = 60

# Table B (unaugmented FDP limit, hours) by acclimated start time and segment count 1..7+.
TABLE_B = [
    (0 * HOUR, 4 * HOUR, [9, 9, 9, 9, 9, 9, 9]),
    (4 * HOUR, 5 * HOUR, [10, 10, 10, 10, 9, 9, 9]),
    (5 * HOUR, 6 * HOUR, [12, 12, 12, 12, 11.5, 11, 10.5]),
    (6 * HOUR, 7 * HOUR, [13, 13, 12, 12, 11.5, 11, 10.5]),
    (7 * HOUR, 12 * HOUR, [14, 14, 13, 13, 12.5, 12, 11.5]),
    (12 * HOUR, 13 * HOUR, [13, 13, 13, 13, 12.5, 12, 11.5]),
    (13 * HOUR, 17 * HOUR, [12, 12, 12, 12, 11.5, 11, 10.5]),
    (17 * HOUR, 22 * HOUR, [12, 12, 11, 11, 10, 9, 9]),
    (22 * HOUR, 23 * HOUR, [11, 11, 10, 10, 9, 9, 9]),
    (23 * HOUR, 24 * HOUR, [10, 10, 10, 9, 9, 9, 9]),
]


def read_csv(name):
    with open(DATA / name, newline="") as f:
        return list(csv.DictReader(f))


class Clock:
    def __init__(self, stations):
        self.tz = {s["station"]: ZoneInfo(s["tz"]) for s in stations}

    def utc(self, local, station):
        dt = datetime.strptime(local, FMT).replace(tzinfo=self.tz[station])
        return int(dt.timestamp()) // 60

    def _local(self, minute, station):
        return datetime.fromtimestamp(minute * 60, timezone.utc).astimezone(self.tz[station])

    def offset(self, minute, station):
        return int(self._local(minute, station).utcoffset().total_seconds()) // 60

    def minute_of_day(self, minute, station):
        t = self._local(minute, station)
        return t.hour * 60 + t.minute


def merge(intervals):
    out = []
    for a, b in sorted(intervals):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def overlap(a, b, lo, hi):
    return max(0, min(b, hi) - max(a, lo))


def free_gaps(duties, lo, hi):
    """Duty-free intervals inside [lo, hi]."""
    gaps, cur = [], lo
    for a, b in merge([(max(a, lo), min(b, hi)) for a, b in duties if b > lo and a < hi]):
        if a > cur:
            gaps.append((cur, a))
        cur = max(cur, b)
    if cur < hi:
        gaps.append((cur, hi))
    return gaps


def longest_free(duties, lo, hi):
    return max((b - a for a, b in free_gaps(duties, lo, hi)), default=0)


def table_b(minute_of_day, segments):
    for lo, hi, row in TABLE_B:
        if lo <= minute_of_day < hi:
            return int(round(row[min(segments, 7) - 1] * HOUR))
    raise ValueError(minute_of_day)


class Pilot:
    def __init__(self, row, clock):
        self.id = row["pilot_id"]
        self.seat = row["seat"]
        self.base = row["base"]
        self.equipment = row["equipment"]
        self.cost = int(row["callout_cost"])
        self.rap_start = clock.utc(row["rap_start_local"], self.base)
        self.rap_end = clock.utc(row["rap_end_local"], self.base)
        self.duties = []  # (report, release, type)
        self.legs = []  # (out, in, dep, arr)


def load():
    clock = Clock(read_csv("stations.csv"))
    pilots = {r["pilot_id"]: Pilot(r, clock) for r in read_csv("pilots.csv")}
    duty_owner = {}
    for d in read_csv("duties.csv"):
        p = pilots[d["pilot_id"]]
        duty_owner[d["duty_id"]] = p
        p.duties.append((clock.utc(d["report_local"], d["report_station"]),
                         clock.utc(d["release_local"], d["release_station"]),
                         d["duty_type"]))
    for leg in read_csv("legs.csv"):
        duty_owner[leg["duty_id"]].legs.append((clock.utc(leg["out_local"], leg["dep"]),
                                                clock.utc(leg["in_local"], leg["arr"]),
                                                leg["dep"], leg["arr"]))
    for p in pilots.values():
        p.duties.sort()
        p.legs.sort()
    trips = {}
    for t in read_csv("trips.csv"):
        trips[t["trip_id"]] = {
            "id": t["trip_id"], "base": t["base"], "seat": t["seat"],
            "equipment": t["equipment"],
            "report": clock.utc(t["report_local"], t["base"]),
            "release": clock.utc(t["release_local"], t["base"]),
            "legs": [],
        }
    for leg in read_csv("trip_legs.csv"):
        trips[leg["trip_id"]]["legs"].append((clock.utc(leg["out_local"], leg["dep"]),
                                              clock.utc(leg["in_local"], leg["arr"])))
    return clock, pilots, trips


def acclimatization(clock, pilot, when, duty_intervals):
    """Return (acclimated, reference_station) at `when`.

    The pilot starts the history acclimated at base. Arriving at a station whose UTC
    offset differs from the reference station's by more than 4 hours starts a stay in a
    new theater (anchored at that station). The pilot becomes acclimated to the new
    theater after 72 hours there, or after 36 consecutive duty-free hours that begin
    after arriving there, whichever comes first.
    """
    ref, away = pilot.base, None

    def acclimated_at(anchor_time, limit):
        best = anchor_time + 72 * HOUR
        for a, b in free_gaps(duty_intervals, anchor_time, limit):
            if b - a >= 36 * HOUR:
                best = min(best, a + 36 * HOUR)
                break
        return best if best <= limit else None

    def within(st_a, st_b, t):
        return abs(clock.offset(t, st_a) - clock.offset(t, st_b)) <= 4 * HOUR

    for out, inn, _dep, arr in pilot.legs:
        if inn > when:
            break
        if away and acclimated_at(away[1], out) is not None:
            ref, away = away[0], None
        if within(arr, ref, inn):
            away = None
        elif away and within(arr, away[0], inn):
            pass
        else:
            away = (arr, inn)
    if away and acclimated_at(away[1], when) is not None:
        ref, away = away[0], None
    return away is None, ref


def legality(clock, pilot, trip):
    if (pilot.base, pilot.seat, pilot.equipment) != (trip["base"], trip["seat"], trip["equipment"]):
        return False
    report, release = trip["report"], trip["release"]
    if not pilot.rap_start <= report <= pilot.rap_end:
        return False
    history = [(a, b) for a, b, _ in pilot.duties]
    # 117.25(e): 10 consecutive hours of rest immediately before the reserve period.
    last_release = max((b for a, b in history if b <= pilot.rap_start), default=None)
    if last_release is not None and pilot.rap_start - last_release < 10 * HOUR:
        return False
    # 117.25(b): 30 consecutive duty-free hours in the 168 hours before reserve and before the FDP.
    if longest_free(history, pilot.rap_start - 168 * HOUR, pilot.rap_start) < 30 * HOUR:
        return False
    with_rap = history + [(pilot.rap_start, report)]
    if longest_free(with_rap, report - 168 * HOUR, report) < 30 * HOUR:
        return False
    # Acclimatization drives which local clock Table A / Table B are read on.
    acclimated, ref = acclimatization(clock, pilot, report, with_rap)
    station = trip["base"] if acclimated else ref
    mod = clock.minute_of_day(report, station)
    fdp_limit = table_b(mod, len(trip["legs"])) - (0 if acclimated else 30)
    fdp = release - report
    if fdp > fdp_limit:
        return False
    # 117.11 Table A.
    flight = sum(b - a for a, b in trip["legs"])
    if flight > (9 if 5 * HOUR <= mod < 20 * HOUR else 8) * HOUR:
        return False
    # 117.21(c)(3): reserve availability period plus FDP.
    if release - pilot.rap_start > min(16 * HOUR, fdp_limit + 4 * HOUR):
        return False
    # 117.23: cumulative limits over windows ending at the end of the new FDP.
    fdps = [(a, b) for a, b, k in pilot.duties if k == "FDP"]
    if sum(overlap(a, b, release - 168 * HOUR, release) for a, b in fdps) + fdp > 60 * HOUR:
        return False
    if sum(overlap(a, b, release - 672 * HOUR, release) for a, b in fdps) + fdp > 190 * HOUR:
        return False
    hist_flight = sum(overlap(a, b, release - 672 * HOUR, release) for a, b, _, _ in pilot.legs)
    if hist_flight + flight > 100 * HOUR:
        return False
    return True


def assign(pilots, trips, legal):
    pairs = sorted(legal)
    if not pairs:
        return []
    n = len(pairs)
    pids = sorted({p for p, _ in pairs})
    tids = sorted({t for _, t in pairs})
    rows = []
    for key, idx in ((pids, 0), (tids, 1)):
        for k in key:
            rows.append([1 if pr[idx] == k else 0 for pr in pairs])
    A = np.array(rows)
    one = LinearConstraint(A, 0, 1)
    integ = np.ones(n)
    bounds = Bounds(0, 1)
    first = milp(-np.ones(n), constraints=[one], integrality=integ, bounds=bounds)
    best = int(round(-first.fun))
    cost = np.array([pilots[p].cost for p, _ in pairs], dtype=float)
    second = milp(cost, constraints=[one, LinearConstraint(np.ones((1, n)), best, best)],
                  integrality=integ, bounds=bounds)
    return [pairs[i] for i in range(n) if second.x[i] > 0.5]


def main():
    clock, pilots, trips = load()
    legal = set()
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "legality.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["pilot_id", "trip_id", "legal"])
        for pid in sorted(pilots):
            for tid in sorted(trips):
                ok = legality(clock, pilots[pid], trips[tid])
                if ok:
                    legal.add((pid, tid))
                w.writerow([pid, tid, "true" if ok else "false"])
    chosen = assign(pilots, trips, legal)
    result = {
        "assignments": [{"trip_id": t, "pilot_id": p} for p, t in sorted(chosen, key=lambda x: x[1])],
        "trips_covered": len(chosen),
        "total_callout_cost": sum(pilots[p].cost for p, _ in chosen),
    }
    (OUT / "assignment.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
