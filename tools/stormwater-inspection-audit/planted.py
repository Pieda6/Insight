"""Hand-planted sites for stormwater-inspection-audit, each with its expected rows worked by hand (dev only).

2026 calendar used below: Jul 6, 13, 20, 27, Aug 3, 10, 17, 24, 31, Sep 14, 21, 28 are Mondays; Aug 1 and Sep 5 are
Saturdays; Sep 7 is Labor Day (no planted site works that day). The audit ends 2026-09-30 23:59.
Every planted site keeps its reports within 24 hours unless a row below says otherwise.
"""
from datetime import date, datetime, timedelta

DAY = timedelta(days=1)


def t(s):
    return datetime.strptime(s, "%Y-%m-%d %H:%M")


def d(s):
    return date.fromisoformat(s)


def days(a, b, weekdays=(0, 1, 2, 3, 4), skip=()):
    out, x = set(), d(a)
    skip = {d(s) for s in skip}
    while x <= d(b):
        if x.weekday() in weekdays and x not in skip:
            out.add(x)
        x += DAY
    return out


PROJECTS = {"business_days": "medical office building, Gurabo", "storms": "highway interchange ramp, Cayey",
            "routine_clock": "housing subdivision, Toa Alta", "reduced_frequency": "distribution warehouse, Carolina",
            "five_acres_exact": "school expansion, Humacao", "five_acres_reopen": "apartment complex, Dorado",
            "five_acres_same_day": "logistics yard, Barceloneta", "stabilization_start": "community center, Cidra",
            "sensitive_waters": "water storage tank, Naguabo", "repeat_fixes": "sports complex, Arecibo",
            "corrective_actions": "fire station, Juncos"}


def site(sid, sched, areas, waters=None, hours=("07:00", "15:30"), project=""):
    waters = waters or [{"water_id": f"{sid}-W1", "name": "Rio Gurabo", "impaired_for": [], "antidegradation_tier": "1"}]
    return {"site_id": sid, "project": project, "inspection_schedule": sched,
            "normal_working_hours": {"start": hours[0], "end": hours[1]}, "receiving_waters": waters,
            "areas": [{"area_id": f"{sid}-{a}", "description": desc, "acres_hundredths": ac,
                       "discharges_to": f"{sid}-{w}", "work_completed_on": d(done) if done else None}
                      for a, desc, ac, w, done in areas]}


def insp(sid, when, areas, report_hours=2.0, report=None):
    c = t(when)
    rep = t(report) if report else c + timedelta(hours=report_hours)
    return {"completed": c, "areas": sorted(f"{sid}-{a}" for a in areas), "report_completed": rep}


def stab(sid, area, start, end, measure="hydroseed and mulch"):
    return {"area_id": f"{sid}-{area}", "initiated": t(start), "completed": t(end) if end else None, "measure": measure}


def find(sid, area, when, control, loc, fix, needs, done, infeas=False, log_id=None, log_done=None, swppp=False,
         swppp_at=None, condition=None):
    return {"area_id": f"{sid}-{area}", "inspection": None, "discovered": t(when), "control_id": control,
            "location": loc, "fix": fix, "needs": needs, "infeasibility_documented": infeas,
            "completed": t(done) if done else None, "log_identified": t(log_id) if log_id else None,
            "log_completed": t(log_done) if log_done else None, "swppp_change": swppp,
            "swppp_updated": t(swppp_at) if swppp_at else None, "condition": condition or f"needs: {fix}"}


def track(sid, area, occ, rem):
    return {"area_id": f"{sid}-{area}", "occurred": t(occ), "removed": t(rem) if rem else None}


def rows(sid, items):
    return [(sid, f"{sid}-{a}", req, due, met) for a, req, due, met in items]


def bundle(s, rain, work, stabs=(), ins=(), finds=(), tracks=()):
    sid = s["site_id"]
    w = {a["area_id"]: set() for a in s["areas"]}
    for a, ds in work.items():
        w[f"{sid}-{a}"] = set(ds)
    return {"site": s, "rain": {d(k): v for k, v in rain.items()}, "work": w, "stabs": list(stabs),
            "insp": sorted(ins, key=lambda i: i["completed"]), "finds": list(finds), "track": list(tracks)}


MONDAYS_FRIDAYS = ["2026-07-06", "2026-07-13", "2026-07-20", "2026-07-27", "2026-08-03", "2026-08-10", "2026-08-17",
                   "2026-08-24", "2026-08-31", "2026-09-04", "2026-09-11", "2026-09-18", "2026-09-25"]


def weekly(sid, areas_on, hour="08:00", skip=()):
    """Weekly inspections (Mondays, then Fridays around Labor Day); areas_on(date) gives the areas covered."""
    out = []
    for x in MONDAYS_FRIDAYS:
        if x in skip:
            continue
        cover = areas_on(d(x))
        if cover:
            out.append(insp(sid, f"{x} {hour}", cover))
    return out


# ------------------------------------------------------------------------------------------------------------------
def business_days(sid):
    """Tuesday-to-Saturday site: Appendix A business days are days with construction activities, not Mon-Fri."""
    s = site(sid, "Part 4.2.1", [("A01", "building pad", 120, "W1", None), ("A02", "parking lot", 80, "W1", None)],
             waters=[{"water_id": f"{sid}-W1", "name": "Rio Hondo", "impaired_for": ["Mercury"],
                      "antidegradation_tier": "1"}])
    tue_sat = days("2026-08-04", "2026-09-30", weekdays=(1, 2, 3, 4, 5))
    ins = [insp(sid, f"{x} 10:00", ["A01", "A02"]) for x in
           ["2026-08-04", "2026-08-11", "2026-08-18", "2026-08-25", "2026-09-01", "2026-09-08", "2026-09-15",
            "2026-09-22", "2026-09-29"]]
    ins.append(insp(sid, "2026-09-04 10:00", ["A01"]))
    finds = [
        # Tue Aug 11: next business day is Wed Aug 12 -> due 08-12 23:59; done Thu 09:00 -> late
        find(sid, "A02", "2026-08-11 10:00", "SF-021", "Sta 1+20", "remove accumulated sediment",
             "routine maintenance", "2026-08-13 09:00"),
        # Fri Sep 4: next business day is Sat Sep 5 -> due 09-05 23:59; done Mon Sep 7 09:00 -> late
        find(sid, "A01", "2026-09-04 10:00", "IP-011", "Sta 0+50", "replace filter bag", "routine maintenance",
             "2026-09-07 09:00"),
    ]
    tracks = [
        track(sid, "A01", "2026-08-08 14:00", "2026-08-10 08:00"),   # Sat is a business day -> due 08-08 23:59, late
        track(sid, "A01", "2026-08-16 09:30", "2026-08-18 11:00"),   # Sun -> next business day Tue 08-18, on time
        track(sid, "A02", "2026-08-24 07:30", "2026-08-25 16:00"),   # Mon is not a business day here -> Tue, on time
    ]
    rain = {"2026-08-20": 80, "2026-09-02": 12}                      # 4.2.1, no sensitive water: no storm inspections
    b = bundle(s, rain, {"A01": tue_sat, "A02": tue_sat}, ins=ins, finds=finds, tracks=tracks)
    exp = rows(sid, [("A01", "trackout_removal", "2026-08-08T23:59", "2026-08-10T08:00"),
                     ("A02", "routine_maintenance", "2026-08-12T23:59", "2026-08-13T09:00"),
                     ("A01", "routine_maintenance", "2026-09-05T23:59", "2026-09-07T09:00")])
    return b, exp, ["business-day", "trackout", "maintenance"]


def storms(sid):
    """Part 4.2.2 site, Mon-Fri, no work on Labor Day: multi-day storms, 0.24 vs 0.25, footnote 68."""
    s = site(sid, "Part 4.2.2", [("A01", "access road", 200, "W1", None)], hours=("07:00", "16:00"))
    work = days("2026-08-03", "2026-09-30", skip=["2026-09-07"])
    rain = {"2026-08-07": 30, "2026-08-08": 40, "2026-08-09": 12, "2026-08-10": 27,   # storm: triggers 08-07, 08-10
            "2026-08-17": 24,                                                          # below 0.25: none
            "2026-08-24": 31, "2026-08-25": 26, "2026-08-26": 33,                      # triggers 08-24, 08-26
            "2026-09-03": 25,                                                          # exactly 0.25: trigger
            "2026-09-05": 50,                                                          # Sat: due Tue 09-08 (Mon off)
            "2026-09-14": 5}
    ins = [insp(sid, x, ["A01"]) for x in
           ["2026-08-03 09:00", "2026-08-10 10:00", "2026-08-12 09:30", "2026-08-17 09:00", "2026-08-25 10:00",
            "2026-08-27 10:00", "2026-09-08 10:00", "2026-09-21 09:00"]]
    # 08-07 -> Sat/Sun not business -> due Mon 08-10 23:59, met 08-10 10:00
    # 08-10 -> due Tue 08-11 23:59, met Wed 08-12 09:30 (late)
    # 08-24 -> due 08-25, met 08-25; 08-26 -> due 08-27, met 08-27
    # 09-03 -> Fri 09-04 is a business day -> due 09-04 23:59, met 09-08 10:00 (late)
    # 09-05 -> Sun, Mon (Labor Day, no work) -> due Tue 09-08 23:59, met 09-08 10:00
    # routine 14-day: 08-03, 08-10, 08-12, 08-17, 08-25, 08-27, 09-08, 09-21 never more than 14 days apart
    b = bundle(s, rain, {"A01": work}, ins=ins)
    exp = rows(sid, [("A01", "storm_inspection", "2026-08-11T23:59", "2026-08-12T09:30"),
                     ("A01", "storm_inspection", "2026-09-04T23:59", "2026-09-08T10:00")])
    return b, exp, ["storm", "business-day"]


def routine_clock(sid):
    """Seven-day clock runs from the actual date of the latest inspection; one row when never inspected."""
    s = site(sid, "Part 4.2.1", [("A01", "north slope", 100, "W1", None), ("A02", "south slope", 100, "W1", None),
                                 ("A03", "east lots", 60, "W1", None)])
    work = days("2026-08-03", "2026-09-30", skip=["2026-09-07"])
    ins = [insp(sid, "2026-08-03 08:30", ["A01", "A02"]),
           insp(sid, "2026-08-10 14:00", ["A01", "A02"], report="2026-08-11 14:00"),     # report exactly 24 h
           insp(sid, "2026-08-18 09:00", ["A01", "A02"]),                                 # day 8: late
           insp(sid, "2026-08-25 10:00", ["A01", "A02"]),                                 # 7 days after 08-18
           insp(sid, "2026-09-01 10:00", ["A01", "A02"], report="2026-09-02 10:01"),     # report 1 minute late
           insp(sid, "2026-09-08 10:00", ["A01", "A02"]),
           insp(sid, "2026-09-15 10:00", ["A01"]),
           insp(sid, "2026-09-24 10:00", ["A01", "A02"])]
    # A01: 08-03 -> 08-10 ok -> due 08-17, met 08-18 (late) -> due 08-25 ok -> 09-01 -> 09-08 -> 09-15 -> due 09-22,
    #      met 09-24 (late) -> due 10-01 (after the audit)
    # A02: same until 09-08 -> due 09-15, next 09-24 (late) -> due 10-01
    # A03: first logged 09-08, never inspected -> one row due 09-15 23:59, none
    b = bundle(s, {"2026-08-12": 18, "2026-09-10": 9},
               {"A01": work, "A02": work, "A03": days("2026-09-08", "2026-09-30")}, ins=ins)
    exp = rows(sid, [("A01", "routine_inspection", "2026-08-17T23:59", "2026-08-18T09:00"),
                     ("A01", "routine_inspection", "2026-09-22T23:59", "2026-09-24T10:00"),
                     ("A01", "inspection_report", "2026-09-02T10:00", "2026-09-02T10:01"),
                     ("A02", "routine_inspection", "2026-08-17T23:59", "2026-08-18T09:00"),
                     ("A02", "routine_inspection", "2026-09-15T23:59", "2026-09-24T10:00"),
                     ("A03", "routine_inspection", "2026-09-15T23:59", "none")])
    return b, exp, ["routine-inspection", "report"]


def reduced_frequency(sid):
    """Stabilized area: 14 days in the first month, one month after, back to regular when work resumes."""
    s = site(sid, "Part 4.2.2", [("A01", "building pad", 200, "W1", None), ("A02", "detention pond", 150, "W1", None)])
    a01 = days("2026-07-06", "2026-09-30", skip=["2026-09-07"])
    a02 = days("2026-07-06", "2026-07-24") | days("2026-09-14", "2026-09-30")
    stabs = [stab(sid, "A02", "2026-07-27 09:00", "2026-07-31 15:00")]
    # A02 stops Fri 07-24, restarts 09-14 (51 idle days): initiation due Mon 07-27 23:59 (met 09:00), completion due
    # 08-10 09:00 (3.50 acres at most, 14 days), met 07-31.  First month 07-31 .. 08-31, monthly from 08-31.
    ins = [insp(sid, f"{x} 08:00", ["A01", "A02"]) for x in ["2026-07-06", "2026-07-20"]]
    ins += [insp(sid, f"{x} 08:00", ["A01"]) for x in ["2026-08-03", "2026-08-17", "2026-08-31", "2026-09-14"]]
    ins += [insp(sid, "2026-08-20 09:00", ["A01"]), insp(sid, "2026-09-16 10:00", ["A01"]),
            insp(sid, "2026-09-28 08:00", ["A01"])]
    ins += [insp(sid, "2026-08-13 10:00", ["A02"]), insp(sid, "2026-08-28 10:00", ["A02"]),
            insp(sid, "2026-09-29 09:00", ["A02"])]
    # A02 routine: 07-20 -> due 07-27; change 07-31 (first month): due 07-31+14 = 08-14; met 08-13 -> due 08-27;
    #   next 08-28 (late); first month on 08-28 -> due 09-11; change 08-31 (monthly): due 09-30; change 09-14
    #   (work resumes): due 09-14+14 = 09-28; next 09-29 09:00 (late).
    # Storms: 08-19 (0.40) needs A01 only (A02 stabilized): due 08-20, met 08-20.  09-15 (0.30): A01 met 09-16;
    #   A02 regular again since 09-14: due 09-16 23:59, next A02 inspection 09-29 (late).
    rain = {"2026-08-19": 40, "2026-09-15": 30, "2026-08-05": 10}
    b = bundle(s, rain, {"A01": a01, "A02": a02}, stabs=stabs, ins=ins)
    exp = rows(sid, [("A02", "routine_inspection", "2026-08-27T23:59", "2026-08-28T10:00"),
                     ("A02", "storm_inspection", "2026-09-16T23:59", "2026-09-29T09:00"),
                     ("A02", "routine_inspection", "2026-09-28T23:59", "2026-09-29T09:00")])
    return b, exp, ["stabilized-area", "storm", "routine-inspection"]


def all_areas(sid, s, work):
    return lambda x: sorted(a["area_id"][len(sid) + 1:] for a in s["areas"] if work.get(a["area_id"][len(sid) + 1:])
                            and min(work[a["area_id"][len(sid) + 1:]]) <= x)


def five_acres_exact(sid):
    """Exactly 5.00 acres at most: the 14-day completion deadline applies."""
    s = site(sid, "Part 4.2.1", [("A01", "building pad", 300, "W1", None),
                                 ("A02", "parking lot", 200, "W1", "2026-08-07")])
    work = {"A01": days("2026-07-06", "2026-09-30", skip=["2026-09-07"]), "A02": days("2026-07-06", "2026-08-07")}
    stabs = [stab(sid, "A02", "2026-08-10 08:00", "2026-08-20 10:00")]
    # A02 ends for good Fri 08-07: initiation due Mon 08-10 23:59 (met 08:00); peak 3.00 + 2.00 = 5.00, not more
    # than 5.0 -> completion due 08-24 08:00, met 08-20 10:00.  No rows.
    b = bundle(s, {"2026-07-15": 60}, work, stabs=stabs, ins=weekly(sid, all_areas(sid, s, work)))
    return b, [], ["acreage", "stabilization"]


def five_acres_reopen(sid):
    """A late reopening pushes the project over 5.0 acres, so an earlier stabilization had only 7 days."""
    s = site(sid, "Part 4.2.1", [("A01", "building pad", 300, "W1", None), ("A02", "stockpile yard", 150, "W1", None),
                                 ("A03", "utility corridor", 60, "W1", None)])
    work = {"A01": days("2026-07-06", "2026-09-30", skip=["2026-09-07"]),
            "A02": days("2026-07-06", "2026-07-31") | days("2026-09-21", "2026-09-30"),
            "A03": days("2026-08-17", "2026-09-30", skip=["2026-09-07"])}
    stabs = [stab(sid, "A02", "2026-08-03 09:00", "2026-08-13 14:00")]
    # 07-06..07-31: 3.00 + 1.50 = 4.50; A02 disturbed through 08-13; from 08-17 3.00 + 0.60 = 3.60; from 09-21
    # 3.00 + 0.60 + 1.50 = 5.10 > 5.0 -> 7 days: completion due 08-03 09:00 + 7 = 08-10 09:00, met 08-13 14:00.
    b = bundle(s, {"2026-08-26": 70}, work, stabs=stabs, ins=weekly(sid, all_areas(sid, s, work)))
    exp = rows(sid, [("A02", "stabilization_completion", "2026-08-10T09:00", "2026-08-13T14:00")])
    return b, exp, ["acreage", "stabilization"]


def five_acres_same_day(sid):
    """An area counts as disturbed through the day its stabilization is completed."""
    s = site(sid, "Part 4.2.1", [("A01", "building pad", 300, "W1", None),
                                 ("A02", "west lots", 200, "W1", "2026-07-31"),
                                 ("A03", "lift station", 10, "W1", None)])
    work = {"A01": days("2026-07-06", "2026-09-30", skip=["2026-09-07"]), "A02": days("2026-07-06", "2026-07-31"),
            "A03": days("2026-08-13", "2026-09-30", skip=["2026-09-07"])}
    stabs = [stab(sid, "A02", "2026-08-03 09:00", "2026-08-13 09:00")]
    # 08-13: A01 3.00 + A02 2.00 (completed that day) + A03 0.10 = 5.10 -> 7 days: due 08-10 09:00, met 08-13 09:00.
    b = bundle(s, {"2026-08-04": 15}, work, stabs=stabs, ins=weekly(sid, all_areas(sid, s, work)))
    exp = rows(sid, [("A02", "stabilization_completion", "2026-08-10T09:00", "2026-08-13T09:00")])
    return b, exp, ["acreage", "stabilization"]


def stabilization_start(sid):
    """13 vs 14 idle days, initiation by the next business day, permanent stop."""
    s = site(sid, "Part 4.2.1", [("A01", "access road", 100, "W1", None), ("A02", "north slope", 100, "W1", None),
                                 ("A03", "south slope", 100, "W1", None), ("A04", "entrance drive", 100, "W1",
                                                                           "2026-09-09")])
    work = {"A01": days("2026-07-06", "2026-09-30", skip=["2026-09-07"]),
            "A02": days("2026-07-06", "2026-07-17") | days("2026-07-31", "2026-08-14") |
            days("2026-08-31", "2026-09-30", skip=["2026-09-07"]),
            "A03": days("2026-07-06", "2026-08-05") | days("2026-08-20", "2026-09-30", skip=["2026-09-07"]),
            "A04": days("2026-07-06", "2026-09-09", skip=["2026-09-07"])}
    stabs = [stab(sid, "A02", "2026-08-18 08:00", "2026-08-28 12:00"),
             stab(sid, "A04", "2026-09-10 15:00", "2026-09-25 08:00")]
    # A02: 07-17 -> 07-31 is 13 idle days (07-18..07-30): nothing required.  08-14 -> 08-31: 16 idle days;
    #   next business day after Fri 08-14 is Mon 08-17 -> due 08-17 23:59, initiated 08-18 08:00 (late);
    #   completion due 08-18 08:00 + 14 = 09-01 08:00, met 08-28.
    # A03: 08-05 -> 08-20 is 14 idle days (08-06..08-19): due Thu 08-06 23:59, never initiated.
    # A04: ends for good Wed 09-09: due Thu 09-10 23:59, initiated 09-10 15:00; completion due 09-24 15:00, met
    #   09-25 08:00 (late).  Peak 4.00 acres.
    b = bundle(s, {"2026-08-21": 35}, work, stabs=stabs, ins=weekly(sid, all_areas(sid, s, work)))
    exp = rows(sid, [("A02", "stabilization_initiation", "2026-08-17T23:59", "2026-08-18T08:00"),
                     ("A03", "stabilization_initiation", "2026-08-06T23:59", "none"),
                     ("A04", "stabilization_completion", "2026-09-24T15:00", "2026-09-25T08:00")])
    return b, exp, ["stabilization", "business-day"]


def sensitive_waters(sid):
    """Tier 2.5 water: storm inspections on a 4.2.1 site and 7-day stabilization; mercury impairment is not."""
    waters = [{"water_id": f"{sid}-W1", "name": "Quebrada Las Lajas", "impaired_for": [], "antidegradation_tier": "2.5"},
              {"water_id": f"{sid}-W2", "name": "Rio Bayamon", "impaired_for": ["Mercury", "Fecal Coliform"],
               "antidegradation_tier": "1"}]
    s = site(sid, "Part 4.2.1", [("A01", "east lots", 100, "W1", None), ("A02", "west lots", 100, "W2", None),
                                 ("A03", "north slope", 100, "W1", "2026-07-24")], waters=waters)
    work = {"A01": days("2026-07-06", "2026-09-30", skip=["2026-09-07"]),
            "A02": days("2026-07-06", "2026-09-30", skip=["2026-09-07"]), "A03": days("2026-07-06", "2026-07-24")}
    stabs = [stab(sid, "A03", "2026-07-27 10:00", "2026-08-03 11:00")]
    # Storm Wed 08-12 (0.45): A01 drains to a Tier 2.5 water -> due Thu 08-13 23:59, next A01 inspection Mon 08-17.
    #   A02 (mercury, fecal coliform) is not sensitive and the site is on 4.2.1: no storm inspection.
    # A03 ends Fri 07-24: initiation due Mon 07-27 23:59 (met 10:00); Tier 2.5 -> 7 days: due 08-03 10:00, met 11:00.
    b = bundle(s, {"2026-08-12": 45, "2026-08-13": 4}, work, stabs=stabs, ins=weekly(sid, all_areas(sid, s, work)))
    exp = rows(sid, [("A01", "storm_inspection", "2026-08-13T23:59", "2026-08-17T08:00"),
                     ("A03", "stabilization_completion", "2026-08-03T10:00", "2026-08-03T11:00")])
    return b, exp, ["sensitive-water", "storm", "stabilization"]


def repeat_fixes(sid):
    """The fourth and later occurrences of the same fix to the same control at the same location are corrective
    actions; the third is still routine maintenance."""
    s = site(sid, "Part 4.2.2", [("A01", "detention pond", 200, "W1", None)])
    work = {"A01": days("2026-07-06", "2026-09-30", skip=["2026-09-07"])}
    weds = ["2026-07-08", "2026-07-15", "2026-07-22", "2026-07-29", "2026-08-05", "2026-08-12", "2026-08-19",
            "2026-08-26", "2026-09-02", "2026-09-09", "2026-09-16", "2026-09-23", "2026-09-30"]
    ins = [insp(sid, f"{x} 10:00", ["A01"]) for x in weds]
    R, S = "routine maintenance", "remove accumulated sediment"
    finds = [
        find(sid, "A01", "2026-07-15 10:00", "SF-11", "Sta 1+20", S, R, "2026-07-16 09:00"),             # 1st
        find(sid, "A01", "2026-07-22 10:00", "SF-11", "Sta 3+40", S, R, "2026-07-23 09:00"),             # other loc
        find(sid, "A01", "2026-07-29 10:00", "SF-11", "Sta 1+20", S, R, "2026-07-30 15:00"),             # 2nd
        find(sid, "A01", "2026-08-05 10:00", "SF-11", "Sta 3+40", S, R, "2026-08-06 09:00"),
        # 3rd: still routine; infeasibility documented -> 7 days: due 08-19 10:00, met 08-17
        find(sid, "A01", "2026-08-12 10:00", "SF-11", "Sta 1+20", S, R, "2026-08-17 10:00", infeas=True),
        find(sid, "A01", "2026-08-19 10:00", "SF-11", "Sta 3+40", S, R, "2026-08-20 09:00"),             # 3rd there
        # 4th: corrective action, next business day Thu 08-27 23:59 (no 7-day allowance); no log entries
        find(sid, "A01", "2026-08-26 10:00", "SF-11", "Sta 1+20", S, R, "2026-08-28 14:00", infeas=True),
        # 5th: handled as a corrective action on time, log at exactly 24 h, SWPPP at exactly 7 days
        find(sid, "A01", "2026-09-09 10:00", "SF-11", "Sta 1+20", S, R, "2026-09-10 11:00",
             log_id="2026-09-09 16:00", log_done="2026-09-11 11:00", swppp=True, swppp_at="2026-09-17 11:00"),
        # same control and location, different fix: first occurrence, due Thu 09-17 23:59, met Fri 09-18
        find(sid, "A01", "2026-09-16 10:00", "SF-11", "Sta 1+20", "re-trench fabric toe", R, "2026-09-18 09:00"),
        # significant repair: done at exactly 7 days; identified entry 1 minute late; later deadlines after 09-30
        find(sid, "A01", "2026-09-23 10:00", "ST-12", "Sta 2+00", "rebuild sediment trap", "significant repair",
             "2026-09-30 10:00", log_id="2026-09-24 10:01", log_done="2026-09-30 15:00", swppp=True,
             condition="sediment trap outlet washed out"),
    ]
    b = bundle(s, {"2026-07-21": 8}, work, ins=ins, finds=finds)
    exp = rows(sid, [("A01", "ca_log_identified", "2026-08-27T10:00", "none"),
                     ("A01", "corrective_action", "2026-08-27T23:59", "2026-08-28T14:00"),
                     ("A01", "ca_log_completed", "2026-08-29T14:00", "none"),
                     ("A01", "routine_maintenance", "2026-09-17T23:59", "2026-09-18T09:00"),
                     ("A01", "ca_log_identified", "2026-09-24T10:00", "2026-09-24T10:01")])
    return b, exp, ["repeat-fix", "maintenance", "corrective-action"]


def corrective_actions(sid):
    """Seven calendar days from the time of discovery, log entries within 24 hours, SWPPP within 7 days."""
    s = site(sid, "Part 4.2.1", [("A01", "parking lot", 150, "W1", None)])
    work = {"A01": days("2026-07-06", "2026-09-30", skip=["2026-09-07"])}
    N = "new or replacement control"
    finds = [
        find(sid, "A01", "2026-07-13 08:00", "IP-14", "Inlet 3", "install new inlet protection", N, "2026-07-20 08:00",
             log_id="2026-07-14 08:00", log_done="2026-07-21 08:01", swppp=True, swppp_at="2026-07-27 08:00",
             condition="inlet protection missing at new inlet"),
        find(sid, "A01", "2026-08-10 08:00", "ST-15", "Sta 4+00", "rebuild sediment trap", "significant repair",
             "2026-08-17 08:01", log_id="2026-08-10 15:00", log_done="2026-08-17 12:00", swppp=True,
             swppp_at="2026-08-25 10:00", condition="sediment trap outlet washed out"),
        find(sid, "A01", "2026-08-31 08:00", "SF-16", "East line", "install new silt fence", N, None,
             log_id="2026-08-31 11:00", condition="silt fence never installed at east property line"),
    ]
    # 07-13: done exactly 7 days later (on time); identified log exactly 24 h; completed log due 07-21 08:00, met
    #   08:01 (late); SWPPP due 07-27 08:00, met 08:00.
    # 08-10: due 08-17 08:00, done 08:01 (late); SWPPP due 08-24 08:01, met 08-25 10:00 (late).
    # 08-31: due 09-07 08:00 (calendar days, Labor Day irrelevant), never done.
    b = bundle(s, {"2026-08-11": 20}, work, ins=weekly(sid, lambda x: ["A01"]), finds=finds)
    exp = rows(sid, [("A01", "ca_log_completed", "2026-07-21T08:00", "2026-07-21T08:01"),
                     ("A01", "corrective_action", "2026-08-17T08:00", "2026-08-17T08:01"),
                     ("A01", "swppp_update", "2026-08-24T08:01", "2026-08-25T10:00"),
                     ("A01", "corrective_action", "2026-09-07T08:00", "none")])
    return b, exp, ["corrective-action"]


SITES = [business_days, storms, routine_clock, reduced_frequency, five_acres_exact, five_acres_reopen,
         five_acres_same_day, stabilization_start, sensitive_waters, repeat_fixes, corrective_actions]
