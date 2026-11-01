"""Generate the treatment plans for tg71-monitor-unit-check (seed 20140301).

Writes environment/data/plans.json and the same file into tests/data, tests/case_tags.json (for each beam, the
misreadings that move its MU outside the tolerance of every MU the protocol allows) and evidence/answers.json.
The commissioning tables (TG-71 Tables II to IX, 6 MV and 9 MeV) and machine.json are written by hand and copied.
"""
import sys
sys.dont_write_bytecode = True       # never leave __pycache__ in the submitted task folder
import json
import random
import shutil
from pathlib import Path

TASK = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TASK / "tests"))
import engine  # noqa: E402

TOL = 0.003
SEED = 20140301
FAMILIES = ("sc_shaped", "no_projection", "oar_unprojected", "oar_ignored", "tray_ignored", "wf_at_10cm",
            "heterogeneity_ignored", "batho_inverted", "inverse_square_ignored", "sp_surface_field",
            "mayneord_ignored", "pdd_inverse_square_to_point", "se_equivalent_square", "isodose_ignored",
            "ssdeff_ignored", "air_gap_factor_ignored")
SITES = [("pelvis", 4), ("prostate", 4), ("lung", 3), ("whole brain", 2), ("spine", 2), ("breast", 2),
         ("abdomen", 3), ("head and neck", 3), ("chest wall", 2), ("skin", 1), ("rib metastasis", 2)]
NAMES = ["AP", "PA", "RLAT", "LLAT", "RAO", "LPO", "LAO", "RPO", "SUP", "BOOST"]


def r1(x):
    return round(x + 0.0, 1)


def jaws(rng, lo=2.5, hi=12.0):
    if rng.random() < 0.55:
        a, b = r1(rng.uniform(lo, hi)), r1(rng.uniform(lo, hi))
        return {"X1": a, "X2": a, "Y1": b, "Y2": b}
    return {k: r1(rng.uniform(lo, hi)) for k in ("X1", "X2", "Y1", "Y2")}


def inside(b, rng):
    """An off-axis point in the plane of the point, at least 1.5 cm (at the isocenter) inside the jaws."""
    j, spd = b["jaws_cm"], b["ssd_cm"] + b["point"]["depth_cm"]
    xs = (-j["X1"] + 1.5, j["X2"] - 1.5)
    ys = (-j["Y1"] + 1.5, j["Y2"] - 1.5)
    if xs[0] >= xs[1] or ys[0] >= ys[1]:
        return [0.0, 0.0]
    xi, yi = rng.uniform(*xs), rng.uniform(*ys)
    return [r1(xi * spd / 100.0), r1(yi * spd / 100.0)]


def photon(rng, kind):
    b = {"modality": "photon", "energy": "6 MV", "jaws_cm": jaws(rng), "field_shaping": "open",
         "shaped_field_equivalent_square_cm": None, "wedge_deg": None, "heterogeneity": None}
    j = b["jaws_cm"]
    jeq = engine.eqsq(j["X1"] + j["X2"], j["Y1"] + j["Y2"])
    shape = rng.random()
    if kind in ("sad", "off", "wedge", "het") and shape < 0.6:
        b["field_shaping"] = "MLC"
    elif kind in ("ssd",) and shape < 0.5:
        b["field_shaping"] = "block on tray"
    elif shape < 0.15:
        b["field_shaping"] = "block on tray"
    if b["field_shaping"] != "open":
        b["shaped_field_equivalent_square_cm"] = r1(jeq * rng.uniform(0.6, 0.9))
    if kind == "ssd":
        b["setup"] = "SSD"
        b["ssd_cm"] = rng.choice([90.0, 100.0, 100.0, 110.0, 115.0, 120.0])
        d = r1(rng.uniform(2.0, 18.0))
        iso_depth = None
    else:
        b["setup"] = "SAD"
        iso_depth = r1(rng.uniform(3.0, 18.0))
        b["ssd_cm"] = r1(100.0 - iso_depth)
        d = iso_depth
        if kind == "off":
            d = r1(min(24.0, max(2.0, iso_depth + rng.choice([-1, 1]) * rng.uniform(1.0, 5.0))))
    b["point"] = {"depth_cm": d, "off_axis_cm": [0.0, 0.0]}
    if kind in ("off", "ssd") and b["field_shaping"] != "MLC" and rng.random() < 0.7:
        b["point"]["off_axis_cm"] = inside(b, rng)
    if kind == "wedge":
        b["wedge_deg"] = rng.choice([15, 30, 45, 60])
        if rng.random() < 0.4:
            b["setup"], b["ssd_cm"] = "SSD", rng.choice([90.0, 100.0, 110.0])
            b["point"]["depth_cm"] = r1(rng.uniform(3.0, 15.0))
    if kind == "het":
        top = r1(rng.uniform(1.5, 5.0))
        bot = r1(top + rng.uniform(3.0, 9.0))
        rho = round(rng.uniform(0.2, 0.4), 2)
        b["point"]["depth_cm"] = d = r1(max(d, bot + rng.uniform(1.5, 6.0)))
        b["ssd_cm"] = r1(100.0 - d) if b["setup"] == "SAD" else b["ssd_cm"]
        b["heterogeneity"] = {"correction": rng.choice(["RTAR", "power law"]),
                              "layers": [{"from_cm": 0.0, "to_cm": top, "rho_e": 1.0},
                                         {"from_cm": top, "to_cm": bot, "rho_e": rho},
                                         {"from_cm": bot, "to_cm": r1(d + rng.uniform(3, 8)), "rho_e": 1.0}]}
    b["dose_cgy"] = r1(rng.uniform(40.0, 220.0))
    return b


def electron(rng):
    app = rng.choice([10, 15, 20, 25])
    L = rng.choice([x / 2 for x in range(8, 2 * app + 1)])
    W = rng.choice([x / 2 for x in range(8, 2 * app + 1)])
    ssd = rng.choice([100.0, 100.0, 105.0, 110.0, 115.0])
    return {"modality": "electron", "energy": "9 MeV", "applicator": f"{app}x{app}", "insert_cm": [L, W],
            "ssd_cm": ssd, "prescription_isodose_pct": rng.choice([100, 90, 90, 80]),
            "extended_distance_method": None if ssd == 100.0 else rng.choice(["effective SSD", "air gap"]),
            "dose_cgy": r1(rng.uniform(150.0, 300.0))}


def tags(t, b, truth):
    out = []
    for fam in FAMILIES:
        try:
            base = engine.allowed(t, b)
            alt = engine.allowed(t, b, frozenset([fam]))
        except (ValueError, AssertionError, KeyError):
            continue
        moved = [a for a, o in zip(alt, base) if abs(a - o) > 1e-9]
        if moved and all(min(abs(a / w - 1) for w in truth) > TOL for a in moved):
            out.append(fam)
    return out


def main():
    rng = random.Random(SEED)
    t = engine.Tables()
    patients, answers, ctags, redrawn = [], {}, {}, 0
    kinds = ["sad"] * 6 + ["off"] * 5 + ["ssd"] * 6 + ["wedge"] * 3 + ["het"] * 3
    n = 0
    for site, nb in SITES * 3:
        n += 1
        pid = f"P{n:02d}"
        beams = []
        nb = max(1, nb + rng.choice([-1, 0, 0, 1]))
        for k in range(nb):
            while True:
                if rng.random() < {"skin": 0.9, "chest wall": 0.8, "breast": 0.3, "head and neck": 0.3}.get(site, 0.0):
                    b = electron(rng)
                else:
                    b = photon(rng, rng.choice(kinds))
                b = {"beam_id": f"{pid}-{k + 1}", "name": NAMES[k % len(NAMES)], **b}
                try:
                    truth = engine.allowed(t, b)
                    spread = max(truth) / min(truth) - 1
                    if spread > TOL:
                        raise ValueError("variants disagree")
                    break
                except (ValueError, AssertionError) as e:   # out of the tabulated range: redraw
                    redrawn += 1
            beams.append(b)
            answers[b["beam_id"]] = truth
            ctags[b["beam_id"]] = tags(t, b, truth)
        patients.append({"patient_id": pid, "site": site, "beams": beams})
    plans = {"patients": patients}
    for d in (TASK / "environment" / "data", TASK / "tests" / "data"):
        (d / "plans.json").write_text(json.dumps(plans, indent=1) + "\n")
    for f in (TASK / "environment" / "data").iterdir():
        if f.name != "plans.json":
            shutil.copy(f, TASK / "tests" / "data" / f.name)
    (TASK / "tests" / "case_tags.json").write_text(json.dumps(ctags, indent=1) + "\n")
    (TASK / "authoring" / "evidence" / "answers.json").write_text(json.dumps(answers, indent=1) + "\n")
    beams = [b for p in patients for b in p["beams"]]
    print(f"{len(patients)} patients, {len(beams)} beams "
          f"({sum(b['modality'] == 'electron' for b in beams)} electron), {redrawn} draws redrawn")
    for fam in FAMILIES:
        print(f"{sum(fam in v for v in ctags.values()):4d}  {fam}")
    print("beams with no tag:", sum(not v for v in ctags.values()))


if __name__ == "__main__":
    main()
