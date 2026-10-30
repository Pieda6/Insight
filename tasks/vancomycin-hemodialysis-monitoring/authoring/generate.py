"""Generate the hemodialysis vancomycin monitoring cases (seed 20200346).

Writes sessions.csv and levels.csv to both data copies, evidence/answers.json (the generator's own decisions, first
implementation in sim below) and ../tests/case_tags.json (per session, the shortcuts that change its row).
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
N_PATIENTS = 150
MG_PER_UMOL = 1.4493
TABLE = {("after_dialysis", "low"): (25.0, 7.5), ("after_dialysis", "high"): (25.0, 10.0),
         ("intradialytic", "low"): (30.0, 8.75), ("intradialytic", "high"): (35.0, 12.5)}   # Rec. 13, range midpoints


# ------------------------------------------------------------------ sim ------------------------------------
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


def rnd250(x, v):
    if v.get("round_down"):
        return 250 * math.floor(x / 250 + 1e-12)
    return 250 * math.floor(x / 250 + 0.5)


def level_value(r, v):
    res = r["result"].strip()
    try:
        x = float(res)
    except ValueError:
        return None
    return x * (MG_PER_UMOL if r["units"] == "umol/L" and not v.get("umol_as_mg") else 1.0)


def decide(sessions, levels, v=None, margins=None):
    """Rows (session_id, level or None, status, dose) for one patient's sessions in order."""
    v = v or {}
    reports = {}
    for r in levels:
        if v.get("ignore_corrections"):
            reports.setdefault(r["accession"], r)
        elif r["accession"] not in reports or r["status"] == "corrected":
            reports[r["accession"]] = r
    lv = [(utc_min(r["collected"], v.get("naive")), level_value(r, v)) for r in reports.values()]
    lv = [x for x in lv if x[1] is not None]
    spans = [(utc_min(s["start"], v.get("naive")), utc_min(s["stop"], v.get("naive"))) for s in sessions]
    window = 120 if not v.get("window_180") else 180
    lo, hi = (15.0, 20.0)
    target = {"to15": 15.0, "to20": 20.0}.get(v.get("target"), 17.5)
    out, current = [], None
    for k, s in enumerate(sessions):
        start = spans[k][0]
        cands = []
        for t, x in lv:
            if not (start - window <= t < start):
                continue
            if not v.get("no_two_hour") and any(a <= t < b + 120 for a, b in spans[:k]):
                continue
            cands.append((t, x))
            if margins is not None:
                margins.append(("window", abs(t - (start - window)) or 1.0))
        level = (min(cands) if v.get("earliest") else max(cands))[1] if cands else None
        if level is None:
            status = "none"
        elif (level < lo) if not v.get("exclusive") else (level <= lo):
            status = "below"
        elif (level > hi) if not v.get("exclusive") else (level >= hi):
            status = "above"
        else:
            status = "within"
        w = float(s["pre_weight_kg"]) if not v.get("first_weight") else float(sessions[0]["pre_weight_kg"])
        load_kg, maint_kg = TABLE[(s["vancomycin_timing"], s["dialyzer"])]
        if v.get("range_low") and s["vancomycin_timing"] == "intradialytic":
            maint_kg = {"low": 7.5, "high": 10.0}[s["dialyzer"]]
        changed = k > 0 and (s["dialyzer"], s["vancomycin_timing"]) != (sessions[k - 1]["dialyzer"],
                                                                         sessions[k - 1]["vancomycin_timing"])
        if margins is not None and level is not None:
            margins.extend(("level", abs(level - c)) for c in (15.0, 20.0, 25.0) if abs(level - c) > 0)
        if k == 0:
            raw = w * load_kg
            if not v.get("no_cap"):
                raw = min(raw, 3000.0)
            dose = rnd250(raw, v)
            if v.get("current_from_loading"):
                current = dose
            _m(margins, raw)
        elif changed and not v.get("no_reset"):
            raw = w * maint_kg
            current = rnd250(raw, v)
            dose = current
            _m(margins, raw)
        else:
            if current is None:
                raw = w * maint_kg
                current = rnd250(raw, v)
                _m(margins, raw)
            if level is not None and status != "within":
                raw = current * target / level
                _m(margins, raw)
                new = rnd250(raw, v) if not v.get("carry_unrounded") else raw
                if level > 25.0 and not v.get("no_hold"):
                    dose = 0
                    if not v.get("hold_keeps_dose"):
                        current = new
                else:
                    current = new
                    dose = new
            else:
                dose = current
        out.append((s["session_id"], level, status, int(rnd250(dose, {})) if v.get("carry_unrounded") else int(dose)))
    return out


def _m(margins, raw):
    if margins is not None:
        margins.append(("dose", abs((raw % 250) - 125)))


SHORTCUTS = {
    "window_taken_as_three_hours": {"window_180": True},
    "two_hours_after_dialysis_ignored": {"no_two_hour": True}, "umol_read_as_mg": {"umol_as_mg": True},
    "original_kept_over_correction": {"ignore_corrections": True}, "earliest_level_used": {"earliest": True},
    "range_ends_exclusive": {"exclusive": True}, "scaled_to_15": {"target": "to15"}, "scaled_to_20": {"target": "to20"},
    "rounded_down": {"round_down": True}, "loading_not_capped": {"no_cap": True},
    "intradialytic_range_low_end": {"range_low": True}, "no_reset_on_change": {"no_reset": True},
    "no_hold_above_25": {"no_hold": True}, "hold_keeps_previous_dose": {"hold_keeps_dose": True},
    "unrounded_dose_carried": {"carry_unrounded": True}, "loading_dose_as_maintenance": {"current_from_loading": True},
    "first_session_weight_throughout": {"first_weight": True},
}


# ------------------------------------------------------------------ generation ------------------------------
def stamp(m):
    """UTC minutes since 2026-01-01 to New York local text."""
    t = dt.datetime(2026, 1, 1) + dt.timedelta(minutes=m)
    for off in (4, 5):
        w = t - dt.timedelta(hours=off)
        txt = w.strftime("%Y-%m-%d %H:%M")
        if utc_min(txt) == m:
            return txt
    raise ValueError


def ambiguous(m):
    w = dt.datetime(2026, 1, 1) + dt.timedelta(minutes=m) - dt.timedelta(hours=5)
    return w.month == 11 and w.day == 1 and w.hour in (0, 1, 2)


def make_patient(rng, k):
    pid = f"HD-{k:03d}"
    anchor = rng.choice([dt.datetime(2026, 3, 8), dt.datetime(2026, 11, 1), dt.datetime(2026, 6, 1)])
    first = anchor - dt.timedelta(days=rng.randint(3, 16))
    days = [0, 2, 4] if rng.random() < 0.5 else [1, 3, 5]
    start_hour = rng.uniform(5.0, 13.0)
    n = rng.randint(9, 13)
    dialyzer = "high" if rng.random() < 0.7 else "low"
    timing = "intradialytic" if rng.random() < 0.5 else "after_dialysis"
    change_at = rng.randint(3, n - 2) if rng.random() < 0.3 else None
    weight = rng.uniform(52, 112)
    lab_umol = rng.random() < 0.3
    sess, week = [], 0
    split_at = rng.randint(2, n - 2) if rng.random() < 0.2 else None
    while len(sess) < n:
        for d in days:
            if len(sess) >= n:
                break
            day = first + dt.timedelta(days=7 * week + d)
            local = day + dt.timedelta(hours=start_hour + rng.uniform(-0.6, 0.6))
            m = round(utc_min(local.strftime("%Y-%m-%d %H:%M")) )
            dur = rng.randint(210, 240)
            sess.append([m, m + dur])
            if split_at is not None and len(sess) == split_at:
                gap = rng.randint(150, 230)                     # interrupted, then a second run the same day
                m2 = m + dur + gap
                sess.append([m2, m2 + rng.randint(90, 150)])
        week += 1
    sess = sess[:n]
    if any(ambiguous(a) or ambiguous(b) for a, b in sess):
        return None
    if change_at is not None:
        what = rng.choice(["dialyzer", "timing"])
    rows = []
    for i, (a, b) in enumerate(sess):
        dz, tm = dialyzer, timing
        if change_at is not None and i >= change_at:
            if what == "dialyzer":
                dz = "low" if dialyzer == "high" else "high"
            else:
                tm = "after_dialysis" if timing == "intradialytic" else "intradialytic"
        weight += rng.uniform(-1.2, 1.2)
        rows.append({"patient_id": pid, "session_id": f"{pid}-S{i + 1:02d}", "start": stamp(a), "stop": stamp(b),
                     "dialyzer": dz, "vancomycin_timing": tm, "pre_weight_kg": f"{weight:.1f}"})
    # levels
    levels, acc = [], [0]

    def add(t, mg, status="final", result=None, units=None):
        acc[0] += 1
        u = units or ("umol/L" if lab_umol else "mg/L")
        if result is None:
            result = f"{mg / MG_PER_UMOL:.1f}" if u == "umol/L" else f"{mg:.1f}"
        rec = {"patient_id": pid, "accession": f"{pid}-A{acc[0]:03d}", "collected": stamp(t), "result": result,
               "units": u, "status": status}
        levels.append(rec)
        return rec

    def value():
        u = rng.random()
        if u < 0.45:
            c = rng.choice([15.0, 20.0, 25.0])
            return c + rng.choice([-1, 1]) * rng.choice([0.0, 0.1, 0.2, 0.3, rng.uniform(0.3, 1.5)])
        return rng.uniform(8.0, 34.0)
    for i, (a, b) in enumerate(sess):
        if i == 0 or rng.random() < 0.35:
            continue
        u = rng.random()
        if u < 0.18:
            off = rng.choice([118, 119, 120, 121, 122])          # at the edge of the 2-hour window
        else:
            off = rng.randint(3, 115)
        t = a - off
        if ambiguous(t):
            continue
        r = add(t, value())
        if rng.random() < 0.12:                                  # corrected later, same accession
            wrong = dict(r)
            levels.remove(r)
            wrong["result"] = f"{float(r['result']) * rng.uniform(0.6, 1.4):.1f}"
            levels.append(wrong)
            levels.append(dict(r, status="corrected"))
        if rng.random() < 0.15:                                  # repeat draw nearer the start
            t2 = a - rng.randint(1, max(2, off - 1))
            if not ambiguous(t2):
                add(t2, value())
        if rng.random() < 0.1:
            add(a - rng.randint(5, 100), 0, result=rng.choice(["rejected: hemolyzed", "cancelled", "rejected: clotted"]))
        if rng.random() < 0.25:                                  # post-dialysis level, not a predialysis one
            t3 = b + rng.randint(5, 180)
            if not ambiguous(t3):
                add(t3, rng.uniform(6, 14))
    if split_at is not None:                                     # level between the two runs of the split day
        a1, b1 = sess[split_at - 1]
        a2 = sess[split_at][0]
        t = b1 + rng.choice([110, 118, 119, 121, 122, 135])
        if a2 - 120 <= t < a2 and not ambiguous(t):
            add(t, value())
    return rows, levels


def write(name, rows):
    for out in OUTS:
        with open(out / name, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]), lineterminator="\n")
            w.writeheader()
            w.writerows(rows)


def main():
    rng = random.Random(20200346)
    sessions, levels, redrawn = [], [], 0
    k = 1
    while k <= N_PATIENTS:
        made = make_patient(rng, k)
        if made is None:
            redrawn += 1
            continue
        s, lv = made
        margins = []
        rows = decide(s, lv, margins=margins)
        # no dose at a rounding midpoint, no level at a cut-off by floating point, doses never zero by rounding
        if min((m for k2, m in margins if k2 == "dose"), default=9) < 0.2 or \
                min((m for k2, m in margins if k2 == "level"), default=9) < 1e-4 or \
                min((m for k2, m in margins if k2 == "window"), default=9) < 0.5 or any(r[3] == 0 and r[1] is not None and r[1] <= 25 for r in rows) or \
                any(r[3] < 0 for r in rows):
            redrawn += 1
            continue
        sessions += s
        levels += lv
        k += 1
    write("sessions.csv", sessions)
    write("levels.csv", levels)
    answers = rebuild()
    fam = {}
    for a in answers.values():
        for t in a["tags"]:
            fam[t] = fam.get(t, 0) + 1
    st = {}
    for a in answers.values():
        st[a["status"]] = st.get(a["status"], 0) + 1
    print(f"patients {N_PATIENTS}, sessions {len(sessions)}, level records {len(levels)}, redrawn {redrawn}")
    print("statuses:", st, "held doses:", sum(a["dose"] == 0 for a in answers.values()))
    for t in SHORTCUTS:
        print(f"  {t}: {fam.get(t, 0)} sessions changed")


def rebuild():
    data = OUTS[0]
    rd = lambda n: list(csv.DictReader(open(data / n)))
    sess, lev = {}, {}
    for s in rd("sessions.csv"):
        sess.setdefault(s["patient_id"], []).append(s)
    for r in rd("levels.csv"):
        lev.setdefault(r["patient_id"], []).append(r)
    answers = {}
    for pid, ss in sess.items():
        base = decide(ss, lev.get(pid, []))
        alt = {name: decide(ss, lev.get(pid, []), v) for name, v in SHORTCUTS.items()}
        for i, (sid, level, status, dose) in enumerate(base):
            tags = [n for n, rows in alt.items() if rows[i][2:] != (status, dose) or
                    (rows[i][1] is None) != (level is None) or
                    (level is not None and rows[i][1] is not None and abs(rows[i][1] - level) > 0.05)]
            answers[sid] = {"level": level, "status": status, "dose": dose, "tags": tags}
    (HERE / "evidence" / "answers.json").write_text(json.dumps(answers, indent=0) + "\n")
    (HERE / "../tests/case_tags.json").write_text(json.dumps({k: a["tags"] for k, a in answers.items()},
                                                             indent=0, sort_keys=True) + "\n")
    return answers


if __name__ == "__main__":
    main()
