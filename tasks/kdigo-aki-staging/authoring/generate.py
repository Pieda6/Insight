"""Generate the KDIGO acute kidney injury staging cases (seed 20120301).

Writes patients.json, creatinine.csv, urine.csv and rrt.csv to both data copies, evidence/answers.json (the generator's
own staging, first implementation in sim below) and ../tests/case_tags.json (per patient, the misreadings that
change its row).
"""
import sys
sys.dont_write_bytecode = True       # never leave __pycache__ in the submitted task folder
import csv
import datetime as dt
import json
import math
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUTS = [HERE / "../environment/data", HERE / "../tests/data"]
N_PATIENTS = 120
UMOL = 88.4
H = 60.0


# ------------------------------------------------------------------ time ----------------------------------
def nth_sunday(y, m, n):
    d = dt.date(y, m, 1)
    return d + dt.timedelta(days=(6 - d.weekday()) % 7 + 7 * (n - 1))


def utc_min(text, naive=False):
    w = dt.datetime.strptime(text, "%Y-%m-%d %H:%M")
    off = 5
    if not naive and dt.datetime.combine(nth_sunday(w.year, 3, 2), dt.time(2)) <= w < \
            dt.datetime.combine(nth_sunday(w.year, 11, 1), dt.time(1)):
        off = 4
    return (w - dt.datetime(2026, 1, 1)).total_seconds() / 60 + 60 * off


def stamp(m):
    t = dt.datetime(2026, 1, 1) + dt.timedelta(minutes=round(m))
    for off in (4, 5):
        txt = (t - dt.timedelta(hours=off)).strftime("%Y-%m-%d %H:%M")
        if utc_min(txt) == round(m):
            return txt
    raise ValueError(m)


def awkward(m):
    w = dt.datetime(2026, 1, 1) + dt.timedelta(minutes=round(m)) - dt.timedelta(hours=5)
    return w.month == 11 and w.day == 1 and w.hour in (0, 1, 2)


# ------------------------------------------------------------------ sim ------------------------------------
def uo_first(charts, start, hours, rate, w, strict_zero=False, margins=None, chart_only=False):
    """First time t (UTC minutes) at which the urine over (t - hours, t] is below rate ml/kg/h (or zero)."""
    times = [start] + [t for t, _ in charts]
    cum = [0.0]
    for _, v in charts:
        cum.append(cum[-1] + v)

    def V(t):
        if t <= times[0]:
            return 0.0
        for i in range(1, len(times)):
            if t <= times[i]:
                f = (t - times[i - 1]) / (times[i] - times[i - 1])
                return cum[i - 1] + f * (cum[i] - cum[i - 1])
        return cum[-1]
    N = hours * H
    lo, hi = start + N, times[-1]
    if lo > hi:
        return None
    thr = 0.0 if strict_zero else rate * w * hours
    pts = sorted({lo, hi} | {t for t in times if lo < t < hi} | {t + N for t in times if lo < t + N < hi})
    if chart_only:
        pts = sorted({t for t in times if lo <= t <= hi})
    vals = [V(t) - V(t - N) for t in pts]
    if margins is not None and not strict_zero:
        m = min(vals)
        margins.append(("uo", abs(m - thr) / thr))
    for i, (t, f) in enumerate(zip(pts, vals)):
        if (f <= 1e-9) if strict_zero else (f < thr):
            if i == 0 or strict_zero or chart_only:
                return t
            a, fa = pts[i - 1], vals[i - 1]
            return a + (fa - thr) / (fa - f) * (t - a)
    return None


def stage(p, creat, charts, rrt, v=None, margins=None):
    """(max_stage, onset, reached) in UTC minutes for one admission."""
    v = v or {}
    naive = v.get("naive")
    start = utc_min(p["admitted"], naive)
    base = float(p["baseline_creatinine_mg_dl"])
    reps = {}
    for r in creat:
        if v.get("ignore_corrections"):
            reps.setdefault(r["accession"], r)
        elif r["accession"] not in reps or r["status"] == "corrected":
            reps[r["accession"]] = r
    vals = []
    for r in reps.values():
        try:
            x = float(r["result"])
        except ValueError:
            continue
        if r["units"] == "umol/L" and not v.get("umol_as_mg"):
            x /= UMOL
        vals.append((utc_min(r["collected"], naive), x))
    vals.sort()
    events = []                                                   # (time, stage)
    for i, (t, c) in enumerate(vals):
        ratio = c / base
        s = 3 if ratio >= 3.0 else 2 if ratio >= 2.0 else 1 if ratio >= 1.5 else 0
        window = 2880 if not v.get("window_24h") else 1440
        rise = any(t - tp <= window and c - cp >= 0.3 for tp, cp in vals[:i]) if not v.get("rise_from_baseline") \
            else c - base >= 0.3
        if v.get("rise_from_first"):
            rise = c - vals[0][1] >= 0.3 and t - vals[0][0] <= 2880
        if rise:
            s = max(s, 1)
        if c >= 4.0 and not v.get("no_4") and (rise or ratio >= 1.5):
            s = 3
        if margins is not None:
            margins.append(("ratio", min(abs(ratio - k) / k for k in (1.5, 2.0, 3.0))))
            margins.append(("abs", abs(c - 4.0)))
            for tp, cp in vals[:i]:
                if abs(c - cp - 0.3) < 0.004:
                    margins.append(("rise", 0.0))
                if c - cp >= 0.3 - 0.004 and abs(t - tp - 2880) < 10:
                    margins.append(("rise", 0.0))
        if s:
            events.append((t, s))
    if rrt and not v.get("no_rrt"):
        events.append((utc_min(rrt, naive), 3))
    w = float(p["weight_kg"])
    ch = [(utc_min(r["charted"], naive), float(r["volume_ml"])) for r in charts]
    ch.sort()
    co = v.get("chart_only", False)
    crit = [(6, 0.5, False, 1), (12, 0.5, False, 2), (24, 0.3, False, 3), (12, 0.0, True, 3)]
    if v.get("no_anuria"):
        crit = crit[:3]
    if v.get("stage1_needs_12h"):
        crit[0] = (12, 0.5, False, 1)
    for hours, rate, zero, s in crit:
        t = uo_first(ch, start, hours, rate, w, zero, margins, co)
        if t is not None:
            events.append((t, s))
    if not events:
        return 0, None, None
    top = max(s for _, s in events)
    onset = min(t for t, _ in events)
    reached = min(t for t, s in events if s == top)
    return top, onset, reached


SHORTCUTS = {
    "umol_read_as_mg": {"umol_as_mg": True},
    "original_kept_over_correction": {"ignore_corrections": True}, "rise_window_24h": {"window_24h": True},
    "rise_measured_from_first_result": {"rise_from_first": True},
    "creatinine_4_rule_ignored": {"no_4": True}, "renal_replacement_ignored": {"no_rrt": True},
    "urine_windows_at_charting_times_only": {"chart_only": True}, "anuria_ignored": {"no_anuria": True},
    "stage1_urine_needs_12h": {"stage1_needs_12h": True},
}


# ------------------------------------------------------------------ generation ------------------------------
def make_patient(rng, k):
    pid = f"ICU-{k:03d}"
    anchor = rng.choice([dt.datetime(2026, 3, 8), dt.datetime(2026, 11, 1), dt.datetime(2026, 7, 1)])
    adm_local = anchor - dt.timedelta(days=rng.uniform(0.2, 4.5))
    start = round(utc_min(adm_local.strftime("%Y-%m-%d %H:%M")))
    dur = rng.uniform(3.0, 6.9) * 1440
    end = round(start + dur)
    w = round(rng.uniform(50, 120), 1)
    high = rng.random() < 0.15
    base = round(rng.uniform(1.75, 2.4) if high else rng.uniform(0.6, 1.6), 2)
    umol = rng.random() < 0.3
    u = rng.random()
    if high:
        peak = rng.uniform(3.92, 4.12) / base
    elif u < 0.25:
        peak = rng.uniform(0.95, 1.25)
    elif u < 0.75:
        k_ = rng.choice([1.5, 2.0, 3.0])
        peak = k_ * (1 + rng.choice([-1, 1]) * rng.uniform(0.003, 0.03))
    else:
        peak = rng.uniform(1.2, 3.8)
    onset = start + rng.uniform(0.1, 0.5) * dur
    rise_h = rng.uniform(20, 70)

    def c_at(t):
        s = 0.0 if t < onset else min(1.0, (t - onset) / (rise_h * 60))
        return base * (1 + (peak - 1) * s)
    creat, acc = [], 0
    t = start + rng.uniform(30, 300)
    while t < end:
        if not awkward(t):
            c = c_at(t) * rng.uniform(0.985, 1.015)
            acc += 1
            res = f"{round(c * UMOL)}" if umol else f"{c:.2f}"
            rec = {"patient_id": pid, "accession": f"{pid}-C{acc:03d}", "collected": stamp(t), "result": res,
                   "units": "umol/L" if umol else "mg/dL", "status": "final"}
            if rng.random() < 0.1:
                wrong = dict(rec, result=f"{float(res) * rng.uniform(0.7, 1.3):.{0 if umol else 2}f}")
                creat += [wrong, dict(rec, status="corrected")]
            else:
                creat.append(rec)
            if rng.random() < 0.06:
                acc += 1
                creat.append(dict(rec, accession=f"{pid}-C{acc:03d}", result=rng.choice(["rejected: hemolyzed",
                                                                                         "cancelled"]), status="final"))
        t += rng.uniform(6, 26) * 60
    rrt = None
    if peak >= 2.4 and rng.random() < 0.45:
        r = onset + rise_h * 60 + rng.uniform(-6, 30) * 60
        if r < end and not awkward(r):
            rrt = stamp(r)
    # urine: rate in ml/kg/h with one possible oliguric episode
    kind = rng.choice(["none", "mild", "moderate", "anuric"] + ["mild"] * 2)
    ep_s = start + rng.uniform(0.15, 0.6) * dur
    ep_len = {"none": 0, "mild": rng.uniform(4.5, 15), "moderate": rng.uniform(11, 32), "anuric": rng.uniform(9, 17)}[kind] * 60
    ep_rate = {"none": 1.0, "mild": rng.choice([rng.uniform(0.40, 0.494), rng.uniform(0.506, 0.56)]),
               "moderate": rng.choice([rng.uniform(0.18, 0.296), rng.uniform(0.304, 0.45)]), "anuric": 0.0}[kind]
    normal = rng.uniform(0.6, 1.6)

    def rate(tm):
        if ep_s <= tm < ep_s + ep_len:
            return ep_rate
        return normal * rng.uniform(0.9, 1.1)
    charts, t_prev = [], start
    while t_prev < end:
        t2 = min(end, t_prev + rng.choice([60, 60, 60, 120, 120, 180, 240]) + rng.uniform(-8, 8))
        steps = 12
        vol = sum(rate(t_prev + (t2 - t_prev) * (i + 0.5) / steps) for i in range(steps)) / steps * w * (t2 - t_prev) / 60
        t2 = round(t2)
        if awkward(t2):
            t_prev = t2
            continue
        charts.append({"patient_id": pid, "charted": stamp(t2), "volume_ml": f"{round(vol)}"})
        t_prev = t2
    patient = {"patient_id": pid, "admitted": stamp(start), "discharged": stamp(end), "age_years": rng.randint(18, 90),
               "weight_kg": f"{w:.1f}", "baseline_creatinine_mg_dl": f"{base:.2f}"}
    return patient, creat, charts, rrt


def write(name, rows, fields=None):
    for out in OUTS:
        with open(out / name, "w", newline="") as fh:
            wr = csv.DictWriter(fh, fieldnames=fields or list(rows[0]), lineterminator="\n")
            wr.writeheader()
            wr.writerows(rows)


def main():
    rng = random.Random(20120301)
    pats, creats, urines, rrts, redrawn, k = [], [], [], [], 0, 1
    while k <= N_PATIENTS:
        p, c, u, r = make_patient(rng, k)
        margins = []
        top, on, re_ = stage(p, c, u, r, margins=margins)
        bad = any((kind == "ratio" and m < 0.002) or (kind == "abs" and m < 0.004) or kind == "rise" or
                  (kind == "uo" and m < 0.01) for kind, m in margins)
        if bad or any(x is not None and awkward(x) for x in (on, re_)):
            redrawn += 1
            continue
        pats.append(p)
        creats += c
        urines += u
        if r:
            rrts.append({"patient_id": p["patient_id"], "started": r})
        k += 1
    for out in OUTS:
        (out / "patients.json").write_text(json.dumps(pats, indent=1) + "\n")
    write("creatinine.csv", creats)
    write("urine.csv", urines)
    write("rrt.csv", rrts, ["patient_id", "started"])
    ans = rebuild()
    from collections import Counter
    print(f"patients {len(pats)}, creatinine records {len(creats)}, urine chartings {len(urines)}, "
          f"renal replacement starts {len(rrts)}, redrawn {redrawn}")
    print("max stage:", dict(sorted(Counter(a["max_stage"] for a in ans.values()).items())))
    fam = Counter(t for a in ans.values() for t in a["tags"])
    for t in SHORTCUTS:
        print(f"  {t}: {fam.get(t, 0)} patients changed")


def rebuild():
    d = OUTS[0]
    pats = json.loads((d / "patients.json").read_text())
    rd = lambda n: list(csv.DictReader(open(d / n)))
    by = lambda rows: {p["patient_id"]: [r for r in rows if r["patient_id"] == p["patient_id"]] for p in pats}
    cr, ur = by(rd("creatinine.csv")), by(rd("urine.csv"))
    rr = {r["patient_id"]: r["started"] for r in rd("rrt.csv")}
    ans = {}
    for p in pats:
        pid = p["patient_id"]
        base = stage(p, cr[pid], ur[pid], rr.get(pid))

        def key(x):
            return (x[0], None if x[1] is None else round(x[1]), None if x[2] is None else round(x[2]))
        tags = []
        for name, v in SHORTCUTS.items():
            alt = stage(p, cr[pid], ur[pid], rr.get(pid), v)
            if alt[0] != base[0] or any((a is None) != (b is None) or (a is not None and abs(a - b) > 1.5)
                                        for a, b in zip(alt[1:], base[1:])):
                tags.append(name)
        ans[pid] = {"max_stage": base[0], "onset": base[1], "reached": base[2], "tags": tags}
    (HERE / "evidence" / "answers.json").write_text(json.dumps(ans, indent=0) + "\n")
    (HERE / "../tests/case_tags.json").write_text(json.dumps({k: a["tags"] for k, a in ans.items()}, indent=0) + "\n")
    return ans


if __name__ == "__main__":
    main()
