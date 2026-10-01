"""Verifier-side Part 117 engine.

Written independently of the reference solution: every pilot's history is rasterised
onto a one-minute grid (duty, FDP and block-time masks) and all look-back limits are
read from prefix sums / run lengths on that grid. Inputs come from the verifier's own
copy of the data (/tests/data), never from the agent's /app.
"""
import csv
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
from scipy.optimize import linear_sum_assignment

DATA = Path(__file__).resolve().parent / "data"
FMT = "%Y-%m-%d %H:%M"
GRID0 = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp()) // 60
GRID_LEN = 120 * 24 * 60

# Table B rows: (first minute of day, last minute of day inclusive, limits in minutes for 1..7+ segments)
_B = {
    "0000-0359": (9, 9, 9, 9, 9, 9, 9),
    "0400-0459": (10, 10, 10, 10, 9, 9, 9),
    "0500-0559": (12, 12, 12, 12, 11.5, 11, 10.5),
    "0600-0659": (13, 13, 12, 12, 11.5, 11, 10.5),
    "0700-1159": (14, 14, 13, 13, 12.5, 12, 11.5),
    "1200-1259": (13, 13, 13, 13, 12.5, 12, 11.5),
    "1300-1659": (12, 12, 12, 12, 11.5, 11, 10.5),
    "1700-2159": (12, 12, 11, 11, 10, 9, 9),
    "2200-2259": (11, 11, 10, 10, 9, 9, 9),
    "2300-2359": (10, 10, 10, 9, 9, 9, 9),
}
TABLE_B = []
for span, hours in _B.items():
    a, b = span.split("-")
    TABLE_B.append((int(a[:2]) * 60 + int(a[2:]), int(b[:2]) * 60 + int(b[2:]), [int(h * 60) for h in hours]))


def _rows(name):
    with open(DATA / name, newline="") as f:
        return list(csv.DictReader(f))


class Data:
    def __init__(self):
        self.zone = {r["station"]: ZoneInfo(r["tz"]) for r in _rows("stations.csv")}
        self.pilots = {r["pilot_id"]: dict(r) for r in _rows("pilots.csv")}
        for p in self.pilots.values():
            p["rap"] = (self.t(p["rap_start_local"], p["base"]), self.t(p["rap_end_local"], p["base"]))
            p["cost"] = int(p["callout_cost"])
            p["duty"] = np.zeros(GRID_LEN, dtype=np.int8)
            p["fdp"] = np.zeros(GRID_LEN, dtype=np.int8)
            p["block"] = np.zeros(GRID_LEN, dtype=np.int8)
            p["arrivals"] = []
            p["releases"] = []
        owner = {}
        for d in _rows("duties.csv"):
            p = self.pilots[d["pilot_id"]]
            owner[d["duty_id"]] = p
            a = self.t(d["report_local"], d["report_station"]) - GRID0
            b = self.t(d["release_local"], d["release_station"]) - GRID0
            p["duty"][a:b] = 1
            if d["duty_type"] == "FDP":
                p["fdp"][a:b] = 1
            p["releases"].append(b + GRID0)
        for leg in _rows("legs.csv"):
            p = owner[leg["duty_id"]]
            o = self.t(leg["out_local"], leg["dep"])
            i = self.t(leg["in_local"], leg["arr"])
            p["block"][o - GRID0:i - GRID0] = 1
            p["arrivals"].append((i, o, leg["arr"]))
        for p in self.pilots.values():
            p["arrivals"].sort()
        self.trips = {r["trip_id"]: dict(r) for r in _rows("trips.csv")}
        for t in self.trips.values():
            t["rep"] = self.t(t["report_local"], t["base"])
            t["rel"] = self.t(t["release_local"], t["base"])
            t["nseg"] = 0
            t["block"] = 0
        for leg in _rows("trip_legs.csv"):
            t = self.trips[leg["trip_id"]]
            t["nseg"] += 1
            t["block"] += self.t(leg["in_local"], leg["arr"]) - self.t(leg["out_local"], leg["dep"])

    def t(self, s, station):
        return int(datetime.strptime(s, FMT).replace(tzinfo=self.zone[station]).timestamp()) // 60

    def utcoff(self, minute, station):
        return datetime.fromtimestamp(minute * 60, timezone.utc).astimezone(self.zone[station]).utcoffset()

    def clock(self, minute, station):
        lt = datetime.fromtimestamp(minute * 60, timezone.utc).astimezone(self.zone[station])
        return lt.hour * 60 + lt.minute


def _longest_zero_run(mask):
    if not len(mask):
        return 0
    padded = np.concatenate(([1], mask, [1]))
    edges = np.flatnonzero(np.diff(padded != 0))
    # edges alternate: end of a 1-run (start of zeros) / start of next 1-run
    starts, ends = edges[0::2], edges[1::2]
    return int((ends - starts).max()) if len(starts) else 0


def _first_free_run_end(mask, need):
    """Index at which the first run of `need` consecutive zeros completes, or None."""
    run = 0
    for k, v in enumerate(mask):
        run = run + 1 if v == 0 else 0
        if run >= need:
            return k + 1
    return None


def _same_theater(D, s1, s2, minute):
    return abs((D.utcoff(minute, s1) - D.utcoff(minute, s2)).total_seconds()) <= 4 * 3600


def acclimated_reference(D, p, when, duty):
    """(is_acclimated, station whose clock Table B is read on when not acclimated)."""
    home = p["base"]
    anchor = None  # (station, arrival minute) of a theater the pilot is not yet acclimated to
    for arr_min, out_min, st in p["arrivals"]:
        if arr_min > when:
            break
        if anchor is not None and _became_acclimated(anchor[1], out_min, duty):
            home, anchor = anchor[0], None
        if _same_theater(D, st, home, arr_min):
            anchor = None
        elif anchor is None or not _same_theater(D, st, anchor[0], arr_min):
            anchor = (st, arr_min)
    if anchor is not None and _became_acclimated(anchor[1], when, duty):
        home, anchor = anchor[0], None
    return anchor is None, home


def _became_acclimated(since, until, duty):
    if until - since >= 72 * 60:
        return True
    window = duty[since - GRID0:until - GRID0]
    return _first_free_run_end(window, 36 * 60) is not None


def table_b(minute_of_day, nseg):
    for lo, hi, lim in TABLE_B:
        if lo <= minute_of_day <= hi:
            return lim[min(nseg, 7) - 1]
    raise AssertionError(minute_of_day)


def is_legal(D, pid, tid):
    p, t = D.pilots[pid], D.trips[tid]
    if p["base"] != t["base"] or p["seat"] != t["seat"] or p["equipment"] != t["equipment"]:
        return False
    rs, re_ = p["rap"]
    rep, rel = t["rep"], t["rel"]
    if rep < rs or rep > re_:
        return False
    prior = [r for r in p["releases"] if r <= rs]
    if prior and rs - max(prior) < 600:
        return False
    duty = p["duty"].copy()
    if _longest_zero_run(duty[rs - GRID0 - 168 * 60:rs - GRID0]) < 1800:
        return False
    duty[rs - GRID0:rep - GRID0] = 1  # the reserve availability period is duty
    if _longest_zero_run(duty[rep - GRID0 - 168 * 60:rep - GRID0]) < 1800:
        return False
    acc, ref = acclimated_reference(D, p, rep, duty)
    mod = D.clock(rep, t["base"] if acc else ref)
    limit = table_b(mod, t["nseg"]) - (0 if acc else 30)
    fdp = rel - rep
    if fdp > limit:
        return False
    if t["block"] > (540 if 300 <= mod <= 1199 else 480):
        return False
    if rel - rs > min(960, limit + 240):
        return False
    end = rel - GRID0
    if int(p["fdp"][end - 168 * 60:end].sum()) + fdp > 3600:
        return False
    if int(p["fdp"][end - 672 * 60:end].sum()) + fdp > 11400:
        return False
    if int(p["block"][end - 672 * 60:end].sum()) + t["block"] > 6000:
        return False
    return True


def legality_matrix(D):
    return {(p, t): is_legal(D, p, t) for p in D.pilots for t in D.trips}


def optimum(D, legal):
    """(max trips covered, min total call-out cost at that coverage)."""
    pids, tids = sorted(D.pilots), sorted(D.trips)
    big = 1 + sum(p["cost"] for p in D.pilots.values())
    w = np.zeros((len(pids), len(tids)))
    for i, p in enumerate(pids):
        for j, t in enumerate(tids):
            if legal[(p, t)]:
                w[i, j] = big - D.pilots[p]["cost"]
    r, c = linear_sum_assignment(w, maximize=True)
    chosen = [(pids[i], tids[j]) for i, j in zip(r, c) if w[i, j] > 0]
    return len(chosen), sum(D.pilots[p]["cost"] for p, _ in chosen)
