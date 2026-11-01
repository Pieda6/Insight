"""Verifier engine for tg71-mu-check: monitor units under AAPM TG-71 (Med Phys 2014;41:031501).

Photon beams: Eq. (1) (TPR) and Eq. (3) (PDDN), with Eq. (4) for Sc of a tertiary-MLC or tray-blocked field, the
patient-incident field projected to the depth of calculation for Sp, TPR and WF (to the normalization depth for Sp in
Eq. (3)), PDDN at another SSD by Eq. (14) and (15), OAR at the radial distance projected to 100 cm, and the
heterogeneity corrections of Eqs. (6) to (8). Electron beams: Eq. (10), (11) and (12) with the square-root rules of
Eq. (13) and (22) and the geometric mean of SSDeff (Sec. 3.B.2.d).

Every MU the protocol allows is computed (Eq. (1) or Eq. (3) for each photon beam, the bracket of Eq. (14) kept or
dropped, the wedge-factor field at depth or at the isocenter, SSDeff as the geometric mean of the sides or of the two
inverse-square corrections); an answer is right when it is within tolerance of one of them.
"""
import csv
import json
import math
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"


def _csv(name):
    with open(DATA / name, newline="") as fh:
        return list(csv.reader(fh))


def _lin(xs, ys, x):
    if not (math.isfinite(x) and xs[0] - 1e-9 <= x <= xs[-1] + 1e-9):
        raise ValueError(f"{x} outside {xs[0]}..{xs[-1]}")
    for xi, yi in zip(xs, ys):
        if abs(x - xi) < 1e-9 and yi is not None:
            return yi
    for i in range(len(xs) - 1):
        if x <= xs[i + 1] + 1e-12:
            a, b, ya, yb = xs[i], xs[i + 1], ys[i], ys[i + 1]
            if ya is None or yb is None:
                raise ValueError("no tabulated value")
            return ya + (yb - ya) * (x - a) / (b - a)
    return ys[-1]


class Grid:
    """Rows by first column, columns by header; bilinear interpolation."""

    def __init__(self, rows, col=lambda h: float(h.split("x")[0].split("_")[-1])):
        self.cols = [col(h) for h in rows[0][1:]]
        self.rows = [float(r[0]) for r in rows[1:]]
        self.v = [[float(x) if x.strip() else None for x in r[1:]] for r in rows[1:]]

    def __call__(self, row, colv):
        per = []
        for vals in self.v:
            try:
                per.append(_lin(self.cols, vals, colv))
            except ValueError:
                per.append(None)
        return _lin(self.rows, per, row)


class Tables:
    def __init__(self):
        self.pdd = Grid(_csv("pddn_6mv_ssd100.csv"))
        self.tpr = Grid(_csv("tpr_6mv.csv"))
        sc = _csv("scatter_6mv.csv")
        self.eq = [float(r[0]) for r in sc[1:]]
        self.sc_v = [float(r[2]) for r in sc[1:]]
        self.sp_v = [float(r[3]) for r in sc[1:]]
        self.oar = Grid(_csv("oar_6mv.csv"), col=float)
        wf = _csv("wedge_factors_6mv.csv")
        self.wf = {}
        for ang in sorted({r[0] for r in wf[1:]}):
            self.wf[int(ang)] = Grid([wf[0][1:]] + [r[1:] for r in wf[1:] if r[0] == ang], col=float)
        self.se = Grid(_csv("electron_9mev_output_factors.csv"))
        ssdeff = _csv("electron_ssdeff.csv")
        self.ssdeff_x = [float(r[0]) for r in ssdeff[1:]]
        self.ssdeff_y = [float(r[2]) for r in ssdeff[1:]]
        self.fair = Grid(_csv("electron_9mev_air_gap_factors.csv"), col=float)
        m = json.loads((DATA / "machine.json").read_text())
        self.p, self.e = m["photon"], m["electron"]

    def sc(self, r):
        return _lin(self.eq, self.sc_v, r)

    def sp(self, r):
        return _lin(self.eq, self.sp_v, r)

    def ssdeff(self, side):
        return _lin(self.ssdeff_x, self.ssdeff_y, side)


def eqsq(a, b):
    return 4 * a * b / (2 * a + 2 * b)


def photon_mu(t, b, formalism="tpr", bracket=False, wf_iso=False, sk=frozenset()):
    """MU for a photon beam. formalism 'tpr' is Eq. (1), 'pdd' is Eq. (3). sk names misreadings (for case tags)."""
    p = t.p
    sad, d0, ssd0, D0 = p["sad_cm"], p["normalization_depth_cm"], p["ssd0_cm"], p["d0_cgy_per_mu"]
    j = b["jaws_cm"]
    jaw_eq = eqsq(j["X1"] + j["X2"], j["Y1"] + j["Y2"])
    shaped = b["shaped_field_equivalent_square_cm"]
    r_iso = shaped if shaped is not None else jaw_eq
    rc = r_iso if "sc_shaped" in sk else jaw_eq
    ssd, d = b["ssd_cm"], b["point"]["depth_cm"]
    spd = ssd + d
    rd = r_iso if "no_projection" in sk else r_iso * spd / sad
    x, y = b["point"]["off_axis_cm"]
    rad = math.hypot(x, y)
    xr = rad if "oar_unprojected" in sk else rad * sad / spd
    oar = 1.0 if (rad == 0 or "oar_ignored" in sk) else t.oar(d, xr)
    tf = p["block_tray_factor"] if b["field_shaping"] == "block on tray" and "tray_ignored" not in sk else 1.0
    wf = 1.0
    if b["wedge_deg"]:
        wd = 10.0 if "wf_at_10cm" in sk else d
        wf = t.wf[b["wedge_deg"]](wd, r_iso if wf_iso else rd)
    cf = 1.0
    h = b["heterogeneity"]
    if h and "heterogeneity_ignored" not in sk:
        if h["correction"] == "RTAR":
            deff = sum((min(L["to_cm"], d) - L["from_cm"]) * L["rho_e"] for L in h["layers"] if L["from_cm"] < d)
            cf = t.tpr(deff, rd) / t.tpr(d, rd)
        else:
            lung = [L for L in h["layers"] if L["rho_e"] != 1.0]
            assert len(lung) == 1 and lung[0]["to_cm"] < d
            d1, d2 = d - lung[0]["from_cm"], d - lung[0]["to_cm"]
            if "batho_inverted" in sk:
                d1, d2 = d2, d1
            cf = (t.tpr(d1, rd) / t.tpr(d2, rd)) ** (lung[0]["rho_e"] - 1)
    D = b["dose_cgy"]
    if formalism == "tpr":
        inv = 1.0 if "inverse_square_ignored" in sk else ((ssd0 + d0) / spd) ** 2
        return D / (D0 * t.sc(rc) * t.sp(rd) * t.tpr(d, rd) * wf * tf * oar * inv * cf)
    rs = r_iso * ssd / sad
    rd0 = rs if "sp_surface_field" in sk else r_iso * (ssd + d0) / sad
    pdd = t.pdd(d, rs)
    if "mayneord_ignored" not in sk:
        s1, s2 = 100.0, ssd
        pdd *= ((s2 + d0) / (s2 + d) * (s1 + d) / (s1 + d0)) ** 2
        if bracket:
            f1 = lambda z: (s1 + z) / s1
            f2 = lambda z: (s2 + z) / s2
            pdd *= (t.tpr(d, rs * f2(d)) / t.tpr(d, rs * f1(d))) * (t.sp(rs * f1(d0)) / t.sp(rs * f1(d))) \
                * (t.sp(rs * f2(d)) / t.sp(rs * f2(d0)))
    inv = ((ssd0 + d0) / (ssd + (d if "pdd_inverse_square_to_point" in sk else d0))) ** 2
    return D * 100.0 / (D0 * t.sc(rc) * t.sp(rd0) * pdd * wf * tf * oar * inv * cf)


def electron_mu(t, b, gm_corr=False, sk=frozenset()):
    e = t.e
    D0, ssd0, dm = e["d0_cgy_per_mu"], e["ssd0_cm"], e["dm_cm"]
    L, W = b["insert_cm"]
    app = float(b["applicator"].split("x")[0])
    if "se_equivalent_square" in sk:
        se = t.se(eqsq(L, W), app)
    else:
        se = math.sqrt(t.se(L, app) * t.se(W, app))
    pdd = 100.0 if "isodose_ignored" in sk else b["prescription_isodose_pct"]
    g = b["ssd_cm"] - ssd0
    corr = 1.0
    if g:
        if b["extended_distance_method"] == "effective SSD":
            if "ssdeff_ignored" in sk:
                corr = ((ssd0 + dm) / (ssd0 + dm + g)) ** 2
            elif gm_corr:
                corr = math.prod((t.ssdeff(s) + dm) / (t.ssdeff(s) + dm + g) for s in (L, W))
            else:
                s = math.sqrt(t.ssdeff(L) * t.ssdeff(W))
                corr = ((s + dm) / (s + dm + g)) ** 2
        else:
            fair = 1.0 if "air_gap_factor_ignored" in sk else math.sqrt(t.fair(L, b["ssd_cm"]) * t.fair(W, b["ssd_cm"]))
            corr = ((ssd0 + dm) / (ssd0 + dm + g)) ** 2 * fair
    return b["dose_cgy"] * 100.0 / (D0 * pdd * se * corr)


def allowed(t, b, sk=frozenset()):
    """Every MU the protocol allows for this beam."""
    if b["modality"] == "electron":
        return [electron_mu(t, b, g, sk) for g in (False, True)]
    out = [photon_mu(t, b, "tpr", False, w, sk) for w in (False, True)]
    out += [photon_mu(t, b, "pdd", br, w, sk) for br in (False, True) for w in (False, True)]
    return out


def load():
    plans = json.loads((DATA / "plans.json").read_text())
    return plans, [b for p in plans["patients"] for b in p["beams"]]


def expected():
    t = Tables()
    _, beams = load()
    return {b["beam_id"]: allowed(t, b) for b in beams}
