#!/usr/bin/env python3
"""Generate the sediment-basin-routing inputs (authoring tool; not part of the agent or verifier images).

Writes identical data to ../environment/data and ../tests/data, plus ../tests/golden.json (published NEH, TR-55
and HEC-22 worked examples, and peak inflows of planted storms worked by hand) and ../tests/case_tags.json.
Random cases are adjusted until no spillway answer lies within 0.002 ft of a crest, so careful implementations
cannot disagree on a yes/no.
"""
import json
import math
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sim  # noqa: E402

SEED = 61717
ROOT = HERE.parent
T0 = datetime(2026, 4, 1)
N_FILLER = 9
CN = {"undisturbed": {"A": 39, "B": 61, "C": 74, "D": 80},      # TR-55 table 2-2a open space, good condition
      "disturbed": {"A": 77, "B": 86, "C": 91, "D": 94},        # newly graded areas
      "stabilized": {"A": 49, "B": 69, "C": 79, "D": 84}}       # open space, fair condition
SMOOTH = "Smooth surfaces (concrete, asphalt, gravel, or bare soil)"
UNDIST = ["Woods: light underbrush", "Grass: dense grasses", "Range (natural)", "Woods: dense underbrush"]
STAB = ["Grass: short grass prairie", "Cultivated soils: residue cover >20%", "Grass: dense grasses"]
TOWNS = ["Caguas", "Gurabo", "Humacao", "Cayey", "Juncos", "Carolina", "Dorado", "Manati", "Arecibo", "Cidra",
         "Naguabo", "Yabucoa", "Toa Alta", "Vega Baja", "Rio Grande"]
PROJECTS = ["school campus", "distribution center", "housing subdivision", "medical center", "solar farm",
            "retail center", "highway interchange", "water treatment plant", "industrial park", "sports complex"]


def kstamp(k):
    return (T0 + timedelta(minutes=6 * k)).strftime("%Y-%m-%dT%H:%M")


def kdate(k):
    return (T0 + timedelta(minutes=6 * k)).date().isoformat()


def kday(stamp):
    return int((datetime.fromisoformat(stamp) - T0).total_seconds() // 360)


# ---------------------------------------------------------------- rainfall
def storm_depths(r, total_h, hours):
    n = max(1, int(hours * 10))
    weights, peak = [], r.random()
    for i in range(n):
        x = i / max(1, n - 1)
        w = math.exp(-((x - peak) ** 2) / (2 * r.uniform(0.02, 0.12))) + r.uniform(0, 0.25)
        if r.random() < 0.12:
            w = 0.0
        weights.append(w)
    if sum(weights) == 0:
        weights[0] = 1.0
    out = [0] * n
    tot = sum(weights)
    for _ in range(total_h):
        x, acc = r.random() * tot, 0.0
        for i, w in enumerate(weights):
            acc += w
            if x <= acc:
                out[i] += 1
                break
    return out


def make_rain(r):
    rain = {}
    k = r.randint(0, 240 * 4)
    while k < sim.END_K - 20:
        heavy = 1.6 if (T0 + timedelta(minutes=6 * k)).month >= 8 else 1.0
        x = r.random()
        depth = (r.randint(1, 12) if x < 0.25 else r.randint(13, 90) if x < 0.75 else
                 int(r.randint(90, 250) * heavy) if x < 0.95 else int(r.randint(250, 520) * heavy))
        pattern = storm_depths(r, depth, r.choice([0.3, 0.5, 1, 1.5, 2, 3, 4, 6, 8, 12]))
        for i, v in enumerate(pattern):
            if v and k + i < sim.END_K:
                rain[k + i] = v
        last = max([k + i for i, v in enumerate(pattern) if v] or [k])
        y = r.random()
        gap = (r.choice([58, 59, 60, 61, 62]) if y < 0.12 else r.randint(10, 57) if y < 0.25 else
               r.randint(63, 240 * 6))
        k = last + gap + 1
    return rain


# ---------------------------------------------------------------- geometry
def trapezoid(r, bottom, depth, target):
    z, ratio, L = r.choice([2.0, 3.0, 3.0]), r.uniform(0.35, 0.6), 10.0
    while True:
        W = L * ratio
        if L * W * depth + (L + W) * z * depth ** 2 + 4 / 3 * z * z * depth ** 3 >= target:
            break
        L += 0.5
    return {"shape": "trapezoid", "bottom": bottom, "L": round(L, 1), "W": round(L * ratio, 1), "Z": z}


def contours(r, bottom, depth, target, top):
    """Surveyed contour areas every foot (irregular growth), scaled so the volume to `depth` is about target."""
    a0 = r.uniform(300, 1500)
    grow = [r.uniform(1.25, 2.4) for _ in range(12)]
    zs = [round(bottom, 2)]
    z = math.floor(bottom) + 1.0
    while z < top + 1.01:
        zs.append(z)
        z += 1.0
    areas = [a0]
    for i in range(1, len(zs)):
        areas.append(areas[-1] * grow[i % 12] ** (zs[i] - zs[i - 1]) + r.uniform(50, 400))
    cs = [[zz, aa] for zz, aa in zip(zs, areas)]
    b = {"shape": "contours", "bottom": zs[0], "contours": cs}
    v = sim.storage(b, bottom + depth)
    f = target / v
    b["contours"] = [[zz, round(aa * f)] for zz, aa in cs]
    return b


def outlets(r, b, d_riser, d_spill):
    bottom = b["bottom"]
    b.update({"orifice": {"d_in": r.choice([2.0, 2.5, 3.0, 3.0, 4.0, 5.0, 6.0]), "inv": bottom, "c": 0.6},
              "riser_d": r.choice([1.5, 2.0, 2.0, 2.5, 3.0]), "riser_crest": round(bottom + d_riser, 2),
              "riser_cw": 0.37, "riser_co": 0.6, "spill_crest": round(bottom + d_spill, 2),
              "spill_L": float(r.choice([6, 8, 10, 12, 15, 20])), "spill_cw": r.choice([0.29, 0.31, 0.33])})
    return b


def flow_path(r):
    path = {"sheet": {"length_ft": float(r.randint(40, 300)), "slope": round(r.uniform(0.01, 0.08), 3)},
            "shallow": {"length_ft": float(r.randint(100, 1100)), "slope": round(r.uniform(0.008, 0.06), 3),
                        "paved": r.random() < 0.15}}
    if r.random() < 0.5:
        path["channel"] = {"length_ft": float(r.randint(100, 700)), "area_sqft": round(r.uniform(1.5, 9.0), 1),
                           "wetted_perimeter_ft": round(r.uniform(4.0, 12.0), 1),
                           "slope": round(r.uniform(0.004, 0.03), 3), "n": r.choice([0.03, 0.035, 0.04, 0.05])}
    return path


def make_area(r, aid, basin):
    hsg = r.choice("ABCCDD")
    return {"id": aid, "acres": round(r.uniform(1.5, 9.5), 2), "hsg": hsg, "basin": basin,
            "cn": {s: CN[s][hsg] for s in CN}, "path": flow_path(r),
            "surface": {"undisturbed": r.choice(UNDIST), "disturbed": SMOOTH, "stabilized": r.choice(STAB)}}


def state_changes(r):
    chg = []
    first = r.choice(["undisturbed", "undisturbed", "disturbed"])
    chg.append((0, first))
    day = r.randint(5, 60)
    if first == "undisturbed":
        chg.append((day * 240, "disturbed"))
        day += r.randint(20, 90)
    if r.random() < 0.7 and day < 175:
        chg.append((day * 240, "stabilized"))
        day += r.randint(10, 60)
        if r.random() < 0.3 and day < 178:
            chg.append((day * 240, "disturbed"))
    return [c for c in chg if c[0] < sim.END_K]


def random_site(r, sid):
    p2 = round(r.uniform(4.2, 5.6), 1)
    nb = r.choice([1, 2, 2, 3, 3])
    basins, areas, changes = [], [], {}
    mains = [f"{sid}-B{k + 1}" for k in range(nb)]
    na = 0
    for k, bid in enumerate(mains):
        down = mains[k + 1] if (k + 1 < nb and r.random() < 0.4) else None
        has_fore = r.random() < 0.7
        local_main, local_fore = 0.0, 0.0
        my_areas = []
        for _ in range(r.choice([1, 2, 2, 3])):
            na += 1
            target = f"{bid}F" if has_fore and r.random() < 0.75 else bid
            a = make_area(r, f"{sid}-A{na:02d}", target)
            my_areas.append(a)
            if target == bid:
                local_main += a["acres"]
            else:
                local_fore += a["acres"]
        if has_fore and local_fore == 0:
            my_areas[0]["basin"] = f"{bid}F"
            local_fore, local_main = my_areas[0]["acres"], local_main - my_areas[0]["acres"]
        total = max(2.0, local_main + local_fore)
        bottom = round(r.uniform(150, 420), 2)
        d_riser, d_spill = round(r.uniform(1.6, 2.6), 2), None
        d_spill = round(d_riser + r.uniform(0.7, 1.4), 2)
        target = 3600.0 * total * r.uniform(0.4, 0.95)
        top_guess = bottom + d_spill + 2.5
        geo = contours(r, bottom, d_spill, target, top_guess) if r.random() < 0.45 else trapezoid(r, bottom, d_spill, target)
        main = outlets(r, geo, d_riser, d_spill)
        main.update({"id": bid, "down": down, "top": None})
        basins.append(main)
        if has_fore:
            fb = round(bottom + r.uniform(0.4, 1.4), 2)
            ftarget = 0.15 * target
            fgeo = (contours(r, fb, 2.0, ftarget, top_guess) if r.random() < 0.5 else trapezoid(r, fb, 2.0, ftarget))
            crest = round(min(main["riser_crest"] + r.uniform(-0.6, 0.3), fb + r.uniform(0.9, 1.8)), 2)
            crest = max(crest, round(fb + 0.6, 2))
            fgeo.update({"id": f"{bid}F", "top": None, "down": None,
                         "divider": {"into": bid, "weir_crest": crest, "weir_L": float(r.choice([3, 4, 6, 8])),
                                     "weir_cw": 0.37, "orifice": {"d_in": r.choice([3.0, 4.0, 6.0]), "inv": fb,
                                                                  "c": 0.6}}})
            basins.append(fgeo)
        for a in my_areas:
            areas.append(a)
            changes[a["id"]] = state_changes(r)
    return {"id": sid, "p2": p2, "basins": basins, "areas": areas}, changes


# ---------------------------------------------------------------- planted sites
def plain_basin(bid, bottom, L, W):
    b = {"shape": "trapezoid", "bottom": bottom, "L": L, "W": W, "Z": 3.0, "id": bid, "down": None, "top": None}
    b.update({"orifice": {"d_in": 4.0, "inv": bottom, "c": 0.6}, "riser_d": 2.5, "riser_crest": bottom + 2.5,
              "riser_cw": 0.37, "riser_co": 0.6, "spill_crest": bottom + 3.8, "spill_L": 12.0, "spill_cw": 0.31})
    return b


def planted_minimum_tc(sid):
    """16 acres (0.025 sq mi), disturbed (smooth surface), soil D: CN 94, S = 0.638298, Ia = 0.127660.
    Tc from the path: sheet 100 ft at 0.03, n 0.011, P2 4.5: 0.007 (1.1)^0.8 / (4.5^0.5 0.03^0.4) = 0.01450 h;
    shallow unpaved 300 ft at 0.03: V = 16.1345 x 0.03^0.5 = 2.7946 ft/s, 0.02982 h; Tc = 0.0443 h, below the
    TR-55 minimum, so Tc = 0.1 h and Tp = 0.05 + 0.06 = 0.11 h, qp = 484 x 0.025 / 0.11 = 110.0 cfs per inch.
    Ordinates at 0.1 h steps (t/Tp = 0.909, 1.818, 2.727, ...): 0.990909, 0.379091, 0.087909, 0.019909, 0.004545.
    Storm 1: 0.50 in in one interval: Q = 0.372340^2 / 1.010638 = 0.137178 in; peak 0.137178 x 110 x 0.990909
    = 14.952 cfs.  Storm 2: 0.30 then 0.30 in: Q(0.3) = 0.036639, Q(0.6) = 0.200880, increments 0.036639 and
    0.164241; at 0.2 h: 0.036639 x 0.379091 + 0.164241 x 0.990909 = 0.176637; peak 0.176637 x 110 = 19.430 cfs.
    (Without the minimum, Tp = 0.0766 h and the peaks change.)"""
    site = {"id": sid, "p2": 4.5, "basins": [plain_basin(f"{sid}-B1", 200.0, 90.0, 45.0)], "areas": [
        {"id": f"{sid}-A01", "acres": 16.0, "hsg": "D", "basin": f"{sid}-B1", "cn": {s: CN[s]["D"] for s in CN},
         "path": {"sheet": {"length_ft": 100.0, "slope": 0.03},
                  "shallow": {"length_ft": 300.0, "slope": 0.03, "paved": False}},
         "surface": {"undisturbed": "Grass: dense grasses", "disturbed": SMOOTH, "stabilized": "Grass: short grass prairie"}}]}
    chg = {f"{sid}-A01": [(0, "disturbed")]}
    s1, s2 = kday("2026-04-14T14:00"), kday("2026-05-02T13:00")
    rain = {s1: 50, s2: 30, s2 + 1: 30}
    return site, chg, rain, {s1: 14.952, s2: 19.430}, ["runoff", "time-of-concentration", "unit-hydrograph"]


def planted_states(sid):
    """Two 32-acre areas (0.05 sq mi each), soil B, P2 4.5 in.
    A01 is undisturbed (CN 61) until it is graded on 2026-05-01, then disturbed (CN 86, smooth surface): sheet 120 ft
    at 0.03 gives 0.016774 h, shallow unpaved 500 ft at 0.03 gives 0.049700 h, Tc 0.066 h -> minimum 0.1 h, Tp 0.11 h,
    qp = 484 x 0.05 / 0.11 = 220 cfs per inch.
    A02 is stabilized (CN 69, short grass prairie n 0.15): sheet 150 ft at 0.04: 0.007 (22.5)^0.8 / (4.5^0.5 0.04^0.4)
    = 0.144349 h; shallow unpaved 600 ft at 0.04: V = 3.2269 ft/s, 0.051649 h; Tc 0.195998 h; Tp 0.167599 h;
    qp = 144.392 cfs per inch.
    Storm 1 (2026-04-20, 1.00 in): A01 CN 61 has Ia 1.279 in > 1.00, no runoff; A02: Q = 0.101449^2 / 4.594203
    = 0.002240 in; ordinates at t/Tp = 0.5967, 1.1933: 0.651370, 0.934400 of qp; peak 0.002240 x 144.392 x 0.934
    = 0.302 cfs.  Storm 2 (2026-05-01 03:00, the grading day, 1.00 in): A01 CN 86: Q = 0.674419^2 / 2.302326 =
    0.197557; at 0.1 h: 0.197557 x 220 x 0.990909 + 0.002240 x 144.392 x 0.651370 = 43.068 + 0.211 = 43.279 cfs."""
    b = plain_basin(f"{sid}-B1", 310.0, 120.0, 60.0)
    areas = [{"id": f"{sid}-A01", "acres": 32.0, "hsg": "B", "basin": b["id"], "cn": {s: CN[s]["B"] for s in CN},
              "path": {"sheet": {"length_ft": 120.0, "slope": 0.03},
                       "shallow": {"length_ft": 500.0, "slope": 0.03, "paved": False}},
              "surface": {"undisturbed": "Woods: light underbrush", "disturbed": SMOOTH,
                          "stabilized": "Grass: short grass prairie"}},
             {"id": f"{sid}-A02", "acres": 32.0, "hsg": "B", "basin": b["id"], "cn": {s: CN[s]["B"] for s in CN},
              "path": {"sheet": {"length_ft": 150.0, "slope": 0.04},
                       "shallow": {"length_ft": 600.0, "slope": 0.04, "paved": False}},
              "surface": {"undisturbed": "Woods: light underbrush", "disturbed": SMOOTH,
                          "stabilized": "Grass: short grass prairie"}}]
    chg = {f"{sid}-A01": [(0, "undisturbed"), (kday("2026-05-01T00:00"), "disturbed")],
           f"{sid}-A02": [(0, "stabilized")]}
    s1, s2 = kday("2026-04-20T10:00"), kday("2026-05-01T03:00")
    return ({"id": sid, "p2": 4.5, "basins": [b], "areas": areas}, chg, {s1: 100, s2: 100},
            {s1: 0.302, s2: 43.279}, ["area-states", "runoff", "time-of-concentration"])


def planted_two_cell(sid):
    """A forebay draining to its main cell through a submerged divider, the main cell draining to a second basin;
    storms close together.  Peaks come from the engine (routing families)."""
    r = random.Random(7)
    main = plain_basin(f"{sid}-B1", 250.0, 80.0, 40.0)
    main.update({"riser_d": 1.5, "riser_crest": 252.0, "spill_crest": 253.1, "spill_L": 8.0, "spill_cw": 0.29,
                 "down": f"{sid}-B2"})
    fore = {"shape": "contours", "bottom": 250.8,
            "contours": [[250.8, 400.0], [251.0, 520.0], [252.0, 1150.0], [253.0, 1900.0], [254.0, 2700.0],
                         [255.0, 3600.0]],
            "id": f"{sid}-B1F", "down": None, "top": None,
            "divider": {"into": main["id"], "weir_crest": 251.9, "weir_L": 4.0, "weir_cw": 0.37,
                        "orifice": {"d_in": 4.0, "inv": 250.8, "c": 0.6}}}
    down = plain_basin(f"{sid}-B2", 240.0, 110.0, 50.0)
    down.update({"Z": 2.0, "riser_d": 2.0, "riser_crest": 242.2, "spill_crest": 243.3})
    areas = [make_area(r, f"{sid}-A01", fore["id"]), make_area(r, f"{sid}-A02", main["id"]),
             make_area(r, f"{sid}-A03", down["id"])]
    areas[0]["acres"], areas[1]["acres"], areas[2]["acres"] = 5.5, 2.5, 4.0
    chg = {a["id"]: [(0, "disturbed")] for a in areas}
    chg[f"{sid}-A03"].append((kday("2026-08-01T00:00"), "stabilized"))
    rain, k = {}, kday("2026-06-03T13:00")
    for depth, hours, gap in [(180, 2, 59), (150, 1.5, 60), (260, 3, 200), (40, 1, 400), (320, 2, 61), (210, 1, 60),
                              (420, 3, 300), (60, 0.5, 59)]:
        pat = storm_depths(r, depth, hours)
        for i, v in enumerate(pat):
            if v:
                rain[k + i] = v
        k = max(k + i for i, v in enumerate(pat) if v) + gap + 1
    return ({"id": sid, "p2": 4.8, "basins": [main, fore, down], "areas": areas}, chg, rain, {},
            ["two-cell", "routing", "series", "spillway", "storms"])


PLANTED = [planted_minimum_tc, planted_states, planted_two_cell]


def fix_crests(site, rain, chg):
    for _ in range(60):
        rows, trace, st = sim.simulate(site, rain, chg)
        bad = {x["basin"] for x in rows if abs(x["margin"]) < 0.002}
        if not bad:
            break
        for b in site["basins"]:
            if b["id"] in bad:
                b["spill_crest"] = round(b["spill_crest"] + 0.01, 2)
    else:
        raise RuntimeError("crest fixing failed")
    peaks = {}
    for x in rows:
        peaks[x["basin"]] = max(peaks.get(x["basin"], -1e9), x["peak_stage"])
    for b in site["basins"]:
        if b.get("divider"):
            continue
        b["top"] = round(max(peaks[b["id"]] + 0.6, b["spill_crest"] + 1.0), 1)
    for b in site["basins"]:
        if b.get("divider"):
            b["top"] = next(x for x in site["basins"] if x["id"] == b["divider"]["into"])["top"]
        if b["shape"] == "contours" and peaks[b["id"]] > b["contours"][-1][0] - 0.3:
            raise RuntimeError("peak above survey")
    return rows, st


def geometry_json(b):
    if b["shape"] == "trapezoid":
        return {"type": "trapezoid", "bottom_elevation_ft": b["bottom"], "bottom_length_ft": b["L"],
                "bottom_width_ft": b["W"], "side_slope_h_per_v": b["Z"]}
    return {"type": "surveyed contours", "contours": [{"elevation_ft": z, "area_sqft": a} for z, a in b["contours"]]}


def site_json(site, project):
    cells = []
    for b in site["basins"]:
        rec = {"basin_id": b["id"], "geometry": geometry_json(b), "embankment_top_ft": b["top"]}
        if b.get("divider"):
            dv = b["divider"]
            rec.update({"cell": "forebay", "divider": {
                "drains_into": dv["into"], "weir_crest_elevation_ft": dv["weir_crest"], "weir_length_ft": dv["weir_L"],
                "weir_coefficient": dv["weir_cw"],
                "orifice": {"diameter_in": dv["orifice"]["d_in"], "invert_elevation_ft": dv["orifice"]["inv"],
                            "discharge_coefficient": dv["orifice"]["c"]}}})
        else:
            rec.update({"cell": "main",
                        "dewatering_orifice": {"diameter_in": b["orifice"]["d_in"],
                                               "invert_elevation_ft": b["orifice"]["inv"],
                                               "discharge_coefficient": b["orifice"]["c"]},
                        "riser": {"diameter_ft": b["riser_d"], "crest_elevation_ft": b["riser_crest"],
                                  "weir_coefficient": b["riser_cw"], "orifice_coefficient": b["riser_co"]},
                        "emergency_spillway": {"crest_elevation_ft": b["spill_crest"], "crest_length_ft": b["spill_L"],
                                               "weir_coefficient": b["spill_cw"]},
                        "discharges_to": b["down"]})
        cells.append(rec)
    return {"site_id": site["id"], "project": project, "two_year_24_hour_rainfall_in": site["p2"], "basins": cells,
            "drainage_areas": [{"area_id": a["id"], "acres": a["acres"], "hydrologic_soil_group": a["hsg"],
                                "curve_numbers": a["cn"], "sheet_flow_surface": a["surface"], "flow_path": a["path"],
                                "drains_to": a["basin"]} for a in site["areas"]]}


def main():
    r = random.Random(SEED)
    ids = [f"S{k:02d}" for k in range(1, N_FILLER + len(PLANTED) + 1)]
    r.shuffle(ids)
    sites, rain_out, states_out, golden_rows, tags = [], [], [], {}, {}
    total = 0
    for n, sid in enumerate(ids):
        project = f"{r.choice(PROJECTS)}, {r.choice(TOWNS)}"
        if n < len(PLANTED):
            site, chg, rain, hand, t = PLANTED[n](sid)
            rows, st = fix_crests(site, rain, chg)
            for start, val in hand.items():
                row = next(x for x in rows if x["start"] == start)
                if abs(row["peak_in"] - val) > 0.002:
                    raise SystemExit(f"planted {sid} {kstamp(start)}: model {row['peak_in']:.4f} vs hand {val}")
                golden_rows[f"{sid}|{site['basins'][0]['id']}|{kstamp(start)}"] = {"peak_inflow_cfs": val}
            tags[sid] = t
        else:
            for attempt in range(50):
                site, chg = random_site(r, sid)
                rain = make_rain(r)
                try:
                    rows, st = fix_crests(site, rain, chg)
                    break
                except RuntimeError:
                    continue
            tags[sid] = ["filler"]
        total += len(rows)
        sites.append(site_json(site, project))
        for k in sorted(rain):
            rain_out.append({"site_id": sid, "interval_start": kstamp(k), "rain_in": f"{rain[k] / 100:.2f}"})
        for a in site["areas"]:
            for k, s in chg[a["id"]]:
                states_out.append({"site_id": sid, "area_id": a["id"], "effective_date": kdate(k), "state": s})
        print(sid, len(site["basins"]), "basins", sum(1 for b in site["basins"] if b.get("divider")), "forebays",
              len(st), "storms", sum(x["spill"] for x in rows), "spill rows")
    sites.sort(key=lambda s: s["site_id"])
    rain_out.sort(key=lambda x: (x["site_id"], x["interval_start"]))
    states_out.sort(key=lambda x: (x["site_id"], x["area_id"], x["effective_date"]))
    data = {"sites.json": sites, "rain_gauge.json": rain_out, "area_states.json": states_out}
    for sub in ("environment/data", "tests/data"):
        p = ROOT / sub
        p.mkdir(parents=True, exist_ok=True)
        for name, obj in data.items():
            (p / name).write_text(json.dumps(obj, indent=1) + "\n")
    (ROOT / "tests" / "golden.json").write_text(json.dumps({"rows": golden_rows, "examples": EXAMPLES}, indent=1,
                                                           sort_keys=True) + "\n")
    (ROOT / "tests" / "case_tags.json").write_text(json.dumps(tags, indent=1, sort_keys=True) + "\n")
    print(f"sites {len(sites)}, rows {total}, rain intervals {len(rain_out)}, state records {len(states_out)}")


EXAMPLES = [
    {"source": "NEH 630.10 example 10-1", "check": "runoff", "rain_in": 4.3, "cn": 74, "expect": 1.82, "tol": 0.005},
    {"source": "NEH 630.10 table 10-2", "check": "runoff", "rain_in": 2.25, "cn": 80, "expect": 0.72, "tol": 0.005},
    {"source": "NEH 630.10 table 10-2", "check": "runoff", "rain_in": 5.00, "cn": 80, "expect": 2.89, "tol": 0.005},
    {"source": "NEH 630.16 example 16-1", "check": "tp", "tc_h": 2.3, "dd_h": 0.3, "expect": 1.53, "tol": 0.005},
    {"source": "NEH 630.16 example 16-1", "check": "qp", "tc_h": 2.3, "dd_h": 0.3, "sq_mi": 4.6, "expect": 1455,
     "tol": 1.0},
    {"source": "TR-55 example 3-1 (worksheet 3)", "check": "tc", "p2_in": 3.6, "surface": "Grass: dense grasses",
     "path": {"sheet": {"length_ft": 100, "slope": 0.01}, "shallow": {"length_ft": 1400, "slope": 0.01, "paved": False},
              "channel": {"length_ft": 7300, "area_sqft": 27, "wetted_perimeter_ft": 28.2, "slope": 0.005, "n": 0.05}},
     "expect": 1.53, "tol": 0.005},
    {"source": "HEC-22 example 10.10", "check": "orifice", "diameter_ft": 0.49, "depth_ft": 3.3, "c": 0.6,
     "expect": 1.59, "tol": 0.005},
    {"source": "HEC-22 example 10.11 (L = 5.5 ft; the printed 3.5 uses a rounded 18.32 constant, the equation "
               "gives 3.43)", "check": "riser", "weir_length_ft": 5.5, "diameter_ft": 1.74,
     "cw": 0.41, "co": 0.6, "head_ft": 0.33, "expect": 3.5, "tol": 0.1},
    {"source": "HEC-22 example 10.11 (L = 5.5 ft)", "check": "riser", "weir_length_ft": 5.5, "diameter_ft": 1.74,
     "cw": 0.41, "co": 0.6, "head_ft": 1.31, "expect": 13.1, "tol": 0.05},
    {"source": "HEC-22 eq. 10.10 (L 100, W 50, Z 3, D 2)", "check": "storage", "L": 100, "W": 50, "Z": 3, "D": 2,
     "expect": 11896, "tol": 0.5},
    {"source": "HEC-22 eq. 10.19 (A1 1,000, A2 4,000, d 1)", "check": "conic", "a1": 1000, "a2": 4000, "d": 1,
     "expect": 2333.333, "tol": 0.01},
    {"source": "HEC-22 eq. 10.34 (h1 1.0, h2 0.5)", "check": "villemonte", "h1": 1.0, "h2": 0.5,
     "expect": 0.8454, "tol": 0.0005},
]

if __name__ == "__main__":
    main()
