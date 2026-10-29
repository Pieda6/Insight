"""Verifier-side model for sediment-basin-routing, written independently of the reference solution.

Differences in method: storms are found with itertools.groupby over gaps; the rainfall excess of each area is a
per-storm list and the basin hydrograph is gathered point by point (sum over earlier excess values) instead of
scattered; the dimensionless unit hydrograph is a dict of segments; each routing step is solved by the Illinois
variant of regula falsi on a bracket. Reads only the verifier's private copy of the data.
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
TABLE16_1 = {0.0: .000, 0.1: .030, 0.2: .100, 0.3: .190, 0.4: .310, 0.5: .470, 0.6: .660, 0.7: .820, 0.8: .930,
             0.9: .990, 1.0: 1.000, 1.1: .990, 1.2: .930, 1.3: .860, 1.4: .780, 1.5: .680, 1.6: .560, 1.7: .460,
             1.8: .390, 1.9: .330, 2.0: .280, 2.2: .207, 2.4: .147, 2.6: .107, 2.8: .077, 3.0: .055, 3.2: .040,
             3.4: .029, 3.6: .021, 3.8: .015, 4.0: .011, 4.5: .005, 5.0: .000}
KNOTS = sorted(TABLE16_1)


def point(s):
    t = datetime.strptime(s, "%Y-%m-%dT%H:%M")
    return int(round((t - ORIGIN).total_seconds() / 60)) // 6


def label(p):
    m = p * 6
    d, rem = divmod(m, 1440)
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


def orifice_q(c, diameter_ft, head_above_centroid):
    return c * math.pi / 4 * diameter_ft ** 2 * G2 * math.sqrt(head_above_centroid) if head_above_centroid > 0 else 0.0


def riser_q(cw, co, weir_len, diameter_ft, head):
    if head <= 0:
        return 0.0
    return min(cw * G2 * weir_len * head ** 1.5, orifice_q(co, diameter_ft, head))


def trapezoid_volume(L, W, Z, D):
    return L * W * D + (L + W) * Z * D * D + 4.0 * Z * Z * D ** 3 / 3.0 if D > 0 else 0.0


class Pond:
    def __init__(self, b):
        self.b = b
        self.bottom = b["bottom_elevation_ft"]
        o = b["dewatering_orifice"]
        self.od = o["diameter_in"] / 12.0
        self.oc = o["invert_elevation_ft"] + self.od / 2

    def S(self, h):
        b = self.b
        return trapezoid_volume(b["bottom_length_ft"], b["bottom_width_ft"], b["side_slope_h_per_v"], h - self.bottom)

    def Q(self, h):
        b, r, s = self.b, self.b["riser"], self.b["emergency_spillway"]
        q = orifice_q(b["dewatering_orifice"]["discharge_coefficient"], self.od, h - self.oc)
        q += riser_q(r["weir_coefficient"], r["orifice_coefficient"], math.pi * r["diameter_ft"], r["diameter_ft"],
                     h - r["crest_elevation_ft"])
        hs = h - s["crest_elevation_ft"]
        if hs > 0:
            q += s["weir_coefficient"] * G2 * s["crest_length_ft"] * hs ** 1.5
        return q

    def solve(self, n):
        if n <= 0:
            return self.bottom
        f = lambda h: self.S(h) / DT + self.Q(h) / 2 - n  # noqa: E731
        a, b = self.bottom, self.bottom + 1.0
        while f(b) < 0:
            a, b = b, b + 1.0
        fa, fb, side = f(a), f(b), 0
        for _ in range(300):
            c = (a * fb - b * fa) / (fb - fa)
            fc = f(c)
            if abs(fc) < 1e-12 * max(1.0, n) or b - a < 1e-11:
                return c
            if fc * fb > 0:
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


def expected(full=False):
    """Rows [site, basin, storm_start, peak_in, peak_out, peak_stage, spill]; with full=True each row also carries
    the stage at the storm's first time point (used by the tests to pick out storms that began with water left
    from earlier storms)."""
    sites = json.loads((DATA / "sites.json").read_text())
    gauge = defaultdict(dict)
    for r in json.loads((DATA / "rain_gauge.json").read_text()):
        gauge[r["site_id"]][point(r["interval_start"])] = int(r["rain_in"].replace(".", ""))
    hist = defaultdict(list)
    for r in json.loads((DATA / "area_states.json").read_text()):
        hist[r["area_id"]].append((point(r["effective_date"] + "T00:00"), r["state"]))
    rows = []
    for site in sites:
        rows += site_rows(site, gauge[site["site_id"]], hist)
    rows.sort(key=lambda r: (r[0], r[1], r[2]))
    return rows if full else [r[:7] for r in rows]


def site_rows(site, gauge, hist):
    wet = sorted(p for p, v in gauge.items() if v > 0)
    groups, g = [], []
    for p in wet:
        if g and p - g[-1] - 1 >= 60:
            groups.append(g)
            g = []
        g.append(p)
    if g:
        groups.append(g)
    starts = [x[0] for x in groups]
    # rainfall excess per area: list of (point, excess)
    hydro = defaultdict(lambda: [0.0] * POINTS)
    for a in site["drainage_areas"]:
        tp = time_to_peak(a["time_of_concentration_h"])
        qp = peak_rate(a["acres"] / 640.0, a["time_of_concentration_h"])
        span = int(math.ceil(5 * tp / 0.1))
        u = [qp * q_over_qp(0.1 * j / tp) for j in range(span + 1)]
        exc = {}
        changes = sorted(hist[a["area_id"]])
        for grp in groups:
            cn = a["curve_numbers"][max((c for c in changes if c[0] <= grp[0]), key=lambda c: c[0])[1]]
            total = 0
            last = 0.0
            for p in range(grp[0], grp[-1] + 1):
                total += gauge.get(p, 0)
                q = runoff_in(total / 100.0, cn)
                if q - last > 0:
                    exc[p] = q - last
                last = q
        series = hydro[a["drains_to"]]
        keys = sorted(exc)
        for p in keys:                       # gather by output point over the support of this excess
            for n in range(p, min(POINTS, p + span + 1)):
                series[n] += exc[p] * u[n - p]
    ponds = {b["basin_id"]: Pond(b) for b in site["basins"]}
    inflow = {bid: list(hydro[bid]) if bid in hydro else [0.0] * POINTS for bid in ponds}
    levels, outs = {}, {}
    order = []
    while len(order) < len(ponds):
        for bid, pond in sorted(ponds.items()):
            if bid in order:
                continue
            if all(x in order for x, p in ponds.items() if p.b["discharges_to"] == bid):
                order.append(bid)
    for bid in order:
        pond = ponds[bid]
        I = list(inflow[bid])
        for x, p in ponds.items():
            if p.b["discharges_to"] == bid:
                I = [a + b for a, b in zip(I, outs[x])]
        inflow[bid] = I
        H, O = [pond.bottom], [0.0]
        for n in range(1, POINTS):
            if I[n - 1] == 0.0 and I[n] == 0.0 and O[-1] == 0.0:
                H.append(H[-1])
                O.append(0.0)
                continue
            target = (I[n - 1] + I[n]) / 2 + pond.S(H[-1]) / DT - O[-1] / 2
            h = pond.solve(target)
            H.append(h)
            O.append(pond.Q(h))
        levels[bid], outs[bid] = H, O
    rows = []
    for bid, pond in ponds.items():
        crest = pond.b["emergency_spillway"]["crest_elevation_ft"]
        for i, s in enumerate(starts):
            e = starts[i + 1] if i + 1 < len(starts) else POINTS
            hmax = max(levels[bid][s:e])
            rows.append([site["site_id"], bid, label(s), max(inflow[bid][s:e]), max(outs[bid][s:e]), hmax,
                         "yes" if hmax > crest else "no", levels[bid][s]])
    return rows
