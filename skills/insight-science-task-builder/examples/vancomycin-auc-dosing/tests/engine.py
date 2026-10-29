"""Independent verifier model for vancomycin-auc-dosing.

Written separately from the reference solution: the amount in the body is carried through a sorted event list
(infusion rate and dialyzer clearance changes) with an explicit state machine; the patient's clearance and volume
are found by nested Illinois regula falsi (outer on volume, inner on the elimination rate from the level ratio);
AUCs are integrated numerically with 24-point Gauss-Legendre quadrature between consecutive event times (the
curve is smooth between them). The closed-form single-compartment functions below the records section serve the
textbook checks in golden.json.

Guideline: Rybak et al., Am J Health-Syst Pharm 2020;77:835-864: AUC/MIC 400 to 600 with the MIC assumed to be
1 mg/L (Recommendation 6), postdistributional sampling at least 1 hour after the end of the infusion, removal by
high-permeability dialyzers (p. 846), AUC from the sampling period and proportional dose changes (p. 840).

"""
import csv
import datetime as dt
import json
import math
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
REF = dt.datetime(2026, 1, 1)


UMOL_TO_MG = 1449.3 / 1000.0          # mg/L per umol/L


def _dst_window(year):
    """Local wall-clock bounds of US daylight time: second Sunday of March 02:00 to first Sunday of November 02:00."""
    sundays = lambda m: [d for d in range(1, 15) if dt.date(year, m, d).weekday() == 6]
    return (dt.datetime(year, 3, sundays(3)[1], 2, 0), dt.datetime(year, 11, sundays(11)[0], 2, 0))


def hours(text):
    """Hours since REF in UTC for a New York local timestamp."""
    wall = dt.datetime.strptime(text, "%Y-%m-%d %H:%M")
    on, off = _dst_window(wall.year)
    if on <= wall < on + dt.timedelta(hours=1) or off - dt.timedelta(hours=1) <= wall < off:
        raise ValueError(f"{text} is skipped or repeated in New York")
    utc = wall + dt.timedelta(hours=4 if on <= wall < off else 5)
    return (utc - REF).total_seconds() / 3600.0


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


# ---- with hemodialysis: event-by-event state, the dialyzer adds its clearance while a session runs ---------
def _events(segs, hd):
    ev = []
    for s, e, mg in segs:
        ev += [(s, "rate", mg / (e - s)), (e, "rate", -mg / (e - s))]
    for s, e, c in hd:
        ev += [(s, "dial", c), (e, "dial", -c)]
    return sorted(ev)


def state_amount(segs, hd, t, cl, vol, _ev=None):
    """Amount in the body at t: walk the events, holding rate and dialyzer clearance constant between them."""
    ev = _ev if _ev is not None else _events(segs, hd)
    clock, amt, rate, dial = None, 0.0, 0.0, 0.0
    for when, kind, delta in ev:
        if when >= t:
            break
        if clock is not None and when > clock:
            k = (cl + dial) / vol
            x = math.exp(-k * (when - clock))
            amt = amt * x + rate / k * (1.0 - x)
        clock = when if clock is None or when > clock else clock
        if kind == "rate":
            rate += delta
        else:
            dial += delta
    if clock is None:
        return 0.0
    k = (cl + dial) / vol
    x = math.exp(-k * (t - clock))
    return amt * x + rate / k * (1.0 - x)


def conc_area(segs, hd, t_from, t_to, cl, vol):
    """Integral of the concentration over [t_from, t_to] by Gauss-Legendre between event times."""
    ev = _events(segs, hd)
    lo = max(t_from, 0.0)
    cuts = sorted({lo, t_to} | {w for w, _, _ in ev if lo < w < t_to})
    tot = 0.0
    for a, b in zip(cuts, cuts[1:]):
        half, mid = (b - a) / 2, (a + b) / 2
        tot += half * sum(w * state_amount(segs, hd, mid + half * x, cl, vol, ev) for x, w in zip(*GL))
    return tot / vol


def _illinois(f, a, b, tol=1e-15):
    fa, fb = f(a), f(b)
    side = 0
    c = a
    for _ in range(300):
        c = (a * fb - b * fa) / (fb - fa)
        fc = f(c)
        if fc == 0 or abs(b - a) < tol * max(abs(b), 1e-300):
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


def solve_cl_vol(segs, hd, t1, c1, t2, c2):
    """Nested Illinois: for each volume, the elimination rate from the level ratio; then the volume from level 1."""
    ev = _events(segs, hd)
    target = math.log(c1 / c2)

    def ke_at(vol, strict=False):
        f = lambda lk: math.log(state_amount(segs, hd, t1, math.exp(lk) * vol, vol, ev) /
                                state_amount(segs, hd, t2, math.exp(lk) * vol, vol, ev)) - target
        pts = [math.log(1e-4) + i * math.log(3e4) / 60 for i in range(61)]
        vals = [f(x) for x in pts]
        hits = [i for i in range(60) if (vals[i] > 0) != (vals[i + 1] > 0)]
        if len(hits) != 1:
            if strict:
                raise ValueError("elimination rate not unique at the fitted volume")
            return None                                   # not one elimination rate at this trial volume
        return math.exp(_illinois(f, pts[hits[0]], pts[hits[0] + 1]))

    def g(lv):
        vol = math.exp(lv)
        ke = ke_at(vol)
        if ke is None:
            return None
        return state_amount(segs, hd, t1, ke * vol, vol, ev) / vol - c1
    pts = [math.log(5.0) + i * math.log(300.0) / 40 for i in range(41)]
    vals = [g(x) for x in pts]
    hits = [i for i in range(40) if vals[i] is not None and vals[i + 1] is not None
            and (vals[i] > 0) != (vals[i + 1] > 0)]
    if len(hits) != 1:
        raise ValueError("volume not unique")
    vol = math.exp(_illinois(g, pts[hits[0]], pts[hits[0] + 1]))
    ke = ke_at(vol, strict=True)
    return ke * vol, vol


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


def load_dialysis(data=None):
    with open(Path(data or DATA) / "hemodialysis.csv", newline="") as fh:
        return list(csv.DictReader(fh))


def evaluate(p, adm, lev, ords, dial=()):
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
    hd = []
    for r in dial:
        c = float(r["vancomycin_clearance_ml_min"]) * 60.0 / 1000.0          # mL/min -> L/h
        if not math.isfinite(c):
            raise ValueError("non-finite dialyzer clearance")
        hd.append((hours(r["start"]) - t0, hours(r["stop"]) - t0, c))
    during_dialysis = 0

    usable, mistimed, unreadable, near_hour = [], 0, 0, False
    latest = {}
    for r in lev:
        if r["status"] == "corrected" or r["accession"] not in latest:
            latest[r["accession"]] = r
    corrected = sum(r["status"] == "corrected" for r in latest.values())
    in_umol = False
    for r in latest.values():
        v = parse_result(r["result"])
        if v is not None and r["units"] == "umol/L":
            v *= UMOL_TO_MG
            in_umol = True
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
        if any(a <= t <= b for a, b, _ in hd):
            during_dialysis += 1
            continue
        if any(1.0 < x <= 1.1 for x in after):
            near_hour = True
        usable.append((t, v))
    usable.sort()
    if len(usable) != 2:
        raise ValueError(f"{p['patient_id']}: {len(usable)} usable levels")
    (t1, c1), (t2, c2) = usable
    clearance, vol = solve_cl_vol(segs, hd, t1, c1, t2, c2)
    ke = clearance / vol

    maint = [o for o in ords if o["frequency"] != "once"]
    cur = max(maint, key=lambda o: hours(o["ordered"]))
    dose = float(cur["dose_mg"])
    auc24 = conc_area(segs, hd, t2 - 24.0, t2, clearance, vol)      # guideline p. 840: sampling-period AUC
    auc48 = conc_area(segs, hd, 0.0, 48.0, clearance, vol)
    mic_info = p["isolate_mic"]
    mic = 1.0                                  # Recommendation 6: measured MICs do not change the target
    ratio = auc24 / mic
    if ratio < 400:
        exposure = "below"
    elif ratio > 600:
        exposure = "above"
    else:
        exposure = "within"
    raw = dose * 500 * mic / auc24                                   # proportional dose change (p. 840)
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
    if corrected:
        tags.add("corrected_results")
    if hd:
        tags.add("hemodialysis_patients")
        if any(s < b and e > a for s, e, _ in segs for a, b, _ in hd):
            tags.add("doses_given_during_dialysis")
    if during_dialysis:
        tags.add("levels_drawn_during_dialysis")
    if in_umol:
        tags.add("results_in_umol_per_l")
    first = min(sp[0] for sp in spans) + t0
    w_on, w_off = _dst_window(2026)
    on = (w_on + dt.timedelta(hours=5) - REF).total_seconds() / 3600.0      # 02:00 EST
    off = (w_off + dt.timedelta(hours=4) - REF).total_seconds() / 3600.0    # 02:00 EDT
    if any(first < c <= t2 + t0 for c in (on, off)):
        tags.add("course_crosses_clock_change")
    tags.add(f"exposure_{exposure}")
    if not all(math.isfinite(x) for x in (ke, vol, auc48, auc24, ratio, raw)):
        raise ValueError(f"{p['patient_id']}: non-finite result")
    return dict(ke=ke, volume=vol, auc48=auc48, auc24=auc24, exposure=exposure, new_dose=new, tags=tags)


def expected(data=None):
    pats, adm, lev, ords = load(data)
    group = lambda rows: {k: [r for r in rows if r["patient_id"] == k] for k in {r["patient_id"] for r in rows}}
    A, L, O, D = group(adm), group(lev), group(ords), group(load_dialysis(data))
    out = {}
    for p in pats:
        pid = p["patient_id"]
        out[pid] = evaluate(p, A.get(pid, []), L.get(pid, []), O.get(pid, []), D.get(pid, []))
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


def dialysis_example_conc():
    """Concentration at 10 h for the hand-worked dialysis case in golden.json."""
    return state_amount([(0.0, 1.0, 1000.0)], [(3.0, 7.0, 7.2)], 10.0, 0.5, 50.0) / 50.0


def total_auc_no_dialysis():
    return conc_area([(0.0, 1.0, 1000.0)], [], 0.0, 2000.0, 0.5, 50.0)
