#!/usr/bin/env python3
"""Reference solution for prostate-seed-dosimetry: edema-corrected post-implant evaluation.

Dose per seed and tissue point follows AAPM TG-43U1 (Rivard et al., Med Phys 2004;31:633-674): Eq. (1) with the
line-source geometry function of Eq. (4) and g_L for seeds with two markers; Eq. (11) with the anisotropy factor for
seeds with one marker, with Appendix C Eq. (C3) below the first tabulated anisotropy-factor distance; ln g_L linear
in r, F bilinear in r and theta with F(r, 90) = 1 and mirror symmetry; nearest-neighbour values outside the tables
(Eq. C1). Source strength per seed from the certificate (Appendix E for apparent activity), decayed to the implant.

Edema: V(t) = V_pre + (V_0 - V_pre) exp(-lambda_e t) with lambda_e fixed by the CT volume; every seed-to-tissue
distance scales by s(t) = (V(t) / V_CT)^(1/3). The total dose is the integral of the dose rate from the implant to
complete decay. With y = (V_0 - V_pre) exp(-lambda_e t) the integral per seed and point is
(lambda_e Y^alpha)^-1 int_0^Y y^(alpha-1) rate(s(y) r) dy, alpha = lambda / lambda_e, Y = V_0 - V_pre,
integrated with Gauss-Jacobi (weight y^(alpha-1)) up to the first y at which s(y) r crosses a table node and with
Gauss-Legendre on geometrically split intervals after it, so every piece of the integrand is smooth.

Voxels: 2.5 mm cubes with centres at (i + 1/2) 2.5 mm in x and y and at the slice positions in z, inside a
structure's polygon by the even-odd rule. Indices by ceiling ranks on the descending dose list.
"""
import csv
import datetime as dt
import json
import math
from pathlib import Path

DATA = Path("/app/data")
OUT = Path("/app/output")

CGY_AIR_PER_R = 0.876                  # air kerma per roentgen (W/e = 33.97 J/C)
VOXEL_MM = 2.5
VOXEL_CC = (VOXEL_MM / 10.0) ** 3
LN2 = math.log(2.0)
N_GAUSS = 8


def read_csv(name):
    with open(DATA / name, newline="") as fh:
        return list(csv.DictReader(fh))


# ----------------------------------------------------------------------------- time ----------------------------
def nth_sunday(year, month, n):
    first = dt.date(year, month, 1)
    return first + dt.timedelta(days=(6 - first.weekday()) % 7 + 7 * (n - 1))


def new_york_to_utc(text):
    wall = dt.datetime.strptime(text.strip(), "%Y-%m-%d %H:%M")
    start = dt.datetime.combine(nth_sunday(wall.year, 3, 2), dt.time(2, 0))
    end = dt.datetime.combine(nth_sunday(wall.year, 11, 1), dt.time(1, 0))
    offset_h = 4 if start <= wall < end else 5
    return (wall + dt.timedelta(hours=offset_h)).replace(tzinfo=dt.timezone.utc)


# ----------------------------------------------------------------------------- quadrature rules ---------------
def legendre_rule(n):
    """Nodes and weights on [-1, 1] by Newton iteration on P_n."""
    xs, ws = [], []
    for i in range(1, n + 1):
        x = math.cos(math.pi * (i - 0.25) / (n + 0.5))
        for _ in range(100):
            p0, p1 = 1.0, x
            for k in range(2, n + 1):
                p0, p1 = p1, ((2 * k - 1) * x * p1 - (k - 1) * p0) / k
            dp = n * (x * p1 - p0) / (x * x - 1.0)
            step = p1 / dp
            x -= step
            if abs(step) < 1e-15:
                break
        xs.append(x)
        ws.append(2.0 / ((1.0 - x * x) * dp * dp))
    return xs, ws


def jacobi_rule_unit(n, beta):
    """Nodes and weights for int_0^1 y^beta f(y) dy (beta > -1): Golub-Welsch on the Jacobi matrix for the weight
    (1 + x)^beta on [-1, 1], eigenvalues by implicit QL, weights from the first eigenvector components."""
    a, b = 0.0, beta
    diag, off = [], []
    for k in range(n):
        if k == 0:
            diag.append((b - a) / (a + b + 2.0))
        else:
            diag.append((b * b - a * a) / ((2 * k + a + b) * (2 * k + a + b + 2.0)))
            num = 4.0 * k * (k + a) * (k + b) * (k + a + b)
            den = (2 * k + a + b) ** 2 * (2 * k + a + b + 1.0) * (2 * k + a + b - 1.0)
            off.append(math.sqrt(num / den))
    mu0 = 2.0 ** (a + b + 1.0) * math.gamma(a + 1.0) * math.gamma(b + 1.0) / math.gamma(a + b + 2.0)
    d = list(diag)
    e = off + [0.0]
    z = [1.0] + [0.0] * (n - 1)
    for l in range(n):
        for _ in range(60):
            m = l
            while m < n - 1 and abs(e[m]) > 1e-16 * (abs(d[m]) + abs(d[m + 1])):
                m += 1
            if m == l:
                break
            g = (d[l + 1] - d[l]) / (2.0 * e[l])
            r = math.hypot(g, 1.0)
            g = d[m] - d[l] + e[l] / (g + (r if g >= 0 else -r))
            s = c = 1.0
            p = 0.0
            i = m - 1
            underflow = False
            while i >= l:
                f = s * e[i]
                bb = c * e[i]
                r = math.hypot(f, g)
                e[i + 1] = r
                if r == 0.0:
                    d[i + 1] -= p
                    e[m] = 0.0
                    underflow = True
                    break
                s, c = f / r, g / r
                g = d[i + 1] - p
                r = (d[i] - g) * s + 2.0 * c * bb
                p = s * r
                d[i + 1] = g + p
                g = c * r - bb
                z[i + 1], z[i] = s * z[i] + c * z[i + 1], c * z[i] - s * z[i + 1]
                i -= 1
            if not underflow:
                d[l] -= p
                e[l] = g
                e[m] = 0.0
    nodes = [(x + 1.0) / 2.0 for x in d]
    weights = [mu0 * zz * zz / 2.0 ** (beta + 1.0) for zz in z]
    return nodes, weights


GL_X, GL_W = legendre_rule(N_GAUSS)


# ----------------------------------------------------------------------------- source model ------------------
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
        self.half_h = d["half_life_days"] * 24.0
        self.lam = LN2 / self.half_h
        self.g = d["radial_dose_function_line_source"]
        self.g_r = [a for a, _ in self.g]
        F = d["anisotropy_function"]
        self.f_r = F["r_cm"]
        self.f_theta = F["theta_deg"] + [90.0]
        self.f = F["F"] + [[1.0] * len(self.f_r)]
        self.phi = d["anisotropy_factor_1d"]
        self.phi_r = [a for a, _ in self.phi]
        self.g_ref = self.G(1.0, 90.0)
        self.nodes_2d = sorted(set(self.g_r) | set(self.f_r))
        self.nodes_1d = sorted(set(self.g_r) | set(self.phi_r))

    def G(self, r, theta):
        th = math.radians(theta)
        rho, z = r * math.sin(th), r * math.cos(th)
        if rho == 0.0:
            return 1.0 / (r * r - self.L * self.L / 4.0)
        beta = math.atan((z + self.L / 2) / rho) - math.atan((z - self.L / 2) / rho)
        return beta / (self.L * rho)

    def radial(self, r):
        j, w = lerp_index(self.g_r, r)
        return math.exp((1 - w) * math.log(self.g[j][1]) + w * math.log(self.g[j + 1][1]))

    def anisotropy(self, r, theta):
        if theta > 90.0:
            theta = 180.0 - theta
        i, u = lerp_index(self.f_theta, theta)
        j, w = lerp_index(self.f_r, r)
        f = self.f
        return ((1 - u) * ((1 - w) * f[i][j] + w * f[i][j + 1]) + u * ((1 - w) * f[i + 1][j] + w * f[i + 1][j + 1]))

    def phi_an(self, r):
        j, w = lerp_index(self.phi_r, r)
        return (1 - w) * self.phi[j][1] + w * self.phi[j + 1][1]

    def rate_2d(self, r, theta):
        """Eq. (1): cGy/h per U."""
        return self.Lambda * self.G(r, theta) / self.g_ref * self.radial(r) * self.anisotropy(r, theta)

    def rate_1d(self, r):
        """Eq. (11); Eq. (C3) with X = L below the first tabulated anisotropy-factor distance."""
        r_min = self.phi_r[0]
        if r < r_min:
            return (self.Lambda * (r_min / r) ** 2 * self.G(r_min, 90.0) / self.g_ref * self.radial(r)
                    * self.phi[0][1])
        return self.Lambda * self.G(r, 90.0) / self.g_ref * self.radial(r) * self.phi_an(r)


# ----------------------------------------------------------------------------- edema and the time integral ---
class Edema:
    def __init__(self, v_pre, v_0, v_ct, t_ct_h, lam):
        self.v_pre, self.v_ct = v_pre, v_ct
        self.Y = v_0 - v_pre
        self.lam_e = -math.log((v_ct - v_pre) / self.Y) / t_ct_h
        self.alpha = lam / self.lam_e
        self.norm = 1.0 / (self.lam_e * self.Y ** self.alpha)
        self.gj_x, self.gj_w = jacobi_rule_unit(N_GAUSS, self.alpha - 1.0)

    def scale(self, y):
        return ((y + self.v_pre) / self.v_ct) ** (1.0 / 3.0)

    def y_at_scale(self, s):
        return s ** 3 * self.v_ct - self.v_pre

    def total(self, rate_at, r, nodes):
        """int_0^inf exp(-lam t) rate(s(t) r) dt as a weighted integral over y, split where s(y) r meets a node."""
        cuts = sorted({self.y_at_scale(rn / r) for rn in nodes if 0.0 < self.y_at_scale(rn / r) < self.Y}) + [self.Y]
        total = 0.0
        lo = 0.0
        for hi in cuts:
            if lo == 0.0:
                total += hi ** self.alpha * sum(w * rate_at(self.scale(hi * x) * r) for x, w in zip(self.gj_x, self.gj_w))
            else:
                segs = [lo]
                while segs[-1] * 3.0 < hi:
                    segs.append(segs[-1] * 3.0)
                segs.append(hi)
                for a, b in zip(segs, segs[1:]):
                    mid, half = (a + b) / 2.0, (b - a) / 2.0
                    total += half * sum(w * (mid + half * x) ** (self.alpha - 1.0) * rate_at(self.scale(mid + half * x) * r)
                                        for x, w in zip(GL_X, GL_W))
            lo = hi
        return total * self.norm


# ----------------------------------------------------------------------------- records -----------------------
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


def inside(poly, x, y):
    """Even-odd rule: count crossings of the ray to +x."""
    hit = False
    for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1]):
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            hit = not hit
    return hit


def voxels(slices):
    """Centres (cm) of the 2.5 mm voxels whose centres lie inside the structure's slice polygons."""
    out = []
    for sl in slices:
        poly = [tuple(p) for p in sl["points_mm"]]
        xs, ys = [p[0] for p in poly], [p[1] for p in poly]
        for i in range(math.floor(min(xs) / VOXEL_MM - 0.5), math.ceil(max(xs) / VOXEL_MM - 0.5) + 1):
            for j in range(math.floor(min(ys) / VOXEL_MM - 0.5), math.ceil(max(ys) / VOXEL_MM - 0.5) + 1):
                x, y = (i + 0.5) * VOXEL_MM, (j + 0.5) * VOXEL_MM
                if inside(poly, x, y):
                    out.append((x / 10.0, y / 10.0, sl["z_mm"] / 10.0))
    return out


def rank(desc, fraction):
    return desc[math.ceil(fraction * len(desc)) - 1]


def main():
    src = json.loads((DATA / "source_data.json").read_text())
    models = {m: Source(d) for m, d in src.items()}
    patients = {p["patient_id"]: p for p in json.loads((DATA / "patients.json").read_text())}
    contours = json.loads((DATA / "contours.json").read_text())
    batches = {b["batch_id"]: b for b in read_csv("batches.csv")}
    seeds = {}
    for s in read_csv("seeds.csv"):
        if s["review"] == "accepted":
            seeds.setdefault(s["patient_id"], []).append(s)

    rows = []
    for pid in sorted(patients):
        p = patients[pid]
        rx = float(p["prescription_gy"])
        t_implant = new_york_to_utc(p["implant"])
        t_ct_h = (new_york_to_utc(p["ct_scan"]) - t_implant).total_seconds() / 3600.0
        implanted = []
        for s in seeds[pid]:
            b = batches[s["batch_id"]]
            source = models[b["seed_model"]]
            hours = (t_implant - dt.datetime.fromisoformat(b["calibrated_at"])).total_seconds() / 3600.0
            sk = strength_per_seed(b) * math.exp(-LN2 * hours / source.half_h)
            m1 = [float(s[k]) / 10.0 for k in ("x1_mm", "y1_mm", "z1_mm")]
            if s["x2_mm"] == "":
                implanted.append((source, sk, m1, None))
            else:
                m2 = [float(s[k]) / 10.0 for k in ("x2_mm", "y2_mm", "z2_mm")]
                axis = [v - u for u, v in zip(m1, m2)]
                n = math.sqrt(sum(x * x for x in axis))
                implanted.append((source, sk, [(u + v) / 2 for u, v in zip(m1, m2)], [x / n for x in axis]))
        source = implanted[0][0]
        edema = Edema(float(p["volume_preimplant_cc"]), float(p["volume_postimplant_cc"]), float(p["volume_ct_cc"]),
                      t_ct_h, source.lam)

        doses = {}
        for name, slices in contours[pid]["structures"].items():
            lst = []
            for q in voxels(slices):
                cgy = 0.0
                for source, sk, centre, axis in implanted:
                    v = [q[k] - centre[k] for k in range(3)]
                    r = math.sqrt(sum(x * x for x in v))
                    if axis is None:
                        cgy += sk * edema.total(source.rate_1d, r, source.nodes_1d)
                    else:
                        cos_t = max(-1.0, min(1.0, sum(v[k] * axis[k] for k in range(3)) / r))
                        theta = math.degrees(math.acos(cos_t))
                        cgy += sk * edema.total(lambda x, th=theta: source.rate_2d(x, th), r, source.nodes_2d)
                lst.append(cgy / 100.0)
            doses[name] = sorted(lst, reverse=True)

        pro, ure, rec = doses["prostate"], doses["urethra"], doses["rectum"]
        d90, ud10, ud30 = rank(pro, 0.9), rank(ure, 0.1), rank(ure, 0.3)
        v100 = 100.0 * sum(d >= rx for d in pro) / len(pro)
        v150 = 100.0 * sum(d >= 1.5 * rx for d in pro) / len(pro)
        rv100 = VOXEL_CC * sum(d >= rx for d in rec)
        rd2cc = rec[math.ceil(2.0 / VOXEL_CC) - 1]
        rows.append([pid, f"{d90:.3f}", f"{v100:.2f}", f"{v150:.2f}", f"{ud10:.3f}", f"{ud30:.3f}", f"{rv100:.3f}",
                     f"{rd2cc:.3f}", "yes" if d90 >= rx else "no", "yes" if v100 >= 95.0 else "no",
                     "yes" if ud10 <= 1.5 * rx else "no", "yes" if rv100 <= 1.0 else "no"])

    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "implant_evaluation.csv", "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["patient_id", "d90_gy", "v100_pct", "v150_pct", "ud10_gy", "ud30_gy", "rv100_cc", "rd2cc_gy",
                    "d90_meets", "v100_meets", "ud10_meets", "rv100_meets"])
        w.writerows(rows)


if __name__ == "__main__":
    main()
