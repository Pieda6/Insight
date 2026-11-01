"""Independent engine for the verifier: KDIGO 2012 AKI definition and staging (Recommendations 2.1.1 and 2.1.2,
Table 2) over each admission's creatinine results, charted urine volumes and renal replacement therapy start."""
import bisect
import csv
import datetime as dt
import json
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
EPOCH = dt.datetime(2000, 1, 1)


def load():
    def rows(name):
        with open(DATA / name, newline="") as fh:
            return list(csv.DictReader(fh))
    return (json.loads((DATA / "patients.json").read_text()), rows("creatinine.csv"), rows("urine.csv"),
            rows("rrt.csv"))


def to_min(text):
    """New York local wall time to minutes on a continuous UTC clock."""
    t = dt.datetime.strptime(text, "%Y-%m-%d %H:%M")
    y = t.year
    mar = dt.date(y, 3, 1)
    mar = dt.datetime.combine(mar + dt.timedelta(days=(6 - mar.weekday()) % 7 + 7), dt.time(2))
    nov = dt.date(y, 11, 1)
    nov = dt.datetime.combine(nov + dt.timedelta(days=(6 - nov.weekday()) % 7), dt.time(1))
    return (t - EPOCH).total_seconds() / 60 + (240 if mar <= t < nov else 300)


def to_text(m):
    for off in (240, 300):
        cand = (EPOCH + dt.timedelta(minutes=round(m) - off)).strftime("%Y-%m-%d %H:%M")
        if to_min(cand) == round(m):
            return cand
    raise ValueError(m)


class Urine:
    """Cumulative urine volume, linear within each charting interval."""

    def __init__(self, start, charts):
        self.t = [start]
        self.v = [0.0]
        for t, ml in sorted(charts):
            self.t.append(t)
            self.v.append(self.v[-1] + ml)

    def at(self, x):
        if x <= self.t[0]:
            return 0.0
        if x >= self.t[-1]:
            return self.v[-1]
        i = bisect.bisect_left(self.t, x)
        a, b = self.t[i - 1], self.t[i]
        return self.v[i - 1] + (self.v[i] - self.v[i - 1]) * (x - a) / (b - a)

    def first_below(self, span, limit):
        """Earliest x with volume over (x - span, x] below limit (zero when limit is None), within the record."""
        lo, hi = self.t[0] + span, self.t[-1]
        if lo > hi:
            return None
        cuts = sorted({lo, hi, *[x for x in self.t if lo < x < hi], *[x + span for x in self.t if lo < x + span < hi]})
        g = lambda x: self.at(x) - self.at(x - span)
        prev = None
        for x in cuts:
            gx = g(x)
            if limit is None:
                if gx <= 1e-9:
                    return x
            elif gx < limit:
                if prev is None:
                    return x
                a, b = prev, x                                  # bisection on the linear piece
                for _ in range(80):
                    m = (a + b) / 2
                    if g(m) < limit:
                        b = m
                    else:
                        a = m
                return b
            prev = x
        return None


def evaluate(p, creat, urine, rrt):
    """(max_stage, onset minutes or None, stage-reached minutes or None)."""
    base = float(p["baseline_creatinine_mg_dl"])
    final = {}
    for r in creat:
        if r["status"] == "corrected" or r["accession"] not in final:
            final[r["accession"]] = r
    res = []
    for r in final.values():
        try:
            x = float(r["result"])
        except ValueError:
            continue
        res.append((to_min(r["collected"]), x / 88.4 if r["units"] == "umol/L" else x))
    res.sort()
    found = []
    for i, (t, c) in enumerate(res):
        acute = any(c - c0 >= 0.3 for t0, c0 in res[:i] if t - t0 <= 48 * 60)
        r_ = c / base
        s = 0
        for k, lim in ((1, 1.5), (2, 2.0), (3, 3.0)):
            if r_ >= lim:
                s = k
        if acute and s == 0:
            s = 1
        if c >= 4.0 and (acute or r_ >= 1.5):
            s = 3
        if s:
            found.append((t, s))
    for r in rrt:
        found.append((to_min(r["started"]), 3))
    w = float(p["weight_kg"])
    u = Urine(to_min(p["admitted"]), [(to_min(r["charted"]), float(r["volume_ml"])) for r in urine])
    for hours, rate, s in ((6, 0.5, 1), (12, 0.5, 2), (24, 0.3, 3), (12, None, 3)):
        x = u.first_below(hours * 60, None if rate is None else rate * w * hours)
        if x is not None:
            found.append((x, s))
    if not found:
        return 0, None, None
    top = max(s for _, s in found)
    return top, min(t for t, _ in found), min(t for t, s in found if s == top)


def expected():
    pats, creat, urine, rrt = load()
    group = lambda rows: {p["patient_id"]: [r for r in rows if r["patient_id"] == p["patient_id"]] for p in pats}
    c, u, r = group(creat), group(urine), group(rrt)
    return {p["patient_id"]: evaluate(p, c[p["patient_id"]], u[p["patient_id"]], r[p["patient_id"]]) for p in pats}
