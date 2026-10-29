#!/usr/bin/env python3
"""Generate the sediment-basin-routing inputs (authoring tool; not part of the agent or verifier images).

Writes identical data to ../environment/data and ../tests/data, plus ../tests/golden.json (hand-worked values:
published NEH and HEC-22 worked examples, and hand-computed peak inflows of planted storms) and
../tests/case_tags.json (method families of the planted sites). Random cases are adjusted until no spillway answer
lies within 0.002 ft of a crest, so careful implementations cannot disagree on a yes/no.
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

SEED = 61716
ROOT = HERE.parent
T0 = datetime(2026, 4, 1)
N_FILLER = 9
# TR-55 table 2-2a curve numbers by hydrologic soil group
CN = {"undisturbed": {"A": 39, "B": 61, "C": 74, "D": 80},      # open space, good condition
      "disturbed": {"A": 77, "B": 86, "C": 91, "D": 94},        # newly graded areas, no vegetation
      "stabilized": {"A": 49, "B": 69, "C": 79, "D": 84}}       # open space, fair condition
TOWNS = ["Caguas", "Gurabo", "Humacao", "Cayey", "Juncos", "Carolina", "Dorado", "Manati", "Arecibo", "Cidra",
         "Naguabo", "Yabucoa", "Toa Alta", "Vega Baja", "Rio Grande"]
PROJECTS = ["school campus", "distribution center", "housing subdivision", "medical center", "solar farm",
            "retail center", "highway interchange", "water treatment plant", "industrial park", "sports complex"]


def kstamp(k):
    return (T0 + timedelta(minutes=6 * k)).strftime("%Y-%m-%dT%H:%M")


def kdate(k):
    return (T0 + timedelta(minutes=6 * k)).date().isoformat()


def kday(datestr):
    return int((datetime.fromisoformat(datestr) - T0).total_seconds() // 360)


# ---------------------------------------------------------------- rainfall
def storm_depths(r, total_h, hours):
    """Spread total_h hundredths over an interval pattern of about `hours` hours with bursts."""
    n = max(1, int(hours * 10))
    weights = []
    peak = r.random()
    for i in range(n):
        x = i / max(1, n - 1)
        w = math.exp(-((x - peak) ** 2) / (2 * r.uniform(0.02, 0.12))) + r.uniform(0, 0.25)
        if r.random() < 0.12:
            w = 0.0                                   # short lulls inside the storm
        weights.append(w)
    if sum(weights) == 0:
        weights[0] = 1.0
    out = [0] * n
    for _ in range(total_h):                          # tipping-bucket hundredths
        x = r.random() * sum(weights)
        acc = 0.0
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
        month = (T0 + timedelta(minutes=6 * k)).month
        heavy = 1.6 if month >= 8 else 1.0
        x = r.random()
        if x < 0.25:
            depth = r.randint(1, 12)
        elif x < 0.75:
            depth = r.randint(13, 90)
        elif x < 0.95:
            depth = int(r.randint(90, 250) * heavy)
        else:
            depth = int(r.randint(250, 520) * heavy)
        hours = r.choice([0.3, 0.5, 1, 1.5, 2, 3, 4, 6, 8, 12])
        pattern = storm_depths(r, depth, hours)
        for i, v in enumerate(pattern):
            if v and k + i < sim.END_K:
                rain[k + i] = v
        last = max([k + i for i, v in enumerate(pattern) if v] or [k])
        y = r.random()
        if y < 0.12:
            gap = r.choice([58, 59, 60, 61, 62])          # dry intervals around the 6-hour separation
        elif y < 0.25:
            gap = r.randint(10, 57)                       # stays the same storm
        else:
            gap = r.randint(63, 240 * 6)
        k = last + gap + 1
    return rain


# ---------------------------------------------------------------- basins
def size_basin(r, acres, bid, down):
    z = r.choice([2.0, 3.0, 3.0])
    d_riser = round(r.uniform(1.6, 2.6), 2)
    d_spill = round(d_riser + r.uniform(0.7, 1.4), 2)
    target = 3600.0 * acres * r.uniform(0.55, 1.15)
    ratio = r.uniform(0.35, 0.6)
    L = 20.0
    while True:
        W = L * ratio
        v = L * W * d_spill + (L + W) * z * d_spill ** 2 + 4 / 3 * z * z * d_spill ** 3
        if v >= target:
            break
        L += 0.5
    bottom = round(r.uniform(150, 420), 2)
    return {"id": bid, "bottom": bottom, "L": round(L, 1), "W": round(L * ratio, 1), "Z": z,
            "orifice_d_in": r.choice([2.0, 2.5, 3.0, 3.0, 4.0, 5.0, 6.0]), "orifice_inv": bottom,
            "orifice_c": 0.6,
            "riser_d": r.choice([1.5, 2.0, 2.0, 2.5, 3.0]), "riser_crest": round(bottom + d_riser, 2),
            "riser_cw": 0.37, "riser_co": 0.6,
            "spill_crest": round(bottom + d_spill, 2), "spill_L": float(r.choice([6, 8, 10, 12, 15, 20])),
            "spill_cw": r.choice([0.29, 0.31, 0.33]), "down": down, "top": None}


def random_site(r, sid):
    nb = r.choice([1, 2, 2, 3, 3, 4])
    basins, areas, changes = [], [], {}
    ids = [f"{sid}-B{k + 1}" for k in range(nb)]
    downs = {}
    for k, bid in enumerate(ids):
        downs[bid] = ids[k + 1] if (k + 1 < nb and r.random() < 0.45) else None
    na = 0
    for bid in ids:
        local = 0.0
        for _ in range(r.choice([1, 2, 2, 3])):
            na += 1
            aid = f"{sid}-A{na:02d}"
            acres = round(r.uniform(1.5, 9.5), 2)
            local += acres
            hsg = r.choice("ABCCDD")
            tc = round(r.uniform(0.15, 0.7), 2)
            areas.append({"id": aid, "acres": acres, "tc": tc, "hsg": hsg, "basin": bid,
                          "cn": {s: CN[s][hsg] for s in CN}})
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
            changes[aid] = [c for c in chg if c[0] < sim.END_K]
        basins.append(size_basin(r, max(local, 2.0), bid, downs[bid]))
    return {"id": sid, "basins": basins, "areas": areas}, changes


# ---------------------------------------------------------------- planted sites (peak inflows worked by hand)
def single_area_site(sid, acres, tc, hsg, chg, basin_extra=None):
    b = {"id": f"{sid}-B1", "bottom": 200.0, "L": 120.0, "W": 60.0, "Z": 3.0, "orifice_d_in": 4.0,
         "orifice_inv": 200.0, "orifice_c": 0.6, "riser_d": 2.5, "riser_crest": 202.5, "riser_cw": 0.37,
         "riser_co": 0.6, "spill_crest": 203.8, "spill_L": 12.0, "spill_cw": 0.31, "down": None, "top": None}
    b.update(basin_extra or {})
    areas = [{"id": f"{sid}-A01", "acres": acres, "tc": tc, "hsg": hsg, "basin": b["id"],
              "cn": {s: CN[s][hsg] for s in CN}}]
    return {"id": sid, "basins": [b], "areas": areas}, {f"{sid}-A01": chg}


def planted_runoff_uh(sid):
    """64 acres (0.1 sq mi), Tc 0.75 h -> Tp = 0.05 + 0.45 = 0.50 h, qp = 484 x 0.1 / 0.5 = 96.8 cfs per inch.
    Unit hydrograph points every 0.1 h are at t/Tp = 0.2 j, exactly on table 16-1.  Soil D, disturbed: CN 94,
    S = 1000/94 - 10 = 0.638298, Ia = 0.127660.
    Storm 1: one interval of 1.00 in: Q = 0.872340^2 / 1.510638 = 0.503741 in; peak = 0.503741 x 96.8 = 48.762.
    Storm 2: 0.60 then 0.60 in: Q(0.6) = 0.472340^2 / 1.110638 = 0.200880; Q(1.2) = 1.072340^2 / 1.710638
    = 0.672213, so the increments are 0.200880 and 0.471333.  At j = 6: 0.200880 x 0.93 + 0.471333 x 1.00
    = 0.658151 (j = 5 gives 0.639220, j = 7 gives 0.595026); peak = 0.658151 x 96.8 = 63.709 cfs.
    Storm 3: 0.30 in only: Q = (0.30 - 0.12766)^2 / (0.30 + 0.510638) = 0.029701 / 0.810638 = 0.036640 in,
    peak = 0.036640 x 96.8 = 3.547 cfs."""
    site, chg = single_area_site(sid, 64.0, 0.75, "D", [(0, "disturbed")],
                                 {"L": 220.0, "W": 110.0, "riser_d": 3.0})
    rain = {}
    s1 = kday("2026-04-14T14:00")
    rain[s1] = 100
    s2 = kday("2026-05-02T13:00")
    rain[s2], rain[s2 + 1] = 60, 60
    s3 = kday("2026-06-09T16:30")
    rain[s3] = 30
    hand = {s1: 48.762, s2: 63.709, s3: 3.547}
    return site, chg, rain, hand, ["runoff", "unit-hydrograph", "storms"]


def planted_states(sid):
    """Two areas of 32 acres (0.05 sq mi each), Tc 0.75 h -> Tp 0.5 h, qp = 48.4 cfs per inch each, soil B.
    A01 is undisturbed (CN 61) until it is graded on 2026-05-01, then disturbed (CN 86).  A02 is stabilized (CN 69).
    Storm 1 (2026-04-20, 1.00 in in one interval): CN 61, S = 6.393443, Ia = 1.278689 > 1.00, no runoff; CN 69,
    S = 4.492754, Ia = 0.898551: Q = 0.101449^2 / 4.594203 = 0.002240, peak = 0.002240 x 48.4 = 0.108 cfs.
    Storm 2 (2026-05-01 03:00, the grading day, 1.00 in): A01 CN 86, S = 1.627907, Ia = 0.325581:
    Q = 0.674419^2 / 2.302326 = 0.197557 -> 9.562 cfs; A02 0.108 cfs at the same time; peak 9.670 cfs.
    (An area-weighted CN of 77.5 would give Q = 0.052935 over 0.1 sq mi = 5.124 cfs.)"""
    b = {"id": f"{sid}-B1", "bottom": 310.0, "L": 90.0, "W": 45.0, "Z": 3.0, "orifice_d_in": 3.0,
         "orifice_inv": 310.0, "orifice_c": 0.6, "riser_d": 2.0, "riser_crest": 312.2, "riser_cw": 0.37,
         "riser_co": 0.6, "spill_crest": 313.4, "spill_L": 10.0, "spill_cw": 0.31, "down": None, "top": None}
    areas = [{"id": f"{sid}-A01", "acres": 32.0, "tc": 0.75, "hsg": "B", "basin": b["id"],
              "cn": {s: CN[s]["B"] for s in CN}},
             {"id": f"{sid}-A02", "acres": 32.0, "tc": 0.75, "hsg": "B", "basin": b["id"],
              "cn": {s: CN[s]["B"] for s in CN}}]
    chg = {f"{sid}-A01": [(0, "undisturbed"), (kday("2026-05-01T00:00"), "disturbed")],
           f"{sid}-A02": [(0, "stabilized")]}
    s1, s2 = kday("2026-04-20T10:00"), kday("2026-05-01T03:00")
    rain = {s1: 100, s2: 100}
    return {"id": sid, "basins": [b], "areas": areas}, chg, rain, {s1: 0.108, s2: 9.670}, ["area-states", "runoff"]


def planted_series(sid):
    """Two basins in series with storms close together: carryover, riser control change, spillway near misses.
    Peaks come from the engine; this site checks routing families."""
    r = random.Random(7)
    b1 = {"id": f"{sid}-B1", "bottom": 250.0, "L": 70.0, "W": 35.0, "Z": 3.0, "orifice_d_in": 3.0,
          "orifice_inv": 250.0, "orifice_c": 0.6, "riser_d": 1.5, "riser_crest": 252.0, "riser_cw": 0.37,
          "riser_co": 0.6, "spill_crest": 253.0, "spill_L": 8.0, "spill_cw": 0.29, "down": f"{sid}-B2", "top": None}
    b2 = {"id": f"{sid}-B2", "bottom": 240.0, "L": 110.0, "W": 50.0, "Z": 2.0, "orifice_d_in": 4.0,
          "orifice_inv": 240.0, "orifice_c": 0.6, "riser_d": 2.0, "riser_crest": 242.2, "riser_cw": 0.37,
          "riser_co": 0.6, "spill_crest": 243.3, "spill_L": 12.0, "spill_cw": 0.31, "down": None, "top": None}
    areas = [{"id": f"{sid}-A01", "acres": 6.5, "tc": 0.3, "hsg": "C", "basin": b1["id"],
              "cn": {s: CN[s]["C"] for s in CN}},
             {"id": f"{sid}-A02", "acres": 4.2, "tc": 0.45, "hsg": "D", "basin": b2["id"],
              "cn": {s: CN[s]["D"] for s in CN}}]
    chg = {f"{sid}-A01": [(0, "disturbed")], f"{sid}-A02": [(0, "disturbed"), (kday("2026-08-01T00:00"), "stabilized")]}
    rain = {}
    k = kday("2026-06-03T13:00")
    for depth, hours, gap in [(180, 2, 59), (150, 1.5, 60), (260, 3, 200), (40, 1, 400), (320, 2, 61), (210, 1, 60)]:
        pat = storm_depths(r, depth, hours)
        for i, v in enumerate(pat):
            if v:
                rain[k + i] = v
        k = max(k + i for i, v in enumerate(pat) if v) + gap + 1
    return {"id": sid, "basins": [b1, b2], "areas": areas}, chg, rain, {}, ["routing", "series", "spillway", "storms"]


PLANTED = [planted_runoff_uh, planted_states, planted_series]


def fix_crests(site, rain, chg):
    """Move spillway crests until no peak is within 0.002 ft of a crest; set embankment tops above every peak."""
    for _ in range(40):
        rows, trace, st = sim.simulate(site, rain, chg)
        bad = {r_["basin"] for r_ in rows if abs(r_["margin"]) < 0.002}
        if not bad:
            break
        for b in site["basins"]:
            if b["id"] in bad:
                b["spill_crest"] = round(b["spill_crest"] + 0.01, 2)
    else:
        raise SystemExit(f"crest fixing failed for {site['id']}")
    for b in site["basins"]:
        peak = max(r_["peak_stage"] for r_ in rows if r_["basin"] == b["id"])
        b["top"] = round(max(peak + 0.6, b["spill_crest"] + 1.0), 1)
    return rows, st


def site_json(site, project):
    return {"site_id": site["id"], "project": project, "basins": [
        {"basin_id": b["id"], "bottom_elevation_ft": b["bottom"], "bottom_length_ft": b["L"],
         "bottom_width_ft": b["W"], "side_slope_h_per_v": b["Z"], "embankment_top_ft": b["top"],
         "dewatering_orifice": {"diameter_in": b["orifice_d_in"], "invert_elevation_ft": b["orifice_inv"],
                                "discharge_coefficient": b["orifice_c"]},
         "riser": {"diameter_ft": b["riser_d"], "crest_elevation_ft": b["riser_crest"],
                   "weir_coefficient": b["riser_cw"], "orifice_coefficient": b["riser_co"]},
         "emergency_spillway": {"crest_elevation_ft": b["spill_crest"], "crest_length_ft": b["spill_L"],
                                "weir_coefficient": b["spill_cw"]},
         "discharges_to": b["down"]} for b in site["basins"]],
        "drainage_areas": [{"area_id": a["id"], "acres": a["acres"], "time_of_concentration_h": a["tc"],
                            "hydrologic_soil_group": a["hsg"], "curve_numbers": a["cn"], "drains_to": a["basin"]}
                           for a in site["areas"]]}


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
            site, chg = random_site(r, sid)
            rain = make_rain(r)
            rows, st = fix_crests(site, rain, chg)
            tags[sid] = ["filler"]
        total += len(rows)
        sites.append(site_json(site, project))
        for k in sorted(rain):
            rain_out.append({"site_id": sid, "interval_start": kstamp(k), "rain_in": f"{rain[k] / 100:.2f}"})
        for a in site["areas"]:
            for k, s in chg[a["id"]]:
                states_out.append({"site_id": sid, "area_id": a["id"], "effective_date": kdate(k), "state": s})
        print(sid, len(site["basins"]), "basins", len(st), "storms", sum(x["spill"] for x in rows), "spill rows")
    sites.sort(key=lambda s: s["site_id"])
    rain_out.sort(key=lambda x: (x["site_id"], x["interval_start"]))
    states_out.sort(key=lambda x: (x["site_id"], x["area_id"], x["effective_date"]))
    data = {"sites.json": sites, "rain_gauge.json": rain_out, "area_states.json": states_out}
    for sub in ("environment/data", "tests/data"):
        p = ROOT / sub
        p.mkdir(parents=True, exist_ok=True)
        for name, obj in data.items():
            (p / name).write_text(json.dumps(obj, indent=1) + "\n")
    golden = {"rows": golden_rows, "examples": EXAMPLES}
    (ROOT / "tests" / "golden.json").write_text(json.dumps(golden, indent=1, sort_keys=True) + "\n")
    (ROOT / "tests" / "case_tags.json").write_text(json.dumps(tags, indent=1, sort_keys=True) + "\n")
    print(f"sites {len(sites)}, rows {total}, rain intervals {len(rain_out)}, state records {len(states_out)}")


# Published worked examples, with the values the documents print (checked against the engine's functions).
EXAMPLES = [
    {"source": "NEH 630.10 example 10-1", "check": "runoff", "rain_in": 4.3, "cn": 74, "expect": 1.82, "tol": 0.005},
    {"source": "NEH 630.10 table 10-2", "check": "runoff", "rain_in": 2.25, "cn": 80, "expect": 0.72, "tol": 0.005},
    {"source": "NEH 630.10 table 10-2", "check": "runoff", "rain_in": 5.00, "cn": 80, "expect": 2.89, "tol": 0.005},
    {"source": "NEH 630.16 example 16-1", "check": "tp", "tc_h": 2.3, "dd_h": 0.3, "expect": 1.53, "tol": 0.005},
    {"source": "NEH 630.16 example 16-1", "check": "qp", "tc_h": 2.3, "dd_h": 0.3, "sq_mi": 4.6, "expect": 1455,
     "tol": 1.0},
    {"source": "HEC-22 example 10.10", "check": "orifice", "diameter_ft": 0.49, "depth_ft": 3.3, "c": 0.6,
     "expect": 1.59, "tol": 0.005},
    {"source": "HEC-22 example 10.11 (L = 5.5 ft; the printed 3.5 uses a rounded 18.32 constant, the equation "
               "gives 3.43)", "check": "riser", "weir_length_ft": 5.5, "diameter_ft": 1.74,
     "cw": 0.41, "co": 0.6, "head_ft": 0.33, "expect": 3.5, "tol": 0.1},
    {"source": "HEC-22 example 10.11 (L = 5.5 ft)", "check": "riser", "weir_length_ft": 5.5, "diameter_ft": 1.74,
     "cw": 0.41, "co": 0.6, "head_ft": 1.31, "expect": 13.1, "tol": 0.05},
    {"source": "HEC-22 eq. 10.10 (L 100, W 50, Z 3, D 2)", "check": "storage", "L": 100, "W": 50, "Z": 3, "D": 2,
     "expect": 11896, "tol": 0.5},
]

if __name__ == "__main__":
    main()
