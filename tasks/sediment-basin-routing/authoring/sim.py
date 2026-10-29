"""Generator-side model for sediment-basin-routing (authoring tool; the third implementation).

Everything runs on a grid of 6-minute time points k = 0 .. END_K from 2026-04-01 00:00 (k = END_K is the end of
September 30, 2026). Interval k is the 6 minutes from point k to point k + 1.

Methods (texts in sources/): NRCS curve number runoff with accumulated storm rain (NEH 630.10, eq. 10-11 and
example 10-6), NRCS dimensionless unit hydrograph (NEH 630.16, table 16-1, Tp = dD/2 + L, L = 0.6 Tc,
qp = 484 A Q / Tp), trapezoidal stage-storage (HEC-22 eq. 10.10), orifice / riser / broad-crested weir ratings
(HEC-22 eqs. 10.23 and 10.32, example 10.11, table 10.10), storage-indication routing (NEH 630.17 eq. 17-3,
HEC-22 eq. 10.45) solved on the continuous relations.
"""
import math

DT_H = 0.1
DT_S = 360.0
END_K = 183 * 240
GAP = 60                      # 6 hours of dry intervals start a new storm
G = 32.2
DUH = [(0.0, 0.0), (0.1, .030), (0.2, .100), (0.3, .190), (0.4, .310), (0.5, .470), (0.6, .660), (0.7, .820),
       (0.8, .930), (0.9, .990), (1.0, 1.000), (1.1, .990), (1.2, .930), (1.3, .860), (1.4, .780), (1.5, .680),
       (1.6, .560), (1.7, .460), (1.8, .390), (1.9, .330), (2.0, .280), (2.2, .207), (2.4, .147), (2.6, .107),
       (2.8, .077), (3.0, .055), (3.2, .040), (3.4, .029), (3.6, .021), (3.8, .015), (4.0, .011), (4.5, .005),
       (5.0, .000)]


def duh(x):
    if x <= 0 or x >= 5.0:
        return 0.0
    for (x0, y0), (x1, y1) in zip(DUH, DUH[1:]):
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return 0.0


def runoff(p, cn):
    s = 1000.0 / cn - 10.0
    return (p - 0.2 * s) ** 2 / (p + 0.8 * s) if p > 0.2 * s else 0.0


def unit_hydrograph(acres, tc):
    tp = DT_H / 2 + 0.6 * tc
    qp = 484.0 * (acres / 640.0) / tp
    out, j = [], 0
    while j * DT_H < 5.0 * tp + 1e-9:
        out.append(qp * duh(j * DT_H / tp))
        j += 1
    return out


def storms(rain):
    """rain: {k: hundredths}. Returns list of (start_k, [wet ks])."""
    out = []
    for k in sorted(rain):
        if rain[k] <= 0:
            continue
        if out and k - out[-1][1][-1] - 1 < GAP:
            out[-1][1].append(k)
        else:
            out.append((k, [k]))
    return out


def state_at(changes, k):
    """changes: sorted list of (k_from, state)."""
    st = changes[0][1]
    for kk, s in changes:
        if kk <= k:
            st = s
    return st


def storage(b, h):
    d = h - b["bottom"]
    if d <= 0:
        return 0.0
    L, W, Z = b["L"], b["W"], b["Z"]
    return L * W * d + (L + W) * Z * d * d + 4.0 / 3.0 * Z * Z * d ** 3


def outflow(b, h, parts=False):
    q_o = q_r = q_s = 0.0
    dia = b["orifice_d_in"] / 12.0
    ho = h - (b["orifice_inv"] + dia / 2)
    if ho > 0:
        q_o = b["orifice_c"] * math.pi * dia * dia / 4 * math.sqrt(2 * G * ho)
    hr = h - b["riser_crest"]
    if hr > 0:
        weir = b["riser_cw"] * math.sqrt(2 * G) * math.pi * b["riser_d"] * hr ** 1.5
        orif = b["riser_co"] * math.pi * b["riser_d"] ** 2 / 4 * math.sqrt(2 * G * hr)
        q_r = min(weir, orif)
    hs = h - b["spill_crest"]
    if hs > 0:
        q_s = b["spill_cw"] * math.sqrt(2 * G) * b["spill_L"] * hs ** 1.5
    if parts:
        return q_o, q_r, q_s
    return q_o + q_r + q_s


def solve_stage(b, rhs, guess):
    """Find h with storage(h)/dt + outflow(h)/2 = rhs (monotonic in h), by bisection to 1e-10 ft."""
    lo = b["bottom"]
    if rhs <= 0:
        return lo
    hi = max(guess, lo) + 0.5
    while storage(b, hi) / DT_S + outflow(b, hi) / 2 < rhs:
        hi += 1.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if storage(b, mid) / DT_S + outflow(b, mid) / 2 < rhs:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-10:
            break
    return (lo + hi) / 2


def simulate(site, rain, area_changes):
    """site: {"areas": [...], "basins": [...]} with parsed numbers. Returns rows and traces."""
    st = storms(rain)
    flows = {b["id"]: [0.0] * (END_K + 1) for b in site["basins"]}
    for a in site["areas"]:
        uh = unit_hydrograph(a["acres"], a["tc"])
        q = flows[a["basin"]]
        for start, wet in st:
            cn = a["cn"][state_at(area_changes[a["id"]], start)]
            cum, prev = 0.0, 0.0
            for k in range(start, wet[-1] + 1):
                cum += rain.get(k, 0) / 100.0
                now = runoff(cum, cn)
                dq = now - prev
                prev = now
                if dq <= 0:
                    continue
                for j, u in enumerate(uh):
                    if k + j > END_K:
                        break
                    q[k + j] += dq * u
    order, done = [], set()
    while len(order) < len(site["basins"]):
        for b in site["basins"]:
            ups = [x for x in site["basins"] if x["down"] == b["id"]]
            if b["id"] not in done and all(u["id"] in done for u in ups):
                order.append(b)
                done.add(b["id"])
    trace = {}
    for b in order:
        inflow = list(flows[b["id"]])
        for u in site["basins"]:
            if u["down"] == b["id"]:
                inflow = [x + y for x, y in zip(inflow, trace[u["id"]]["O"])]
        H = [b["bottom"]] * (END_K + 1)
        O = [0.0] * (END_K + 1)
        h, s, o = b["bottom"], 0.0, 0.0
        for k in range(END_K):
            i1, i2 = inflow[k], inflow[k + 1]
            if i1 == 0 and i2 == 0 and o == 0:
                H[k + 1], O[k + 1] = h, 0.0
                continue
            rhs = (i1 + i2) / 2 + s / DT_S - o / 2
            h = solve_stage(b, rhs, h)
            s, o = storage(b, h), outflow(b, h)
            H[k + 1], O[k + 1] = h, o
        trace[b["id"]] = {"I": inflow, "O": O, "H": H}
        if b["id"] in flows:
            flows[b["id"]] = inflow
    rows = []
    for b in site["basins"]:
        tr = trace[b["id"]]
        for n, (start, wet) in enumerate(st):
            stop = st[n + 1][0] if n + 1 < len(st) else END_K + 1
            ks = range(start, stop)
            ph = max(tr["H"][k] for k in ks)
            rows.append({"basin": b["id"], "start": start, "peak_in": max(tr["I"][k] for k in ks),
                         "peak_out": max(tr["O"][k] for k in ks), "peak_stage": ph,
                         "spill": ph > b["spill_crest"], "margin": ph - b["spill_crest"]})
    return rows, trace, st
