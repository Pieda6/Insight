"""Shortcut solutions: each is solve.py with one reading changed by text replacement. Prints how many of the 220 values
(20 patients x 11 columns) each gets wrong (outside the verifier's tolerance) and whether the tests catch it.
Every shortcut must fail at least one test."""
import sys
sys.dont_write_bytecode = True       # never leave __pycache__ in the submitted task folder
import csv
from pathlib import Path

import local_check

TASK = Path(__file__).resolve().parent.parent
SOLVE = (TASK / "solution" / "solve.py").read_text()
COLS = ["d90_gy", "v100_pct", "v150_pct", "ud10_gy", "ud30_gy", "rv100_cc", "rd2cc_gy",
        "d90_meets", "v100_meets", "ud10_meets", "rv100_meets"]

SHORTCUTS = {
    "static dosimetry: dose rate at the CT positions times the mean life": [
        ("        return total * self.norm\n",
         "        return rate_at(r) / (self.alpha * self.lam_e)\n        return total * self.norm\n")],
    "seed distances scaled by the volume ratio instead of its cube root": [
        ("return ((y + self.v_pre) / self.v_ct) ** (1.0 / 3.0)", "return (y + self.v_pre) / self.v_ct"),
        ("return s ** 3 * self.v_ct - self.v_pre", "return s * self.v_ct - self.v_pre")],
    "distances scaled about the pre-implant volume instead of the CT volume": [
        ("return ((y + self.v_pre) / self.v_ct) ** (1.0 / 3.0)", "return ((y + self.v_pre) / self.v_pre) ** (1.0 / 3.0)"),
        ("return s ** 3 * self.v_ct - self.v_pre", "return s ** 3 * self.v_pre - self.v_pre")],
    "dose integrated from the CT onward instead of from the implant": [
        ("        cuts = sorted({self.y_at_scale(rn / r) for rn in nodes if 0.0 < self.y_at_scale(rn / r) < self.Y}) + [self.Y]\n",
         "        y_top = self.v_ct - self.v_pre\n"
         "        cuts = sorted({self.y_at_scale(rn / r) for rn in nodes if 0.0 < self.y_at_scale(rn / r) < y_top}) + [y_top]\n")],
    "one-marker seeds calculated with the 2D formalism along the slice axis": [
        ('            if s["x2_mm"] == "":\n                implanted.append((source, sk, m1, None))\n',
         '            if s["x2_mm"] == "":\n                implanted.append((source, sk, m1, [0.0, 0.0, 1.0]))\n')],
    "nearest-neighbour anisotropy factor instead of Eq. C3 below its first distance": [
        ("        if r < r_min:\n            return (self.Lambda * (r_min / r) ** 2", "        if False:\n            return (self.Lambda * (r_min / r) ** 2")],
    "radial dose function interpolated linearly": [
        ("return math.exp((1 - w) * math.log(self.g[j][1]) + w * math.log(self.g[j + 1][1]))",
         "return (1 - w) * self.g[j][1] + w * self.g[j + 1][1]")],
    "F held at the last tabulated angle (no F = 1 at 90 degrees)": [
        ('self.f_theta = F["theta_deg"] + [90.0]', 'self.f_theta = F["theta_deg"]'),
        ('self.f = F["F"] + [[1.0] * len(self.f_r)]', 'self.f = F["F"]')],
    "apparent activity used as if it were U": [
        ('return value * float(b["exposure_rate_constant"]) * CGY_AIR_PER_R', "return value")],
    "apparent activity converted with fixed 1.270 / 1.293 (not the vendor's constant)": [
        ('return value * float(b["exposure_rate_constant"]) * CGY_AIR_PER_R',
         'return value * (1.270 if float(b["exposure_rate_constant"]) < 1.47 else 1.293)')],
    "batch total read as per seed": [('return value / int(b["seeds_in_batch"])', "return value")],
    "no decay from calibration to implant": [
        ("sk = strength_per_seed(b) * math.exp(-LN2 * hours / source.half_h)", "sk = strength_per_seed(b)")],
    "calibration time zone offset ignored": [
        ('dt.datetime.fromisoformat(b["calibrated_at"])',
         'dt.datetime.fromisoformat(b["calibrated_at"][:16]).replace(tzinfo=dt.timezone.utc)')],
    "certificates dated after the implant treated as calibrated at the implant": [
        ("sk = strength_per_seed(b) * math.exp(-LN2 * hours / source.half_h)",
         "sk = strength_per_seed(b) * math.exp(-LN2 * max(hours, 0.0) / source.half_h)")],
    "implant and CT times without daylight saving (EST all year)": [("offset_h = 4 if start <= wall < end else 5", "offset_h = 5")],
    "duplicate detections kept": [('if s["review"] == "accepted":', "if True:")],
    "indices at floor ranks instead of ceiling ranks": [
        ("return desc[math.ceil(fraction * len(desc)) - 1]", "return desc[max(math.floor(fraction * len(desc)), 1) - 1]"),
        ("rd2cc = rec[math.ceil(2.0 / VOXEL_CC) - 1]", "rd2cc = rec[math.floor(2.0 / VOXEL_CC) - 1]")],
    "urethra voxels removed from the prostate": [
        ("        pro, ure, rec = doses[\"prostate\"], doses[\"urethra\"], doses[\"rectum\"]\n",
         "        pro, ure, rec = doses[\"prostate\"], doses[\"urethra\"], doses[\"rectum\"]\n"
         "        pro = sorted((d for d in pro if d not in set(ure)), reverse=True)\n")],
    "decay integral scaled as if the mean life were 1.44 T1/2": [
        ("        return total * self.norm\n", "        return total * self.norm * 1.44 * LN2\n")],
    "strict inequalities for the criteria": [
        ('"yes" if d90 >= rx else "no", "yes" if v100 >= 95.0 else "no"', '"yes" if d90 > rx else "no", "yes" if v100 > 95.0 else "no"'),
        ('"yes" if ud10 <= 1.5 * rx else "no", "yes" if rv100 <= 1.0 else "no"', '"yes" if ud10 < 1.5 * rx else "no", "yes" if rv100 < 1.0 else "no"')],
    "voxel centres on the lattice i x 2.5 mm instead of (i + 1/2) x 2.5 mm": [
        ("x, y = (i + 0.5) * VOXEL_MM, (j + 0.5) * VOXEL_MM", "x, y = i * VOXEL_MM, j * VOXEL_MM")],
}


def kind(col):
    return "gy" if col.endswith("_gy") else "pct" if col.endswith("_pct") else "cc" if col.endswith("_cc") else "cat"


def wrong(col, got, want):
    k = kind(col)
    if k == "cat":
        return got != want
    g = float(got)
    return abs(g - want) > (0.001 * abs(want) if k == "gy" else 0.30 if k == "pct" else 0.030)


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
        with open(out / "implant_evaluation.csv") as fh:
            got = {r["patient_id"]: r for r in csv.DictReader(fh)}
        n_wrong = sum(wrong(c, got[pid][c], w[c]) for pid, w in truth.items() for c in COLS)
        passed, failed = local_check.run_tests(TASK, out)
        caught = bool(failed)
        all_caught &= caught
        print(f"{'caught' if caught else 'MISSED'} {n_wrong:4d} of {len(truth) * len(COLS)} values wrong  {name}")
    print("CALIBRATION:", "every shortcut caught" if all_caught else "PROBLEM")
    sys.exit(0 if all_caught else 1)


if __name__ == "__main__":
    main()
