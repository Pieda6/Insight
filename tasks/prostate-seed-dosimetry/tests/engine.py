"""Independent TG-43U1 dose engine for the verifier.

2D formalism (Rivard et al., Med Phys 2004;31:633-674, Eq. 1) with the line-source geometry function (Eq. 4), the
consensus data in data/source_data.json, nearest-neighbour values outside the tabulated distances (Appendix C,
Eq. C1), F(r, 90 degrees) = 1 by definition (Eq. 8), mirror symmetry about the transverse plane (Sec. III A),
apparent activity converted with the vendor's own exposure-rate constant (Appendix E), decay from calibration to
implant with the Table XIII half-lives, and the total dose to complete decay (initial dose rate times the mean life).
"""
import bisect
import csv
import datetime as dt
import json
import math
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
CGY_PER_R = 0.876
LN2 = math.log(2.0)


def load():
    src = json.loads((DATA / "source_data.json").read_text())
    patients = json.loads((DATA / "patients.json").read_text())

    def rows(name):
        with open(DATA / name, newline="") as fh:
            return list(csv.DictReader(fh))
    return src, patients, rows("batches.csv"), rows("seeds.csv"), rows("points.csv")


def _segment(xs, x):
    """Index j with xs[j] <= x <= xs[j+1], clamped to the table."""
    return min(max(bisect.bisect_right(xs, x) - 1, 0), len(xs) - 2)


def radial(table, r):
    xs = [a for a, _ in table]
    if r <= xs[0]:
        return table[0][1]
    if r >= xs[-1]:
        return table[-1][1]
    j = _segment(xs, r)
    w = (r - xs[j]) / (xs[j + 1] - xs[j])
    return table[j][1] ** (1 - w) * table[j + 1][1] ** w                # ln g linear in r


def anisotropy(F, r, theta):
    rs = F["r_cm"]
    th = list(F["theta_deg"]) + [90.0]
    grid = [list(row) for row in F["F"]] + [[1.0] * len(rs)]
    t = 180.0 - theta if theta > 90.0 else theta
    i = _segment(th, t)
    u = (t - th[i]) / (th[i + 1] - th[i])
    rc = min(max(r, rs[0]), rs[-1])                                     # nearest neighbour outside the table
    j = _segment(rs, rc)
    w = (rc - rs[j]) / (rs[j + 1] - rs[j])
    lo = grid[i][j] * (1 - w) + grid[i][j + 1] * w
    hi = grid[i + 1][j] * (1 - w) + grid[i + 1][j + 1] * w
    return lo * (1 - u) + hi * u


def geometry(L, rho, z):
    """Line-source G_L from the cylindrical coordinates of the point (rho off axis, z along axis)."""
    a = (rho * rho + (z - L / 2) ** 2) ** 0.5
    b = (rho * rho + (z + L / 2) ** 2) ** 0.5
    cos_beta = (a * a + b * b - L * L) / (2 * a * b)
    beta = math.acos(max(-1.0, min(1.0, cos_beta)))
    return beta / (L * rho)


def rate_per_unit(d, r, theta):
    """Dose rate (cGy/h) per U of air-kerma strength."""
    L = d["active_length_cm"]
    rho, z = r * math.sin(math.radians(theta)), r * math.cos(math.radians(theta))
    g0 = 2.0 * math.atan(L / 2.0) / L
    return (d["dose_rate_constant_cGy_per_h_per_U"] * geometry(L, rho, z) / g0
            * radial(d["radial_dose_function_line_source"], r) * anisotropy(d["anisotropy_function"], r, theta))


def rate_1d(d, r):
    """Eq. (11): the 1D line-source formalism with phi_an(r) (used to check the tables against Table XV)."""
    L = d["active_length_cm"]
    phi = d["anisotropy_factor_1d"]
    xs = [a for a, _ in phi]
    j = _segment(xs, min(max(r, xs[0]), xs[-1]))
    w = (min(max(r, xs[0]), xs[-1]) - xs[j]) / (xs[j + 1] - xs[j])
    p = phi[j][1] + w * (phi[j + 1][1] - phi[j][1])
    return (d["dose_rate_constant_cGy_per_h_per_U"] * geometry(L, r, 0.0) / (2 * math.atan(L / 2) / L)
            * radial(d["radial_dose_function_line_source"], r) * p)


def _sunday(y, m, nth):
    d = dt.date(y, m, 1)
    return d + dt.timedelta(days=(6 - d.weekday()) % 7 + 7 * (nth - 1))


def new_york(text):
    """New York local wall time to an aware UTC datetime (US rules since 2007)."""
    t = dt.datetime.strptime(text, "%Y-%m-%d %H:%M")
    edt = dt.datetime.combine(_sunday(t.year, 3, 2), dt.time(2)) <= t < dt.datetime.combine(_sunday(t.year, 11, 1),
                                                                                             dt.time(1))
    return (t + dt.timedelta(hours=4 if edt else 5)).replace(tzinfo=dt.timezone.utc)


def per_seed_strength(batch, src):
    nuc = src[batch["seed_model"]]["radionuclide"]
    value = float(batch["strength"])
    unit = batch["strength_unit"]
    if unit == "U_per_seed":
        return value
    if unit == "U_total":
        return value / int(batch["seeds_in_batch"])
    if unit == "mCi_apparent":
        return value * float(batch["exposure_rate_constant"]) * CGY_PER_R
    raise ValueError(unit)


def expected():
    """{(patient_id, point_id): dose in Gy}."""
    src, patients, batches, seeds, points = load()
    implant = {p["patient_id"]: new_york(p["implant"]) for p in patients}
    bt = {b["batch_id"]: b for b in batches}
    sources = {}
    for s in seeds:
        if s["review"] != "accepted":
            continue
        b = bt[s["batch_id"]]
        d = src[b["seed_model"]]
        p1 = [float(s["x1_mm"]), float(s["y1_mm"]), float(s["z1_mm"])]
        p2 = [float(s["x2_mm"]), float(s["y2_mm"]), float(s["z2_mm"])]
        centre = [(u + v) / 20.0 for u, v in zip(p1, p2)]
        axis = [v - u for u, v in zip(p1, p2)]
        n = math.sqrt(sum(a * a for a in axis))
        t_half_h = d["half_life_days"] * 24.0
        elapsed = (implant[s["patient_id"]] - dt.datetime.fromisoformat(b["calibrated_at"])).total_seconds() / 3600
        sk0 = per_seed_strength(b, src) * 2.0 ** (-elapsed / t_half_h)
        sources.setdefault(s["patient_id"], []).append((centre, [a / n for a in axis], d, sk0 * t_half_h / LN2))
    out = {}
    for p in points:
        q = [float(p["x_mm"]) / 10, float(p["y_mm"]) / 10, float(p["z_mm"]) / 10]
        total = 0.0
        for centre, axis, d, sk_tau in sources[p["patient_id"]]:
            v = [q[k] - centre[k] for k in range(3)]
            r = math.sqrt(sum(a * a for a in v))
            c = sum(v[k] * axis[k] for k in range(3)) / r
            theta = math.degrees(math.acos(max(-1.0, min(1.0, c))))
            total += sk_tau * rate_per_unit(d, r, theta)
        assert math.isfinite(total)
        out[(p["patient_id"], p["point_id"])] = total / 100.0
    return out
