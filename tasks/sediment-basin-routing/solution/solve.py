#!/usr/bin/env python3
"""Reference solution for sediment-basin-routing.

Hydrology (NRCS NEH Part 630): storms are split from the 6-minute gauge record; within each storm the accumulated
rain gives accumulated runoff by the curve number equation (ch. 10, eq. 10-11, example 10-6) for each drainage
area at its state when the storm begins; the 6-minute runoff increments are convolved with the area's unit
hydrograph from the dimensionless unit hydrograph (ch. 16, table 16-1; Tp = dD/2 + 0.6 Tc, qp = 484 A Q / Tp).
Hydraulics (FHWA HEC-22 4th ed., sec. 10.3): trapezoidal stage-storage (eq. 10.10); dewatering orifice (eq.
10.23, head from the centroid), riser as weir on its circumference or orifice on its area, whichever passes less
(example 10.11), broad-crested emergency spillway (eq. 10.32), all added (table 10.10). Routing: storage-
indication (NEH ch. 17 eq. 17-3, HEC-22 eq. 10.45) through the whole season, upstream basins first, each step
solved by Newton's method on the continuous relations.
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
N = 183 * 240                     # last time point: 2026-09-30 24:00
DT = 360.0                        # seconds
DD = 0.1                          # hours: unit duration = gauge interval
G = 32.2
T_RATIO = [0, .1, .2, .3, .4, .5, .6, .7, .8, .9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0, 2.2,
           2.4, 2.6, 2.8, 3.0, 3.2, 3.4, 3.6, 3.8, 4.0, 4.5, 5.0]
Q_RATIO = [.000, .030, .100, .190, .310, .470, .660, .820, .930, .990, 1.000, .990, .930, .860, .780, .680, .560,
           .460, .390, .330, .280, .207, .147, .107, .077, .055, .040, .029, .021, .015, .011, .005, .000]


def idx(stamp):
    return round((datetime.strptime(stamp, "%Y-%m-%dT%H:%M") - START) / STEP)


def stamp(i):
    return (START + STEP * i).strftime("%Y-%m-%dT%H:%M")


def ratio(x):                                   # table 16-1, linear interpolation
    if x <= 0 or x >= 5:
        return 0.0
    j = bisect.bisect_right(T_RATIO, x) - 1
    return Q_RATIO[j] + (Q_RATIO[j + 1] - Q_RATIO[j]) * (x - T_RATIO[j]) / (T_RATIO[j + 1] - T_RATIO[j])


def accumulated_runoff(p, cn):                  # eq. 10-11 with Ia = 0.2 S
    s = 1000 / cn - 10
    ia = 0.2 * s
    return 0.0 if p <= ia else (p - ia) ** 2 / (p - ia + s)


class Basin:
    def __init__(self, rec):
        self.id = rec["basin_id"]
        self.z0 = rec["bottom_elevation_ft"]
        self.L, self.W, self.Z = rec["bottom_length_ft"], rec["bottom_width_ft"], rec["side_slope_h_per_v"]
        o, rr, sp = rec["dewatering_orifice"], rec["riser"], rec["emergency_spillway"]
        d = o["diameter_in"] / 12
        self.o_area, self.o_center, self.o_c = math.pi * d * d / 4, o["invert_elevation_ft"] + d / 2, o["discharge_coefficient"]
        self.r_len, self.r_area = math.pi * rr["diameter_ft"], math.pi * rr["diameter_ft"] ** 2 / 4
        self.r_crest, self.r_cw, self.r_co = rr["crest_elevation_ft"], rr["weir_coefficient"], rr["orifice_coefficient"]
        self.s_crest, self.s_len, self.s_cw = sp["crest_elevation_ft"], sp["crest_length_ft"], sp["weir_coefficient"]
        self.down = rec["discharges_to"]

    def volume(self, h):                        # HEC-22 eq. 10.10
        D = h - self.z0
        if D <= 0:
            return 0.0, 0.0
        v = self.L * self.W * D + (self.L + self.W) * self.Z * D ** 2 + 4 / 3 * self.Z ** 2 * D ** 3
        dv = self.L * self.W + 2 * (self.L + self.W) * self.Z * D + 4 * self.Z ** 2 * D ** 2
        return v, dv

    def discharge(self, h):                     # HEC-22 sec. 10.3.3, returns (Q, dQ/dh)
        q = dq = 0.0
        g2 = math.sqrt(2 * G)
        ho = h - self.o_center
        if ho > 0:
            q += self.o_c * self.o_area * g2 * math.sqrt(ho)
            dq += self.o_c * self.o_area * g2 * 0.5 / math.sqrt(ho)
        hr = h - self.r_crest
        if hr > 0:
            weir = self.r_cw * g2 * self.r_len * hr ** 1.5
            orifice = self.r_co * self.r_area * g2 * math.sqrt(hr)
            if weir <= orifice:
                q += weir
                dq += 1.5 * self.r_cw * g2 * self.r_len * math.sqrt(hr)
            else:
                q += orifice
                dq += self.r_co * self.r_area * g2 * 0.5 / math.sqrt(hr)
        hs = h - self.s_crest
        if hs > 0:
            q += self.s_cw * g2 * self.s_len * hs ** 1.5
            dq += 1.5 * self.s_cw * g2 * self.s_len * math.sqrt(hs)
        return q, dq

    def step(self, target, h):
        """Solve volume(h)/DT + discharge(h)/2 = target by safeguarded Newton from the previous stage."""
        if target <= 0:
            return self.z0
        lo, hi = self.z0, None
        for _ in range(100):
            v, dv = self.volume(h)
            q, dq = self.discharge(h)
            f = v / DT + q / 2 - target
            if f > 0:
                hi = h
            else:
                lo = h
            if abs(f) < 1e-11 * max(1.0, target):
                return h
            slope = dv / DT + dq / 2
            nxt = h - f / slope if slope > 0 else None
            if nxt is None or nxt <= lo or (hi is not None and nxt >= hi):
                nxt = (lo + hi) / 2 if hi is not None else h + 1.0
            if abs(nxt - h) < 1e-12:
                return nxt
            h = nxt
        return h


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
                    "spillway_flow"])
        w.writerows(rows)


def run_site(site, rain, states):
    # storms: 6 hours (60 intervals) or more without measurable rain separate storms
    storms = []
    for i in sorted(k for k, v in rain.items() if v > 0):
        if storms and i - storms[-1][-1] <= 60:
            storms[-1].append(i)
        else:
            storms.append([i])
    basins = {b["basin_id"]: Basin(b) for b in site["basins"]}
    local = {b: [0.0] * (N + 1) for b in basins}
    for a in site["drainage_areas"]:
        tp = DD / 2 + 0.6 * a["time_of_concentration_h"]
        qp = 484 * a["acres"] / 640 / tp
        uh = [qp * ratio(j * DD / tp) for j in range(int(5 * tp / DD) + 2)]
        hydro = local[a["drains_to"]]
        hist = sorted(states[a["area_id"]])
        for storm in storms:
            begin = storm[0]
            state = [s for k, s in hist if k <= begin][-1]
            cn = a["curve_numbers"][state]
            p = prev = 0.0
            for i in range(begin, storm[-1] + 1):
                p += rain.get(i, 0.0)
                q = accumulated_runoff(p, cn)
                excess, prev = q - prev, q
                if excess > 0:
                    for j, u in enumerate(uh):
                        if i + j <= N:
                            hydro[i + j] += excess * u
    inflow = {b: list(v) for b, v in local.items()}
    stage, outq = {}, {}
    pending = set(basins)
    while pending:
        for bid in sorted(pending):
            if any(basins[u].down == bid and u in pending for u in basins):
                continue
            bs = basins[bid]
            I = inflow[bid]
            H = [bs.z0] * (N + 1)
            O = [0.0] * (N + 1)
            h, s, o = bs.z0, 0.0, 0.0
            for k in range(N):
                if I[k] == 0 and I[k + 1] == 0 and o == 0:
                    H[k + 1] = h
                    continue
                h = bs.step((I[k] + I[k + 1]) / 2 + s / DT - o / 2, h)
                s = bs.volume(h)[0]
                o = bs.discharge(h)[0]
                H[k + 1], O[k + 1] = h, o
            stage[bid], outq[bid] = H, O
            if bs.down:
                inflow[bs.down] = [x + y for x, y in zip(inflow[bs.down], O)]
            pending.discard(bid)
            break
    out = []
    for bid, bs in basins.items():
        for n, storm in enumerate(storms):
            end = storms[n + 1][0] if n + 1 < len(storms) else N + 1
            window = range(storm[0], end)
            peak_h = max(stage[bid][k] for k in window)
            out.append([site["site_id"], bid, stamp(storm[0]), f"{max(inflow[bid][k] for k in window):.3f}",
                        f"{max(outq[bid][k] for k in window):.3f}", f"{peak_h:.3f}",
                        "yes" if peak_h > bs.s_crest else "no"])
    return out


if __name__ == "__main__":
    main()
