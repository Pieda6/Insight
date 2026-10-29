#!/usr/bin/env python3
"""Run shortcut versions of the reference solution against the tests.

Usage: python3 calibrate.py      (from authoring/)

Each shortcut is a plausible misreading of HEC-22 Sections 9.1.6.7 and 9.4 or of the instruction, made by
editing solution/solve.py text. A shortcut is caught when at least one test fails; the number of wrong rows
(out of all pipe and event rows) shows how widely it shows up.
"""
import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TASK = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(TASK / "tests"))
from local_check import run_solution, run_tests  # noqa: E402
import engine  # noqa: E402

SHORTCUTS = {
    "plunging test against Ei instead of Eai": [("if zk > eai:", "if zk > ei:")],
    "plunging test against the final level (Ea) by iterating once": [
        ("            if zk > eai:\n", "            if zk > eai + 0.5 * (eai - ei) * 0 + max(0.0, 2.0 * (eai - ei)):\n")],
    "every inflow pipe in the flow-weighted angle": [
        ("qj = sum(f for f, _ in joined)", "joined = joined + [(q[ip.id], ip.angle) for ip in inflow_pipes if ip.inv_down - za > eai]\n        qj = sum(f for f, _ in joined)")],
    "no 10-diameter limit on the drop": [("min(zk, 10.0 * p.d)", "zk")],
    "10-diameter limit applied to hk instead of zk": [("min(zk, 10.0 * p.d) - eai) / p.d", "min((zk - eai) / p.d, 10.0))")],
    "entrance and exit loss coefficients swapped (0.4 and 0.2)": [("K_ENTRANCE = 0.2", "K_ENTRANCE = 0.4"),
                                                                 ("K_EXIT = 0.4", "K_EXIT = 0.2")],
    "benching without interpolation (unsubmerged below 2.5)": [("            elif ratio <= 1.0:", "            elif True:")],
    "benching coefficient also at terminal structures": [("        else:\n            cb = 0.0", "        else:\n            cb = BENCH[st[\"floor\"]][1]")],
    "no zero floor on the added loss Ha": [("h_a = max(0.0, (cb + c_theta + c_p) * (eai - ei))", "h_a = (cb + c_theta + c_p) * (eai - ei)")],
    "no floor at the outflow pipe energy Ei": [("e_a = max(eai + h_a, ei)", "e_a = eai + h_a")],
    "outlet control kept in condition D": [('eaio = 0.0 if cond == "D" else ei + K_ENTRANCE * hv_i', "eaio = ei + K_ENTRANCE * hv_i")],
    "no supercritical reset in condition D": [("            hgl_i = boc_i + yn\n            egl_i = hgl_i + hv_n\n", "            pass\n")],
    "outfall exit loss 0.4 like a structure": [("K_OUTFALL = 1.0", "K_OUTFALL = 0.4")],
    "outfall exit loss only when submerged": [
        ("            egl_o = egl_a + k_exit * vhead(qp, segment(egl_a - boc_o, p.d)[0])\n        elif",
         "            egl_o = egl_a + (0.0 if at_outfall else k_exit) * vhead(qp, segment(egl_a - boc_o, p.d)[0])\n        elif")],
    "outfall starts at max(tailwater, invert + (yc + D)/2)": [
        ("    walk(outfall_pipe, tailwater, True)",
         "    _p = outfall_pipe\n    _yc = critical_depth(q[_p.id], _p.d)\n    walk(_p, max(tailwater, _p.inv_down + (_yc + _p.d) / 2), True)")],
    "case B and C exit loss with the full-pipe velocity": [
        ("egl_o = egl_a + k_exit * vhead(qp, segment(egl_a - boc_o, p.d)[0])\n        elif egl_a > boc_o + yc",
         "egl_o = egl_a + k_exit * hv_full\n        elif egl_a > boc_o + yc")],
    "friction slope from equation 9.4 in every case": [('        if case == "A":\n            sf', '        if True:\n            sf')],
    "Hi from the full-pipe velocity head always": [("ei + K_ENTRANCE * hv_i", "ei + K_ENTRANCE * hv_full")],
    "surface inflow ignored (no plunging term from the inlet)": [("        if surface > 0:\n", "        if False:\n")],
    "case B only above both normal and critical depth": [("elif egl_a > boc_o + yn:", "elif egl_a > boc_o + max(yn, yc):")],
    "Manning constant 1.49": [("KU = 1.486", "KU = 1.49")],
    "g = 32.174": [("G = 32.2", "G = 32.174")],
    "inflow angle taken as the deflection (180 - angle)": [("joined.append((q[ip.id], ip.angle))", "joined.append((q[ip.id], 180.0 - ip.angle))")],
    "C-theta with all inflow over outflow": [("c_theta = 4.5 * qj / qp", "c_theta = 4.5 * (qp - surface) / qp")],
    "benching ratio from Ei instead of Eai": [("ratio = eai / p.d", "ratio = ei / p.d")],
    "intermediate values rounded to two decimals as in Example 9.2": [
        ("        eai = max(eaio, p.d * di ** 2, 1.6 * p.d * di ** 0.67)",
         "        ei = round(ei, 2)\n        eai = round(max(eaio, p.d * di ** 2, 1.6 * p.d * di ** 0.67), 2)")],
    "full-flow friction with the exact Manning constant (0.4632, 8/3)": [
        ("sf = (qp * p.n / (KQ * p.d ** 2.67)) ** 2", "sf = (qp * p.n / (0.4632 * p.d ** (8 / 3))) ** 2")],
    "surcharge judged on the HGL (EGLa less the outflow velocity head)": [
        ('"yes" if egl_struct > st["rim_elevation_ft"] else "no"', '"yes" if egl_struct - hv_i > st["rim_elevation_ft"] else "no"')],
    "Approximate Method (Table 9.4) instead of the FHWA method": [
        ("        egl_struct = za + e_a\n",
         "        egl_struct = egl_i + (0.15 if not joined or theta_w >= 170 else 1.0) * hv_i\n")],
}


def count_wrong(out_dir):
    truth = engine.expected(TASK / "tests" / "data")
    with open(out_dir / "pipe_grades.csv", newline="") as fh:
        got = {(r["system_id"], r["event"], r["pipe_id"]): r for r in csv.DictReader(fh)}
    wrong = 0
    for w in truth:
        g = got.get(w[:3])
        if g is None or g["ds_case"] != w[3] or g["us_condition"] not in w[5] or g["surcharged"] != w[9] or \
                any(abs(float(g[k]) - v) > 0.002 for k, v in zip(("egl_ds_ft", "egl_us_ft", "structure_egl_ft"), w[6:9])):
            wrong += 1
    return wrong, len(truth)


def main():
    src = (TASK / "solution" / "solve.py").read_text()
    caught = 0
    for name, edits in SHORTCUTS.items():
        s = src
        for a, b in edits:
            assert s.count(a) >= 1, (name, a)
            s = s.replace(a, b)
        try:
            out = run_solution(TASK, source=s)
        except Exception as e:                      # noqa: BLE001
            print(f"{name}: crashed ({type(e).__name__}: {e})")
            continue
        passed, failed = run_tests(TASK, out)
        wrong, total = count_wrong(out)
        caught += bool(failed)
        print(f"{'CAUGHT' if failed else 'MISSED'}  {wrong:4d} of {total} rows wrong  {name}")
    print(f"{caught} of {len(SHORTCUTS)} shortcuts caught")
    sys.exit(0 if caught == len(SHORTCUTS) else 1)


if __name__ == "__main__":
    main()
