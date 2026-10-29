#!/usr/bin/env python3
"""Build the patients for vancomycin-auc-dosing.

Usage: python3 generate.py            (from authoring/; writes ../environment/data and ../tests/data)

Each patient gets a true clearance and volume (clearance from Cockcroft-Gault creatinine clearance, volume about
0.7 L/kg), a regimen inside the guideline ranges (maintenance 15 to 20 mg/kg-sized doses every 8, 12 or 24 hours,
loading 20 to 35 mg/kg up to 3,000 mg, at most 5 mg/mL and at least 1 hour per 1,000 mg), and an administration
record with real-world irregularities (late and early doses, held doses, paused, interrupted and partly given
infusions, rate changes, order changes). Two usable levels are drawn in one of four patterns (steady-state peak and
trough in one interval, trough then peak around one dose, first-day levels after the first dose, and peak and
trough two intervals apart), plus unusable results (rejected specimens, results below the reporting limit, levels
drawn during an infusion or less than an hour after one). Level values are the true concentration with assay
noise, to 0.1 mg/L. The answers are then fitted from the recorded data with sim.py.

Planted values sit near the thresholds that change an answer: AUC24 0.6 to 2 percent inside and outside 400 and 600,
doses 0.6 to 2 percent either side of a 250 mg rounding midpoint, and levels drawn 55 to 59 or 61 to 65 minutes after an infusion
ends. Every patient keeps at least 0.6 percent between AUC24 and 400 or 600 and between the unrounded new dose
and a rounding midpoint (more than the 0.5 percent tolerance; the MIC is 1 mg/L for everyone, Recommendation 6), and exactly one solution for the elimination rate between 0.0001 and
3 per hour.
"""
import sys
sys.dont_write_bytecode = True       # never leave __pycache__ in the submitted task folder
import csv
import datetime as dt
import json
import math
import random
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sim  # noqa: E402

SEED = 20200601
N = 240
STATS = Counter()
MARGIN = 0.006      # every boundary and rounding midpoint more than the 0.5 percent tolerance away
EPOCH = dt.datetime(2026, 3, 10, 0, 0)       # after the 2026 DST change; all records before November


def stamp(minutes):
    return (EPOCH + dt.timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M")


def bag_for(dose):
    return 250 if dose <= 1250 else 500 if dose <= 2500 else 750


def minutes_for(dose):
    return {500: 60, 750: 60, 1000: 60, 1250: 90, 1500: 90, 1750: 120, 2000: 120, 2250: 150, 2500: 150,
            2750: 180, 3000: 180}[dose]


class Patient:
    def __init__(self, rng, idx):
        self.rng = rng
        self.pid = f"VP-{idx:04d}"
        self.sex = rng.choice("MF")
        self.age = rng.randint(21, 89)
        self.weight = round(rng.uniform(48, 150) if rng.random() < 0.85 else rng.uniform(150, 190), 1)
        self.height = rng.randint(150, 196) if self.sex == "M" else rng.randint(145, 182)
        self.scr = round(rng.uniform(0.5, 2.6) if rng.random() < 0.8 else rng.uniform(0.4, 0.8), 2)
        crcl = (140 - self.age) * min(self.weight, 120) / (72 * self.scr) * (0.85 if self.sex == "F" else 1)
        crcl = min(max(crcl, 15), 160)
        self.cl = 0.05 * crcl * rng.uniform(0.8, 1.25)
        self.v = 0.7 * self.weight * rng.uniform(0.75, 1.3)
        self.ke = self.cl / self.v
        if crcl > 90:
            self.tau = rng.choice([8, 12, 12])
        elif crcl > 50:
            self.tau = rng.choice([12, 12, 24])
        else:
            self.tau = 24
        target = rng.uniform(250, 950)
        dose = target * self.cl * self.tau / 24
        self.dose = int(min(max(round(dose / 250) * 250, 500), 2500))
        self.loading = None
        if rng.random() < 0.7:
            self.loading = int(min(round(self.weight * rng.uniform(20, 35) / 250) * 250, 3000))
            self.loading = max(self.loading, 1000)
        r = rng.random()
        if r < 0.35:
            self.mic = None
        elif r < 0.65:
            self.mic = {"value_mg_l": rng.choice([0.5, 0.5, 1.0, 1.0, 1.0, 2.0]), "method": "broth microdilution"}
        else:
            self.mic = {"value_mg_l": rng.choice([0.5, 0.75, 1.0, 1.5, 2.0]),
                        "method": rng.choice(["Etest", "Etest", "Vitek 2", "MicroScan"])}
        self.unit = rng.choice(["MICU", "SICU", "CCU", "6 West", "7 East", "Step-down"])
        self.start = rng.randint(0, 60 * 24 * 70)

    # ---- dosing record -----------------------------------------------------------------------------------
    def build_doses(self, n_maint):
        """Planned and actual administrations. Returns list of dicts with events (minutes)."""
        rng = self.rng
        admins = []
        t = self.start
        plan = []
        if self.loading:
            plan.append((t, self.loading))
            t += self.tau * 60
        self.orders = []
        if self.loading:
            self.orders.append(("once", self.start - rng.randint(15, 90), self.loading, None))
        dose = self.dose
        change_at = rng.randint(2, 4) if rng.random() < 0.25 else None
        first_dose = self.dose if change_at is None else int(min(max(self.dose + rng.choice([-500, -250, 250, 500]), 500), 2500))
        self.orders.append(("maint", t - rng.randint(30, 300), first_dose, self.tau))
        for i in range(n_maint):
            if change_at is not None and i == change_at:
                self.orders.append(("maint", t - rng.randint(60, 240), self.dose, self.tau))
            plan.append((t, first_dose if (change_at is not None and i < change_at) else dose))
            t += self.tau * 60
        for j, (when, mg) in enumerate(plan):
            aid = f"{self.pid}-A{j + 1:02d}"
            shift = int(rng.choice([0, 0, 0, rng.randint(-30, 10), rng.randint(10, 120)]))
            s = when + shift
            if j > 0 and rng.random() < 0.04 and j != len(plan) - 1:
                admins.append({"id": aid, "dose": mg, "held": True, "time": s, "events": []})
                continue
            bag = bag_for(mg)
            dur = minutes_for(mg)
            rate = round(bag / (dur / 60))
            run = bag / rate * 60
            kind = rng.random()
            ev = [(s, "start", None, rate)]
            if kind < 0.10:
                x = rng.randint(10, int(run) - 10)
                v = round(rate * x / 60)
                p = rng.randint(10, 75)
                ev.append((s + x, "pause", v, None))
                ev.append((s + x + p, "resume", None, rate))
                end = s + x + p + round((bag - v) / rate * 60)
                ev.append((end, "stop", bag, None))
                STATS["paused infusions"] += 1
            elif kind < 0.16:
                x = rng.randint(15, int(run) - 5)
                v = round(rate * x / 60)
                ev.append((s + x, "stop", v, None))
                STATS["partly given infusions"] += 1
            elif kind < 0.24:
                x = rng.randint(10, int(run) - 10)
                v = round(rate * x / 60)
                r2 = round(rate * rng.choice([0.5, 0.67, 0.75, 1.25, 1.5]))
                ev.append((s + x, "rate_change", v, r2))
                ev.append((s + x + round((bag - v) / r2 * 60), "stop", bag, None))
                STATS["rate changes"] += 1
            else:
                ev.append((s + round(run), "stop", bag, None))
            admins.append({"id": aid, "dose": mg, "held": False, "time": s, "events": ev, "bag": bag})
        return admins

    def segments(self, admins):
        segs = []
        for a in admins:
            if a["held"]:
                continue
            conc = a["dose"] / a["bag"]
            prev_t, prev_v = None, 0
            for t, kind, vol, _ in a["events"]:
                if kind in ("start", "resume"):
                    prev_t = t
                    continue
                if prev_t is not None and t > prev_t and vol > prev_v:
                    segs.append([prev_t, t, (vol - prev_v) * conc])
                if kind == "rate_change":
                    prev_t, prev_v = t, vol
                else:
                    prev_t, prev_v = None, vol
        return segs

    def intervals(self, admins):
        """(start, stop) of every given administration (pauses included)."""
        out = []
        for a in admins:
            if not a["held"]:
                out.append((a["events"][0][0], a["events"][-1][0]))
        return out


def usable(t, spans):
    return all(not (s <= t <= e) and not (e < t < e + 60) for s, e in spans)


def make_patient(rng, idx):
    p = Patient(rng, idx)
    pattern = rng.choice(["ss_same", "trough_peak", "trough_peak", "first_day", "first_day", "spread", "spread"])
    k = {"ss_same": rng.randint(3, 5), "trough_peak": rng.randint(3, 5), "first_day": 0, "spread": rng.randint(2, 4)}[pattern]
    admins = p.build_doses(k + 4)
    given = [a for a in admins if not a["held"]]
    if k + 2 >= len(given):
        return None
    spans = p.intervals(admins)
    end_k = given[k]["events"][-1][0]
    start_next = given[k + 1]["events"][0][0]
    if pattern in ("ss_same", "first_day"):
        t_peak = end_k + rng.choice([rng.randint(61, 65), rng.randint(65, 120)])
        t2 = start_next - rng.randint(5, 45) if pattern == "ss_same" else t_peak + rng.randint(240, 600)
        times = [t_peak, t2]
    elif pattern == "trough_peak":
        t_tr = given[k]["events"][0][0] - rng.randint(5, 45)
        times = [t_tr, end_k + rng.choice([rng.randint(61, 65), rng.randint(65, 120)])]
    else:
        t_peak = end_k + rng.randint(61, 120)
        times = [t_peak, given[k + 2]["events"][0][0] - rng.randint(5, 45)]
    if not all(usable(t, spans) for t in times) or times[0] >= times[1]:
        return None
    if any(t == s or t == e or t == e + 60 for t in times for s, e in spans):
        return None
    segs = p.segments(admins)
    t0 = segs[0][0]
    rel = [[s - t0, e - t0, mg] for s, e, mg in segs]

    def true_conc(t):
        return sim.amount_at((t - t0) / 60, [(s / 60, e / 60, mg) for s, e, mg in rel], p.ke) / p.v

    levels = []
    for t in times:
        c = true_conc(t) * rng.uniform(0.92, 1.08)
        levels.append([t, round(c, 1), True])
    # unusable results
    extras = []
    if rng.random() < 0.35:
        a = rng.choice(given[1:k + 2])
        s0, e0 = a["events"][0][0], a["events"][-1][0]
        extras.append((rng.randint(s0 + 5, e0 - 5), "during"))
    if rng.random() < 0.35:
        a = rng.choice(given[:k + 2])
        extras.append((a["events"][-1][0] + rng.choice([rng.randint(55, 59), rng.randint(20, 54)]), "early"))
    if rng.random() < 0.2:
        extras.append((rng.choice(times) + rng.randint(-20, 20), "rejected"))
    if rng.random() < 0.25:
        extras.append((given[0]["events"][0][0] - rng.randint(30, 300), "baseline"))
    for t, why in extras:
        if why in ("during", "early") and usable(t, spans):
            continue
        if any(t == s or t == e or t == e + 60 for s, e in spans):
            continue
        if why == "rejected":
            levels.append([t, rng.choice(["Specimen hemolyzed - recollect", "Clotted specimen - rejected",
                                          "Unlabeled specimen - rejected", "QNS - test cancelled"]), False])
        elif why == "baseline":
            levels.append([t, "<4.0", False])
        else:
            levels.append([t, round(true_conc(t) * rng.uniform(0.92, 1.08), 1), False])
        STATS[f"unusable result ({why})"] += 1
    p.admins, p.levels, p.segs, p.t0, p.pattern = admins, levels, rel, t0, pattern
    return p


def answers(p):
    segs = [(s / 60, e / 60, mg) for s, e, mg in p.segs]
    use = [(t, c) for t, c, ok in p.levels if ok]
    (ta, ca), (tb, cb) = sorted(use)
    ke, V, roots = sim.fit(segs, (ta - p.t0) / 60, ca, (tb - p.t0) / 60, cb)
    if ke is None:
        return None
    cur = max((o for o in p.orders if o[0] == "maint"), key=lambda o: o[1])
    mic = 1.0                                   # guideline Recommendation 6: measured MICs do not change the target
    cl = ke * V
    auc24 = cur[2] * 24 / cur[3] / cl
    auc48 = sim.auc_to(48.0, segs, ke, V)
    ratio = auc24 / mic
    raw = 500 * mic * cl * cur[3] / 24
    if 400 <= ratio <= 600:
        exposure, new = "within", cur[2]
    else:
        exposure = "below" if ratio < 400 else "above"
        new = int(math.floor(raw / 250 + 0.5) * 250)
    return dict(ke=ke, V=V, auc48=auc48, auc24=auc24, ratio=ratio, raw=raw, exposure=exposure, new=new, mic=mic,
                cur=cur)


def margins(a):
    m_ratio = min(abs(a["ratio"] / 400 - 1), abs(a["ratio"] / 600 - 1))
    frac = a["raw"] / 250 - math.floor(a["raw"] / 250)
    m_round = abs(frac - 0.5) * 250 / a["raw"] if a["exposure"] != "within" else 999   # relative
    return m_ratio, m_round


def plant(rng, p, goal):
    """Nudge one usable level by 0.1 mg/L steps until the goal margin falls in its band."""
    idx = [i for i, l in enumerate(p.levels) if l[2]]
    best = None
    for i in idx:
        base = p.levels[i][1]
        for step in range(-60, 61):
            p.levels[i][1] = round(base + step * 0.1, 1)
            if p.levels[i][1] <= 0.5:
                continue
            a = answers(p)
            if a is None or not (0.01 <= a["ke"] <= 0.5 and 15 <= a["V"] <= 260):
                continue
            mr, mro = margins(a)
            if mr < MARGIN or mro < MARGIN:
                continue
            if goal == "ratio" and MARGIN <= mr <= 0.02:
                best = (i, p.levels[i][1])
            if goal == "round" and MARGIN <= mro <= 0.02 and a["exposure"] != "within":
                best = (i, p.levels[i][1])
            if best:
                return True
        p.levels[i][1] = base
    return False


def main():
    rng = random.Random(SEED)
    pats = []
    idx = 1
    while len(pats) < N:
        p = make_patient(rng, idx)
        if p is None:
            STATS["redrawn"] += 1
            continue
        a = answers(p)
        if a is None or not (0.01 <= a["ke"] <= 0.5 and 15 <= a["V"] <= 260):
            STATS["redrawn"] += 1
            continue
        r = rng.random()
        if r < 0.3:
            if plant(rng, p, "ratio"):
                STATS["planted AUC24/MIC near 400 or 600"] += 1
        elif r < 0.5 and a["exposure"] != "within":
            if plant(rng, p, "round"):
                STATS["planted dose near a 250 mg rounding step"] += 1
        a = answers(p)
        mr, mro = margins(a)
        if a is None or mr < MARGIN or mro < MARGIN or not (0.01 <= a["ke"] <= 0.5 and 15 <= a["V"] <= 260):
            STATS["redrawn"] += 1
            continue
        p.ans = a
        pats.append(p)
        idx += 1
    write(pats)
    c = Counter(p.ans["exposure"] for p in pats)
    print(f"patients {len(pats)}; exposure {dict(c)}; patterns {dict(Counter(p.pattern for p in pats))}")
    print("MIC used", dict(Counter(p.ans["mic"] for p in pats)))
    for k, v in sorted(STATS.items()):
        print(f"{k}: {v}")


def write(pats):
    rng = random.Random(SEED + 1)
    patients, admin_rows, level_rows, order_rows = [], [], [], []
    for p in pats:
        patients.append({"patient_id": p.pid, "unit": p.unit, "age": p.age, "sex": p.sex, "weight_kg": p.weight,
                         "height_cm": p.height, "serum_creatinine_mg_dl": p.scr, "isolate_mic": p.mic})
        for a in p.admins:
            if a["held"]:
                admin_rows.append([p.pid, a["id"], stamp(a["time"]), "not_given", a["dose"], "", "", "",
                                   rng.choice(["held - patient in OR", "held - per prescriber", "held - IV access lost"])])
                continue
            for t, kind, vol, rate in a["events"]:
                if kind == "start":
                    row = [p.pid, a["id"], stamp(t), "start", a["dose"], a["bag"], rate, "", ""]
                elif kind == "resume":
                    row = [p.pid, a["id"], stamp(t), "resume", "", "", rate, "", ""]
                elif kind == "rate_change":
                    row = [p.pid, a["id"], stamp(t), "rate_change", "", "", rate, vol, ""]
                elif kind == "pause":
                    row = [p.pid, a["id"], stamp(t), "pause", "", "", "", vol,
                           rng.choice(["line occluded", "patient to imaging", "IV site check", "blood transfusion"])]
                else:
                    note = "" if vol == a["bag"] else rng.choice(["IV infiltrated - discontinued", "bag leaking - discontinued"])
                    row = [p.pid, a["id"], stamp(t), "stop", "", "", "", vol, note]
                admin_rows.append(row)
        for j, (t, c, ok) in enumerate(sorted(p.levels, key=lambda l: l[0])):
            label = rng.choice(["Vancomycin, random", "Vancomycin, trough", "Vancomycin, peak", "Vancomycin level"])
            if isinstance(c, float):
                text = f"{c:.1f}" + (" H" if c > 40 else "")
            else:
                text = c
            level_rows.append([p.pid, f"L{rng.randint(10**7, 10**8 - 1)}", stamp(t), label, text, "mg/L"])
        for j, (kind, when, dose, tau) in enumerate(p.orders):
            order_rows.append([p.pid, f"{p.pid}-O{j + 1}", stamp(when), dose,
                               "once" if tau is None else f"every {tau} hours"])
    for root in (HERE.parent / "environment" / "data", HERE.parent / "tests" / "data"):
        root.mkdir(parents=True, exist_ok=True)
        (root / "patients.json").write_text(json.dumps(patients, indent=1) + "\n")
        for name, header, rows in (
                ("administrations.csv", ["patient_id", "administration_id", "time", "event", "dose_mg", "bag_volume_ml",
                                         "rate_ml_h", "volume_infused_ml", "comment"], admin_rows),
                ("levels.csv", ["patient_id", "accession", "collected", "test", "result", "units"], level_rows),
                ("orders.csv", ["patient_id", "order_id", "ordered", "dose_mg", "frequency"], order_rows)):
            with open(root / name, "w", newline="") as fh:
                w = csv.writer(fh, lineterminator="\n")
                w.writerow(header)
                w.writerows(rows)


if __name__ == "__main__":
    main()


def rebuild_answers(data=None):
    """Fit every patient from the written files with sim.py (used by check_agreement.py)."""
    import re
    data = Path(data or HERE.parent / "tests" / "data")
    pats = json.loads((data / "patients.json").read_text())

    def rows(name):
        with open(data / name, newline="") as fh:
            return list(csv.DictReader(fh))

    def mins(s):
        return (dt.datetime.strptime(s, "%Y-%m-%d %H:%M") - EPOCH).total_seconds() / 60

    adm, lev, ords = rows("administrations.csv"), rows("levels.csv"), rows("orders.csv")
    out = {}
    for p in pats:
        pid = p["patient_id"]
        ev = {}
        for r in adm:
            if r["patient_id"] == pid:
                ev.setdefault(r["administration_id"], []).append(r)
        segs, spans = [], []
        for rs in ev.values():
            if rs[0]["event"] == "not_given":
                continue
            conc = float(rs[0]["dose_mg"]) / float(rs[0]["bag_volume_ml"])
            on, v0 = None, 0.0
            for r in rs:
                t = mins(r["time"])
                if r["event"] in ("start", "resume"):
                    on = t
                    continue
                v = float(r["volume_infused_ml"])
                if on is not None and v > v0:
                    segs.append([on, t, (v - v0) * conc])
                v0, on = v, (t if r["event"] == "rate_change" else None)
            spans.append((mins(rs[0]["time"]), mins(rs[-1]["time"])))
        levels = []
        for r in lev:
            if r["patient_id"] != pid:
                continue
            m = re.match(r"^(\d+\.\d)( H)?$", r["result"])
            t = mins(r["collected"])
            levels.append([t, float(m.group(1)) if m else r["result"], bool(m) and usable(t, spans)])
        o = [r for r in ords if r["patient_id"] == pid]
        q = Patient.__new__(Patient)
        q.segs = segs
        q.t0 = min(s for s, _, _ in segs)
        q.segs = [[s - q.t0, e - q.t0, mg] for s, e, mg in segs]
        q.levels = levels
        q.orders = [("once" if r["frequency"] == "once" else "maint", mins(r["ordered"]), int(r["dose_mg"]),
                     None if r["frequency"] == "once" else int(r["frequency"].split()[1])) for r in o]
        q.mic = p["isolate_mic"]
        out[pid] = answers(q)
    return out
