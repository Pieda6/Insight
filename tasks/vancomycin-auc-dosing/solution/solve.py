#!/usr/bin/env python3
"""Reference solution for vancomycin-auc-dosing.

AUC-guided vancomycin dosing (2020 ASHP/IDSA/PIDS/SIDP consensus guideline) from each patient's documented
administrations and two usable levels: a one-compartment model with constant-rate infusion segments and
first-order elimination, fitted by superposition of every documented infusion segment.
"""
import csv
import datetime as dt
import json
import math
import re
from pathlib import Path

DATA = Path("/app/data")
OUT = Path("/app/output")


def minutes(text):
    return (dt.datetime.strptime(text.strip(), "%Y-%m-%d %H:%M") - dt.datetime(2000, 1, 1)).total_seconds() / 60.0


def read_csv(name):
    with open(DATA / name, newline="") as fh:
        return list(csv.DictReader(fh))


def segment_amount(seg, t, ke):
    """Drug amount (mg) in the body at time t from one constant-rate segment (s, e, mg)."""
    s, e, mg = seg
    if t <= s:
        return 0.0
    rate = mg / (e - s)
    if t <= e:
        return rate / ke * (1.0 - math.exp(-ke * (t - s)))
    return rate / ke * (1.0 - math.exp(-ke * (e - s))) * math.exp(-ke * (t - e))


def segment_area(seg, T, ke):
    """Integral of segment_amount from 0 to T."""
    s, e, mg = seg
    if T <= s:
        return 0.0
    rate = mg / (e - s)
    t1 = min(T, e)
    area = rate / ke * ((t1 - s) - (1.0 - math.exp(-ke * (t1 - s))) / ke)
    if T > e:
        area += segment_amount(seg, e, ke) * (1.0 - math.exp(-ke * (T - e))) / ke
    return area


def total(segs, t, ke):
    return sum(segment_amount(sg, t, ke) for sg in segs)


def fit(segs, t1, c1, t2, c2):
    target = math.log(c1 / c2)

    def g(k):
        return math.log(total(segs, t1, k) / total(segs, t2, k)) - target

    grid = [1e-4 * (3e4) ** (i / 300) for i in range(301)]
    vals = [g(k) for k in grid]
    roots = [i for i in range(300) if (vals[i] > 0) != (vals[i + 1] > 0)]
    if len(roots) != 1:
        raise ValueError(f"{len(roots)} solutions for the elimination rate")
    lo, hi = grid[roots[0]], grid[roots[0] + 1]
    glo = g(lo)
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        gm = g(mid)
        if (gm > 0) == (glo > 0):
            lo, glo = mid, gm
        else:
            hi = mid
    ke = 0.5 * (lo + hi)
    return ke, total(segs, t1, ke) / c1


def main():
    patients = json.loads((DATA / "patients.json").read_text())
    admins = {}
    for r in read_csv("administrations.csv"):
        admins.setdefault(r["patient_id"], {}).setdefault(r["administration_id"], []).append(r)
    levels, orders = {}, {}
    for r in read_csv("levels.csv"):
        levels.setdefault(r["patient_id"], []).append(r)
    for r in read_csv("orders.csv"):
        orders.setdefault(r["patient_id"], []).append(r)

    out = []
    for p in patients:
        pid = p["patient_id"]
        segs, spans = [], []
        for aid, rows in admins.get(pid, {}).items():
            rows.sort(key=lambda r: minutes(r["time"]))
            start = [r for r in rows if r["event"] == "start"]
            if not start:
                continue                                       # not given
            conc = float(start[0]["dose_mg"]) / float(start[0]["bag_volume_ml"])
            open_t, done_v = None, 0.0
            for r in rows:
                t = minutes(r["time"]) / 60.0
                ev = r["event"]
                if ev in ("start", "resume"):
                    open_t = t
                elif ev in ("pause", "rate_change", "stop"):
                    vol = float(r["volume_infused_ml"])
                    if open_t is not None and vol > done_v and t > open_t:
                        segs.append((open_t, t, (vol - done_v) * conc))
                    done_v = vol
                    open_t = t if ev == "rate_change" else None
            spans.append((minutes(rows[0]["time"]), minutes(rows[-1]["time"])))
        t0 = min(s for s, _, _ in segs)
        segs = [(s - t0, e - t0, mg) for s, e, mg in segs]

        good = []
        for r in levels.get(pid, []):
            m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(?:[HL])?\s*", r["result"])
            if not m:
                continue                                       # rejected or below the reporting limit
            t = minutes(r["collected"])
            if any(s <= t <= e or e < t < e + 60 for s, e in spans):
                continue                                       # during an infusion or less than 1 h after one
            good.append((t / 60.0 - t0, float(m.group(1))))
        good.sort()
        (ta, ca), (tb, cb) = good
        ke, vol = fit(segs, ta, ca, tb, cb)
        cl = ke * vol

        cur = max((o for o in orders[pid] if o["frequency"] != "once"), key=lambda o: minutes(o["ordered"]))
        dose = float(cur["dose_mg"])
        tau = float(re.search(r"\d+", cur["frequency"]).group())
        auc24 = dose * 24.0 / tau / cl
        auc48 = sum(segment_area(sg, 48.0, ke) for sg in segs) / vol
        mic = 1.0                                          # guideline Recommendation 6: assume 1 mg/L
        ratio = auc24 / mic
        if 400.0 <= ratio <= 600.0:
            exposure, new = "within", int(dose)
        else:
            exposure = "below" if ratio < 400.0 else "above"
            raw = 500.0 * mic * cl * tau / 24.0
            new = int(math.floor(raw / 250.0 + 0.5) * 250)
        out.append([pid, f"{ke:.5f}", f"{vol:.2f}", f"{auc48:.1f}", f"{auc24:.1f}", exposure, new])

    out.sort(key=lambda r: r[0])
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "vancomycin_review.csv", "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["patient_id", "ke_per_h", "volume_l", "auc48", "auc24_ss", "exposure", "new_dose_mg"])
        w.writerows(out)


if __name__ == "__main__":
    main()
