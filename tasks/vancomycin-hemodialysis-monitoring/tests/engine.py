"""Independent engine for the verifier: predialysis-concentration monitoring of vancomycin in hemodialysis under the
2020 guideline (Rybak et al., Am J Health-Syst Pharm 2020;77:835-864): Recommendations 13 and 14 (page 847), the
sampling advice (page 848) and the loading-dose maximum (page 845)."""
import csv
import datetime as dt
import math
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
MG_PER_UMOL = 1.4493
MG_PER_KG = {"after_dialysis": {"low": (25.0, 7.5), "high": (25.0, 10.0)},
             "intradialytic": {"low": (30.0, (7.5 + 10.0) / 2), "high": (35.0, (10.0 + 15.0) / 2)}}


def load():
    def rows(name):
        with open(DATA / name, newline="") as fh:
            return list(csv.DictReader(fh))
    return rows("sessions.csv"), rows("levels.csv")


def _edt(year):
    def sunday(month, nth):
        d = dt.date(year, month, 1)
        return dt.datetime.combine(d + dt.timedelta(days=(6 - d.weekday()) % 7 + 7 * (nth - 1)), dt.time(2))
    return sunday(3, 2), sunday(11, 1) - dt.timedelta(hours=1)


def to_utc(text):
    t = dt.datetime.strptime(text, "%Y-%m-%d %H:%M")
    a, b = _edt(t.year)
    return t + dt.timedelta(hours=4 if a <= t < b else 5)


def round250(x):
    q, r = divmod(x, 250.0)
    return int(250 * (q + (1 if r >= 125.0 else 0)))


def mg_per_l(rec):
    try:
        x = float(rec["result"])
    except ValueError:
        return None
    return x * MG_PER_UMOL if rec["units"] == "umol/L" else x


def evaluate(sessions, records):
    """{session_id: (level or None, status, dose)} for one patient."""
    final = {}
    for r in records:
        if r["status"] == "corrected" or r["accession"] not in final:
            final[r["accession"]] = r
    draws = sorted((to_utc(r["collected"]), mg_per_l(r)) for r in final.values() if mg_per_l(r) is not None)
    times = [(to_utc(s["start"]), to_utc(s["stop"])) for s in sessions]
    two_h = dt.timedelta(hours=2)
    out, have_level, previous = {}, False, None
    for k, s in enumerate(sessions):
        start = times[k][0]
        usable = [x for t, x in draws if start - two_h <= t < start
                  and not any(a <= t < b + two_h for a, b in times[:k])]
        level = usable[-1] if usable else None                     # draws are sorted, so the last is the latest
        status = "none" if level is None else "below" if level < 15 else "above" if level > 20 else "within"
        load_kg, maint_kg = MG_PER_KG[s["vancomycin_timing"]][s["dialyzer"]]
        weight = float(s["pre_weight_kg"])
        if k == 0:
            dose = round250(min(weight * load_kg, 3000.0))
        else:
            # weight-based until a predialysis level has been determined, then the previous dose
            base = round250(weight * maint_kg) if not have_level else previous
            dose = base if status in ("none", "within") else round250(base * 17.5 / level)
        have_level = have_level or level is not None
        previous = dose
        out[s["session_id"]] = (level, status, dose)
    return out


def expected():
    sessions, levels = load()
    by_s, by_l = {}, {}
    for s in sessions:
        by_s.setdefault(s["patient_id"], []).append(s)
    for r in levels:
        by_l.setdefault(r["patient_id"], []).append(r)
    out = {}
    for pid, ss in by_s.items():
        ss.sort(key=lambda s: to_utc(s["start"]))
        out.update(evaluate(ss, by_l.get(pid, [])))
    for lv, _, _ in out.values():
        assert lv is None or math.isfinite(lv)
    return out
