#!/usr/bin/env python3
"""Reference solution for prostate-seed-dosimetry.

Post-implant dosimetry of permanent prostate seed implants with the AAPM TG-43U1 protocol (Rivard et al., Med Phys
2004;31:633-674). Each seed's centre and axis come from its two CT end markers. Dose rate per seed: Eq. (1), the 2D
formalism with the line-source geometry function of Eq. (4) and g_L(r); F(r, theta) mirrored about the transverse
plane (Sec. III A) and equal to 1 at 90 degrees (Eq. 8); nearest-neighbour values outside the tabulated distances
(Appendix C, Eq. C1). Source strength: air-kerma strength per seed, from a batch total, or from apparent activity
times the vendor's exposure-rate constant (Appendix E), decayed to the implant time with the Table XIII half-life.
Total dose to complete decay: initial dose rate times the mean life, T1/2 / ln 2.
"""
import csv
import datetime as dt
import json
import math
from pathlib import Path

DATA = Path("/app/data")
OUT = Path("/app/output")

CGY_AIR_PER_R = 0.876                  # air kerma per roentgen (W/e = 33.97 J/C)
REF_R, REF_THETA = 1.0, 90.0


def read_csv(name):
    with open(DATA / name, newline="") as fh:
        return list(csv.DictReader(fh))


def nth_sunday(year, month, n):
    first = dt.date(year, month, 1)
    return first + dt.timedelta(days=(6 - first.weekday()) % 7 + 7 * (n - 1))


def new_york_to_utc(text):
    wall = dt.datetime.strptime(text.strip(), "%Y-%m-%d %H:%M")
    start = dt.datetime.combine(nth_sunday(wall.year, 3, 2), dt.time(2, 0))
    end = dt.datetime.combine(nth_sunday(wall.year, 11, 1), dt.time(1, 0))
    offset_h = 4 if start <= wall < end else 5
    return (wall + dt.timedelta(hours=offset_h)).replace(tzinfo=dt.timezone.utc)


def lerp_index(xs, x):
    """Segment index and weight for x, clamped to the table ends (nearest neighbour outside)."""
    if x <= xs[0]:
        return 0, 0.0
    if x >= xs[-1]:
        return len(xs) - 2, 1.0
    j = 0
    while xs[j + 1] < x:
        j += 1
    return j, (x - xs[j]) / (xs[j + 1] - xs[j])


class Source:
    def __init__(self, d):
        self.L = d["active_length_cm"]
        self.Lambda = d["dose_rate_constant_cGy_per_h_per_U"]
        self.g = d["radial_dose_function_line_source"]
        F = d["anisotropy_function"]
        self.f_r = F["r_cm"]
        self.f_theta = F["theta_deg"] + [90.0]
        self.f = F["F"] + [[1.0] * len(self.f_r)]
        self.g_ref = self.G(REF_R, REF_THETA)

    def G(self, r, theta):
        th = math.radians(theta)
        rho, z = r * math.sin(th), r * math.cos(th)
        if rho == 0.0:
            return 1.0 / (r * r - self.L * self.L / 4.0)
        beta = math.atan((z + self.L / 2) / rho) - math.atan((z - self.L / 2) / rho)
        return beta / (self.L * rho)

    def radial(self, r):
        j, w = lerp_index([a for a, _ in self.g], r)
        return math.exp((1 - w) * math.log(self.g[j][1]) + w * math.log(self.g[j + 1][1]))

    def anisotropy(self, r, theta):
        if theta > 90.0:
            theta = 180.0 - theta
        i, u = lerp_index(self.f_theta, theta)
        j, w = lerp_index(self.f_r, r)
        f = self.f
        return ((1 - u) * ((1 - w) * f[i][j] + w * f[i][j + 1]) + u * ((1 - w) * f[i + 1][j] + w * f[i + 1][j + 1]))

    def dose_rate(self, sk, r, theta):
        return sk * self.Lambda * self.G(r, theta) / self.g_ref * self.radial(r) * self.anisotropy(r, theta)


def strength_per_seed(b):
    value = float(b["strength"])
    unit = b["strength_unit"]
    if unit == "U_per_seed":
        return value
    if unit == "U_total":
        return value / int(b["seeds_in_batch"])
    if unit == "mCi_apparent":
        return value * float(b["exposure_rate_constant"]) * CGY_AIR_PER_R
    raise ValueError(f"unknown strength unit {unit}")


def main():
    src = json.loads((DATA / "source_data.json").read_text())
    models = {m: Source(d) for m, d in src.items()}
    patients = {p["patient_id"]: p for p in json.loads((DATA / "patients.json").read_text())}
    batches = {b["batch_id"]: b for b in read_csv("batches.csv")}
    seeds = {}
    for s in read_csv("seeds.csv"):
        if s["review"] == "accepted":
            seeds.setdefault(s["patient_id"], []).append(s)

    implanted = {}
    for pid, rows in seeds.items():
        t_implant = new_york_to_utc(patients[pid]["implant"])
        lst = []
        for s in rows:
            b = batches[s["batch_id"]]
            model = b["seed_model"]
            half_h = src[model]["half_life_days"] * 24.0
            hours = (t_implant - dt.datetime.fromisoformat(b["calibrated_at"])).total_seconds() / 3600.0
            sk = strength_per_seed(b) * math.exp(-math.log(2) * hours / half_h)
            a = [float(s[k]) / 10.0 for k in ("x1_mm", "y1_mm", "z1_mm")]
            c = [float(s[k]) / 10.0 for k in ("x2_mm", "y2_mm", "z2_mm")]
            centre = [(u + v) / 2 for u, v in zip(a, c)]
            axis = [v - u for u, v in zip(a, c)]
            n = math.sqrt(sum(x * x for x in axis))
            lst.append((models[model], sk, half_h / math.log(2), centre, [x / n for x in axis]))
        implanted[pid] = lst

    out = []
    for p in read_csv("points.csv"):
        q = [float(p[k]) / 10.0 for k in ("x_mm", "y_mm", "z_mm")]
        dose_cgy = 0.0
        for source, sk, mean_life_h, centre, axis in implanted[p["patient_id"]]:
            v = [q[k] - centre[k] for k in range(3)]
            r = math.sqrt(sum(x * x for x in v))
            cos_t = max(-1.0, min(1.0, sum(v[k] * axis[k] for k in range(3)) / r))
            dose_cgy += source.dose_rate(sk, r, math.degrees(math.acos(cos_t))) * mean_life_h
        out.append([p["patient_id"], p["point_id"], f"{dose_cgy / 100.0:.3f}"])

    out.sort(key=lambda r: (r[0], r[1]))
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "point_doses.csv", "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["patient_id", "point_id", "dose_gy"])
        w.writerows(out)


if __name__ == "__main__":
    main()
