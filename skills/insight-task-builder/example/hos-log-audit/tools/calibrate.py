#!/usr/bin/env python3
"""Dev-only calibration for hos-log-audit (never uploaded): oracle passes, empty output fails, and each
common misreading of 49 CFR 395.1-395.3 fails at least one test. Each misreading is a small source edit of
the reference solution. Needs writable /app."""
import csv
import shutil
import subprocess
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TASK = ROOT / "tasks" / "hos-log-audit"
OUT = Path("/app/output/violations.csv")
SRC = (TASK / "solution" / "solve.py").read_text()

SHORTCUTS = {
    "rolling 168/192 hours instead of carrier days": [
        ('w0 = day_start(day_index(m) - (days - 1))', 'w0 = m - days * 1440')],
    "carrier days at midnight UTC": [('return (m + off - day0) // 1440', 'return m // 1440'),
                                     ('return idx * 1440 + day0 - off', 'return idx * 1440')],
    "carrier days at local midnight whatever the designated time": [
        ('return (m + off - day0) // 1440', 'return (m + off) // 1440'),
        ('return idx * 1440 + day0 - off', 'return idx * 1440 - off')],
    "70 hours in 8 days for every carrier": [('days = 8 if carrier["operates_every_day"] else 7', 'days = 8'),
                                             ('cap = (70 if carrier["operates_every_day"] else 60) * 60',
                                              'cap = 70 * 60')],
    "34-hour restart ignored": [('restarts = [r for r in rests if r[1] - r[0] >= 34 * 60]', 'restarts = []')],
    "restart needs more than 34 hours": [('if r[1] - r[0] >= 34 * 60]', 'if r[1] - r[0] > 34 * 60]')],
    "travel time always on duty": [('if off >= 600:\n                code = "O"', 'if False:\n                code = "O"')],
    "travel time always off duty": [('if off >= 600:\n                code = "O"', 'if True:\n                code = "O"')],
    "short-haul radius read as 150 statute miles": [('t["max_miles"] <= 172.6', 't["max_miles"] <= 150')],
    "short-haul exemption never applied": [('t["short_haul"] = (', 't["short_haul"] = False and (')],
    "short-haul without the 14-hour release": [('and t["end"] - t["start"] <= 14 * 60\n', '\n')],
    "short-haul without the release location": [('t["max_miles"] <= 172.6 and t["release_home"] and',
                                                 't["max_miles"] <= 172.6 and')],
    "adverse driving conditions ignored": [('t["adverse"] = any(', 't["adverse"] = False and any(')],
    "adverse extension even when known beforehand": [('any(not a["known_to_driver_or_carrier_beforehand"]',
                                                      'any(True or a["known_to_driver_or_carrier_beforehand"]')],
    "16-hour exception ignored": [('if ok:\n                t["sixteen"] = True', 'if False:\n                t["sixteen"] = True')],
    "16-hour exception taken on the claim alone": [('ok = len(prev5) == 5 and all(p["release_home"] for p in prev5)',
                                                    'ok = True'),
                                                   ('ok = ok and t["release_home"] and t["end"] - t["start"] <= 16 * 60',
                                                    'ok = ok'),
                                                   ('ok = False\n            if ok:', 'pass\n            if ok:')],
    "16-hour exception without the five-tour history": [
        ('ok = len(prev5) == 5 and all(p["release_home"] for p in prev5)', 'ok = True')],
    "16-hour exception without the 6-day limit": [('ok = False\n            if ok:', 'pass\n            if ok:')],
    "16-hour exception: a restart does not lift the 6-day limit": [
        ('and not any(u < r[0] < t["start"] for r in restarts)', '')],
    "16-hour exception: release within 16 h not checked": [
        ('ok = ok and t["release_home"] and t["end"] - t["start"] <= 16 * 60', 'ok = ok and t["release_home"]')],
    "sleeper-berth pairs ignored": [('pairs.append((c[1], prev[1], c[1] - c[0]))', 'pass')],
    "pair excludes both periods from the 14 hours": [
        ('pairs.append((c[1], prev[1], c[1] - c[0]))',
         'pairs.append((c[1], t["start"], (c[1] - c[0]) + (prev[1] - prev[0])))')],
    "pair accepted under 10 hours in total": [('and (prev[1] - prev[0]) + (c[1] - c[0]) >= 600', '')],
    "pair accepted without 7 hours in the berth": [('if long_sb >= 420 and', 'if long_sb >= 0 and')],
    "10-hour reset needs one status, not off duty plus sleeper": [
        ('resets = [r for r in rests if r[1] - r[0] >= 600]',
         'resets = [r for r in runs(status, t0, "O") + runs(status, t0, "S") if r[1] - r[0] >= 600]\n'
         '    resets.sort()')],
    "30-minute break only off duty counts": [('if c != "D":\n            nd += 1', 'if c in "OS":\n            nd += 1')],
    "30-minute break: violation only after 8 h 01": [("pre_drive[since_break[m - t0]] >= 480", "pre_drive[since_break[m - t0]] > 480")],
    "11 hours: violation only after 11 h 01": [('pre_drive[calc - t0] >= drive_limit', 'pre_drive[calc - t0] > drive_limit')],
    "14 hours: driving at the 14th hour still allowed": [('if m >= calc + window + excl:', 'if m > calc + window + excl:')],
    "60/70 hours: violation only after the limit is exceeded": [('pre_work[w0 - t0] >= cap', 'pre_work[w0 - t0] > cap')],
    "one row per rule per duty tour": [('first = {}\n', 'first = {}\n        seen = tour.setdefault("seen", set())\n'),
                                       ('for rule, m in first.items():\n            rows.append((driver, stamp(m), rule))',
                                        'for rule, m in first.items():\n            if rule not in seen:\n'
                                        '                seen.add(rule)\n                rows.append((driver, stamp(m), rule))')],
}


def tests():
    p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                        str(TASK / "tests" / "test_outputs.py")], capture_output=True, text=True)
    return p.returncode, [ln.split("::", 1)[1].split(" ")[0] for ln in p.stdout.splitlines() if ln.startswith("FAILED")]


def run(src):
    mod = types.ModuleType("variant")
    exec(compile(src, "variant", "exec"), mod.__dict__)
    mod.main()


def main():
    Path("/app/data").mkdir(parents=True, exist_ok=True)
    for f in Path("/app/data").iterdir():
        f.unlink()
    for f in (TASK / "environment" / "data").iterdir():
        shutil.copy(f, Path("/app/data") / f.name)
    run(SRC)
    print("oracle", tests())
    truth = {tuple(r) for r in csv.reader(open(OUT))}
    OUT.unlink()
    print("nop rc", tests()[0])
    ok = True
    for name, edits in SHORTCUTS.items():
        src = SRC
        for old, new in edits:
            assert old in src, (name, old)
            src = src.replace(old, new)
        run(src)
        got = {tuple(r) for r in csv.reader(open(OUT))}
        rc, failed = tests()
        ok &= bool(rc)
        fams = [f.split("[")[1].rstrip("]") for f in failed if "family" in f]
        print(f"{'ok ' if rc else '!! PASSES'} {name:62s} diff={len(got ^ truth):3d} {fams}")
    run(SRC)
    print("ALL SHORTCUTS FAIL" if ok else "SOME SHORTCUT PASSES")


if __name__ == "__main__":
    main()
