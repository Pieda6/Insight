#!/usr/bin/env python3
"""Three-way agreement check for sediment-basin-routing (authoring tool): runs the reference solution, the
verifier engine and the generator's model (sim.py) on the shipped data and writes evidence/agreement.txt."""
import csv
import json
import shutil
import sys
import tempfile
import types
from pathlib import Path

HERE = Path(__file__).resolve().parent
TASK = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(TASK / "tests"))
import engine  # noqa: E402
import generate  # noqa: E402
import sim  # noqa: E402


def to_sim(s):
    site = {"id": s["site_id"], "p2": s["two_year_24_hour_rainfall_in"], "basins": [], "areas": []}
    for b in s["basins"]:
        g = b["geometry"]
        if g["type"] == "trapezoid":
            c = {"shape": "trapezoid", "bottom": g["bottom_elevation_ft"], "L": g["bottom_length_ft"],
                 "W": g["bottom_width_ft"], "Z": g["side_slope_h_per_v"]}
        else:
            cs = [[x["elevation_ft"], x["area_sqft"]] for x in g["contours"]]
            c = {"shape": "contours", "bottom": cs[0][0], "contours": cs}
        c.update({"id": b["basin_id"], "top": b["embankment_top_ft"]})
        if b["cell"] == "forebay":
            d = b["divider"]
            c.update({"down": None, "divider": {
                "into": d["drains_into"], "weir_crest": d["weir_crest_elevation_ft"], "weir_L": d["weir_length_ft"],
                "weir_cw": d["weir_coefficient"],
                "orifice": {"d_in": d["orifice"]["diameter_in"], "inv": d["orifice"]["invert_elevation_ft"],
                            "c": d["orifice"]["discharge_coefficient"]}}})
        else:
            o, r, sp = b["dewatering_orifice"], b["riser"], b["emergency_spillway"]
            c.update({"orifice": {"d_in": o["diameter_in"], "inv": o["invert_elevation_ft"],
                                  "c": o["discharge_coefficient"]},
                      "riser_d": r["diameter_ft"], "riser_crest": r["crest_elevation_ft"],
                      "riser_cw": r["weir_coefficient"], "riser_co": r["orifice_coefficient"],
                      "spill_crest": sp["crest_elevation_ft"], "spill_L": sp["crest_length_ft"],
                      "spill_cw": sp["weir_coefficient"], "down": b["discharges_to"]})
        site["basins"].append(c)
    for a in s["drainage_areas"]:
        site["areas"].append({"id": a["area_id"], "acres": a["acres"], "basin": a["drains_to"], "cn": a["curve_numbers"],
                              "path": a["flow_path"], "surface": a["sheet_flow_surface"]})
    return site


def sim_rows():
    data = TASK / "tests" / "data"
    rain = json.loads((data / "rain_gauge.json").read_text())
    states = json.loads((data / "area_states.json").read_text())
    out = {}
    for s in json.loads((data / "sites.json").read_text()):
        rn = {generate.kday(x["interval_start"]): round(float(x["rain_in"]) * 100) for x in rain
              if x["site_id"] == s["site_id"]}
        ch = {}
        for x in states:
            if x["site_id"] == s["site_id"]:
                ch.setdefault(x["area_id"], []).append((generate.kday(x["effective_date"] + "T00:00"), x["state"]))
        rows, _, _ = sim.simulate(to_sim(s), rn, ch)
        for r in rows:
            out[(s["site_id"], r["basin"], generate.kstamp(r["start"]))] = (
                r["peak_in"], r["peak_out"], r["peak_stage"], generate.kstamp(r["peak_k"]),
                "yes" if r["spill"] else "no", r["spill_volume"])
    return out


def main():
    work = Path(tempfile.mkdtemp())
    shutil.copytree(TASK / "environment" / "data", work / "data")
    mod = types.ModuleType("solve")
    exec(compile((TASK / "solution" / "solve.py").read_text(), "solve.py", "exec"), mod.__dict__)
    mod.DATA, mod.OUT = work / "data", work / "out"
    mod.main()
    sol = {(r[0], r[1], r[2]): (float(r[3]), float(r[4]), float(r[5]), r[6], r[7], float(r[8]))
           for r in list(csv.reader(open(work / "out" / "basin_storms.csv")))[1:]}
    eng = {(r[0], r[1], r[2]): (r[3], r[4], r[5], r[6], r[7], r[8]) for r in engine.expected()}
    gen = sim_rows()
    lines = [f"rows: solution {len(sol)}, engine {len(eng)}, generator {len(gen)}",
             f"same basin-storm keys in all three: {set(sol) == set(eng) == set(gen)}"]
    for name, a, b in (("engine vs generator (unrounded)", eng, gen), ("solution (3 decimals) vs engine", sol, eng)):
        diff = [0.0] * 6
        for k in b:
            for i in (0, 1, 2, 5):
                diff[i] = max(diff[i], abs(a[k][i] - b[k][i]))
            diff[3] += a[k][3] != b[k][3]
            diff[4] += a[k][4] != b[k][4]
        lines.append(f"{name}: max |peak inflow| {diff[0]:.2e} cfs, |peak outflow| {diff[1]:.2e} cfs, "
                     f"|peak stage| {diff[2]:.2e} ft, |spill volume| {diff[5]:.2e} cf, time-of-peak differences "
                     f"{int(diff[3])}, spillway disagreements {int(diff[4])}")
    print("\n".join(lines))
    (HERE / "evidence").mkdir(exist_ok=True)
    (HERE / "evidence" / "agreement.txt").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
