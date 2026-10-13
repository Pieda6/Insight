"""Verifier-side model of 49 CFR 395.1-395.3 for property-carrying drivers, written independently of the
reference solution (interval arithmetic instead of a minute scan). Reads only the verifier's private inputs."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
H = 60
WORK = {"driving", "on_duty_not_driving"}


def parse(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)


def fmt(t):
    return t.strftime("%Y-%m-%dT%H:%MZ")


class Record:
    """One driver's record of duty status as intervals of minutes from the first entry."""

    def __init__(self, segments):
        self.origin = parse(segments[0]["start"])
        self.items = []
        for i, seg in enumerate(segments):
            a, b = self.m(seg["start"]), self.m(seg["end"])
            kind = seg["status"]
            notes = seg.get("notes", {})
            if kind == "on_duty_not_driving" and notes.get("travel_at_carrier_direction"):
                rest, k = 0, i + 1                       # 395.1(j)(1): off duty if 10 h off on arrival
                while k < len(segments) and segments[k]["status"] == "off_duty":
                    rest += self.m(segments[k]["end"]) - self.m(segments[k]["start"])
                    k += 1
                if rest >= 10 * H:
                    kind = "off_duty"
            self.items.append({"a": a, "b": b, "kind": kind, "notes": notes})
        self.end = self.items[-1]["b"]

    def m(self, text):
        return int((parse(text) - self.origin).total_seconds()) // 60

    def at(self, minute):
        return self.origin + timedelta(minutes=minute)

    def blocks(self, kinds):
        out = []
        for it in self.items:
            if it["kind"] in kinds:
                if out and out[-1][1] == it["a"]:
                    out[-1][1] = it["b"]
                else:
                    out.append([it["a"], it["b"]])
        return [tuple(x) for x in out]

    def amount(self, kinds, lo, hi):
        return sum(max(0, min(hi, it["b"]) - max(lo, it["a"])) for it in self.items if it["kind"] in kinds)

    def sleeper_stretch(self, lo, hi):
        best = run = 0
        last = None
        for it in self.items:
            if it["b"] <= lo or it["a"] >= hi:
                continue
            if it["kind"] == "sleeper_berth":
                a, b = max(lo, it["a"]), min(hi, it["b"])
                run = run + (b - a) if last == a else b - a
                last = b
                best = max(best, run)
            else:
                last = None
        return best


def analyse(driver, rec, carrier, offset_h):
    rests = rec.blocks({"off_duty", "sleeper_berth"})
    full = [r for r in rests if r[1] - r[0] >= 10 * H]
    restarts = [r for r in rests if r[1] - r[0] >= 34 * H]
    tours = []
    for i, r in enumerate(full):
        nxt = full[i + 1][0] if i + 1 < len(full) else rec.end
        if r[1] < rec.end and rec.amount(WORK, r[1], nxt) > 0:
            tours.append({"on": r[1], "off": nxt, "before": r})

    hh, mm = (int(x) for x in carrier["day_starts_at"].split(":"))
    shift = offset_h * H - (hh * H + mm)                 # minutes to add to UTC to land on a day grid
    span = 8 if carrier["operates_every_day"] else 7
    limit = (70 if carrier["operates_every_day"] else 60) * H
    base = int(rec.origin.timestamp() // 60)

    def carrier_day(minute):
        return (base + minute + shift) // (24 * H)

    def first_minute_of_day(day):
        return day * 24 * H - shift - base

    def note_of(lo, hi, key):
        return [it["notes"][key] for it in rec.items if lo <= it["a"] < hi and key in it["notes"]]

    used_16 = []
    for i, t in enumerate(tours):
        release = next((it for it in rec.items if it["a"] == t["off"]), None)
        t["home"] = bool(release) and release["notes"].get("location") == "normal_work_reporting_location"
        t["miles"] = max(note_of(t["on"], t["off"], "max_distance_from_work_reporting_location_statute_miles") or [0])
        t["adverse"] = any(not x["known_to_driver_or_carrier_beforehand"]
                           for x in note_of(t["on"], t["off"], "adverse_driving_conditions"))
        t["o16"] = False
        if any(note_of(t["on"], t["off"], "claims_16_hour_exception")):
            earlier = tours[i - 5:i] if i >= 5 else []
            ok = len(earlier) == 5 and all(e["home"] for e in earlier) and t["home"] and t["off"] - t["on"] <= 16 * H
            today = carrier_day(t["on"])
            for u in used_16:
                within = today - 6 <= carrier_day(u) < today
                reset_since = any(u < r[0] < t["on"] for r in restarts)
                if within and not reset_since:
                    ok = False
            if ok:
                t["o16"] = True
                used_16.append(t["on"])
        before_all_off = rec.amount({"sleeper_berth", "on_duty_not_driving", "driving"}, *t["before"]) == 0
        t["short_haul"] = (t["miles"] <= 172.6 and t["home"] and t["off"] - t["on"] <= 14 * H and before_all_off
                           and carrier["keeps_short_haul_time_records"])
        # 395.1(g)(1)(ii): consecutive rest periods of 2 h or more inside the tour, pairing one of 7 h in the berth
        inner = [r for r in rests if t["on"] < r[0] and r[1] <= t["off"] and 2 * H <= r[1] - r[0] < 10 * H]
        t["recalc"] = []
        for first, second in zip(inner, inner[1:]):
            berth = max(rec.sleeper_stretch(*first), rec.sleeper_stretch(*second))
            if berth >= 7 * H and (first[1] - first[0]) + (second[1] - second[0]) >= 10 * H:
                t["recalc"].append({"from": second[1], "start": first[1], "skip": second[1] - second[0]})

    found = []
    for a, b in rec.blocks({"driving"}):
        t = next(x for x in tours if x["on"] <= a < x["off"])
        start, skip = t["on"], 0
        for rc in t["recalc"]:
            if rc["from"] <= a:
                start, skip = rc["start"], rc["skip"]
        extra = 2 * H if t["adverse"] else 0                  # 395.1(b)(1)
        hits = {}
        need = 11 * H + extra - rec.amount({"driving"}, start, a)
        if a + max(0, need) < b:
            hits["11_HOUR_DRIVING"] = a + max(0, need)
        stop = start + (16 if t["o16"] else 14) * H + extra + skip
        if max(a, stop) < b:
            hits["14_HOUR_WINDOW"] = max(a, stop)
        if not t["short_haul"]:
            pause_end = 0
            for r in rec.blocks({"off_duty", "sleeper_berth", "on_duty_not_driving"}):
                if r[1] <= a and r[1] - r[0] >= 30:
                    pause_end = r[1]
            need = 8 * H - rec.amount({"driving"}, pause_end, a)
            if a + max(0, need) < b:
                hits["30_MINUTE_BREAK"] = a + max(0, need)
        # 60/70 hours: the window restarts at each carrier day boundary inside the stretch
        cuts = [a]
        day = carrier_day(a) + 1
        while first_minute_of_day(day) < b:
            cuts.append(first_minute_of_day(day))
            day += 1
        cuts.append(b)
        for p, q in zip(cuts, cuts[1:]):
            lo = first_minute_of_day(carrier_day(p) - (span - 1))
            for r in restarts:                                 # 395.3(c)
                if lo < r[1] <= p:
                    lo = r[1]
            have = rec.amount(WORK, max(lo, 0), p)
            when = p + max(0, limit - have)
            if when < q:
                hits["60_70_HOUR"] = when
                break
        for rule, minute in hits.items():
            found.append([driver, fmt(rec.at(minute)), rule])
    return found


def expected():
    carriers = {c["carrier_id"]: c for c in json.loads((DATA / "carriers.json").read_text())}
    terminals = json.loads((DATA / "terminals.json").read_text())
    logs = json.loads((DATA / "logs.json").read_text())
    rows = []
    for d in json.loads((DATA / "drivers.json").read_text()):
        off = terminals[d["home_terminal"]]["utc_offset"]
        hours = (-1 if off.startswith("-") else 1) * (int(off[1:3]) + int(off[4:6]) / 60)
        rows += analyse(d["driver_id"], Record(logs[d["driver_id"]]), carriers[d["carrier_id"]], int(hours))
    return sorted(rows)
