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


SHORTCUTS = {
    "no_tandem_exception": lambda s, n, t: TRUE_LIMIT(s, n, False),
    "floor_feet": floor_feet,
    "whole_truck_bridge_only": lambda s, n, t: TRUE_LIMIT(s, n, t) if n == 5 else 10 ** 9,
    "no_bridge_formula": lambda s, n, t: 10 ** 9,
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


def main():
    ok = cross_check()
    shutil.rmtree("/app/output", ignore_errors=True)
    print("nop:", run_tests()[0])
    solve.bridge_limit = TRUE_LIMIT
    solve.DATA = Path("/app/data")
    solve.main()
    print("oracle:", run_tests()[0])
    for name, fn in SHORTCUTS.items():
        solve.bridge_limit = fn
        shutil.rmtree("/app/output", ignore_errors=True)
        solve.main()
        summary, failed = run_tests()
        print(f"{name:26s} {summary:22s} {failed}")
    shutil.rmtree("/app/output", ignore_errors=True)
    greedy()
    summary, failed = run_tests()
    print(f"{'greedy_heaviest_first':26s} {summary:22s} {failed}")
    solve.bridge_limit = TRUE_LIMIT
    shutil.rmtree("/app/output", ignore_errors=True)
    solve.main()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
