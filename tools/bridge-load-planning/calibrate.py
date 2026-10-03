#!/usr/bin/env python3
"""Developer checks (not shipped): engine cross-check and shortcut solvers.

  python tools/bridge-load-planning/calibrate.py            # cross-check + every shortcut
Each shortcut writes /app/output and runs the real tests; every one must fail.
"""
import importlib.util
import random
import shutil
import subprocess
import sys
from fractions import Fraction as F
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "tasks" / "bridge-load-planning"
sys.path.insert(0, str(ROOT / "solution"))
sys.path.insert(0, str(ROOT / "tests"))
import engine  # noqa: E402
import solve  # noqa: E402

solve.DATA = ROOT / "environment" / "data"
TRUE_LIMIT = solve.bridge_limit


def cross_check(n=4000):
    configs, pallets = solve.load_problem()
    units, sliders, _ = engine.load()
    rng = random.Random(1)
    mism = 0
    for _ in range(n):
        uid = rng.choice(sorted(configs))
        cfg = rng.choice(configs[uid])
        items = rng.sample(pallets, rng.randint(1, 7))
        pos, x = [], 0
        for _, w, ln in items:
            x += rng.randint(0, 30)
            pos.append(x)
            x += ln
        if x > cfg.length:
            continue
        w = sum(i[1] for i in items)
        m = sum(F(i[1]) * (p + F(i[2], 2)) for i, p in zip(items, pos))
        a = cfg.loads(F(w), m)
        b = engine.axle_loads(units[uid], sliders[cfg.slider_id], [(i[1], p, i[2]) for i, p in zip(items, pos)])
        legal_b = not engine.violations(units[uid], sliders[cfg.slider_id], b)
        if a != b or cfg.legal(F(w), m) != legal_b:
            mism += 1
    print("engine cross-check mismatches:", mism)
    return mism == 0


def floor_feet(span, n, tt):
    feet = span // 12
    w = 500 * solve.half_up(F(feet * n, n - 1) + 12 * n + 36)
    return max(w, 68000) if tt and feet >= 36 else w


TRUE_APU = solve.apu_allowance


def _apu(fn):
    return lambda u: fn(u) if u.get("apu_installed") == "yes" else 0


SHORTCUTS = {
    "no_tandem_exception": dict(bridge=lambda s, n, t: TRUE_LIMIT(s, n, False)),
    "floor_feet": dict(bridge=floor_feet),
    "whole_truck_bridge_only": dict(bridge=lambda s, n, t: TRUE_LIMIT(s, n, t) if n == 5 else 10 ** 9),
    "no_bridge_formula": dict(bridge=lambda s, n, t: 10 ** 9),
    "apu_ignored": dict(apu=lambda u: 0),
    "apu_cfr_400": dict(apu=_apu(lambda u: min(int(u["apu_certified_weight_lb"]), 400)
                                 if u.get("apu_fully_functional") == "yes" else 0)),
    "apu_flat_550": dict(apu=_apu(lambda u: 550)),
    "apu_status_ignored": dict(apu=_apu(lambda u: min(int(u["apu_certified_weight_lb"]), 550))),
    "apu_uncapped": dict(apu=_apu(lambda u: int(u["apu_certified_weight_lb"])
                                  if u.get("apu_fully_functional") == "yes" else 0)),
}


def run_tests():
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                        str(ROOT / "tests" / "test_outputs.py")], capture_output=True, text=True)
    lines = r.stdout.strip().splitlines()
    failed = [l.split("::")[1].split(" ")[0] for l in lines if l.startswith("FAILED")]
    return lines[-1], failed


def greedy():
    """Heaviest pallet first onto the first already-open unit where it can be placed."""
    solve.bridge_limit = TRUE_LIMIT
    configs, pallets = solve.load_problem()
    best = sorted(((solve.capacity(c), c) for cs in configs.values() for c in cs),
                  key=lambda t: (-t[0], t[1].slider_id))
    used_units, trucks = set(), []
    for p in sorted(pallets, key=lambda p: (-p[1], p[0])):
        for t in trucks:
            if solve.place(t[0], t[1] + [p]) is not None:
                t[1].append(p)
                break
        else:
            cfg = next(c for _, c in best if c.unit_id not in used_units)
            used_units.add(cfg.unit_id)
            trucks.append((cfg, [p]))
    solve.write([t[0] for t in trucks], [solve.place(t[0], t[1]) for t in trucks], pallets)


def decompose_simple(max_rounds=150, seconds=20):
    """Pack by weight and floor length only (each unit at its first max-capacity slider),
    then try simple placements; failing truck sets are cut off and the packing repeated."""
    from ortools.sat.python import cp_model
    solve.bridge_limit = TRUE_LIMIT
    configs, pallets = solve.load_problem()
    total = sum(p[1] for p in pallets)
    best = {}
    for u, cs in configs.items():
        cap = max(solve.capacity(c) for c in cs)
        best[u] = (cap, next(c for c in cs if solve.capacity(c) == cap))
    k = next(i for i in range(1, 99) if sum(sorted((v[0] for v in best.values()), reverse=True)[:i]) >= total)
    units = sorted(best)
    cuts = []
    for _ in range(max_rounds):
        md = cp_model.CpModel()
        P, C = len(pallets), len(units)
        x = {(p, c): md.NewBoolVar("") for p in range(P) for c in range(C)}
        y = [md.NewBoolVar("") for _ in range(C)]
        for p in range(P):
            md.AddExactlyOne(x[p, c] for c in range(C))
        md.Add(sum(y) <= k)
        for c, u in enumerate(units):
            cap, cfg = best[u]
            md.Add(sum(pallets[p][1] * x[p, c] for p in range(P)) <= cap * y[c])
            md.Add(sum(pallets[p][2] * x[p, c] for p in range(P)) <= cfg.length * y[c])
        for c, ps in cuts:
            md.AddBoolOr([x[p, c].Not() for p in ps])
        sv = cp_model.CpSolver()
        sv.parameters.max_time_in_seconds = seconds
        sv.parameters.num_workers = 8
        if sv.Solve(md) not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return "no 9-truck packing found" if k == 9 else f"stopped at k={k}"
        trucks = []
        bad = None
        for c, u in enumerate(units):
            ps = [p for p in range(P) if sv.Value(x[p, c])]
            if ps:
                pos = solve.place(best[u][1], [pallets[p] for p in ps])
                if pos is None:
                    bad = (c, ps)
                    break
                trucks.append((best[u][1], pos))
        if bad is None:
            solve.write([t[0] for t in trucks], [t[1] for t in trucks], pallets)
            return f"found k={k} after {len(cuts)} failed placements"
        cuts.append(bad)
    return f"gave up after {max_rounds} rounds at k={k}"


def main():
    ok = cross_check()
    shutil.rmtree("/app/output", ignore_errors=True)
    print("nop:", run_tests()[0])
    solve.bridge_limit = TRUE_LIMIT
    solve.DATA = Path("/app/data")
    solve.main()
    print("oracle:", run_tests()[0])
    for name, sc in SHORTCUTS.items():
        solve.bridge_limit = sc.get("bridge", TRUE_LIMIT)
        solve.apu_allowance = sc.get("apu", TRUE_APU)
        shutil.rmtree("/app/output", ignore_errors=True)
        try:
            solve.main()
        except (SystemExit, AssertionError) as e:
            print(f"{name:26s} solver stopped: {e!r}")
        summary, failed = run_tests()
        print(f"{name:26s} {summary:22s} {failed}")
    solve.bridge_limit, solve.apu_allowance = TRUE_LIMIT, TRUE_APU
    shutil.rmtree("/app/output", ignore_errors=True)
    greedy()
    summary, failed = run_tests()
    print(f"{'greedy_heaviest_first':26s} {summary:22s} {failed}")
    shutil.rmtree("/app/output", ignore_errors=True)
    note = decompose_simple()
    summary, failed = run_tests()
    print(f"{'weight_length_then_place':26s} {summary:22s} {failed}  ({note})")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
