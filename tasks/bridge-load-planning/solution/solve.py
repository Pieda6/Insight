#!/usr/bin/env python3
"""Reference solution: legal minimum-truck load plan under 23 CFR 658.17.

Every axle load is linear in (W, M), where W is a trailer's payload and M its first moment
about the trailer's inside front wall. For a fixed unit and slider setting, the legal M for
a given W is therefore an interval, and the largest legal W is that unit's capacity.
The weight bound (fewest units whose capacities cover the freight) gives a lower bound on
the truck count. CP-SAT then packs the pallets onto that many units and chooses slider
settings, with the densest-first moment bounds so that each truck's centre of gravity can
reach its legal window; each truck then gets exact integer positions (CP-SAT with no
overlap). A packing that cannot be placed is cut off and the search repeats.
"""
import csv
import json
import os
from fractions import Fraction as F
from pathlib import Path

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

DATA = Path("/app/data")
OUT = Path("/app/output")

SINGLE, TANDEM, GROSS = 20000, 34000, 80000


def read(name):
    with open(DATA / name, newline="") as f:
        return list(csv.DictReader(f))


def half_up(x):
    """Round a non-negative Fraction to the nearest integer, halves up."""
    return int(F(x) + F(1, 2)) if F(x) >= 0 else -int(-F(x) + F(1, 2))


def bridge_limit(span_in, n, two_tandems):
    feet = half_up(F(span_in, 12))
    w = 500 * (F(feet * n, n - 1) + 12 * n + 36)
    w = 500 * half_up(w / 500)
    if two_tandems and feet >= 36:
        w = max(w, 68000)
    return w


class Config:
    """One unit with one slider setting."""

    def __init__(self, unit, slider):
        self.unit_id = unit["unit_id"]
        self.slider_id = slider["slider_position_id"]
        self.length = int(unit["trailer_inside_length_in"])
        self.kp = int(unit["kingpin_x_in"])
        self.x = [int(unit["steer_x_in"]), int(unit["drive1_x_in"]), int(unit["drive2_x_in"]),
                  int(slider["trailer1_x_in"]), int(slider["trailer2_x_in"])]
        self.tare = [int(slider[k]) for k in ("tare_steer_lb", "tare_drive1_lb", "tare_drive2_lb",
                                              "tare_trailer1_lb", "tare_trailer2_lb")]
        s, d, t = F(self.x[0]), F(self.x[1] + self.x[2], 2), F(self.x[3] + self.x[4], 2)
        k = F(self.kp)
        # Each axle load = tare + a*W + b*M (exact coefficients).
        rt_w, rt_m = -k / (t - k), 1 / (t - k)          # trailer tandem reaction
        kp_w, kp_m = 1 - rt_w, -rt_m                     # kingpin reaction
        fs, fd = (d - k) / (d - s), (k - s) / (d - s)    # kingpin split steer / drive
        self.coef = [(fs * kp_w, fs * kp_m),
                     (fd * kp_w / 2, fd * kp_m / 2), (fd * kp_w / 2, fd * kp_m / 2),
                     (rt_w / 2, rt_m / 2), (rt_w / 2, rt_m / 2)]
        # Limits on sums of consecutive axle groups: (first, last, limit).
        self.limits = [(0, 0, SINGLE), (1, 2, TANDEM), (3, 4, TANDEM), (0, 4, GROSS)]
        for i in range(5):
            for j in range(i + 1, 5):
                self.limits.append((i, j, bridge_limit(self.x[j] - self.x[i], j - i + 1, (i, j) == (1, 4))))

    def loads(self, w, m):
        return [F(self.tare[i]) + a * w + b * m for i, (a, b) in enumerate(self.coef)]

    def group_rows(self):
        """Yield (a, b, rhs) meaning a*W + b*M <= rhs for every limit."""
        for i, j, lim in self.limits:
            a = sum(self.coef[q][0] for q in range(i, j + 1))
            b = sum(self.coef[q][1] for q in range(i, j + 1))
            yield a, b, lim - sum(self.tare[i:j + 1])

    def legal(self, w, m):
        ld = self.loads(w, m)
        return all(sum(ld[i:j + 1]) <= lim for i, j, lim in self.limits)

    def m_interval(self, w):
        lo, hi = F(-10 ** 12), F(10 ** 12)
        for a, b, rhs in self.group_rows():
            r = rhs - a * w
            if b > 0:
                hi = min(hi, r / b)
            elif b < 0:
                lo = max(lo, r / b)
            elif r < 0:
                return None
        return (lo, hi) if lo <= hi else None


def load_problem():
    units = {u["unit_id"]: u for u in read("units.csv")}
    configs = {}
    for s in read("sliders.csv"):
        configs.setdefault(s["unit_id"], []).append(Config(units[s["unit_id"]], s))
    pallets = [(p["pallet_id"], int(p["weight_lb"]), int(p["length_in"])) for p in read("pallets.csv")]
    return configs, pallets


def place(cfg, items):
    """Integer front-edge positions for `items` [(id, w, len)] legal on `cfg`, or None."""
    w = sum(i[1] for i in items)
    if sum(i[2] for i in items) > cfg.length:
        return None
    iv = cfg.m_interval(F(w))
    if iv is None:
        return None
    lo, hi = iv
    orders = [sorted(items, key=lambda i: (-F(i[1], i[2]), i[0])),
              sorted(items, key=lambda i: (F(i[1], i[2]), i[0])),
              sorted(items, key=lambda i: (-i[1], i[0])), sorted(items, key=lambda i: (i[1], i[0]))]
    for order in orders:
        n = len(order)
        # 2*M = sum w*(2p + len) ; keep everything integer by doubling.
        c = np.zeros(n)
        cons = []
        rows = []
        for q in range(n - 1):
            r = np.zeros(n)
            r[q + 1], r[q] = 1, -1
            rows.append(r)
        if rows:
            cons.append(LinearConstraint(np.array(rows), [order[q][2] for q in range(n - 1)], np.inf))
        wv = np.array([2.0 * it[1] for it in order])
        base = sum(it[1] * it[2] for it in order)
        target_lo, target_hi = float(2 * lo - base), float(2 * hi - base)
        cons.append(LinearConstraint(wv.reshape(1, -1), target_lo + 1, target_hi - 1))
        ub = [cfg.length - it[2] for it in order]
        res = milp(c, constraints=cons, integrality=np.ones(n), bounds=Bounds(np.zeros(n), ub))
        if res.status != 0:
            continue
        pos = [int(round(v)) for v in res.x]
        m = sum(F(it[1]) * (p + F(it[2], 2)) for it, p in zip(order, pos))
        if cfg.legal(F(w), m) and all(pos[q + 1] >= pos[q] + order[q][2] for q in range(n - 1)) \
                and all(0 <= p <= cfg.length - it[2] for it, p in zip(order, pos)):
            return {it[0]: p for it, p in zip(order, pos)}
    return None


def capacity(cfg):
    """Largest payload (lb) for which some moment is legal on this configuration."""
    lo, hi = 0, 200000
    while lo < hi:
        mid = (lo + hi + 1) // 2
        iv = cfg.m_interval(F(mid))
        if iv is not None and iv[1] >= 0 and iv[0] <= mid * cfg.length:
            lo = mid
        else:
            hi = mid - 1
    return lo


def int_rows(cfg):
    """Legality rows as integers: a*W + b*(2M) <= rhs, all exact."""
    from math import lcm
    rows = []
    for a, b, rhs in cfg.group_rows():
        b2 = F(b) / 2
        d = lcm(F(a).denominator, b2.denominator, F(rhs).denominator)
        rows.append((int(a * d), int(b2 * d), int(rhs * d)))
    return rows


def solve_plan(cands, pallets, k, seconds, min_load=None):
    """Exact CP-SAT model: assignment, slider choice and integer positions together.

    cands: configurations (unit + slider). Each pallet goes on exactly one used
    configuration, at most one configuration per unit, at most k configurations. Positions
    are optional intervals with no overlap on the floor; twice the payload moment is
    sum(w * (2*front + len)), which keeps every legality row linear and integral.
    """
    from ortools.sat.python import cp_model

    P, C = len(pallets), len(cands)
    md = cp_model.CpModel()
    x = {(p, c): md.NewBoolVar("") for p in range(P) for c in range(C)}
    y = [md.NewBoolVar("") for _ in range(C)]
    start = {}
    for p in range(P):
        md.AddExactlyOne(x[p, c] for c in range(C))
    for u in {c.unit_id for c in cands}:
        md.AddAtMostOne(y[c] for c in range(C) if cands[c].unit_id == u)
    md.Add(sum(y) <= k)
    for c, cfg in enumerate(cands):
        if min_load is not None:  # implied by the weight bound: little spare capacity overall
            md.Add(sum(pallets[p][1] * x[p, c] for p in range(P)) >= min_load[c] * y[c])
        ivs, mom = [], []
        for p, (_, w, ln) in enumerate(pallets):
            md.AddImplication(x[p, c], y[c])
            s_ = md.NewIntVar(0, cfg.length - ln, "")
            start[p, c] = s_
            ivs.append(md.NewOptionalFixedSizeIntervalVar(s_, ln, x[p, c], ""))
            m = md.NewIntVar(0, w * (2 * cfg.length), "")
            md.Add(m == w * (2 * s_ + ln)).OnlyEnforceIf(x[p, c])
            md.Add(m == 0).OnlyEnforceIf(x[p, c].Not())
            mom.append(m)
        md.AddNoOverlap(ivs)
        wsum = sum(pallets[p][1] * x[p, c] for p in range(P))
        m2 = sum(mom)
        md.Add(sum(pallets[p][2] * x[p, c] for p in range(P)) <= cfg.length)
        for a, b2, rhs in int_rows(cfg):
            md.Add(a * wsum + b2 * m2 <= rhs).OnlyEnforceIf(y[c])
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = seconds
    solver.parameters.num_workers = max(4, os.cpu_count() or 4)
    solver.parameters.random_seed = 0
    st = solver.Solve(md)
    if st == cp_model.INFEASIBLE:
        return "infeasible"
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None
    plan = []
    for c, cfg in enumerate(cands):
        pos = {pallets[p][0]: solver.Value(start[p, c]) for p in range(P) if solver.Value(x[p, c])}
        if pos:
            plan.append((cfg, pos))
    return plan


def pack(cands, pallets, k, cuts, spare, seconds, seed=0):
    """CP-SAT packing with necessary centre-of-gravity conditions.

    For a pallet set S packed against the front wall, 2*moment is smallest when pallets go
    densest-first (weight per inch, Smith's rule), giving
        Q(S) = sum w_i*len_i + 2 * sum_{i<j in S} min(w_i*len_j, w_j*len_i);
    packed against the rear wall the largest value is 2*L*W - Q(S). A legal placement
    needs the legal moment interval for W to meet [Q, 2LW - Q]. Because densest-first is a
    single global order, Q is linear once each pallet's "floor ahead of it" is a variable.
    Exact placement is checked afterwards.
    """
    from ortools.sat.python import cp_model

    P, C = len(pallets), len(cands)
    md = cp_model.CpModel()
    x = {(p, c): md.NewBoolVar("") for p in range(P) for c in range(C)}
    y = [md.NewBoolVar("") for _ in range(C)]
    for p in range(P):
        md.AddExactlyOne(x[p, c] for c in range(C))
    for u in {c.unit_id for c in cands}:
        md.AddAtMostOne(y[c] for c in range(C) if cands[c].unit_id == u)
    md.Add(sum(y) <= k)
    # Densest-first is one global order, so a pallet's offset in the front-packed layout is
    # the floor length of the denser pallets on the same truck (a linear expression).
    rank = sorted(range(P), key=lambda p: (-F(pallets[p][1], pallets[p][2]), p))
    for c, cfg in enumerate(cands):
        W = sum(pallets[p][1] * x[p, c] for p in range(P))
        cap = capacity(cfg)
        md.Add(W <= cap * y[c])
        md.Add(W >= (cap - spare) * y[c])
        md.Add(sum(pallets[p][2] * x[p, c] for p in range(P)) <= cfg.length * y[c])
        q_terms = [pallets[p][1] * pallets[p][2] * x[p, c] for p in range(P)]
        ahead = 0
        for p in rank:
            w = pallets[p][1]
            t = md.NewIntVar(0, w * cfg.length, "")
            md.Add(t >= w * ahead).OnlyEnforceIf(x[p, c])
            q_terms.append(2 * t)
            ahead = ahead + pallets[p][2] * x[p, c]
        Q = sum(q_terms)
        for a, b2, rhs in int_rows(cfg):
            if b2 > 0:     # moment upper limit: the most forward packing must reach it
                md.Add(a * W + b2 * Q <= rhs).OnlyEnforceIf(y[c])
            elif b2 < 0:   # moment lower limit: the most rearward packing must reach it
                md.Add(a * W + b2 * (2 * cfg.length * W - Q) <= rhs).OnlyEnforceIf(y[c])
    for c, ps in cuts:
        md.AddBoolOr([x[p, c].Not() for p in ps] + [y[c].Not()])
    sv = cp_model.CpSolver()
    sv.parameters.max_time_in_seconds = seconds
    sv.parameters.num_workers = max(4, os.cpu_count() or 4)
    sv.parameters.random_seed = seed
    st = sv.Solve(md)
    if st == cp_model.INFEASIBLE:
        return "infeasible"
    if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None
    return [(c, [p for p in range(P) if sv.Value(x[p, c])]) for c in range(C) if sv.Value(y[c])]


def main():
    configs, pallets = load_problem()
    total = sum(p[1] for p in pallets)
    caps = {u: max(capacity(c) for c in cfgs) for u, cfgs in configs.items()}
    order = sorted(caps.values(), reverse=True)
    k = next(i for i in range(1, len(order) + 1) if sum(order[:i]) >= total)  # weight lower bound
    while True:
        best_k = sorted(caps.values(), reverse=True)[:k]
        spare = sum(best_k) - total  # capacity left over in the strongest possible k-unit fleet
        cands = [c for u in sorted(configs) if caps[u] >= best_k[-1] - spare
                 for c in configs[u] if capacity(c) >= caps[u] - spare]
        cuts = []
        while True:
            packing = None
            for seed in range(40):  # restart with a new seed every 2 minutes
                packing = pack(cands, pallets, k, cuts, spare, 120, seed)
                if packing is not None:
                    break
            if packing == "infeasible":
                break
            if packing is None:
                raise SystemExit("packing search hit its time limit")
            placed, bad = [], None
            for c, ps in packing:
                items = [pallets[p] for p in ps]
                plan = solve_plan([cands[c]], items, 1, 60)
                if not isinstance(plan, list) or not plan:
                    bad = (c, ps)
                    break
                placed.append(plan[0])
            if bad is None:
                for cfg, pos in placed:  # exact re-check
                    w = sum(p[1] for p in pallets if p[0] in pos)
                    m = sum(F(p[1]) * (pos[p[0]] + F(p[2], 2)) for p in pallets if p[0] in pos)
                    assert cfg.legal(F(w), m)
                write([c for c, _ in placed], [p for _, p in placed], pallets)
                return
            cuts.append(bad)
        k += 1


def write(cfgs, positions, pallets):
    OUT.mkdir(parents=True, exist_ok=True)
    wmap = {p[0]: p for p in pallets}
    rows, units, axles = [], [], {}
    for cfg, pos in zip(cfgs, positions):
        units.append((cfg.unit_id, cfg.slider_id))
        w = sum(wmap[i][1] for i in pos)
        m = sum(F(wmap[i][1]) * (p + F(wmap[i][2], 2)) for i, p in pos.items())
        axles[cfg.unit_id] = [half_up(v) for v in cfg.loads(F(w), m)]
        rows += [(i, cfg.unit_id, p) for i, p in pos.items()]
    with open(OUT / "load_plan.csv", "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["pallet_id", "unit_id", "position_in"])
        wr.writerows(sorted(rows))
    with open(OUT / "units.csv", "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["unit_id", "slider_position_id"])
        wr.writerows(sorted(units))
    (OUT / "summary.json").write_text(json.dumps(
        {"units_used": len(units), "axle_loads_lb": dict(sorted(axles.items()))}, indent=2) + "\n")


if __name__ == "__main__":
    main()
