"""Shortcut solutions: solve.py with one reading changed by text replacement. Each must fail at least one test.

solve.py uses Eq. (1) for every photon beam, so the misreadings of Eq. (3) (Sp at the surface field, PDDN not
converted from SSD 100 cm, the inverse square taken to the point) are counted from the engine's case tags instead.
"""
import sys
sys.dont_write_bytecode = True       # never leave __pycache__ in the submitted task folder
import csv
import json
from pathlib import Path

import engine_loader
import local_check

TASK = Path(__file__).resolve().parent.parent
SOLVE = (TASK / "solution" / "solve.py").read_text()
TOL = 0.003
S = {
    "Sc from the MLC or block field": [("* SC(rc) *", "* SC(field) *")],
    "field not projected to the depth of the point": [("rd = field * spd / sad", "rd = field")],
    "off-axis ratio ignored": [("oar = OAR(depth, off) if off > 0 else 1.0", "oar = 1.0")],
    "tray factor ignored": [('tf = m["block_tray_factor"] if', 'tf = 1.0 if')],
    "wedge factor at 10 cm depth": [('WF(b["wedge_deg"], depth, rd)', 'WF(b["wedge_deg"], 10.0, rd)')],
    "heterogeneity ignored": [("    if het:\n", "    if False:\n")],
    "power law distances swapped": [('d1, d2 = depth - slab["from_cm"], depth - slab["to_cm"]',
                                     'd2, d1 = depth - slab["from_cm"], depth - slab["to_cm"]')],
    "inverse square ignored": [("* ((ssd0 + d0) / spd) ** 2", "")],
    "SSD0 taken as 100 cm": [("* ((ssd0 + d0) / spd) ** 2", "* ((100.0 + d0) / spd) ** 2")],
    "electron output by equivalent square": [("se = math.sqrt(SE(L, app) * SE(W, app))",
                                              "se = SE(2 * L * W / (L + W), app)")],
    "prescription isodose ignored": [('* b["prescription_isodose_pct"] *', '* 100.0 *')],
    "effective SSD ignored": [("s = math.sqrt(SSD_EFF(L) * SSD_EFF(W))", 's = m["ssd0_cm"]')],
    "air gap factor ignored": [('fair = math.sqrt(FAIR(L, b["ssd_cm"]) * FAIR(W, b["ssd_cm"]))', "fair = 1.0")],
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
        with open(out / "monitor_units.csv") as fh:
            got = {r["beam_id"]: float(r["mu"]) for r in csv.DictReader(fh)}
        wrong = sum(min(abs(got[k] / w - 1) for w in v) > TOL for k, v in truth.items())
        failed = bool(local_check.run_tests(TASK, out)[1])
        ok &= failed
        print(f"{'caught' if failed else 'MISSED'}  {wrong:4d} of {len(truth)} beams wrong  {name}")
    tags = json.loads((TASK / "tests" / "case_tags.json").read_text())
    for fam in ("sp_surface_field", "mayneord_ignored", "pdd_inverse_square_to_point"):
        print(f"engine  {sum(fam in v for v in tags.values()):4d} of {len(truth)} beams wrong  Eq. (3) {fam}")
    print("CALIBRATION:", "every shortcut caught" if ok else "SOME SHORTCUT PASSES")


if __name__ == "__main__":
    main()
