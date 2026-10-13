#!/usr/bin/env python3
"""Reference solution: audit property-carrying drivers' duty-status records under 49 CFR 395.1-395.3."""
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

DATA = Path("/app/data")
OUT = Path("/app/output")
EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)
CODE = {"off_duty": "O", "sleeper_berth": "S", "driving": "D", "on_duty_not_driving": "N"}


def minute(s):
    return int((datetime.strptime(s, "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc) - EPOCH).total_seconds() // 60)


def stamp(m):
    return datetime.fromtimestamp(EPOCH.timestamp() + m * 60, tz=timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def offset_minutes(text):                      # "-05:00"
    sign = -1 if text[0] == "-" else 1
    h, m = text[1:].split(":")
    return sign * (int(h) * 60 + int(m))


def runs(status, t0, kinds):
    """Maximal runs of minutes whose status is in kinds: list of (start, end) absolute minutes."""
    out, i, n = [], 0, len(status)
    while i < n:
        if status[i] in kinds:
            j = i
            while j < n and status[j] in kinds:
                j += 1
            out.append((t0 + i, t0 + j))
            i = j
        else:
            i += 1
    return out


def longest(status, t0, a, b, kind):
    best = cur = 0
    for k in range(a - t0, b - t0):
        cur = cur + 1 if status[k] == kind else 0
        best = max(best, cur)
    return best


def audit(driver, segs, carrier, terminal):
    t0, t1 = minute(segs[0]["start"]), minute(segs[-1]["end"])
    status = []
    notes_at = {}
    for i, s in enumerate(segs):
        a, b = minute(s["start"]), minute(s["end"])
        code = CODE[s["status"]]
        if code == "N" and s.get("notes", {}).get("travel_at_carrier_direction"):
            off = 0
            for nxt in segs[i + 1:]:                       # 395.1(j)(1)
                if nxt["status"] != "off_duty":
                    break
                off += minute(nxt["end"]) - minute(nxt["start"])
            if off >= 600:
                code = "O"
        status.extend(code * (b - a))
        notes_at[a] = s
    n = len(status)
    work = [1 if c in "DN" else 0 for c in status]
    pre_work = [0]
    for w in work:
        pre_work.append(pre_work[-1] + w)
    drive = [1 if c == "D" else 0 for c in status]
    pre_drive = [0]
    for d in drive:
        pre_drive.append(pre_drive[-1] + d)

    rests = runs(status, t0, "OS")
    resets = [r for r in rests if r[1] - r[0] >= 600]
    restarts = [r for r in rests if r[1] - r[0] >= 34 * 60]

    # duty tours: from the first work minute after a reset to the start of the next reset
    tours = []
    for k, r in enumerate(resets):
        start = r[1]
        if start >= t1:
            continue
        end = resets[k + 1][0] if k + 1 < len(resets) else t1
        if pre_work[end - t0] - pre_work[start - t0] == 0:
            continue
        tours.append({"start": start, "end": end, "prev_reset": r})

    def tour_notes(t):
        segs_in = [s for s in segs if t["start"] <= minute(s["start"]) < t["end"]]
        rel = notes_at.get(t["end"])
        return segs_in, rel

    off = offset_minutes(terminal["utc_offset"])
    hh, mm = carrier["day_starts_at"].split(":")
    day0 = int(hh) * 60 + int(mm)
    days = 8 if carrier["operates_every_day"] else 7
    cap = (70 if carrier["operates_every_day"] else 60) * 60

    def day_index(m):
        return (m + off - day0) // 1440

    def day_start(idx):
        return idx * 1440 + day0 - off

    valid_16 = []                                         # tour starts where 395.1(o) was used
    for i, t in enumerate(tours):
        segs_in, rel = tour_notes(t)
        t["release_home"] = bool(rel and rel.get("notes", {}).get("location") == "normal_work_reporting_location")
        t["max_miles"] = max([s.get("notes", {}).get("max_distance_from_work_reporting_location_statute_miles", 0)
                              for s in segs_in if s["status"] == "driving"] or [0])
        adverse = [s["notes"]["adverse_driving_conditions"] for s in segs_in if s["status"] == "driving"
                   and s.get("notes", {}).get("adverse_driving_conditions")]
        t["adverse"] = any(not a["known_to_driver_or_carrier_beforehand"] for a in adverse)
        claim = any(s.get("notes", {}).get("claims_16_hour_exception") for s in segs_in)
        t["sixteen"] = False
        if claim:
            prev5 = tours[max(0, i - 5):i]
            ok = len(prev5) == 5 and all(p["release_home"] for p in prev5)
            ok = ok and t["release_home"] and t["end"] - t["start"] <= 16 * 60
            d = day_index(t["start"])
            for u in valid_16:
                if d - 6 <= day_index(u) <= d - 1 and not any(u < r[0] < t["start"] for r in restarts):
                    ok = False
            if ok:
                t["sixteen"] = True
                valid_16.append(t["start"])
        prev_rest_pure_off = all(c == "O" for c in status[t["prev_reset"][0] - t0:t["prev_reset"][1] - t0])
        t["short_haul"] = (t["max_miles"] <= 172.6 and t["release_home"] and t["end"] - t["start"] <= 14 * 60
                           and prev_rest_pure_off and carrier["keeps_short_haul_time_records"])
        # sleeper berth pairs inside the tour (395.1(g)(1)(ii)-(iii))
        cands = [r for r in rests if t["start"] < r[0] and r[1] <= t["end"] and 120 <= r[1] - r[0] < 600]
        pairs, prev = [], None
        for c in cands:
            if prev:
                long_sb = max(longest(status, t0, prev[0], prev[1], "S"), longest(status, t0, c[0], c[1], "S"))
                if long_sb >= 420 and (prev[1] - prev[0]) + (c[1] - c[0]) >= 600:
                    pairs.append((c[1], prev[1], c[1] - c[0]))   # effective from, calc start, excluded
            prev = c
        t["pairs"] = pairs

    # start of the current run of driving not yet interrupted by 30 consecutive non-driving minutes
    since_break, nd, last = [0] * n, 0, 0
    for i, c in enumerate(status):
        if c != "D":
            nd += 1
        else:
            if nd >= 30:
                last = i
            nd = 0
        since_break[i] = last

    rows = []
    for a, b in runs(status, t0, "D"):
        tour = next(t for t in tours if t["start"] <= a < t["end"])
        first = {}
        drive_limit = 660 + (120 if tour["adverse"] else 0)          # 395.1(b)(1)
        window = (960 if tour["sixteen"] else 840) + (120 if tour["adverse"] else 0)
        for m in range(a, b):
            calc, excl = tour["start"], 0
            for eff, cs, ex in tour["pairs"]:
                if eff <= m:
                    calc, excl = cs, ex
            if pre_drive[m - t0] - pre_drive[calc - t0] >= drive_limit:
                first.setdefault("11_HOUR_DRIVING", m)
            if m >= calc + window + excl:
                first.setdefault("14_HOUR_WINDOW", m)
            if not tour["short_haul"] and pre_drive[m - t0] - pre_drive[since_break[m - t0]] >= 480:
                first.setdefault("30_MINUTE_BREAK", m)
            w0 = day_start(day_index(m) - (days - 1))
            for r in restarts:                               # 395.3(c)
                if w0 < r[1] <= m:
                    w0 = r[1]
            w0 = max(w0, t0)
            if pre_work[m - t0] - pre_work[w0 - t0] >= cap:
                first.setdefault("60_70_HOUR", m)
        for rule, m in first.items():
            rows.append((driver, stamp(m), rule))
    return rows


def main():
    carriers = {c["carrier_id"]: c for c in json.loads((DATA / "carriers.json").read_text())}
    terminals = json.loads((DATA / "terminals.json").read_text())
    drivers = json.loads((DATA / "drivers.json").read_text())
    logs = json.loads((DATA / "logs.json").read_text())
    rows = []
    for d in drivers:
        rows += audit(d["driver_id"], logs[d["driver_id"]], carriers[d["carrier_id"]], terminals[d["home_terminal"]])
    rows.sort()
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "violations.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["driver_id", "violation_start", "rule"])
        w.writerows(rows)


if __name__ == "__main__":
    main()
