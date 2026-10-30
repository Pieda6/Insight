"""Generate the post-implant prostate seed dosimetry cases (seed 20040301).

Writes patients.json, batches.csv, seeds.csv and points.csv to both data copies, and evidence/answers.json with the
generator's own doses (first implementation, sim below) and, per point, the shortcuts that move its dose by more
than 0.3 percent (the rule families used by the tests).
"""
import sys
sys.dont_write_bytecode = True       # never leave __pycache__ in the submitted task folder
import csv
import datetime as dt
import json
import math
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = json.loads((HERE / "../environment/data/source_data.json").read_text())
OUTS = [HERE / "../environment/data", HERE / "../tests/data"]
N_PATIENTS = 60
R_PER_ROENTGEN = 0.876          # cGy air kerma per R (the factor behind TG-43U1 Appendix E's 1.270 and 1.293)
FAMILY_SHIFT = 0.0015

UTC = dt.timezone.utc


# ---------------------------------------------------------------- sim (generator's model) ----------
def tables(model, v):
    d = SRC[model]
    g = d["radial_dose_function_point_source" if v.get("g_point") else "radial_dose_function_line_source"]
    F = d["anisotropy_function"]
    thetas = list(F["theta_deg"])
    rows = [list(x) for x in F["F"]]
    if not v.get("no_90"):
        thetas.append(90.0)
        rows.append([1.0] * len(F["r_cm"]))
    return d, g, F["r_cm"], thetas, rows


def interp1(xs, ys, x, log=False, extrap=False):
    if x <= xs[0] or x >= xs[-1]:
        if not extrap:
            return ys[0] if x <= xs[0] else ys[-1]
        j = 0 if x <= xs[0] else len(xs) - 2
    else:
        j = 0
        while xs[j + 1] < x:
            j += 1
    t = (x - xs[j]) / (xs[j + 1] - xs[j])
    if log:
        return math.exp(math.log(ys[j]) + t * (math.log(ys[j + 1]) - math.log(ys[j])))
    return ys[j] + t * (ys[j + 1] - ys[j])


def dose_rate_per_sk(model, r, theta, v):
    """cGy/h per U at polar coordinates (r cm, theta degrees) of one seed."""
    d, g, fr, ft, rows = tables(model, v)
    L = d["active_length_cm"] if not v.get("length_045") else 0.45
    th = theta if theta <= 90 or v.get("no_mirror") else 180.0 - theta
    th = min(th, 90.0)
    rad = math.radians(th)
    if v.get("point_geometry"):
        G, G0 = 1 / r ** 2, 1.0
    else:
        z, rho = r * math.cos(rad), r * math.sin(rad)
        beta = math.atan2(z + L / 2, rho) - math.atan2(z - L / 2, rho)
        G = beta / (L * rho)
        G0 = 2 * math.atan(L / 2) / L
    gr = interp1([a for a, _ in g], [b for _, b in g], r, log=not v.get("g_linear"), extrap=v.get("g_extrap"))
    if v.get("one_d"):
        phi = d["anisotropy_factor_1d"]
        Fv = interp1([a for a, _ in phi], [b for _, b in phi], r)
    else:
        col = [interp1(ft, [row[k] for row in rows], th) for k in range(len(fr))]
        Fv = interp1(fr, col, r, extrap=v.get("f_extrap"))
    return d["dose_rate_constant_cGy_per_h_per_U"] * G / G0 * gr * Fv


def ny_to_utc(text, naive=False):
    wall = dt.datetime.strptime(text, "%Y-%m-%d %H:%M")
    if naive:
        return wall.replace(tzinfo=UTC) + dt.timedelta(hours=5)
    y = wall.year
    mar = dt.datetime(y, 3, 8 + (6 - dt.date(y, 3, 8).weekday()) % 7, 2)
    nov = dt.datetime(y, 11, 1 + (6 - dt.date(y, 11, 1).weekday()) % 7, 2)
    off = 4 if mar <= wall < nov else 5
    return wall.replace(tzinfo=UTC) + dt.timedelta(hours=off)


def seed_strength(batch, implant_utc, v):
    """Air-kerma strength (U) of one seed of the batch at the implant time."""
    model = batch["seed_model"]
    s = float(batch["strength"])
    unit = batch["strength_unit"]
    if unit == "U_total" and not v.get("total_as_per_seed"):
        s /= int(batch["seeds_in_batch"])
    if unit == "mCi_apparent":
        if v.get("app_unconverted"):
            pass
        elif v.get("app_fixed"):
            s *= 1.270 if SRC[model]["radionuclide"] == "I-125" else 1.293
        else:
            s *= float(batch["exposure_rate_constant"]) * R_PER_ROENTGEN
    cal = dt.datetime.fromisoformat(batch["calibrated_at"])
    if v.get("ignore_offset"):
        cal = cal.replace(tzinfo=UTC)
    hours = (implant_utc - cal).total_seconds() / 3600.0
    if v.get("no_decay"):
        hours = 0.0
    t_half = SRC[model]["half_life_days"] * 24
    return s * math.exp(-math.log(2) * hours / t_half)


def point_dose(p, seeds, batches, implant, v=None):
    v = v or {}
    implant_utc = ny_to_utc(implant, naive=v.get("naive_time"))
    total = 0.0
    for s in seeds:
        if s["review"] != "accepted" and not v.get("keep_duplicates"):
            continue
        b = batches[s["batch_id"]]
        m1 = [float(s[k]) / 10 for k in ("x1_mm", "y1_mm", "z1_mm")]
        m2 = [float(s[k]) / 10 for k in ("x2_mm", "y2_mm", "z2_mm")]
        c = m1 if v.get("first_marker") else [(a + b2) / 2 for a, b2 in zip(m1, m2)]
        ax = [b2 - a for a, b2 in zip(m1, m2)]
        n = math.sqrt(sum(a * a for a in ax))
        ax = [a / n for a in ax]
        dvec = [p[k] - c[k] for k in range(3)]
        r = math.sqrt(sum(a * a for a in dvec))
        cos = max(-1.0, min(1.0, sum(a * b2 for a, b2 in zip(dvec, ax)) / r))
        theta = math.degrees(math.acos(cos))
        sk = seed_strength(b, implant_utc, v)
        tau = SRC[b["seed_model"]]["half_life_days"] * 24 * (1.44 if v.get("tau_144") else 1 / math.log(2))
        total += sk * dose_rate_per_sk(b["seed_model"], r, theta, v) * tau
    return total / 100.0


SHORTCUTS = {
    "linear_g_interpolation": {"g_linear": True}, "point_source_radial_dose_function": {"g_point": True},
    "point_source_geometry": {"point_geometry": True}, "anisotropy_held_beyond_last_angle": {"no_90": True},
    "anisotropy_extrapolated_in_r": {"f_extrap": True},
    "one_dimensional_anisotropy_factor": {"one_d": True}, "no_mirror_beyond_90": {"no_mirror": True},
    "capsule_length_for_L": {"length_045": True}, "mean_life_144": {"tau_144": True},
    "apparent_activity_unconverted": {"app_unconverted": True},
    "apparent_activity_fixed_coefficient": {"app_fixed": True}, "batch_total_as_per_seed": {"total_as_per_seed": True},
    "no_decay_to_implant": {"no_decay": True}, "calibration_offset_ignored": {"ignore_offset": True},
    "implant_time_without_daylight_saving": {"naive_time": True}, "duplicates_kept": {"keep_duplicates": True},
    "first_marker_as_centre": {"first_marker": True},
}


# ---------------------------------------------------------------- case generation -------------------
def make_patient(rng, k, model):
    pid = f"PT-{k:03d}"
    nuc = SRC[model]["radionuclide"]
    # implant date: most near a 2026 clock change
    base = rng.choice([dt.datetime(2026, 3, 8), dt.datetime(2026, 11, 1), dt.datetime(2026, 6, 15)])
    day = base + dt.timedelta(days=rng.randint(-12, 12))
    implant = day.replace(hour=rng.randint(7, 15), minute=rng.randrange(0, 60))
    if implant.month == 11 and implant.day == 1 and implant.hour < 3:
        implant = implant.replace(hour=9)
    implant_s = implant.strftime("%Y-%m-%d %H:%M")
    centre = [rng.uniform(-30, 30), rng.uniform(-80, -40), rng.uniform(-60, 60)]          # mm
    a, b, c = rng.uniform(1.9, 2.5), rng.uniform(1.4, 1.9), rng.uniform(1.8, 2.4)         # cm
    per_seed = rng.uniform(0.35, 0.65) if nuc == "I-125" else rng.uniform(1.4, 2.3)          # U at implant
    # needles on a 0.5 cm template inside the ellipse, away from the urethra
    needles = []
    for i in range(-6, 7):
        for j in range(-5, 6):
            x, y = 0.5 * i, 0.5 * j
            q = (x / (a * 0.9)) ** 2 + (y / (b * 0.9)) ** 2
            if q <= 1 and math.hypot(x, y) >= 0.5 and (q > 0.35 or rng.random() < 0.35):
                needles.append((x, y))
    rng.shuffle(needles)
    needles = needles[:rng.randint(16, 24)]
    seeds = []
    for x, y in needles:
        zmax = c * math.sqrt(max(0.05, 1 - (x / a) ** 2 - (y / b) ** 2))
        n = max(1, int(2 * zmax / 1.0))
        z0 = -0.5 * (n - 1)
        for q in range(n):
            u = rng.random()
            tilt = rng.uniform(0, 15) if u < 0.7 else rng.uniform(15, 40) if u < 0.9 else rng.uniform(40, 90)
            phi = rng.uniform(0, 2 * math.pi)
            ax = (math.sin(math.radians(tilt)) * math.cos(phi), math.sin(math.radians(tilt)) * math.sin(phi),
                  math.cos(math.radians(tilt)))
            ctr = (x + rng.gauss(0, 0.12), y + rng.gauss(0, 0.12), z0 + q * 1.0 + rng.gauss(0, 0.12))
            seeds.append((ctr, ax))
    # batches: one main batch, sometimes a second (extra seeds ordered separately)
    vendor_tz = {"Amersham": -6, "Best": -5, "NASI": -8, "Bebig/Theragenics": -5, "Imagyn": -6,
                 "Theragenics": -5}[SRC[model]["manufacturer"]]
    implant_utc = ny_to_utc(implant_s)
    nb = 2 if rng.random() < 0.35 else 1
    split = len(seeds) if nb == 1 else len(seeds) - rng.randint(4, 10)
    batch_rows, seed_batch = [], []
    t_half = SRC[model]["half_life_days"] * 24
    for bi in range(nb):
        bid = f"{pid}-B{bi + 1}"
        count = split if bi == 0 else len(seeds) - split
        strength_at_implant = per_seed * rng.uniform(0.97, 1.03)
        cal_local = (implant - dt.timedelta(days=rng.randint(-6, 21))).replace(hour=12, minute=0)
        # vendor offset: standard or daylight time of its own zone
        dst = 1 if dt.datetime(2026, 3, 9) <= cal_local < dt.datetime(2026, 11, 2) else 0
        off = vendor_tz + dst
        cal = cal_local.replace(tzinfo=dt.timezone(dt.timedelta(hours=off)))
        hours = (implant_utc - cal).total_seconds() / 3600
        s_cal = strength_at_implant * math.exp(math.log(2) * hours / t_half)
        u = rng.random()
        row = {"patient_id": pid, "batch_id": bid, "seed_model": model, "seeds_in_batch": count,
               "calibrated_at": cal.isoformat(timespec="minutes"), "exposure_rate_constant": ""}
        if u < 0.25:
            gamma = rng.choice([1.45, 1.464]) if SRC[model]["radionuclide"] == "I-125" else rng.choice([1.476, 1.48])
            row.update(strength=f"{s_cal / (gamma * R_PER_ROENTGEN):.4f}", strength_unit="mCi_apparent",
                       exposure_rate_constant=f"{gamma}")
        elif u < 0.45:
            row.update(strength=f"{s_cal * count:.3f}", strength_unit="U_total")
        else:
            row.update(strength=f"{s_cal:.4f}", strength_unit="U_per_seed")
        batch_rows.append(row)
        seed_batch += [bid] * count
    seed_rows = []
    for i, ((ctr, ax), bid) in enumerate(zip(seeds, seed_batch)):
        sep = rng.uniform(0.35, 0.45)
        m1 = [10 * (ctr[k] - ax[k] * sep / 2) + centre[k] for k in range(3)]
        m2 = [10 * (ctr[k] + ax[k] * sep / 2) + centre[k] for k in range(3)]
        if rng.random() < 0.5:
            m1, m2 = m2, m1
        seed_rows.append({"patient_id": pid, "seed_id": f"S{i + 1:03d}", "batch_id": bid,
                          **{f"{c}1_mm": f"{v:.1f}" for c, v in zip("xyz", m1)},
                          **{f"{c}2_mm": f"{v:.1f}" for c, v in zip("xyz", m2)}, "review": "accepted"})
    # duplicate detections
    if rng.random() < 0.3:
        for _ in range(rng.randint(1, 3)):
            src = rng.choice(seed_rows[:len(seeds)])
            dup = dict(src)
            for key in ("x1_mm", "y1_mm", "z1_mm", "x2_mm", "y2_mm", "z2_mm"):
                dup[key] = f"{float(src[key]) + rng.uniform(-0.4, 0.4):.1f}"
            dup["seed_id"] = f"S{len(seed_rows) + 1:03d}"
            dup["review"] = f"duplicate of {src['seed_id']}"
            seed_rows.append(dup)
    # dose points (cm, local frame), written in mm
    pts = []
    for zz in [-0.8 * c + 1.6 * c * t / 7 for t in range(8)]:
        pts.append(("urethra", (0.15 * math.sin(zz), 0.1 * zz / c + rng.uniform(-0.05, 0.05), zz)))
    for t in range(4):
        zz = -0.6 * c + 1.2 * c * t / 3
        pts.append(("rectum", (rng.uniform(-0.5, 0.5), -(b + rng.uniform(0.35, 0.6)), zz)))
    for t in range(3):
        u1, u2 = rng.uniform(0, 2 * math.pi), rng.uniform(-0.8, 0.8)
        pts.append(("prostate", (a * math.cos(u1) * math.sqrt(1 - u2 ** 2), b * math.sin(u1) * math.sqrt(1 - u2 ** 2),
                                 c * u2)))
    for t in range(3):
        pts.append(("prostate", (rng.uniform(-0.7, 0.7) * a, rng.uniform(-0.7, 0.7) * b, rng.uniform(-0.7, 0.7) * c)))
    point_rows = []
    for j, (struct, q) in enumerate(pts):
        point_rows.append({"patient_id": pid, "point_id": f"P{j + 1:02d}", "structure": struct,
                           **{f"{cc}_mm": f"{10 * q[k] + centre[k]:.1f}" for k, cc in enumerate("xyz")}})
    patient = {"patient_id": pid, "implant": implant_s, "prescription_gy": 145 if nuc == "I-125" else 125}
    return patient, batch_rows, seed_rows, point_rows


def geometry_ok(seed_rows, point_rows):
    """Every point lies outside L/2 + 0.07 cm of every seed centre and off its axis by at least 0.05 cm."""
    for p in point_rows:
        q = [float(p[k]) / 10 for k in ("x_mm", "y_mm", "z_mm")]
        for s in seed_rows:
            m1 = [float(s[k]) / 10 for k in ("x1_mm", "y1_mm", "z1_mm")]
            m2 = [float(s[k]) / 10 for k in ("x2_mm", "y2_mm", "z2_mm")]
            c = [(a + b) / 2 for a, b in zip(m1, m2)]
            ax = [b - a for a, b in zip(m1, m2)]
            n = math.sqrt(sum(a * a for a in ax))
            d = [q[k] - c[k] for k in range(3)]
            r = math.sqrt(sum(a * a for a in d))
            along = abs(sum(d[k] * ax[k] for k in range(3)) / n)
            if r < 0.30 or math.sqrt(max(0.0, r * r - along * along)) < 0.05:
                return False
    return True


def main():
    rng = random.Random(20040301)
    models = list(SRC)
    patients, batches, seeds, points = [], [], [], []
    redrawn = 0
    for k in range(1, N_PATIENTS + 1):
        model = models[(k - 1) % len(models)]
        while True:
            pat, b, s, p = make_patient(rng, k, model)
            if geometry_ok(s, p):
                break
            redrawn += 1
        patients.append(pat)
        batches += b
        seeds += s
        points += p
    for out in OUTS:
        (out / "patients.json").write_text(json.dumps(patients, indent=1) + "\n")
        for name, rows in (("batches.csv", batches), ("seeds.csv", seeds), ("points.csv", points)):
            with open(out / name, "w", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
                w.writeheader()
                w.writerows(rows)
    answers = rebuild_answers()
    lows = min(a["dose_gy"] for a in answers.values())
    print(f"patients {len(patients)}, points {len(points)}, seeds {sum(s['review'] == 'accepted' for s in seeds)}, "
          f"duplicate rows {sum(s['review'] != 'accepted' for s in seeds)}, batches {len(batches)}, "
          f"patients redrawn for geometry {redrawn}, lowest point dose {lows:.2f} Gy")
    fam = {}
    for a in answers.values():
        for t in a["tags"]:
            fam[t] = fam.get(t, 0) + 1
    for t in SHORTCUTS:
        print(f"  {t}: {fam.get(t, 0)} points moved by more than {FAMILY_SHIFT:.2%}")


def rebuild_answers():
    """Generator doses and shortcut tags computed from the written files."""
    data = OUTS[0]
    patients = json.loads((data / "patients.json").read_text())
    rd = lambda n: list(csv.DictReader(open(data / n)))
    batches = {b["batch_id"]: b for b in rd("batches.csv")}
    seeds, points = {}, rd("points.csv")
    for s in rd("seeds.csv"):
        seeds.setdefault(s["patient_id"], []).append(s)
    implants = {p["patient_id"]: p["implant"] for p in patients}
    answers = {}
    for p in points:
        q = [float(p[k]) / 10 for k in ("x_mm", "y_mm", "z_mm")]
        pid = p["patient_id"]
        d = point_dose(q, seeds[pid], batches, implants[pid])
        tags = [name for name, v in SHORTCUTS.items()
                if abs(point_dose(q, seeds[pid], batches, implants[pid], v) - d) > FAMILY_SHIFT * d]
        answers[f"{pid}/{p['point_id']}"] = {"dose_gy": d, "tags": tags}
    (HERE / "evidence" / "answers.json").write_text(json.dumps(answers, indent=0) + "\n")
    tags = {k: a["tags"] for k, a in answers.items()}
    (HERE / "../tests/case_tags.json").write_text(json.dumps(tags, indent=0, sort_keys=True) + "\n")
    return answers


if __name__ == "__main__":
    main()
