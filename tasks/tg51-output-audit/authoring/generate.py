"""Generate the calibration worksheets for tg51-output-audit (seed 19990901).

Writes audit.json, readings.csv, depth_scans.csv, profiles.csv and electron_pdd.csv to both data copies (the report
tables addendum_kq.csv, tg51_photon_kq.csv and tg51_kecal.csv are transcribed by hand), tests/case_tags.json and
evidence/answers.json. Readings are scaled so the dose per MU at dmax lands near the clinic's 1 cGy/MU convention.
"""
import sys
sys.dont_write_bytecode = True       # never leave __pycache__ in the submitted task folder
import csv
import json
import math
import random
import shutil
from pathlib import Path

TASK = Path(__file__).resolve().parent.parent
ENV = TASK / "environment" / "data"
sys.path.insert(0, str(TASK / "tests"))
import engine  # noqa: E402

SEED = 19990901
TOL = 0.003
FAMILIES = ("temp_unit", "pressure_unit", "pelec_wrong_range", "ppol_ignored", "ppol_wrong_reading", "pion_ignored",
            "pion_continuous", "prp_ignored", "prp_full_profile", "no_shift", "tg51_kq", "no_substitution",
            "old_ptw_new_data", "dmax_with_dd10x", "sad_with_pdd", "foil_eq_ignored", "eq15_ignored",
            "fff_without_foil", "r50_is_i50", "kr50_swapped", "pgr_ignored", "e_pdd_from_ionization", "crosscal_pelec")

# model: (type, cavity radius cm, active length cm, typical ND,w Gy/C)
SPEC = {
    "NE2571": ("cylindrical", 0.315, 2.40, 5.33e7), "Exradin A12": ("cylindrical", 0.305, 2.42, 5.38e7),
    "Capintec PR-06C/G": ("cylindrical", 0.320, 2.20, 5.50e7), "PTW 30013": ("cylindrical", 0.305, 2.30, 5.40e7),
    "IBA FC65-G": ("cylindrical", 0.310, 2.30, 4.82e7), "Exradin A19": ("cylindrical", 0.310, 2.16, 5.29e7),
    "PTW 30012": ("cylindrical", 0.305, 2.30, 5.46e7), "IBA FC65-P": ("cylindrical", 0.310, 2.30, 4.84e7),
    "PTW N30001": ("cylindrical", 0.305, 2.30, 5.36e7), "PTW N30004": ("cylindrical", 0.305, 2.30, 5.31e7),
    "NE2505/3,3A": ("cylindrical", 0.315, 2.40, 5.30e7), "NE2577": ("cylindrical", 0.315, 1.00, 1.43e8),
    "PTW 31003": ("cylindrical", 0.275, 1.65, 1.03e8), "Wellhofer IC-10": ("cylindrical", 0.300, 0.58, 2.79e8),
    "Capintec PR-05/PR-05P": ("cylindrical", 0.200, 1.10, 2.36e8), "IBA FC23-C": ("cylindrical", 0.310, 1.20, 1.38e8),
    "Exradin A12S": ("cylindrical", 0.305, 0.73, 1.62e8), "IBA CC25": ("cylindrical", 0.300, 1.00, 1.10e8),
    "IBA CC13": ("cylindrical", 0.300, 0.58, 2.75e8), "Exradin A1SL": ("cylindrical", 0.200, 0.44, 4.73e8),
    "PTW 31013": ("cylindrical", 0.275, 1.65, 1.04e8),
    "PTB/Roos": ("plane-parallel", 0.780, None, 8.27e7), "Markus": ("plane-parallel", 0.265, None, 5.60e8),
    "NACP": ("plane-parallel", 0.500, None, 1.62e8), "Exradin": ("plane-parallel", 1.000, None, 4.50e7),
}
PHOTON_REF = ["NE2571", "Exradin A12", "Capintec PR-06C/G", "PTW 30013", "IBA FC65-G", "Exradin A19", "PTW 30012",
              "IBA FC65-P", "PTW N30001", "PTW N30004", "NE2505/3,3A", "NE2577", "PTW 31003", "Wellhofer IC-10",
              "Capintec PR-05/PR-05P", "IBA FC23-C", "Exradin A12S"]
ELECTRON_CYL = ["NE2571", "Exradin A12", "Capintec PR-06C/G", "PTW N30001", "PTW N30004", "NE2505/3,3A"]
SCANNING = ["IBA CC13", "Exradin A1SL", "PTW 31013", "IBA CC25"]
PP = ["PTB/Roos", "Markus", "NACP", "Exradin"]
PHOTON_X = {"6X": (66.2, 67.6), "10X": (72.6, 74.2), "15X": (76.2, 77.6), "18X": (79.0, 80.8),
            "6FFF": (63.2, 64.2), "10FFF": (70.8, 72.0)}
TMR10 = {"6X": 0.742, "10X": 0.790, "15X": 0.818, "18X": 0.838, "6FFF": 0.718, "10FFF": 0.770}
R50 = {6: 2.40, 9: 3.55, 12: 4.95, 16: 6.55, 20: 8.10}
CLINICS = ["Lakeshore Cancer Center", "Mesa Verde Radiation Oncology", "St. Brendan's Hospital", "Northfield Regional",
           "Cascade Oncology", "Riverbend Medical Center", "High Plains Cancer Institute", "Bayview Radiation Therapy",
           "Granite State Oncology", "Sun Valley Cancer Care", "Harbor Point Medical", "Pinecrest Radiotherapy"]


def r4(x):
    return float(f"{x:.6g}")


def photon_dd(d, mu, b, contam):
    return (1 - math.exp(-d / b)) * math.exp(-mu * d) * (100.0 / (100.0 + d)) ** 2 + contam * math.exp(-d / 1.1)


def fit_mu(target, b, contam):
    lo, hi = 0.005, 0.12
    for _ in range(80):
        mid = (lo + hi) / 2
        zs = [i / 100 for i in range(0, 3001)]
        vals = [photon_dd(z, mid, b, contam) for z in zs]
        pct = 100 * photon_dd(10.0, mid, b, contam) / max(vals)
        lo, hi = (mid, hi) if pct > target else (lo, mid)
    return (lo + hi) / 2


def photon_scan(rng, target, shift, b, contam):
    mu = fit_mu(target, b, contam)
    scale = rng.uniform(0.8, 3.0)
    out = []
    z = round(max(shift, 0.0) + 0.1, 1)
    while z <= 30.0 + 1e-9:
        out.append((round(z, 1), r4(scale * photon_dd(z - shift, mu, b, contam))))
        z = round(z + 0.1, 1)
    return out


def e_curve(d, dm, dh, w, s0, tail, q=0.0, span=1.0):
    if d <= dm:
        return s0 + (1 - s0) * (1 - ((dm - d) / dm) ** 2)
    g = lambda x: 1 / (1 + math.exp((x - dh) / w))
    return (tail + (1 - tail) * g(d) / g(dm)) * max(0.0, 1 - q * ((d - dm) / span) ** 2)


def fit_dh(target50, dm, w, s0, tail, q=0.0, span=1.0):
    lo, hi = dm, dm + 15
    for _ in range(80):
        mid = (lo + hi) / 2
        v = e_curve(target50, dm, mid, w, s0, tail, q, span)
        lo, hi = (mid, hi) if v < 0.5 else (lo, mid)
    return (lo + hi) / 2


def pres(rng, altitude):
    kpa = rng.uniform(83.0, 85.5) if altitude else rng.uniform(98.6, 102.4)
    unit = rng.choice(["kPa", "kPa", "hPa", "mmHg", "inHg"])
    return round(kpa / engine.KPA[unit], {"kPa": 2, "hPa": 1, "mmHg": 1, "inHg": 2}[unit]), unit


def temp(rng, fahrenheit):
    c = rng.uniform(19.0, 24.5)
    return (round(c * 9 / 5 + 32, 1), "F") if fahrenheit else (round(c, 1), "C")


def reading_rows(rng, beam_id, purpose, ch, cl, env, rng_name, pion, ppol, mu, base):
    vh = ch["operating_voltage_V"]
    vl = vh / 2
    ratio = vh / vl
    mh = base
    ml = mh / (ratio + (1 - ratio) / pion)
    other = (2 * ppol - 1) * mh
    cal = ch["calibration_polarity"]
    sign = 1 if cal == "+" else -1
    rows = [(cal, vh, sign * mh), ("-" if cal == "+" else "+", vh, -sign * other), (cal, vl, sign * ml)]
    out = []
    for pol, v, m in rows:
        out.append({"beam_id": beam_id, "purpose": purpose, "chamber": ch["serial"], "polarity": pol,
                    "voltage_V": f"{v:g}", "mu": mu, "reading_nC": f"{m:.4f}", "electrometer_range": rng_name,
                    "temperature": env[0], "temperature_unit": env[1], "pressure": env[2], "pressure_unit": env[3]})
    return out


def make_chamber(rng, cl_id, model, k, calib="ADCL"):
    t, rcav, length, ndw = SPEC[model]
    ch = {"serial": f"{cl_id}-{k}", "model": model, "type": t, "cavity_radius_cm": rcav,
          "calibration_polarity": rng.choice(["+", "-", "+"]), "operating_voltage_V": rng.choice([300, 300, 250])}
    if t == "cylindrical":
        ch["active_length_cm"] = length
    if calib == "ADCL":
        v = ndw * rng.uniform(0.985, 1.015)
        if rng.random() < 0.3:
            ch["ndw"], ch["ndw_unit"] = round(v / 1e7, 4), "cGy/nC"
        else:
            ch["ndw"], ch["ndw_unit"] = float(f"{v:.5g}"), "Gy/C"
        ch["calibration"] = "ADCL"
    return ch


def build(rng):
    clinics, readings, scans, profiles, pdds = [], [], [], [], []
    for ci, name in enumerate(CLINICS):
        cid = f"C{ci + 1:02d}"
        altitude = name in ("Mesa Verde Radiation Oncology", "High Plains Cancer Institute")
        fahrenheit = rng.random() < 0.3
        em = {"model": rng.choice(["Standard Imaging MAX 4000", "PTW UNIDOS webline", "IBA Dose 1", "Sun Nuclear PC Electrometer"]),
              "pelec": {"low": round(rng.uniform(0.997, 1.004), 4), "high": round(rng.uniform(0.997, 1.004), 4)}}
        ref = make_chamber(rng, cid, rng.choice(PHOTON_REF), "R")
        scan_ch = make_chamber(rng, cid, rng.choice(SCANNING), "S")
        scan_ch.pop("ndw", None), scan_ch.pop("ndw_unit", None), scan_ch.pop("calibration", None)
        scan_ch["use"] = "depth scans only"
        chambers = [ref, scan_ch]
        has_e = rng.random() < 0.75
        ecyl = ref if ref["model"] in ELECTRON_CYL else None
        if has_e and ecyl is None:
            ecyl = make_chamber(rng, cid, rng.choice(ELECTRON_CYL), "E")
            chambers.append(ecyl)
        pp = None
        if has_e:
            cross = rng.random() < 0.5
            pp = make_chamber(rng, cid, rng.choice(PP), "P", "ADCL" if not cross else "cross")
            if cross:
                pp["calibration"] = "cross-calibrated"
            chambers.append(pp)
        beams = []
        linacs = rng.choice([1, 2, 2, 3])
        for li in range(linacs):
            lname = f"Linac {li + 1}"
            pset = rng.sample(list(PHOTON_X), rng.choice([2, 3, 3, 4]))
            for en in pset:
                bid = f"{cid}-L{li + 1}-{en}"
                fff = en.endswith("FFF")
                mv = int(en.rstrip("XF"))
                x_true = rng.uniform(*PHOTON_X[en])
                setup = "SAD" if rng.random() < 0.3 else "SSD"
                b = {"beam_id": bid, "machine": lname, "modality": "photon", "energy_MV": mv, "fff": fff,
                     "setup": setup, "reference_chamber": ref["serial"], "scans": {"open": scan_ch["serial"]}}
                if setup == "SAD":
                    b["tmr_10"] = round(TMR10[en] * rng.uniform(0.985, 1.015), 4)
                sh = 0.6 * scan_ch["cavity_radius_cm"]
                bpar = rng.uniform(0.30, 0.42) * (1 + 0.15 * (mv >= 10))
                if mv < 10 and not fff:
                    scans += [dict(beam_id=bid, scan="open", depth_cm=z, reading=v)
                              for z, v in photon_scan(rng, x_true, sh, bpar, 0.0)]
                else:
                    want_foil = fff or rng.random() < 0.6
                    open_ = (x_true + 20.0) / 1.267 + rng.uniform(-0.25, 0.25) if not fff else x_true - rng.uniform(0.2, 0.6)
                    contam = rng.uniform(0.02, 0.06)
                    scans += [dict(beam_id=bid, scan="open", depth_cm=z, reading=v)
                              for z, v in photon_scan(rng, open_, sh, bpar, contam)]
                    if want_foil:
                        pos = "lead_foil_50cm" if rng.random() < 0.7 else "lead_foil_30cm"
                        a, c0, thr = (0.00150, 0.8905, 73.0) if pos == "lead_foil_50cm" else (0.00264, 0.8116, 71.0)
                        pb = (-c0 + math.sqrt(c0 * c0 + 4 * a * x_true)) / (2 * a)
                        if pb < thr:
                            pb = x_true
                        scans += [dict(beam_id=bid, scan=pos, depth_cm=z, reading=v)
                                  for z, v in photon_scan(rng, pb, sh, bpar, rng.uniform(0.0, 0.01))]
                        b["scans"][pos] = scan_ch["serial"]
                # radial profile across the chamber at 10 cm
                c2 = rng.uniform(0.0045, 0.0065) if en == "6FFF" else rng.uniform(0.008, 0.012) if fff else -rng.uniform(0.0004, 0.0016)
                tilt = rng.uniform(-0.0015, 0.0015)
                scale = rng.uniform(90, 110)
                for i in range(-25, 26):
                    p = i / 10
                    profiles.append(dict(beam_id=bid, position_cm=f"{p:.1f}", relative_dose=f"{scale * (1 - c2 * p * p + tilt * p):.3f}"))
                env = (*temp(rng, fahrenheit), *pres(rng, altitude))
                pion = rng.uniform(1.012, 1.030) if fff else rng.uniform(1.002, 1.009)
                ppol = rng.uniform(0.9976, 1.0024) if mv <= 6 else rng.uniform(0.9965, 1.0035)
                mu = rng.choice([100, 200, 200, 300])
                readings += reading_rows(rng, bid, "reference", ref, None, env, rng.choice(["low", "high"]), pion, ppol, mu, 1.0)
                beams.append(b)
            if has_e and rng.random() < 0.85:
                eset = sorted(rng.sample(list(R50), rng.choice([3, 4, 5])))
                ebeams = []
                for e in eset:
                    bid = f"{cid}-L{li + 1}-{e}MeV"
                    r50 = R50[e] * rng.uniform(0.97, 1.03)
                    use_pp = r50 <= 4.3
                    ch = pp if use_pp else ecyl
                    sch = pp if (use_pp or rng.random() < 0.5) else scan_ch
                    b = {"beam_id": bid, "machine": lname, "modality": "electron", "energy_MeV": e, "setup": "SSD",
                         "reference_chamber": ch["serial"], "scans": {"electron": sch["serial"]}}
                    i50 = (r50 + 0.06) / 1.029
                    dm = max(0.9, min(0.48 * r50 + rng.uniform(-0.15, 0.1), 2.9))
                    w = 0.12 + 0.028 * r50
                    s0 = 0.72 + 0.03 * e / 4 + rng.uniform(-0.02, 0.02)
                    tail = 0.004 * e / 3
                    qi = 0.03 + 0.004 * e + rng.uniform(-0.005, 0.005)
                    sp = max(r50 - dm, 0.8)
                    dh = fit_dh(i50, dm, w, s0, tail, qi, sp)
                    shift = 0.5 * sch["cavity_radius_cm"] if sch["type"] == "cylindrical" else 0.0
                    sc = rng.uniform(0.8, 3.0)
                    z = round(max(shift, 0.0), 1)
                    while z <= round(r50 * 1.5 + 2, 1):
                        scans.append(dict(beam_id=bid, scan="electron", depth_cm=z, reading=r4(sc * e_curve(z - shift, dm, dh, w, s0, tail, qi, sp))))
                        z = round(z + 0.1, 1)
                    # clinical percentage depth dose (dose, not ionization)
                    dmd = dm + rng.uniform(-0.1, 0.1)
                    qd = qi - 0.012
                    dhd = fit_dh(r50, dmd, w * 0.95, s0 + 0.04, tail, qd, sp)
                    z = 0.0
                    while z <= round(r50 * 1.5 + 2, 1):
                        pdds.append(dict(beam_id=bid, depth_cm=f"{z:.1f}", pdd_percent=f"{100 * min(1.0, e_curve(z, dmd, dhd, w * 0.95, s0 + 0.04, tail, qd, sp)):.2f}"))
                        z = round(z + 0.1, 1)
                    env = (*temp(rng, fahrenheit), *pres(rng, altitude))
                    pion = rng.uniform(1.004, 1.014)
                    ppol = rng.uniform(0.996, 1.004) if ch["type"] == "plane-parallel" else rng.uniform(0.998, 1.004)
                    mu = rng.choice([100, 200])
                    readings += reading_rows(rng, bid, "reference", ch, None, env, rng.choice(["low", "high"]), pion, ppol, mu, 1.0)
                    b["_curve"] = (dm, dh, w, s0, tail, r50, qi, sp)
                    beams.append(b)
                    ebeams.append(b)
                if pp["calibration"] == "cross-calibrated" and "cross_calibration" not in pp:
                    top = ebeams[-1]
                    if top["reference_chamber"] != ecyl["serial"]:
                        top["reference_chamber"] = ecyl["serial"]
                    pp["cross_calibration"] = {"beam_id": top["beam_id"], "cylindrical_chamber": ecyl["serial"]}
                    env = (*temp(rng, fahrenheit), *pres(rng, altitude))
                    mu = 200
                    readings += reading_rows(rng, top["beam_id"], "crosscal_cylindrical", ecyl, None, env, "high", rng.uniform(1.004, 1.012), rng.uniform(0.998, 1.003), mu, rng.uniform(15, 30))
                    readings += reading_rows(rng, top["beam_id"], "crosscal_plane_parallel", pp, None, env, "low", rng.uniform(1.004, 1.012), rng.uniform(0.997, 1.003), mu, rng.uniform(8, 60))
        if pp is not None and pp["calibration"] == "cross-calibrated" and "cross_calibration" not in pp:
            pp["calibration"] = "ADCL"
            t = make_chamber(rng, cid, pp["model"], "P")
            pp["ndw"], pp["ndw_unit"] = t["ndw"], t["ndw_unit"]
        clinics.append({"clinic_id": cid, "name": name, "electrometer": em, "chambers": chambers, "beams": beams})
    return clinics, readings, scans, profiles, pdds


def gradient_rows(clinics, readings):
    """Readings with the cylindrical chamber's centre at dref + 0.5 rcav, for every purpose measured with one."""
    out = []
    byk = {}
    for r in readings:
        byk.setdefault((r["beam_id"], r["purpose"]), []).append(r)
    chs = {c["serial"]: c for cl in clinics for c in cl["chambers"]}
    for cl in clinics:
        for b in cl["beams"]:
            if b["modality"] != "electron":
                continue
            dm, dh, w, s0, tail, r50, qi, sp = b["_curve"]
            for purpose in ("reference", "crosscal_cylindrical"):
                rows = byk.get((b["beam_id"], purpose))
                if not rows:
                    continue
                ch = chs[rows[0]["chamber"]]
                if ch["type"] != "cylindrical":
                    continue
                main = rows[0]
                dref = 0.6 * r50 - 0.1
                h = 0.5 * ch["cavity_radius_cm"]
                ratio = e_curve(dref, dm, dh, w, s0, tail, qi, sp) / e_curve(dref - h, dm, dh, w, s0, tail, qi, sp)
                g = dict(main)
                g["purpose"] = purpose + "_gradient"
                g["reading_nC"] = f"{float(main['reading_nC']) * ratio:.4f}"
                out.append(g)
    return out


FIELDS = ["beam_id", "purpose", "chamber", "polarity", "voltage_V", "mu", "reading_nC", "electrometer_range",
          "temperature", "temperature_unit", "pressure", "pressure_unit"]


def write(clinics, readings, scans, profiles, pdds, d=ENV):
    for cl in clinics:
        for b in cl["beams"]:
            b.pop("_curve", None)
    (d / "audit.json").write_text(json.dumps({"clinics": clinics}, indent=1) + "\n")
    with open(d / "readings.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader(), w.writerows(readings)
    for name, rows, f in (("depth_scans.csv", scans, ["beam_id", "scan", "depth_cm", "reading"]),
                          ("profiles.csv", profiles, ["beam_id", "position_cm", "relative_dose"]),
                          ("electron_pdd.csv", pdds, ["beam_id", "depth_cm", "pdd_percent"])):
        with open(d / name, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=f, lineterminator="\n")
            w.writeheader(), w.writerows(rows)


def tags(dd, b, truth):
    out = []
    for fam in FAMILIES:
        try:
            base = engine.allowed(dd, b)
            alt = engine.allowed(dd, b, frozenset([fam]))
        except (ValueError, KeyError, StopIteration):
            continue
        moved = [a for a, o in zip(alt, base) if max(abs(a[0] - o[0]), abs(a[1] - o[1])) > 1e-12]
        if moved and all(not any(abs(a[0] / w[0] - 1) <= TOL and abs(a[1] / w[1] - 1) <= TOL for w in truth) for a in moved):
            out.append(fam)
    return out


def main():
    rng = random.Random(SEED)
    clinics, readings, scans, profiles, pdds = build(rng)
    curves = {b["beam_id"]: b.get("_curve") for cl in clinics for b in cl["beams"]}
    readings += gradient_rows(clinics, readings)
    write(clinics, readings, scans, profiles, pdds)
    for cl in clinics:
        for b in cl["beams"]:
            if curves[b["beam_id"]]:
                b["_curve"] = curves[b["beam_id"]]
    # scale each beam's reference readings so the dose at dmax is near 1 cGy/MU
    engine.DATA = ENV
    dd = engine.Data()
    target = {b["beam_id"]: rng.uniform(0.985, 1.015) for b in dd.beams}
    factor = {}
    for b in dd.beams:
        dmax = engine.allowed(dd, b)[0][1]
        factor[b["beam_id"]] = target[b["beam_id"]] / dmax
    for r in readings:
        if r["purpose"] in ("reference", "reference_gradient"):
            r["reading_nC"] = f"{float(r['reading_nC']) * factor[r['beam_id']]:.4f}"
    write(clinics, readings, scans, profiles, pdds)
    for f in ENV.iterdir():
        shutil.copy(f, TASK / "tests" / "data" / f.name)
    dd = engine.Data()
    truth, ctags, spread = {}, {}, 0.0
    for b in dd.beams:
        t = engine.allowed(dd, b)
        truth[b["beam_id"]] = t
        spread = max(spread, max(v[1] for v in t) / min(v[1] for v in t) - 1, max(v[0] for v in t) / min(v[0] for v in t) - 1)
        ctags[b["beam_id"]] = tags(dd, b, t)
    (TASK / "tests" / "case_tags.json").write_text(json.dumps(ctags, indent=1) + "\n")
    (TASK / "authoring" / "evidence" / "answers.json").write_text(json.dumps(truth, indent=1) + "\n")
    ph = sum(b["modality"] == "photon" for b in dd.beams)
    print(f"{len(dd.audit['clinics'])} clinics, {len(dd.beams)} beams ({ph} photon, {len(dd.beams) - ph} electron); "
          f"largest spread among allowed values {spread * 100:.3f}%")
    for fam in FAMILIES:
        print(f"{sum(fam in v for v in ctags.values()):4d}  {fam}")
    print("beams with no tag:", sum(not v for v in ctags.values()))


if __name__ == "__main__":
    main()
