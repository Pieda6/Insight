"""Generator's own model for prostate-seed-dosimetry (third implementation).

Edema-corrected post-implant dosimetry under AAPM TG-43U1 (Rivard et al., Med Phys 2004;31:633-674).

Static dose rate per unit air-kerma strength: Eq. (1) with the line-source geometry function of Eq. (4) and g_L for
seeds with two markers; Eq. (11) with phi_an(r) for seeds with one marker, with Appendix C Eq. (C3) below the first
tabulated phi_an distance. ln g_L linear in r, F bilinear in r and theta with F(r, 90) = 1 and mirror symmetry,
nearest-neighbour values outside the tabulated distances (Eq. C1), phi_an linear in r and held at its ends.

Edema: V(t) = V_pre + (V_0 - V_pre) exp(-lambda_e t); s(t) = (V(t) / V_CT)^(1/3); every seed-to-tissue distance at
the CT scales by s(t). Total dose per unit strength at implant: K(r, theta) = integral_0^inf exp(-lambda t)
rate(s(t) r, theta) dt. With y = (V_0 - V_pre) exp(-lambda_e t):
K = (lambda_e Y^alpha)^-1 integral_0^Y y^(alpha-1) rate(s(y) r, theta) dy, alpha = lambda / lambda_e, Y = V_0 - V_pre.
This file integrates with the tanh-sinh (double exponential) rule on each interval between the y values where
s(y) r crosses a table node, taking the singular weight on the first interval from the exact distance to y = 0.
Kernels are tabulated on a geometric grid in r (with K r^2 interpolated bilinearly in ln r and theta) and read
per seed-voxel pair; pairs closer than R_DIRECT are integrated directly.

Voxels: 2.5 mm cubes with centres at (i + 1/2) 2.5 mm in x and y and at the slice positions in z; a voxel belongs
to a structure when its centre is inside the slice polygon by the even-odd rule (ray casting here).
"""
import sys
sys.dont_write_bytecode = True
import bisect
import csv
import datetime as dt
import json
import math
from pathlib import Path

LN2 = math.log(2.0)
CGY_PER_R = 0.876
VOXEL_MM = 2.5
VOXEL_CC = (VOXEL_MM / 10.0) ** 3
R_DIRECT = 0.6           # cm: pairs closer than this are integrated directly, not read from the kernel grid
_KERNELS = {}            # cache: kernels depend on the model, the edema parameters and the kernel-affecting flags only
R_HI = 14.0            # cm: upper end of the kernel grid
DTHETA = 0.5
UTC = dt.timezone.utc
KERNEL_FLAGS = ("volume_scaling", "anchor_pre", "from_ct", "nn_instead_c3", "g_linear", "f_hold_last_angle")


# ----------------------------------------------------------------------------- static TG-43U1 engine --------
class Model:
    def __init__(self, d, v=None):
        v = v or {}
        self.L = d["active_length_cm"]
        self.Lam = d["dose_rate_constant_cGy_per_h_per_U"]
        self.half_h = d["half_life_days"] * 24.0
        self.lam = LN2 / self.half_h
        g = d["radial_dose_function_line_source"]
        self.g_r = [a for a, _ in g]
        self.g_v = [b for _, b in g]
        self.g_ln = [math.log(b) for b in self.g_v]
        F = d["anisotropy_function"]
        self.F_r = list(F["r_cm"])
        self.F_th = list(F["theta_deg"])
        self.F = [list(row) for row in F["F"]]
        if not v.get("f_hold_last_angle"):
            self.F_th.append(90.0)
            self.F.append([1.0] * len(self.F_r))
        phi = d["anisotropy_factor_1d"]
        self.phi_r = [a for a, _ in phi]
        self.phi_v = [b for _, b in phi]
        self.g_linear = bool(v.get("g_linear"))
        self.nn_c3 = bool(v.get("nn_instead_c3"))
        self.G0 = self.G(1.0, 90.0)
        self.r_nodes = sorted(set(self.g_r) | set(self.F_r))
        self.r_nodes_1d = sorted(set(self.g_r) | set(self.phi_r))

    def G(self, r, theta_deg):
        th = math.radians(theta_deg)
        rho, z = r * math.sin(th), r * math.cos(th)
        if rho < 1e-12:
            return 1.0 / (r * r - self.L * self.L / 4.0)
        beta = math.atan2(z + self.L / 2.0, rho) - math.atan2(z - self.L / 2.0, rho)
        return beta / (self.L * rho)

    def g(self, r):
        xs = self.g_r
        if r <= xs[0]:
            return self.g_v[0]
        if r >= xs[-1]:
            return self.g_v[-1]
        j = bisect.bisect_right(xs, r) - 1
        w = (r - xs[j]) / (xs[j + 1] - xs[j])
        if self.g_linear:
            return self.g_v[j] + w * (self.g_v[j + 1] - self.g_v[j])
        return math.exp(self.g_ln[j] + w * (self.g_ln[j + 1] - self.g_ln[j]))

    def F_at(self, r, theta_deg):
        th = 180.0 - theta_deg if theta_deg > 90.0 else theta_deg
        ths = self.F_th
        if th >= ths[-1]:
            i, u = len(ths) - 2, 1.0
        else:
            i = bisect.bisect_right(ths, th) - 1
            u = (th - ths[i]) / (ths[i + 1] - ths[i])
        rs = self.F_r
        rc = min(max(r, rs[0]), rs[-1])
        j = min(bisect.bisect_right(rs, rc) - 1, len(rs) - 2)
        w = (rc - rs[j]) / (rs[j + 1] - rs[j])
        row0, row1 = self.F[i], self.F[i + 1]
        return ((1 - u) * ((1 - w) * row0[j] + w * row0[j + 1]) + u * ((1 - w) * row1[j] + w * row1[j + 1]))

    def phi(self, r):
        xs = self.phi_r
        rc = min(max(r, xs[0]), xs[-1])
        j = min(bisect.bisect_right(xs, rc) - 1, len(xs) - 2)
        w = (rc - xs[j]) / (xs[j + 1] - xs[j])
        return self.phi_v[j] + w * (self.phi_v[j + 1] - self.phi_v[j])

    def rate2d(self, r, theta_deg):
        """cGy/h per U, Eq. (1)."""
        return self.Lam * self.G(r, theta_deg) / self.G0 * self.g(r) * self.F_at(r, theta_deg)

    def rate1d(self, r):
        """cGy/h per U, Eq. (11); Eq. (C3) with X = L below the first tabulated phi_an distance."""
        rmin = self.phi_r[0]
        if r < rmin and not self.nn_c3:
            return self.Lam * (rmin / r) ** 2 * self.G(rmin, 90.0) / self.G0 * self.g(r) * self.phi_v[0]
        return self.Lam * self.G(r, 90.0) / self.G0 * self.g(r) * self.phi(r)


# ----------------------------------------------------------------------------- edema and time integral --------
class Edema:
    def __init__(self, V_pre, V_0, V_ct, t_ct_h, lam, v=None):
        v = v or {}
        self.V_pre, self.V_0, self.V_ct = V_pre, V_0, V_ct
        self.Y = V_0 - V_pre
        self.lam_e = -math.log((V_ct - V_pre) / self.Y) / t_ct_h
        self.lam = lam
        self.alpha = lam / self.lam_e
        self.y_ct = V_ct - V_pre
        self.anchor = V_pre if v.get("anchor_pre") else V_ct
        self.cube = not v.get("volume_scaling")
        self.y_hi = self.y_ct if v.get("from_ct") else self.Y
        assert all(math.isfinite(x) for x in (self.lam_e, self.alpha, self.Y)) and self.lam_e > 0

    def s(self, y):
        q = (y + self.V_pre) / self.anchor
        return q ** (1.0 / 3.0) if self.cube else q

    def y_of_s(self, s):
        return (s ** 3 if self.cube else s) * self.anchor - self.V_pre


def _ts_nodes(h=0.25, N=20):
    """tanh-sinh abscissae as (distance to the lower end in units of the half length, weight), for sh < 0 and
    mirrored; returned as a list of (dist_lo, dist_hi, w) with dist = 1 -/+ x computed from exponentials."""
    out = []
    for k in range(-N, N + 1):
        u = k * h
        sh = math.pi / 2 * math.sinh(u)
        ex = math.exp(-2 * abs(sh))
        dist = 2 * ex / (1 + ex)                          # 1 - |x|
        w = math.pi / 2 * math.cosh(u) * 4 * ex / (1 + ex) ** 2 * h
        if sh < 0:
            out.append((dist, 2 - dist, w))
        else:
            out.append((2 - dist, dist, w))
    return out


TS = _ts_nodes()


def kernel_direct(model, ed, r, theta_deg, one_d, static=False):
    """K(r, theta): total dose (cGy) per U of air-kerma strength at the implant, by tanh-sinh on each kink interval."""
    rate = (lambda x: model.rate1d(x)) if one_d else (lambda x: model.rate2d(x, theta_deg))
    if static:
        return rate(r) / model.lam
    nodes = model.r_nodes_1d if one_d else model.r_nodes
    ks = [0.0]
    for rn in nodes:
        y = ed.y_of_s(rn / r)
        if 0.0 < y < ed.y_hi:
            ks.append(y)
    ks = sorted(set(ks)) + [ed.y_hi]
    beta = ed.alpha - 1.0
    total = 0.0
    for a, b in zip(ks, ks[1:]):
        half = (b - a) / 2.0
        acc = 0.0
        for dlo, dhi, w in TS:
            d_lo = half * dlo
            y = a + d_lo if dlo <= 1.0 else b - half * dhi
            if d_lo <= 0.0 or y <= a or y >= b:
                continue
            wt = d_lo ** beta if a == 0.0 else y ** beta
            acc += w * wt * rate(ed.s(y) * r)
        total += half * acc
    return total / (ed.lam_e * ed.Y ** ed.alpha)


class Kernel:
    """Tabulated Q = K r^2 G_L(r, 90) / G_L(r, theta) on a uniform r grid (fine below 1 cm) and a theta grid.
    Q is interpolated linearly in theta (F is piecewise linear in theta, and the geometry function's own theta
    dependence is divided out) and log-linearly in r (ln g_L is piecewise linear in r and G_L r^2 is nearly constant)."""

    def __init__(self, model, ed, one_d, static=False):
        self.one_d = one_d
        self.model = model
        self.r_a, self.h_a = R_DIRECT * 0.98, 0.004           # fine segment [r_a, 1.0)
        self.n_a = int(round((1.0 - self.r_a) / self.h_a))
        self.h_b = 0.0125                                      # coarse segment [1.0, R_HI]
        self.n_b = int(math.ceil((R_HI - 1.0) / self.h_b)) + 1
        rs = [self.r_a + i * self.h_a for i in range(self.n_a)] + [1.0 + i * self.h_b for i in range(self.n_b)]
        self.rs = rs
        self.ths = [0.0] if one_d else [j * DTHETA for j in range(int(round(90.0 / DTHETA)) + 1)]
        self.q = [[kernel_direct(model, ed, r, th, one_d, static) * r * r * (1.0 if one_d else model.G(r, 90.0) / model.G(r, th))
                   for r in rs] for th in self.ths]
        self.nth = len(self.ths)

    def _index(self, r):
        if r < 1.0:
            x = (r - self.r_a) / self.h_a
            i = int(x)
            if i < 0:
                raise ValueError(f"r {r} below the kernel grid")
            return i, x - i
        x = (r - 1.0) / self.h_b
        i = int(x)
        if i >= self.n_b - 1:
            raise ValueError(f"r {r} above the kernel grid")
        return self.n_a + i, x - i

    def value(self, r, theta_deg):
        i, w = self._index(r)
        if self.one_d:
            row = self.q[0]
            return row[i] ** (1 - w) * row[i + 1] ** w / (r * r)
        th = 180.0 - theta_deg if theta_deg > 90.0 else theta_deg
        y = th / DTHETA
        j = min(int(y), self.nth - 2)
        u = y - j
        r0, r1 = self.q[j], self.q[j + 1]
        q0 = (1 - u) * r0[i] + u * r1[i]
        q1 = (1 - u) * r0[i + 1] + u * r1[i + 1]
        return q0 ** (1 - w) * q1 ** w * self.model.G(r, th) / (self.model.G(r, 90.0) * r * r)


# ----------------------------------------------------------------------------- records ------------------------
def read_csv(path):
    with open(path, newline="") as fh:
        return list(csv.DictReader(fh))


def load(data_dir):
    data_dir = Path(data_dir)
    d = {"src": json.loads((data_dir / "source_data.json").read_text()),
         "patients": {p["patient_id"]: p for p in json.loads((data_dir / "patients.json").read_text())},
         "batches": {b["batch_id"]: b for b in read_csv(data_dir / "batches.csv")},
         "contours": json.loads((data_dir / "contours.json").read_text()), "seeds": {}}
    for s in read_csv(data_dir / "seeds.csv"):
        d["seeds"].setdefault(s["patient_id"], []).append(s)
    return d


def ny_to_utc(text, naive=False):
    wall = dt.datetime.strptime(text, "%Y-%m-%d %H:%M")
    if naive:
        return wall.replace(tzinfo=UTC) + dt.timedelta(hours=5)
    y = wall.year
    mar = dt.datetime(y, 3, 8 + (6 - dt.date(y, 3, 8).weekday()) % 7, 2)
    nov = dt.datetime(y, 11, 1 + (6 - dt.date(y, 11, 1).weekday()) % 7, 2)
    off = 4 if mar <= wall < nov else 5
    return wall.replace(tzinfo=UTC) + dt.timedelta(hours=off)


def seed_strength(batch, src, implant_utc, v):
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
            s *= 1.270 if src[model]["radionuclide"] == "I-125" else 1.293
        else:
            s *= float(batch["exposure_rate_constant"]) * CGY_PER_R
    cal = dt.datetime.fromisoformat(batch["calibrated_at"])
    if v.get("ignore_offset"):
        cal = cal.replace(tzinfo=UTC)
    hours = (implant_utc - cal).total_seconds() / 3600.0
    if v.get("no_decay"):
        hours = 0.0
    if v.get("clamp_negative_decay"):
        hours = max(hours, 0.0)
    return s * math.exp(-LN2 * hours / (src[model]["half_life_days"] * 24.0))


# ----------------------------------------------------------------------------- voxels -------------------------
def inside(poly, x, y):
    """Even-odd rule by ray casting towards +x."""
    n = len(poly)
    c = False
    x0, y0 = poly[-1]
    for x1, y1 in poly:
        if (y1 > y) != (y0 > y):
            xi = x0 + (y - y0) * (x1 - x0) / (y1 - y0)
            if x < xi:
                c = not c
        x0, y0 = x1, y1
    return c


def voxel_centres(struct_slices):
    """Centres (cm) of the voxels of one structure given its slices [{'z_mm', 'points_mm'}]."""
    out = []
    for sl in struct_slices:
        poly = sl["points_mm"]
        xs = [p[0] for p in poly]
        ys = [p[1] for p in poly]
        i0 = math.floor(min(xs) / VOXEL_MM - 0.5)
        i1 = math.ceil(max(xs) / VOXEL_MM - 0.5)
        j0 = math.floor(min(ys) / VOXEL_MM - 0.5)
        j1 = math.ceil(max(ys) / VOXEL_MM - 0.5)
        z = sl["z_mm"]
        for i in range(i0, i1 + 1):
            x = (i + 0.5) * VOXEL_MM
            for j in range(j0, j1 + 1):
                y = (j + 0.5) * VOXEL_MM
                if inside(poly, x, y):
                    out.append((x / 10.0, y / 10.0, z / 10.0))
    return out


def structures(contours_of_patient, v=None):
    v = v or {}
    vox = {name: voxel_centres(sl) for name, sl in contours_of_patient["structures"].items()}
    if v.get("urethra_subtracted"):
        u = set(vox["urethra"])
        vox["prostate"] = [c for c in vox["prostate"] if c not in u]
    return vox


# ----------------------------------------------------------------------------- doses and metrics -------------
def implanted_seeds(data, pid, v):
    """[(centre cm, unit axis or None, S_K at implant in U, model name)] for the accepted seeds."""
    src = data["src"]
    implant_utc = ny_to_utc(data["patients"][pid]["implant"], naive=v.get("naive_time"))
    out = []
    for s in data["seeds"][pid]:
        if s["review"] != "accepted" and not v.get("keep_duplicates"):
            continue
        b = data["batches"][s["batch_id"]]
        m1 = [float(s[k]) / 10.0 for k in ("x1_mm", "y1_mm", "z1_mm")]
        if s["x2_mm"] == "":
            centre, axis = m1, None
            if v.get("two_d_single"):
                axis = [0.0, 0.0, 1.0]
        else:
            m2 = [float(s[k]) / 10.0 for k in ("x2_mm", "y2_mm", "z2_mm")]
            centre = [(a + c) / 2.0 for a, c in zip(m1, m2)]
            ax = [c - a for a, c in zip(m1, m2)]
            n = math.sqrt(sum(a * a for a in ax))
            axis = [a / n for a in ax]
        out.append((centre, axis, seed_strength(b, src, implant_utc, v), b["seed_model"]))
    return out


def edema_of(data, pid, model, v):
    p = data["patients"][pid]
    t_ct_h = (ny_to_utc(p["ct_scan"], naive=v.get("naive_time")) - ny_to_utc(p["implant"], naive=v.get("naive_time"))
              ).total_seconds() / 3600.0
    return Edema(float(p["volume_preimplant_cc"]), float(p["volume_postimplant_cc"]), float(p["volume_ct_cc"]),
                 t_ct_h, model.lam, v)


def patient_doses(data, pid, v=None, vox=None):
    """{structure: [dose Gy per voxel]} in the order of structures()."""
    v = v or {}
    seeds = implanted_seeds(data, pid, v)
    model_name = seeds[0][3]
    model = Model(data["src"][model_name], v)
    ed = edema_of(data, pid, model, v)
    static = bool(v.get("static"))
    kern = {}
    for one_d in {s[1] is None for s in seeds}:
        key = (model_name, ed.V_pre, ed.V_0, ed.V_ct, round(ed.lam_e, 15), one_d, static,
               tuple(sorted(k for k in v if k in KERNEL_FLAGS and v[k])))
        if key not in _KERNELS:
            _KERNELS[key] = Kernel(model, ed, one_d, static)
        kern[one_d] = _KERNELS[key]
    tau = model.half_h * 1.44 if v.get("tau_144") else 1.0 / model.lam
    vox = vox or structures(data["contours"][pid], v)
    out = {}
    for name, centres in vox.items():
        doses = []
        for (x, y, z) in centres:
            total = 0.0
            for c, axis, sk, _ in seeds:
                dx, dy, dz = x - c[0], y - c[1], z - c[2]
                r = math.sqrt(dx * dx + dy * dy + dz * dz)
                if axis is None:
                    th = 90.0
                else:
                    ct = abs(dx * axis[0] + dy * axis[1] + dz * axis[2]) / r
                    th = math.degrees(math.acos(min(1.0, ct)))
                one_d = axis is None
                if r < R_DIRECT:
                    k = kernel_direct(model, ed, r, th, one_d, static)
                else:
                    k = kern[one_d].value(r, th)
                if v.get("tau_144"):
                    k = k * model.lam * tau
                total += sk * k
            doses.append(total / 100.0)
        out[name] = doses
    return out


def rank_dose(doses_desc, fraction, floor_rank=False):
    n = len(doses_desc)
    k = math.floor(fraction * n) if floor_rank else math.ceil(fraction * n)
    return doses_desc[max(k, 1) - 1]


def metrics(doses, rx, v=None):
    v = v or {}
    fl = bool(v.get("floor_rank"))
    pro = sorted(doses["prostate"], reverse=True)
    ure = sorted(doses["urethra"], reverse=True)
    rec = sorted(doses["rectum"], reverse=True)
    m = {"d90_gy": rank_dose(pro, 0.9, fl),
         "v100_pct": 100.0 * sum(d >= rx for d in pro) / len(pro),
         "v150_pct": 100.0 * sum(d >= 1.5 * rx for d in pro) / len(pro),
         "ud10_gy": rank_dose(ure, 0.1, fl), "ud30_gy": rank_dose(ure, 0.3, fl),
         "rv100_cc": VOXEL_CC * sum(d >= rx for d in rec)}
    k2 = math.ceil(2.0 / VOXEL_CC)
    k2 = math.floor(2.0 / VOXEL_CC) if fl else k2
    m["rd2cc_gy"] = rec[k2 - 1]
    if v.get("strict_criteria"):            # misreading: strict inequalities (differs only exactly on a line)
        m["d90_meets"] = "yes" if m["d90_gy"] > rx else "no"
        m["v100_meets"] = "yes" if m["v100_pct"] > 95.0 else "no"
        m["ud10_meets"] = "yes" if m["ud10_gy"] < 1.5 * rx else "no"
        m["rv100_meets"] = "yes" if m["rv100_cc"] < 1.0 else "no"
    else:
        m["d90_meets"] = "yes" if m["d90_gy"] >= rx else "no"
        m["v100_meets"] = "yes" if m["v100_pct"] >= 95.0 else "no"
        m["ud10_meets"] = "yes" if m["ud10_gy"] <= 1.5 * rx else "no"
        m["rv100_meets"] = "yes" if m["rv100_cc"] <= 1.0 else "no"
    for k, x in m.items():
        if not isinstance(x, str):
            assert math.isfinite(x), (k, x)
    return m


def evaluate(data_dir, v=None):
    data = load(data_dir)
    out = {}
    for pid in sorted(data["patients"]):
        doses = patient_doses(data, pid, v)
        out[pid] = metrics(doses, float(data["patients"][pid]["prescription_gy"]), v)
    return out


if __name__ == "__main__":
    import time
    t0 = time.time()
    res = evaluate(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent / "../environment/data")
    for pid, m in res.items():
        print(pid, {k: (round(x, 4) if not isinstance(x, str) else x) for k, x in m.items()})
    print(f"{time.time() - t0:.1f} s")
