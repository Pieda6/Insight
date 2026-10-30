"""Solution, verifier engine and generator agree; prints every count quoted in the READMEs."""
import sys
sys.dont_write_bytecode = True       # never leave __pycache__ in the submitted task folder
import collections
import csv
import json
import math
import time
from pathlib import Path

import engine_loader
import local_check
import sim

HERE = Path(__file__).resolve().parent
TASK = HERE.parent
DATA = TASK / "environment" / "data"
COLS = ["d90_gy", "v100_pct", "v150_pct", "ud10_gy", "ud30_gy", "rv100_cc", "rd2cc_gy",
        "d90_meets", "v100_meets", "ud10_meets", "rv100_meets"]
TOL = {"gy": 0.001, "pct": 0.30, "cc": 0.030}
MARGIN = {"d90": 0.003, "v100": 0.8, "ud10": 0.003, "rv100": 0.08}


def kind(col):
    return "gy" if col.endswith("_gy") else "pct" if col.endswith("_pct") else "cc" if col.endswith("_cc") else "cat"


def diff(col, a, b):
    k = kind(col)
    if k == "cat":
        return 0.0 if a == b else 1.0
    return abs(a - b) / abs(b) if k == "gy" else abs(a - b)


def main():
    t0 = time.time()
    truth = engine_loader.truth()
    t_engine = time.time() - t0
    gen = json.loads((HERE / "evidence" / "answers.json").read_text())
    t0 = time.time()
    out = local_check.run_solution(TASK)
    t_solution = time.time() - t0
    with open(out / "implant_evaluation.csv") as fh:
        sol = {r["patient_id"]: r for r in csv.DictReader(fh)}
    worst = {"gen_vs_engine": collections.defaultdict(float), "sol_vs_engine": collections.defaultdict(float)}
    cat_diff = 0
    for pid, want in truth.items():
        for c in COLS:
            k = kind(c)
            g = gen[pid]["metrics"][c]
            s = sol[pid][c] if k == "cat" else float(sol[pid][c])
            worst["gen_vs_engine"][k] = max(worst["gen_vs_engine"][k], diff(c, g, want[c]))
            worst["sol_vs_engine"][k] = max(worst["sol_vs_engine"][k], diff(c, s, want[c]))
            cat_diff += (k == "cat") and (g != want[c] or s != want[c])

    patients = json.loads((DATA / "patients.json").read_text())
    batches = list(csv.DictReader(open(DATA / "batches.csv")))
    seeds = list(csv.DictReader(open(DATA / "seeds.csv")))
    contours = json.loads((DATA / "contours.json").read_text())
    src = json.loads((DATA / "source_data.json").read_text())
    model_of = {b["patient_id"]: b["seed_model"] for b in batches}
    nuc_of = {p["patient_id"]: src[model_of[p["patient_id"]]]["radionuclide"] for p in patients}
    accepted = [s for s in seeds if s["review"] == "accepted"]
    vox = {p["patient_id"]: {n: len(engine_vox(contours[p["patient_id"]]["structures"][n]))
                             for n in ("prostate", "urethra", "rectum")} for p in patients}
    print(f"patients {len(patients)}, accepted seeds {len(accepted)}, one-marker seeds "
          f"{sum(s['x2_mm'] == '' for s in accepted)} in {len({s['patient_id'] for s in accepted if s['x2_mm'] == ''})} "
          f"patients, duplicate detections {sum(s['review'] != 'accepted' for s in seeds)} in "
          f"{len({s['patient_id'] for s in seeds if s['review'] != 'accepted'})} patients")
    print("patients per seed model:", dict(collections.Counter(model_of[p["patient_id"]] for p in patients)))
    print("patients per radionuclide:", dict(collections.Counter(nuc_of.values())))
    print("batches per strength unit:", dict(collections.Counter(b["strength_unit"] for b in batches)))
    print("apparent-activity batches per exposure-rate constant:",
          dict(collections.Counter(b["exposure_rate_constant"] for b in batches if b["exposure_rate_constant"])))
    print(f"patients with two batches: {sum(c == 2 for c in collections.Counter(b['patient_id'] for b in batches).values())}")
    print("calibration UTC offsets:", dict(collections.Counter(b["calibrated_at"][-6:] for b in batches)))
    implant_day = {p["patient_id"]: p["implant"][:10] for p in patients}
    print(f"batches calibrated after the implant date: {sum(b['calibrated_at'][:10] > implant_day[b['patient_id']] for b in batches)}")
    tot = {n: sum(v[n] for v in vox.values()) for n in ("prostate", "urethra", "rectum")}
    print(f"voxels: prostate {tot['prostate']}, urethra {tot['urethra']}, rectum {tot['rectum']}, total {sum(tot.values())}; "
          f"per patient {min(sum(v.values()) for v in vox.values())} to {max(sum(v.values()) for v in vox.values())}")
    print(f"seed-voxel pairs: {sum(sum(vox[s['patient_id']].values()) for s in accepted)}")
    edema = []
    for p in patients:
        v_pre, v_0, v_ct = (float(p[k]) for k in ("volume_preimplant_cc", "volume_postimplant_cc", "volume_ct_cc"))
        t_ct_h = (sim.ny_to_utc(p["ct_scan"]) - sim.ny_to_utc(p["implant"])).total_seconds() / 3600
        lam_e = -math.log((v_ct - v_pre) / (v_0 - v_pre)) / t_ct_h
        edema.append((100 * (v_0 / v_pre - 1), math.log(2) / lam_e / 24, t_ct_h / 24, (v_0 / v_ct) ** (1 / 3), (v_pre / v_ct) ** (1 / 3)))
    print(f"edema at implant {min(e[0] for e in edema):.0f} to {max(e[0] for e in edema):.0f} percent of the pre-implant volume; "
          f"edema half-life {min(e[1] for e in edema):.1f} to {max(e[1] for e in edema):.1f} days; CT {min(e[2] for e in edema):.1f} to "
          f"{max(e[2] for e in edema):.1f} days after the implant; scale factor at implant {min(e[3] for e in edema):.3f} to "
          f"{max(e[3] for e in edema):.3f}, after full resolution {min(e[4] for e in edema):.3f} to {max(e[4] for e in edema):.3f}")
    static = sim.evaluate(DATA, {"static": True})
    ratio = [static[pid]["d90_gy"] / truth[pid]["d90_gy"] for pid in truth]
    print(f"static D90 over edema-corrected D90: {min(ratio):.3f} to {max(ratio):.3f} "
          f"(palladium-103 {min(r for r, pid in zip(ratio, truth) if nuc_of[pid] == 'Pd-103'):.3f} to "
          f"{max(r for r, pid in zip(ratio, truth) if nuc_of[pid] == 'Pd-103'):.3f})")
    rx = {p["patient_id"]: float(p["prescription_gy"]) for p in patients}
    import generate
    on_line = [p["patient_id"] for p, plant in zip(patients, generate.PLANT) if plant == ("rv100", 0)]
    for pid in on_line:
        rec = sorted(sim.patient_doses(data_of(DATA, pid), pid)["rectum"], reverse=True)
        k = round(1.0 / sim.VOXEL_CC)
        print(f"{pid} planted exactly on the rectal V100 line: {sum(d >= rx[pid] for d in rec)} rectum voxels at or above "
              f"the prescription = {truth[pid]['rv100_cc']:.6f} cc, criterion {truth[pid]['rv100_meets']}; rank {k} voxel "
              f"{100 * (rec[k - 1] / rx[pid] - 1):.3f} percent above the prescription, rank {k + 1} voxel "
              f"{100 * (1 - rec[k] / rx[pid]):.3f} percent below it")
    dist = {"d90": [], "v100": [], "ud10": [], "rv100": []}
    for pid, m in truth.items():
        dist["d90"].append(abs(m["d90_gy"] / rx[pid] - 1))
        dist["v100"].append(abs(m["v100_pct"] - 95.0))
        dist["ud10"].append(abs(m["ud10_gy"] / (1.5 * rx[pid]) - 1))
        if pid not in on_line:
            dist["rv100"].append(abs(m["rv100_cc"] - 1.0))
    for k, v in dist.items():
        print(f"closest {k} to its line: {min(v):.4f} (margin {MARGIN[k]}); values within twice the margin: {sum(x < 2 * MARGIN[k] for x in v)}")
    crit = {c: collections.Counter(m[c] for m in truth.values()) for c in COLS if c.endswith("_meets")}
    print("criteria:", {c: dict(v) for c, v in crit.items()})
    print(f"D90 as a fraction of the prescription: {min(m['d90_gy'] / rx[p] for p, m in truth.items()):.3f} to "
          f"{max(m['d90_gy'] / rx[p] for p, m in truth.items()):.3f}; V100 {min(m['v100_pct'] for m in truth.values()):.2f} to "
          f"{max(m['v100_pct'] for m in truth.values()):.2f} percent; urethral D10 {min(m['ud10_gy'] / rx[p] for p, m in truth.items()):.3f} to "
          f"{max(m['ud10_gy'] / rx[p] for p, m in truth.items()):.3f} of the prescription; rectal V100 "
          f"{min(m['rv100_cc'] for m in truth.values()):.3f} to {max(m['rv100_cc'] for m in truth.values()):.3f} cc")
    planted = collections.Counter(f"{p[0]} {'above' if p[1] > 0 else 'below' if p[1] < 0 else 'on the line'}"
                                  for p in generate.PLANT if p)
    print(f"planted patients: {sum(planted.values())} ({dict(sorted(planted.items()))}); unplanted: {generate.PLANT.count(None)}")
    golden = json.loads((TASK / "tests" / "golden.json").read_text())["examples"]
    print(f"golden checks: {len(golden)} ({dict(collections.Counter(e['check'] for e in golden))}); rate_1d from Table XV: "
          f"{sum(e['source'].startswith('TG-43U1 Table XV') for e in golden)}, from Eq. C3: "
          f"{sum(e['source'].startswith('Eq. C3') for e in golden)}")
    print(f"two-marker seeds: {sum(s['x2_mm'] != '' for s in accepted)}")
    fam = collections.Counter(t for a in gen.values() for tags in a["tags"].values() for t in tags)
    print("values per rule family (moved past the tag threshold when the rule is misread):")
    for t, n in sorted(fam.items()):
        print(f"  {t}: {n}")
    print(f"generator vs engine worst difference: doses {worst['gen_vs_engine']['gy']:.1e} relative, percentages "
          f"{worst['gen_vs_engine']['pct']:.4f} points, volumes {worst['gen_vs_engine']['cc']:.4f} cc; criteria differing: {cat_diff}")
    print(f"solution vs engine worst difference: doses {worst['sol_vs_engine']['gy']:.1e} relative, percentages "
          f"{worst['sol_vs_engine']['pct']:.4f} points, volumes {worst['sol_vs_engine']['cc']:.4f} cc")
    print(f"engine run time {t_engine:.0f} s, solution run time {t_solution:.0f} s")
    ok = (worst["gen_vs_engine"]["gy"] < 1e-4 and worst["gen_vs_engine"]["pct"] <= 0.05 and worst["gen_vs_engine"]["cc"] <= 0.02
          and worst["sol_vs_engine"]["gy"] < 1e-4 and worst["sol_vs_engine"]["pct"] <= 0.05
          and worst["sol_vs_engine"]["cc"] <= 0.02 and cat_diff == 0
          and all(min(dist[k]) >= MARGIN[k] for k in dist) and t_engine < 240)
    print("AGREEMENT:", "OK" if ok else "PROBLEM")
    sys.exit(0 if ok else 1)


def data_of(data_dir, pid):
    """The generator model's input structure for one patient."""
    data = sim.load(data_dir)
    return {"src": data["src"], "patients": {pid: data["patients"][pid]}, "contours": {pid: data["contours"][pid]},
            "seeds": {pid: data["seeds"][pid]}, "batches": {k: b for k, b in data["batches"].items() if b["patient_id"] == pid}}


def engine_vox(slices):
    sys.path.insert(0, str(TASK / "tests"))
    try:
        import engine
    finally:
        sys.path.remove(str(TASK / "tests"))
    return engine.voxel_centres(slices)


if __name__ == "__main__":
    main()
