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

ACCUM = """                p += rain.get(i, 0.0)
                q = accumulated_runoff(p, cn)
                excess, prev = q - prev, q"""
CN_LINE = '            cn, u = a["curve_numbers"][state], uh[state]'
WEIGHTED = """            cn = sum(x["curve_numbers"][[s for k, s in sorted(states[x["area_id"]]) if k <= storm[0]][-1]] * x["acres"]
                     for x in site["drainage_areas"] if x["drains_to"] == a["drains_to"]) / \\
                sum(x["acres"] for x in site["drainage_areas"] if x["drains_to"] == a["drains_to"])
            u = uh[state]"""
RISER = """            q += min(self.r_cw * G2 * math.pi * self.r_d * hr ** 1.5,
                     self.r_co * math.pi * self.r_d ** 2 / 4 * G2 * math.sqrt(hr))"""
COUPLED = """                hm = solve_increasing(main_balance, m.bottom, hm)
                hf = fore_level(hm)"""
LAGGED = """                hf = fore_level(hm)
                hm = solve_increasing(lambda x: m.volume(x) / DT - f.divider(hf, x) / 2 + m.outflow(x)[0] / 2 - tm,
                                      m.bottom, hm)"""
SINGLE = """            for k in range(N):
                if Im[k] == 0 and Im[k + 1] == 0 and o == 0:"""
RESET = """            starts = {st[0] for st in storms}
            for k in range(N):
                if k in starts:
                    h, s, o = m.bottom, 0.0, 0.0
                if Im[k] == 0 and Im[k + 1] == 0 and o == 0:"""
SHORTCUTS = {
    # ---- runoff and storms (NEH 630.10)
    "runoff from each 6-minute increment alone": [(ACCUM, "                excess = accumulated_runoff(rain.get(i, 0.0), cn)")],
    "rain accumulated over the whole season": [("            p = prev = 0.0\n", ""),
                                               ('        hist = sorted(states[a["area_id"]])', '        hist = sorted(states[a["area_id"]])\n        p = prev = 0.0')],
    "storms split only after more than 6 hours": [("if storms and i - storms[-1][-1] <= 60:", "if storms and i - storms[-1][-1] <= 61:")],
    "storms split after 5.9 hours": [("if storms and i - storms[-1][-1] <= 60:", "if storms and i - storms[-1][-1] < 60:")],
    "area state at the end of the storm": [("state = [s for k, s in hist if k <= storm[0]][-1]", "state = [s for k, s in hist if k <= storm[-1]][-1]")],
    "area states ignored for the curve number": [(CN_LINE, '            cn, u = a["curve_numbers"]["disturbed"], uh[state]')],
    "area-weighted curve number per cell": [(CN_LINE, WEIGHTED)],
    # ---- time of concentration (TR-55 ch. 3) and unit hydrograph (NEH 630.16)
    "time of concentration not changed by the state": [(CN_LINE, '            cn, u = a["curve_numbers"][state], uh["stabilized"]')],
    "no TR-55 minimum time of concentration": [("    return max(tc, 0.1)", "    return tc")],
    "paved shallow flow treated as unpaved": [('(20.3282 if sc["paved"] else 16.1345)', "16.1345")],
    "Tp without the half unit duration": [("tp = DD / 2 + 0.6 * time_of_concentration(", "tp = 0.6 * time_of_concentration(")],
    "table 16-1 read as steps": [("    return Q_RATIO[j] + (Q_RATIO[j + 1] - Q_RATIO[j]) * (x - T_RATIO[j]) / (T_RATIO[j + 1] - T_RATIO[j])",
                                  "    return Q_RATIO[j]")],
    # ---- stage-storage and stage-discharge (HEC-22 sec. 10.3)
    "trapezoid as a vertical-walled prism": [("            return L * W * D + (L + W) * Z * D * D + 4 / 3 * Z * Z * D ** 3", "            return L * W * D")],
    "contours by average end area": [("self.cum.append(self.cum[-1] + (z2 - z1) * (a1 + math.sqrt(a1 * a2) + a2) / 3)",
                                      "self.cum.append(self.cum[-1] + (z2 - z1) * (a1 + a2) / 2)"),
                                     ("return self.cum[i] + (h - z1) * (a1 + math.sqrt(a1 * a) + a) / 3",
                                      "return self.cum[i] + (h - z1) * (a1 + a) / 2")],
    "orifice head from the invert": [('self.o_area, self.o_cent, self.o_c = math.pi * dia ** 2 / 4, o["invert_elevation_ft"] + dia / 2,',
                                      'self.o_area, self.o_cent, self.o_c = math.pi * dia ** 2 / 4, o["invert_elevation_ft"],')],
    "riser always a weir": [(RISER, "            q += self.r_cw * G2 * math.pi * self.r_d * hr ** 1.5")],
    "riser weir length equal to its diameter": [("self.r_cw * G2 * math.pi * self.r_d * hr ** 1.5", "self.r_cw * G2 * self.r_d * hr ** 1.5")],
    "spillway coefficient taken as dimensioned": [("spill = self.s_cw * G2 * self.s_len * hs ** 1.5", "spill = self.s_cw * self.s_len * hs ** 1.5")],
    # ---- forebay divider and coupling
    "divider weir never submerged": [("                q *= (1 - (h2 / h1) ** 1.5) ** 0.385", "                pass")],
    "divider orifice head always from its centroid": [("q += orifice_flow(self.d_c, self.d_area, self.d_cent, up, dn)",
                                                       "q += orifice_flow(self.d_c, self.d_area, self.d_cent, up)")],
    "no flow back through the divider": [("        up, dn, sign = (hf, hm, 1.0) if hf >= hm else (hm, hf, -1.0)",
                                         "        if hf < hm:\n            return 0.0\n        up, dn, sign = hf, hm, 1.0")],
    "forebay routed against the main cell's previous level": [(COUPLED, LAGGED)],
    "forebay outflow reported as a magnitude": [('f"{max(O[k] for k in window):.3f}"', 'f"{max(abs(O[k]) for k in window):.3f}"')],
    # ---- routing (NEH 630.17, HEC-22 sec. 10.5)
    "routing time step in minutes": [("DT = 360.0", "DT = 6.0")],
    "inflow at the end of each step": [("target = (Im[k] + Im[k + 1]) / 2 + s / DT - o / 2", "target = Im[k + 1] + s / DT - o / 2")],
    "single cells start every storm empty": [(SINGLE, RESET)],
    "outflow of upstream main cells ignored": [("            free_in[m.down] = [x + y for x, y in zip(free_in[m.down], Om)]", "            pass")],
    "values only while it rains": [("end = storms[n + 1][0] if n + 1 < len(storms) else N + 1", "end = storm[-1] + 1")],
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
