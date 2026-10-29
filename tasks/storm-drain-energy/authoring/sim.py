"""Generator's model for storm-drain-energy (third implementation).

Step functions over one pipe or one structure, so that generate.py can place near-threshold cases while it walks
upstream, plus evaluate() for a whole system. Depths are solved by plain bisection in depth with a
precomputed relative depth of maximum flow.

HEC-22 4th edition: Tables 9.6 and 9.7 (Section 9.4) and Section 9.1.6.7.
"""
import math

g = 32.2
BENCH_SUB = {"flat": -0.05, "depressed": 0.0, "half_benched": -0.05, "full_benched": -0.25, "improved": -0.60}
BENCH_UNSUB = {"flat": -0.05, "depressed": 0.0, "half_benched": -0.85, "full_benched": -0.93, "improved": -0.98}


def wet(y, D):
    r = D / 2.0
    h = min(max(y, 0.0), D)
    half = math.acos((r - h) / r)          # half the central angle
    area = r * r * (half - math.sin(half) * math.cos(half))
    perim = 2.0 * r * half
    top = 2.0 * math.sqrt(max(h * (D - h), 0.0))
    return area, perim, top


def q_manning(y, D, n, S):
    a, p, _ = wet(y, D)
    return 1.486 / n * a * (a / p) ** (2.0 / 3.0) * S ** 0.5


_YMAX = None


def ymax_ratio():
    global _YMAX
    if _YMAX is None:
        lo, hi = 0.6, 0.999
        for _ in range(300):
            a = lo + (hi - lo) * 0.382
            b = lo + (hi - lo) * 0.618
            if q_manning(a, 1.0, 1.0, 1.0) > q_manning(b, 1.0, 1.0, 1.0):
                hi = b
            else:
                lo = a
        _YMAX = 0.5 * (lo + hi)
    return _YMAX


def yn_of(Q, D, n, S):
    lo, hi = 0.0, ymax_ratio() * D
    if q_manning(hi, D, n, S) <= Q:
        return None
    for _ in range(300):
        m = 0.5 * (lo + hi)
        if q_manning(m, D, n, S) < Q:
            lo = m
        else:
            hi = m
    return 0.5 * (lo + hi)


def yc_of(Q, D):
    lo, hi = 0.0, D
    for _ in range(300):
        m = 0.5 * (lo + hi)
        a, _, t = wet(m, D)
        if a ** 3 / max(t, 1e-300) < Q * Q / g:
            lo = m
        else:
            hi = m
    return 0.5 * (lo + hi)


def hv(Q, A):
    return Q * Q / (A * A * 2.0 * g)


def pipe_state(Q, D, n, L, inv_up, inv_dn, egl_a, outfall):
    """Downstream case, upstream condition and grade lines for one pipe; also the thresholds used."""
    S = (inv_up - inv_dn) / L
    yn, yc = yn_of(Q, D, n, S), yc_of(Q, D)
    Af = math.pi * D * D / 4.0
    hf, hn = hv(Q, Af), hv(Q, wet(yn, D)[0])
    kx = 1.0 if outfall else 0.4
    if egl_a >= inv_dn + D:
        case, eglo = "A", egl_a + kx * hf
    elif egl_a > inv_dn + yn:
        case, eglo = "B", egl_a + kx * hv(Q, wet(egl_a - inv_dn, D)[0])
    elif egl_a > inv_dn + yc:
        case = "C"
        via_face = egl_a + kx * hv(Q, wet(egl_a - inv_dn, D)[0])
        eglo = max(via_face, inv_dn + yn + hn)
    elif egl_a > inv_dn:
        case, eglo = "D", inv_dn + yn + hn
    else:
        case, eglo = "E", inv_dn + yn + hn
    if case == "A":
        egli = eglo + (Q * n / (0.46 * D ** 2.67)) ** 2 * L
        hvi = hf
    else:
        egli = eglo + (inv_up - inv_dn)
        hvi = hn
    # hgl_i equals inv_up + yn when the pipe runs at normal depth
    structural = case in ("D", "E") or (case == "C" and inv_dn + yn + hn >= via_face)
    hgli = inv_up + yn if structural else egli - hvi
    if hgli >= inv_up + D:
        cond = "A"
    elif hgli > inv_up + max(yn, yc):
        cond = "B"
    elif hgli > inv_up + yc:
        cond = "C"
    else:
        cond = "D"
    if cond == "D":
        egli = inv_up + yn + hn
    return dict(case=case, cond=cond, eglo=eglo, egli=egli, hgli=hgli, hvi=hvi, yn=yn, yc=yc, S=S,
                hf=hf, hn=hn, structural=structural, egl_a=egl_a, inv_dn=inv_dn, inv_up=inv_up, D=D)


def structure_state(ps, Q, inflows, surface_q, rim, floor):
    """inflows: list of (q, zk, angle) of inflow pipes. Returns Eai, Ea, EGLa and the plunging split."""
    D = ps["D"]
    za = ps["inv_up"]
    Ei = ps["egli"] - za
    A = math.pi * D * D / 4.0
    DI = Q / (A * math.sqrt(g * D))
    cand = [D * DI ** 2, 1.6 * D * DI ** 0.67]
    if ps["cond"] != "D":
        cand.append(Ei + 0.2 * ps["hvi"])
    Eai = max(cand)
    plunge, join = [], []
    for q, zk, ang in inflows:
        if zk > Eai:
            plunge.append((q, zk))
        else:
            join.append((q, ang))
    if surface_q > 0:
        plunge.append((surface_q, rim - za))
    if inflows:
        x = Eai / D
        w = min(1.0, max(0.0, (x - 1.0) / 1.5))
        CB = (1 - w) * BENCH_UNSUB[floor] + w * BENCH_SUB[floor]
    else:
        CB = 0.0
    sq = sum(q for q, _ in join)
    tw = sum(q * a for q, a in join) / sq if sq else 180.0
    Ct = 4.5 * sq / Q * math.cos(math.radians(tw) / 2.0)
    Cp = 0.0
    for q, zk in plunge:
        Cp += q * (min(zk, 10 * D) - Eai) / D
    Cp /= Q
    Ha = (CB + Ct + Cp) * (Eai - Ei)
    Ea = Eai + (Ha if Ha > 0 else 0.0)
    if Ea < Ei:
        Ea = Ei
    return dict(Eai=Eai, Ei=Ei, Ea=Ea, egla=za + Ea, za=za, CB=CB, Ct=Ct, Cp=Cp, DI=DI)


def evaluate(system, flows, tw):
    """{pipe_id: (case, cond, eglo, egli, egla, surcharged)} for one event."""
    S = {s["structure_id"]: s for s in system["structures"]}
    into = {}
    for p in system["pipes"]:
        into.setdefault(p["to_structure"], []).append(p)
    Qp = {}

    def total(sid):
        t = flows.get(sid, 0.0) + sum(total(p["from_structure"]) for p in into.get(sid, []))
        return t

    for p in system["pipes"]:
        Qp[p["pipe_id"]] = total(p["from_structure"])
    res = {}
    stack = [(into[None][0], tw, True)]
    while stack:
        p, egla, outfall = stack.pop()
        Q = Qp[p["pipe_id"]]
        ps = pipe_state(Q, p["diameter_in"] / 12.0, p["manning_n"], p["length_ft"], p["upstream_invert_ft"],
                        p["downstream_invert_ft"], egla, outfall)
        s = S[p["from_structure"]]
        ins = into.get(s["structure_id"], [])
        inflows = [(Qp[x["pipe_id"]], x["downstream_invert_ft"] - ps["inv_up"], x["angle_deg"]) for x in ins]
        ss = structure_state(ps, Q, inflows, flows.get(s["structure_id"], 0.0), s["rim_elevation_ft"], s["floor"])
        res[p["pipe_id"]] = (ps["case"], ps["cond"], ps["eglo"], ps["egli"], ss["egla"],
                             "yes" if ss["egla"] > s["rim_elevation_ft"] else "no")
        for x in ins:
            stack.append((x, ss["egla"], False))
    return res
