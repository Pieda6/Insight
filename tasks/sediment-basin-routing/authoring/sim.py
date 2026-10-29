"""Generator-side model for sediment-basin-routing (authoring tool; the third implementation).

Everything runs on a grid of 6-minute time points k = 0 .. END_K from 2026-04-01 00:00 (k = END_K is the end of
September 30, 2026). Interval k is the 6 minutes from point k to point k + 1.

Methods (texts in sources/):
- runoff: NRCS curve number with accumulated storm rain (NEH 630.10 eq. 10-11, example 10-6);
- time of concentration: TR-55 chapter 3 (eqs. 3-1 to 3-4, table 3-1, appendix F, minimum 0.1 h), per state;
- unit hydrograph: NEH 630.16 table 16-1, Tp = dD/2 + 0.6 Tc, qp = 484 A Q / Tp;
- stage-storage: trapezoid (HEC-22 eq. 10.10) or surveyed contours by the conic formula (eq. 10.19) with the
  area at an intermediate stage interpolated linearly between contours;
- outlets: orifice (eq. 10.23, head from the centroid, or the difference of water surfaces when submerged),
  riser weir/orifice (eq. 10.32, example 10.11), broad-crested spillway, all added (table 10.10); a forebay divider
  is a sharp-crested weir (eq. 10.32) with submergence (eq. 10.34) plus an orifice, flowing from the higher to the
  lower water surface;
- routing: storage-indication (NEH 630.17 eq. 17-3, HEC-22 eq. 10.45) with every flow averaged over the step,
  a forebay and its main cell solved together.
"""
import math

DT_H = 0.1
DT_S = 360.0
END_K = 183 * 240
GAP = 60
G = 32.2
G2 = math.sqrt(2 * G)
SHEET_N = {"Smooth surfaces (concrete, asphalt, gravel, or bare soil)": 0.011, "Fallow (no residue)": 0.05,
           "Cultivated soils: residue cover <=20%": 0.06, "Cultivated soils: residue cover >20%": 0.17,
           "Grass: short grass prairie": 0.15, "Grass: dense grasses": 0.24, "Grass: Bermudagrass": 0.41,
           "Range (natural)": 0.13, "Woods: light underbrush": 0.40, "Woods: dense underbrush": 0.80}
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


def tc_hours(path, surface, p2):
    sheet = path["sheet"]
    tt = 0.007 * (SHEET_N[surface] * sheet["length_ft"]) ** 0.8 / (p2 ** 0.5 * sheet["slope"] ** 0.4)
    sh = path["shallow"]
    v = (20.3282 if sh["paved"] else 16.1345) * sh["slope"] ** 0.5
    tt += sh["length_ft"] / (3600 * v)
    ch = path.get("channel")
    if ch:
        r = ch["area_sqft"] / ch["wetted_perimeter_ft"]
        v = 1.49 * r ** (2 / 3) * ch["slope"] ** 0.5 / ch["n"]
        tt += ch["length_ft"] / (3600 * v)
    return max(tt, 0.1)


def unit_hydrograph(acres, tc):
    tp = DT_H / 2 + 0.6 * tc
    qp = 484.0 * (acres / 640.0) / tp
    out, j = [], 0
    while j * DT_H < 5.0 * tp + 1e-9:
        out.append(qp * duh(j * DT_H / tp))
        j += 1
    return out


def storms(rain):
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
    st = changes[0][1]
    for kk, s in changes:
        if kk <= k:
            st = s
    return st


# ---------------------------------------------------------------- stage-storage
def storage(b, h):
    if b["shape"] == "trapezoid":
        d = h - b["bottom"]
        if d <= 0:
            return 0.0
        L, W, Z = b["L"], b["W"], b["Z"]
        return L * W * d + (L + W) * Z * d * d + 4.0 / 3.0 * Z * Z * d ** 3
    cs = b["contours"]
    if h <= cs[0][0]:
        return 0.0
    v = 0.0
    for (z1, a1), (z2, a2) in zip(cs, cs[1:]):
        if h >= z2:
            v += (z2 - z1) * (a1 + math.sqrt(a1 * a2) + a2) / 3
            continue
        a = a1 + (a2 - a1) * (h - z1) / (z2 - z1)
        return v + (h - z1) * (a1 + math.sqrt(a1 * a) + a) / 3
    z1, a1 = cs[-1]
    return v + (h - z1) * a1                                  # above the survey (never reached)


# ---------------------------------------------------------------- outlets
def orifice(c, d_ft, centroid, hu, hd=None):
    head = hu - centroid if hd is None or hd <= centroid else hu - hd
    return c * math.pi * d_ft * d_ft / 4 * G2 * math.sqrt(head) if head > 0 else 0.0


def main_outflow(b, h, parts=False):
    o = b["orifice"]
    d = o["d_in"] / 12.0
    q_o = orifice(o["c"], d, o["inv"] + d / 2, h)
    q_r = 0.0
    hr = h - b["riser_crest"]
    if hr > 0:
        q_r = min(b["riser_cw"] * G2 * math.pi * b["riser_d"] * hr ** 1.5,
                  b["riser_co"] * math.pi * b["riser_d"] ** 2 / 4 * G2 * math.sqrt(hr))
    q_s = 0.0
    hs = h - b["spill_crest"]
    if hs > 0:
        q_s = b["spill_cw"] * G2 * b["spill_L"] * hs ** 1.5
    return (q_o, q_r, q_s) if parts else q_o + q_r + q_s


def divider_flow(dv, h_f, h_m):
    """Flow from forebay to main cell (negative when it runs back into the forebay)."""
    sign, hu, hd = (1.0, h_f, h_m) if h_f >= h_m else (-1.0, h_m, h_f)
    q = 0.0
    h1 = hu - dv["weir_crest"]
    if h1 > 0:
        q = dv["weir_cw"] * G2 * dv["weir_L"] * h1 ** 1.5
        h2 = hd - dv["weir_crest"]
        if h2 > 0:
            q *= (1 - (h2 / h1) ** 1.5) ** 0.385
    o = dv["orifice"]
    d = o["d_in"] / 12.0
    q += orifice(o["c"], d, o["inv"] + d / 2, hu, hd)
    return sign * q


# ---------------------------------------------------------------- routing
def bisect(f, lo, hi, tol=1e-11):
    """f increasing; f(lo) <= 0 <= f(hi)."""
    for _ in range(300):
        mid = (lo + hi) / 2
        if f(mid) < 0:
            lo = mid
        else:
            hi = mid
        if hi - lo < tol:
            break
    return (lo + hi) / 2


def upper(f, lo):
    hi = lo + 0.5
    while f(hi) < 0:
        hi += 1.0
    return hi


def step_single(b, rhs):
    lo = b["bottom"]
    if rhs <= 0:
        return lo
    f = lambda h: storage(b, h) / DT_S + main_outflow(b, h) / 2 - rhs  # noqa: E731
    return bisect(f, lo, upper(f, lo))


def step_pair(F, M, r_f, r_m):
    """Solve S_f(hf)/dt + D(hf,hm)/2 = r_f and S_m(hm)/dt - D(hf,hm)/2 + O(hm)/2 = r_m together."""
    dv = F["divider"]

    def hf_given(hm):
        f = lambda hf: storage(F, hf) / DT_S + divider_flow(dv, hf, hm) / 2 - r_f  # noqa: E731
        lo = F["bottom"]
        if f(lo) >= 0:
            return lo
        return bisect(f, lo, upper(f, lo))

    def g(hm):
        hf = hf_given(hm)
        return storage(M, hm) / DT_S - divider_flow(dv, hf, hm) / 2 + main_outflow(M, hm) / 2 - r_m

    lo = M["bottom"]
    if g(lo) >= 0:
        hm = lo
    else:
        hm = bisect(g, lo, upper(g, lo))
    return hf_given(hm), hm


def simulate(site, rain, area_changes):
    st = storms(rain)
    basins = {b["id"]: b for b in site["basins"]}
    local = {bid: [0.0] * (END_K + 1) for bid in basins}
    for a in site["areas"]:
        uhs = {s: unit_hydrograph(a["acres"], tc_hours(a["path"], a["surface"][s], site["p2"])) for s in a["cn"]}
        q = local[a["basin"]]
        for start, wet in st:
            state = state_at(area_changes[a["id"]], start)
            cn, uh = a["cn"][state], uhs[state]
            cum, prev = 0.0, 0.0
            for k in range(start, wet[-1] + 1):
                cum += rain.get(k, 0) / 100.0
                now = runoff(cum, cn)
                dq, prev = now - prev, now
                if dq <= 0:
                    continue
                for j, u in enumerate(uh):
                    if k + j > END_K:
                        break
                    q[k + j] += dq * u
    # units: a main cell with its forebay(s) is solved together; free outfalls feed downstream units
    fore = {b["divider"]["into"]: b["id"] for b in site["basins"] if b.get("divider")}
    units = [bid for bid, b in basins.items() if not b.get("divider")]
    trace, free_in = {}, {bid: [0.0] * (END_K + 1) for bid in basins}
    done = set()
    while len(done) < len(units):
        for m in units:
            if m in done:
                continue
            ups = [u for u in units if basins[u].get("down") == m]
            if any(u not in done for u in ups):
                continue
            M = basins[m]
            Im = [x + y for x, y in zip(local[m], free_in[m])]
            Hm, Om, Qs = [M["bottom"]] * (END_K + 1), [0.0] * (END_K + 1), [0.0] * (END_K + 1)
            if m in fore:
                F = basins[fore[m]]
                If = local[F["id"]]
                Hf, D = [F["bottom"]] * (END_K + 1), [0.0] * (END_K + 1)
                hf, hm, d, om = F["bottom"], M["bottom"], 0.0, 0.0
                for k in range(END_K):
                    if If[k] == If[k + 1] == Im[k] == Im[k + 1] == 0 and d == 0 and om == 0:
                        Hf[k + 1], Hm[k + 1] = hf, hm
                        continue
                    r_f = (If[k] + If[k + 1]) / 2 + storage(F, hf) / DT_S - d / 2
                    r_m = (Im[k] + Im[k + 1]) / 2 + storage(M, hm) / DT_S + d / 2 - om / 2
                    hf, hm = step_pair(F, M, r_f, r_m)
                    d, om = divider_flow(F["divider"], hf, hm), main_outflow(M, hm)
                    Hf[k + 1], Hm[k + 1], D[k + 1], Om[k + 1] = hf, hm, d, om
                    Qs[k + 1] = main_outflow(M, hm, parts=True)[2]
                trace[F["id"]] = {"I": If, "O": D, "H": Hf, "S": [0.0] * (END_K + 1)}
                Im = [x + y for x, y in zip(Im, D)]
            else:
                h, om = M["bottom"], 0.0
                for k in range(END_K):
                    if Im[k] == 0 and Im[k + 1] == 0 and om == 0:
                        Hm[k + 1] = h
                        continue
                    rhs = (Im[k] + Im[k + 1]) / 2 + storage(M, h) / DT_S - om / 2
                    h = step_single(M, rhs)
                    om = main_outflow(M, h)
                    Hm[k + 1], Om[k + 1] = h, om
                    Qs[k + 1] = main_outflow(M, h, parts=True)[2]
            trace[m] = {"I": Im, "O": Om, "H": Hm, "S": Qs}
            if M.get("down"):
                free_in[M["down"]] = [x + y for x, y in zip(free_in[M["down"]], Om)]
            done.add(m)
    rows = []
    for b in site["basins"]:
        tr = trace[b["id"]]
        crest = b.get("spill_crest")
        for n, (start, wet) in enumerate(st):
            stop = st[n + 1][0] if n + 1 < len(st) else END_K + 1
            ks = range(start, stop)
            ph = max(tr["H"][k] for k in ks)
            kpk = next(k for k in ks if tr["H"][k] == ph)
            rows.append({"basin": b["id"], "start": start, "peak_in": max(tr["I"][k] for k in ks),
                         "peak_out": max(tr["O"][k] for k in ks), "peak_stage": ph, "peak_k": kpk,
                         "spill": crest is not None and ph > crest,
                         "margin": (ph - crest) if crest is not None else 99.0,
                         "spill_volume": sum(tr["S"][k] for k in ks) * DT_S})
    return rows, trace, st
