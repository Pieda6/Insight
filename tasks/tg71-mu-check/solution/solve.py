"""Reference solution for tg71-mu-check.

Photon beams use the TPR formalism of TG-71 Eq. (1) for every setup; electron beams use Eq. (10) to (13), (22).
"""
import csv
import json
import math
from bisect import bisect_left
from pathlib import Path

DATA = Path("/app/data")
OUT = Path("/app/output")


def table(name):
    with open(DATA / name, newline="") as fh:
        rows = list(csv.reader(fh))
    return rows[0], rows[1:]


def interp(xs, ys, x):
    """Piecewise-linear interpolation on increasing xs; ys may hold None where a value is not tabulated."""
    pts = [(a, b) for a, b in zip(xs, ys) if b is not None]
    px = [a for a, _ in pts]
    if not px[0] - 1e-9 <= x <= px[-1] + 1e-9:
        raise ValueError(f"{x} outside the table")
    i = min(max(bisect_left(px, x), 1), len(px) - 1)
    (x0, y0), (x1, y1) = pts[i - 1], pts[i]
    return y0 + (y1 - y0) * (x - x0) / (x1 - x0)


def grid(name, colkey):
    head, rows = table(name)
    cols = [colkey(h) for h in head[1:]]
    keys = [float(r[0]) for r in rows]
    vals = [[float(v) if v.strip() else None for v in r[1:]] for r in rows]

    def f(row, col):
        across = []
        for v in vals:
            try:
                across.append(interp(cols, v, col))
            except (ValueError, IndexError):
                across.append(None)
        return interp(keys, across, row)
    return f


side = lambda h: float(h.split("x")[0])
WSIDE = [5.0, 10.0, 15.0, 20.0, 30.0]


def load_tables():
    global PDD, TPR, OAR, FAIR, SCR, EQ, WFR, SEH, SER, SSDEFF
    PDD = grid("pddn_6mv_ssd100.csv", side)
    TPR = grid("tpr_6mv.csv", side)
    OAR = grid("oar_6mv.csv", float)
    FAIR = grid("electron_9mev_air_gap_factors.csv", float)
    _, SCR = table("scatter_6mv.csv")
    EQ = [float(r[0]) for r in SCR]
    _, WFR = table("wedge_factors_6mv.csv")
    SEH, SER = table("electron_9mev_output_factors.csv")
    _, SSDEFF = table("electron_ssdeff.csv")


def SC(r):
    return interp(EQ, [float(x[2]) for x in SCR], r)


def SP(r):
    return interp(EQ, [float(x[3]) for x in SCR], r)


def WF(angle, depth, s):
    rows = [r for r in WFR if int(r[0]) == angle]
    across = [interp(WSIDE, [float(v) if v.strip() else None for v in r[2:]], s) for r in rows]
    return interp([float(r[1]) for r in rows], across, depth)


def SE(sq, applicator):
    col = SEH.index(f"applicator_{applicator}")
    return interp([float(r[0]) for r in SER], [float(r[col]) if r[col].strip() else None for r in SER], sq)


def SSD_EFF(sq):
    return interp([float(r[0]) for r in SSDEFF], [float(r[2]) for r in SSDEFF], sq)


def photon(m, b):
    sad, ssd0, d0 = m["sad_cm"], m["ssd0_cm"], m["normalization_depth_cm"]
    j = b["jaws_cm"]
    wx, wy = j["X1"] + j["X2"], j["Y1"] + j["Y2"]
    rc = 2 * wx * wy / (wx + wy)                      # Eq. (4): the jaws set Sc (tertiary MLC and tray blocks)
    field = b["shaped_field_equivalent_square_cm"] or rc
    depth = b["point"]["depth_cm"]
    spd = b["ssd_cm"] + depth
    rd = field * spd / sad                            # field incident on the patient, at the depth of the point
    off = math.hypot(*b["point"]["off_axis_cm"]) * sad / spd
    oar = OAR(depth, off) if off > 0 else 1.0
    wf = WF(b["wedge_deg"], depth, rd) if b["wedge_deg"] else 1.0
    tf = m["block_tray_factor"] if b["field_shaping"] == "block on tray" else 1.0
    cf = 1.0
    het = b["heterogeneity"]
    if het:
        if het["correction"] == "RTAR":           # Eqs. (6) and (7)
            deff = 0.0
            for layer in het["layers"]:
                top, bottom = layer["from_cm"], min(layer["to_cm"], depth)
                if bottom > top:
                    deff += (bottom - top) * layer["rho_e"]
            cf = TPR(deff, rd) / TPR(depth, rd)
        else:                                      # Eq. (8), the point below the heterogeneity
            (slab,) = [layer for layer in het["layers"] if layer["rho_e"] != 1.0]
            d1, d2 = depth - slab["from_cm"], depth - slab["to_cm"]
            cf = (TPR(d1, rd) / TPR(d2, rd)) ** (slab["rho_e"] - 1.0)
    dose_per_mu = (m["d0_cgy_per_mu"] * SC(rc) * SP(rd) * TPR(depth, rd) * wf * tf * oar
                   * ((ssd0 + d0) / spd) ** 2 * cf)
    return b["dose_cgy"] / dose_per_mu


def electron(m, b):
    L, W = b["insert_cm"]
    app = b["applicator"]
    se = math.sqrt(SE(L, app) * SE(W, app))           # Eq. (13)
    gap = b["ssd_cm"] - m["ssd0_cm"]
    dm = m["dm_cm"]
    corr = 1.0
    if gap > 0 and b["extended_distance_method"] == "effective SSD":      # Eq. (11)
        s = math.sqrt(SSD_EFF(L) * SSD_EFF(W))
        corr = ((s + dm) / (s + dm + gap)) ** 2
    elif gap > 0:                                                          # Eq. (12) with Eq. (22)
        fair = math.sqrt(FAIR(L, b["ssd_cm"]) * FAIR(W, b["ssd_cm"]))
        corr = ((m["ssd0_cm"] + dm) / (m["ssd0_cm"] + dm + gap)) ** 2 * fair
    return b["dose_cgy"] * 100.0 / (m["d0_cgy_per_mu"] * b["prescription_isodose_pct"] * se * corr)


def main():
    load_tables()
    machine = json.loads((DATA / "machine.json").read_text())
    plans = json.loads((DATA / "plans.json").read_text())
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "monitor_units.csv", "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["beam_id", "mu"])
        for p in plans["patients"]:
            for b in p["beams"]:
                mu = photon(machine["photon"], b) if b["modality"] == "photon" else electron(machine["electron"], b)
                w.writerow([b["beam_id"], f"{mu:.2f}"])


if __name__ == "__main__":
    main()
