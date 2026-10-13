#!/usr/bin/env python3
"""Generate the hos-log-audit inputs (dev only, never shipped).

Two property-carrying motor carriers' drivers, with ELD duty-status records in UTC. Planted drivers each
carry a hand-worked list of violations (tests/golden.json); filler drivers are realistic random fleets
whose expected rows come from the verifier engine only. Constructs whose reading is contested (a
2-hour off-duty period as half of a sleeper-berth pair, sleeper-berth time inside a 34-hour restart,
driving between two paired rests beyond the original 14 hours) are kept out of the data.
"""
import json
import random
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "tasks" / "hos-log-audit"
ENV, TST = ROOT / "environment" / "data", ROOT / "tests" / "data"
rng = random.Random(395003)
UTC = timezone.utc
STATUS = {"O": "off_duty", "S": "sleeper_berth", "D": "driving", "N": "on_duty_not_driving"}
CARRIERS = [
    {"carrier_id": "PRAIRIE", "name": "Prairie Line Freight", "operates_every_day": True, "day_starts_at": "00:00",
     "keeps_short_haul_time_records": True},
    {"carrier_id": "MESA", "name": "Mesa Regional Haul", "operates_every_day": False, "day_starts_at": "06:00",
     "keeps_short_haul_time_records": True},
]
TERMINALS = {
    "CHI": {"city": "Chicago, IL", "time_zone": "America/Chicago", "utc_offset": "-05:00"},
    "IND": {"city": "Indianapolis, IN", "time_zone": "America/Indiana/Indianapolis", "utc_offset": "-04:00"},
    "DEN": {"city": "Denver, CO", "time_zone": "America/Denver", "utc_offset": "-06:00"},
    "PHX": {"city": "Phoenix, AZ", "time_zone": "America/Phoenix", "utc_offset": "-07:00"},
}
OFFSET = {"CHI": -5, "IND": -4, "DEN": -6, "PHX": -7}
NAMES = ["A. Brandt", "B. Okoro", "C. Vega", "D. Lund", "E. Farah", "F. Marsh", "G. Ito", "H. Kaya", "I. Novak",
         "J. Reyes", "K. Osei", "L. Duval", "M. Petrov", "N. Quinn", "O. Haas", "P. Mwangi", "Q. Soto", "R. Iqbal",
         "S. Byrne", "T. Moreau", "U. Adeyemi", "V. Lind", "W. Park", "X. Ruiz"]


def Z(day, h=0, m=0, month=9):
    """A UTC instant in September (or `month`) 2026."""
    return datetime(2026, month, 1, tzinfo=UTC) + timedelta(days=day - 1, hours=h, minutes=m)


def L(term, day, h=0, m=0):
    """A local wall-clock time at the terminal, as a UTC instant."""
    return Z(day, h, m) - timedelta(hours=OFFSET[term])


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%MZ")


class Log:
    def __init__(self, start, miles=None):
        self.t = start
        self.segs = []
        self.miles = miles if miles is not None else rng.choice([310, 420, 560, 780, 905])

    def add(self, code, minutes, **notes):
        if code == "D" and "max_distance_from_work_reporting_location_statute_miles" not in notes:
            notes["max_distance_from_work_reporting_location_statute_miles"] = self.miles
        end = self.t + timedelta(minutes=minutes)
        if self.segs and self.segs[-1]["status"] == STATUS[code] and not notes and not self.segs[-1].get("notes") \
                and code != "D":
            self.segs[-1]["end"] = iso(end)
        else:
            s = {"start": iso(self.t), "end": iso(end), "status": STATUS[code]}
            if notes:
                s["notes"] = notes
            self.segs.append(s)
        self.t = end
        return self

    def until(self, code, when, **notes):
        return self.add(code, int((when - self.t).total_seconds() // 60), **notes)

    def release(self, home=True, until=None, minutes=None):
        """Off duty after work, noting where the driver was released."""
        loc = "normal_work_reporting_location" if home else "away_from_normal_work_reporting_location"
        if until is not None:
            return self.until("O", until, location=loc)
        return self.add("O", minutes, location=loc)


class World:
    def __init__(self):
        self.drivers, self.logs, self.golden, self.tags = [], {}, {}, {}

    def driver(self, carrier, term, log, tags, expected=None):
        did = f"DR{len(self.drivers) + 1:03d}"
        k = len(self.drivers)
        self.drivers.append({"driver_id": did, "name": f"{'ABCDEFGHJKLMNPRSTVW'[k // len(NAMES)]}. {NAMES[k % len(NAMES)][3:]}",
                             "carrier_id": carrier, "home_terminal": term, "normal_work_reporting_location": term,
                             "vehicle": "property-carrying tractor with a sleeper berth"})
        self.logs[did] = log.segs
        self.tags[did] = tags
        if expected is not None:
            self.golden[did] = sorted([[did, iso(t), r] for t, r in expected])
        return did


def day_tour(log, miles=120, home=True, rest_to=None, rest_minutes=None, **first_notes):
    """A regular 9-hour local tour: 30 on, 240 driving, 30 on, 210 driving, 30 on."""
    log.add("N", 30, **first_notes).add("D", 240, max_distance_from_work_reporting_location_statute_miles=miles)
    log.add("N", 30).add("D", 210, max_distance_from_work_reporting_location_statute_miles=miles).add("N", 30)
    return log.release(home, until=rest_to, minutes=rest_minutes)


def planted(w):
    D = "driving"
    # ---------------- 11 hours, 14 hours, 30-minute break -------------------------------------------------
    g = Log(Z(19)).until("O", Z(21, 12))
    g.add("N", 30).add("D", 300).add("N", 30).add("D", 360).add("N", 15).add("D", 30).release(minutes=900)
    w.driver("PRAIRIE", "CHI", g, ["driving-11"], [(Z(22, 0, 15), "11_HOUR_DRIVING")])
    g = Log(Z(19)).until("O", Z(21, 12))
    g.add("N", 30).add("D", 300).add("N", 30).add("D", 360).release(minutes=900)
    w.driver("PRAIRIE", "CHI", g, ["driving-11", "boundary"], [])
    g = Log(Z(19)).until("O", Z(21, 12))
    g.add("N", 60).add("D", 240).add("O", 180).add("D", 240).add("N", 120).add("D", 60).release(minutes=900)
    w.driver("PRAIRIE", "CHI", g, ["window-14"], [(Z(22, 2), "14_HOUR_WINDOW")])
    g = Log(Z(19)).until("O", Z(21, 12))
    g.add("N", 60).add("D", 300).add("O", 120).add("D", 360).release(minutes=900)
    w.driver("PRAIRIE", "CHI", g, ["window-14", "boundary"], [])
    g = Log(Z(19)).until("O", Z(21, 12))
    g.add("N", 30).add("D", 480).add("N", 10).add("D", 60).release(minutes=900)
    w.driver("MESA", "DEN", g, ["break-30"], [(Z(21, 20, 40), "30_MINUTE_BREAK")])
    g = Log(Z(19)).until("O", Z(21, 12))
    g.add("N", 30).add("D", 480).add("O", 15).add("N", 15).add("D", 60).release(minutes=900)
    w.driver("MESA", "DEN", g, ["break-30"], [])

    # ---------------- short-haul (395.1(e)(1)) and the 30-minute break ------------------------------------
    def short(miles, release_after, home=True):
        g = Log(Z(19)).until("O", Z(21, 12))
        g.add("N", 30).add("D", 500, max_distance_from_work_reporting_location_statute_miles=miles)
        g.add("N", release_after - 530)
        return g.release(home, minutes=900)

    w.driver("MESA", "PHX", short(165, 590), ["short-haul"], [])
    w.driver("MESA", "PHX", short(180, 590), ["short-haul"], [(Z(21, 20, 30), "30_MINUTE_BREAK")])
    w.driver("MESA", "PHX", short(165, 845), ["short-haul"], [(Z(21, 20, 30), "30_MINUTE_BREAK")])
    w.driver("MESA", "PHX", short(165, 840), ["short-haul", "boundary"], [])
    w.driver("MESA", "PHX", short(120, 590, home=False), ["short-haul"], [(Z(21, 20, 30), "30_MINUTE_BREAK")])

    # ---------------- adverse driving conditions (395.1(b)(1)) --------------------------------------------
    for known, exp in ((False, []), (True, [(Z(22, 0, 15), "11_HOUR_DRIVING")])):
        g = Log(Z(19)).until("O", Z(21, 12))
        g.add("N", 30).add("D", 330).add("N", 30)
        g.add("D", 330, adverse_driving_conditions={"known_to_driver_or_carrier_beforehand": known})
        g.add("N", 15).add("D", 60).release(minutes=900)
        w.driver("PRAIRIE", "CHI", g, ["adverse"], exp)
    for known, exp in ((False, []), (True, [(Z(22, 2), "14_HOUR_WINDOW")])):
        g = Log(Z(19)).until("O", Z(21, 12))
        g.add("N", 60).add("D", 300).add("N", 240)
        g.add("D", 300, adverse_driving_conditions={"known_to_driver_or_carrier_beforehand": known})
        g.release(minutes=900)
        w.driver("PRAIRIE", "CHI", g, ["adverse"], exp)

    # ---------------- sleeper berth split (395.1(g)(1)(ii)-(iii)) -----------------------------------------
    def split_head():
        g = Log(Z(19)).until("O", Z(21, 12))
        return g.add("N", 30).add("D", 300).add("S", 180).add("D", 240)

    # a valid pair (3 h + 8 h): limits run from the end of the first period and the 14 hours skip the second
    g = split_head().add("S", 480).add("D", 300).add("N", 30).add("D", 60).release(minutes=900)
    w.driver("PRAIRIE", "CHI", g, ["sleeper-split"], [])
    g = split_head().add("S", 480).add("D", 120).add("N", 420).add("D", 30).release(minutes=900)
    w.driver("PRAIRIE", "CHI", g, ["sleeper-split"], [])
    # 2 h + 7.5 h is under 10 hours: no pair, so the original 11 and 14 hours still run from 12:00
    g = Log(Z(19)).until("O", Z(21, 12))
    g.add("N", 30).add("D", 300).add("S", 120).add("D", 240).add("S", 450).add("D", 300).release(minutes=900)
    w.driver("PRAIRIE", "CHI", g, ["sleeper-split"], [(Z(22, 7), "14_HOUR_WINDOW"), (Z(22, 9), "11_HOUR_DRIVING")])
    g = split_head().add("S", 410).add("D", 300).release(minutes=900)
    w.driver("PRAIRIE", "CHI", g, ["sleeper-split"], [(Z(22, 7, 20), "14_HOUR_WINDOW"), (Z(22, 9, 20), "11_HOUR_DRIVING")])
    # two 5-hour berth periods: neither is 7 hours, so no pair and the 14 hours still run from 12:00
    g = Log(Z(19)).until("O", Z(21, 12))
    g.add("N", 30).add("D", 300).add("S", 300).add("D", 120).add("S", 300).add("D", 240).release(minutes=900)
    w.driver("PRAIRIE", "CHI", g, ["sleeper-split"], [(Z(22, 5, 30), "14_HOUR_WINDOW")])
    g = Log(Z(19)).until("O", Z(21, 12))
    g.add("N", 30).add("D", 300).add("N", 30).add("D", 300).add("O", 300).add("S", 300).add("D", 300)
    g.release(minutes=900)
    w.driver("PRAIRIE", "CHI", g, ["sleeper-split", "reset-10"], [])

    # near misses: 2.5 h + 7 h (under 10), 1 h 50 + 8 h 20 (short period under 2 h), 2.5 h + (6 h 40 berth
    # + 1 h off) (no 7 consecutive berth hours): no pair, so the 14 hours still run from 12:00
    def near(first, second, after):
        g = Log(Z(19)).until("O", Z(21, 12))
        g.add("N", 30).add("D", 300).add("S", first).add("D", 180)
        for code, mins in second:
            g.add(code, mins)
        return g.add("D", after).release(minutes=900)

    w.driver("PRAIRIE", "DEN", near(150, [("S", 420)], 180), ["sleeper-split"], [(Z(22, 6), "14_HOUR_WINDOW")])
    w.driver("MESA", "PHX", near(110, [("S", 500)], 120), ["sleeper-split"], [(Z(22, 6, 40), "14_HOUR_WINDOW")])
    w.driver("PRAIRIE", "IND", near(150, [("S", 400), ("O", 60)], 180), ["sleeper-split"],
             [(Z(22, 6, 40), "14_HOUR_WINDOW")])
    # 8 h berth + 2 h off is a 10-hour rest; with 10 minutes on duty between them it is not
    for gap, exp in ((0, []), (10, [(Z(22, 9), "14_HOUR_WINDOW")])):
        g = Log(Z(19)).until("O", Z(21, 12))
        g.add("N", 30).add("D", 300).add("N", 30).add("D", 240).add("N", 30).add("S", 480)
        if gap:
            g.add("N", gap).add("O", 110)
        else:
            g.add("O", 120)
        g.add("N", 30).add("D", 120).release(minutes=900)
        w.driver("PRAIRIE", "CHI", g, ["reset-10"], exp)
    # 29 consecutive non-driving minutes are not a break; 15 on duty + 15 off are
    for off, exp in ((9, [(Z(21, 20, 59), "30_MINUTE_BREAK")]), (10, [])):
        g = Log(Z(19)).until("O", Z(21, 12))
        g.add("N", 30).add("D", 300).add("N", 20).add("O", off).add("D", 240).release(minutes=900)
        w.driver("MESA", "DEN", g, ["break-30"], exp)

    # ---------------- 60/70 hours: carrier days, restarts, travel time ------------------------------------
    def week(term, days, start_h, on_minutes, log):
        for d in days:
            log.until("O", L(term, d, start_h))
            log.add("N", 30).add("D", 240).add("N", 30).add("D", 240)
            if on_minutes > 540:
                log.add("N", on_minutes - 540)
            log.release(minutes=60)
        return log

    for end, exp in (((20, 50), []), ((21, 30), [(L("CHI", 28, 21), "60_70_HOUR")])):
        g = Log(Z(18))
        g.until("O", L("CHI", 20, 14)).add("N", 30).add("D", 240).add("N", 30).add("D", 240).add("N", 60)
        g.release(minutes=30)
        week("CHI", range(21, 27), 10, 540, g)
        g.until("O", L("CHI", 27, 10)).add("N", 30).add("D", 240).add("N", 30).release(minutes=60)
        g.until("O", L("CHI", 28, 10)).add("N", 30).add("D", 240).add("N", 30).add("D", 240).add("N", 90)
        g.until("D", L("CHI", 28, *end)).release(minutes=900)
        w.driver("PRAIRIE", "CHI", g, ["cycle-70", "carrier-day"], exp)
    for rest_h, exp in ((34, []), (33, [(L("CHI", 28, 15), "60_70_HOUR")])):
        g = Log(Z(18))
        week("CHI", range(21, 27), 10, 600, g)
        g.until("O", L("CHI", 26, 20) + timedelta(hours=rest_h))
        g.add("N", 30).add("D", 240).add("N", 30).add("D", 240).add("N", 30).add("D", 60).release(minutes=900)
        w.driver("PRAIRIE", "CHI", g, ["cycle-70", "restart"], exp)
    for off_before, exp in ((20, []), (16, [(L("CHI", 28, 14), "60_70_HOUR")])):
        g = Log(Z(18))
        week("CHI", range(21, 27), 10, 600, g)
        g.until("O", L("CHI", 26, 20) + timedelta(hours=off_before))
        g.add("N", 240, travel_at_carrier_direction=True).add("O", 720)
        g.add("N", 30).add("D", 240).add("N", 30).add("D", 240).add("N", 30).add("D", 60).release(minutes=900)
        w.driver("PRAIRIE", "CHI", g, ["cycle-70", "travel-time"], exp)
    # travel followed by only 9 hours off stays on duty: the 14 hours start when the travel starts
    g = Log(Z(18))
    week("CHI", range(21, 27), 10, 600, g)
    g.until("O", L("CHI", 27, 20)).add("N", 180, travel_at_carrier_direction=True).add("O", 540)
    g.add("N", 30).add("D", 240).release(minutes=900)
    w.driver("PRAIRIE", "CHI", g, ["travel-time", "window-14"], [(L("CHI", 28, 10), "14_HOUR_WINDOW")])
    g = Log(Z(18))
    g.until("O", L("DEN", 21, 1)).add("N", 30).add("D", 180).add("N", 30).release(minutes=60)
    week("DEN", range(21, 27), 15, 540, g)
    g.until("O", L("DEN", 27, 15)).add("N", 30).add("D", 240).add("N", 30).add("D", 120).release(minutes=900)
    w.driver("MESA", "DEN", g, ["cycle-60", "carrier-day"], [(L("DEN", 27, 21), "60_70_HOUR")])

    # ---------------- 16-hour property-carrying exception (395.1(o)) ----------------------------------------
    def long_day(g, d, release_min, miles=120, first_drive=None):
        g.until("O", Z(d, 8))
        if first_drive:
            g.add("N", 30, claims_16_hour_exception=True)
            g.add("D", first_drive, max_distance_from_work_reporting_location_statute_miles=miles)
            g.add("N", 250).add("D", 120, max_distance_from_work_reporting_location_statute_miles=miles)
        else:
            g.add("N", 60, claims_16_hour_exception=True)
            g.add("D", 300, max_distance_from_work_reporting_location_statute_miles=miles).add("N", 180)
            g.add("D", 240, max_distance_from_work_reporting_location_statute_miles=miles).add("N", 60)
            g.add("D", 60, max_distance_from_work_reporting_location_statute_miles=miles)
        g.until("N", Z(d, 8) + timedelta(minutes=release_min))
        return g.release(minutes=720)

    def history(days, away=()):
        g = Log(Z(5))
        for d in days:
            g.until("O", Z(d, 12))
            day_tour(g, home=d not in away, rest_minutes=60)
        return g

    g = long_day(history([14, 15, 16, 17, 18]), 21, 930)
    w.driver("PRAIRIE", "IND", g, ["sixteen-hour"], [])
    g = long_day(history([14, 15, 16, 17, 18]), 21, 970)
    w.driver("PRAIRIE", "IND", g, ["sixteen-hour"], [(Z(21, 22), "14_HOUR_WINDOW")])
    g = history([7, 8, 9, 10, 11, 14, 15])
    long_day(g, 16, 930)
    g.until("O", Z(17, 12))
    day_tour(g, rest_minutes=60)
    long_day(g, 18, 930)
    w.driver("PRAIRIE", "IND", g, ["sixteen-hour"], [(Z(18, 22), "14_HOUR_WINDOW")])
    g = history([7, 8, 9, 10, 11, 14, 15])
    long_day(g, 16, 930)
    for d in (17, 18):
        g.until("O", Z(d, 12))
        day_tour(g, rest_minutes=60)
    long_day(g, 21, 930)
    w.driver("PRAIRIE", "IND", g, ["sixteen-hour", "restart"], [])
    g = long_day(history([14, 15, 16, 17, 18], away=(17,)), 21, 930)
    w.driver("PRAIRIE", "IND", g, ["sixteen-hour"], [(Z(21, 22), "14_HOUR_WINDOW")])
    g = long_day(history([14, 15, 16, 17, 18]), 21, 930, first_drive=500)
    w.driver("PRAIRIE", "IND", g, ["sixteen-hour", "short-haul"], [(Z(21, 16, 30), "30_MINUTE_BREAK")])


# ---------------- filler fleets ---------------------------------------------------------------------------
def long_haul(w, carrier, term, weeks=3):
    """Over-the-road driver: 10-11 h sleeper-berth resets on the road, home on weekends (off duty)."""
    g = Log(Z(5))
    start = L(term, 7, rng.choice([5, 6, 7, 8]))
    for wk in range(weeks):
        g.until("O", start + timedelta(days=7 * wk))
        ndays = rng.choice([4, 5])
        for day in range(ndays):
            g.add("N", rng.choice([15, 30, 45]))
            g.add("D", rng.choice([180, 240, 270, 300, 330]))
            g.add(rng.choice("NO"), rng.choice([30, 35, 45]))
            g.add("D", rng.choice([150, 210, 240, 300, 330, 380]))
            if rng.random() < 0.5:
                g.add("N", rng.choice([10, 20, 40]))
                g.add("D", rng.choice([30, 60, 90, 150]))
            g.add("N", rng.choice([15, 30, 90, 150]))
            if day < ndays - 1:                              # weekend restarts stay purely off duty
                g.add("S", rng.choice([600, 630, 660, 720]))
        g.release(minutes=60)
    g.add("O", 600)
    return g


def split_runner(w, carrier, term):
    """Long-haul driver who sometimes splits: 2-3 h sleeper early, then 7-8 h sleeper."""
    g = Log(Z(5))
    g.until("O", L(term, 7, rng.choice([4, 6])))
    for day in range(rng.choice([8, 9, 10])):
        g.add("N", 30).add("D", rng.choice([240, 270, 300]))
        if rng.random() < 0.6:
            # short sleeper first, then 7-8 h; driving around the pair stays inside the recalculated limits
            # whenever the pair is valid (so 395.1(g)(1)(ii)(D) is never in play)
            mid = rng.choice([180, 210, 240])
            g.add("S", rng.choice([120, 150, 180])).add("D", mid)
            g.add("S", rng.choice([420, 450, 480]))
            x = rng.choice([180, 240, 300])
            y = rng.choice([30, 60, 90, 120])
            while mid + x + y > 660:
                y -= 30
            g.add("D", x)
            if y > 0:
                g.add("N", 30).add("D", y)
            g.add("N", 30).add("S", 660)
        else:
            g.add("N", 30).add("D", rng.choice([240, 300, 360])).add("N", 30).add("S", 630)
    return g


def regional(w, carrier, term, weeks=3):
    g = Log(Z(5))
    for wk in range(weeks):
        days = [7 + 7 * wk + d for d in range(rng.choice([4, 5, 6]))]
        for d in days:
            g.until("O", L(term, d, rng.choice([5, 6, 7])))
            miles = rng.choice([90, 130, 160, 170, 185, 240])
            g.add("N", rng.choice([20, 30]))
            g.add("D", rng.choice([240, 300, 420, 470, 500]), max_distance_from_work_reporting_location_statute_miles=miles)
            g.add("N", rng.choice([20, 40, 60]))
            g.add("D", rng.choice([60, 120, 180, 240]), max_distance_from_work_reporting_location_statute_miles=miles)
            g.add("N", rng.choice([20, 45, 90, 200]))
            g.release(home=rng.random() < 0.9, minutes=60)
    g.add("O", 900)
    return g


def tight_split(w, carrier, term):
    """Sleeper-berth driver whose rests sit right at the thresholds: valid splits, splits just under
    10 hours, a short period under 2 hours, a 'long' period with under 7 consecutive berth hours, a
    10-hour rest broken by a short on-duty entry, and breaks a minute short of 30."""
    g = Log(Z(5))
    g.until("O", L(term, 7, rng.choice([3, 5, 7])))
    for day in range(rng.choice([8, 9, 10])):
        kind = rng.choice("abcdeff" if day % 2 else "abcde")
        g.add("N", 30).add("D", rng.choice([240, 270, 300]))
        if kind == "a":                                   # valid pair, limits respected afterwards
            s1 = rng.choice([120, 135, 150, 180])
            mid = rng.choice([150, 180, 210])
            g.add("S", s1).add("D", mid).add("S", max(420, 600 - s1) + rng.choice([0, 15, 30]))
            x = rng.choice([180, 240, 300])
            y = max(0, min(rng.choice([60, 120, 180]), 660 - mid - x))
            g.add("D", x)
            if y:
                g.add("N", 30).add("D", y)
        elif kind == "b":                                 # 7+ hours in the berth but under 10 in total
            s1 = rng.choice([120, 150])
            g.add("S", s1).add("D", rng.choice([150, 180])).add("S", rng.choice([540, 570, 585]) - s1)
            g.add("D", rng.choice([120, 180, 240])).add("N", 30).add("D", rng.choice([30, 60]))
        elif kind == "c":                                 # first period under 2 hours
            g.add("S", rng.choice([100, 110, 115])).add("D", rng.choice([150, 180]))
            g.add("S", rng.choice([490, 500, 510])).add("D", rng.choice([120, 180, 240]))
        elif kind == "d":                                 # long period has under 7 consecutive berth hours
            g.add("S", rng.choice([150, 180])).add("D", rng.choice([150, 180]))
            g.add("S", rng.choice([380, 400, 410])).add("O", rng.choice([50, 60, 70]))
            g.add("D", rng.choice([120, 180, 240]))
        elif kind == "e":                                 # 10 hours off interrupted by a short on-duty entry
            g.add("N", 30).add("D", rng.choice([180, 240])).add("N", 30)
            g.add("S", 480).add("N", rng.choice([5, 10, 15])).add("O", rng.choice([100, 110]))
            g.add("N", 30).add("D", rng.choice([120, 180, 240]))
        else:                                             # breaks of 29 and 30 minutes
            g.add("N", 20).add("O", rng.choice([9, 10]))
            g.add("D", rng.choice([200, 240])).add("N", 15).add("O", 15).add("D", rng.choice([60, 120]))
        if day == 4:                                      # home for a restart mid-run
            g.add("N", 30).release(minutes=rng.choice([2100, 2160]))
        else:
            g.add("N", 30).add("S", rng.choice([600, 630, 660]))
    g.release(minutes=900)
    return g


def contested(log):
    """True when a log would need a reading the regulation leaves open: a tour with more than two
    rest periods that could pair, a valid pair with driving beyond the original limits before the
    second period or beyond the recalculated limits after it, a pure off-duty half of a pair, or a
    34-hour rest that contains sleeper-berth time."""
    def m(x):
        return int((datetime.strptime(x, "%Y-%m-%dT%H:%MZ").replace(tzinfo=UTC) - Z(1)).total_seconds() // 60)
    t0 = m(log.segs[0]["start"])
    st = []
    for sg in log.segs:
        st.extend({"off_duty": "O", "sleeper_berth": "S", "driving": "D",
                   "on_duty_not_driving": "N"}[sg["status"]] * (m(sg["end"]) - m(sg["start"])))
    rests, i = [], 0
    while i < len(st):
        if st[i] in "OS":
            j = i
            while j < len(st) and st[j] in "OS":
                j += 1
            rests.append((i, j))
            i = j
        else:
            i += 1

    def berth(a, b):
        best = cur = 0
        for k in range(a, b):
            cur = cur + 1 if st[k] == "S" else 0
            best = max(best, cur)
        return best

    def driven(a, b):
        return sum(1 for k in range(a, b) if st[k] == "D")

    for a, b in rests:
        if b - a >= 34 * 60 and "S" in st[a:b] and "D" in st[b:]:
            return True
    resets = [r for r in rests if r[1] - r[0] >= 600]
    for k, r in enumerate(resets):
        start = r[1]
        end = resets[k + 1][0] if k + 1 < len(resets) else len(st)
        cands = [x for x in rests if start < x[0] and x[1] <= end and 120 <= x[1] - x[0] < 600]
        if len(cands) > 2:
            return True
        if len(cands) == 2:
            p, q = cands
            if max(berth(*p), berth(*q)) >= 420 and (p[1] - p[0]) + (q[1] - q[0]) >= 600:
                if berth(*p) == 0 or berth(*q) == 0:
                    return True
                for t in range(start, q[0]):
                    if st[t] == "D" and (t >= start + 840 or driven(start, t) >= 660):
                        return True
                for t in range(q[1], end):
                    if st[t] == "D" and (t >= p[1] + 840 + (q[1] - q[0]) or driven(p[1], t) >= 660):
                        return True
    return False


REJECTED = []


def filler(w, builder, carrier, term):
    while True:
        g = builder(w, carrier, term)
        if not contested(g):
            return w.driver(carrier, term, g, ["filler"])
        REJECTED.append(builder.__name__)


def main():
    w = World()
    planted(w)
    for _ in range(9):
        filler(w, long_haul, rng.choice(["PRAIRIE", "MESA"]), rng.choice(list(TERMINALS)))
    for _ in range(5):
        filler(w, split_runner, rng.choice(["PRAIRIE", "MESA"]), rng.choice(list(TERMINALS)))
    for _ in range(7):
        filler(w, regional, rng.choice(["PRAIRIE", "MESA"]), rng.choice(list(TERMINALS)))
    for _ in range(14):
        filler(w, tight_split, rng.choice(["PRAIRIE", "MESA"]), rng.choice(list(TERMINALS)))
    # shuffle the driver ids so planted drivers are not grouped
    ids = [d["driver_id"] for d in w.drivers]
    new = ids[:]
    rng.shuffle(new)
    ren = dict(zip(ids, new))
    for d in w.drivers:
        d["driver_id"] = ren[d["driver_id"]]
    w.drivers.sort(key=lambda d: d["driver_id"])
    w.logs = {ren[k]: v for k, v in sorted(w.logs.items(), key=lambda kv: ren[kv[0]])}
    w.tags = {ren[k]: v for k, v in w.tags.items()}
    w.golden = {ren[k]: sorted([[ren[k], t, r] for _, t, r in v]) for k, v in w.golden.items()}
    ENV.mkdir(parents=True, exist_ok=True)
    (ENV / "carriers.json").write_text(json.dumps(CARRIERS, indent=1) + "\n")
    (ENV / "terminals.json").write_text(json.dumps(TERMINALS, indent=1) + "\n")
    (ENV / "drivers.json").write_text(json.dumps(w.drivers, indent=1) + "\n")
    (ENV / "logs.json").write_text(json.dumps(w.logs, indent=1) + "\n")
    if TST.exists():
        shutil.rmtree(TST)
    shutil.copytree(ENV, TST)
    (ROOT / "tests" / "case_tags.json").write_text(json.dumps(w.tags, indent=1, sort_keys=True) + "\n")
    (ROOT / "tests" / "golden.json").write_text(json.dumps(w.golden, indent=1, sort_keys=True) + "\n")
    print(len(w.drivers), "drivers,", sum(len(v) for v in w.logs.values()), "segments,", len(w.golden), "golden,",
          len(REJECTED), "contested filler logs regenerated")


if __name__ == "__main__":
    main()
