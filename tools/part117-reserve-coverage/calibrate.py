#!/usr/bin/env python3
"""Developer diagnostics: explain each pair, and check that every planted shortcut
changes at least one graded answer. Not shipped."""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "tasks" / "part117-reserve-coverage"
spec = importlib.util.spec_from_file_location("solve", ROOT / "solution" / "solve.py")
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)
S.DATA = ROOT / "environment" / "data"
H = 60


def explain(clock, p, t, *, accl_mode="true", reduce_in_cap=True, rest_at_report=True,
            fdp_kinds=("FDP",), clip=True, naive_local=False, table_a=True):
    """First failed rule for (p, t) or 'legal'. Keyword flags switch on known shortcuts."""
    if (p.base, p.seat, p.equipment) != (t["base"], t["seat"], t["equipment"]):
        return "compat"
    rep, rel = t["report"], t["release"]
    if not p.rap_start <= rep <= p.rap_end:
        return "rap_window"
    hist = [(a, b) for a, b, _ in p.duties]
    last = max((b for a, b in hist if b <= p.rap_start), default=None)
    if last is not None and p.rap_start - last < 10 * H:
        return "rest10"
    if S.longest_free(hist, p.rap_start - 168 * H, p.rap_start) < 30 * H:
        return "free30_rap"
    with_rap = hist + [(p.rap_start, rep)]
    if rest_at_report and S.longest_free(with_rap, rep - 168 * H, rep) < 30 * H:
        return "free30_report"
    if accl_mode == "true":
        acc, ref = S.acclimatization(clock, p, rep, with_rap)
    elif accl_mode == "local":
        acc, ref = True, t["base"]
    else:  # "recent_europe": anyone back from Europe < 72 h is unacclimated to Paris
        recent = [l for l in p.legs if l[2] in ("CDG", "FRA", "AMS") and l[3] == p.base and rep - l[1] < 72 * H]
        acc, ref = (False, recent[-1][2]) if recent else (True, t["base"])
    st = t["base"] if acc else ref
    mod = clock.minute_of_day(rep, st)
    if naive_local and not acc:
        mod = (mod + 60) % (24 * H)  # EST instead of EDT
    lim = S.table_b(mod, len(t["legs"])) - (0 if acc else 30)
    if rel - rep > lim:
        return "tableB"
    fl = sum(b - a for a, b in t["legs"])
    if table_a and fl > (9 if 5 * H <= mod < 20 * H else 8) * H:
        return "tableA"
    cap_lim = lim if reduce_in_cap else lim + (0 if acc else 30)
    if rel - p.rap_start > min(16 * H, cap_lim + 4 * H):
        return "rap_plus_fdp"
    fdps = [(a, b) for a, b, k in p.duties if k in fdp_kinds]
    lo = rel - 168 * H + (60 if naive_local else 0)
    ov = (lambda a, b, l, h: S.overlap(a, b, l, h)) if clip else (lambda a, b, l, h: (b - a) if b > l and a < h else 0)
    if sum(ov(a, b, lo, rel) for a, b in fdps) + rel - rep > 60 * H:
        return "fdp60"
    if sum(ov(a, b, rel - 672 * H, rel) for a, b in fdps) + rel - rep > 190 * H:
        return "fdp190"
    if sum(ov(a, b, rel - 672 * H, rel) for a, b, _, _ in p.legs) + fl > 100 * H:
        return "flight100"
    return "legal"


SHORTCUTS = {
    "local_departure_time": dict(accl_mode="local"),
    "recent_europe_heuristic": dict(accl_mode="recent_europe"),
    "unreduced_tableB_in_cap": dict(reduce_in_cap=False),
    "rest_check_only_at_rap": dict(rest_at_report=False),
    "other_duty_counted_as_fdp": dict(fdp_kinds=("FDP", "OTHER")),
    "whole_duty_in_window": dict(clip=False),
    "est_instead_of_edt": dict(naive_local=True),
    "no_table_a": dict(table_a=False),
}


def main():
    clock, pilots, trips = S.load()
    truth = {(p, t): S.legality(clock, pilots[p], trips[t]) for p in pilots for t in trips}
    for (p, t), v in truth.items():
        assert v == (explain(clock, pilots[p], trips[t]) == "legal"), (p, t)
    if "-v" in sys.argv:
        tids = sorted(trips)
        for pid in sorted(pilots):
            rel = [t for t in tids if trips[t]["base"] == pilots[pid].base and trips[t]["seat"] == pilots[pid].seat]
            print(pid, " ".join(f"{t}:{explain(clock, pilots[pid], trips[t])}" for t in rel))
    legal = {k for k, v in truth.items() if v}
    chosen = S.assign(pilots, trips, legal)
    best = len(chosen)
    print("legal pairs", len(legal), "coverage", best, "/", len(trips), "cost", sum(pilots[p].cost for p, _ in chosen))
    for name, kw in SHORTCUTS.items():
        diff = [k for k in truth if truth[k] != (explain(clock, pilots[k[0]], trips[k[1]], **kw) == "legal")]
        alt = {k for k in truth if explain(clock, pilots[k[0]], trips[k[1]], **kw) == "legal"}
        ch = S.assign(pilots, trips, alt)
        print(f"{name:28s} flips {len(diff):3d} pairs, coverage {len(ch)} cost {sum(pilots[p].cost for p, _ in ch)}  e.g. {diff[:4]}")
    # greedy: trips by report time, cheapest legal unused pilot
    used, cov = set(), 0
    for tid in sorted(trips, key=lambda t: (trips[t]["report"], t)):
        cands = sorted((pilots[p].cost, p) for p in pilots if (p, tid) in legal and p not in used)
        if cands:
            used.add(cands[0][1])
            cov += 1
    print("greedy cheapest-first coverage", cov)
    if "--write" in sys.argv:
        groups = {
            "time_zones_and_acclimatization": ["local_departure_time", "recent_europe_heuristic", "est_instead_of_edt"],
            "reserve_and_rest": ["unreduced_tableB_in_cap", "rest_check_only_at_rap"],
            "cumulative_limits": ["other_duty_counted_as_fdp", "whole_duty_in_window"],
            "flight_time_limit": ["no_table_a"],
        }
        out = {}
        for g, names in groups.items():
            pairs = set()
            for n in names:
                pairs |= {k for k in truth if truth[k] != (explain(clock, pilots[k[0]], trips[k[1]], **SHORTCUTS[n]) == "legal")}
            if g == "reserve_and_rest":
                pairs |= {k for k in truth if explain(clock, pilots[k[0]], trips[k[1]]) in ("rest10", "rap_plus_fdp")}
            out[g] = sorted(list(k) for k in pairs)
        (ROOT / "tests" / "trap_pairs.json").write_text(json.dumps(out, indent=1) + "\n")
        print({g: len(v) for g, v in out.items()})


if __name__ == "__main__" and "--submit" not in sys.argv:
    main()


def submit(name):
    """Write /app/output as a solver that uses shortcut `name` would ('greedy' = true
    legality but cheapest-first greedy assignment)."""
    import csv as _csv
    clock, pilots, trips = S.load()
    kw = SHORTCUTS.get(name, {})
    legal = {(p, t) for p in pilots for t in trips if explain(clock, pilots[p], trips[t], **kw) == "legal"}
    if name == "greedy":
        used, chosen = set(), []
        for tid in sorted(trips, key=lambda t: (trips[t]["report"], t)):
            c = sorted((pilots[p].cost, p) for p in pilots if (p, tid) in legal and p not in used)
            if c:
                used.add(c[0][1])
                chosen.append((c[0][1], tid))
    else:
        chosen = S.assign(pilots, trips, legal)
    S.OUT.mkdir(parents=True, exist_ok=True)
    with open(S.OUT / "legality.csv", "w", newline="") as f:
        w = _csv.writer(f)
        w.writerow(["pilot_id", "trip_id", "legal"])
        for p in sorted(pilots):
            for t in sorted(trips):
                w.writerow([p, t, "true" if (p, t) in legal else "false"])
    (S.OUT / "assignment.json").write_text(json.dumps({
        "assignments": [{"trip_id": t, "pilot_id": p} for p, t in chosen],
        "trips_covered": len(chosen),
        "total_callout_cost": sum(pilots[p].cost for p, _ in chosen)}))


if __name__ == "__main__" and "--submit" in sys.argv:
    submit(sys.argv[sys.argv.index("--submit") + 1])
