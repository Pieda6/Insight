"""Shortcut ports: the repaired tg51calc with one legacy behaviour put back, and the legacy code ported mechanically
(Python 3 syntax and the removed numpy/scipy calls fixed, inHg added, nothing else). Each must fail at least one test.
Run with a Python that has numpy and scipy (the versions pinned in environment/Dockerfile)."""
import sys
sys.dont_write_bytecode = True       # never leave __pycache__ in the submitted task folder
import contextlib
import csv
import io
import shutil
import tempfile
from pathlib import Path

import engine_loader
import local_check

TASK = Path(__file__).resolve().parent.parent
FIXED = TASK / "solution" / "tg51calc"
LEGACY = TASK / "environment" / "tg51calc"
TOL = 0.003
S = {
    "Fahrenheit read as Celsius (legacy)": ("corrections.py", "    t = (temp - 32.0) * 5.0 / 9.0 if temp_unit == 'F' else temp\n", "    t = temp\n"),
    "electrometer factor of one range (legacy)": ("corrections.py", "electrometer['pelec'][main['electrometer_range']]", "electrometer['pelec']['high']"),
    "polarity correction over the positive reading (legacy)": ("corrections.py", "corr *= p_pol(per_mu(plus), per_mu(minus), m)", "corr *= p_pol(per_mu(plus), per_mu(minus), per_mu(plus))"),
    "continuous-beam recombination formula (legacy)": ("corrections.py", "    return (1.0 - r) / (m_high / m_low - r)", "    return (1.0 - r ** 2) / (m_high / m_low - r ** 2)"),
    "Pelec kept for cross-calibrated chambers (legacy)": ("corrections.py", "corr *= 1.0 if cross_calibrated else", "corr *= "),
    "scans taken as already shifted (legacy)": ("photons.py", "return fraction * ch['cavity_radius_cm'] if ch['type'] == 'cylindrical' else 0.0", "return 0.0"),
    "no radial-profile correction (legacy)": ("photons.py", "d10 = m * 1e-9 * p_rp(ws, beam, chamber) *", "d10 = m * 1e-9 *"),
    "dose at dmax from %dd(10)x and PDD for SAD (legacy)": ("photons.py", "    if beam['setup'] == 'SAD':\n        return d10, d10 / beam['tmr_10']\n    return d10, d10 / (open_pct / 100.0)", "    return d10, d10 / (x / 100.0)"),
    "Eq. (19) for plane-parallel chambers (legacy)": ("electrons.py", "    if kind == 'cylindrical':\n        return 0.9905", "    if True:\n        return 0.9905"),
}
MECHANICAL = [
    ("review.py", "print beam['beam_id'], '%.5f' % d_ref, '%.5f' % d_max", "print(beam['beam_id'], '%.5f' % d_ref, '%.5f' % d_max)"),
    ("review.py", "open(out_csv, 'wb')", "open(out_csv, 'w', newline='')"),
    ("worksheets.py", "open(path, 'rb')", "open(path, newline='')"),
    ("worksheets.py", ".iteritems()", ".items()"),
    ("worksheets.py", "dtype=np.float)", "dtype=float)"),
    ("corrections.py", "np.float(", "float("),
    ("corrections.py", "'mmHg': MMHG}", "'mmHg': MMHG, 'inHg': 3.386388640341}"),
    ("photons.py", "scipy.interp(10.0", "np.interp(10.0"),
    ("photons.py", "return scipy.interp(x, KQ_X, ys)", "return np.interp(x, KQ_X, ys)"),
    ("electrons.py", "i50 = scipy.interp(", "i50 = np.interp("),
    ("electrons.py", "(scipy.interp(0.6 * r - 0.1", "(np.interp(0.6 * r - 0.1"),
]


def run(package_src, edits):
    work = Path(tempfile.mkdtemp(prefix="calib_"))
    pkg = work / "tg51calc"
    shutil.copytree(package_src, pkg)
    for fname, old, new in edits:
        text = (pkg / fname).read_text()
        assert text.count(old) >= 1, (fname, old)
        (pkg / fname).write_text(text.replace(old, new))
    out = work / "output"
    out.mkdir()
    sys.path.insert(0, str(work))
    for m in [m for m in sys.modules if m == "tg51calc" or m.startswith("tg51calc.")]:
        del sys.modules[m]
    try:
        from tg51calc.review import main as review
        with contextlib.redirect_stdout(io.StringIO()):
            review([str(TASK / "environment" / "data"), str(out / "dose_per_mu.csv")])
    finally:
        sys.path.remove(str(work))
    return out


def score(out, truth):
    with open(out / "dose_per_mu.csv") as fh:
        got = {r["beam_id"]: (float(r["dose_ref_cgy_per_mu"]), float(r["dose_dmax_cgy_per_mu"])) for r in csv.DictReader(fh)}
    return sum(not any(abs(got[k][0] / p[0] - 1) <= TOL and abs(got[k][1] / p[1] - 1) <= TOL for p in v)
               for k, v in truth.items())


def main():
    truth = engine_loader.truth()
    ok = True
    cases = [(n, FIXED, [e]) for n, e in S.items()] + [("legacy code ported mechanically", LEGACY, MECHANICAL)]
    print(f"{len(cases)} shortcuts, each must fail at least one test")
    for name, src, edits in cases:
        out = run(src, edits)
        failed = bool(local_check.run_tests(TASK, out)[1])
        ok &= failed
        print(f"{'caught' if failed else 'MISSED'}  {score(out, truth):4d} of {len(truth)} beams wrong  {name}")
    print("CALIBRATION:", "every shortcut caught" if ok else "SOME SHORTCUT PASSES")


if __name__ == "__main__":
    main()
