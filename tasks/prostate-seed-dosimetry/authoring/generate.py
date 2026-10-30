"""Generate the edema-corrected post-implant evaluation cases (seed 20090137).

Writes patients.json, batches.csv, seeds.csv, contours.json to both data copies (source_data.json and
tg43u1_formalism.txt are written by tables.py and formalism_text.py), evidence/answers.json with the generator's
own metrics (sim.py) and ../tests/case_tags.json with, per patient and column, the misreadings that move the value
past the tag threshold.

Ranges: prostate volume before implant 25 to 55 cc; edema 10 to 100 percent at the end of the procedure, resolving
with a half-life of 4 to 25 days (Waterman et al., Int J Radiat Oncol Biol Phys 1998 reported a mean of about
9 days and a range of 4 to 25 days); CT 7 to 25 days after a palladium-103 implant and 14 to 45 days after an
iodine-125 implant. Seed strengths at implant 0.35 to 0.65 U (iodine-125) and 1.4 to 2.3 U (palladium-103) before
planting. Prescriptions 145 Gy (iodine-125) and 125 Gy (palladium-103).
"""
import sys
sys.dont_write_bytecode = True
import csv
import datetime as dt
import json
import math
import random
import time
from pathlib import Path

import sim

HERE = Path(__file__).resolve().parent
OUTS = [HERE / "../environment/data", HERE / "../tests/data"]
SRC = json.loads((OUTS[0] / "source_data.json").read_text())
SEED = 20090137
MODELS = ["6702", "200", "6711", "MED3633", "2301", "200", "MED3631-A/M", "MED3633", "I25.S06", "200",
          "IS-12501", "MED3633", "6702", "200", "6711", "MED3633", "2301", "200", "MED3631-A/M", "I25.S06"]
N_PATIENTS = len(MODELS)
# which criterion each patient is planted near, and on which side (None: unplanted)
PLANT = [("d90", +1), ("v100", -1), ("ud10", +1), ("rv100", -1), ("d90", -1), ("v100", +1), ("ud10", -1),
         ("rv100", +1), ("d90", +1), ("v100", -1), ("ud10", +1), ("rv100", -1), None, ("d90", -1), ("v100", +1),
         None, ("ud10", -1), ("rv100", +1), None, None]
SINGLE_MARKER = {2, 3, 5, 8, 9, 11, 12, 14, 16, 17, 19}      # patients (1-based) with one-marker seeds
TOL = {"gy": 0.001, "pct": 0.30, "cc": 0.030}                 # verifier tolerances
MARGIN = {"d90": 0.003, "v100": 0.8, "ud10": 0.003, "rv100": 0.08}
TAG = {"gy": 0.0015, "pct": 0.45, "cc": 0.045}                # a misreading is tagged when it moves a value this far
VENDOR_TZ = {"Amersham": -6, "Best": -5, "NASI": -8, "Bebig/Theragenics": -5, "Imagyn": -6, "Theragenics": -5}

SHORTCUTS = {
    "static_dose": {"static": True}, "volume_scaling": {"volume_scaling": True},
    "scaled_about_preimplant_volume": {"anchor_pre": True}, "integral_from_ct": {"from_ct": True},
    "two_d_for_single_marker": {"two_d_single": True}, "nearest_neighbour_instead_of_c3": {"nn_instead_c3": True},
    "linear_g_interpolation": {"g_linear": True}, "anisotropy_held_beyond_last_angle": {"f_hold_last_angle": True},
    "apparent_activity_unconverted": {"app_unconverted": True},
    "apparent_activity_fixed_coefficient": {"app_fixed": True}, "batch_total_as_per_seed": {"total_as_per_seed": True},
    "no_decay_to_implant": {"no_decay": True}, "calibration_offset_ignored": {"ignore_offset": True},
    "negative_decay_clamped": {"clamp_negative_decay": True},
    "implant_time_without_daylight_saving": {"naive_time": True}, "duplicates_kept": {"keep_duplicates": True},
    "floor_rank": {"floor_rank": True}, "urethra_subtracted_from_prostate": {"urethra_subtracted": True},
    "mean_life_144": {"tau_144": True},
}
COLS = ["d90_gy", "v100_pct", "v150_pct", "ud10_gy", "ud30_gy", "rv100_cc", "rd2cc_gy",
        "d90_meets", "v100_meets", "ud10_meets", "rv100_meets"]


def kind(col):
    return "gy" if col.endswith("_gy") else "pct" if col.endswith("_pct") else "cc" if col.endswith("_cc") else "cat"


def local_time(rng, day):
    return day.replace(hour=rng.randint(7, 15), minute=rng.randrange(60))


def fmt_local(t):
    return t.strftime("%Y-%m-%d %H:%M")


def polygon(rng, cx, cy, ax, by, phases, n=36):
    """Closed contour with vertices written to 0.01 mm, redrawn with a small radial jitter until no voxel centre lies
    within 0.02 mm of any edge, so that every point-in-polygon rule agrees on which voxels belong to it."""
    for _ in range(200):
        pts = []
        for m in range(n):
            ph = 2 * math.pi * m / n
            rho = 1 + 0.04 * math.sin(2 * ph + phases[0]) + 0.03 * math.sin(3 * ph + phases[1]) + 0.02 * math.sin(5 * ph + phases[2])
            jit = rng.uniform(-0.08, 0.08)                     # mm, enough to move an edge clear of a voxel centre
            pts.append([round(cx + (ax * rho + jit) * math.cos(ph), 2), round(cy + (by * rho + jit) * math.sin(ph), 2)])
        if edge_clear(pts):
            return pts
    raise RuntimeError("no clean polygon in 200 draws")


def edge_clear(poly, min_mm=0.02):
    """True when no voxel centre (i + 1/2) x 2.5 mm lies within min_mm of an edge of the polygon."""
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    for i in range(math.floor(min(xs) / 2.5 - 0.5), math.ceil(max(xs) / 2.5 - 0.5) + 1):
        px = (i + 0.5) * 2.5
        for j in range(math.floor(min(ys) / 2.5 - 0.5), math.ceil(max(ys) / 2.5 - 0.5) + 1):
            py = (j + 0.5) * 2.5
            for k in range(len(poly)):
                x0, y0 = poly[k]
                x1, y1 = poly[(k + 1) % len(poly)]
                dx, dy = x1 - x0, y1 - y0
                t = max(0.0, min(1.0, ((px - x0) * dx + (py - y0) * dy) / (dx * dx + dy * dy)))
                if math.hypot(px - x0 - t * dx, py - y0 - t * dy) < min_mm:
                    return False
    return True


def area(poly):
    s = 0.0
    for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1]):
        s += x0 * y1 - x1 * y0
    return abs(s) / 2.0


def slice_positions(zlo, zhi):
    k0 = math.ceil((zlo - 1.25) / 2.5)
    k1 = math.floor((zhi - 1.25) / 2.5)
    return [1.25 + 2.5 * k for k in range(k0, k1 + 1)]


def build_contours(rng, centre_mm, a, b, c):
    """Prostate, urethra and rectum slices; returns (structures dict, prostate polygon volume cc, urethra axis)."""
    x0, y0, z0 = centre_mm
    phases_p = [rng.uniform(0, 2 * math.pi) for _ in range(3)]
    phases_r = [rng.uniform(0, 2 * math.pi) for _ in range(3)]
    prostate, urethra, rectum = [], [], []
    ur_amp, ur_rad = rng.uniform(0.8, 1.8), rng.uniform(3.0, 3.5)
    gap, rr, ratio = rng.uniform(1.0, 2.5), rng.uniform(9.0, 13.0), rng.uniform(1.4, 1.7)
    zs = slice_positions(z0 - 10 * c + 1.0, z0 + 10 * c - 1.0)
    vol = 0.0
    for z in zs:
        f = math.sqrt(max(0.0, 1 - ((z - z0) / (10 * c)) ** 2))
        az, bz = 10 * a * f, 10 * b * f
        if min(az, bz) < 2.0:
            continue
        poly = polygon(rng, x0, y0, az, bz, phases_p)
        vol += area(poly) * 2.5
        prostate.append({"z_mm": round(z, 2), "points_mm": poly})
        if min(az, bz) > ur_rad + 3.5:
            ux = x0 + ur_amp * math.sin(math.pi * (z - z0) / (10 * c))
            uy = y0 + 0.08 * (z - z0)
            urethra.append({"z_mm": round(z, 2), "points_mm": polygon(rng, ux, uy, ur_rad, ur_rad, [0, 0, 0], 16)})
    for z in slice_positions(prostate[0]["z_mm"] - 5.5, prostate[-1]["z_mm"] + 5.5):
        ry = y0 - 10 * b - gap - rr + rng.uniform(-0.5, 0.5)
        rectum.append({"z_mm": round(z, 2), "points_mm": polygon(rng, x0 + rng.uniform(-2, 2), ry, rr * ratio, rr, phases_r, 32)})
    return {"prostate": prostate, "urethra": urethra, "rectum": rectum}, vol / 1000.0, (ur_amp,)


def make_patient(rng, k, model, want_single):
    pid = f"PT-{k:03d}"
    d = SRC[model]
    nuc = d["radionuclide"]
    rx = 145 if nuc == "I-125" else 125
    # times: implant near a 2026 clock change or in June; CT weeks later
    base = rng.choice([dt.datetime(2026, 3, 8), dt.datetime(2026, 11, 1), dt.datetime(2026, 6, 15)])
    implant = local_time(rng, base + dt.timedelta(days=rng.randint(-12, 12)))
    t_ct_days = rng.randint(7, 25) if nuc == "Pd-103" else rng.randint(14, 45)
    ct = local_time(rng, implant + dt.timedelta(days=t_ct_days))
    t_ct_h = (sim.ny_to_utc(fmt_local(ct)) - sim.ny_to_utc(fmt_local(implant))).total_seconds() / 3600.0
    # edema
    while True:
        v_pre = round(rng.uniform(25, 55), 1)
        delta = rng.uniform(0.10, 1.0)
        t_e = rng.uniform(4, 25)
        v_0 = round(v_pre * (1 + delta), 1)
        v_ct_target = v_pre + (v_0 - v_pre) * math.exp(-math.log(2) * t_ct_h / (24 * t_e))
        if v_ct_target >= 1.05 * v_pre and v_0 >= 1.08 * v_ct_target:
            break
    # prostate at the CT: ellipsoid semi-axes (cm) scaled to the target polygon volume
    ratio_b, ratio_c = rng.uniform(0.70, 0.85), rng.uniform(0.9, 1.2)
    a = (3 * v_ct_target / (4 * math.pi * ratio_b * ratio_c)) ** (1 / 3)
    b, c = a * ratio_b, a * ratio_c
    centre_mm = [rng.uniform(-6, 6), rng.uniform(-45, -25), rng.uniform(-20, 20)]
    structs, vol, _ = build_contours(rng, centre_mm, a, b, c)
    scale = (v_ct_target / vol) ** (1 / 3)
    structs, vol, _ = build_contours(rng, centre_mm, a * scale, b * scale, c * scale)
    v_ct = round(vol, 1)
    if not (v_ct >= 1.05 * v_pre and v_0 >= 1.08 * v_ct):
        return None
    a, b, c = a * scale, b * scale, c * scale
    # seeds inside the CT prostate, on needles of a 0.5 cm template away from the urethra
    x0, y0, z0 = [u / 10.0 for u in centre_mm]
    needles = []                       # peripheral loading: most needles in the outer ring, a few central ones
    for i in range(-7, 8):
        for j in range(-6, 7):
            x, y = 0.5 * i, 0.5 * j
            q = (x / (a * 0.97)) ** 2 + (y / (b * 0.97)) ** 2
            if q <= 1 and math.hypot(x, y) >= 0.65 and (q > 0.45 or rng.random() < 0.15):
                needles.append((x, y))
    rng.shuffle(needles)
    needles = needles[:rng.randint(18, 26)]
    seeds = []
    for x, y in needles:
        zmax = c * math.sqrt(max(0.05, 1 - (x / a) ** 2 - (y / b) ** 2)) + 0.15
        n = max(1, int(2 * zmax / 1.0) + 1)
        zs = -0.5 * (n - 1)
        for q in range(n):
            u = rng.random()
            tilt = rng.uniform(0, 15) if u < 0.7 else rng.uniform(15, 40) if u < 0.9 else rng.uniform(40, 90)
            phi = rng.uniform(0, 2 * math.pi)
            ax = (math.sin(math.radians(tilt)) * math.cos(phi), math.sin(math.radians(tilt)) * math.sin(phi),
                  math.cos(math.radians(tilt)))
            jit = lambda: max(-0.25, min(0.25, rng.gauss(0, 0.12)))
            ctr = (x0 + x + jit(), y0 + y + jit(), z0 + zs + q + jit())
            seeds.append((ctr, ax))
    single = set()
    if want_single:
        # seeds whose orientation was not resolved on the CT: every seed for the patients evaluated with the 1D
        # formalism throughout (the models whose anisotropy factor starts at 1 cm, where the Appendix C
        # short-distance model matters), one to four seeds otherwise
        if d["anisotropy_factor_1d"][0][0] >= 1.0:
            single = set(range(len(seeds)))
        else:
            single = set(rng.sample(range(len(seeds)), rng.randint(1, 4)))
    per_seed = rng.uniform(0.35, 0.65) if nuc == "I-125" else rng.uniform(1.4, 2.3)
    nb = 2 if rng.random() < 0.4 else 1
    split = len(seeds) if nb == 1 else len(seeds) - rng.randint(4, 10)
    batch_specs = []
    for bi in range(nb):
        count = split if bi == 0 else len(seeds) - split
        cal_local = (implant - dt.timedelta(days=rng.randint(-6, 21))).replace(hour=12, minute=0)
        dst = 1 if dt.datetime(2026, 3, 9) <= cal_local < dt.datetime(2026, 11, 2) else 0
        off = VENDOR_TZ[d["manufacturer"]] + dst
        cal = cal_local.replace(tzinfo=dt.timezone(dt.timedelta(hours=off)))
        u = rng.random()
        unit = "mCi_apparent" if u < 0.25 else "U_total" if u < 0.45 else "U_per_seed"
        gamma = (rng.choice([1.45, 1.464]) if nuc == "I-125" else rng.choice([1.476, 1.48])) if unit == "mCi_apparent" else None
        batch_specs.append({"id": f"{pid}-B{bi + 1}", "count": count, "cal": cal, "unit": unit, "gamma": gamma,
                            "strength_factor": rng.uniform(0.97, 1.03)})
    seed_rows = []
    bid_of = []
    for bi, bs in enumerate(batch_specs):
        bid_of += [bs["id"]] * bs["count"]
    for i, ((ctr, ax), bid) in enumerate(zip(seeds, bid_of)):
        row = {"patient_id": pid, "seed_id": f"S{i + 1:03d}", "batch_id": bid}
        if i in single:
            row.update({f"{cc}1_mm": f"{10 * ctr[kk]:.1f}" for kk, cc in enumerate("xyz")})
            row.update({f"{cc}2_mm": "" for cc in "xyz"})
        else:
            sep = rng.uniform(0.35, 0.45)
            m1 = [10 * (ctr[kk] - ax[kk] * sep / 2) for kk in range(3)]
            m2 = [10 * (ctr[kk] + ax[kk] * sep / 2) for kk in range(3)]
            if rng.random() < 0.5:
                m1, m2 = m2, m1
            row.update({f"{cc}1_mm": f"{m1[kk]:.1f}" for kk, cc in enumerate("xyz")})
            row.update({f"{cc}2_mm": f"{m2[kk]:.1f}" for kk, cc in enumerate("xyz")})
        row["review"] = "accepted"
        seed_rows.append(row)
    if rng.random() < 0.35:
        for _ in range(rng.randint(1, 3)):
            srow = rng.choice(seed_rows[:len(seeds)])
            dup = dict(srow)
            for key in ("x1_mm", "y1_mm", "z1_mm", "x2_mm", "y2_mm", "z2_mm"):
                if srow[key] != "":
                    dup[key] = f"{float(srow[key]) + rng.uniform(-0.4, 0.4):.1f}"
            dup["seed_id"] = f"S{len(seed_rows) + 1:03d}"
            dup["review"] = f"duplicate of {srow['seed_id']}"
            seed_rows.append(dup)
    patient = {"patient_id": pid, "implant": fmt_local(implant), "ct_scan": fmt_local(ct), "prescription_gy": rx,
               "volume_preimplant_cc": v_pre, "volume_postimplant_cc": v_0, "volume_ct_cc": v_ct}
    contours = {"slice_thickness_mm": 2.5, "structures": structs}
    return patient, batch_specs, per_seed, seed_rows, contours, model


def batch_rows(pid, model, batch_specs, per_seed_implant, implant_utc):
    rows = []
    half_h = SRC[model]["half_life_days"] * 24
    for bs in batch_specs:
        hours = (implant_utc - bs["cal"]).total_seconds() / 3600
        s_cal = per_seed_implant * bs["strength_factor"] * math.exp(math.log(2) * hours / half_h)
        row = {"patient_id": pid, "batch_id": bs["id"], "seed_model": model, "seeds_in_batch": bs["count"],
               "calibrated_at": bs["cal"].isoformat(timespec="minutes"), "exposure_rate_constant": ""}
        if bs["unit"] == "mCi_apparent":
            row.update(strength=f"{s_cal / (bs['gamma'] * sim.CGY_PER_R):.4f}", strength_unit="mCi_apparent",
                       exposure_rate_constant=f"{bs['gamma']}")
        elif bs["unit"] == "U_total":
            row.update(strength=f"{s_cal * bs['count']:.3f}", strength_unit="U_total")
        else:
            row.update(strength=f"{s_cal:.4f}", strength_unit="U_per_seed")
        rows.append(row)
    return rows


def geometry_ok(seed_rows, vox):
    """No voxel centre within 0.02 cm of a seed centre, and none within 0.005 cm of a two-marker seed's axis while
    inside the active length plus 0.1 cm (keeps every pair off the on-axis branch of the geometry function)."""
    seeds = []
    for s in seed_rows:
        if s["review"] != "accepted":
            continue
        m1 = [float(s[k]) / 10 for k in ("x1_mm", "y1_mm", "z1_mm")]
        if s["x2_mm"] == "":
            seeds.append((m1, None))
            continue
        m2 = [float(s[k]) / 10 for k in ("x2_mm", "y2_mm", "z2_mm")]
        c = [(p + q) / 2 for p, q in zip(m1, m2)]
        ax = [q - p for p, q in zip(m1, m2)]
        n = math.sqrt(sum(a * a for a in ax))
        seeds.append((c, [a / n for a in ax]))
    for centres in vox.values():
        for (x, y, z) in centres:
            for c, ax in seeds:
                dx, dy, dz = x - c[0], y - c[1], z - c[2]
                r2 = dx * dx + dy * dy + dz * dz
                if r2 < 0.02 ** 2:
                    return False
                if ax is not None and r2 < 0.16:
                    along = dx * ax[0] + dy * ax[1] + dz * ax[2]
                    if abs(along) < 0.35 and r2 - along * along < 0.005 ** 2:
                        return False
    return True


def choose_scale(doses, rx, plant, rng):
    """Factor on every seed strength that puts the planted criterion in its band (doses scale linearly)."""
    pro = sorted(doses["prostate"], reverse=True)
    ure = sorted(doses["urethra"], reverse=True)
    rec = sorted(doses["rectum"], reverse=True)
    if plant is None:
        d90 = sim.rank_dose(pro, 0.9)
        return rx * rng.uniform(0.96, 1.10) / d90
    crit, side = plant
    if crit == "d90":
        return rx * (1 + side * rng.uniform(0.003, 0.006)) / sim.rank_dose(pro, 0.9)
    if crit == "ud10":
        return 1.5 * rx * (1 + side * rng.uniform(0.003, 0.006)) / sim.rank_dose(ure, 0.1)
    if crit == "v100":
        n = len(pro)
        k = round(n * (95.0 + side * rng.uniform(0.8, 1.5)) / 100.0)
        thr = (pro[k - 1] + pro[k]) / 2.0
        return rx / thr
    if crit == "rv100":
        k = round((1.0 + side * rng.uniform(0.08, 0.15)) / sim.VOXEL_CC)
        thr = (rec[k - 1] + rec[k]) / 2.0
        return rx / thr
    raise ValueError(crit)


def margins_ok(doses, rx):
    m = sim.metrics(doses, rx)
    # realism: a reportable implant, not a grossly under- or overdosed one
    if not (0.90 <= m["d90_gy"] / rx <= 1.30 and 85.0 <= m["v100_pct"] <= 99.5 and m["ud10_gy"] <= 1.9 * rx
            and m["rv100_cc"] <= 3.0):
        return False, m
    if abs(m["d90_gy"] / rx - 1) < MARGIN["d90"] or abs(m["v100_pct"] - 95.0) < MARGIN["v100"]:
        return False, m
    if abs(m["ud10_gy"] / (1.5 * rx) - 1) < MARGIN["ud10"] or abs(m["rv100_cc"] - 1.0) < MARGIN["rv100"]:
        return False, m
    for f in (0.999, 1.001):
        scaled = {k: [x * f for x in v] for k, v in doses.items()}
        ms = sim.metrics(scaled, rx)
        if abs(ms["v100_pct"] - m["v100_pct"]) > TOL["pct"] / 2 or abs(ms["v150_pct"] - m["v150_pct"]) > TOL["pct"] / 2:
            return False, m
        if abs(ms["rv100_cc"] - m["rv100_cc"]) > TOL["cc"] / 2:
            return False, m
        if any(ms[c] != m[c] for c in COLS if c.endswith("_meets")):
            return False, m
    return True, m


def main():
    rng = random.Random(SEED)
    patients, batches, seeds, contours = [], [], [], {}
    redrawn = 0
    t0 = time.time()
    for k in range(1, N_PATIENTS + 1):
        model = MODELS[k - 1]
        while True:
            made = make_patient(rng, k, model, k in SINGLE_MARKER)
            if made is None:
                redrawn += 1
                continue
            pat, batch_specs, per_seed, seed_rows, cont, model = made
            vox = sim.structures(cont)
            if len(vox["rectum"]) < 128 or len(vox["urethra"]) < 20 or not geometry_ok(seed_rows, vox):
                redrawn += 1
                continue
            implant_utc = sim.ny_to_utc(pat["implant"])
            pid = pat["patient_id"]
            data = {"src": SRC, "patients": {pid: pat}, "contours": {pid: cont}, "seeds": {pid: seed_rows},
                    "batches": {b["batch_id"]: b for b in batch_rows(pid, model, batch_specs, per_seed, implant_utc)}}
            doses = sim.patient_doses(data, pid, vox=vox)
            scale = choose_scale(doses, pat["prescription_gy"], PLANT[k - 1], rng)
            rows = batch_rows(pid, model, batch_specs, per_seed * scale, implant_utc)
            data["batches"] = {b["batch_id"]: b for b in rows}
            doses = sim.patient_doses(data, pid, vox=vox)
            ok, m = margins_ok(doses, pat["prescription_gy"])
            if ok:
                break
            redrawn += 1
        patients.append(pat)
        batches += rows
        seeds += seed_rows
        contours[pid] = cont
        print(f"{pid} {model:12s} {PLANT[k - 1]} seeds {sum(s['review'] == 'accepted' for s in seed_rows)} "
              f"voxels {sum(len(v) for v in vox.values())} D90/Rx {m['d90_gy'] / pat['prescription_gy']:.4f} "
              f"V100 {m['v100_pct']:.2f} UD10/1.5Rx {m['ud10_gy'] / 1.5 / pat['prescription_gy']:.4f} "
              f"RV100 {m['rv100_cc']:.3f}  ({time.time() - t0:.0f} s)", flush=True)
    for out in OUTS:
        (out / "patients.json").write_text(json.dumps(patients, indent=1) + "\n")
        (out / "contours.json").write_text(json.dumps(contours, separators=(",", ":")) + "\n")
        for name, rows_ in (("batches.csv", batches), ("seeds.csv", seeds)):
            with open(out / name, "w", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=list(rows_[0]), lineterminator="\n")
                w.writeheader()
                w.writerows(rows_)
    print(f"patients {len(patients)}, accepted seeds {sum(s['review'] == 'accepted' for s in seeds)}, duplicate rows "
          f"{sum(s['review'] != 'accepted' for s in seeds)}, one-marker seeds {sum(s['x2_mm'] == '' for s in seeds)}, "
          f"batches {len(batches)}, patients redrawn {redrawn}", flush=True)
    tags(flush=True)


def tags(flush=False):
    """Generator metrics from the written files, and the misreadings that move each value past the tag threshold."""
    truth = sim.evaluate(OUTS[0])
    answers = {pid: {"metrics": m, "tags": {c: [] for c in COLS}} for pid, m in truth.items()}
    counts = {}
    for name, v in SHORTCUTS.items():
        alt = sim.evaluate(OUTS[0], v)
        n = 0
        for pid, m in truth.items():
            for c in COLS:
                kd = kind(c)
                a, b = m[c], alt[pid][c]
                moved = (a != b) if kd == "cat" else (abs(a - b) > TAG[kd] * (abs(a) if kd == "gy" else 1.0))
                if moved:
                    answers[pid]["tags"][c].append(name)
                    n += 1
        counts[name] = n
        print(f"  {name}: {n} values moved past the tag threshold", flush=flush)
    (HERE / "evidence" / "answers.json").write_text(json.dumps(answers, indent=1) + "\n")
    (HERE / "../tests/case_tags.json").write_text(
        json.dumps({pid: a["tags"] for pid, a in answers.items()}, indent=0, sort_keys=True) + "\n")
    return answers


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "tags":
        tags(flush=True)
    else:
        main()
