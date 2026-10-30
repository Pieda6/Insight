"""Independent engine for the verifier of prostate-seed-dosimetry.

Static TG-43U1 dose rate per unit air-kerma strength (Rivard et al., Med Phys 2004;31:633-674): the 2D formalism of
Eq. (1) with the line-source geometry function (Eq. 4, the subtended angle from the law of cosines) and g_L for
two-marker seeds; the 1D formalism of Eq. (11) with phi_an(r) for one-marker seeds and Appendix C Eq. (C3) below the
first tabulated phi_an distance; log-linear g_L, bilinear F with F(r, 90) = 1 and mirror symmetry; nearest-neighbour
values outside the tables (Eq. C1); apparent activity times the vendor's exposure-rate constant (Appendix E).

Edema: V(t) = V_pre + (V_0 - V_pre) exp(-lambda_e t), lambda_e from the CT volume; distances scale by
s(t) = (V(t) / V_CT)^(1/3). The dose per unit strength at implant is integral_0^inf exp(-lambda t) rate(s(t) r) dt.
It is split at the times where s(t) r crosses a table node; pieces of finite length are integrated by Gauss-Legendre
in t on sub-intervals of at most two edema half-lives, and the tail from the last crossing to infinity by
Gauss-Jacobi in w = exp(-lambda_e t), whose weight w^(alpha - 1), alpha = lambda / lambda_e, carries the decay.
Gauss-Jacobi abscissae come from Newton iteration on the Jacobi polynomial recurrence.

Per patient the dose per unit strength is tabulated as Q(r, theta) = K r^2 G_L(r, 90) / G_L(r, theta) on a uniform
r grid (0.005 cm below 1 cm, 0.0125 cm above) and a 1-degree theta grid, read linearly in theta and log-linearly in
r; pairs closer than 0.6 cm are integrated directly. Voxels: 2.5 mm cubes, centres inside the slice polygon by the
winding number. Indices by ceiling rank on the descending dose list.
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
VOX = 0.25                                   # cm
VOX_CC = VOX ** 3
R_DIRECT = 0.6
R_TOP = 14.0
N_RULE = 8
COLUMNS = ("d90_gy", "v100_pct", "v150_pct", "ud10_gy", "ud30_gy", "rv100_cc", "rd2cc_gy",
           "d90_meets", "v100_meets", "ud10_meets", "rv100_meets")


# ----------------------------------------------------------------------------- records ------------------------
def load(data=None):
    data = Path(data) if data else DATA
    src = json.loads((data / "source_data.json").read_text())
    patients = json.loads((data / "patients.json").read_text())
    contours = json.loads((data / "contours.json").read_text())

    def rows(name):
        with open(data / name, newline="") as fh:
            return list(csv.DictReader(fh))
    batches, seeds = rows("batches.csv"), rows("seeds.csv")
    for p in patients:
        for k in ("volume_preimplant_cc", "volume_postimplant_cc", "volume_ct_cc", "prescription_gy"):
            assert math.isfinite(float(p[k])), (p["patient_id"], k)
    return src, patients, batches, seeds, contours


def _sunday(y, m, nth):
    d = dt.date(y, m, 1)
    return d + dt.timedelta(days=(6 - d.weekday()) % 7 + 7 * (nth - 1))


def new_york(text):
    """New York wall time to an aware UTC datetime (US rules since 2007)."""
    t = dt.datetime.strptime(text, "%Y-%m-%d %H:%M")
    edt = (dt.datetime.combine(_sunday(t.year, 3, 2), dt.time(2)) <= t
           < dt.datetime.combine(_sunday(t.year, 11, 1), dt.time(1)))
    return (t + dt.timedelta(hours=4 if edt else 5)).replace(tzinfo=dt.timezone.utc)


def per_seed_strength(batch):
    value = float(batch["strength"])
    unit = batch["strength_unit"]
    if unit == "U_per_seed":
        return value
    if unit == "U_total":
        return value / int(batch["seeds_in_batch"])
    if unit == "mCi_apparent":
        return value * float(batch["exposure_rate_constant"]) * CGY_PER_R
    raise ValueError(unit)


# ----------------------------------------------------------------------------- static dose rate ---------------
def _segment(xs, x):
    return min(max(bisect.bisect_right(xs, x) - 1, 0), len(xs) - 2)


class SourceData:
    def __init__(self, d):
        self.L = d["active_length_cm"]
        self.Lambda = d["dose_rate_constant_cGy_per_h_per_U"]
        self.lam = LN2 / (d["half_life_days"] * 24.0)
        self.half_h = d["half_life_days"] * 24.0
        self.g_tab = d["radial_dose_function_line_source"]
        self.g_xs = [a for a, _ in self.g_tab]
        F = d["anisotropy_function"]
        self.F_rs = list(F["r_cm"])
        self.F_th = list(F["theta_deg"]) + [90.0]
        self.F_grid = [list(row) for row in F["F"]] + [[1.0] * len(self.F_rs)]
        self.phi_tab = d["anisotropy_factor_1d"]
        self.phi_xs = [a for a, _ in self.phi_tab]
        self.g0 = geometry(self.L, 1.0, 0.0)
        self.nodes2 = sorted(set(self.g_xs) | set(self.F_rs))
        self.nodes1 = sorted(set(self.g_xs) | set(self.phi_xs))


def geometry(L, rho, z):
    """Line-source G_L from cylindrical coordinates; the subtended angle beta from the law of cosines, and the
    on-axis form (r^2 - L^2/4)^-1 of Eq. (4) when rho is zero."""
    if rho < 1e-12:
        return 1.0 / (z * z - L * L / 4.0)
    a = math.sqrt(rho * rho + (z - L / 2) ** 2)
    b = math.sqrt(rho * rho + (z + L / 2) ** 2)
    cos_beta = (a * a + b * b - L * L) / (2 * a * b)
    beta = math.acos(max(-1.0, min(1.0, cos_beta)))
    return beta / (L * rho)


def radial(table, xs, r):
    if r <= xs[0]:
        return table[0][1]
    if r >= xs[-1]:
        return table[-1][1]
    j = _segment(xs, r)
    w = (r - xs[j]) / (xs[j + 1] - xs[j])
    return table[j][1] ** (1 - w) * table[j + 1][1] ** w


def anisotropy(sd, r, theta):
    t = 180.0 - theta if theta > 90.0 else theta
    th = sd.F_th
    i = _segment(th, t)
    u = (t - th[i]) / (th[i + 1] - th[i])
    rs = sd.F_rs
    rc = min(max(r, rs[0]), rs[-1])
    j = _segment(rs, rc)
    w = (rc - rs[j]) / (rs[j + 1] - rs[j])
    g = sd.F_grid
    lo = g[i][j] * (1 - w) + g[i][j + 1] * w
    hi = g[i + 1][j] * (1 - w) + g[i + 1][j + 1] * w
    return lo * (1 - u) + hi * u


def phi_an(sd, r):
    xs = sd.phi_xs
    rc = min(max(r, xs[0]), xs[-1])
    j = _segment(xs, rc)
    w = (rc - xs[j]) / (xs[j + 1] - xs[j])
    return sd.phi_tab[j][1] * (1 - w) + sd.phi_tab[j + 1][1] * w


def rate_per_unit(d, r, theta):
    """Eq. (1): dose rate (cGy/h) per U at (r cm, theta degrees). d is the model's consensus dataset."""
    sd = d if isinstance(d, SourceData) else SourceData(d)
    rho, z = r * math.sin(math.radians(theta)), r * math.cos(math.radians(theta))
    return sd.Lambda * geometry(sd.L, rho, z) / sd.g0 * radial(sd.g_tab, sd.g_xs, r) * anisotropy(sd, r, theta)


def rate_1d(d, r):
    """Eq. (11) with phi_an(r); Eq. (C3) with X = L below the first tabulated phi_an distance."""
    sd = d if isinstance(d, SourceData) else SourceData(d)
    r_min = sd.phi_xs[0]
    if r < r_min:
        return (sd.Lambda * (r_min / r) ** 2 * geometry(sd.L, r_min, 0.0) / sd.g0 * radial(sd.g_tab, sd.g_xs, r)
                * sd.phi_tab[0][1])
    return sd.Lambda * geometry(sd.L, r, 0.0) / sd.g0 * radial(sd.g_tab, sd.g_xs, r) * phi_an(sd, r)


# ----------------------------------------------------------------------------- quadrature ---------------------
def legendre(n):
    """Gauss-Legendre abscissae and weights on [-1, 1] (Newton on the three-term recurrence)."""
    xs, ws = [], []
    for i in range(n):
        x = math.cos(math.pi * (i + 0.75) / (n + 0.5))
        for _ in range(50):
            p1, p2 = x, 1.0
            for k in range(2, n + 1):
                p1, p2 = ((2 * k - 1) * x * p1 - (k - 1) * p2) / k, p1
            dp = n * (x * p1 - p2) / (x * x - 1)
            dx = p1 / dp
            x -= dx
            if abs(dx) < 1e-15:
                break
        xs.append(x)
        ws.append(2 / ((1 - x * x) * dp * dp))
    return xs, ws


def jacobi_unit(n, beta):
    """Gauss-Jacobi abscissae and weights for integral_0^1 x^beta f(x) dx, beta > -1, by Newton iteration on
    P_n^(0, beta) (Numerical Recipes gaujac) mapped from [-1, 1]."""
    alf = 0.0
    xs, ws = [], []
    x = 0.0
    for i in range(n):
        if i == 0:
            an, bn = alf / n, beta / n
            r1 = (1 + alf) * (2.78 / (4 + n * n) + 0.768 * an / n)
            r2 = 1 + 1.48 * an + 0.96 * bn + 0.452 * an * an + 0.83 * an * bn
            x = 1 - r1 / r2
        elif i == 1:
            r1 = (4.1 + alf) / ((1 + alf) * (1 + 0.156 * alf))
            r2 = 1 + 0.06 * (n - 8) * (1 + 0.12 * alf) / n
            r3 = 1 + 0.012 * beta * (1 + 0.25 * abs(alf)) / n
            x -= (1 - x) * r1 * r2 * r3
        elif i == 2:
            r1 = (1.67 + 0.28 * alf) / (1 + 0.37 * alf)
            r2 = 1 + 0.22 * (n - 8) / n
            r3 = 1 + 8 * beta / ((6.28 + beta) * n * n)
            x -= (xs[0] - x) * r1 * r2 * r3
        elif i == n - 2:
            r1 = (1 + 0.235 * beta) / (0.766 + 0.119 * beta)
            r2 = 1 / (1 + 0.639 * (n - 4) / (1 + 0.71 * (n - 4)))
            r3 = 1 / (1 + 20 * alf / ((7.5 + alf) * n * n))
            x += (x - xs[-2]) * r1 * r2 * r3
        elif i == n - 1:
            r1 = (1 + 0.37 * beta) / (1.67 + 0.28 * beta)
            r2 = 1 / (1 + 0.22 * (n - 8) / n)
            r3 = 1 / (1 + 8 * alf / ((6.28 + alf) * n * n))
            x += (x - xs[-2]) * r1 * r2 * r3
        else:
            x = 3 * xs[-1] - 3 * xs[-2] + xs[-3]
        alfbet = alf + beta
        for _ in range(100):
            temp = 2 + alfbet
            p1 = (alf - beta + temp * x) / 2
            p2 = 1.0
            for j in range(2, n + 1):
                p3 = p2
                p2 = p1
                temp = 2 * j + alfbet
                a = 2 * j * (j + alfbet) * (temp - 2)
                b = (temp - 1) * (alf * alf - beta * beta + temp * (temp - 2) * x)
                c = 2 * (j - 1 + alf) * (j - 1 + beta) * temp
                p1 = (b * p2 - c * p3) / a
            pp = (n * (alf - beta - temp * x) * p1 + 2 * (n + alf) * (n + beta) * p2) / (temp * (1 - x * x))
            dx = p1 / pp
            x -= dx
            if abs(dx) < 1e-14:
                break
        xs.append(x)
        ws.append(math.exp(math.lgamma(alf + n) + math.lgamma(beta + n) - math.lgamma(n + 1) - math.lgamma(n + alfbet + 1))
                  * temp * 2 ** alfbet / (pp * p2))
    # map (1 + x)^beta on [-1, 1] to y^beta on [0, 1]: y = (1 + x) / 2, dy = dx / 2
    return [(1 + x) / 2 for x in xs], [w / 2 ** (beta + 1) for w in ws]


GL_X, GL_W = legendre(N_RULE)


class Edema:
    def __init__(self, v_pre, v_0, v_ct, t_ct_h, lam):
        self.v_pre, self.v_ct, self.Y = v_pre, v_ct, v_0 - v_pre
        self.lam_e = -math.log((v_ct - v_pre) / self.Y) / t_ct_h
        self.lam = lam
        self.alpha = lam / self.lam_e
        self.T_e = LN2 / self.lam_e
        self.gj_x, self.gj_w = jacobi_unit(N_RULE, self.alpha - 1.0)
        # exactness check of the rule on the first monomials (static check of the quadrature itself)
        for k in range(3):
            got = sum(w * x ** k for x, w in zip(self.gj_x, self.gj_w))
            assert abs(got - 1.0 / (self.alpha + k)) < 1e-9 * (1.0 / (self.alpha + k)), "Gauss-Jacobi rule"
        assert math.isfinite(self.alpha) and self.lam_e > 0

    def s_of_t(self, t):
        return ((self.v_pre + self.Y * math.exp(-self.lam_e * t)) / self.v_ct) ** (1.0 / 3.0)

    def s_of_w(self, w):
        return ((self.v_pre + self.Y * w) / self.v_ct) ** (1.0 / 3.0)

    def t_of_scale(self, s):
        """Time at which the scale factor equals s, or None if never (s outside the range of s(t))."""
        w = (s ** 3 * self.v_ct - self.v_pre) / self.Y
        if w <= 0.0 or w >= 1.0:
            return None
        return -math.log(w) / self.lam_e

    def integral(self, rate_of_r, r, nodes):
        """integral_0^inf exp(-lam t) rate(s(t) r) dt (cGy per U), split at the table-node crossings."""
        cuts = sorted(t for t in (self.t_of_scale(x / r) for x in nodes) if t is not None)
        total = 0.0
        lo = 0.0
        for hi in cuts:
            m = max(1, math.ceil((hi - lo) / (2.0 * self.T_e)))
            for k in range(m):
                a = lo + (hi - lo) * k / m
                b = lo + (hi - lo) * (k + 1) / m
                mid, half = (a + b) / 2, (b - a) / 2
                total += half * sum(w * math.exp(-self.lam * (mid + half * x)) * rate_of_r(self.s_of_t(mid + half * x) * r)
                                    for x, w in zip(GL_X, GL_W))
            lo = hi
        w_last = math.exp(-self.lam_e * lo)
        tail = sum(w * rate_of_r(self.s_of_w(w_last * x) * r) for x, w in zip(self.gj_x, self.gj_w))
        total += tail * w_last ** self.alpha / self.lam_e
        assert math.isfinite(total)
        return total


class Kernel:
    """Q(r, theta) = K r^2 G_L(r, 90) / G_L(r, theta) on a uniform r grid and a 1-degree theta grid."""

    def __init__(self, sd, edema, one_d):
        self.sd, self.one_d = sd, one_d
        self.r0, self.h_fine, self.h_coarse = R_DIRECT * 0.98, 0.005, 0.0125
        self.n_fine = int(round((1.0 - self.r0) / self.h_fine))
        rs = [self.r0 + i * self.h_fine for i in range(self.n_fine)]
        rs += [1.0 + i * self.h_coarse for i in range(int(math.ceil((R_TOP - 1.0) / self.h_coarse)) + 1)]
        self.rs = rs
        self.ths = [0.0] if one_d else [float(j) for j in range(91)]
        self.q = []
        for th in self.ths:
            if one_d:
                row = [edema.integral(lambda x: rate_1d(sd, x), r, sd.nodes1) * r * r for r in rs]
            else:
                rho_c, z_c = math.sin(math.radians(th)), math.cos(math.radians(th))
                row = [edema.integral(lambda x, t=th: rate_per_unit(sd, x, t), r, sd.nodes2) * r * r
                       * geometry(sd.L, r, 0.0) / geometry(sd.L, r * rho_c, r * z_c) for r in rs]
            self.q.append([math.log(v) for v in row])

    def read(self, r, theta):
        if r < 1.0:
            x = (r - self.r0) / self.h_fine
        else:
            x = self.n_fine + (r - 1.0) / self.h_coarse
        i = int(x)
        w = x - i
        assert 0 <= i < len(self.rs) - 1, r
        if self.one_d:
            q = self.q[0]
            return math.exp(q[i] * (1 - w) + q[i + 1] * w) / (r * r)
        t = 180.0 - theta if theta > 90.0 else theta
        j = min(int(t), 89)
        u = t - j
        qa = math.exp(self.q[j][i]) * (1 - u) + math.exp(self.q[j + 1][i]) * u
        qb = math.exp(self.q[j][i + 1]) * (1 - u) + math.exp(self.q[j + 1][i + 1]) * u
        sd = self.sd
        rho, z = r * math.sin(math.radians(t)), r * math.cos(math.radians(t))
        return qa ** (1 - w) * qb ** w * geometry(sd.L, rho, z) / (geometry(sd.L, r, 0.0) * r * r)


# ----------------------------------------------------------------------------- voxels and indices -------------
def winding_inside(poly, x, y):
    """Nonzero winding number (equal to even-odd for the simple polygons here)."""
    wn = 0
    for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1]):
        if y0 <= y:
            if y1 > y and (x1 - x0) * (y - y0) - (x - x0) * (y1 - y0) > 0:
                wn += 1
        elif y1 <= y and (x1 - x0) * (y - y0) - (x - x0) * (y1 - y0) < 0:
            wn -= 1
    return wn != 0


def voxel_centres(slices):
    out = []
    for sl in slices:
        poly = [(p[0] / 10.0, p[1] / 10.0) for p in sl["points_mm"]]
        z = sl["z_mm"] / 10.0
        xs, ys = [p[0] for p in poly], [p[1] for p in poly]
        for i in range(math.floor(min(xs) / VOX - 0.5), math.ceil(max(xs) / VOX - 0.5) + 1):
            x = (i + 0.5) * VOX
            for j in range(math.floor(min(ys) / VOX - 0.5), math.ceil(max(ys) / VOX - 0.5) + 1):
                y = (j + 0.5) * VOX
                if winding_inside(poly, x, y):
                    out.append((x, y, z))
    return out


def at_rank(desc, fraction):
    k = math.ceil(fraction * len(desc))
    return desc[k - 1]


def indices(doses, rx):
    pro = sorted(doses["prostate"], reverse=True)
    ure = sorted(doses["urethra"], reverse=True)
    rec = sorted(doses["rectum"], reverse=True)
    m = {"d90_gy": at_rank(pro, 0.9),
         "v100_pct": 100.0 * sum(1 for d in pro if d >= rx) / len(pro),
         "v150_pct": 100.0 * sum(1 for d in pro if d >= 1.5 * rx) / len(pro),
         "ud10_gy": at_rank(ure, 0.1), "ud30_gy": at_rank(ure, 0.3),
         "rv100_cc": VOX_CC * sum(1 for d in rec if d >= rx),
         "rd2cc_gy": rec[math.ceil(2.0 / VOX_CC) - 1]}
    m["d90_meets"] = "yes" if m["d90_gy"] >= rx else "no"
    m["v100_meets"] = "yes" if m["v100_pct"] >= 95.0 else "no"
    m["ud10_meets"] = "yes" if m["ud10_gy"] <= 1.5 * rx else "no"
    m["rv100_meets"] = "yes" if m["rv100_cc"] <= 1.0 else "no"
    assert all(math.isfinite(v) for v in m.values() if not isinstance(v, str))
    return m


# ----------------------------------------------------------------------------- golden helpers -----------------
def dynamic_point_source(v_pre, v_0, v_ct, t_ct_h, half_life_days, r):
    """The engine's time integral for an inverse-square point source (G = 1/r^2, g = F = 1): cGy per U per cGy/h."""
    ed = Edema(v_pre, v_0, v_ct, t_ct_h, LN2 / (half_life_days * 24.0))
    return ed.integral(lambda x: 1.0 / (x * x), r, [])


def dynamic_point_source_closed_form(v_pre, v_0, v_ct, t_ct_h, half_life_days, r):
    """Closed form of the same integral when alpha = lambda / lambda_e is 1 or 2."""
    Y = v_0 - v_pre
    lam_e = -math.log((v_ct - v_pre) / Y) / t_ct_h
    lam = LN2 / (half_life_days * 24.0)
    alpha = lam / lam_e
    c = v_ct ** (2.0 / 3.0) / (lam_e * r * r)
    if abs(alpha - 1.0) < 1e-12:
        return c * 3.0 / Y * ((v_pre + Y) ** (1.0 / 3.0) - v_pre ** (1.0 / 3.0))
    if abs(alpha - 2.0) < 1e-12:
        f = lambda u: 0.75 * u ** (4.0 / 3.0) - 3.0 * v_pre * u ** (1.0 / 3.0)
        return c / (Y * Y) * (f(v_pre + Y) - f(v_pre))
    raise ValueError("closed form only for alpha 1 or 2")


def static_total(d, r, theta):
    """Dose per U to complete decay without edema: rate times the mean life (cGy per U)."""
    sd = SourceData(d)
    return rate_per_unit(sd, r, theta) / sd.lam


def dynamic_total_tiny_edema(d, r, theta):
    """The engine's time integral with a 1e-6 edema, which must equal the static total to about 1e-6."""
    sd = SourceData(d)
    ed = Edema(40.0, 40.0 * (1 + 1e-6), 40.0 * (1 + 0.5e-6), 24.0 * 20, sd.lam)
    return ed.integral(lambda x, t=theta: rate_per_unit(sd, x, t), r, sd.nodes2)


# ----------------------------------------------------------------------------- expected -----------------------
def expected(data=None):
    """{patient_id: {column: value}} for every patient, sorted by patient_id."""
    src, patients, batches, seeds, contours = load(data)
    bt = {b["batch_id"]: b for b in batches}
    models = {m: SourceData(d) for m, d in src.items()}
    by_patient = {}
    for s in seeds:
        if s["review"] == "accepted":
            by_patient.setdefault(s["patient_id"], []).append(s)
    out = {}
    for p in sorted(patients, key=lambda q: q["patient_id"]):
        pid = p["patient_id"]
        rx = float(p["prescription_gy"])
        t_imp = new_york(p["implant"])
        t_ct_h = (new_york(p["ct_scan"]) - t_imp).total_seconds() / 3600.0
        assert t_ct_h > 0
        implanted = []
        for s in by_patient[pid]:
            b = bt[s["batch_id"]]
            sd = models[b["seed_model"]]
            elapsed_h = (t_imp - dt.datetime.fromisoformat(b["calibrated_at"])).total_seconds() / 3600.0
            sk = per_seed_strength(b) * 2.0 ** (-elapsed_h / sd.half_h)
            c1 = (float(s["x1_mm"]) / 10, float(s["y1_mm"]) / 10, float(s["z1_mm"]) / 10)
            if s["x2_mm"].strip() == "":
                implanted.append((sd, sk, c1, None))
            else:
                c2 = (float(s["x2_mm"]) / 10, float(s["y2_mm"]) / 10, float(s["z2_mm"]) / 10)
                axis = tuple(b_ - a_ for a_, b_ in zip(c1, c2))
                n = math.sqrt(sum(a * a for a in axis))
                implanted.append((sd, sk, tuple((a_ + b_) / 2 for a_, b_ in zip(c1, c2)), tuple(a / n for a in axis)))
        sd = implanted[0][0]
        ed = Edema(float(p["volume_preimplant_cc"]), float(p["volume_postimplant_cc"]), float(p["volume_ct_cc"]),
                   t_ct_h, sd.lam)
        kernels = {one_d: Kernel(sd, ed, one_d) for one_d in {s[3] is None for s in implanted}}
        doses = {}
        for name, slices in contours[pid]["structures"].items():
            lst = []
            for (x, y, z) in voxel_centres(slices):
                cgy = 0.0
                for sd_, sk, centre, axis in implanted:
                    dx, dy, dz = x - centre[0], y - centre[1], z - centre[2]
                    r = math.sqrt(dx * dx + dy * dy + dz * dz)
                    if axis is None:
                        k = (ed.integral(lambda q: rate_1d(sd_, q), r, sd_.nodes1) if r < R_DIRECT
                             else kernels[True].read(r, 0.0))
                    else:
                        cos_t = abs(dx * axis[0] + dy * axis[1] + dz * axis[2]) / r
                        theta = math.degrees(math.acos(min(1.0, cos_t)))
                        k = (ed.integral(lambda q, t=theta: rate_per_unit(sd_, q, t), r, sd_.nodes2) if r < R_DIRECT
                             else kernels[False].read(r, theta))
                    cgy += sk * k
                lst.append(cgy / 100.0)
            doses[name] = lst
        out[pid] = indices(doses, rx)
    return out
