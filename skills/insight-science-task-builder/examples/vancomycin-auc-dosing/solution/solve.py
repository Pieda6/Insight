#!/usr/bin/env python3
"""Reference solution for vancomycin-auc-dosing.

AUC-guided vancomycin dosing (2020 ASHP/IDSA/PIDS/SIDP consensus guideline) from each patient's documented
administrations and two usable levels. One-compartment model: constant-rate infusion stretches, first-order
elimination at the patient's own clearance plus the dialyzer's clearance while a hemodialysis session runs. The
amount in the body is carried in closed form across every infusion and dialysis breakpoint; the patient's
clearance and volume are found by a coarse grid search followed by a damped two-dimensional Newton iteration.
"""
import csv
import datetime as dt
import json
import math
import re
from pathlib import Path

DATA = Path("/app/data")
OUT = Path("/app/output")

MG_PER_UMOL = 1.4493          # vancomycin 1449.3 g/mol: 1 umol/L = 1.4493 mg/L
ML_MIN_TO_L_H = 0.06


def nth_sunday(year, month, n):
    first = dt.date(year, month, 1)
    return first + dt.timedelta(days=(6 - first.weekday()) % 7 + 7 * (n - 1))


def minutes(text):
    """Minutes on a continuous clock from a New York local time (US daylight saving rules)."""
    wall = dt.datetime.strptime(text.strip(), "%Y-%m-%d %H:%M")
    start = dt.datetime.combine(nth_sunday(wall.year, 3, 2), dt.time(2, 0))
    end = dt.datetime.combine(nth_sunday(wall.year, 11, 1), dt.time(1, 0))
    offset_h = 4 if start <= wall < end else 5                 # UTC = local + 4 h (EDT) or + 5 h (EST)
    return (wall - dt.datetime(2000, 1, 1)).total_seconds() / 60.0 + 60 * offset_h


def read_csv(name):
    with open(DATA / name, newline="") as fh:
        return list(csv.DictReader(fh))


class Timeline:
    """Breakpoints of a patient's infusions and dialysis sessions, in hours from the first infusion."""

    def __init__(self, segs, sessions):
        points = sorted({0.0} | {x for s, e, _ in segs for x in (s, e) if x > 0}
                        | {x for s, e, _ in sessions for x in (s, e) if x > 0})
        self.steps = []
        for a, b in zip(points, points[1:] + [math.inf]):
            mid = a + 1.0 if b == math.inf else (a + b) / 2
            rate = sum(mg / (e - s) for s, e, mg in segs if s < mid < e)
            dialysis = sum(c for s, e, c in sessions if s < mid < e)
            self.steps.append((a, b, rate, dialysis))

    def amount(self, t, cl, vol):
        a_mg = 0.0
        for a, b, rate, dialysis in self.steps:
            if a >= t:
                break
            k = (cl + dialysis) / vol
            decay = math.exp(-k * (min(b, t) - a))
            a_mg = a_mg * decay + rate / k * (1.0 - decay)
        return a_mg

    def area(self, t_from, t_to, cl, vol):
        """Integral of the concentration over [t_from, t_to]."""
        a_mg, total = 0.0, 0.0
        for a, b, rate, dialysis in self.steps:
            if a >= t_to:
                break
            k = (cl + dialysis) / vol
            end = min(b, t_to)
            start = max(a, t_from)
            if start < end:
                pre = math.exp(-k * (start - a))
                at_start = a_mg * pre + rate / k * (1.0 - pre)
                d = end - start
                decay = math.exp(-k * d)
                total += at_start * (1.0 - decay) / k + rate / k * (d - (1.0 - decay) / k)
            decay = math.exp(-k * (end - a))
            a_mg = a_mg * decay + rate / k * (1.0 - decay)
        return total / vol


def fit(line, t1, c1, t2, c2):
    """Patient clearance (L/h) and volume (L) through both levels."""
    def resid(u):
        if not (math.log(1e-4) < u[0] < math.log(200.0) and math.log(1.0) < u[1] < math.log(5000.0)):
            return None                                        # outside any plausible clearance or volume
        cl, vol = math.exp(u[0]), math.exp(u[1])
        a1, a2 = line.amount(t1, cl, vol), line.amount(t2, cl, vol)
        if a1 <= 0 or a2 <= 0:
            return None
        return (math.log(a1 / vol / c1), math.log(a2 / vol / c2))

    starts = []
    for i in range(31):
        for j in range(31):
            u = (math.log(0.003) + i * math.log(30.0 / 0.003) / 30, math.log(5.0) + j * math.log(1500.0 / 5.0) / 30)
            r = resid(u)
            if r is not None:
                starts.append((r[0] ** 2 + r[1] ** 2, u))
    starts.sort()
    best = None
    for _, u in starts:                                        # Newton from the best grid points until exact
        u = newton(resid, u)
        r = resid(u)
        if r is not None and (best is None or r[0] ** 2 + r[1] ** 2 < best[0]):
            best = (r[0] ** 2 + r[1] ** 2, u)
        if best[0] < 1e-24:
            break
    return math.exp(best[1][0]), math.exp(best[1][1])


def newton(resid, u):
    """Damped Newton on the two log residuals."""
    for _ in range(200):
        r = resid(u)
        h = 1e-7
        r_a, r_b = resid((u[0] + h, u[1])), resid((u[0], u[1] + h))
        if r_a is None or r_b is None:
            break
        j11, j21 = (r_a[0] - r[0]) / h, (r_a[1] - r[1]) / h
        j12, j22 = (r_b[0] - r[0]) / h, (r_b[1] - r[1]) / h
        det = j11 * j22 - j12 * j21
        du0 = (-r[0] * j22 + r[1] * j12) / det
        du1 = (-r[1] * j11 + r[0] * j21) / det
        step = 1.0
        norm = r[0] ** 2 + r[1] ** 2
        while step > 1e-6:
            cand = (u[0] + step * du0, u[1] + step * du1)
            rc = resid(cand)
            if rc is not None and rc[0] ** 2 + rc[1] ** 2 < norm:
                u = cand
                break
            step /= 2
        if norm < 1e-26:
            break
    return u


def main():
    patients = json.loads((DATA / "patients.json").read_text())
    admins, levels, orders, dialysis = {}, {}, {}, {}
    for r in read_csv("administrations.csv"):
        admins.setdefault(r["patient_id"], {}).setdefault(r["administration_id"], []).append(r)
    for r in read_csv("levels.csv"):
        levels.setdefault(r["patient_id"], []).append(r)
    for r in read_csv("orders.csv"):
        orders.setdefault(r["patient_id"], []).append(r)
    for r in read_csv("hemodialysis.csv"):
        dialysis.setdefault(r["patient_id"], []).append(r)

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
        sessions_min = [(minutes(r["start"]), minutes(r["stop"]), float(r["vancomycin_clearance_ml_min"]))
                        for r in dialysis.get(pid, [])]
        sessions = [(s / 60.0 - t0, e / 60.0 - t0, c * ML_MIN_TO_L_H) for s, e, c in sessions_min]

        reports = {}
        for r in levels.get(pid, []):                          # a corrected result replaces the original
            if r["accession"] not in reports or r["status"] == "corrected":
                reports[r["accession"]] = r
        good = []
        for r in reports.values():
            m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(?:[HL])?\s*", r["result"])
            if not m:
                continue                                       # rejected or below the reporting limit
            t = minutes(r["collected"])
            if any(s <= t <= e or e < t < e + 60 for s, e in spans):
                continue                                       # during an infusion or less than 1 h after one
            if any(s <= t <= e for s, e, _ in sessions_min):
                continue                                       # during a dialysis session
            value = float(m.group(1)) * (MG_PER_UMOL if r["units"] == "umol/L" else 1.0)
            good.append((t / 60.0 - t0, value))
        good.sort()
        (ta, ca), (tb, cb) = good
        line = Timeline(segs, sessions)
        cl, vol = fit(line, ta, ca, tb, cb)
        ke = cl / vol

        cur = max((o for o in orders[pid] if o["frequency"] != "once"), key=lambda o: minutes(o["ordered"]))
        dose = float(cur["dose_mg"])
        auc24 = line.area(tb - 24.0, tb, cl, vol)              # the 24 hours before the later usable level
        auc48 = line.area(0.0, 48.0, cl, vol)
        if 400.0 <= auc24 <= 600.0:                            # MIC taken as 1 mg/L (Recommendation 6)
            exposure, new = "within", int(dose)
        else:
            exposure = "below" if auc24 < 400.0 else "above"
            raw = dose * 500.0 / auc24                         # dose changes give proportional AUC changes
            new = int(math.floor(raw / 250.0 + 0.5) * 250)
        out.append([pid, f"{ke:.6f}", f"{vol:.2f}", f"{auc48:.1f}", f"{auc24:.1f}", exposure, new])

    out.sort(key=lambda r: r[0])
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "vancomycin_review.csv", "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["patient_id", "ke_per_h", "volume_l", "auc48", "auc24", "exposure", "new_dose_mg"])
        w.writerows(out)


if __name__ == "__main__":
    main()
