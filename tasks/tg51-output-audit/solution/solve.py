"""Reference solution for tg51-output-audit: TG-51 (1999) with the 2014 photon addendum."""
import csv
import json
import math
from collections import defaultdict
from pathlib import Path

DATA = Path("/app/data")
OUT = Path("/app/output")

TO_KPA = {"kPa": 1.0, "hPa": 0.1, "mmHg": 101.325 / 760.0, "inHg": 3.386388640341}
REPLACED_BY = {"PTW 31003": "PTW 31013", "Wellhofer IC-10": "IBA CC13"}     # addendum Sec. 3.E (i) and (ii)


def rows(name):
    with open(DATA / name, newline="") as fh:
        return list(csv.DictReader(fh))


def interp(points, x):
    points = sorted(points)
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    raise ValueError(f"{x} outside the data")


class Audit:
    def __init__(self):
        self.audit = json.loads((DATA / "audit.json").read_text())
        self.chamber = {c["serial"]: c for cl in self.audit["clinics"] for c in cl["chambers"]}
        self.clinic = {b["beam_id"]: cl for cl in self.audit["clinics"] for b in cl["beams"]}
        self.beam = {b["beam_id"]: b for cl in self.audit["clinics"] for b in cl["beams"]}
        self.read = defaultdict(list)
        for r in rows("readings.csv"):
            self.read[(r["beam_id"], r["purpose"])].append(r)
        self.scan = defaultdict(list)
        for r in rows("depth_scans.csv"):
            self.scan[(r["beam_id"], r["scan"])].append((float(r["depth_cm"]), float(r["reading"])))
        self.profile = defaultdict(list)
        for r in rows("profiles.csv"):
            self.profile[r["beam_id"]].append((float(r["position_cm"]), float(r["relative_dose"])))
        self.pdd = defaultdict(list)
        for r in rows("electron_pdd.csv"):
            self.pdd[r["beam_id"]].append((float(r["depth_cm"]), float(r["pdd_percent"])))
        self.add = {r["chamber"]: r for r in rows("addendum_kq.csv")}
        self.tg51 = {r["chamber"]: r for r in rows("tg51_photon_kq.csv")}
        self.kecal = {r["chamber"]: float(r["kecal"]) for r in rows("tg51_kecal.csv")}

    # ---- TG-51 Sec. VII and addendum Eq. (3); Pleak = 1 and Prp applied separately
    def charge(self, beam_id, purpose, cross_calibrated=False):
        rs = self.read[(beam_id, purpose)]
        ch = self.chamber[rs[0]["chamber"]]
        vh, cal = float(ch["operating_voltage_V"]), ch["calibration_polarity"]
        per_mu = lambda r: float(r["reading_nC"]) / float(r["mu"])
        main = next(r for r in rs if r["polarity"] == cal and float(r["voltage_V"]) == vh)
        other = next(r for r in rs if r["polarity"] != cal and float(r["voltage_V"]) == vh)
        low = next(r for r in rs if r["polarity"] == cal and float(r["voltage_V"]) < vh)
        m, mo, ml = per_mu(main), per_mu(other), per_mu(low)
        m_plus, m_minus = (m, mo) if cal == "+" else (mo, m)
        p_pol = abs((m_plus - m_minus) / (2 * m))                                    # Eq. (9)
        v_ratio = vh / float(low["voltage_V"])
        p_ion = (1 - v_ratio) / (m / ml - v_ratio)                                   # Eq. (12)
        t = float(main["temperature"])
        if main["temperature_unit"] == "F":
            t = (t - 32) * 5 / 9
        p = float(main["pressure"]) * TO_KPA[main["pressure_unit"]]
        p_tp = (273.2 + t) / 295.2 * 101.33 / p                                      # Eq. (10)
        p_elec = 1.0 if cross_calibrated else self.clinic[beam_id]["electrometer"]["pelec"][main["electrometer_range"]]
        return abs(m) * p_tp * p_ion * p_pol * p_elec, main

    @staticmethod
    def ndw(ch):
        return ch["ndw"] * (1e7 if ch["ndw_unit"] == "cGy/nC" else 1.0)            # Gy/C

    def pct_at_10(self, beam_id, name, shift):
        s = [(z - shift, m) for z, m in self.scan[(beam_id, name)]]
        return 100 * interp(s, 10.0) / max(m for _, m in s)

    def shift(self, serial, frac):
        ch = self.chamber[serial]
        return frac * ch["cavity_radius_cm"] if ch["type"] == "cylindrical" else 0.0

    # ---- TG-51 Sec. VIII.B with addendum Secs. 4.H and 4.K
    def beam_quality(self, b):
        sh = lambda name: self.shift(b["scans"][name], 0.6)
        open_pct = self.pct_at_10(b["beam_id"], "open", sh("open"))
        foils = [k for k in b["scans"] if k.startswith("lead_foil")]
        if not b["fff"] and b["energy_MV"] < 10:
            return open_pct, open_pct
        if foils:
            pb = self.pct_at_10(b["beam_id"], foils[0], sh(foils[0]))
            if foils[0] == "lead_foil_50cm":
                x = (0.8905 + 0.00150 * pb) * pb if pb >= 73 else pb                 # Eq. (13)
            else:
                x = (0.8116 + 0.00264 * pb) * pb if pb >= 71 else pb                 # Eq. (14)
            return x, open_pct
        return (1.267 * open_pct - 20.0 if open_pct > 75 else open_pct), open_pct    # Eq. (15)

    def k_q(self, model, x):
        model = REPLACED_BY.get(model, model)
        if model in self.add:                                                       # addendum Table I, Eq. (1)
            r = self.add[model]
            if x <= 63:
                return 1.0 + (float(r["kq_63"]) - 1.0) * (x - 58) / 5
            return float(r["A"]) + float(r["B"]) * 1e-3 * x + float(r["C"]) * 1e-5 * x * x
        r = self.tg51[model]                                                        # TG-51 Table I
        pts = [(float(k[3:]), float(v)) for k, v in r.items() if k.startswith("kq_")]
        return interp(pts, x)

    def p_rp(self, b, ch):
        prof = sorted(self.profile[b["beam_id"]])
        half = ch["active_length_cm"] / 2
        inside = [v for p, v in prof if abs(p) <= half + 1e-9]
        return interp(prof, 0.0) / (sum(inside) / len(inside))

    def photon(self, b):
        ch = self.chamber[b["reference_chamber"]]
        m, _ = self.charge(b["beam_id"], "reference")
        x, open_pct = self.beam_quality(b)
        d10 = m * 1e-9 * self.p_rp(b, ch) * self.k_q(ch["model"], x) * self.ndw(ch) * 100   # cGy per MU
        if b["setup"] == "SAD":
            return d10, d10 / b["tmr_10"]
        return d10, d10 / (open_pct / 100)

    # ---- TG-51 Sec. X
    def r50(self, b):
        name = "electron"
        s = [(z - self.shift(b["scans"][name], 0.5), m) for z, m in self.scan[(b["beam_id"], name)]]
        top = max(range(len(s)), key=lambda i: s[i][1])
        half = s[top][1] / 2
        for (z0, m0), (z1, m1) in zip(s[top:], s[top + 1:]):
            if m0 >= half >= m1:
                i50 = z0 + (z1 - z0) * (m0 - half) / (m0 - m1)
                break
        return 1.029 * i50 - 0.06 if i50 <= 10 else 1.059 * i50 - 0.37               # Eqs. (16), (17)

    def k_r50(self, r50, kind):
        if kind == "cylindrical":
            return 0.9905 + 0.0710 * math.exp(-r50 / 3.67)                          # Eq. (19)
        return 1.2239 - 0.145 * r50 ** 0.214                                         # Eq. (20)

    def gradient(self, beam_id, purpose, main):
        g = self.read.get((beam_id, purpose + "_gradient"))
        return abs(float(g[0]["reading_nC"]) / float(g[0]["mu"]) / (float(main["reading_nC"]) / float(main["mu"])))

    def electron(self, b):
        ch = self.chamber[b["reference_chamber"]]
        r50 = self.r50(b)
        cross = ch.get("calibration") == "cross-calibrated"
        m, main = self.charge(b["beam_id"], "reference", cross_calibrated=cross)
        p_gr = self.gradient(b["beam_id"], "reference", main) if ch["type"] == "cylindrical" else 1.0
        if cross:                                                                    # Eq. (22)
            cc = ch["cross_calibration"]
            cb = self.beam[cc["beam_id"]]
            cyl = self.chamber[cc["cylindrical_chamber"]]
            r50c = self.r50(cb)
            mc, mainc = self.charge(cb["beam_id"], "crosscal_cylindrical")
            dw = mc * self.gradient(cb["beam_id"], "crosscal_cylindrical", mainc) * self.k_r50(r50c, "cylindrical") \
                * self.kecal[cyl["model"]] * self.ndw(cyl)
            mp, _ = self.charge(cb["beam_id"], "crosscal_plane_parallel", cross_calibrated=True)
            calib = dw / (mp * self.k_r50(r50c, ch["type"]))
        else:
            calib = self.kecal[ch["model"]] * self.ndw(ch)
        d_ref = m * 1e-9 * p_gr * self.k_r50(r50, ch["type"]) * calib * 100
        depth = 0.6 * r50 - 0.1                                                      # Eq. (18)
        return d_ref, d_ref / (interp(self.pdd[b["beam_id"]], depth) / 100)


def main():
    a = Audit()
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "dose_per_mu.csv", "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["beam_id", "dose_ref_cgy_per_mu", "dose_dmax_cgy_per_mu"])
        for cl in a.audit["clinics"]:
            for b in cl["beams"]:
                d_ref, d_max = a.photon(b) if b["modality"] == "photon" else a.electron(b)
                w.writerow([b["beam_id"], f"{d_ref:.5f}", f"{d_max:.5f}"])


if __name__ == "__main__":
    main()
