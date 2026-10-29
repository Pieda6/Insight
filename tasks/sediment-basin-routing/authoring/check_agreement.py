#!/usr/bin/env python3
"""Three-way agreement check for sediment-basin-routing (authoring tool): runs the reference solution, the
verifier engine and the generator's model (sim.py) on the shipped data and writes evidence/agreement.txt with the
largest differences found."""
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


def sim_rows():
    data = TASK / "tests" / "data"
    sites = json.loads((data / "sites.json").read_text())
    rain = json.loads((data / "rain_gauge.json").read_text())
    states = json.loads((data / "area_states.json").read_text())
    out = {}
    for s in sites:
        site = {"id": s["site_id"], "basins": [], "areas": []}
        for b in s["basins"]:
            o, r, sp = b["dewatering_orifice"], b["riser"], b["emergency_spillway"]
            site["basins"].append({
                "id": b["basin_id"], "bottom": b["bottom_elevation_ft"], "L": b["bottom_length_ft"],
                "W": b["bottom_width_ft"], "Z": b["side_slope_h_per_v"], "orifice_d_in": o["diameter_in"],
                "orifice_inv": o["invert_elevation_ft"], "orifice_c": o["discharge_coefficient"],
                "riser_d": r["diameter_ft"], "riser_crest": r["crest_elevation_ft"], "riser_cw": r["weir_coefficient"],
                "riser_co": r["orifice_coefficient"], "spill_crest": sp["crest_elevation_ft"],
                "spill_L": sp["crest_length_ft"], "spill_cw": sp["weir_coefficient"], "down": b["discharges_to"]})
        for a in s["drainage_areas"]:
            site["areas"].append({"id": a["area_id"], "acres": a["acres"], "tc": a["time_of_concentration_h"],
                                  "basin": a["drains_to"], "cn": a["curve_numbers"]})
        rn = {generate.kday(x["interval_start"]): round(float(x["rain_in"]) * 100) for x in rain
              if x["site_id"] == s["site_id"]}
        ch = {}
        for x in states:
            if x["site_id"] == s["site_id"]:
                ch.setdefault(x["area_id"], []).append((generate.kday(x["effective_date"] + "T00:00"), x["state"]))
        rows, _, _ = sim.simulate(site, rn, ch)
        for r in rows:
            out[(s["site_id"], r["basin"], generate.kstamp(r["start"]))] = (
                r["peak_in"], r["peak_out"], r["peak_stage"], "yes" if r["spill"] else "no")
    return out


def main():
    work = Path(tempfile.mkdtemp())
    shutil.copytree(TASK / "environment" / "data", work / "data")
    mod = types.ModuleType("solve")
    exec(compile((TASK / "solution" / "solve.py").read_text(), "solve.py", "exec"), mod.__dict__)
    mod.DATA, mod.OUT = work / "data", work / "out"
    mod.main()
    sol = {(r[0], r[1], r[2]): (float(r[3]), float(r[4]), float(r[5]), r[6])
           for r in list(csv.reader(open(work / "out" / "basin_storms.csv")))[1:]}
    eng = {(r[0], r[1], r[2]): (r[3], r[4], r[5], r[6]) for r in engine.expected()}
    gen = sim_rows()
    lines = [f"rows: solution {len(sol)}, engine {len(eng)}, generator {len(gen)}",
             f"same basin-storm keys in all three: {set(sol) == set(eng) == set(gen)}"]
    for name, a, b in (("engine vs generator (unrounded)", eng, gen), ("solution (3 decimals) vs engine", sol, eng)):
        diff = [0.0, 0.0, 0.0]
        spill = 0
        for k in b:
            for i in range(3):
                diff[i] = max(diff[i], abs(a[k][i] - b[k][i]))
            spill += a[k][3] != b[k][3]
        lines.append(f"{name}: max |peak inflow| {diff[0]:.2e} cfs, max |peak outflow| {diff[1]:.2e} cfs, "
                     f"max |peak stage| {diff[2]:.2e} ft, spillway disagreements {spill}")
    print("\n".join(lines))
    (HERE / "evidence").mkdir(exist_ok=True)
    (HERE / "evidence" / "agreement.txt").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
