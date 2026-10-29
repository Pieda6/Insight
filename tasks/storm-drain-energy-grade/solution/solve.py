#!/usr/bin/env python3
"""Reference solution for storm-drain-energy-grade.

Energy grade line evaluation of each storm drain network by FHWA HEC-22, 4th edition, Section 9.4, with the
FHWA inlet and access hole energy loss method of Section 9.1.6.7 at every structure. Work starts at the outfall
and proceeds upstream through every branch.
"""
import csv
import json
import math
from pathlib import Path

DATA = Path("/app/data")
OUT = Path("/app/output")

G = 32.2
KU = 1.486            # Manning constant, HEC-22 equation 6.5
KQ = 0.46             # full-flow constant, HEC-22 equations 9.2 and 9.4
K_ENTRANCE = 0.2      # Ki, equation 9.15
K_EXIT = 0.4          # Ko, equation 9.31
K_OUTFALL = 1.0       # equation 9.5 with still receiving water
BENCH = {             # Table 9.5: (bench submerged, bench unsubmerged)
    "flat": (-0.05, -0.05),
    "depressed": (0.0, 0.0),
    "half_benched": (-0.05, -0.85),
    "full_benched": (-0.25, -0.93),
    "improved": (-0.60, -0.98),
}


def segment(y, d):
    """Area, wetted perimeter and top width of a circular pipe flowing at depth y."""
    theta = 2.0 * math.acos(max(-1.0, min(1.0, 1.0 - 2.0 * y / d)))
    area = d * d / 8.0 * (theta - math.sin(theta))
    return area, d * theta / 2.0, d * math.sin(theta / 2.0)


def manning_flow(y, d, n, s):
    a, p, _ = segment(y, d)
    return KU / n * a * (a / p) ** (2.0 / 3.0) * math.sqrt(s)


def bisect(f, lo, hi, iters=200):
    flo = f(lo)
    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        fm = f(mid)
        if (fm > 0) == (flo > 0):
            lo, flo = mid, fm
        else:
            hi = mid
    return 0.5 * (lo + hi)


def depth_of_max_flow(d):
    lo, hi = 0.5 * d, d
    for _ in range(200):
        m1, m2 = lo + (hi - lo) / 3, hi - (hi - lo) / 3
        if manning_flow(m1, d, 1.0, 1.0) < manning_flow(m2, d, 1.0, 1.0):
            lo = m1
        else:
            hi = m2
    return 0.5 * (lo + hi)


def normal_depth(q, d, n, s):
    top = depth_of_max_flow(d)
    if manning_flow(top, d, n, s) < q:
        raise ValueError("flow exceeds the pipe's open-channel capacity")
    return bisect(lambda y: manning_flow(y, d, n, s) - q, 1e-12 * d, top)


def critical_depth(q, d):
    def f(y):
        a, _, t = segment(y, d)
        return q * q * t - G * a ** 3
    return bisect(f, 1e-12 * d, d * (1 - 1e-12))


def vhead(q, area):
    return (q / area) ** 2 / (2.0 * G)


class Pipe:
    def __init__(self, rec):
        self.id = rec["pipe_id"]
        self.up = rec["from_structure"]
        self.down = rec["to_structure"]
        self.d = rec["diameter_in"] / 12.0
        self.length = rec["length_ft"]
        self.inv_up = rec["upstream_invert_ft"]
        self.inv_down = rec["downstream_invert_ft"]
        self.n = rec["manning_n"]
        self.angle = rec["angle_deg"]
        self.slope = (self.inv_up - self.inv_down) / self.length
        self.area = math.pi * self.d ** 2 / 4.0


def evaluate(system, flows, tailwater):
    """Return {pipe_id: row values} for one system and one event."""
    structures = {s["structure_id"]: s for s in system["structures"]}
    pipes = [Pipe(p) for p in system["pipes"]]
    into = {}
    for p in pipes:
        into.setdefault(p.down, []).append(p)
    out_pipe = {p.up: p for p in pipes}

    # pipe flows: inlet flow at every structure upstream
    q = {}

    def accumulate(sid):
        total = flows.get(sid, 0.0)
        for p in into.get(sid, []):
            total += accumulate(p.up)
        q[out_pipe[sid].id] = total
        return total

    outfall_pipe = into[None][0]
    accumulate(outfall_pipe.up)

    rows = {}

    def walk(p, egl_a, at_outfall):
        qp = q[p.id]
        yn = normal_depth(qp, p.d, p.n, p.slope)
        yc = critical_depth(qp, p.d)
        hv_full = vhead(qp, p.area)
        hv_n = vhead(qp, segment(yn, p.d)[0])
        k_exit = K_OUTFALL if at_outfall else K_EXIT

        # Table 9.6, downstream end of the pipe
        boc_o = p.inv_down
        toc_o = boc_o + p.d
        if egl_a >= toc_o:
            case = "A"
            egl_o = egl_a + k_exit * hv_full
        elif egl_a > boc_o + yn:
            case = "B"
            egl_o = egl_a + k_exit * vhead(qp, segment(egl_a - boc_o, p.d)[0])
        elif egl_a > boc_o + yc:
            case = "C"
            egl_o = max(egl_a + k_exit * vhead(qp, segment(egl_a - boc_o, p.d)[0]), boc_o + yn + hv_n)
        elif egl_a > boc_o:
            case = "D"
            egl_o = boc_o + yn + hv_n
        else:
            case = "E"
            egl_o = boc_o + yn + hv_n
        at_normal = egl_o == boc_o + yn + hv_n       # the pipe runs at normal depth to its upstream end

        # Table 9.7, upstream end of the pipe
        boc_i = p.inv_up
        toc_i = boc_i + p.d
        if case == "A":
            sf = (qp * p.n / (KQ * p.d ** 2.67)) ** 2
            egl_i = egl_o + sf * p.length
            hv_i = hv_full
        else:
            egl_i = egl_o + (boc_i - boc_o)
            hv_i = hv_n
        hgl_i = boc_i + yn if at_normal else egl_i - hv_i
        if hgl_i >= toc_i:
            cond = "A"
        elif hgl_i > boc_i + max(yn, yc):
            cond = "B"
        elif hgl_i > boc_i + yc:
            cond = "C"
        else:
            cond = "D"
        if cond == "D":
            hgl_i = boc_i + yn
            egl_i = hgl_i + hv_n

        # Section 9.1.6.7 at the structure at the pipe's upstream end
        st = structures[p.up]
        za = boc_i
        ei = egl_i - za
        eaio = 0.0 if cond == "D" else ei + K_ENTRANCE * hv_i
        di = qp / (p.area * math.sqrt(G * p.d))
        eai = max(eaio, p.d * di ** 2, 1.6 * p.d * di ** 0.67)

        inflow_pipes = into.get(st["structure_id"], [])
        plunging = []                       # (flow, zk)
        joined = []                         # (flow, angle)
        for ip in inflow_pipes:
            zk = ip.inv_down - za
            if zk > eai:
                plunging.append((q[ip.id], zk))
            else:
                joined.append((q[ip.id], ip.angle))
        surface = flows.get(st["structure_id"], 0.0)
        if surface > 0:
            plunging.append((surface, st["rim_elevation_ft"] - za))

        if inflow_pipes:
            sub, unsub = BENCH[st["floor"]]
            ratio = eai / p.d
            if ratio >= 2.5:
                cb = sub
            elif ratio <= 1.0:
                cb = unsub
            else:
                cb = unsub + (sub - unsub) * (ratio - 1.0) / 1.5
        else:
            cb = 0.0
        qj = sum(f for f, _ in joined)
        theta_w = sum(f * a for f, a in joined) / qj if qj > 0 else 180.0
        c_theta = 4.5 * qj / qp * math.cos(math.radians(theta_w / 2.0))
        c_p = sum(f * (min(zk, 10.0 * p.d) - eai) / p.d for f, zk in plunging) / qp
        h_a = max(0.0, (cb + c_theta + c_p) * (eai - ei))
        e_a = max(eai + h_a, ei)
        egl_struct = za + e_a

        rows[p.id] = (case, cond, egl_o, egl_i, egl_struct,
                      "yes" if egl_struct > st["rim_elevation_ft"] else "no")
        for ip in inflow_pipes:
            walk(ip, egl_struct, False)

    walk(outfall_pipe, tailwater, True)
    return rows


def main():
    systems = json.loads((DATA / "networks.json").read_text())
    flows = {}
    with open(DATA / "inlet_flows.csv", newline="") as fh:
        for r in csv.DictReader(fh):
            flows.setdefault(r["event"], {})[r["structure_id"]] = float(r["flow_cfs"])
    tail = {}
    with open(DATA / "outfalls.csv", newline="") as fh:
        for r in csv.DictReader(fh):
            tail[(r["system_id"], r["event"])] = float(r["receiving_water_elevation_ft"])

    out = []
    for system in systems:
        for event in sorted(flows):
            res = evaluate(system, flows[event], tail[(system["system_id"], event)])
            for pid, (case, cond, eo, ei, ea, sur) in res.items():
                out.append((system["system_id"], event, pid, case, cond,
                            f"{eo:.3f}", f"{ei:.3f}", f"{ea:.3f}", sur))
    out.sort(key=lambda r: (r[0], r[1], r[2]))
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "pipe_grades.csv", "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["system_id", "event", "pipe_id", "ds_case", "us_condition",
                    "egl_ds_ft", "egl_us_ft", "structure_egl_ft", "surcharged"])
        w.writerows(out)


if __name__ == "__main__":
    main()
