#!/usr/bin/env python3
"""Shortcut calibration for sediment-basin-routing (authoring tool): the oracle passes, and each plausible
implementation mistake, written as a small source edit of the reference solution, fails at least one test.
Runs without Docker or a writable /app (uses local_check.py next to this file). Writes evidence/calibration.txt."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from local_check import run_solution, run_tests  # noqa: E402

TASK = HERE.parent
SRC = (TASK / "solution" / "solve.py").read_text()

ACCUM = '''                p += rain.get(i, 0.0)
                q = accumulated_runoff(p, cn)
                excess, prev = q - prev, q'''
WEIGHTED_CN = '''            cn = sum(x["curve_numbers"][[s for k, s in sorted(states[x["area_id"]]) if k <= begin][-1]] * x["acres"]
                     for x in site["drainage_areas"] if x["drains_to"] == a["drains_to"]) / \\
                sum(x["acres"] for x in site["drainage_areas"] if x["drains_to"] == a["drains_to"])'''
VOL = "        v = self.L * self.W * D + (self.L + self.W) * self.Z * D ** 2 + 4 / 3 * self.Z ** 2 * D ** 3\n" \
      "        dv = self.L * self.W + 2 * (self.L + self.W) * self.Z * D + 4 * self.Z ** 2 * D ** 2"
SHORTCUTS = {
    # ---- runoff and storms (NEH 630.10)
    "runoff from each 6-minute increment alone": [(ACCUM, "                excess = accumulated_runoff(rain.get(i, 0.0), cn)")],
    "rain accumulated over the whole season": [("            p = prev = 0.0\n", ""),
                                               ('        hist = sorted(states[a["area_id"]])', '        hist = sorted(states[a["area_id"]])\n        p = prev = 0.0')],
    "storms split only after more than 6 hours": [("if storms and i - storms[-1][-1] <= 60:", "if storms and i - storms[-1][-1] <= 61:")],
    "storms split after 5.9 hours": [("if storms and i - storms[-1][-1] <= 60:", "if storms and i - storms[-1][-1] < 60:")],
    "area state at the end of the storm": [("state = [s for k, s in hist if k <= begin][-1]", "state = [s for k, s in hist if k <= storm[-1]][-1]")],
    "area states ignored (always disturbed)": [('cn = a["curve_numbers"][state]', 'cn = a["curve_numbers"]["disturbed"]')],
    "area-weighted curve number per basin": [('            cn = a["curve_numbers"][state]', WEIGHTED_CN)],
    # ---- unit hydrograph (NEH 630.16)
    "Tp without the half unit duration": [("tp = DD / 2 + 0.6 * a[\"time_of_concentration_h\"]", "tp = 0.6 * a[\"time_of_concentration_h\"]")],
    "lag equal to Tc": [("tp = DD / 2 + 0.6 * a[\"time_of_concentration_h\"]", "tp = DD / 2 + a[\"time_of_concentration_h\"]")],
    "table 16-1 read as steps, no interpolation": [("    return Q_RATIO[j] + (Q_RATIO[j + 1] - Q_RATIO[j]) * (x - T_RATIO[j]) / (T_RATIO[j + 1] - T_RATIO[j])",
                                                    "    return Q_RATIO[j]")],
    "area in acres treated as square miles / 640 twice": [("qp = 484 * a[\"acres\"] / 640 / tp", "qp = 484 * a[\"acres\"] / 640 / 640 * 640 / 1.1 / tp")],
    # ---- stage-storage and stage-discharge (HEC-22 sec. 10.3)
    "storage as a vertical-walled prism": [(VOL, "        v = self.L * self.W * D\n        dv = self.L * self.W")],
    "orifice head from the invert": [('self.o_center, self.o_c = math.pi * d * d / 4, o["invert_elevation_ft"] + d / 2,', 'self.o_center, self.o_c = math.pi * d * d / 4, o["invert_elevation_ft"],')],
    "riser always a weir": [("            if weir <= orifice:", "            if True:")],
    "riser always an orifice": [("            if weir <= orifice:", "            if False:")],
    "riser weir length equal to its diameter": [('self.r_len, self.r_area = math.pi * rr["diameter_ft"],', 'self.r_len, self.r_area = rr["diameter_ft"],')],
    "spillway coefficient taken as dimensioned (no root 2g)": [("            q += self.s_cw * g2 * self.s_len * hs ** 1.5", "            q += self.s_cw * self.s_len * hs ** 1.5")],
    "riser weir coefficient taken as dimensioned": [("            weir = self.r_cw * g2 * self.r_len * hr ** 1.5", "            weir = self.r_cw * self.r_len * hr ** 1.5")],
    # ---- routing (NEH 630.17, HEC-22 sec. 10.5)
    "routing time step in minutes (HEC-22 eq. 10.45 units)": [("DT = 360.0                        # seconds", "DT = 6.0")],
    "inflow at the end of each step instead of the average": [("h = bs.step((I[k] + I[k + 1]) / 2 + s / DT - o / 2, h)", "h = bs.step(I[k + 1] + s / DT - o / 2, h)")],
    "each basin starts every storm empty": [("            for k in range(N):\n", "            starts = {st[0] for st in storms}\n            for k in range(N):\n                if k in starts:\n                    h, s, o = bs.z0, 0.0, 0.0\n")],
    "upstream basin outflow ignored": [("                inflow[bs.down] = [x + y for x, y in zip(inflow[bs.down], O)]", "                pass")],
    "peaks only while it rains": [("            end = storms[n + 1][0] if n + 1 < len(storms) else N + 1", "            end = storm[-1] + 1")],
}


def main():
    lines = []
    out = run_solution(TASK)
    _, failed = run_tests(TASK, out)
    lines.append("oracle: " + ("OK" if not failed else str(failed)))
    all_fail = True
    for name, edits in SHORTCUTS.items():
        src = SRC
        for old, new in edits:
            assert old in src, f"{name}: text not found in solve.py: {old!r}"
            src = src.replace(old, new)
        try:
            out = run_solution(TASK, src)
            _, failed = run_tests(TASK, out)
        except Exception as e:                          # a crash also counts as failing
            failed = [f"crash: {e}"]
        fams = sorted({f.split("[")[1].split("]")[0] for f in failed if "test_rule_family[" in f})
        every = next((f for f in failed if f.startswith("test_every_row")), "")
        wrong = every.split(": ", 2)[-1].split(" wrong")[0] if " of " in every else "-"
        all_fail &= bool(failed)
        lines.append(f"{'ok ' if failed else '!! PASSES'} {name:58s} rows wrong {wrong:>12s}  "
                     f"{len(failed):2d} failing tests, families {fams}")
    lines.append("ALL SHORTCUTS FAIL" if all_fail else "SOME SHORTCUT PASSES")
    print("\n".join(lines))
    (HERE / "evidence").mkdir(exist_ok=True)
    (HERE / "evidence" / "calibration.txt").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
