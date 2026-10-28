"""Generator-side model of the 2022 CGP requirements audited by stormwater-inspection-audit (authoring tool).

This is the third implementation. It works on one site "bundle" at a time and, in strict mode, also reports the
places where a second defensible reading of the permit could change the answer, so the generator can repair or
reject them.

Bundle: {"site": site record, "rain": {date: hundredths}, "work": {area_id: set(dates)},
         "stabs": [...], "insp": [...], "finds": [...], "track": [...]} with datetimes already parsed.
"""
from datetime import date, datetime, time, timedelta

END_DAY = date(2026, 9, 30)
END = datetime(2026, 9, 30, 23, 59)
DAY = timedelta(days=1)


def eod(d):
    return datetime.combine(d, time(23, 59))


def add_month(d):
    y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    for dd in (d.day, 31, 30, 29, 28):
        if dd <= d.day:
            try:
                return date(y, m, dd)
            except ValueError:
                continue


def sensitive(site, area):
    w = next(x for x in site["receiving_waters"] if x["water_id"] == area["discharges_to"])
    imp = {p.lower() for p in w["impaired_for"]}
    return bool(imp & {"sedimentation/siltation", "total phosphorus", "total nitrogen"}) or \
        w["antidegradation_tier"] in ("2", "2.5", "3")


def sim(b, strict=False):
    site = b["site"]
    sid = site["site_id"]
    work = b["work"]
    biz = set().union(*work.values()) if work else set()
    flags = []
    rows = []

    def next_biz(d):                       # first business day strictly after d, or None within the audit
        d += DAY
        while d <= END_DAY:
            if d in biz:
                return d
            d += DAY
        return None

    def row(area, req, due, met):
        if due <= END and (met is None or met > due):
            rows.append((sid, area, req, due.strftime("%Y-%m-%dT%H:%M"),
                         met.strftime("%Y-%m-%dT%H:%M") if met else "none"))

    areas = {a["area_id"]: a for a in site["areas"]}
    sched7 = site["inspection_schedule"] == "Part 4.2.1"

    # ---- per-area stabilization history: completion dates and modes
    comp = {a: sorted(s["completed"].date() for s in b["stabs"] if s["area_id"] == a and s["completed"])
            for a in areas}

    def mode(a, d):
        cs = [c for c in comp[a] if c <= d]
        if not cs:
            return "regular"
        c = cs[-1]
        if any(c < w <= d for w in work[a]):
            return "regular"
        return "first" if d < add_month(c) else "monthly"

    def changes(a):
        out = []
        for c in comp[a]:
            out.append(c)
            later = sorted(w for w in work[a] if w > c)
            r = later[0] if later else None
            m = add_month(c)
            if r is None or r > m:
                out.append(m)
            if r is not None:
                out.append(r)
        return sorted(set(x for x in out if x <= END_DAY))

    def limit(a, d, m):
        if m == "regular":
            return d + timedelta(days=7 if sched7 or sensitive(site, areas[a]) else 14)
        if m == "first":
            return d + timedelta(days=14)
        return add_month(d)

    insp_by_area = {a: sorted((i["completed"] for i in b["insp"] if a in i["areas"])) for a in areas}

    # ---- routine inspections (Parts 4.2, 4.3.1, 4.4.1)
    for a in areas:
        if not work[a]:
            continue
        first = min(work[a])
        last = first
        due = eod(limit(a, first, mode(a, first)))
        items = [(c, 0, None) for c in changes(a) if c >= first] + \
                [(t.date(), 1, t) for t in insp_by_area[a] if t.date() >= first]
        items.sort()
        for d, kind, t in items:
            if kind == 0:
                if strict and (due.date() < d or (due.date() == d and
                                                  not any(x.date() == d for x in insp_by_area[a]))):
                    flags.append(("change_overdue", a, due.date()))
                due = eod(limit(a, max(last, d), mode(a, d)))
            else:
                if t > due:
                    if strict and due.date() not in biz:
                        flags.append(("routine_nonbiz", a, due.date()))
                    row(a, "routine_inspection", due, t)
                last = d
                due = eod(limit(a, d, mode(a, d)))
        if due <= END:
            if strict and due.date() not in biz:
                flags.append(("routine_nonbiz", a, due.date()))
            row(a, "routine_inspection", due, None)

    # ---- storm inspections (Part 4.2.2, 4.3.1, footnotes 67-69)
    wet = sorted(d for d, v in b["rain"].items() if v >= 1)
    storms, cur = [], []
    for d in wet:
        if cur and d == cur[-1] + DAY:
            cur.append(d)
        else:
            if cur:
                storms.append(cur)
            cur = [d]
    if cur:
        storms.append(cur)
    triggers = []
    for s in storms:
        big = [d for d in s if b["rain"][d] >= 25]
        if big:
            triggers.append(big[0])
            if big[-1] != big[0]:
                triggers.append(big[-1])
    for a in areas:
        if not work[a] or not (not sched7 or sensitive(site, areas[a])):
            continue
        first = min(work[a])
        for d in triggers:
            if d < first or mode(a, d) != "regular":
                if strict and d >= first and mode(a, d + DAY) == "regular":
                    flags.append(("storm_mode", a, d))
                continue
            nb = d + DAY if d + DAY in biz else next_biz(d + DAY)
            if nb is None:
                continue
            if strict and any(d < c <= nb for c in changes(a)):
                flags.append(("storm_mode", a, d))
            met = next((t for t in insp_by_area[a] if t.date() > d), None)
            row(a, "storm_inspection", eod(nb), met)

    # ---- inspection reports (Part 4.7.1)
    for i in b["insp"]:
        row(i["areas"][0], "inspection_report", i["completed"] + timedelta(hours=24), i["report_completed"])

    # ---- maintenance and corrective actions (Parts 2.1.4, 5.1, 5.2.1, 5.4.1)
    seen = {}
    for f in sorted(b["finds"], key=lambda x: (x["discovered"], x.get("finding_id", ""))):
        disc = f["discovered"]
        a = f["area_id"]
        if f["needs"] == "routine maintenance":
            k = seen.get((f["control_id"], f["location"], f["fix"]), 0) + 1
            seen[(f["control_id"], f["location"], f["fix"])] = k
            ca = k >= 4
        else:
            ca = True
        nb = next_biz(disc.date())
        if not ca:
            due = disc + timedelta(days=7) if f["infeasibility_documented"] else (eod(nb) if nb else None)
            if due:
                row(a, "routine_maintenance", due, f["completed"])
            continue
        if f["needs"] == "routine maintenance":
            due = eod(nb) if nb else None
        else:
            due = disc + timedelta(days=7)
        if due:
            row(a, "corrective_action", due, f["completed"])
        row(a, "ca_log_identified", disc + timedelta(hours=24), f["log_identified"])
        if f["completed"]:
            row(a, "ca_log_completed", f["completed"] + timedelta(hours=24), f["log_completed"])
            if f["swppp_change"]:
                row(a, "swppp_update", f["completed"] + timedelta(days=7), f["swppp_updated"])

    # ---- track-out (Part 2.2.4)
    for t in b["track"]:
        d = t["occurred"].date()
        nb = d if d in biz else next_biz(d)
        if nb:
            row(t["area_id"], "trackout_removal", eod(nb), t["removed"])

    # ---- stabilization (Part 2.2.14, footnotes 38-41)
    days = []
    d = date(2026, 1, 1)
    while d <= END_DAY:
        days.append(d)
        d += DAY
    peak = 0
    state = {a: False for a in areas}
    for d in days:
        tot = 0
        for a in areas:
            if d in work[a]:
                state[a] = True
                if strict and d in comp[a]:
                    flags.append(("work_on_completion_day", a, d))
            if state[a]:
                tot += areas[a]["acres_hundredths"]
            if d in comp[a]:
                state[a] = False
        peak = max(peak, tot)
    big_site = peak > 500
    for a in areas:
        ws = sorted(work[a])
        done = areas[a].get("work_completed_on")
        for i, w in enumerate(ws):
            n = ws[i + 1] if i + 1 < len(ws) else None
            if n is None and w != done:
                continue                       # still under construction after the audit, no 14-day break
            if n is not None and (n - w).days - 1 < 14:
                continue
            nb = next_biz(w)
            if strict and nb is not None and n is not None and nb >= n:
                flags.append(("stab_nobiz", a, w))
            if nb is None:
                continue
            recs = sorted((s for s in b["stabs"] if s["area_id"] == a and s["initiated"].date() >= w
                           and (n is None or s["initiated"].date() < n)), key=lambda s: s["initiated"])
            init = recs[0] if recs else None
            row(a, "stabilization_initiation", eod(nb), init["initiated"] if init else None)
            if init:
                lim = 7 if (sensitive(site, areas[a]) or big_site) else 14
                if strict and n is not None and (init["completed"] is None or init["completed"].date() >= n):
                    flags.append(("stab_after_resume", a, w))
                row(a, "stabilization_completion", init["initiated"] + timedelta(days=lim), init["completed"])
    rows.sort()
    return rows, flags, {"peak": peak}
