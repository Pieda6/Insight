"""Verifier-side model of the 2022 Construction General Permit requirements audited by stormwater-inspection-audit.

Written independently of the reference solution: dates are ordinal day numbers and times are whole minutes from the
start of 2026; each area's schedule is a list of (first ordinal, regime) segments, routine deadlines come from a sweep
over the merged reset points (inspections and schedule changes), and storms are runs found with itertools.groupby.
Reads only the verifier's private copy of the data.
"""
import itertools
import json
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
EPOCH = date(2026, 1, 1).toordinal()
LAST = date(2026, 9, 30).toordinal()
HORIZON = (LAST - EPOCH) * 1440 + 1439
SED_NUT = ("sedimentation/siltation", "total phosphorus", "total nitrogen")


def load(name):
    return json.loads((DATA / name).read_text())


def minute(s):
    if s is None:
        return None
    t = datetime.strptime(s, "%Y-%m-%dT%H:%M")
    return (t.date().toordinal() - EPOCH) * 1440 + t.hour * 60 + t.minute


def day_of(m):
    return EPOCH + m // 1440


def close(o):                         # 23:59 on ordinal day o
    return (o - EPOCH) * 1440 + 1439


def text(m):
    if m is None:
        return "none"
    d = date.fromordinal(EPOCH + m // 1440)
    return f"{d.isoformat()}T{m % 1440 // 60:02d}:{m % 60:02d}"


def month_on(o):
    d = date.fromordinal(o)
    y = d.year + (d.month == 12)
    m = d.month % 12 + 1
    last = (date(y + (m == 12), m % 12 + 1, 1).toordinal() - 1)
    return min(date(y, m, 1).toordinal() + d.day - 1, last)


def expected():
    per = defaultdict(lambda: defaultdict(list))
    for name in ("rain_gauge", "construction_log", "stabilization_records", "inspections", "findings", "trackout"):
        for r in load(name + ".json"):
            per[r["site_id"]][name].append(r)
    rows = []
    for site in load("sites.json"):
        rows.extend(site_rows(site, per[site["site_id"]]))
    rows.sort(key=lambda r: (r[0], r[1], r[3], r[2], r[4]))
    return rows


def site_rows(site, rec):
    sid = site["site_id"]
    res = []
    log = defaultdict(set)
    for e in rec["construction_log"]:
        log[e["area_id"]].add(date.fromisoformat(e["date"]).toordinal())
    bdays = sorted(set(itertools.chain.from_iterable(log.values())))
    bset = set(bdays)

    def first_bday_from(o):
        return next((x for x in bdays if x >= o), None)

    def add(aid, kind, due, met):
        if due <= HORIZON and (met is None or met > due):
            res.append([sid, aid, kind, text(due), text(met)])

    water = {w["water_id"]: w for w in site["receiving_waters"]}
    sens = {}
    for a in site["areas"]:
        w = water[a["discharges_to"]]
        sens[a["area_id"]] = any(p.lower() in SED_NUT for p in w["impaired_for"]) or \
            w["antidegradation_tier"] in ("2", "2.5", "3")
    four_two_one = site["inspection_schedule"] == "Part 4.2.1"
    finished = defaultdict(list)
    for s in rec["stabilization_records"]:
        if s["completed"]:
            finished[s["area_id"]].append(day_of(minute(s["completed"])))
    looks = defaultdict(list)
    for i in rec["inspections"]:
        for a in i["areas_inspected"]:
            looks[a].append(minute(i["completed"]))

    # storms: runs of consecutive measurable days; inspection after the first and last day with >= 0.25 in
    wet = sorted((date.fromisoformat(r["date"]).toordinal(), int(r["rain_inches"].replace(".", "")))
                 for r in load_rain(rec) if int(r["rain_inches"].replace(".", "")) > 0)
    triggers = []
    for _, grp in itertools.groupby(enumerate(wet), key=lambda p: p[1][0] - p[0]):
        big = [o for _, (o, v) in grp if v >= 25]
        triggers += sorted({big[0], big[-1]}) if big else []

    # regimes per area: list of (from ordinal, regime)
    def regimes(aid):
        segs = [(min(log[aid]), "R")]
        for c in sorted(finished[aid]):
            back = min((o for o in log[aid] if o > c), default=None)
            segs.append((c, "F"))
            m = month_on(c)
            if back is None or back > m:
                segs.append((m, "M"))
            if back is not None:
                segs.append((back, "R"))
        return sorted(segs)

    def regime_on(segs, o):
        cur = None
        for start, g in segs:
            if start <= o:
                cur = g
        return cur

    for a in site["areas"]:
        aid = a["area_id"]
        if not log[aid]:
            continue
        step = 7 if (four_two_one or sens[aid]) else 14
        segs = regimes(aid)

        def limit(o, g):
            return o + step if g == "R" else o + 14 if g == "F" else month_on(o)

        points = sorted([(o, 0, None) for o, _ in segs[1:] if o <= LAST] + [(day_of(m), 1, m) for m in looks[aid]])
        last_seen = min(log[aid])
        due = close(limit(last_seen, "R"))
        for o, kind, m in points:
            if kind == 0:
                due = close(limit(max(last_seen, o), regime_on(segs, o)))
                continue
            if m > due:
                add(aid, "routine_inspection", due, m)
            last_seen = o
            due = close(limit(o, regime_on(segs, o)))
        add(aid, "routine_inspection", due, None)

        if four_two_one and not sens[aid]:
            continue
        for o in triggers:
            if o < min(log[aid]) or regime_on(segs, o) != "R":
                continue
            b = first_bday_from(o + 1)
            if b is None:
                continue
            after = [m for m in sorted(looks[aid]) if day_of(m) > o]
            add(aid, "storm_inspection", close(b), after[0] if after else None)

    for i in rec["inspections"]:
        t = minute(i["completed"])
        add(i["areas_inspected"][0], "inspection_report", t + 1440, minute(i["report_completed"]))

    count = defaultdict(int)
    for f in sorted(rec["findings"], key=lambda x: (minute(x["discovered"]), x["finding_id"])):
        t = minute(f["discovered"])
        aid = f["area_id"]
        done = minute(f["completed"])
        nb = next((x for x in bdays if x > day_of(t)), None)
        if f["needs"] == "routine maintenance":
            key = (f["control_id"], f["location"], f["fix"])
            count[key] += 1
            if count[key] <= 3:
                due = t + 7 * 1440 if f["infeasibility_documented"] else (close(nb) if nb else None)
                if due is not None:
                    add(aid, "routine_maintenance", due, done)
                continue
            if nb:
                add(aid, "corrective_action", close(nb), done)
        else:
            add(aid, "corrective_action", t + 7 * 1440, done)
        add(aid, "ca_log_identified", t + 1440, minute(f["log_entry_identified"]))
        if done is not None:
            add(aid, "ca_log_completed", done + 1440, minute(f["log_entry_completed"]))
            if f["swppp_change_needed"]:
                add(aid, "swppp_update", done + 7 * 1440, minute(f["swppp_updated"]))

    for t in rec["trackout"]:
        o = day_of(minute(t["occurred"]))
        b = o if o in bset else next((x for x in bdays if x > o), None)
        if b is not None:
            add(t["area_id"], "trackout_removal", close(b), minute(t["removed"]))

    # disturbed acreage: per area, intervals [logged day .. completion day]
    load_by_day = defaultdict(int)
    for a in site["areas"]:
        aid = a["area_id"]
        hundredths = int(a["acres"].replace(".", ""))
        ends = sorted(finished[aid])
        on = set()
        for o in sorted(log[aid]):
            stop = min((c for c in ends if c >= o), default=LAST)
            on.update(range(o, stop + 1))
        for o in on:
            load_by_day[o] += hundredths
    heavy_site = max(load_by_day.values(), default=0) > 500

    for a in site["areas"]:
        aid = a["area_id"]
        seq = sorted(log[aid])
        for here, there in zip(seq, seq[1:] + [None]):
            if there is None and a["work_completed_on"] != date.fromordinal(here).isoformat():
                continue
            if there is not None and there - here - 1 < 14:
                continue
            nb = next((x for x in bdays if x > here), None)
            if nb is None:
                continue
            cands = [s for s in rec["stabilization_records"] if s["area_id"] == aid
                     and here <= day_of(minute(s["initiated"])) and (there is None or day_of(minute(s["initiated"])) < there)]
            cands.sort(key=lambda s: minute(s["initiated"]))
            add(aid, "stabilization_initiation", close(nb), minute(cands[0]["initiated"]) if cands else None)
            if cands:
                span = 7 if (sens[aid] or heavy_site) else 14
                add(aid, "stabilization_completion", minute(cands[0]["initiated"]) + span * 1440,
                    minute(cands[0]["completed"]))
    return res


def load_rain(rec):
    return rec["rain_gauge"]
