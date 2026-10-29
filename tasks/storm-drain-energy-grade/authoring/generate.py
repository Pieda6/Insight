#!/usr/bin/env python3
"""Build the storm drain networks for storm-drain-energy-grade.

Usage: python3 generate.py            (from authoring/; writes ../environment/data, ../tests/data)

Each system is a tree of inlets and access holes draining to one outfall. Topology, inlet flows, pipe slopes,
materials and diameters are drawn first (diameters never decrease downstream and carry the 100-year flow at no
more than 85 percent of the equation 9.2 full-flow capacity). The generator then walks upstream from the outfall
with its own model (sim.py), choosing each pipe's length, each inflow pipe's drop into its structure and each
rim. While it walks it places values on purpose a little to either side of the thresholds that change an
answer: the receiving water or a structure's energy level against a pipe's crown, normal depth, critical depth
and invert (Table 9.6), the upstream grade line against the crown (Table 9.7), an inflow invert against the
initial access hole energy level (equation 9.24), and a structure's energy level against its rim (surcharge).
Every such comparison, planted or not, is kept at least 0.001 ft away from its threshold in both events, so
careful implementations cannot disagree on a letter or a yes/no.
"""
import csv
import json
import math
import random
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sim  # noqa: E402

SEED = 92024
N_SYSTEMS = 44
EVENTS = ("10-year", "100-year")
SIZES = (15, 18, 21, 24, 27, 30, 36, 42, 48, 54, 60)
MIN_MARGIN = 0.001
STATS = Counter()


def r2(x):
    return round(x + 0.0, 2)


def pick_band(rng, cands, lo=0.002, hi=0.03):
    """cands: [(value, signed margin)]; choose one whose margin lies in the band."""
    ok = [c for c in cands if c[1] is not None and lo <= abs(c[1]) <= hi]
    return rng.choice(ok)[0] if ok else None


class System:
    def __init__(self, rng, sid):
        self.rng = rng
        self.sid = sid
        n = rng.randint(5, 18)
        self.parent = {0: None}
        kids = {0: []}
        for k in range(1, n):
            choices = [j for j in range(k) if len(kids[j]) < 3]
            par = k - 1 if (rng.random() < 0.6 and len(kids[k - 1]) < 3) else rng.choice(choices)
            self.parent[k] = par
            kids[par].append(k)
            kids[k] = []
        self.kids = kids
        self.n = n
        self.type = {}
        for k in range(n):
            if not kids[k]:
                self.type[k] = "inlet"
            else:
                self.type[k] = "inlet" if rng.random() < 0.45 else "access_hole"
        self.flow = {ev: {} for ev in EVENTS}
        for k in range(n):
            if self.type[k] == "inlet":
                q10 = r2(rng.uniform(0.4, 5.5))
                self.flow["10-year"][k] = q10
                self.flow["100-year"][k] = r2(q10 * rng.uniform(1.5, 1.9))
        self.Q = {ev: {} for ev in EVENTS}
        for ev in EVENTS:
            for k in sorted(range(n), reverse=True):
                self.Q[ev][k] = self.flow[ev].get(k, 0.0) + sum(self.Q[ev][c] for c in kids[k])
        self.nval = rng.choice([0.013] * 5 + [0.012] * 2 + [0.011, 0.024])
        self.slope = {}
        for k in range(n):
            self.slope[k] = rng.uniform(0.0008, 0.004) if rng.random() < 0.7 else rng.uniform(0.012, 0.05)
        self.D = {}
        for k in sorted(range(n), reverse=True):
            need = max([self.D[c] for c in kids[k]] + [15])
            for size in SIZES:
                if size >= need and self.Q["100-year"][k] <= 0.85 * 0.46 / self.nval * (size / 12) ** 2.67 * \
                        math.sqrt(self.slope[k]):
                    break
            else:
                raise RuntimeError("no size")
            if rng.random() < 0.2 and size != SIZES[-1]:
                size = SIZES[SIZES.index(size) + 1]
            self.D[k] = size
        self.floor = {}
        for k in range(n):
            if self.type[k] == "inlet":
                self.floor[k] = rng.choice(["flat"] * 5 + ["depressed"] * 3 + ["half_benched"] * 2)
            else:
                self.floor[k] = rng.choice(["flat", "depressed", "half_benched", "full_benched", "improved"])
        self.angle = {}
        for k in range(n):
            ks = kids[k]
            if len(ks) == 1:
                self.angle[ks[0]] = rng.choice([180, 180, 180, 157, 135, 90])
            elif len(ks) == 2:
                a = rng.choice([(180, 90), (90, 90), (135, 135), (180, 135), (120, 150)])
                for c, x in zip(ks, a):
                    self.angle[c] = x
            elif len(ks) == 3:
                for c, x in zip(ks, (180, 90, 90)):
                    self.angle[c] = x
        self.L, self.inv_up, self.inv_dn, self.rim = {}, {}, {}, {}

    # ---- walking upstream ---------------------------------------------------------------------------------
    def pipe(self, k, egl_a):
        D = self.D[k] / 12.0
        return {ev: sim.pipe_state(self.Q[ev][k], D, self.nval, self.L[k], self.inv_up[k], self.inv_dn[k],
                                   egl_a[ev], self.parent[k] is None) for ev in EVENTS}

    def down_margins(self, k, egl_a):
        """Signed distances of each event's EGLa from pipe k's Table 9.6 thresholds."""
        D = self.D[k] / 12.0
        S = self.slope_real(k)
        out = []
        for ev in EVENTS:
            q = self.Q[ev][k]
            yn, yc = sim.yn_of(q, D, self.nval, S), sim.yc_of(q, D)
            if yn is None:
                return None
            for t in (0.0, yc, yn, D):
                out.append(egl_a[ev] - (self.inv_dn[k] + t))
        return out

    def slope_real(self, k):
        return (self.inv_up[k] - self.inv_dn[k]) / self.L[k]

    def up_ok(self, ps):
        for st in ps.values():
            if any(abs(st["egl_a"] - (st["inv_dn"] + t)) < MIN_MARGIN
                   for t in (0.0, st["yc"] or 0.0, st["yn"] or 0.0, st["D"])):
                return False
            if st["yn"] is None or abs(st["yn"] - st["yc"]) < MIN_MARGIN:
                return False
            ts = [st["D"], st["yc"]] + ([] if st["structural"] else [st["yn"]])
            if any(abs(st["hgli"] - (st["inv_up"] + t)) < MIN_MARGIN for t in ts):
                return False
        return True

    def choose_length(self, k, egl_a, target_ev):
        rng = self.rng
        D = self.D[k] / 12.0
        for attempt in range(60):
            L = round(rng.uniform(25, 420), 1)
            self.L[k] = L
            self.inv_up[k] = r2(self.inv_dn[k] + self.slope[k] * L)
            ps = self.pipe(k, egl_a)
            st = ps[target_ev]
            if attempt < 20 and st["case"] == "A" and rng.random() < 0.5:
                # plant the upstream grade line near the crown: try lengths that move hgl_i across toc_i
                cands = []
                sf = (self.Q[target_ev][k] * self.nval / (0.46 * D ** 2.67)) ** 2
                if abs(sf - self.slope[k]) > 1e-6:
                    base = (self.inv_dn[k] + D - st["eglo"] + st["hf"]) / (sf - self.slope[k])
                    for dl in (-3, -2, -1, 0, 1, 2, 3):
                        L2 = round(base + dl * 0.1 * (1 + attempt), 1)
                        if 25 <= L2 <= 600:
                            self.L[k] = L2
                            self.inv_up[k] = r2(self.inv_dn[k] + self.slope[k] * L2)
                            s2 = self.pipe(k, egl_a)[target_ev]
                            cands.append((L2, s2["hgli"] - (s2["inv_up"] + D)))
                L2 = pick_band(rng, cands)
                if L2 is not None:
                    self.L[k] = L2
                    self.inv_up[k] = r2(self.inv_dn[k] + self.slope[k] * L2)
                    ps = self.pipe(k, egl_a)
                    if self.up_ok(ps):
                        STATS["planted upstream grade line near the crown"] += 1
                        return ps
                self.L[k] = L
                self.inv_up[k] = r2(self.inv_dn[k] + self.slope[k] * L)
                ps = self.pipe(k, egl_a)
            if self.up_ok(ps):
                return ps
        raise RuntimeError("length")

    def structure(self, k, ps, zk, rim):
        kids = self.kids[k]
        out = {}
        for ev in EVENTS:
            inflows = [(self.Q[ev][c], zk[c], self.angle[c]) for c in kids]
            out[ev] = sim.structure_state(ps[ev], self.Q[ev][k], inflows, self.flow[ev].get(k, 0.0), rim,
                                          self.floor[k])
        return out

    def structure_ok(self, k, ps, zk, rim, ss):
        D = self.D[k] / 12.0
        za = self.inv_up[k]
        if rim - za < D + 1.0:
            return False
        for ev in EVENTS:
            s = ss[ev]
            if abs(s["egla"] - rim) < MIN_MARGIN:
                return False
            if self.type[k] == "inlet" and s["Eai"] >= rim - za - 0.05:
                return False
            for c in self.kids[k]:
                if zk[c] < 0 or abs(zk[c] - s["Eai"]) < MIN_MARGIN:
                    return False
        for c in self.kids[k]:
            self.inv_dn[c] = r2(za + zk[c])
            self.L[c] = 100.0
            self.inv_up[c] = r2(self.inv_dn[c] + self.slope[c] * 100.0)
            m = self.down_margins(c, {ev: ss[ev]["egla"] for ev in EVENTS})
            if m is None or any(abs(x) < MIN_MARGIN for x in m):
                return False
        return True

    def choose_structure(self, k, ps, target_ev):
        rng = self.rng
        D = self.D[k] / 12.0
        za = self.inv_up[k]
        kids = self.kids[k]
        eai = {ev: sim.structure_state(ps[ev], self.Q[ev][k], [], 0.0, za + 100, self.floor[k])["Eai"]
               for ev in EVENTS}
        for attempt in range(400):
            plant = attempt < 150
            zk = {}
            for c in kids:
                mode = rng.choice(["crown", "crown", "crown", "small", "small", "small", "mid", "big", "C"])
                if mode == "crown":
                    zk[c] = r2(D - self.D[c] / 12.0 + (rng.choice([0, 0, 0.05, 0.1]) if rng.random() < 0.5 else 0))
                elif mode == "small":
                    zk[c] = r2(rng.uniform(0.05, 1.5))
                elif mode == "mid":
                    zk[c] = r2(rng.uniform(1.5, 6.0))
                elif mode == "big":
                    zk[c] = r2(rng.uniform(6.0, 30.0))
                else:
                    zk[c] = None
            rim = r2(za + D + (rng.uniform(1.0, 4.0) if rng.random() < 0.5 else rng.uniform(4.0, 8.0)))
            if any(v is None for v in zk.values()):
                # place the structure's energy level between the inflow pipe's critical and normal depths
                tmp = {c: (v if v is not None else 0.0) for c, v in zk.items()}
                egla = self.structure(k, ps, tmp, rim)[target_ev]["egla"]
                for c in kids:
                    if zk[c] is None:
                        q = self.Q[target_ev][c]
                        Dc = self.D[c] / 12.0
                        yn, yc = sim.yn_of(q, Dc, self.nval, self.slope[c]), sim.yc_of(q, Dc)
                        zk[c] = r2(max(0.0, egla - za - rng.uniform(min(yn, yc), max(yn, yc))))
            tie = None
            if plant and kids and rng.random() < 0.55:
                c = rng.choice(kids)
                tie = rng.choice(["plunge", "plunge", "case"])
                if tie == "plunge":
                    cands = []
                    for j in range(-4, 5):
                        zk[c] = r2(eai[target_ev] + j * 0.01)
                        cands.append((zk[c], zk[c] - eai[target_ev]))
                    v = pick_band(rng, cands)
                    if v is None:
                        continue
                    zk[c] = v
                else:
                    q = self.Q[target_ev][c]
                    Dc = self.D[c] / 12.0
                    yn = sim.yn_of(q, Dc, self.nval, self.slope[c])
                    yc = sim.yc_of(q, Dc)
                    t = rng.choice([Dc, Dc, yn, yn, yc, yc, 0.0])
                    ss = self.structure(k, ps, zk, rim)
                    base = ss[target_ev]["egla"] - za - t
                    cands = []
                    for j in range(-5, 6):
                        zk[c] = r2(base + j * 0.01)
                        if zk[c] < 0:
                            continue
                        s2 = self.structure(k, ps, zk, rim)[target_ev]
                        cands.append((zk[c], s2["egla"] - (za + zk[c] + t)))
                    v = pick_band(rng, cands)
                    if v is None:
                        continue
                    zk[c] = v
            rim_tie = False
            if plant and rng.random() < 0.45:
                cands = []
                ss = self.structure(k, ps, zk, rim)
                for j in range(-5, 6):
                    r = r2(ss[target_ev]["egla"] + j * 0.01)
                    s2 = self.structure(k, ps, zk, r)[target_ev]
                    cands.append((r, s2["egla"] - r))
                v = pick_band(rng, cands)
                if v is not None and v - za >= D + 1.0:
                    rim = v
                    rim_tie = True
            ss = self.structure(k, ps, zk, rim)
            if self.structure_ok(k, ps, zk, rim, ss):
                if tie == "plunge":
                    STATS["planted inflow invert near the initial energy level"] += 1
                elif tie == "case":
                    STATS["planted structure energy level near an inflow pipe threshold"] += 1
                if rim_tie:
                    STATS["planted energy level near the rim"] += 1
                for c in kids:
                    self.inv_dn[c] = r2(za + zk[c])
                    if zk[c] > 10 * D:
                        STATS["drop above 10 diameters"] += 1
                self.rim[k] = rim
                return ss
        raise RuntimeError("structure")

    def build(self):
        rng = self.rng
        self.inv_dn[0] = r2(rng.uniform(20, 400))
        self.L[0] = 100.0
        self.inv_up[0] = r2(self.inv_dn[0] + self.slope[0] * 100.0)
        D0 = self.D[0] / 12.0
        for attempt in range(200):
            lift = {"E": rng.uniform(-2.0, -0.05), "D": None, "mid": rng.uniform(0.3, 0.9), "A": rng.uniform(0.3, 8.0)}
            kind = rng.choice(["E", "mid", "mid", "A", "A"])
            if kind == "E":
                tw10 = self.inv_dn[0] + lift["E"]
            elif kind == "mid":
                tw10 = self.inv_dn[0] + lift["mid"] * D0
            else:
                tw10 = self.inv_dn[0] + D0 + lift["A"]
            tw = {"10-year": r2(tw10), "100-year": r2(tw10 + rng.uniform(0.2, 4.0))}
            target = rng.choice(EVENTS)
            if attempt < 100 and rng.random() < 0.35:
                q = self.Q[target][0]
                t = rng.choice([D0, sim.yn_of(q, D0, self.nval, self.slope[0]), sim.yc_of(q, D0), 0.0])
                cands = [(r2(self.inv_dn[0] + t + j * 0.01), r2(self.inv_dn[0] + t + j * 0.01) - self.inv_dn[0] - t)
                         for j in range(-4, 5)]
                v = pick_band(rng, cands)
                if v is not None:
                    tw[target] = v
                    if target == "10-year" and tw["100-year"] < v:
                        tw["100-year"] = r2(v + rng.uniform(0.05, 1.0))
                    if target == "100-year" and tw["10-year"] > v:
                        tw["10-year"] = r2(v - rng.uniform(0.05, 1.0))
            m = self.down_margins(0, tw)
            if m is not None and all(abs(x) >= MIN_MARGIN for x in m):
                if any(abs(x) <= 0.03 for x in m):
                    STATS["planted receiving water near a threshold"] += 1
                break
        else:
            raise RuntimeError("tailwater")
        self.tw = tw
        queue = [(0, tw)]
        while queue:
            k, egl_a = queue.pop(0)
            target = rng.choice(EVENTS)
            ps = self.choose_length(k, egl_a, target)
            ss = self.choose_structure(k, ps, target)
            for c in self.kids[k]:
                queue.append((c, {ev: ss[ev]["egla"] for ev in EVENTS}))
        # every pipe still carries the 100-year flow within capacity at its realised slope
        for k in range(self.n):
            S = self.slope_real(k)
            if S <= 0 or self.Q["100-year"][k] > 0.9 * 0.46 / self.nval * (self.D[k] / 12) ** 2.67 * math.sqrt(S):
                raise RuntimeError("capacity")

    def records(self):
        rng = self.rng
        labels = list(range(1, self.n + 1))
        rng.shuffle(labels)
        name = {k: f"{self.sid}-S{labels[k]:02d}" for k in range(self.n)}
        pname = {k: f"{self.sid}-P{labels[k]:02d}" for k in range(self.n)}
        structures = [{"structure_id": name[k], "type": self.type[k], "rim_elevation_ft": self.rim[k],
                       "floor": self.floor[k]} for k in range(self.n)]
        pipes = [{"pipe_id": pname[k], "from_structure": name[k],
                  "to_structure": None if self.parent[k] is None else name[self.parent[k]],
                  "diameter_in": self.D[k], "length_ft": self.L[k], "upstream_invert_ft": self.inv_up[k],
                  "downstream_invert_ft": self.inv_dn[k], "manning_n": self.nval,
                  "angle_deg": self.angle.get(k)} for k in range(self.n)]
        structures.sort(key=lambda s: s["structure_id"])
        rng.shuffle(pipes)
        flows = [(name[k], ev, self.flow[ev][k]) for ev in EVENTS for k in range(self.n) if k in self.flow[ev]]
        return {"system_id": self.sid, "structures": structures, "pipes": pipes}, flows


def main():
    rng = random.Random(SEED)
    systems, flows, outfalls = [], [], []
    for i in range(1, N_SYSTEMS + 1):
        sid = f"SD-{i:02d}"
        for attempt in range(50):
            try:
                s = System(rng, sid)
                s.build()
                break
            except RuntimeError as e:
                STATS[f"rebuilt ({e})"] += 1
        else:
            raise SystemExit(f"could not build {sid}")
        rec, fl = s.records()
        systems.append(rec)
        flows.extend(fl)
        for ev in EVENTS:
            outfalls.append((sid, ev, s.tw[ev]))
    flows.sort()
    for root in (HERE.parent / "environment" / "data", HERE.parent / "tests" / "data"):
        root.mkdir(parents=True, exist_ok=True)
        (root / "networks.json").write_text(json.dumps(systems, indent=1) + "\n")
        with open(root / "inlet_flows.csv", "w", newline="") as fh:
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(["structure_id", "event", "flow_cfs"])
            w.writerows([(a, b, f"{c:.2f}") for a, b, c in flows])
        with open(root / "outfalls.csv", "w", newline="") as fh:
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(["system_id", "event", "receiving_water_elevation_ft"])
            w.writerows([(a, b, f"{c:.2f}") for a, b, c in outfalls])

    # summary from the generator's own model
    fl = {}
    for a, b, c in flows:
        fl.setdefault(b, {})[a] = c
    tw = {(a, b): c for a, b, c in outfalls}
    cases, conds, sur = Counter(), Counter(), Counter()
    rows = 0
    for s in systems:
        for ev in EVENTS:
            for pid, r in sim.evaluate(s, fl[ev], tw[(s["system_id"], ev)]).items():
                rows += 1
                cases[r[0]] += 1
                conds[r[1]] += 1
                sur[r[5]] += 1
    print(f"systems {len(systems)}, structures {sum(len(s['structures']) for s in systems)}, rows {rows}")
    print("downstream cases", dict(sorted(cases.items())))
    print("upstream conditions", dict(sorted(conds.items())))
    print("surcharged", dict(sur))
    for k, v in sorted(STATS.items()):
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
