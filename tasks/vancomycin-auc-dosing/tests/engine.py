"""Independent verifier model for vancomycin-auc-dosing.

Written separately from the reference solution: concentrations are evaluated per segment in the form
R/ke * (exp(-ke (t - min(t, end))) - exp(-ke (t - start))), the elimination rate is found by the Illinois regula
falsi method on the concentration ratio, and the 48-hour AUC is integrated numerically with 24-point
Gauss-Legendre quadrature between consecutive event times (the curve is smooth between them).

Guideline: Rybak et al., Am J Health-Syst Pharm 2020;77:835-864 (AUC/MIC 400 to 600 with the MIC assumed to
be 1 mg/L as Recommendation 6 says, postdistributional sampling at least 1 hour after the end of the infusion).
"""
import csv
import datetime as dt
import json
import math
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
REF = dt.datetime(2026, 1, 1)


def hours(text):
    return (dt.datetime.strptime(text, "%Y-%m-%d %H:%M") - REF).total_seconds() / 3600.0


# ---- one-compartment model ----------------------------------------------------------------------------------
def amount(segs, t, ke):
    a = 0.0
    for s, e, mg in segs:
        if t > s:
            r = mg / (e - s)
            a += r / ke * (math.exp(-ke * (t - min(t, e))) - math.exp(-ke * (t - s)))
    return a


def _gauss_legendre(n):
    nodes, weights = [], []
    for i in range(1, n + 1):
        x = math.cos(math.pi * (i - 0.25) / (n + 0.5))
        for _ in range(100):
            p0, p1 = 1.0, x
            for k in range(2, n + 1):
                p0, p1 = p1, ((2 * k - 1) * x * p1 - (k - 1) * p0) / k
            dp = n * (x * p1 - p0) / (x * x - 1)
            dx = p1 / dp
            x -= dx
            if abs(dx) < 1e-16:
                break
        nodes.append(x)
        weights.append(2 / ((1 - x * x) * dp * dp))
    return nodes, weights


GL = _gauss_legendre(24)


def area(segs, T, ke):
    """Integral of amount() from 0 to T, piecewise between event times."""
    cuts = sorted({0.0, T} | {x for s, e, _ in segs for x in (s, e) if 0 < x < T})
    tot = 0.0
    for a, b in zip(cuts, cuts[1:]):
        half, mid = (b - a) / 2, (a + b) / 2
        tot += half * sum(w * amount(segs, mid + half * x, ke) for x, w in zip(*GL))
    return tot


def solve_ke(segs, t1, c1, t2, c2):
    def f(k):
        return amount(segs, t1, k) * c2 - amount(segs, t2, k) * c1
    pts = [10 ** (-4 + 4.5 * i / 450) for i in range(451)]
    vals = [f(k) for k in pts]
    hits = [i for i in range(450) if (vals[i] > 0) != (vals[i + 1] > 0)]
    if len(hits) != 1:
        raise ValueError(f"{len(hits)} solutions")
    a, b = pts[hits[0]], pts[hits[0] + 1]
    fa, fb = vals[hits[0]], vals[hits[0] + 1]
    side = 0
    c = a
    for _ in range(300):
        c = (a * fb - b * fa) / (fb - fa)
        fc = f(c)
        if fc == 0 or abs(b - a) < 1e-14 * b:
            break
        if (fc > 0) == (fb > 0):
            b, fb = c, fc
            if side == -1:
                fa /= 2
            side = -1
        else:
            a, fa = c, fc
            if side == 1:
                fb /= 2
            side = 1
    return c


# ---- records -----------------------------------------------------------------------------------------------
def segments_of(rows):
    """Constant-rate segments (start h, end h, mg) of one administration from its pump events."""
    rows = sorted(rows, key=lambda r: hours(r["time"]))
    first = rows[0]
    if first["event"] != "start":
        return [], None
    mg_per_ml = float(first["dose_mg"]) / float(first["bag_volume_ml"])
    out = []
    running_from, vol_before = None, 0.0
    for r in rows:
        t = hours(r["time"])
        if r["event"] in ("start", "resume"):
            running_from = t
            continue
        v = float(r["volume_infused_ml"])
        if running_from is not None and v > vol_before:
            out.append((running_from, t, (v - vol_before) * mg_per_ml))
        vol_before = v
        running_from = t if r["event"] == "rate_change" else None
    return out, (hours(rows[0]["time"]), hours(rows[-1]["time"]))


def parse_result(text):
    tok = text.split()
    if not tok:
        return None
    try:
        v = float(tok[0])
    except ValueError:
        return None
    if len(tok) > 2 or (len(tok) == 2 and tok[1] not in ("H", "L")) or not math.isfinite(v):
        return None
    return v


def load(data=None):
    data = Path(data or DATA)
    pats = json.loads((data / "patients.json").read_text())

    def rows(name):
        with open(data / name, newline="") as fh:
            return list(csv.DictReader(fh))
    return pats, rows("administrations.csv"), rows("levels.csv"), rows("orders.csv")


def evaluate(p, adm, lev, ords):
    """Everything about one patient: answers plus facts used to tag method families."""
    by_admin = {}
    for r in adm:
        by_admin.setdefault(r["administration_id"], []).append(r)
    segs, spans, irregular = [], [], False
    for rows in by_admin.values():
        s, span = segments_of(rows)
        if span is None:
            irregular = True
            continue
        segs += s
        spans.append(span)
        if len(rows) > 2 or any(r["comment"] for r in rows):
            irregular = True
    t0 = min(s for s, _, _ in segs)
    segs = [(s - t0, e - t0, mg) for s, e, mg in segs]
    spans = [(a - t0, b - t0) for a, b in spans]

    usable, mistimed, unreadable, near_hour = [], 0, 0, False
    for r in lev:
        v = parse_result(r["result"])
        t = hours(r["collected"]) - t0
        if v is None:
            unreadable += 1
            continue
        if not math.isfinite(t):
            raise ValueError(f"{p['patient_id']}: collection time is not a finite number")
        after = [t - b for a, b in spans if t > b]
        if any(a <= t <= b for a, b in spans) or any(x < 1.0 for x in after):
            mistimed += 1
            if any(0.9 <= x < 1.0 for x in after):
                near_hour = True
            continue
        if any(1.0 < x <= 1.1 for x in after):
            near_hour = True
        usable.append((t, v))
    usable.sort()
    if len(usable) != 2:
        raise ValueError(f"{p['patient_id']}: {len(usable)} usable levels")
    (t1, c1), (t2, c2) = usable
    ke = solve_ke(segs, t1, c1, t2, c2)
    vol = amount(segs, t1, ke) / c1
    clearance = ke * vol

    maint = [o for o in ords if o["frequency"].startswith("every")]
    cur = max(maint, key=lambda o: hours(o["ordered"]))
    dose = float(cur["dose_mg"])
    tau = float(cur["frequency"].split()[1])
    auc24 = dose * (24.0 / tau) / clearance
    auc48 = area(segs, 48.0, ke) / vol
    mic_info = p["isolate_mic"]
    mic = 1.0                                  # Recommendation 6: measured MICs do not change the target
    ratio = auc24 / mic
    if ratio < 400:
        exposure = "below"
    elif ratio > 600:
        exposure = "above"
    else:
        exposure = "within"
    raw = 500 * mic * clearance * tau / 24
    new = int(dose) if exposure == "within" else 250 * int(math.floor(raw / 250 + 0.5))

    before = [sp for sp in spans if sp[0] < t1]
    tags = set()
    if len(before) <= 1:
        tags.add("first_day_levels")
    if any(t1 < sp[0] < t2 for sp in spans):
        tags.add("dose_given_between_levels")
    if irregular:
        tags.add("irregular_administration_records")
    if mistimed:
        tags.add("mistimed_levels")
    if unreadable:
        tags.add("rejected_or_unreportable_results")
    if near_hour:
        tags.add("levels_near_one_hour_after_infusion")
    if mic_info and mic_info["value_mg_l"] != 1.0:
        tags.add("measured_mic_not_1")
    if min(abs(ratio / 400 - 1), abs(ratio / 600 - 1)) <= 0.02:
        tags.add("near_target_edges")
    if exposure != "within" and abs(raw / 250 - math.floor(raw / 250) - 0.5) * 250 / raw <= 0.02:
        tags.add("near_rounding_steps")
    if len(maint) > 1:
        tags.add("changed_orders")
    tags.add(f"exposure_{exposure}")
    if not all(math.isfinite(x) for x in (ke, vol, auc48, auc24, ratio, raw)):
        raise ValueError(f"{p['patient_id']}: non-finite result")
    return dict(ke=ke, volume=vol, auc48=auc48, auc24=auc24, exposure=exposure, new_dose=new, tags=tags)


def expected(data=None):
    pats, adm, lev, ords = load(data)
    group = lambda rows: {k: [r for r in rows if r["patient_id"] == k] for k in {r["patient_id"] for r in rows}}
    A, L, O = group(adm), group(lev), group(ords)
    out = {}
    for p in pats:
        pid = p["patient_id"]
        out[pid] = evaluate(p, A.get(pid, []), L.get(pid, []), O.get(pid, []))
    return dict(sorted(out.items()))


# ---- textbook checks used by golden.json ----------------------------------------------------------------------
def end_of_infusion_conc(dose_mg, hours_inf, ke, vol):
    """Single constant-rate infusion: C = R/(ke V) (1 - exp(-ke T))."""
    return amount([(0.0, hours_inf, dose_mg)], hours_inf, ke) / vol


def steady_state_peak(dose_mg, hours_inf, tau, ke, vol, n_doses=400):
    """Peak after n identical doses every tau hours (approaches the steady-state formula)."""
    segs = [(i * tau, i * tau + hours_inf, dose_mg) for i in range(n_doses)]
    t = (n_doses - 1) * tau + hours_inf
    return amount(segs, t, ke) / vol


def two_level_ke(dose_mg, hours_inf, tau, ke, vol, t_peak_after_end, t_trough_before_next, n_doses=400):
    """Fit ke from a simulated steady-state peak and trough in one interval."""
    segs = [(i * tau, i * tau + hours_inf, dose_mg) for i in range(n_doses)]
    last = (n_doses - 1) * tau
    t1, t2 = last + hours_inf + t_peak_after_end, last + tau - t_trough_before_next
    c1, c2 = amount(segs, t1, ke) / vol, amount(segs, t2, ke) / vol
    segs = segs + [(last + tau, last + tau + hours_inf, dose_mg)]
    return solve_ke(segs, t1, c1, t2, c2)


def auc_steady_interval(dose_mg, hours_inf, tau, ke, vol, n_doses=400):
    """AUC over one dosing interval at steady state; equals dose / (ke V)."""
    segs = [(i * tau, i * tau + hours_inf, dose_mg) for i in range(n_doses)]
    a, b = (n_doses - 1) * tau, n_doses * tau
    return (area(segs, b, ke) - area(segs, a, ke)) / vol
