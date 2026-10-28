#!/usr/bin/env python3
"""Dev-only calibration for stormwater-inspection-audit (never uploaded): the oracle passes, and each common
misreading of the 2022 Construction General Permit, written as a small source edit of the reference solution, fails
at least one test. Runs without Docker or a writable /app (uses templates/local_check.py)."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "skills" / "insight-task-builder" / "templates"))
from local_check import run_solution, run_tests  # noqa: E402

TASK = HERE.parents[1] / "tasks" / "stormwater-inspection-audit"
SRC = (TASK / "solution" / "solve.py").read_text()

WEEKDAYS = ("sorted(date(2026, 1, 1) + timedelta(days=k) for k in range(273) "
            "if (date(2026, 1, 1) + timedelta(days=k)).weekday() < 5)")
ALLDAYS = "sorted(date(2026, 1, 1) + timedelta(days=k) for k in range(273))"
LATE_FROM_DUE = '''                    if open_due and t > due:
                        emit(aid, "routine_inspection", due, t)
                        d_anchor = due.date()
                    else:
                        d_anchor = d
                    latest = d
                    if mode == "regular":
                        due = end_of(d_anchor + interval)'''
SHORTCUTS = {
    # ---- business days (Appendix A)
    "business days are Monday to Friday": [("business = sorted(set().union(*worked.values()))", f"business = {WEEKDAYS}")],
    "every calendar day is a business day": [("business = sorted(set().union(*worked.values()))", f"business = {ALLDAYS}")],
    # ---- storm inspections (4.2.2, 4.3.1, footnotes 67-69)
    "an inspection after every day with 0.25 inches": [("            storm_days.append(heavy[0])\n            if heavy[-1] != heavy[0]:\n                storm_days.append(heavy[-1])",
                                                      "            storm_days.extend(heavy)")],
    "only the first heavy day of a storm": [("            if heavy[-1] != heavy[0]:\n                storm_days.append(heavy[-1])", "")],
    "threshold read as more than 0.25": [("heavy = [x for x in run if rain[x] >= 25]", "heavy = [x for x in run if rain[x] > 25]")],
    "storm deadline always 24 hours": [("deadline_day = business_day_from(day + ONE)", "deadline_day = day + ONE")],
    "storm deadline always next business day after the rain day + 1": [("deadline_day = business_day_from(day + ONE)", "deadline_day = business_day_after(day + ONE)")],
    "storm inspections on 4.2.1 sites too": [("        if weekly_only and not is_sensitive(area):\n            continue\n", "")],
    "4.3.1 ignored for 4.2.1 sites": [("        if weekly_only and not is_sensitive(area):\n            continue\n", "        if weekly_only:\n            continue\n")],
    "storm inspections for stabilized areas": [("if day < start or day not in regular_on[aid]:", "if day < start:")],
    "same-day inspection meets the storm": [("met = next((t for t in seen_by[aid] if t.date() > day), None)", "met = next((t for t in seen_by[aid] if t.date() >= day), None)")],
    # ---- routine inspections (4.2, 4.3.1, 4.4.1)
    "clock restarts from the missed due date": [('''                    if open_due and t > due:
                        emit(aid, "routine_inspection", due, t)
                    latest = d
                    if mode == "regular":
                        due = end_of(d + interval)''', LATE_FROM_DUE)],
    "seven days for every area": [("interval = timedelta(days=7 if weekly_only or is_sensitive(area) else 14)", "interval = timedelta(days=7)")],
    "fourteen days for sensitive areas on 4.2.2": [("interval = timedelta(days=7 if weekly_only or is_sensitive(area) else 14)", "interval = timedelta(days=7 if weekly_only else 14)")],
    "no reduced frequency for stabilized areas": [('                if d in completions[aid]:\n                    new, stab_day = "first", d', "")],
    "reduced frequency continues after work resumes": [('                if d in worked[aid] and stab_day is not None and d > stab_day:\n                    new, stab_day = "regular", None', "")],
    "a month read as 30 days": [("due = end_of(plus_month(base))", "due = end_of(base + timedelta(days=30))"),
                                ("due = end_of(plus_month(d))", "due = end_of(d + timedelta(days=30))")],
    "schedule change keeps the old deadline": [("                if new != mode:                                  # schedule change: count from the later day\n                    mode = new",
                                                "                if new != mode:\n                    mode = new\n                    continue_due = due"),
                                               ("                    open_due = True\n                if mode == \"regular\":",
                                                "                    open_due = True\n                    due = continue_due if 'continue_due' in dir() else due\n                if mode == \"regular\":")],
    "a day of grace on routine inspections": [("if open_due and t > due:", "if open_due and t > due + ONE:")],
    # ---- reports (4.7.1)
    "report due by the end of the next day": [('emit(i["areas_inspected"][0], "inspection_report", ts(i["completed"]) + timedelta(hours=24),',
                                               'emit(i["areas_inspected"][0], "inspection_report", end_of(ts(i["completed"]).date() + ONE),')],
    # ---- maintenance and corrective actions (2.1.4, 5.1, 5.2.1, 5.4.1)
    "escalation on the third repeat": [("] >= 4      # 2.1.4c", "] >= 3      # 2.1.4c")],
    "repeats never escalate": [("] >= 4      # 2.1.4c", "] >= 99      # 2.1.4c")],
    "repeats counted per control": [('times_fixed[(f["control_id"], f["location"], f["fix"])]', 'times_fixed[f["control_id"]]')],
    "repeats counted per control and location": [('times_fixed[(f["control_id"], f["location"], f["fix"])]', 'times_fixed[(f["control_id"], f["location"])]')],
    "escalated repeats keep the 7-day allowance": [('                emit(aid, "corrective_action", end_of(nbd), done)                        # 5.2.1b',
                                                    '                emit(aid, "corrective_action", found + timedelta(days=7) if f["infeasibility_documented"] else end_of(nbd), done)')],
    "infeasibility documentation ignored": [('                if f["infeasibility_documented"]:', "                if False:")],
    "corrective actions always 7 days": [('                emit(aid, "corrective_action", end_of(nbd), done)                        # 5.2.1b',
                                          '                emit(aid, "corrective_action", found + timedelta(days=7), done)')],
    "7 days counted to the end of the day": [('emit(aid, "corrective_action", found + timedelta(days=7), done)              # 5.2.1c',
                                              'emit(aid, "corrective_action", end_of(found.date() + timedelta(days=7)), done)')],
    "no completion log entry required": [('            emit(aid, "ca_log_completed", done + timedelta(hours=24), ts(f["log_entry_completed"]))\n', "")],
    "SWPPP update for every corrective action": [('if f["swppp_change_needed"]:', "if True:")],
    # ---- track-out (2.2.4)
    "track-out always by the next business day": [("day = business_day_from(happened.date())", "day = business_day_after(happened.date())")],
    "track-out by the end of the day it happened": [("day = business_day_from(happened.date())", "day = happened.date()")],
    # ---- stabilization (2.2.14, footnotes 38-41)
    "more than 14 idle days": [("elif (nxt - last).days - 1 < 14:", "elif (nxt - last).days - 1 < 15:")],
    "idle days counted inclusive": [("elif (nxt - last).days - 1 < 14:", "elif (nxt - last).days < 14:")],
    "initiation due the next calendar day": [("            nbd = business_day_after(last)\n            if nbd is None:\n                continue\n            starts",
                                              "            nbd = last + ONE\n            starts")],
    "completion always 14 days": [("days_allowed = 7 if is_sensitive(area) or over_five else 14", "days_allowed = 14")],
    "completion always 7 days": [("days_allowed = 7 if is_sensitive(area) or over_five else 14", "days_allowed = 7")],
    "five acres or more": [("over_five = max(disturbed.values(), default=0) > 500", "over_five = max(disturbed.values(), default=0) >= 500")],
    "five-acre test at the time of stabilization": [("days_allowed = 7 if is_sensitive(area) or over_five else 14",
                                                     "days_allowed = 7 if is_sensitive(area) or max([v for k, v in disturbed.items() if k <= ts(first['initiated']).date()], default=0) > 500 else 14")],
    "completion day not counted as disturbed": [("            if exposed:\n                disturbed[d] += acres\n            if d in completions[aid]:\n                exposed = False",
                                                 "            if d in completions[aid]:\n                exposed = False\n            if exposed:\n                disturbed[d] += acres")],
    "sensitive waters ignored for stabilization": [("days_allowed = 7 if is_sensitive(area) or over_five else 14", "days_allowed = 7 if over_five else 14")],
    "nutrient impairments not sensitive": [('SENSITIVE_IMPAIRMENTS = {"sedimentation/siltation", "total phosphorus", "total nitrogen"}',
                                           'SENSITIVE_IMPAIRMENTS = {"sedimentation/siltation"}')],
    "any impairment makes a water sensitive": [('return bool({p.lower() for p in w["impaired_for"]} & SENSITIVE_IMPAIRMENTS) or \\',
                                               'return bool(w["impaired_for"]) or \\')],
    "Tier 2.5 not sensitive": [('SENSITIVE_TIERS = {"2", "2.5", "3"}', 'SENSITIVE_TIERS = {"2", "3"}')],
    "permanent stops ignored": [('                if area["work_completed_on"] != last.isoformat():\n                    continue',
                                 "                continue")],
    "last logged day treated as a permanent stop": [('                if area["work_completed_on"] != last.isoformat():\n                    continue',
                                                     "                pass")],
    "completion counted from the initiation deadline": [('emit(aid, "stabilization_completion", ts(first["initiated"]) + timedelta(days=days_allowed),',
                                                         'emit(aid, "stabilization_completion", end_of(nbd) + timedelta(days=days_allowed),')],
}


def main():
    out = run_solution(TASK)
    _, failed = run_tests(TASK, out)
    print("oracle:", "OK" if not failed else failed)
    all_fail = True
    for name, edits in SHORTCUTS.items():
        src = SRC
        for old, new in edits:
            assert old in src, f"{name}: text not found in solve.py: {old!r}"
            src = src.replace(old, new)
        try:
            out = run_solution(TASK, src)
            _, failed = run_tests(TASK, out)
        except Exception as e:                          # a crash also counts as failing
            failed = [f"crash: {e}"]
        families = sorted({f.split("[")[-1].rstrip("]") for f in failed if "rule_family" in f})
        all_fail &= bool(failed)
        print(f"{'ok ' if failed else '!! PASSES'} {name:58s} {len(failed):2d} {families}")
    print("ALL SHORTCUTS FAIL" if all_fail else "SOME SHORTCUT PASSES: add a hand-worked case that separates it")


if __name__ == "__main__":
    main()
