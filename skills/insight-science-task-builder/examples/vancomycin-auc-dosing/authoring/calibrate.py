#!/usr/bin/env python3
"""Run shortcut versions of the reference solution against the tests.

Usage: python3 calibrate.py      (from authoring/)

Each shortcut is a plausible misreading of the guideline, the records or the instruction, made by editing
solution/solve.py text. A shortcut is caught when at least one test fails; the number of wrong patients shows how
widely it shows up.
"""
import sys
sys.dont_write_bytecode = True       # never leave __pycache__ in the submitted task folder
import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TASK = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(TASK / "tests"))
from local_check import run_solution, run_tests  # noqa: E402
import engine  # noqa: E402

FIT = "        cl, vol = fit(line, ta, ca, tb, cb)\n"
SESS = "        sessions = [(s / 60.0 - t0, e / 60.0 - t0, c * ML_MIN_TO_L_H) for s, e, c in sessions_min]\n"
AUC24 = "        auc24 = line.area(tb - 24.0, tb, cl, vol)              # the 24 hours before the later usable level\n"
SHORTCUTS = {
    # dialysis
    "dialysis sessions ignored": [(SESS, SESS + "        sessions = []\n")],
    "dialyzer clearance read as L/h (mL/min not converted)": [("ML_MIN_TO_L_H = 0.06", "ML_MIN_TO_L_H = 1.0")],
    "dialyzer clearance converted with 60/100 instead of 60/1000": [("ML_MIN_TO_L_H = 0.06", "ML_MIN_TO_L_H = 0.6")],
    "dialysis removal spread evenly over the whole course": [
        (SESS, SESS + "        _tot = sum(c * (e - s) for s, e, c in sessions); _span = max([e for _, e, _ in sessions] + [1.0])\n"
                      "        sessions = [(0.0, 1e6, _tot / _span)] if sessions else []\n")],
    "levels drawn during dialysis kept": [
        ("            if any(s <= t <= e for s, e, _ in sessions_min):\n                continue                                       # during a dialysis session\n", "")],
    "superposition at one rate fitted from the level ratio (dialysis ignored in the fit)": [
        (FIT, "        _l0 = Timeline(segs, [])\n        cl, vol = fit(_l0, ta, ca, tb, cb)\n")],
    # sampling-period AUC and dose
    "auc24 as daily dose over clearance (steady state)": [
        (AUC24, "        _f = cur['frequency']; _tau = float(re.search(r'\\d+', _f).group()) if 'every' in _f else 48.0\n"
                "        auc24 = dose * 24.0 / _tau / cl\n")],
    "auc24 over the 24 hours after the earlier level": [(AUC24, "        auc24 = line.area(ta, ta + 24.0, cl, vol)\n")],
    "auc24 between the two levels scaled to 24 hours": [(AUC24, "        auc24 = line.area(ta, tb, cl, vol) * 24.0 / (tb - ta)\n")],
    "new dose from clearance at an AUC of 500 (steady-state formula)": [
        ("            raw = dose * 500.0 / auc24                         # dose changes give proportional AUC changes",
         "            _f = cur['frequency']; _tau = float(re.search(r'\\d+', _f).group()) if 'every' in _f else 48.0\n"
         "            raw = 500.0 * cl * _tau / 24.0")],
    # records
    "local times read as naive clock times (daylight saving ignored)": [
        ("    offset_h = 4 if start <= wall < end else 5", "    offset_h = 5")],
    "daylight saving applied from midnight instead of 02:00": [
        ('    start = dt.datetime.combine(nth_sunday(wall.year, 3, 2), dt.time(2, 0))\n    end = dt.datetime.combine(nth_sunday(wall.year, 11, 1), dt.time(1, 0))',
         '    start = dt.datetime.combine(nth_sunday(wall.year, 3, 2), dt.time(0, 0))\n    end = dt.datetime.combine(nth_sunday(wall.year, 11, 1), dt.time(0, 0))')],
    "umol/L results read as mg/L": [('(MG_PER_UMOL if r["units"] == "umol/L" else 1.0)', '1.0')],
    "umol/L converted with the hydrochloride salt mass (1485.7 g/mol)": [("MG_PER_UMOL = 1.4493 ", "MG_PER_UMOL = 1.4857 ")],
    "original result kept instead of its correction": [
        ('if r["accession"] not in reports or r["status"] == "corrected":', 'if r["accession"] not in reports:')],
    "full ordered dose for every infusion (volumes infused ignored)": [
        ("segs.append((open_t, t, (vol - done_v) * conc))", "segs.append((open_t, t, (vol - done_v) * conc * float(start[0]['bag_volume_ml']) / max(float(rows[-1]['volume_infused_ml']), 1)))")],
    "pauses ignored (one segment from start to stop)": [
        ("                if ev in (\"start\", \"resume\"):\n                    open_t = t",
         "                if ev == \"start\":\n                    open_t = t\n                elif ev == \"resume\":\n                    pass")],
    "held doses counted as given": [
        ("            if not start:\n                continue                                       # not given",
         "            if not start:\n                _t = minutes(rows[0]['time']) / 60.0\n                segs.append((_t, _t + 1.0, float(rows[0]['dose_mg'])))\n                continue")],
    "levels within 1 hour after an infusion kept": [
        ("            if any(s <= t <= e or e < t < e + 60 for s, e in spans):", "            if any(s <= t <= e for s, e in spans):")],
    "1-hour rule counted from the start of the infusion": [("e < t < e + 60 for s, e in spans", "s < t < s + 60 for s, e in spans")],
    "measured MIC from any method used": [
        ("        if 400.0 <= auc24 <= 600.0:", "        _m = p.get('isolate_mic'); _mic = float(_m['value_mg_l']) if _m else 1.0\n        auc24 = auc24 / _mic\n        if 400.0 <= auc24 <= 600.0:")],
    "first maintenance order instead of the current one": [("key=lambda o: minutes(o[\"ordered\"]))", "key=lambda o: -minutes(o[\"ordered\"]))")],
    "new dose rounded down to 250 mg": [("math.floor(raw / 250.0 + 0.5)", "math.floor(raw / 250.0)")],
    "new dose rounded up to 250 mg": [("math.floor(raw / 250.0 + 0.5)", "math.ceil(raw / 250.0)")],
    "new dose also when exposure is within range": [('exposure, new = "within", int(dose)', 'exposure, new = "within", int(math.floor(dose * 500.0 / auc24 / 250.0 + 0.5) * 250)')],
    "48-hour AUC by the linear trapezoid rule on hourly concentrations": [
        ("        auc48 = line.area(0.0, 48.0, cl, vol)", "        auc48 = sum((line.amount(h, cl, vol) + line.amount(h + 1, cl, vol)) / 2 for h in range(48)) / vol")],
    "amounts from pump rate times running time": [
        ("segs.append((open_t, t, (vol - done_v) * conc))", "segs.append((open_t, t, _rate * (t - open_t) * conc))"),
        ("                if ev in (\"start\", \"resume\"):\n                    open_t = t",
         "                if r['rate_ml_h']:\n                    _rate = float(r['rate_ml_h'])\n                if ev in (\"start\", \"resume\"):\n                    open_t = t")],
}


def count_wrong(out_dir):
    truth = engine.expected(TASK / "tests" / "data")
    with open(out_dir / "vancomycin_review.csv", newline="") as fh:
        got = {r["patient_id"]: r for r in csv.DictReader(fh)}
    wrong = 0
    for pid, w in truth.items():
        g = got.get(pid)
        ok = g is not None and all(abs(float(g[k]) - w[x]) <= 0.005 * abs(w[x]) for k, x in
                                   (("ke_per_h", "ke"), ("volume_l", "volume"), ("auc48", "auc48"), ("auc24", "auc24"))) \
            and g["exposure"] == w["exposure"] and int(g["new_dose_mg"]) == w["new_dose"]
        wrong += not ok
    return wrong, len(truth)


def main():
    src = (TASK / "solution" / "solve.py").read_text()
    caught = 0
    for name, edits in SHORTCUTS.items():
        # a shortcut keeps going where the reference would stop: first root, or a typical value if none
        s = src.replace('        raise ValueError(f"{len(roots)} solutions for the elimination rate")',
                        '        roots = roots or [150]')
        for a, b in edits:
            assert s.count(a) >= 1, (name, a)
            s = s.replace(a, b)
        # if a shortcut leaves other than two usable levels, keep going with the first two found
        s = s.replace("        (ta, ca), (tb, cb) = good\n",
                      "        good = good[:2] if len(good) >= 2 else good + [(good[0][0] + 1.0, good[0][1] * 0.9)]\n"
                      "        (ta, ca), (tb, cb) = good\n")
        try:
            out = run_solution(TASK, source=s)
        except Exception as e:                      # noqa: BLE001
            print(f"CRASHED ({type(e).__name__}: {str(e)[:80]})  {name}")
            caught += 1
            continue
        passed, failed = run_tests(TASK, out)
        wrong, total = count_wrong(out)
        caught += bool(failed)
        print(f"{'CAUGHT' if failed else 'MISSED'}  {wrong:4d} of {total} patients wrong  {name}")
    print(f"{caught} of {len(SHORTCUTS)} shortcuts caught")
    sys.exit(0 if caught == len(SHORTCUTS) else 1)


if __name__ == "__main__":
    main()
