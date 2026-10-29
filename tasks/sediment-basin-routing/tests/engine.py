"""Verifier-side model for sediment-basin-routing, written independently of the reference solution.

Differences in method: storms are found by scanning gaps; each area's unit hydrographs are built per state from a
dict of table 16-1 segments; basin hydrographs are gathered point by point; contour storage is accumulated from a
precomputed list of conic slices; each routing step is solved with the Illinois variant of regula falsi (nested
for a forebay and its main cell). Reads only the verifier's private copy of the data.
"""
import json
import math
from collections import defaultdict
from datetime import datetime
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
ORIGIN = datetime(2026, 4, 1)
POINTS = 183 * 240 + 1
DT = 6 * 60.0
G2 = math.sqrt(2 * 32.2)
TABLE3_1 = {"Smooth surfaces (concrete, asphalt, gravel, or bare soil)": 0.011, "Fallow (no residue)": 0.05,
            "Cultivated soils: residue cover <=20%": 0.06, "Cultivated soils: residue cover >20%": 0.17,
            "Grass: short grass prairie": 0.15, "Grass: dense grasses": 0.24, "Grass: Bermudagrass": 0.41,
            "Range (natural)": 0.13, "Woods: light underbrush": 0.40, "Woods: dense underbrush": 0.80}
TABLE16_1 = {0.0: .000, 0.1: .030, 0.2: .100, 0.3: .190, 0.4: .310, 0.5: .470, 0.6: .660, 0.7: .820, 0.8: .930,
             0.9: .990, 1.0: 1.000, 1.1: .990, 1.2: .930, 1.3: .860, 1.4: .780, 1.5: .680, 1.6: .560, 1.7: .460,
             1.8: .390, 1.9: .330, 2.0: .280, 2.2: .207, 2.4: .147, 2.6: .107, 2.8: .077, 3.0: .055, 3.2: .040,
             3.4: .029, 3.6: .021, 3.8: .015, 4.0: .011, 4.5: .005, 5.0: .000}
KNOTS = sorted(TABLE16_1)


def point(s):
    t = datetime.strptime(s, "%Y-%m-%dT%H:%M")
    return int(round((t - ORIGIN).total_seconds() / 60)) // 6


def label(p):
    d, rem = divmod(p * 6, 1440)
    t = datetime.fromordinal(ORIGIN.toordinal() + d)
    return f"{t:%Y-%m-%d}T{rem // 60:02d}:{rem % 60:02d}"


def q_over_qp(x):
    if not 0 < x < 5:
        return 0.0
    for a, b in zip(KNOTS, KNOTS[1:]):
        if a <= x <= b:
            return TABLE16_1[a] + (x - a) / (b - a) * (TABLE16_1[b] - TABLE16_1[a])
    return 0.0


# ---- functions also used by the tests on published worked examples
def runoff_in(p, cn):
    s = 1000.0 / cn - 10.0
    return max(0.0, p - 0.2 * s) ** 2 / (p + 0.8 * s) if p > 0.2 * s else 0.0


def time_to_peak(tc, dd=0.1):
    return dd / 2.0 + 0.6 * tc


def peak_rate(sq_mi, tc, dd=0.1):
    return 484.0 * sq_mi / time_to_peak(tc, dd)


def tc_tr55(path, surface, p2, apply_minimum=True):
    segs = []
    s = path["sheet"]
    segs.append(0.007 * (TABLE3_1[surface] * s["length_ft"]) ** 0.8 / (p2 ** 0.5 * s["slope"] ** 0.4))
    c = path["shallow"]
    k = 20.3282 if c["paved"] else 16.1345
    segs.append(c["length_ft"] / 3600.0 / (k * c["slope"] ** 0.5))
    if path.get("channel"):
        ch = path["channel"]
        r = ch["area_sqft"] / ch["wetted_perimeter_ft"]
        segs.append(ch["length_ft"] / 3600.0 / (1.49 * r ** (2.0 / 3.0) * ch["slope"] ** 0.5 / ch["n"]))
    t = sum(segs)
    return max(0.1, t) if apply_minimum else t


def orifice_q(c, diameter_ft, head):
    return c * math.pi / 4 * diameter_ft ** 2 * G2 * math.sqrt(head) if head > 0 else 0.0


def riser_q(cw, co, weir_len, diameter_ft, head):
    if head <= 0:
        return 0.0
    return min(cw * G2 * weir_len * head ** 1.5, orifice_q(co, diameter_ft, head))


def trapezoid_volume(L, W, Z, D):
    return L * W * D + (L + W) * Z * D * D + 4.0 * Z * Z * D ** 3 / 3.0 if D > 0 else 0.0


def conic(a1, a2, d):
    return d / 3.0 * (a1 + a2 + math.sqrt(a1 * a2))


def villemonte(h1, h2):
    return (1 - (h2 / h1) ** 1.5) ** 0.385 if h2 > 0 else 1.0


def illinois(f, a, b):
    """Root of increasing f with f(a) < 0 < f(b)."""
    fa, fb, side = f(a), f(b), 0
    c = a
    for _ in range(400):
        c = (a * fb - b * fa) / (fb - fa)
        fc = f(c)
        if abs(fc) < 1e-13 or b - a < 1e-11:
            return c
        if fc > 0:
            b, fb = c, fc
            if side == -1:
                fa /= 2
            side = -1
        else:
            a, fa = c, fc
            if side == 1:
                fb /= 2
            side = 1
    return c


def root(f, lo):
    if f(lo) >= 0:
        return lo
    hi = lo + 1.0
    while f(hi) <= 0:
        lo, hi = hi, hi + 1.0
    return illinois(f, lo, hi)


def pair_step(F, M, cf, cm, gf, gm):
    """Solve the forebay and main-cell equations together: 2-D Newton from the previous levels (finite-difference
    Jacobian), falling back to nested regula falsi when Newton does not settle inside the cells."""
    def res(hf, hm):
        d = F.D(hf, hm)
        return F.S(hf) / DT + d / 2 - cf, M.S(hm) / DT - d / 2 + M.Q(hm)[0] / 2 - cm

    hf, hm = max(gf, F.z0), max(gm, M.z0)
    for _ in range(40):
        r1, r2 = res(hf, hm)
        if abs(r1) < 1e-10 and abs(r2) < 1e-10:
            if hf >= F.z0 and hm >= M.z0:
                return hf, hm
            break
        e = 1e-7
        a1, a2 = res(hf + e, hm)
        b1, b2 = res(hf, hm + e)
        j11, j21, j12, j22 = (a1 - r1) / e, (a2 - r2) / e, (b1 - r1) / e, (b2 - r2) / e
        det = j11 * j22 - j12 * j21
        if det == 0:
            break
        dhf = (-r1 * j22 + r2 * j12) / det
        dhm = (-r2 * j11 + r1 * j21) / det
        if abs(dhf) > 0.5 or abs(dhm) > 0.5:
            break
        hf, hm = hf + dhf, hm + dhm
        if hf < F.z0 - 1e-9 or hm < M.z0 - 1e-9:
            break
    def fore(x):
        return root(lambda y: F.S(y) / DT + F.D(y, x) / 2 - cf, F.z0)
    hm = root(lambda x: M.S(x) / DT - F.D(fore(x), x) / 2 + M.Q(x)[0] / 2 - cm, M.z0)
    return fore(hm), hm


class Cell:
    def __init__(self, rec):
        self.rec = rec
        g = rec["geometry"]
        if g["type"] == "trapezoid":
            self.z0 = g["bottom_elevation_ft"]
            self.slices = None
        else:
            pts = [(c["elevation_ft"], c["area_sqft"]) for c in g["contours"]]
            self.z0 = pts[0][0]
            self.slices, acc = [], 0.0
            for (z1, a1), (z2, a2) in zip(pts, pts[1:]):
                self.slices.append((z1, z2, a1, a2, acc))
                acc += conic(a1, a2, z2 - z1)

    def S(self, h):
        if h <= self.z0:
            return 0.0
        g = self.rec["geometry"]
        if self.slices is None:
            return trapezoid_volume(g["bottom_length_ft"], g["bottom_width_ft"], g["side_slope_h_per_v"], h - self.z0)
        for z1, z2, a1, a2, acc in self.slices:
            if h <= z2:
                return acc + conic(a1, a1 + (a2 - a1) * (h - z1) / (z2 - z1), h - z1)
        z1, z2, a1, a2, acc = self.slices[-1]
        return acc + conic(a1, a2, z2 - z1) + (h - z2) * a2

    def Q(self, h):
        """Main cell: (total outflow, spillway flow)."""
        r = self.rec
        o, ri, sp = r["dewatering_orifice"], r["riser"], r["emergency_spillway"]
        d = o["diameter_in"] / 12.0
        q = orifice_q(o["discharge_coefficient"], d, h - o["invert_elevation_ft"] - d / 2)
        q += riser_q(ri["weir_coefficient"], ri["orifice_coefficient"], math.pi * ri["diameter_ft"], ri["diameter_ft"],
                     h - ri["crest_elevation_ft"])
        hs = h - sp["crest_elevation_ft"]
        s = sp["weir_coefficient"] * G2 * sp["crest_length_ft"] * hs ** 1.5 if hs > 0 else 0.0
        return q + s, s

    def D(self, hf, hm):
        """Forebay divider flow toward the main cell (negative back into the forebay)."""
        dv = self.rec["divider"]
        hi, lo = max(hf, hm), min(hf, hm)
        q = 0.0
        if hi > dv["weir_crest_elevation_ft"]:
            q = dv["weir_coefficient"] * G2 * dv["weir_length_ft"] * (hi - dv["weir_crest_elevation_ft"]) ** 1.5 * \
                villemonte(hi - dv["weir_crest_elevation_ft"], lo - dv["weir_crest_elevation_ft"])
        o = dv["orifice"]
        d = o["diameter_in"] / 12.0
        cen = o["invert_elevation_ft"] + d / 2
        q += orifice_q(o["discharge_coefficient"], d, hi - max(lo, cen))
        return q if hf >= hm else -q


def expected(full=False):
    """Rows [site, basin, storm_start, peak_in, peak_out, peak_stage, time_of_peak, spill, spill_volume]; with
    full=True each row also carries the stage at the storm's first point and the set of time labels within
    0.0005 ft of the peak stage (the tests accept any of them as the time of the peak)."""
    sites = json.loads((DATA / "sites.json").read_text())
    gauge = defaultdict(dict)
    for r in json.loads((DATA / "rain_gauge.json").read_text()):
        gauge[r["site_id"]][point(r["interval_start"])] = int(round(float(r["rain_in"]) * 100))
    hist = defaultdict(list)
    for r in json.loads((DATA / "area_states.json").read_text()):
        hist[r["area_id"]].append((point(r["effective_date"] + "T00:00"), r["state"]))
    rows = []
    for site in sites:
        rows += site_rows(site, gauge[site["site_id"]], hist)
    rows.sort(key=lambda r: (r[0], r[1], r[2]))
    return rows if full else [r[:9] for r in rows]


def site_rows(site, gauge, hist):
    groups = []
    for p in sorted(p for p, v in gauge.items() if v > 0):
        if groups and p - groups[-1][-1] - 1 < 60:
            groups[-1].append(p)
        else:
            groups.append([p])
    starts = [g[0] for g in groups]
    hydro = defaultdict(lambda: [0.0] * POINTS)
    p2 = site["two_year_24_hour_rainfall_in"]
    for a in site["drainage_areas"]:
        uhs = {}
        for state, surface in a["sheet_flow_surface"].items():
            tc = tc_tr55(a["flow_path"], surface, p2)
            tp, qp = time_to_peak(tc), peak_rate(a["acres"] / 640.0, tc)
            uhs[state] = [qp * q_over_qp(0.1 * j / tp) for j in range(int(math.ceil(5 * tp / 0.1)) + 1)]
        changes = sorted(hist[a["area_id"]])
        exc = {}
        for grp in groups:
            state = max((c for c in changes if c[0] <= grp[0]), key=lambda c: c[0])[1]
            cn = a["curve_numbers"][state]
            total, last = 0, 0.0
            for p in range(grp[0], grp[-1] + 1):
                total += gauge.get(p, 0)
                q = runoff_in(total / 100.0, cn)
                if q - last > 0:
                    exc[p] = (q - last, state)
                last = q
        series = hydro[a["drains_to"]]
        for p, (x, state) in exc.items():
            u = uhs[state]
            for n in range(p, min(POINTS, p + len(u))):
                series[n] += x * u[n - p]
    cells = {b["basin_id"]: Cell(b) for b in site["basins"]}
    forebay = {b["divider"]["drains_into"]: b["basin_id"] for b in site["basins"] if b["cell"] == "forebay"}
    mains = [b for b in site["basins"] if b["cell"] == "main"]
    inflow = {bid: list(hydro[bid]) if bid in hydro else [0.0] * POINTS for bid in cells}
    level, out, spill = {}, {}, {}
    order = []
    while len(order) < len(mains):
        for b in mains:
            if b["basin_id"] not in order and all(u["basin_id"] in order for u in mains
                                                   if u["discharges_to"] == b["basin_id"]):
                order.append(b["basin_id"])
    for mid in order:
        M = cells[mid]
        I = inflow[mid]
        for b in mains:
            if b["discharges_to"] == mid:
                I = [x + y for x, y in zip(I, out[b["basin_id"]])]
        H, O, SP = [M.z0], [0.0], [0.0]
        if mid in forebay:
            fid = forebay[mid]
            F = cells[fid]
            J = inflow[fid]
            HF, DF = [F.z0], [0.0]
            for n in range(1, POINTS):
                if J[n - 1] == J[n] == I[n - 1] == I[n] == 0.0 and DF[-1] == 0.0 and O[-1] == 0.0:
                    H.append(H[-1]); O.append(0.0); SP.append(0.0); HF.append(HF[-1]); DF.append(0.0)  # noqa: E702
                    continue
                cf = (J[n - 1] + J[n]) / 2 + F.S(HF[-1]) / DT - DF[-1] / 2
                cm = (I[n - 1] + I[n]) / 2 + M.S(H[-1]) / DT + DF[-1] / 2 - O[-1] / 2

                hf, hm = pair_step(F, M, cf, cm, HF[-1], H[-1])
                q, s = M.Q(hm)
                H.append(hm); O.append(q); SP.append(s); HF.append(hf); DF.append(F.D(hf, hm))  # noqa: E702
            level[fid], out[fid], spill[fid] = HF, DF, [0.0] * POINTS
            inflow[fid] = J
            I = [x + y for x, y in zip(I, DF)]
        else:
            for n in range(1, POINTS):
                if I[n - 1] == 0.0 and I[n] == 0.0 and O[-1] == 0.0:
                    H.append(H[-1]); O.append(0.0); SP.append(0.0)  # noqa: E702
                    continue
                c = (I[n - 1] + I[n]) / 2 + M.S(H[-1]) / DT - O[-1] / 2
                h = root(lambda x: M.S(x) / DT + M.Q(x)[0] / 2 - c, M.z0)
                q, s = M.Q(h)
                H.append(h); O.append(q); SP.append(s)  # noqa: E702
        inflow[mid], level[mid], out[mid], spill[mid] = I, H, O, SP
    rows = []
    for b in site["basins"]:
        bid = b["basin_id"]
        crest = b["emergency_spillway"]["crest_elevation_ft"] if b["cell"] == "main" else None
        for i, s in enumerate(starts):
            e = starts[i + 1] if i + 1 < len(starts) else POINTS
            seg = level[bid][s:e]
            top = max(seg)
            when = s + seg.index(top)
            near = {label(s + j) for j, v in enumerate(seg) if v >= top - 0.0005}
            rows.append([site["site_id"], bid, label(s), max(inflow[bid][s:e]), max(out[bid][s:e]), top, label(when),
                         "yes" if crest is not None and top > crest else "no", sum(spill[bid][s:e]) * DT,
                         level[bid][s], near])
    return rows
