"""Shortcut solutions: each is solve.py with one reading changed by text replacement. Prints how many of the 1,080
points each gets wrong (more than 0.1 percent from the engine) and which tests fail. Every shortcut must fail."""
import sys
sys.dont_write_bytecode = True       # never leave __pycache__ in the submitted task folder
import csv
from pathlib import Path

import local_check

TASK = Path(__file__).resolve().parent.parent
SOLVE = (TASK / "solution" / "solve.py").read_text()

SHORTCUTS = {
    "radial dose function interpolated linearly": [
        ("return math.exp((1 - w) * math.log(self.g[j][1]) + w * math.log(self.g[j + 1][1]))",
         "return (1 - w) * self.g[j][1] + w * self.g[j + 1][1]")],
    "point-source radial dose function g_P used in 2D": [
        ('d["radial_dose_function_line_source"]', 'd["radial_dose_function_point_source"]')],
    "point-source geometry function 1/r^2": [
        ("        th = math.radians(theta)\n", "        return 1.0 / (r * r)\n        th = math.radians(theta)\n")],
    "1D formalism with phi_an instead of F(r, theta)": [
        ("        if theta > 90.0:\n            theta = 180.0 - theta\n",
         "        tab = self.phi\n        j, w = lerp_index([a for a, _ in tab], r)\n"
         "        return (1 - w) * tab[j][1] + w * tab[j + 1][1]\n"),
        ('        self.g_ref = self.G(REF_R, REF_THETA)', '        self.g_ref = self.G(REF_R, REF_THETA)\n'
         '        self.phi = d["anisotropy_factor_1d"]')],
    "F held at the last tabulated angle (no F = 1 at 90 degrees)": [
        ('self.f_theta = F["theta_deg"] + [90.0]', 'self.f_theta = F["theta_deg"]'),
        ('self.f = F["F"] + [[1.0] * len(self.f_r)]', 'self.f = F["F"]')],
    "F extrapolated linearly beyond the tabulated distances": [
        ("        j, w = lerp_index(self.f_r, r)\n",
         "        j, w = lerp_index(self.f_r, r)\n        rs = self.f_r\n"
         "        j = 0 if r < rs[0] else (len(rs) - 2 if r > rs[-1] else j)\n"
         "        w = (r - rs[j]) / (rs[j + 1] - rs[j])\n")],
    "radial dose function extrapolated beyond the table (ln g linear)": [
        ("        j, w = lerp_index([a for a, _ in self.g], r)\n",
         "        j, w = lerp_index([a for a, _ in self.g], r)\n        xs = [a for a, _ in self.g]\n"
         "        j = 0 if r < xs[0] else (len(xs) - 2 if r > xs[-1] else j)\n"
         "        w = (r - xs[j]) / (xs[j + 1] - xs[j])\n")],
    "angles beyond 90 degrees not mirrored": [("        if theta > 90.0:\n            theta = 180.0 - theta\n", "")],
    "capsule length 0.45 cm used for L": [('self.L = d["active_length_cm"]', 'self.L = 0.45')],
    "mean life taken as 1.44 T1/2": [("half_h / math.log(2), centre", "half_h * 1.44, centre")],
    "apparent activity used as if it were U": [
        ('return value * float(b["vendor_conversion_U_per_mCi"])', "return value")],
    "apparent activity converted with fixed 1.270 / 1.293 (not the vendor's coefficient)": [
        ('return value * float(b["vendor_conversion_U_per_mCi"])',
         'return value * (1.270 if float(b["vendor_conversion_U_per_mCi"]) < 1.29 else 1.293)')],
    "batch total read as per seed": [('return value / int(b["seeds_in_batch"])', "return value")],
    "no decay from calibration to implant": [("sk = strength_per_seed(b) * math.exp(-math.log(2) * hours / half_h)",
                                              "sk = strength_per_seed(b)")],
    "calibration time zone offset ignored": [('dt.datetime.fromisoformat(b["calibrated_at"])',
                                              'dt.datetime.fromisoformat(b["calibrated_at"][:16]).replace('
                                              'tzinfo=dt.timezone.utc)')],
    "implant time without daylight saving (EST all year)": [("offset_h = 4 if start <= wall < end else 5",
                                                              "offset_h = 5")],
    "implant time read as UTC": [("offset_h = 4 if start <= wall < end else 5", "offset_h = 0")],
    "duplicate detections kept": [('if s["review"] == "accepted":', "if True:")],
    "first end marker taken as the seed centre": [("centre = [(u + v) / 2 for u, v in zip(a, c)]", "centre = a")],
    "seed axis ignored (every point on the transverse plane)": [
        ("dose_cgy += source.dose_rate(sk, r, math.degrees(math.acos(cos_t))) * mean_life_h",
         "dose_cgy += source.dose_rate(sk, r, 90.0) * mean_life_h")],
    "F interpolated in cos(theta) instead of theta": [
        ("        i, u = lerp_index(self.f_theta, theta)\n",
         "        i, u = lerp_index(self.f_theta, theta)\n"
         "        c0, c1 = math.cos(math.radians(self.f_theta[i])), math.cos(math.radians(self.f_theta[i + 1]))\n"
         "        u = (math.cos(math.radians(theta)) - c0) / (c1 - c0)\n")],
    "dose rate only (no total to complete decay), as Gy per day times 30": [
        ("* mean_life_h\n", "* 24 * 30\n")],
}


def main():
    import engine_loader
    truth = engine_loader.truth()
    print(f"{len(SHORTCUTS)} shortcuts, each must fail at least one test")
    all_caught = True
    for name, reps in SHORTCUTS.items():
        src = SOLVE
        for old, new in reps:
            assert src.count(old) == 1, (name, old)
            src = src.replace(old, new)
        out = local_check.run_solution(TASK, src)
        with open(out / "point_doses.csv") as fh:
            got = {(r["patient_id"], r["point_id"]): float(r["dose_gy"]) for r in csv.DictReader(fh)}
        wrong = sum(abs(got[k] - w) > max(0.001 * w, 0.0005) for k, w in truth.items())
        passed, failed = local_check.run_tests(TASK, out)
        caught = bool(failed)
        all_caught &= caught
        print(f"{'caught' if caught else 'MISSED'}  {wrong:5d} of {len(truth)} points wrong  {name}")
    print("CALIBRATION:", "every shortcut caught" if all_caught else "SOME SHORTCUT PASSES")


if __name__ == "__main__":
    main()
