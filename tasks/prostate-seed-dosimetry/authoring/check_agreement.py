"""Solution, verifier engine and generator agree; prints the counts quoted in the READMEs."""
import sys
sys.dont_write_bytecode = True       # never leave __pycache__ in the submitted task folder
import collections
import csv
import json
from pathlib import Path

import engine_loader
import local_check

HERE = Path(__file__).resolve().parent
TASK = HERE.parent
DATA = TASK / "environment" / "data"


def main():
    truth = engine_loader.truth()
    gen = json.loads((HERE / "evidence" / "answers.json").read_text())
    worst_gen = max(abs(gen[f"{k[0]}/{k[1]}"]["dose_gy"] - v) / v for k, v in truth.items())
    out = local_check.run_solution(TASK)
    with open(out / "point_doses.csv") as fh:
        sol = {(r["patient_id"], r["point_id"]): float(r["dose_gy"]) for r in csv.DictReader(fh)}
    worst_sol = max(abs(sol[k] - round(v, 4)) for k, v in truth.items())
    patients = json.loads((DATA / "patients.json").read_text())
    batches = list(csv.DictReader(open(DATA / "batches.csv")))
    seeds = list(csv.DictReader(open(DATA / "seeds.csv")))
    points = list(csv.DictReader(open(DATA / "points.csv")))
    src = json.loads((DATA / "source_data.json").read_text())
    model_of = {b["patient_id"]: b["seed_model"] for b in batches}
    print(f"patients {len(patients)}, points {len(points)}, accepted seeds "
          f"{sum(s['review'] == 'accepted' for s in seeds)}, duplicate detections "
          f"{sum(s['review'] != 'accepted' for s in seeds)} in "
          f"{len({s['patient_id'] for s in seeds if s['review'] != 'accepted'})} patients")
    print("patients per seed model:", dict(collections.Counter(model_of[p["patient_id"]] for p in patients)))
    print("patients per radionuclide:", dict(collections.Counter(src[model_of[p["patient_id"]]]["radionuclide"]
                                                                 for p in patients)))
    print("batches per strength unit:", dict(collections.Counter(b["strength_unit"] for b in batches)))
    print("apparent-activity batches per vendor coefficient:",
          dict(collections.Counter(b["vendor_conversion_U_per_mCi"] for b in batches if b["vendor_conversion_U_per_mCi"])))
    print(f"patients with two batches: {sum(c == 2 for c in collections.Counter(b['patient_id'] for b in batches).values())}")
    print("calibration UTC offsets:", dict(collections.Counter(b["calibrated_at"][-6:] for b in batches)))
    late = sum(1 for b in batches if b["calibrated_at"][:10] > next(p["implant"][:10] for p in patients
                                                                     if p["patient_id"] == b["patient_id"]))
    print(f"batches calibrated after the implant date: {late}")
    print("points per structure:", dict(collections.Counter(p["structure"] for p in points)))
    fam = collections.Counter(t for a in gen.values() for t in a["tags"])
    print("points per rule family (dose moves by more than 0.15 percent if the rule is misread):")
    for t, n in sorted(fam.items()):
        print(f"  {t}: {n}")
    print(f"lowest and highest point dose: {min(truth.values()):.3f} and {max(truth.values()):.3f} Gy")
    print(f"generator vs engine worst relative difference: {worst_gen:.1e}")
    print(f"solution printed values vs engine rounded to 4 decimals: worst difference {worst_sol:.4f} Gy")
    ok = worst_gen < 1e-9 and worst_sol <= 0.00011
    print("AGREEMENT:", "OK" if ok else "PROBLEM")


if __name__ == "__main__":
    main()
