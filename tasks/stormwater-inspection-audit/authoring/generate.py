#!/usr/bin/env python3
"""Generate the stormwater-inspection-audit inputs (authoring tool; not part of the agent or verifier images).

Writes identical data to tasks/stormwater-inspection-audit/environment/data and tests/data, plus tests/golden.json
(hand-worked rows of the planted sites) and tests/case_tags.json (rule families of the planted sites).
Random filler sites are repaired or regenerated until the strict model (sim.py) finds no case where a second
defensible reading of the permit would change the answer.
"""
import json
import random
import sys
from datetime import date, datetime, time, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from sim import DAY, END_DAY, add_month, sensitive, sim  # noqa: E402
import planted  # noqa: E402

SEED = 40122
ROOT = HERE.parent                                     # the task folder (this file lives in authoring/)
START = date(2026, 1, 1)
N_FILLER = 28

TOWNS = ["Caguas", "Bayamon", "Carolina", "Humacao", "Gurabo", "Juncos", "Cayey", "Dorado", "Manati", "Arecibo",
         "Toa Alta", "Trujillo Alto", "Vega Baja", "Fajardo", "Rio Grande", "Canovanas", "Aguadilla", "Mayaguez",
         "Hatillo", "Barceloneta", "Cidra", "Las Piedras", "Naguabo", "Yabucoa", "San Lorenzo", "Corozal",
         "Naranjito", "Morovis", "Ciales", "Isabela", "Camuy", "Quebradillas"]
PROJECTS = ["medical office building", "retail center", "school expansion", "housing subdivision", "distribution warehouse",
            "highway interchange ramp", "water storage tank", "solar farm access roads", "parking structure",
            "community center", "pharmaceutical plant addition", "hotel annex", "fire station", "bridge approach",
            "apartment complex", "logistics yard", "sports complex", "clinic", "data center pad", "sewer pump station"]
WATERS = ["Rio Grande de Loiza", "Rio Bayamon", "Rio de la Plata", "Rio Gurabo", "Rio Cagitas", "Quebrada Blasina",
          "Rio Hondo", "Rio Cibuco", "Rio Manati", "Rio Grande de Arecibo", "Quebrada Grande", "Rio Fajardo",
          "Rio Espiritu Santo", "Rio Canovanas", "Quebrada Las Lajas", "Rio Culebrinas", "Rio Yaguez", "Rio Humacao",
          "Quebrada Frontera", "Rio Turabo"]
IMPAIR_SENS = ["Sedimentation/Siltation", "Total Phosphorus", "Total Nitrogen"]
IMPAIR_OTHER = ["Mercury", "Fecal Coliform", "Enterococci", "Copper", "pH"]
AREA_DESC = ["building pad", "parking lot", "access road", "utility corridor", "detention pond", "stockpile yard",
             "north slope", "south slope", "east lots", "west lots", "entrance drive", "lift station"]
ACTIVITIES = ["clearing", "grubbing", "grading", "excavation", "trenching", "fill placement", "topsoil stockpiling",
              "subgrade compaction"]
CONTROLS = [("SF", "silt fence"), ("IP", "inlet protection"), ("CE", "stabilized construction exit"),
            ("ST", "sediment trap"), ("FS", "compost filter sock"), ("DD", "diversion dike")]
FIXES = {"SF": ["remove accumulated sediment", "re-trench fabric toe", "replace broken stakes"],
         "IP": ["replace filter bag", "remove sediment from inlet insert"],
         "CE": ["add stone to exit pad", "remove sediment from exit pad"],
         "ST": ["remove accumulated sediment", "repair outlet stone"],
         "FS": ["reseat sock", "remove accumulated sediment"],
         "DD": ["repair eroded crest", "reshape channel"]}
SIG = ["silt fence collapsed along 40 feet", "sediment trap outlet washed out", "inlet protection torn open",
       "diversion dike breached", "construction exit undermined"]
NEW = ["inlet protection missing at new inlet", "no perimeter control below new stockpile",
       "silt fence never installed at east property line", "check dams needed in new swale"]


def fmt(t):
    return t.strftime("%Y-%m-%dT%H:%M")


def at(d, hh, mm=0):
    return datetime.combine(d, time(hh, mm))


class Site:
    """Build one random filler site."""

    def __init__(self, rng, sid, n):
        self.rng, self.sid, self.n = rng, sid, n

    def build(self):
        r = self.rng
        sid = self.sid
        start_h = r.choice([(6, 30), (7, 0), (7, 0), (7, 30)])
        end_h = r.choice([(15, 0), (15, 30), (15, 30), (16, 0), (17, 0)])
        nw = r.choice([1, 1, 2])
        waters = []
        for k in range(nw):
            kind = r.random()
            imp, tier = [], "1"
            if kind < 0.18:
                imp = [r.choice(IMPAIR_SENS)]
            elif kind < 0.28:
                tier = r.choice(["2", "2.5", "3"])
            elif kind < 0.55:
                imp = r.sample(IMPAIR_OTHER, r.choice([1, 2]))
            waters.append({"water_id": f"{sid}-W{k + 1}", "name": r.choice(WATERS), "impaired_for": imp,
                           "antidegradation_tier": tier})
        na = r.choice([3, 4, 4, 5, 5, 6])
        commence = START + timedelta(days=r.randint(4, 120))
        while commence.weekday() >= 5:
            commence += DAY
        acres_target = r.choice([None, None, 500, 499, 501, 510, 480])
        areas = []
        for k in range(na):
            areas.append({"area_id": f"{sid}-A{k + 1:02d}", "description": r.choice(AREA_DESC),
                          "acres_hundredths": r.randint(40, 260), "discharges_to": r.choice(waters)["water_id"]})
        site = {"site_id": sid, "project": f"{r.choice(PROJECTS)}, {r.choice(TOWNS)}",
                "inspection_schedule": r.choice(["Part 4.2.1", "Part 4.2.2", "Part 4.2.2"]),
                "normal_working_hours": {"start": f"{start_h[0]:02d}:{start_h[1]:02d}",
                                         "end": f"{end_h[0]:02d}:{end_h[1]:02d}"},
                "receiving_waters": waters, "areas": areas}
        self.site = site
        self.hours = (start_h, end_h)
        self.rain = self.make_rain()
        self.work = self.make_work(commence, acres_target)
        self.stabs = self.make_stabs()
        return site

    # ---- rain (hundredths of an inch per calendar day, measurable days only)
    def make_rain(self):
        r = self.rng
        rain = {}
        d = START
        while d <= END_DAY:
            wet = 0.45 if d.month >= 5 else 0.28
            if r.random() < wet:
                x = r.random()
                if x < 0.35:
                    v = r.randint(1, 15)
                elif x < 0.65:
                    v = r.randint(20, 30)
                elif x < 0.9:
                    v = r.randint(31, 90)
                else:
                    v = r.randint(91, 260)
                rain[d] = v
            d += DAY
        return rain

    # ---- construction days by area
    def make_work(self, commence, acres_target):
        r = self.rng
        site = self.site
        sat = r.random() < 0.3
        off = set(r.sample([date(2026, 1, 6), date(2026, 1, 19), date(2026, 2, 16), date(2026, 3, 23),
                            date(2026, 4, 3), date(2026, 5, 25), date(2026, 6, 19), date(2026, 7, 3),
                            date(2026, 7, 27), date(2026, 9, 7)], r.randint(3, 8)))

        def workday(d):
            if d in off:
                return False
            if d.weekday() == 6:
                return False
            if d.weekday() == 5 and not (sat and r.random() < 0.7):
                return False
            if self.rain.get(d, 0) >= 60 and r.random() < 0.5:
                return False
            return True

        cal = {}
        d = commence
        while d <= END_DAY:
            cal[d] = workday(d)
            d += DAY
        cal[commence] = True

        def snap_fwd(d):
            while d <= END_DAY and not cal.get(d):
                d += DAY
            return d

        def snap_back(d, lo):
            while d > lo and not cal.get(d):
                d -= DAY
            return d

        work = {}
        areas = site["areas"]
        for k, a in enumerate(areas):
            s = commence if k == 0 else snap_fwd(commence + timedelta(days=r.randint(0, 70)))
            days = set()
            cur = s
            keep_going = k == 0
            while cur <= END_DAY:
                seg_end = min(END_DAY, cur + timedelta(days=r.randint(8, 55)))
                seg_end = snap_back(seg_end, cur)
                d = cur
                while d <= seg_end:
                    if cal.get(d) and (d in (cur, seg_end) or r.random() < 0.88):
                        days.add(d)
                    d += DAY
                x = r.random()
                if x < 0.08 and not keep_going and seg_end < END_DAY - timedelta(days=20):
                    a["work_completed_on"] = max(days) if days else None
                    break                                       # permanent cessation
                if x < 0.45:
                    gap = r.randint(2, 11)
                elif x < 0.7:
                    gap = r.choice([12, 13, 13, 14, 14, 15])
                else:
                    gap = r.randint(16, 50)
                nxt = snap_fwd(seg_end + timedelta(days=gap + 1))
                cur = nxt
            days = {d for d in days if d <= END_DAY}
            if not a.get("work_completed_on"):
                tail = max(days)
                if tail < END_DAY - timedelta(days=13):     # ongoing areas keep working into the last two weeks
                    d = snap_fwd(END_DAY - timedelta(days=r.randint(0, 12)))
                    if d > END_DAY:
                        d = snap_back(END_DAY, tail)
                    days.add(d)
            work[a["area_id"]] = days
        # keep every calendar day with work in the area-0 run (the site office never closes for long)
        a0 = areas[0]["area_id"]
        for d, ok in cal.items():
            if ok and r.random() < 0.6:
                work[a0].add(d)
        if acres_target:
            tot = sum(a["acres_hundredths"] for a in areas)
            scale = acres_target / tot * (1.6 if len(areas) > 4 else 1.25)
            for a in areas:
                a["acres_hundredths"] = max(25, round(a["acres_hundredths"] * scale))
        return work

    # ---- stabilization records for long gaps and permanent stops, plus some voluntary ones
    def make_stabs(self):
        r = self.rng
        site = self.site
        biz = set().union(*self.work.values())
        stabs = []

        def nbiz(d):
            d += DAY
            while d <= END_DAY:
                if d in biz:
                    return d
                d += DAY
            return None

        for a in site["areas"]:
            aid = a["area_id"]
            ws = sorted(self.work[aid])
            for i, w in enumerate(ws):
                n = ws[i + 1] if i + 1 < len(ws) else None
                inactive = (n - w).days - 1 if n else 999
                if inactive < 5:
                    continue
                if inactive < 14 and r.random() > 0.15:
                    continue
                nb = nbiz(w)
                if nb is None:
                    continue
                x = r.random()
                if x < 0.05 and inactive >= 14:
                    continue                                    # never initiated
                if x < 0.12:
                    idate = w
                elif x < 0.8:
                    idate = nb
                else:
                    idate = nb + timedelta(days=r.randint(1, 4))
                if n is not None and idate >= n - DAY:
                    continue
                itime = at(idate, r.randint(13 if idate == w else 7, 16), r.choice([0, 15, 30, 45]))
                span = r.choice([3, 5, 6, 7, 7, 8, 9, 10, 12, 13, 14, 14, 15])
                cdate = idate + timedelta(days=span)
                ctime = itime + timedelta(days=span) + timedelta(minutes=r.choice([-90, -30, 0, 0, 1, 45]))
                if n is not None and ctime.date() >= n:
                    cdate = n - DAY
                    if cdate <= idate:
                        continue
                    ctime = at(cdate, 11, 0)
                if ctime.date() > END_DAY:
                    ctime = None
                stabs.append({"area_id": aid, "initiated": itime, "completed": ctime,
                              "measure": r.choice(["hydroseed and mulch", "erosion control blanket", "straw mulch",
                                                   "gravel cover", "sod"])})
        return stabs

    # ---- inspections, as a site inspector would plan them
    def make_inspections(self):
        r = self.rng
        site = self.site
        biz = sorted(set().union(*self.work.values()))
        sched7 = site["inspection_schedule"] == "Part 4.2.1"
        sens = any(sensitive(site, a) for a in site["areas"])
        cadence = 7 if (sched7 or sens) else 14
        comp = {a["area_id"]: sorted(s["completed"].date() for s in self.stabs
                                     if s["area_id"] == a["area_id"] and s["completed"]) for a in site["areas"]}

        def stabilized(aid, d):
            cs = [c for c in comp[aid] if c <= d]
            return bool(cs) and not any(cs[-1] < w <= d for w in self.work[aid])

        trig = set()
        for d, v in self.rain.items():
            if v >= 25:
                trig.add(d)
        insp = []
        last = None
        handled = set()
        slip = 0
        for d in biz:
            begun = [a["area_id"] for a in site["areas"] if self.work[a["area_id"]] and min(self.work[a["area_id"]]) <= d]
            if not begun:
                continue
            go = False
            if last is None or (d - last).days >= cadence - r.choice([0, 0, 1, 2, 3]) + slip:
                go = True
                slip = r.choice([0] * 9 + [1, 2, 3])
            due_storms = [t for t in trig if t < d and t not in handled]
            if due_storms:
                x = r.random()
                if x < 0.9 or min(due_storms) < d - timedelta(days=4):
                    go = True
                    handled.update(due_storms)
                elif x < 0.93:
                    handled.update(due_storms)              # skipped
            if go:
                handled.update(t for t in trig if t < d)
                cover = []
                for aid in begun:
                    if stabilized(aid, d) and r.random() < 0.55:
                        continue
                    if r.random() < 0.03:
                        continue
                    cover.append(aid)
                if cover:
                    self.add_insp(insp, d, cover)
                    last = d
        return insp

    def add_insp(self, insp, d, cover, t=None):
        r = self.rng
        (sh, sm), (eh, em) = self.hours
        lo = sh * 60 + sm + 30
        hi = eh * 60 + em - 30
        if t is None:
            m = r.randint(lo, hi)
            t = at(d, m // 60, m % 60)
        x = r.random()
        if x < 0.88:
            rep = t + timedelta(minutes=r.randint(30, 20 * 60))
        elif x < 0.93:
            rep = t + timedelta(hours=24)
        elif x < 0.95:
            rep = t + timedelta(hours=24, minutes=1)
        elif x < 0.99:
            rep = t + timedelta(minutes=r.randint(25 * 60, 70 * 60))
        else:
            rep = None
        insp.append({"completed": t, "areas": sorted(cover), "report_completed": rep})

    # ---- findings on inspections
    def make_findings(self, insp):
        r = self.rng
        site = self.site
        biz = set().union(*self.work.values())

        def nbiz(d):
            d += DAY
            while d <= END_DAY:
                if d in biz:
                    return d
                d += DAY
            return None

        controls = {}
        for a in site["areas"]:
            cs = []
            for k, (code, name) in enumerate(r.sample(CONTROLS, r.randint(2, 4))):
                cs.append((f"{code}-{a['area_id'][-2:]}{k + 1}", code, name,
                           f"Sta {r.randint(0, 9)}+{r.randint(0, 9)}{r.choice([0, 5])}"))
            controls[a["area_id"]] = cs
        chains = {}
        for a in site["areas"]:
            if r.random() < 0.6:
                cid, code, name, loc = r.choice(controls[a["area_id"]])
                chains[a["area_id"]] = [cid, code, loc, r.choice(FIXES[code]), r.randint(2, 6)]
        counts = {}
        finds = []
        for i in sorted(insp, key=lambda x: x["completed"]):
            for aid in i["areas"]:
                ch = chains.get(aid)
                if ch and ch[4] > 0 and r.random() < 0.55:
                    ch[4] -= 1
                    cid, code, loc, fix = ch[0], ch[1], ch[2], ch[3]
                    needs = "routine maintenance"
                elif r.random() < 0.12:
                    cid, code, name, loc = r.choice(controls[aid])
                    y = r.random()
                    needs = "routine maintenance" if y < 0.72 else ("significant repair" if y < 0.88
                                                                    else "new or replacement control")
                    fix = (r.choice(FIXES[code]) if needs == "routine maintenance" else
                           f"rebuild {name}" if needs == "significant repair" else f"install new {name}")
                else:
                    continue
                disc = i["completed"]
                key = (cid, loc, fix)
                if needs == "routine maintenance":
                    counts[key] = counts.get(key, 0) + 1
                k = counts.get(key, 0)
                treat_ca = needs != "routine maintenance" or (k >= 4 and r.random() < 0.5)
                infeas = needs == "routine maintenance" and r.random() < (0.35 if k >= 3 else 0.12)
                nb = nbiz(disc.date())
                x = r.random()
                if infeas or needs != "routine maintenance":
                    target = disc + timedelta(days=7)
                    if x < 0.55:
                        comp = disc + timedelta(hours=r.randint(20, 140))
                    elif x < 0.7:
                        comp = target
                    elif x < 0.92:
                        comp = target + timedelta(minutes=r.choice([1, 30, 600, 1500, 3000]))
                    else:
                        comp = None
                else:
                    if nb is None:
                        comp = None
                    elif x < 0.7:
                        comp = at(r.choice([disc.date(), nb]), r.randint(8, 15), r.choice([0, 20, 40]))
                        if comp < disc:
                            comp = disc + timedelta(hours=2)
                    elif x < 0.8:
                        comp = at(nb, 23, 59)
                    elif x < 0.97:
                        later = nbiz(nb) or nb
                        comp = at(later, r.randint(8, 15), 0) if later != nb else at(nb + DAY, 9, 0)
                    else:
                        comp = None
                if comp and comp.date() > END_DAY:
                    comp = None
                f = {"area_id": aid, "inspection": i, "discovered": disc, "control_id": cid, "location": loc,
                     "fix": fix, "needs": needs, "infeasibility_documented": infeas, "completed": comp,
                     "log_identified": None, "log_completed": None, "swppp_change": False, "swppp_updated": None,
                     "condition": (r.choice(SIG) if needs == "significant repair" else
                                   r.choice(NEW) if needs == "new or replacement control" else f"needs: {fix}")}
                if treat_ca:
                    y = r.random()
                    f["log_identified"] = (None if y < 0.04 else disc + timedelta(hours=24) if y < 0.14 else
                                           disc + timedelta(hours=24, minutes=r.choice([1, 90])) if y < 0.22 else
                                           disc + timedelta(minutes=r.randint(20, 22 * 60)))
                    if comp:
                        y = r.random()
                        f["log_completed"] = (None if y < 0.05 else comp + timedelta(hours=24) if y < 0.12 else
                                              comp + timedelta(hours=26) if y < 0.2 else
                                              comp + timedelta(minutes=r.randint(10, 20 * 60)))
                        if needs == "new or replacement control" or r.random() < 0.3:
                            f["swppp_change"] = True
                            y = r.random()
                            f["swppp_updated"] = (None if y < 0.06 else comp + timedelta(days=7) if y < 0.15 else
                                                  comp + timedelta(days=r.choice([8, 9])) if y < 0.25 else
                                                  comp + timedelta(days=r.randint(1, 6), hours=r.randint(0, 5)))
                    for k2 in ("log_identified", "log_completed", "swppp_updated"):
                        if f[k2] and f[k2].date() > END_DAY:
                            f[k2] = None
                finds.append(f)
        return finds

    # ---- track-out events
    def make_trackout(self):
        r = self.rng
        site = self.site
        biz = set().union(*self.work.values())
        out = []
        first = min(biz)
        d = first + timedelta(days=r.randint(3, 15))
        while d <= END_DAY - timedelta(days=3):
            onbiz = d in biz
            if onbiz or r.random() < 0.5:
                aid = r.choice([a["area_id"] for a in site["areas"] if self.work[a["area_id"]] and
                                min(self.work[a["area_id"]]) <= d] or [site["areas"][0]["area_id"]])
                occ = at(d, r.randint(7, 17), r.choice([0, 10, 25, 40, 55]))
                nb = d if onbiz else min((x for x in biz if x > d), default=None)
                x = r.random()
                if nb is None:
                    rem = None
                elif x < 0.6:
                    rem = at(nb, r.randint(max(occ.hour, 8) if nb == d else 8, 18), r.choice([0, 30]))
                    if rem < occ:
                        rem = occ + timedelta(hours=1)
                elif x < 0.7:
                    rem = at(nb, 23, 59)
                elif x < 0.95:
                    rem = at(nb + DAY, r.randint(7, 10), 0)
                else:
                    rem = None
                if rem and rem.date() > END_DAY:
                    rem = None
                out.append({"area_id": aid, "occurred": occ, "removed": rem})
            d += timedelta(days=r.randint(6, 20))
        return out


def bundle_of(site, rain, work, stabs, insp, finds, track):
    s = dict(site)
    return {"site": s, "rain": rain, "work": work, "stabs": stabs, "insp": insp, "finds": finds, "track": track}


def last_biz_on_or_before(biz, d, lo):
    while d >= lo:
        if d in biz:
            return d
        d -= DAY
    return None


def filler(rng, sid, n):
    for attempt in range(200):
        s = Site(rng, sid, n)
        site = s.build()
        insp = s.make_inspections()
        biz = set().union(*s.work.values())
        ok = False
        for _ in range(60):
            b = bundle_of(site, s.rain, s.work, s.stabs, insp, [], [])
            _, flags, _ = sim(b, strict=True)
            if not flags:
                ok = True
                break
            hard = [f for f in flags if f[0] not in ("routine_nonbiz", "change_overdue", "storm_mode")]
            if hard:
                break
            for kind, aid, d in flags:
                if kind == "storm_mode":
                    s.rain[d] = rng.randint(5, 20)
                    continue
                first = min(s.work[aid])
                x = last_biz_on_or_before(biz, d, first)
                if x is None:
                    continue
                ex = [i for i in insp if i["completed"].date() == x]
                if ex:
                    if aid not in ex[0]["areas"]:
                        ex[0]["areas"] = sorted(ex[0]["areas"] + [aid])
                else:
                    s.add_insp(insp, x, [aid])
        if not ok:
            continue
        finds = s.make_findings(insp)
        track = s.make_trackout()
        b = bundle_of(site, s.rain, s.work, s.stabs, insp, finds, track)
        rows, flags, info = sim(b, strict=True)
        if flags:
            continue
        return b
    raise SystemExit(f"could not build {sid}")


def to_json(bundles):
    sites, rain, log, stab, insp, finds, track = [], [], [], [], [], [], []
    for b in bundles:
        site = b["site"]
        sid = site["site_id"]
        sites.append({"site_id": sid, "project": site["project"], "inspection_schedule": site["inspection_schedule"],
                      "normal_working_hours": site["normal_working_hours"],
                      "receiving_waters": site["receiving_waters"],
                      "areas": [{"area_id": a["area_id"], "description": a["description"],
                                 "acres": f"{a['acres_hundredths'] // 100}.{a['acres_hundredths'] % 100:02d}",
                                 "discharges_to": a["discharges_to"],
                                 "work_completed_on": a["work_completed_on"].isoformat()
                                 if a.get("work_completed_on") else None} for a in site["areas"]]})
        for d in sorted(b["rain"]):
            v = b["rain"][d]
            if v >= 1:
                rain.append({"site_id": sid, "date": d.isoformat(), "rain_inches": f"{v // 100}.{v % 100:02d}"})
        for aid in sorted(b["work"]):
            pass
        acts = []
        for aid, days in b["work"].items():
            for d in days:
                acts.append((d, aid))
        for d, aid in sorted(acts):
            log.append({"site_id": sid, "date": d.isoformat(), "area_id": aid,
                        "activity": ACTIVITIES[(d.toordinal() * 7 + int(aid[-2:]) * 3) % len(ACTIVITIES)]})
        for s in sorted(b["stabs"], key=lambda x: (x["initiated"], x["area_id"])):
            stab.append({"site_id": sid, "area_id": s["area_id"], "initiated": fmt(s["initiated"]),
                         "completed": fmt(s["completed"]) if s["completed"] else None, "measure": s["measure"]})
        for i in sorted(b["insp"], key=lambda x: x["completed"]):
            insp.append({"site_id": sid, "completed": fmt(i["completed"]), "areas_inspected": i["areas"],
                         "report_completed": fmt(i["report_completed"]) if i["report_completed"] else None,
                         "_obj": i})
        at_time = {i["completed"]: i for i in b["insp"]}
        for f in sorted(b["finds"], key=lambda x: (x["discovered"], x["area_id"], x["control_id"])):
            if f.get("inspection") is None and f["discovered"] in at_time and \
                    f["area_id"] in at_time[f["discovered"]]["areas"]:
                f["inspection"] = at_time[f["discovered"]]
            finds.append({"site_id": sid, "area_id": f["area_id"], "_insp": f.get("inspection"),
                          "discovered": fmt(f["discovered"]), "control_id": f["control_id"],
                          "location": f["location"], "condition": f["condition"], "fix": f["fix"],
                          "needs": f["needs"], "infeasibility_documented": f["infeasibility_documented"],
                          "completed": fmt(f["completed"]) if f["completed"] else None,
                          "log_entry_identified": fmt(f["log_identified"]) if f["log_identified"] else None,
                          "log_entry_completed": fmt(f["log_completed"]) if f["log_completed"] else None,
                          "swppp_change_needed": f["swppp_change"],
                          "swppp_updated": fmt(f["swppp_updated"]) if f["swppp_updated"] else None})
        for t in sorted(b["track"], key=lambda x: x["occurred"]):
            track.append({"site_id": sid, "area_id": t["area_id"], "occurred": fmt(t["occurred"]),
                          "removed": fmt(t["removed"]) if t["removed"] else None})
    # ids: numbered in time order across all sites
    insp.sort(key=lambda x: (x["completed"], x["site_id"]))
    for k, i in enumerate(insp):
        i["inspection_id"] = f"I{k + 1:05d}"
        i["_obj"]["_id"] = i["inspection_id"]
    insp = [{"inspection_id": i["inspection_id"], **{k: v for k, v in i.items() if k not in ("_obj", "inspection_id")}}
            for i in insp]
    finds.sort(key=lambda x: (x["discovered"], x["site_id"], x["area_id"], x["control_id"]))
    out_f = []
    for k, f in enumerate(finds):
        ins = f.pop("_insp")
        out_f.append({"finding_id": f"F{k + 1:05d}", "site_id": f["site_id"], "area_id": f["area_id"],
                      "inspection_id": ins["_id"] if ins else None, **{x: f[x] for x in f if x not in ("site_id", "area_id")}})
    stab.sort(key=lambda x: (x["initiated"], x["site_id"], x["area_id"]))
    stab = [{"record_id": f"Z{k + 1:04d}", **s} for k, s in enumerate(stab)]
    track.sort(key=lambda x: (x["occurred"], x["site_id"]))
    track = [{"trackout_id": f"T{k + 1:04d}", **t} for k, t in enumerate(track)]
    log.sort(key=lambda x: (x["site_id"], x["date"], x["area_id"]))
    rain.sort(key=lambda x: (x["site_id"], x["date"]))
    sites.sort(key=lambda x: x["site_id"])
    return {"sites.json": sites, "rain_gauge.json": rain, "construction_log.json": log,
            "stabilization_records.json": stab, "inspections.json": insp, "findings.json": out_f,
            "trackout.json": track}


def main():
    rng = random.Random(SEED)
    ids = [f"S{k:02d}" for k in range(1, N_FILLER + len(planted.SITES) + 1)]
    rng.shuffle(ids)
    bundles, golden, tags = [], {}, {}
    for k, make in enumerate(planted.SITES):
        sid = ids[k]
        b, expected, t = make(sid)
        b["site"]["project"] = planted.PROJECTS[make.__name__]
        rows, flags, _ = sim(b, strict=True)
        exp = sorted(tuple(x) for x in expected)
        if rows != exp or flags:
            print("PLANTED MISMATCH", make.__name__, sid, flags)
            for x in sorted(set(rows) - set(exp)):
                print("  sim only ", x)
            for x in sorted(set(exp) - set(rows)):
                print("  hand only", x)
            raise SystemExit(1)
        bundles.append(b)
        golden[sid] = [list(x) for x in exp]
        tags[sid] = t
    for k in range(len(planted.SITES), len(ids)):
        sid = ids[k]
        bundles.append(filler(rng, sid, k))
        tags[sid] = ["filler"]
    data = to_json(bundles)
    total = 0
    for b in bundles:
        total += len(sim(b)[0])
    for sub in ("environment/data", "tests/data"):
        p = ROOT / sub
        p.mkdir(parents=True, exist_ok=True)
        for name, obj in data.items():
            (p / name).write_text(json.dumps(obj, indent=1) + "\n")
    (ROOT / "tests" / "golden.json").write_text(json.dumps(golden, indent=1, sort_keys=True) + "\n")
    (ROOT / "tests" / "case_tags.json").write_text(json.dumps(tags, indent=1, sort_keys=True) + "\n")
    answers = sorted(r for b in bundles for r in sim(b)[0])
    dev = HERE.parents[2] / "tools" / "stormwater-inspection-audit"     # author's workspace only, never in the task
    if dev.is_dir():
        (dev / "sim_answers.json").write_text(json.dumps([list(r) for r in answers]) + "\n")
    print(f"sites {len(bundles)} (planted {len(planted.SITES)}), rows {total}, "
          + ", ".join(f"{k} {len(v)}" for k, v in data.items()))


if __name__ == "__main__":
    main()
