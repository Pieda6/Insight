"""Verifier engine for tg51-output-audit: reference dosimetry under AAPM TG-51 (Med Phys 1999;26:1847) and its photon
addendum (Med Phys 2014;41:041501).

Charge: M = Mraw PTP Pion Ppol Pelec Pleak Prp (TG-51 Eqs. 8-12, addendum Eq. 3). Photon beam quality from depth scans
shifted 0.6 rcav (TG-51 Sec. VIII), Eqs. 13-15, the addendum's Sec. 4.H (Eq. 15 allowed for flattened beams) and
4.K(3) (lead foil for every flattening-filter-free beam). kQ from addendum Table I (Eq. 1, or its tabulated values,
and below %dd(10)x = 63 linear to 1.000 at 58) for the chambers it lists or names a replacement for (Sec. 3.E), and
from TG-51 Table I otherwise. Electron beams: R50 (Eqs. 16-17), dref (Eq. 18), k'R50 (Eqs. 19-20), Pgr (Eq. 21),
kecal (Tables II-III) or the cross-calibrated product (Eq. 22, Pelec = 1). Dose at dmax from the clinical PDD (SSD
set-up) or TMR (SAD set-up).

allowed() returns every value the documents allow for a beam (kQ by Eq. 1 or by interpolating the addendum's table;
Eq. 13/14 or Eq. 15 for a flattened beam of 10 MV or more; the profile averaged as a mean of samples or by the
trapezoid rule). sk names misreadings, used only to tag cases.
"""
import csv
import json
import math
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"

KPA = {"kPa": 1.0, "hPa": 0.1, "mmHg": 0.133322387415, "inHg": 3.386388640341}
ADD_TAB_X = [63.0, 67.0, 73.0, 77.0, 81.0]
TG51_TAB_X = [58.0, 63.0, 66.0, 71.0, 81.0, 93.0]


def lin(xs, ys, x):
    if not (math.isfinite(x) and xs[0] - 1e-9 <= x <= xs[-1] + 1e-9):
        raise ValueError(f"{x} outside {xs[0]}..{xs[-1]}")
    for i in range(len(xs) - 1):
        if x <= xs[i + 1] + 1e-12:
            return ys[i] + (ys[i + 1] - ys[i]) * (x - xs[i]) / (xs[i + 1] - xs[i])
    return ys[-1]


def _csv(name):
    with open(DATA / name, newline="") as fh:
        return list(csv.DictReader(fh))


class Data:
    def __init__(self):
        self.audit = json.loads((DATA / "audit.json").read_text())
        self.kq_add = {r["chamber"]: r for r in _csv("addendum_kq.csv")}
        self.kq_tg51 = {r["chamber"]: r for r in _csv("tg51_photon_kq.csv")}
        self.kecal = {r["chamber"]: float(r["kecal"]) for r in _csv("tg51_kecal.csv")}
        self.chambers = {c["serial"]: c for cl in self.audit["clinics"] for c in cl["chambers"]}
        self.readings = {}
        for r in _csv("readings.csv"):
            self.readings.setdefault((r["beam_id"], r["purpose"]), []).append(r)
        self.scans = {}
        for r in _csv("depth_scans.csv"):
            self.scans.setdefault((r["beam_id"], r["scan"]), []).append((float(r["depth_cm"]), float(r["reading"])))
        self.profiles = {}
        for r in _csv("profiles.csv"):
            self.profiles.setdefault(r["beam_id"], []).append((float(r["position_cm"]), float(r["relative_dose"])))
        self.pdd = {}
        for r in _csv("electron_pdd.csv"):
            self.pdd.setdefault(r["beam_id"], []).append((float(r["depth_cm"]), float(r["pdd_percent"])))
        self.beams = [b for cl in self.audit["clinics"] for b in cl["beams"]]
        self.clinic_of = {b["beam_id"]: cl for cl in self.audit["clinics"] for b in cl["beams"]}


# ---------------------------------------------------------------- charge
def ptp(T, tunit, P, punit, sk=frozenset()):
    tc = T if (tunit == "C" or "temp_unit" in sk) else (T - 32.0) * 5.0 / 9.0
    pk = P if "pressure_unit" in sk else P * KPA[punit]
    return (273.2 + tc) / (273.2 + 22.0) * 101.33 / pk


def corrected(d, cl, rows, chamber, pelec_one=False, sk=frozenset()):
    """Fully corrected reading per MU in nC (Prp applied by the caller)."""
    cal = chamber["calibration_polarity"]
    vh = chamber["operating_voltage_V"]
    get = lambda pol, v: [r for r in rows if r["polarity"] == pol and float(r["voltage_V"]) == v]
    opp = "-" if cal == "+" else "+"
    (mh,) = get(cal, vh)
    (mo,) = get(opp, vh)
    lows = [r for r in rows if r["polarity"] == cal and float(r["voltage_V"]) != vh]
    (ml,) = lows
    mu = float(mh["mu"])
    rd = lambda r: float(r["reading_nC"]) / float(r["mu"])
    Mh, Mo, Ml = rd(mh), rd(mo), rd(ml)
    Mplus, Mminus = (Mh, Mo) if cal == "+" else (Mo, Mh)
    pp = abs((Mplus - Mminus) / (2.0 * (Mo if "ppol_wrong_reading" in sk else Mh)))
    if "ppol_ignored" in sk:
        pp = 1.0
    vl = float(ml["voltage_V"])
    ratio = vh / vl
    if "pion_continuous" in sk:
        pion = (1.0 - ratio ** 2) / (Mh / Ml - ratio ** 2)
    else:
        pion = (1.0 - ratio) / (Mh / Ml - ratio)
    if "pion_ignored" in sk:
        pion = 1.0
    env = mh
    pt = ptp(float(env["temperature"]), env["temperature_unit"], float(env["pressure"]), env["pressure_unit"], sk)
    if pelec_one and "crosscal_pelec" not in sk:
        pe = 1.0
    else:
        em = cl["electrometer"]
        rng = mh["electrometer_range"]
        if "pelec_wrong_range" in sk:
            rng = [k for k in em["pelec"] if k != rng][0]
        pe = em["pelec"][rng]
    return abs(Mh) * pt * pion * pp * pe, mu


# ---------------------------------------------------------------- scans
def shifted(scan, shift):
    return [(z - shift, m) for z, m in scan]


def value_at(curve, depth):
    xs = [c[0] for c in curve]
    ys = [c[1] for c in curve]
    return lin(xs, ys, depth)


def pdd10(scan, shift):
    c = shifted(scan, shift)
    return 100.0 * value_at(c, 10.0) / max(m for _, m in c)


def i50(scan, shift):
    c = shifted(scan, shift)
    mx = max(m for _, m in c)
    k = max(range(len(c)), key=lambda i: c[i][1])
    for i in range(k, len(c) - 1):
        (z0, m0), (z1, m1) = c[i], c[i + 1]
        if m0 >= 0.5 * mx >= m1:
            return z0 + (m0 - 0.5 * mx) * (z1 - z0) / (m0 - m1)
    raise ValueError("no 50% point")


def scan_shift(d, serial, factor, sk):
    ch = d.chambers[serial]
    if ch["type"] != "cylindrical" or "no_shift" in sk:
        return 0.0
    return factor * ch["cavity_radius_cm"]


# ---------------------------------------------------------------- photons
def dd10x(d, b, mode, sk):
    scans = {k[1]: v for k, v in d.scans.items() if k[0] == b["beam_id"]}
    sh = lambda name: scan_shift(d, b["scans"][name], 0.6, sk)
    open_ = pdd10(scans["open"], sh("open"))
    foil = [k for k in scans if k.startswith("lead_foil")]
    if b["energy_MV"] < 10 and not b["fff"]:
        return open_
    if foil and (b["fff"] or mode == "foil") and "fff_without_foil" not in sk:
        name = foil[0]
        pb = pdd10(scans[name], sh(name))
        if "foil_eq_ignored" in sk:
            return pb
        if name == "lead_foil_50cm":
            return (0.8905 + 0.00150 * pb) * pb if pb >= 73.0 else pb
        return (0.8116 + 0.00264 * pb) * pb if pb >= 71.0 else pb
    if "eq15_ignored" in sk:
        return open_
    return 1.267 * open_ - 20.0 if open_ > 75.0 else open_


def kq(d, model, x, mode, sk):
    sub = {"PTW 31003": "PTW 31013", "Wellhofer IC-10": "IBA CC13"}
    if model in sub and "no_substitution" not in sk:
        model = sub[model]
    old = {"PTW N30001": "PTW 30010", "PTW N30002": "PTW 30011", "PTW N30004": "PTW 30012"}
    if model in old and "old_ptw_new_data" in sk:
        model = old[model]
    if model in d.kq_add and not ("tg51_kq" in sk and model in d.kq_tg51):
        r = d.kq_add[model]
        tab = [float(r[f"kq_{int(v)}"]) for v in ADD_TAB_X]
        if x <= 63.0:
            return lin([58.0, 63.0], [1.0, tab[0]], x)
        if mode == "fit":
            return float(r["A"]) + float(r["B"]) * 1e-3 * x + float(r["C"]) * 1e-5 * x * x
        return lin(ADD_TAB_X, tab, x)
    r = d.kq_tg51[model]
    return lin(TG51_TAB_X, [float(r[f"kq_{int(v)}"]) for v in TG51_TAB_X], x)


def prp(d, b, ch, mode, sk):
    if "prp_ignored" in sk:
        return 1.0
    prof = sorted(d.profiles[b["beam_id"]])
    half = ch["active_length_cm"] / 2.0
    if "prp_full_profile" in sk:
        half = max(abs(p) for p, _ in prof)
    pts = [(p, v) for p, v in prof if -half - 1e-9 <= p <= half + 1e-9]
    centre = value_at(prof, 0.0)
    if mode == "mean":
        avg = sum(v for _, v in pts) / len(pts)
    else:
        area = sum((pts[i + 1][0] - pts[i][0]) * (pts[i + 1][1] + pts[i][1]) / 2 for i in range(len(pts) - 1))
        avg = area / (pts[-1][0] - pts[0][0])
    return centre / avg


def ndw_gy_per_c(ch):
    return ch["ndw"] * (1e7 if ch["ndw_unit"] == "cGy/nC" else 1.0)


def photon(d, b, kq_mode="fit", dd_mode="foil", prp_mode="mean", sk=frozenset()):
    cl = d.clinic_of[b["beam_id"]]
    ch = d.chambers[b["reference_chamber"]]
    m, mu = corrected(d, cl, d.readings[(b["beam_id"], "reference")], ch, sk=sk)
    x = dd10x(d, b, dd_mode, sk)
    k = kq(d, ch["model"], x, kq_mode, sk)
    dref = m * 1e-9 * prp(d, b, ch, prp_mode, sk) * k * ndw_gy_per_c(ch) * 100.0
    if b["setup"] == "SAD" and "sad_with_pdd" not in sk:
        return dref, dref / b["tmr_10"]
    scan = d.scans[(b["beam_id"], "open")]
    clin = x if "dmax_with_dd10x" in sk else pdd10(scan, scan_shift(d, b["scans"]["open"], 0.6, sk))
    return dref, dref / (clin / 100.0)


# ---------------------------------------------------------------- electrons
def r50_of(d, b, sk):
    scan = d.scans[(b["beam_id"], "electron")]
    h = i50(scan, scan_shift(d, b["scans"]["electron"], 0.5, sk))
    if "r50_is_i50" in sk:
        return h
    return 1.029 * h - 0.06 if h <= 10.0 else 1.059 * h - 0.37


def krp(r50, kind, sk):
    if ("kr50_swapped" in sk) == (kind == "cylindrical"):
        return 1.2239 - 0.145 * r50 ** 0.214
    return 0.9905 + 0.0710 * math.exp(-r50 / 3.67)


def electron_ref(d, b, serial, purpose, sk, pelec_one=False):
    cl = d.clinic_of[b["beam_id"]]
    ch = d.chambers[serial]
    rows = [r for r in d.readings[(b["beam_id"], purpose)]]
    m, mu = corrected(d, cl, rows, ch, pelec_one=pelec_one, sk=sk)
    r50 = r50_of(d, b, sk)
    pgr = 1.0
    if ch["type"] == "cylindrical" and "pgr_ignored" not in sk:
        (g,) = d.readings[(b["beam_id"], purpose + "_gradient")]
        pgr = (float(g["reading_nC"]) / float(g["mu"])) / (float([r for r in rows if r["polarity"] == ch["calibration_polarity"] and float(r["voltage_V"]) == ch["operating_voltage_V"]][0]["reading_nC"]) / mu)
        pgr = abs(pgr)
    return m, pgr, krp(r50, ch["type"], sk), r50, ch


def electron(d, b, sk=frozenset()):
    cl = d.clinic_of[b["beam_id"]]
    ch = d.chambers[b["reference_chamber"]]
    if ch.get("calibration") == "cross-calibrated":
        cc = ch["cross_calibration"]
        cb = next(x for x in d.beams if x["beam_id"] == cc["beam_id"])
        mc, pgrc, kc, _, chc = electron_ref(d, cb, cc["cylindrical_chamber"], "crosscal_cylindrical", sk)
        dw_cyl = mc * pgrc * kc * d.kecal[chc["model"]] * ndw_gy_per_c(chc)
        mp, _, kp, _, _ = electron_ref(d, cb, b["reference_chamber"], "crosscal_plane_parallel", sk, pelec_one=True)
        product = dw_cyl / (mp * kp)
        m, pgr, k, r50, _ = electron_ref(d, b, b["reference_chamber"], "reference", sk, pelec_one=True)
        dref = m * 1e-9 * pgr * k * product * 100.0
    else:
        m, pgr, k, r50, _ = electron_ref(d, b, b["reference_chamber"], "reference", sk)
        dref = m * 1e-9 * pgr * k * d.kecal[ch["model"]] * ndw_gy_per_c(ch) * 100.0
    depth = 0.6 * r50 - 0.1
    if "e_pdd_from_ionization" in sk:
        scan = d.scans[(b["beam_id"], "electron")]
        c = shifted(scan, scan_shift(d, b["scans"]["electron"], 0.5, sk))
        p = 100.0 * value_at(c, depth) / max(v for _, v in c)
    else:
        p = value_at(sorted(d.pdd[b["beam_id"]]), depth)
    return dref, dref / (p / 100.0)


def allowed(d, b, sk=frozenset()):
    if b["modality"] == "electron":
        return [electron(d, b, sk)]
    out = []
    for km in ("fit", "table"):
        for dm in ("foil", "eq15"):
            for pm in ("mean", "trapezoid"):
                out.append(photon(d, b, km, dm, pm, sk))
    return out


def expected():
    d = Data()
    return {b["beam_id"]: allowed(d, b) for b in d.beams}
