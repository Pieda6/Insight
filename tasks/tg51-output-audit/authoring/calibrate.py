"""Shortcut solutions: solve.py with one reading changed by text replacement. Each must fail at least one test."""
import sys
sys.dont_write_bytecode = True       # never leave __pycache__ in the submitted task folder
import csv
from pathlib import Path

import engine_loader
import local_check

TASK = Path(__file__).resolve().parent.parent
SOLVE = (TASK / "solution" / "solve.py").read_text()
TOL = 0.003
S = {
    "Fahrenheit read as Celsius": [('        if main["temperature_unit"] == "F":\n            t = (t - 32) * 5 / 9\n', "")],
    "pressure unit not converted to kPa": [(' * TO_KPA[main["pressure_unit"]]', "")],
    "electrometer factor of the wrong range": [('["pelec"][main["electrometer_range"]]', '["pelec"]["low"]')],
    "polarity correction ignored": [("p_pol = abs((m_plus - m_minus) / (2 * m))", "p_pol = 1.0")],
    "polarity correction over the other reading": [("p_pol = abs((m_plus - m_minus) / (2 * m))",
                                                    "p_pol = abs((m_plus - m_minus) / (2 * mo))")],
    "recombination correction ignored": [("p_ion = (1 - v_ratio) / (m / ml - v_ratio)", "p_ion = 1.0")],
    "continuous-beam recombination formula": [("p_ion = (1 - v_ratio) / (m / ml - v_ratio)",
                                               "p_ion = (1 - v_ratio ** 2) / (m / ml - v_ratio ** 2)")],
    "radial profile correction ignored": [("        return interp(prof, 0.0) / (sum(inside) / len(inside))",
                                           "        return 1.0")],
    "profile averaged over the whole scan": [("        half = ch[\"active_length_cm\"] / 2", "        half = 99.0")],
    "depth scans not shifted": [('return frac * ch["cavity_radius_cm"] if ch["type"] == "cylindrical" else 0.0',
                                 "return 0.0")],
    "dose at dmax from %dd(10)x": [("return d10, d10 / (open_pct / 100)", "return d10, d10 / (x / 100)")],
    "SAD beams through the depth dose": [('        if b["setup"] == "SAD":\n', "        if False:\n")],
    "kR50 formulas swapped": [('        if kind == "cylindrical":\n            return 0.9905', '        if kind != "cylindrical":\n            return 0.9905')],
    "electrometer factor kept for the cross-calibrated chamber": [(
        'p_elec = 1.0 if cross_calibrated else self.clinic', 'p_elec = self.clinic')],
}


def main():
    truth = engine_loader.truth()
    ok = True
    print(f"{len(S)} shortcuts, each must fail at least one test")
    for name, reps in S.items():
        src = SOLVE
        for old, new in reps:
            assert src.count(old) == 1, (name, old)
            src = src.replace(old, new)
        out = local_check.run_solution(TASK, src)
        with open(out / "dose_per_mu.csv") as fh:
            got = {r["beam_id"]: (float(r["dose_ref_cgy_per_mu"]), float(r["dose_dmax_cgy_per_mu"])) for r in csv.DictReader(fh)}
        wrong = sum(not any(abs(got[k][0] / p[0] - 1) <= TOL and abs(got[k][1] / p[1] - 1) <= TOL for p in v)
                    for k, v in truth.items())
        failed = bool(local_check.run_tests(TASK, out)[1])
        ok &= failed
        print(f"{'caught' if failed else 'MISSED'}  {wrong:4d} of {len(truth)} beams wrong  {name}")
    print("CALIBRATION:", "every shortcut caught" if ok else "SOME SHORTCUT PASSES")


if __name__ == "__main__":
    main()
