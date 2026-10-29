#!/usr/bin/env python3
"""Reference solution for sediment-basin-routing.

Hydrology: storms from the 6-minute gauge (six dry hours separate storms); for each drainage area and storm, the
state at the storm's start gives the curve number and the sheet-flow surface; time of concentration from the flow
path by TR-55 chapter 3 (sheet flow eq. 3-3 with table 3-1 n, shallow concentrated flow from appendix F, channel
flow by Manning eq. 3-4, minimum 0.1 h); accumulated runoff by NEH 630.10 eq. 10-11; unit hydrograph from NEH
630.16 table 16-1 (Tp = dD/2 + 0.6 Tc, qp = 484 A Q / Tp) convolved with the 6-minute runoff increments.
Hydraulics (HEC-22 4th ed.): trapezoid storage (eq. 10.10) or surveyed contours by the conic formula (eq. 10.19)
with linear area between contours; dewatering orifice (eq. 10.23), riser weir/orifice (example 10.11), broad-
crested spillway, added (table 10.10); forebay divider = sharp-crested weir (eq. 10.32) with submergence (eq.
10.34) plus an orifice whose head is the difference of water surfaces when submerged, flowing from the higher
pool to the lower.  Routing: storage-indication (NEH 630.17 eq. 17-3) with every flow averaged over the step;
a forebay and its main cell are solved together at each step (nested safeguarded Newton).
"""
import bisect
import csv
import json
import math
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

DATA = Path("/app/data")
OUT = Path("/app/output")
START = datetime(2026, 4, 1)
STEP = timedelta(minutes=6)
N = 183 * 240
DT = 360.0
DD = 0.1
G2 = math.sqrt(2 * 32.2)
SHEET_N = {"Smooth surfaces (concrete, asphalt, gravel, or bare soil)": 0.011, "Fallow (no residue)": 0.05,
           "Cultivated soils: residue cover <=20%": 0.06, "Cultivated soils: residue cover >20%": 0.17,
           "Grass: short grass prairie": 0.15, "Grass: dense grasses": 0.24, "Grass: Bermudagrass": 0.41,
           "Range (natural)": 0.13, "Woods: light underbrush": 0.40, "Woods: dense underbrush": 0.80}
T_RATIO = [0, .1, .2, .3, .4, .5, .6, .7, .8, .9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0, 2.2,
           2.4, 2.6, 2.8, 3.0, 3.2, 3.4, 3.6, 3.8, 4.0, 4.5, 5.0]
Q_RATIO = [.000, .030, .100, .190, .310, .470, .660, .820, .930, .990, 1.000, .990, .930, .860, .780, .680, .560,
           .460, .390, .330, .280, .207, .147, .107, .077, .055, .040, .029, .021, .015, .011, .005, .000]


def idx(stamp):
    return round((datetime.strptime(stamp, "%Y-%m-%dT%H:%M") - START) / STEP)


def stamp(i):
    return (START + STEP * i).strftime("%Y-%m-%dT%H:%M")


def ratio(x):
    if x <= 0 or x >= 5:
        return 0.0
    j = bisect.bisect_right(T_RATIO, x) - 1
    return Q_RATIO[j] + (Q_RATIO[j + 1] - Q_RATIO[j]) * (x - T_RATIO[j]) / (T_RATIO[j + 1] - T_RATIO[j])


def accumulated_runoff(p, cn):
    s = 1000 / cn - 10
    ia = 0.2 * s
    return 0.0 if p <= ia else (p - ia) ** 2 / (p - ia + s)


def time_of_concentration(path, surface, p2):
    sh = path["sheet"]
    tc = 0.007 * (SHEET_N[surface] * sh["length_ft"]) ** 0.8 / (math.sqrt(p2) * sh["slope"] ** 0.4)
    sc = path["shallow"]
    tc += sc["length_ft"] / (3600 * (20.3282 if sc["paved"] else 16.1345) * math.sqrt(sc["slope"]))
    ch = path.get("channel")
    if ch:
        v = 1.49 / ch["n"] * (ch["area_sqft"] / ch["wetted_perimeter_ft"]) ** (2 / 3) * math.sqrt(ch["slope"])
        tc += ch["length_ft"] / (3600 * v)
    return max(tc, 0.1)


def orifice_flow(c, area, centroid, up, down=None):
    head = up - centroid if down is None or down <= centroid else up - down
    return c * area * G2 * math.sqrt(head) if head > 0 else 0.0


class Cell:
    def __init__(self, rec):
        self.id = rec["basin_id"]
        g = rec["geometry"]
        if g["type"] == "trapezoid":
            self.bottom = g["bottom_elevation_ft"]
            self.trap = (g["bottom_length_ft"], g["bottom_width_ft"], g["side_slope_h_per_v"])
            self.cont = None
        else:
            self.cont = [(c["elevation_ft"], c["area_sqft"]) for c in g["contours"]]
            self.bottom = self.cont[0][0]
            self.trap = None
            self.cum = [0.0]
            for (z1, a1), (z2, a2) in zip(self.cont, self.cont[1:]):
                self.cum.append(self.cum[-1] + (z2 - z1) * (a1 + math.sqrt(a1 * a2) + a2) / 3)
        self.fore = rec["cell"] == "forebay"
        if self.fore:
            d = rec["divider"]
            o = d["orifice"]
            dia = o["diameter_in"] / 12
            self.into = d["drains_into"]
            self.w_crest, self.w_len, self.w_c = d["weir_crest_elevation_ft"], d["weir_length_ft"], d["weir_coefficient"]
            self.d_area, self.d_cent, self.d_c = math.pi * dia ** 2 / 4, o["invert_elevation_ft"] + dia / 2, o["discharge_coefficient"]
            self.down = None
            self.crest = None
        else:
            o, rr, sp = rec["dewatering_orifice"], rec["riser"], rec["emergency_spillway"]
            dia = o["diameter_in"] / 12
            self.o_area, self.o_cent, self.o_c = math.pi * dia ** 2 / 4, o["invert_elevation_ft"] + dia / 2, o["discharge_coefficient"]
            self.r_crest, self.r_d = rr["crest_elevation_ft"], rr["diameter_ft"]
            self.r_cw, self.r_co = rr["weir_coefficient"], rr["orifice_coefficient"]
            self.crest, self.s_len, self.s_cw = sp["crest_elevation_ft"], sp["crest_length_ft"], sp["weir_coefficient"]
            self.down = rec["discharges_to"]

    def volume(self, h):
        if h <= self.bottom:
            return 0.0
        if self.trap:
            L, W, Z = self.trap
            D = h - self.bottom
            return L * W * D + (L + W) * Z * D * D + 4 / 3 * Z * Z * D ** 3
        i = bisect.bisect_right([z for z, _ in self.cont], h) - 1
        if i >= len(self.cont) - 1:
            z, a = self.cont[-1]
            return self.cum[-1] + (h - z) * a
        (z1, a1), (z2, a2) = self.cont[i], self.cont[i + 1]
        a = a1 + (a2 - a1) * (h - z1) / (z2 - z1)
        return self.cum[i] + (h - z1) * (a1 + math.sqrt(a1 * a) + a) / 3

    def outflow(self, h):                               # main cells: (total, spillway part)
        q = orifice_flow(self.o_c, self.o_area, self.o_cent, h)
        hr = h - self.r_crest
        if hr > 0:
            q += min(self.r_cw * G2 * math.pi * self.r_d * hr ** 1.5,
                     self.r_co * math.pi * self.r_d ** 2 / 4 * G2 * math.sqrt(hr))
        hs = h - self.crest
        spill = self.s_cw * G2 * self.s_len * hs ** 1.5 if hs > 0 else 0.0
        return q + spill, spill

    def divider(self, hf, hm):                          # forebay cells: flow toward the main cell
        up, dn, sign = (hf, hm, 1.0) if hf >= hm else (hm, hf, -1.0)
        q = 0.0
        h1 = up - self.w_crest
        if h1 > 0:
            q = self.w_c * G2 * self.w_len * h1 ** 1.5
            h2 = dn - self.w_crest
            if h2 > 0:
                q *= (1 - (h2 / h1) ** 1.5) ** 0.385
        q += orifice_flow(self.d_c, self.d_area, self.d_cent, up, dn)
        return sign * q


def solve_increasing(f, lo, guess):
    """Root of an increasing function f on [lo, inf): find a bracket, then Newton steps with a numerical slope,
    halving the bracket whenever a Newton step leaves it or fails to halve the residual."""
    if f(lo) >= 0:
        return lo
    a = lo
    b = max(guess, lo) + 0.05
    while f(b) < 0:
        a, b = b, b + 2 * (b - lo) + 0.05
    x = min(max(guess, a), b)
    fx = f(x)
    for _ in range(300):
        if fx > 0:
            b = x
        else:
            a = x
        if b - a < 1e-11 or fx == 0:
            return x
        eps = 1e-8
        slope = (f(x + eps) - fx) / eps
        nxt = x - fx / slope if slope > 0 else None
        if nxt is None or not a < nxt < b:
            nxt = (a + b) / 2
        fn = f(nxt)
        if abs(fn) > 0.5 * abs(fx):                     # slow progress: bisect instead
            mid = (a + b) / 2
            if fn > 0:
                b = min(b, nxt)
            else:
                a = max(a, nxt)
            nxt = (a + b) / 2 if not a < mid < b else mid
            fn = f(nxt)
        x, fx = nxt, fn
    return x


def main():
    sites = json.loads((DATA / "sites.json").read_text())
    rain = defaultdict(dict)
    for r in json.loads((DATA / "rain_gauge.json").read_text()):
        rain[r["site_id"]][idx(r["interval_start"])] = float(r["rain_in"])
    states = defaultdict(list)
    for r in json.loads((DATA / "area_states.json").read_text()):
        states[r["area_id"]].append((idx(r["effective_date"] + "T00:00"), r["state"]))
    rows = []
    for site in sites:
        rows += run_site(site, rain[site["site_id"]], states)
    rows.sort(key=lambda r: (r[0], r[1], r[2]))
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "basin_storms.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["site_id", "basin_id", "storm_start", "peak_inflow_cfs", "peak_outflow_cfs", "peak_stage_ft",
                    "time_of_peak_stage", "spillway_flow", "spill_volume_cf"])
        w.writerows(rows)


def run_site(site, rain, states):
    storms = []
    for i in sorted(k for k, v in rain.items() if v > 0):
        if storms and i - storms[-1][-1] <= 60:
            storms[-1].append(i)
        else:
            storms.append([i])
    cells = {b["basin_id"]: Cell(b) for b in site["basins"]}
    local = {c: [0.0] * (N + 1) for c in cells}
    p2 = site["two_year_24_hour_rainfall_in"]
    for a in site["drainage_areas"]:
        uh = {}
        for state, surface in a["sheet_flow_surface"].items():
            tp = DD / 2 + 0.6 * time_of_concentration(a["flow_path"], surface, p2)
            qp = 484 * a["acres"] / 640 / tp
            uh[state] = [qp * ratio(j * DD / tp) for j in range(int(5 * tp / DD) + 2)]
        hydro = local[a["drains_to"]]
        hist = sorted(states[a["area_id"]])
        for storm in storms:
            state = [s for k, s in hist if k <= storm[0]][-1]
            cn, u = a["curve_numbers"][state], uh[state]
            p = prev = 0.0
            for i in range(storm[0], storm[-1] + 1):
                p += rain.get(i, 0.0)
                q = accumulated_runoff(p, cn)
                excess, prev = q - prev, q
                if excess > 0:
                    for j, uj in enumerate(u):
                        if i + j <= N:
                            hydro[i + j] += excess * uj
    fore_of = {c.into: c for c in cells.values() if c.fore}
    free_in = {c: [0.0] * (N + 1) for c in cells}
    series = {}
    remaining = [c for c in cells.values() if not c.fore]
    while remaining:
        m = next(c for c in remaining if not any(o.down == c.id for o in remaining if o is not c))
        remaining.remove(m)
        Im = [x + y for x, y in zip(local[m.id], free_in[m.id])]
        Hm, Om, Sm = [m.bottom] * (N + 1), [0.0] * (N + 1), [0.0] * (N + 1)
        f = fore_of.get(m.id)
        if f is None:
            h, s, o = m.bottom, 0.0, 0.0
            for k in range(N):
                if Im[k] == 0 and Im[k + 1] == 0 and o == 0:
                    Hm[k + 1] = h
                    continue
                target = (Im[k] + Im[k + 1]) / 2 + s / DT - o / 2
                h = solve_increasing(lambda x: m.volume(x) / DT + m.outflow(x)[0] / 2 - target, m.bottom, h)
                s = m.volume(h)
                o, sp = m.outflow(h)
                Hm[k + 1], Om[k + 1], Sm[k + 1] = h, o, sp
        else:
            If = local[f.id]
            Hf, Df = [f.bottom] * (N + 1), [0.0] * (N + 1)
            hf, hm, d, o = f.bottom, m.bottom, 0.0, 0.0
            for k in range(N):
                if If[k] == If[k + 1] == Im[k] == Im[k + 1] == 0 and d == 0 and o == 0:
                    Hf[k + 1], Hm[k + 1] = hf, hm
                    continue
                tf = (If[k] + If[k + 1]) / 2 + f.volume(hf) / DT - d / 2
                tm = (Im[k] + Im[k + 1]) / 2 + m.volume(hm) / DT + d / 2 - o / 2
                guess_f = hf

                def fore_level(x):
                    return solve_increasing(lambda y: f.volume(y) / DT + f.divider(y, x) / 2 - tf, f.bottom, guess_f)

                def main_balance(x):
                    y = fore_level(x)
                    return m.volume(x) / DT - f.divider(y, x) / 2 + m.outflow(x)[0] / 2 - tm

                hm = solve_increasing(main_balance, m.bottom, hm)
                hf = fore_level(hm)
                d = f.divider(hf, hm)
                o, sp = m.outflow(hm)
                Hf[k + 1], Hm[k + 1], Df[k + 1], Om[k + 1], Sm[k + 1] = hf, hm, d, o, sp
            series[f.id] = (If, Df, Hf, [0.0] * (N + 1))
            Im = [x + y for x, y in zip(Im, Df)]
        series[m.id] = (Im, Om, Hm, Sm)
        if m.down:
            free_in[m.down] = [x + y for x, y in zip(free_in[m.down], Om)]
    out = []
    for cid, c in cells.items():
        I, O, H, S = series[cid]
        for n, storm in enumerate(storms):
            end = storms[n + 1][0] if n + 1 < len(storms) else N + 1
            window = range(storm[0], end)
            top = max(H[k] for k in window)
            when = next(k for k in window if H[k] == top)
            spill = c.crest is not None and top > c.crest
            out.append([site["site_id"], cid, stamp(storm[0]), f"{max(I[k] for k in window):.3f}",
                        f"{max(O[k] for k in window):.3f}", f"{top:.3f}", stamp(when), "yes" if spill else "no",
                        f"{sum(S[k] for k in window) * DT:.3f}"])
    return out


if __name__ == "__main__":
    main()
