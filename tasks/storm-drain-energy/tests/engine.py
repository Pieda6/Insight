"""Independent verifier model for storm-drain-energy.

Written separately from the reference solution: networks are ordered once from the outfall with an explicit
queue, circular sections are handled through the central angle, normal depth is found by a safeguarded Newton
iteration in that angle and critical depth by the Illinois regula falsi method.

Method: FHWA HEC-22, 4th edition (February 2024), Section 9.4 (Tables 9.6 and 9.7) with the FHWA inlet and
access hole energy loss method of Section 9.1.6.7 (equations 9.12 to 9.31) at every structure.
"""
import csv
import json
import math
from collections import deque
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
GRAV = 32.2
TIE = 1e-6            # ft; structural ties (the same quantity reached two ways) accept either letter

CB_TABLE = {          # Table 9.5 (bench unsubmerged, bench submerged)
    "flat": (-0.05, -0.05),
    "depressed": (0.0, 0.0),
    "half_benched": (-0.85, -0.05),
    "full_benched": (-0.93, -0.25),
    "improved": (-0.98, -0.60),
}


# ---- circular sections by central angle -------------------------------------------------------------------
def angle_at(y, dia):
    c = 1.0 - 2.0 * y / dia
    return 2.0 * math.acos(min(1.0, max(-1.0, c)))


def area_of(phi, dia):
    return dia * dia * (phi - math.sin(phi)) / 8.0


def conveyance(phi, dia):
    """1.486/n * A * R^(2/3) without n."""
    a = area_of(phi, dia)
    return 1.486 * a ** (5.0 / 3.0) / (dia * phi / 2.0) ** (2.0 / 3.0)


def full_area(dia):
    return math.pi * dia * dia / 4.0


def capacity_full(dia, n, slope):
    """HEC-22 equation 9.2."""
    return 0.46 / n * dia ** 2.67 * math.sqrt(slope)


def friction_slope_full(q, dia, n):
    """HEC-22 equation 9.4."""
    return (q * n / (0.46 * dia ** 2.67)) ** 2


def _phi_peak():
    # d/dphi of A^(5/3) P^(-2/3) = 0  ->  5 P dA/dphi = 2 A dP/dphi, with A ~ phi - sin phi, P ~ phi
    g = lambda p: 5.0 * p * (1.0 - math.cos(p)) - 2.0 * (p - math.sin(p))
    a, b = math.pi, 2.0 * math.pi - 1e-9
    for _ in range(200):
        m = 0.5 * (a + b)
        if g(m) > 0:
            a = m
        else:
            b = m
    return 0.5 * (a + b)


PHI_PEAK = _phi_peak()


def normal_depth(q, dia, n, slope):
    target = q * n / math.sqrt(slope)
    if conveyance(PHI_PEAK, dia) < target:
        raise ValueError("no normal depth")
    lo, hi = 0.0, PHI_PEAK
    phi = 0.5 * PHI_PEAK
    for _ in range(100):
        f = conveyance(phi, dia) - target
        if f > 0:
            hi = phi
        else:
            lo = phi
        h = 1e-7
        dfd = (conveyance(phi + h, dia) - conveyance(phi - h, dia)) / (2 * h)
        nxt = phi - f / dfd if dfd > 0 else 0.5 * (lo + hi)
        if not (lo < nxt < hi):
            nxt = 0.5 * (lo + hi)
        if abs(nxt - phi) < 1e-15:
            phi = nxt
            break
        phi = nxt
    return dia * (1.0 - math.cos(phi / 2.0)) / 2.0


def critical_depth(q, dia):
    def f(phi):
        return GRAV * area_of(phi, dia) ** 3 - q * q * dia * math.sin(phi / 2.0)
    a, b = 1e-9, 2.0 * math.pi - 1e-9
    fa, fb = f(a), f(b)
    side = 0
    for _ in range(400):
        c = (a * fb - b * fa) / (fb - fa)
        fc = f(c)
        if abs(b - a) < 1e-14:
            break
        if (fc > 0) == (fb > 0):
            b, fb = c, fc
            if side == -1:
                fa /= 2
            side = -1
        else:
            a, fa = c, fc
            if side == 1:
                fb /= 2
            side = 1
    return dia * (1.0 - math.cos(c / 2.0)) / 2.0


def velocity_head(q, area):
    v = q / area
    return v * v / (2.0 * GRAV)


# ---- access hole method -------------------------------------------------------------------------------------
def discharge_intensity(q, dia):
    """Equation 9.16."""
    return q / (full_area(dia) * math.sqrt(GRAV * dia))


def initial_energy(ei, hv_out, q, dia, outlet_control):
    """Equations 9.13 to 9.18. Returns (Eai, Eaio, Eais, Eaiu)."""
    di = discharge_intensity(q, dia)
    eaio = ei + 0.2 * hv_out if outlet_control else 0.0
    eais = dia * di ** 2
    eaiu = 1.6 * dia * di ** 0.67
    return max(eaio, eais, eaiu), eaio, eais, eaiu


def bench_coefficient(floor, eai, dia):
    lo, hi = CB_TABLE[floor]
    r = eai / dia
    if r <= 1.0:
        return lo
    if r >= 2.5:
        return hi
    return lo + (r - 1.0) / 1.5 * (hi - lo)


def angle_coefficient(joined, q_out):
    """Equations 9.21 and 9.22 from the non-plunging inflows [(q, angle)]."""
    total = sum(x for x, _ in joined)
    if total <= 0:
        return 0.0
    tw = sum(x * a for x, a in joined) / total
    return 4.5 * total / q_out * math.cos(tw * math.pi / 360.0)


def plunge_coefficient(plunging, eai, dia, q_out):
    """Equations 9.24 and 9.25 from the plunging inflows [(q, zk)], zk limited to 10 Do."""
    return sum(x * (min(z, 10.0 * dia) - eai) / dia for x, z in plunging) / q_out


def final_energy(eai, ei, cb, ct, cp):
    """Equations 9.27 and 9.28 with the floors of Section 9.1.6.7.2."""
    ha = (cb + ct + cp) * (eai - ei)
    if ha < 0:
        ha = 0.0
    return max(eai + ha, ei)


def eaio(ei, hv, q, dia):
    return initial_energy(ei, hv, q, dia, True)[1]


def eais(q, dia):
    return initial_energy(0.0, 0.0, q, dia, False)[2]


def eaiu(q, dia):
    return initial_energy(0.0, 0.0, q, dia, False)[3]


def yn_ratio(q, dia, n, slope):
    return normal_depth(q, dia, n, slope) / dia


def structure_energy(ei, hv, q, dia, floor, joined, plunging, outlet_control, terminal=False):
    """Ea for one structure whose inflows are already split into joined [(q, angle)] and plunging [(q, zk)]."""
    eai = initial_energy(ei, hv, q, dia, outlet_control)[0]
    cb = 0.0 if terminal else bench_coefficient(floor, eai, dia)
    return final_energy(eai, ei, cb, angle_coefficient(joined, q), plunge_coefficient(plunging, eai, dia, q))


# ---- network evaluation -------------------------------------------------------------------------------------
def _downstream_case(egl_a, boc, dia, yn, yc):
    if egl_a >= boc + dia:
        return "A"
    if egl_a > boc + yn:
        return "B"
    if egl_a > boc + yc:
        return "C"
    if egl_a > boc:
        return "D"
    return "E"


def _upstream_conditions(hgl, boc, dia, yn, yc):
    """Every Table 9.7 letter that holds within TIE of hgl (first match in table order for each)."""
    out = set()
    for h in (hgl - TIE, hgl, hgl + TIE):
        if h >= boc + dia:
            out.add("A")
        elif h > boc + max(yn, yc):
            out.add("B")
        elif h > boc + yc:
            out.add("C")
        else:
            out.add("D")
    return out


def evaluate(system, inlet_q, tailwater, trace=None):
    """Rows {pipe_id: (case, condition, accepted_conditions, egl_ds, egl_us, egl_structure, surcharged)}."""
    st = {s["structure_id"]: s for s in system["structures"]}
    pipes = {p["pipe_id"]: p for p in system["pipes"]}
    leaving = {p["from_structure"]: pid for pid, p in pipes.items()}
    entering = {}
    for pid, p in pipes.items():
        entering.setdefault(p["to_structure"], []).append(pid)

    order = []
    queue = deque(entering[None])
    while queue:
        pid = queue.popleft()
        order.append(pid)
        queue.extend(entering.get(pipes[pid]["from_structure"], []))

    flow = {}
    for pid in reversed(order):
        up = pipes[pid]["from_structure"]
        flow[pid] = inlet_q.get(up, 0.0) + sum(flow[x] for x in entering.get(up, []))

    egl_struct = {}
    rows = {}
    for pid in order:
        p = pipes[pid]
        dia = p["diameter_in"] / 12.0
        q = flow[pid]
        n = p["manning_n"]
        boc_o, boc_i = p["downstream_invert_ft"], p["upstream_invert_ft"]
        slope = (boc_i - boc_o) / p["length_ft"]
        yn = normal_depth(q, dia, n, slope)
        yc = critical_depth(q, dia)
        a_n = area_of(angle_at(yn, dia), dia)
        hv_f = velocity_head(q, full_area(dia))
        hv_n = velocity_head(q, a_n)
        outfall = p["to_structure"] is None
        k_out = 1.0 if outfall else 0.4
        egl_a = tailwater if outfall else egl_struct[p["to_structure"]]

        case = _downstream_case(egl_a, boc_o, dia, yn, yc)
        normal_e = boc_o + yn + hv_n
        if case == "A":
            egl_o = egl_a + k_out * hv_f
        elif case in ("B", "C"):
            face = area_of(angle_at(egl_a - boc_o, dia), dia)
            egl_o = egl_a + k_out * velocity_head(q, face)
            if case == "C":
                egl_o = max(egl_o, normal_e)
        else:
            egl_o = normal_e

        if case == "A":
            egl_i = egl_o + friction_slope_full(q, dia, n) * p["length_ft"]
            hv_i = hv_f
        else:
            egl_i = egl_o + slope * p["length_ft"]
            hv_i = hv_n
        hgl_i = boc_i + yn if egl_o == normal_e else egl_i - hv_i
        accepted = _upstream_conditions(hgl_i, boc_i, dia, yn, yc)
        cond = "A" if hgl_i >= boc_i + dia else "B" if hgl_i > boc_i + max(yn, yc) else \
            "C" if hgl_i > boc_i + yc else "D"
        if cond == "D":
            egl_i = boc_i + yn + hv_n

        s = st[p["from_structure"]]
        za = boc_i
        ei = egl_i - za
        eai, eaio, eais, eaiu = initial_energy(ei, hv_i, q, dia, cond != "D")
        ins = entering.get(s["structure_id"], [])
        joined, plunging = [], []
        for x in ins:
            zk = pipes[x]["downstream_invert_ft"] - za
            (plunging if zk > eai else joined).append((flow[x], zk if zk > eai else pipes[x]["angle_deg"]))
        if inlet_q.get(s["structure_id"], 0.0) > 0:
            plunging.append((inlet_q[s["structure_id"]], s["rim_elevation_ft"] - za))
        cb = bench_coefficient(s["floor"], eai, dia) if ins else 0.0
        ct = angle_coefficient(joined, q)
        cp = plunge_coefficient(plunging, eai, dia, q)
        ea = final_energy(eai, ei, cb, ct, cp)
        egl_struct[s["structure_id"]] = za + ea
        rows[pid] = (case, cond, accepted, egl_o, egl_i, za + ea,
                     "yes" if za + ea > s["rim_elevation_ft"] else "no")
        if trace is not None:
            trace[pid] = dict(q=q, yn=yn, yc=yc, hv_full=hv_f, hv_normal=hv_n, egl_a_down=egl_a, hgl_i=hgl_i,
                              ei=ei, eai=eai, eaio=eaio, eais=eais, eaiu=eaiu, cb=cb, c_theta=ct, c_p=cp,
                              plunging=plunging, joined=joined, za=za, rim=s["rim_elevation_ft"],
                              boc_o=boc_o, boc_i=boc_i, dia=dia, case=case, at_normal=egl_o == normal_e,
                              inflow_zk=[pipes[x]["downstream_invert_ft"] - za for x in ins], ea=ea)
    return rows


def load(data=None):
    data = Path(data or DATA)
    systems = json.loads((data / "networks.json").read_text())
    flows = {}
    with open(data / "inlet_flows.csv", newline="") as fh:
        for r in csv.DictReader(fh):
            flows.setdefault(r["event"], {})[r["structure_id"]] = float(r["flow_cfs"])
    tw = {}
    with open(data / "outfalls.csv", newline="") as fh:
        for r in csv.DictReader(fh):
            tw[(r["system_id"], r["event"])] = float(r["receiving_water_elevation_ft"])
    return systems, flows, tw


def tags_of(pid, p_to, t, row, floor):
    """Method families a row exercises, from the engine's own trace."""
    case, cond = row[0], row[1]
    tags = set()
    if p_to is None:
        tags.add("outfall_pipes")
    tags.add({"A": "submerged_outlets", "B": "partly_full_outlets", "C": "partly_full_outlets"}.get(
        case, "normal_depth_outlets"))
    if cond == "A":
        tags.add("full_flow_upstream")
    if cond == "D":
        tags.add("supercritical_reset")
    if any(z > t["eai"] for z in t["inflow_zk"]):
        tags.add("plunging_inflow_pipes")
    if any(a < 180 for _, a in t["joined"]):
        tags.add("angled_inflows")
    if not t["inflow_zk"]:
        tags.add("terminal_structures")
    if t["inflow_zk"] and floor in ("half_benched", "full_benched", "improved") and 1.0 < t["eai"] / t["dia"] < 2.5:
        tags.add("benching_interpolated")
    if any(z > 10 * t["dia"] for _, z in t["plunging"]):
        tags.add("drops_over_10_diameters")
    if t["ea"] <= t["ei"]:
        tags.add("outflow_energy_governs")
    if row[6] == "yes":
        tags.add("surcharged_structures")
    near = [t["egl_a_down"] - (t["boc_o"] + x) for x in (0.0, t["yc"], t["yn"], t["dia"])]
    near += [t["hgl_i"] - (t["boc_i"] + x) for x in (t["dia"], t["yc"]) + (() if t["at_normal"] else (t["yn"],))]
    near += [z - t["eai"] for z in t["inflow_zk"]] + [t["za"] + t["ea"] - t["rim"]]
    if any(abs(v) <= 0.03 for v in near):
        tags.add("near_thresholds")
    return tags


def expected(data=None, with_tags=False):
    """Sorted rows: (system_id, event, pipe_id, case, condition, accepted, egl_ds, egl_us, egl_struct, surcharged)."""
    systems, flows, tw = load(data)
    out = []
    tags = {}
    for s in systems:
        floors = {x["structure_id"]: x["floor"] for x in s["structures"]}
        pipes = {p["pipe_id"]: p for p in s["pipes"]}
        for ev in sorted(flows):
            tr = {}
            for pid, r in evaluate(s, flows[ev], tw[(s["system_id"], ev)], trace=tr).items():
                out.append((s["system_id"], ev, pid) + r)
                p = pipes[pid]
                tags[(s["system_id"], ev, pid)] = tags_of(pid, p["to_structure"], tr[pid], r, floors[p["from_structure"]])
    out.sort(key=lambda r: r[:3])
    return (out, tags) if with_tags else out
