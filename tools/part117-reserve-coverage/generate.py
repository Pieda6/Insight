#!/usr/bin/env python3
"""Build the synthetic airline data set for the part117-reserve-coverage task.

Not shipped to the agent. Writes environment/data/*.csv and a byte-identical copy in
tests/data/ (the verifier never trusts /app/data). calibrate.py --write adds
tests/trap_pairs.json.

Run:  python tools/part117-reserve-coverage/generate.py
"""
import csv
import random
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2] / "tasks" / "part117-reserve-coverage"
ENV_DATA = ROOT / "environment" / "data"
TEST_DATA = ROOT / "tests" / "data"
FMT = "%Y-%m-%d %H:%M"
H = 60
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

STATIONS = {
    "JFK": "America/New_York", "BOS": "America/New_York", "MIA": "America/New_York",
    "ATL": "America/New_York", "DCA": "America/New_York", "ORD": "America/Chicago", "MSP": "America/Chicago",
    "DEN": "America/Denver", "LAX": "America/Los_Angeles", "SFO": "America/Los_Angeles",
    "CDG": "Europe/Paris", "FRA": "Europe/Berlin", "AMS": "Europe/Amsterdam",
}
BLOCK = {
    ("JFK", "BOS"): 75, ("BOS", "JFK"): 80, ("JFK", "MIA"): 190, ("MIA", "JFK"): 175,
    ("JFK", "ATL"): 150, ("ATL", "JFK"): 135, ("JFK", "ORD"): 155, ("ORD", "JFK"): 130,
    ("JFK", "LAX"): 380, ("LAX", "JFK"): 330, ("JFK", "CDG"): 445, ("CDG", "JFK"): 505,
    ("JFK", "FRA"): 470, ("FRA", "JFK"): 535, ("CDG", "FRA"): 75, ("FRA", "CDG"): 80,
    ("CDG", "AMS"): 80, ("AMS", "CDG"): 80, ("FRA", "AMS"): 70, ("AMS", "FRA"): 70,
    ("ORD", "MSP"): 85, ("MSP", "ORD"): 85, ("ORD", "DEN"): 160, ("DEN", "ORD"): 140,
    ("ORD", "ATL"): 120, ("ATL", "ORD"): 125, ("ORD", "LAX"): 275, ("LAX", "ORD"): 245,
    ("ORD", "SFO"): 285, ("SFO", "ORD"): 260, ("DEN", "LAX"): 150, ("LAX", "DEN"): 135,
    ("JFK", "DCA"): 80, ("DCA", "JFK"): 75, ("BOS", "DCA"): 90, ("DCA", "BOS"): 85,
    ("JFK", "DEN"): 270, ("DEN", "JFK"): 235,
    ("ORD", "BOS"): 140, ("BOS", "ORD"): 160, ("MSP", "DEN"): 120, ("DEN", "MSP"): 115,
}
DOMESTIC = {
    "JFK": [["BOS"], ["DCA"], ["ATL"], ["ORD"], ["MIA"], ["BOS", "JFK", "DCA"]],
    "ORD": [["MSP"], ["DEN"], ["ATL"], ["BOS"], ["MSP", "ORD", "MSP"], ["ATL", "ORD", "MSP"]],
}


def utc(y, mo, d, hh, mm=0):
    return int((datetime(y, mo, d, hh, mm, tzinfo=timezone.utc) - EPOCH).total_seconds()) // 60


def loc(y, mo, d, hh, mm, station):
    dt = datetime(y, mo, d, hh, mm, tzinfo=ZoneInfo(STATIONS[station]))
    return int(dt.timestamp()) // 60


def fmt(minute, station):
    t = datetime.fromtimestamp(minute * 60, timezone.utc).astimezone(ZoneInfo(STATIONS[station]))
    s = t.strftime(FMT)
    back = int(datetime.strptime(s, FMT).replace(tzinfo=ZoneInfo(STATIONS[station])).timestamp()) // 60
    assert back == minute, (s, station)  # no DST-gap / fold local times
    return s


class World:
    def __init__(self):
        self.pilots, self.duties, self.legs = [], [], []
        self.trips, self.trip_legs = [], []
        self.nduty = 0

    def pilot(self, pid, seat, base, eq, cost, rap_start, rap_hours=14):
        self.pilots.append(dict(pilot_id=pid, seat=seat, base=base, equipment=eq,
                                callout_cost=cost, rap_start=rap_start,
                                rap_end=rap_start + rap_hours * H))

    def fdp(self, pid, start, route, turns=None, report_pad=60, release_pad=30):
        """FDP flying `route` (list of stations); first block-out at `start` (UTC minute)."""
        self.nduty += 1
        did = f"D{self.nduty:04d}"
        t = start
        legs = []
        for i, (a, b) in enumerate(zip(route, route[1:])):
            if i:
                t += (turns[i - 1] if turns else 50)
            legs.append((a, b, t, t + BLOCK[(a, b)]))
            t += BLOCK[(a, b)]
        rep, rel = start - report_pad, t + release_pad
        self.duties.append(dict(duty_id=did, pilot_id=pid, duty_type="FDP",
                                report_station=route[0], report=rep,
                                release_station=route[-1], release=rel))
        for n, (a, b, o, i) in enumerate(legs, 1):
            self.legs.append(dict(duty_id=did, leg_no=n, dep=a, arr=b, out=o, inn=i))
        return rep, rel

    def other(self, pid, start, end, station):
        self.nduty += 1
        self.duties.append(dict(duty_id=f"D{self.nduty:04d}", pilot_id=pid, duty_type="OTHER",
                                report_station=station, report=start,
                                release_station=station, release=end))

    def trip(self, tid, base, seat, eq, report, route, fdp_minutes, sit_after=None):
        """Open trip: report at `report`; slack is put into the turn after leg `sit_after`."""
        blocks = [BLOCK[(a, b)] for a, b in zip(route, route[1:])]
        n = len(blocks)
        turns = [50] * (n - 1)
        slack = fdp_minutes - 60 - 30 - sum(blocks) - sum(turns)
        assert slack >= 0, (tid, slack)
        if n > 1:
            turns[(sit_after if sit_after is not None else (n - 1) // 2)] += slack
            pad = 60
        else:
            pad = 60 + slack
        self.trips.append(dict(trip_id=tid, base=base, seat=seat, equipment=eq,
                               report=report, release=report + fdp_minutes))
        t = report + pad
        for k, (a, b) in enumerate(zip(route, route[1:])):
            self.trip_legs.append(dict(trip_id=tid, leg_no=k + 1, dep=a, arr=b, out=t, inn=t + blocks[k]))
            t += blocks[k] + (turns[k] if k < n - 1 else 0)
        assert t + 30 == report + fdp_minutes or n == 1, tid

    def domestic_filler(self, rng, pid, base, start_day, end_utc, rest_days=(), sim_days=()):
        """Base round-trip FDPs on working days between start_day and end_utc."""
        day = start_day
        last_rel = None
        while True:
            y, mo, d = day.year, day.month, day.day
            if day.strftime("%m-%d") in sim_days:
                s = loc(y, mo, d, 8, 0, base)
                self.other(pid, s, s + 8 * H, base)
                last_rel = s + 8 * H
            elif day.strftime("%m-%d") not in rest_days:
                hh = rng.choice([6, 7, 8, 9, 10, 11, 12])
                mm = rng.choice([0, 15, 30, 45])
                route = [base] + rng.choice(DOMESTIC[base]) + [base]
                start = loc(y, mo, d, hh, mm, base)
                if last_rel is not None and start - 60 - last_rel < 12 * H:
                    start = last_rel + 12 * H + 60
                if start + 16 * H > end_utc:
                    break
                _, last_rel = self.fdp(pid, start, route)
            day += timedelta(days=1)
            if loc(day.year, day.month, day.day, 0, 0, base) > end_utc:
                break
        return last_rel


def days_off(rng):
    """Realistic work/off pattern between 02-09 and 03-08 (3-4 days on, 3 off)."""
    off = set()
    d = datetime(2026, 2, 9) + timedelta(days=rng.randint(0, 3))
    while d < datetime(2026, 3, 9):
        d += timedelta(days=3)
        for _ in range(rng.randint(3, 4)):
            off.add(d.strftime("%m-%d"))
            d += timedelta(days=1)
    return off


def q4_plan(lo, hi):
    """Mix of daily round trips whose flight minutes total lies in (lo, hi]."""
    for a in range(12, -1, -1):
        for c in range(10):
            for b in range(10):
                for d in range(4):
                    tot = 520 * a + 300 * b + 415 * c + 170 * d
                    if lo < tot <= hi and a + b + c + d <= 18:
                        return [520] * a + [415] * c + [300] * b + [170] * d
    raise ValueError("no plan")


def build():
    rng = random.Random(117)
    w = World()
    start_day = datetime(2026, 2, 9)
    A321, B737 = "A321", "B737"

    def jfk(h, m=0, d=9):
        return loc(2026, 3, d, h, m, "JFK")

    def ord_(h, m=0, d=9):
        return loc(2026, 3, d, h, m, "ORD")

    end_hist = utc(2026, 3, 9, 4)  # nothing in the history after this

    # ------------------------------------------------------------------ open trips (03-09)
    for seat in ("CA", "FO"):
        s = seat[0]
        w.trip(f"J{s}01", "JFK", seat, A321, jfk(6, 30), ["JFK", "MIA", "JFK"], 13 * H + 15)
        w.trip(f"J{s}02", "JFK", seat, A321, jfk(7, 0), ["JFK", "MIA", "JFK"], 13 * H)
        w.trip(f"J{s}03", "JFK", seat, A321, jfk(13, 0), ["JFK", "BOS", "JFK", "ATL", "JFK"], 11 * H + 30)
        w.trip(f"J{s}04", "JFK", seat, A321, jfk(21, 0), ["JFK", "BOS", "JFK"], 5 * H)
        w.trip(f"J{s}05", "JFK", seat, A321, jfk(20, 15), ["JFK", "DEN", "JFK"], 10 * H + 45)
        w.trip(f"J{s}06", "JFK", seat, A321, jfk(5, 30), ["JFK", "BOS", "JFK", "DCA", "BOS", "JFK"], 11 * H + 45)
        w.trip(f"J{s}07", "JFK", seat, A321, jfk(9, 0), ["JFK", "ATL", "JFK"], 8 * H)
        w.trip(f"J{s}08", "JFK", seat, A321, jfk(15, 30), ["JFK", "ORD", "JFK"], 7 * H + 30)
        w.trip(f"O{s}01", "ORD", seat, B737, ord_(6, 0), ["ORD", "DEN", "ORD"], 9 * H)
        w.trip(f"O{s}02", "ORD", seat, B737, ord_(7, 0), ["ORD", "MSP", "ORD", "ATL", "ORD"], 11 * H)
        w.trip(f"O{s}03", "ORD", seat, B737, ord_(10, 0), ["ORD", "BOS", "ORD"], 8 * H)
        w.trip(f"O{s}04", "ORD", seat, B737, ord_(12, 30), ["ORD", "ATL", "ORD"], 7 * H)
        w.trip(f"O{s}05", "ORD", seat, B737, ord_(14, 0), ["ORD", "MSP", "ORD", "DEN", "ORD"], 12 * H)
        w.trip(f"O{s}06", "ORD", seat, B737, ord_(17, 0), ["ORD", "MSP", "ORD"], 5 * H + 30)
        w.trip(f"O{s}07", "ORD", seat, B737, ord_(8, 15), ["ORD", "DEN", "ORD"], 7 * H + 30)

    # ------------------------------------------------------------------ JFK pilots
    for seat in ("CA", "FO"):
        s = seat[0]
        # P1: 48 h off at CDG -> acclimated to Paris; back at JFK on 03-08 -> not acclimated.
        pid = f"JFK-{s}01"
        w.pilot(pid, seat, "JFK", A321, 340, jfk(13, 0))
        w.domestic_filler(rng, pid, "JFK", start_day, utc(2026, 3, 2, 0), rest_days=days_off(rng))
        w.fdp(pid, jfk(18, 0, 4), ["JFK", "CDG"])
        w.fdp(pid, loc(2026, 3, 7, 11, 0, "CDG"), ["CDG", "FRA", "CDG"], turns=[60])
        w.fdp(pid, loc(2026, 3, 8, 11, 30, "CDG"), ["CDG", "JFK"])

        # P2: 24 h CDG layover only -> never acclimated to Paris, still acclimated at JFK.
        pid = f"JFK-{s}02"
        w.pilot(pid, seat, "JFK", A321, 300, jfk(5, 0))
        w.domestic_filler(rng, pid, "JFK", start_day, utc(2026, 3, 4, 0), rest_days=days_off(rng))
        w.fdp(pid, jfk(19, 0, 6), ["JFK", "CDG"])
        w.fdp(pid, loc(2026, 3, 8, 12, 0, "CDG"), ["CDG", "JFK"])

        # P3: > 72 h in the European theater with short rests -> acclimated there by time.
        pid = f"JFK-{s}03"
        w.pilot(pid, seat, "JFK", A321, 320, jfk(5, 0))
        w.domestic_filler(rng, pid, "JFK", start_day, utc(2026, 3, 1, 0), rest_days=days_off(rng))
        w.fdp(pid, jfk(17, 30, 3), ["JFK", "FRA"])
        w.fdp(pid, loc(2026, 3, 5, 9, 0, "FRA"), ["FRA", "AMS", "FRA"], turns=[60])
        w.fdp(pid, loc(2026, 3, 6, 9, 0, "FRA"), ["FRA", "CDG", "FRA"], turns=[60])
        w.fdp(pid, loc(2026, 3, 7, 9, 0, "FRA"), ["FRA", "AMS", "FRA"], turns=[60])
        w.fdp(pid, loc(2026, 3, 8, 10, 30, "FRA"), ["FRA", "JFK"])

        # P4: Europe trip early in the month, long time home since -> acclimated at JFK.
        pid = f"JFK-{s}04"
        w.pilot(pid, seat, "JFK", A321, 260, jfk(12, 0))
        w.fdp(pid, jfk(18, 0, 10), ["JFK", "CDG"])
        w.fdp(pid, loc(2026, 2, 12, 11, 0, "CDG"), ["CDG", "JFK"])
        w.domestic_filler(rng, pid, "JFK", datetime(2026, 2, 15), end_hist - 20 * H, rest_days=days_off(rng))

        # P5: very early reserve start -> reserve + FDP cap binds.
        pid = f"JFK-{s}05"
        w.pilot(pid, seat, "JFK", A321, 220, jfk(3, 30))
        w.domestic_filler(rng, pid, "JFK", start_day, end_hist - 30 * H, rest_days=days_off(rng))

        # P6, P7: ordinary reserves (morning and evening reserve periods).
        for k, (cost, rs) in enumerate([(200, jfk(4, 30)), (240, jfk(15, 0))], 6):
            pid = f"JFK-{s}0{k}"
            w.pilot(pid, seat, "JFK", A321, cost, rs)
            w.domestic_filler(rng, pid, "JFK", start_day, end_hist - 24 * H, rest_days=days_off(rng))

        # P8: only 9.5 h rest before the reserve period.
        pid = f"JFK-{s}08"
        w.pilot(pid, seat, "JFK", A321, 180, jfk(6, 0))
        w.domestic_filler(rng, pid, "JFK", start_day, utc(2026, 3, 6, 0), rest_days=days_off(rng))
        w.fdp(pid, jfk(10, 0, 8), ["JFK", "MIA", "JFK", "ATL", "JFK"], turns=[50, 240, 50])

    # ------------------------------------------------------------------ ORD pilots
    for seat in ("CA", "FO"):
        s = seat[0]
        # Q1: the only 30 h duty-free block fits the 168 h look-back from the reserve start
        # but slides out of the look-back from a report more than 1 h later.
        pid = f"ORD-{s}01"
        rs = ord_(5, 0)
        w.pilot(pid, seat, "ORD", B737, 210, rs)
        w.domestic_filler(rng, pid, "ORD", start_day, rs - 240 * H, rest_days=days_off(rng))
        w.other(pid, rs - 208 * H, rs - 200 * H, "ORD")
        t, k = rs - 137 * H, 0
        while t + 9 * H <= rs - 20 * H:  # alternate ground duty and short FDPs, 13 h rests
            if k % 2 == 0:
                w.other(pid, t, t + 8 * H, "ORD")
                t += 8 * H + 13 * H
            else:
                _, rel = w.fdp(pid, t + 60, ["ORD", "DEN", "ORD"])
                t = rel + 13 * H
            k += 1

        # Q2: 60 h / 168 h with an FDP straddling the window start, across the DST change.
        pid = f"ORD-{s}02"
        w.pilot(pid, seat, "ORD", B737, 190, ord_(9, 0))
        ws = ord_(12, 30) + 7 * H - 168 * H  # look-back start for trip O?04
        w.domestic_filler(rng, pid, "ORD", start_day, ws - 40 * H, rest_days=days_off(rng))
        w.fdp(pid, ws - 150 + 60, ["ORD", "DEN", "ORD", "MSP", "ORD"], turns=[50, 60, 50])
        for d in (4, 5, 6, 7):
            w.fdp(pid, loc(2026, 3, d, 8, 0, "ORD"), ["ORD", "MSP", "ORD", "ATL", "ORD"], turns=[50, 55, 50])

        # Q3: legal only if OTHER (non-flight) duty is kept out of the FDP limits.
        pid = f"ORD-{s}03"
        w.pilot(pid, seat, "ORD", B737, 170, ord_(9, 0))
        w.domestic_filler(rng, pid, "ORD", start_day, utc(2026, 3, 1, 12), rest_days=days_off(rng))
        w.other(pid, loc(2026, 3, 3, 7, 0, "ORD"), loc(2026, 3, 3, 17, 0, "ORD"), "ORD")
        for d in (4, 5, 6, 7):
            w.fdp(pid, loc(2026, 3, d, 7, 0, "ORD"), ["ORD", "MSP", "ORD", "ATL", "ORD"], turns=[50, 55, 50])

        # Q4: 100 flight hours / 672 h, with a leg straddling the window start.
        pid = f"ORD-{s}04"
        w.pilot(pid, seat, "ORD", B737, 150, ord_(5, 30))
        ws1 = ord_(6, 0) + 9 * H - 672 * H  # look-back start for trip O?01
        lax_out = ws1 + 60 - BLOCK[("LAX", "ORD")]
        w.fdp(pid, lax_out - 50 - BLOCK[("ORD", "LAX")], ["ORD", "LAX", "ORD"])
        routes = {520: ["ORD", "LAX", "ORD"], 300: ["ORD", "DEN", "ORD"],
                  415: ["ORD", "MSP", "ORD", "ATL", "ORD"], 170: ["ORD", "MSP", "ORD"]}
        plan = q4_plan(5640, 5685)
        days = [datetime(2026, 2, 10) + timedelta(days=i) for i in range(25)]
        days = [d for d in days if d.weekday() not in (5, 6)][:len(plan)]
        for d, f in zip(days, plan):
            w.fdp(pid, loc(2026, d.month, d.day, 6, 0, "ORD"), routes[f])

        # Q5..Q7: ordinary reserves.
        for k, (cost, rs) in enumerate([(120, ord_(5, 0)), (230, ord_(11, 0)), (260, ord_(6, 30))], 5):
            pid = f"ORD-{s}0{k}"
            w.pilot(pid, seat, "ORD", B737, cost, rs)
            w.domestic_filler(rng, pid, "ORD", start_day, end_hist - 22 * H, rest_days=days_off(rng))
    return w


def write(w):
    for d in (ENV_DATA, TEST_DATA):
        d.mkdir(parents=True, exist_ok=True)

    def dump(name, header, rows):
        with open(ENV_DATA / name, "w", newline="") as f:
            wr = csv.writer(f, lineterminator="\n")
            wr.writerow(header)
            wr.writerows(rows)

    dump("stations.csv", ["station", "tz"], sorted(STATIONS.items()))
    dump("pilots.csv", ["pilot_id", "seat", "base", "equipment", "callout_cost", "rap_start_local", "rap_end_local"],
         [[p["pilot_id"], p["seat"], p["base"], p["equipment"], p["callout_cost"],
           fmt(p["rap_start"], p["base"]), fmt(p["rap_end"], p["base"])]
          for p in sorted(w.pilots, key=lambda p: p["pilot_id"])])
    duties = sorted(w.duties, key=lambda d: (d["pilot_id"], d["report"]))
    ren = {d["duty_id"]: f"D{i:04d}" for i, d in enumerate(duties, 1)}
    dump("duties.csv", ["duty_id", "pilot_id", "duty_type", "report_station", "report_local",
                        "release_station", "release_local"],
         [[ren[d["duty_id"]], d["pilot_id"], d["duty_type"], d["report_station"],
           fmt(d["report"], d["report_station"]), d["release_station"],
           fmt(d["release"], d["release_station"])] for d in duties])
    legs = sorted(w.legs, key=lambda l: (ren[l["duty_id"]], l["leg_no"]))
    dump("legs.csv", ["duty_id", "leg_no", "dep", "arr", "out_local", "in_local"],
         [[ren[l["duty_id"]], l["leg_no"], l["dep"], l["arr"], fmt(l["out"], l["dep"]),
           fmt(l["inn"], l["arr"])] for l in legs])
    dump("trips.csv", ["trip_id", "base", "seat", "equipment", "report_local", "release_local"],
         [[t["trip_id"], t["base"], t["seat"], t["equipment"], fmt(t["report"], t["base"]),
           fmt(t["release"], t["base"])] for t in sorted(w.trips, key=lambda t: t["trip_id"])])
    dump("trip_legs.csv", ["trip_id", "leg_no", "dep", "arr", "out_local", "in_local"],
         [[l["trip_id"], l["leg_no"], l["dep"], l["arr"], fmt(l["out"], l["dep"]),
           fmt(l["inn"], l["arr"])] for l in sorted(w.trip_legs, key=lambda l: (l["trip_id"], l["leg_no"]))])
    for f in ENV_DATA.glob("*.csv"):
        shutil.copy(f, TEST_DATA / f.name)


if __name__ == "__main__":
    write(build())
    print("wrote", ENV_DATA)
