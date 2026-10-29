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

FIT = "        ke, vol = fit(segs, ta, ca, tb, cb)\n"
SHORTCUTS = {
    "local times read as naive clock times (daylight saving ignored)": [
        ("    offset_h = 4 if start <= wall < end else 5", "    offset_h = 5")],
    "daylight saving applied from midnight instead of 02:00": [
        ('    start = dt.datetime.combine(nth_sunday(wall.year, 3, 2), dt.time(2, 0))\n    end = dt.datetime.combine(nth_sunday(wall.year, 11, 1), dt.time(1, 0))',
         '    start = dt.datetime.combine(nth_sunday(wall.year, 3, 2), dt.time(0, 0))\n    end = dt.datetime.combine(nth_sunday(wall.year, 11, 1), dt.time(0, 0))')],
    "umol/L results read as mg/L": [('(MG_PER_UMOL if r["units"] == "umol/L" else 1.0)', '1.0')],
    "umol/L converted with the hydrochloride salt mass (1485.7 g/mol)": [("MG_PER_UMOL = 1.4493 ", "MG_PER_UMOL = 1.4857 ")],
    "original result kept instead of its correction": [
        ('if r["accession"] not in reports or r["status"] == "corrected":', 'if r["accession"] not in reports:')],
    "two-level steady-state equation for ke (ln of the level ratio over the time between them)": [
        (FIT, "        ke = abs(math.log(ca / cb)) / (tb - ta)\n        vol = total(segs, ta, ke) / ca\n")],
    "steady-state equations for ke and V (Sawchuk-Zaske, last dose only)": [
        (FIT, "        ke = abs(math.log(ca / cb)) / (tb - ta)\n"
              "        last = [sg for sg in segs if sg[0] < ta][-1:]\n"
              "        vol = total(last, ta, ke) / ca / 1.0\n")],
    "full ordered dose for every infusion (volumes infused ignored)": [
        ("segs.append((open_t, t, (vol - done_v) * conc))", "segs.append((open_t, t, (vol - done_v) * conc * float(start[0]['bag_volume_ml']) / max(float(rows[-1]['volume_infused_ml']), 1)))")],
    "pauses ignored (one segment from start to stop)": [
        ("                if ev in (\"start\", \"resume\"):\n                    open_t = t",
         "                if ev == \"start\":\n                    open_t = t\n                elif ev == \"resume\":\n                    pass")],
    "infusion assumed to last the nominal hour per 1,000 mg": [
        ("            spans.append((minutes(rows[0][\"time\"]), minutes(rows[-1][\"time\"])))",
         "            _d = float(start[0]['dose_mg']); _s = minutes(rows[0]['time']) / 60.0\n"
         "            segs = [sg for sg in segs if sg[0] < _s - 1e-9] + [(_s, _s + max(1.0, round(_d / 1000 * 2) / 2), _d)]\n"
         "            spans.append((minutes(rows[0][\"time\"]), minutes(rows[-1][\"time\"])))")],
    "held doses counted as given": [
        ("            if not start:\n                continue                                       # not given",
         "            if not start:\n                _t = minutes(rows[0]['time']) / 60.0\n                segs.append((_t, _t + 1.0, float(rows[0]['dose_mg'])))\n                continue")],
    "levels within 1 hour after an infusion kept (last two numeric levels used)": [
        ("            if any(s <= t <= e or e < t < e + 60 for s, e in spans):", "            if any(s <= t <= e for s, e in spans):"),
        ("        (ta, ca), (tb, cb) = good", "        (ta, ca), (tb, cb) = good[-2:]")],
    "1-hour rule counted from the start of the infusion": [
        ("e < t < e + 60 for s, e in spans", "s < t < s + 60 for s, e in spans"),
        ("        (ta, ca), (tb, cb) = good", "        (ta, ca), (tb, cb) = good[-2:]")],
    "flagged results (H) treated as unusable": [(r'(?:[HL])?\s*", r["result"])', r'", r["result"])')],
    "measured broth microdilution MIC used instead of 1 mg/L": [
        ("        mic = 1.0 ", "        _m = p.get('isolate_mic'); mic = float(_m['value_mg_l']) if _m and _m['method'] == 'broth microdilution' else 1.0 ")],
    "measured MIC from any method used": [
        ("        mic = 1.0 ", "        _m = p.get('isolate_mic'); mic = float(_m['value_mg_l']) if _m else 1.0 ")],
    "first maintenance order instead of the current one": [("key=lambda o: minutes(o[\"ordered\"]))", "key=lambda o: -minutes(o[\"ordered\"]))")],
    "new dose rounded down to 250 mg": [("math.floor(raw / 250.0 + 0.5)", "math.floor(raw / 250.0)")],
    "new dose rounded up to 250 mg": [("math.floor(raw / 250.0 + 0.5)", "math.ceil(raw / 250.0)")],
    "new dose also when exposure is within range": [('exposure, new = "within", int(dose)', 'exposure, new = "within", int(math.floor(500.0 * mic * cl * tau / 24.0 / 250.0 + 0.5) * 250)')],
    "48-hour AUC taken as twice the steady-state AUC24": [("auc48 = sum(segment_area(sg, 48.0, ke) for sg in segs) / vol", "auc48 = 2 * auc24")],
    "48-hour AUC by the linear trapezoid rule on hourly concentrations": [
        ("auc48 = sum(segment_area(sg, 48.0, ke) for sg in segs) / vol",
         "auc48 = sum((total(segs, h, ke) + total(segs, h + 1, ke)) / 2 for h in range(48)) / vol")],
    "48-hour AUC from the first maintenance dose": [
        ("auc48 = sum(segment_area(sg, 48.0, ke) for sg in segs) / vol",
         "_m = sorted(s for s, _, _ in segs)\n        _o = [s for s in _m if s > 0][0] if any(o['frequency'] == 'once' for o in orders[pid]) else 0.0\n"
         "        auc48 = sum(segment_area(sg, 48.0 + _o, ke) - segment_area(sg, _o, ke) for sg in segs) / vol")],
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
                                   (("ke_per_h", "ke"), ("volume_l", "volume"), ("auc48", "auc48"), ("auc24_ss", "auc24"))) \
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
