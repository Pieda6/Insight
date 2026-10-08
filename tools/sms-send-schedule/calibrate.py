#!/usr/bin/env python3
"""Dev-only calibration for sms-send-schedule (never uploaded).

Checks oracle == engine == golden, oracle passes and empty output fails, then runs common
misreadings of 47 CFR 64.1200 (patched copies of the reference solution) through the real tests.
Every shortcut must fail at least one test. Run from anywhere; needs writable /app.
"""
import contextlib
import csv
import importlib.util
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
TASK = ROOT / "tasks" / "sms-send-schedule"
OUT = Path("/app/output/send_schedule.csv")


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


solve = load("solve", TASK / "solution" / "solve.py")
engine = load("engine", TASK / "tests" / "engine.py")
orig = {k: getattr(solve, k) for k in ("allowed", "candidates", "revokes", "load", "months_before")}


def run_tests():
    p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                        str(TASK / "tests" / "test_outputs.py")], capture_output=True, text=True)
    failed = [ln.split("::", 1)[1].split(" ")[0] for ln in p.stdout.splitlines() if ln.startswith("FAILED")]
    return p.returncode, failed


@contextlib.contextmanager
def patched(**kw):
    old = {k: getattr(solve, k) for k in kw}
    for k, v in kw.items():
        setattr(solve, k, v)
    try:
        yield
    finally:
        for k, v in old.items():
            setattr(solve, k, v)


def hours_ok(t, zone):
    lt = t.astimezone(ZoneInfo(zone))
    return 8 * 60 <= lt.hour * 60 + lt.minute <= 21 * 60


def quiet_hours_always(t, c, k, a):
    return orig["allowed"](t, c, k, a) and hours_ok(t, c["address_time_zone"])


def registry_always(t, c, k, a):
    return orig["allowed"](t, c, k, a) and not any(r <= t and (x is None or t < x) for r, x in k["registry"])


def ctia_only(text):
    return text.strip().strip(".!").lower() in {"stop", "end", "cancel", "unsubscribe", "quit", "stopall"}


def all_atds(t, c, k, a):
    return orig["allowed"](t, c, k, True)


def no_atds(t, c, k, a):
    return orig["allowed"](t, c, k, False)


def ebr_enough_for_atds(t, c, k, a):
    if orig["allowed"](t, c, k, a):
        return True
    if not a:
        return False
    return orig["allowed"](t, c, k, False) and _ebr(t, c, k)


def _ebr(t, c, k):
    d = t.astimezone(ZoneInfo(c["address_time_zone"])).date()
    fr = min(k["requests"], default=None)
    if fr is not None and fr <= t:
        return False
    return any(solve.months_before(d, 18) <= e <= d for e in k["purchases"]) or \
        any(solve.months_before(d, 3) <= e <= d for e in k["inquiries"])


def any_consent_load():
    contacts, atds, info = orig["load"]()
    for r in solve.read("consents.csv"):
        info[r["contact_id"]]["consent"].append(solve.ts(r["obtained_at"]))
    return contacts, atds, info


def inquiries_18_months_load():
    contacts, atds, info = orig["load"]()
    for k in info.values():
        k["purchases"] += k["inquiries"]
    return contacts, atds, info


def utc_date(t, c, k, a):
    """Hours on the address zone, but the relationship window counted from the UTC date."""
    if any(r <= t < solve.add_years(r, 5) for r in k["requests"]):
        return False
    consent = any(o <= t for o in k["consent"]) and not any(r <= t for r in k["requests"])
    if a and not consent:
        return False
    if consent or _ebr(t, dict(c, address_time_zone="UTC"), k):
        return True
    if any(r <= t and (x is None or t < x) for r, x in k["registry"]):
        return False
    return hours_ok(t, c["address_time_zone"])


def dnc_forever(t, c, k, a):
    if any(r <= t for r in k["requests"]):
        return False
    return orig["allowed"](t, c, k, a)


def ebr_survives_request(t, c, k, a):
    if any(r <= t < solve.add_years(r, 5) for r in k["requests"]):
        return False
    k2 = dict(k, requests=[])
    consent = any(o <= t for o in k["consent"]) and not any(r <= t for r in k["requests"])
    if a and not consent:
        return False
    if consent or _ebr(t, c, k2):
        return True
    return orig["allowed"](t, c, dict(k, purchases=[], inquiries=[]), a)


def consent_returns_after_lapse(t, c, k, a):
    k2 = dict(k, requests=[r for r in k["requests"] if t < solve.add_years(r, 5)])
    return orig["allowed"](t, c, k2, a)


def area_code_load():
    contacts, atds, info = orig["load"]()
    zones = {r["npa"]: r["time_zone"] for r in solve.read("area_codes.csv")}
    for c in contacts.values():
        c["address_time_zone"] = zones[c["phone"][2:5]]
    return contacts, atds, info


def hq_zone_load():
    contacts, atds, info = orig["load"]()
    for c in contacts.values():
        c["address_time_zone"] = "America/New_York"
    return contacts, atds, info


def no_dst(t, c, k, a):
    """Use the zone's offset at the start of the batch for every instant (ignores the change)."""
    z = ZoneInfo(c["address_time_zone"])
    return _allowed_fixed(t, c, k, a, timezone(datetime(2026, 10, 27, 12, tzinfo=z).utcoffset()))


def _allowed_fixed(t, c, k, a, tz):
    saved = solve.ZoneInfo
    solve.ZoneInfo = lambda name: tz
    try:
        return orig["allowed"](t, c, k, a)
    finally:
        solve.ZoneInfo = saved


def no_dst_candidates(sched, c, k):
    z = ZoneInfo(c["address_time_zone"])
    tz = timezone(datetime(2026, 10, 27, 12, tzinfo=z).utcoffset())
    saved = solve.ZoneInfo
    solve.ZoneInfo = lambda name: tz
    try:
        return orig["candidates"](sched, c, k)
    finally:
        solve.ZoneInfo = saved


def hourly_candidates(sched, c, k):
    out = [sched]
    t = sched.replace(minute=0) + timedelta(hours=1)
    while t <= sched + timedelta(days=7):
        out.append(t)
        t += timedelta(hours=1)
    return out


def strict_nine(t, c, k, a):
    lt = t.astimezone(ZoneInfo(c["address_time_zone"]))
    if (lt.hour, lt.minute) == (21, 0):
        ok = orig["allowed"](t, c, k, a)
        if ok:
            # would this send rely on the hours rule? test with 21:01-equivalent
            return orig["allowed"](t + timedelta(minutes=1), c, k, a)
    return orig["allowed"](t, c, k, a)


SHORTCUTS = {
    "quiet hours on every message": dict(allowed=quiet_hours_always),
    "national registry on every message": dict(allowed=registry_always),
    "CTIA keyword list only (no revoke / opt out / explicit)": dict(revokes=ctia_only),
    "every platform is an autodialer": dict(allowed=all_atds),
    "no platform is an autodialer": dict(allowed=no_atds),
    "any consent record accepted": dict(load=any_consent_load),
    "business relationship enough for autodialer": dict(allowed=ebr_enough_for_atds),
    "18 months for inquiries and applications": dict(load=inquiries_18_months_load),
    "relationship date taken in UTC": dict(allowed=utc_date),
    "seller do-not-call honored forever": dict(allowed=dnc_forever),
    "consent returns when do-not-call period ends": dict(allowed=consent_returns_after_lapse),
    "area-code time zone": dict(load=area_code_load),
    "headquarters time zone": dict(load=hq_zone_load),
    "offset frozen before the DST change": dict(allowed=no_dst, candidates=no_dst_candidates),
    "hourly search": dict(candidates=hourly_candidates),
    "21:00 not allowed": dict(allowed=strict_nine),
}


# Readings that the rule's structure makes equivalent on this data (reported, not required to fail):
# while a seller do-not-call request is honored every message is blocked anyway, and no purchase
# or inquiry follows a request, so whether the request also ends the relationship never matters.
EQUIVALENT = {"do-not-call request does not end relationship": dict(allowed=ebr_survives_request)}


def main():
    Path("/app/data").mkdir(parents=True, exist_ok=True)
    for f in (TASK / "environment" / "data").iterdir():
        shutil.copy(f, Path("/app/data") / f.name)
    solve.main()
    truth = engine.expected()
    got = {r["message_id"]: (r["decision"], r["send_at"]) for r in csv.DictReader(open(OUT))}
    print("engine vs solve mismatches:", [m for m in truth if truth[m] != got[m]][:5])
    rc, failed = run_tests()
    print(f"oracle rc={rc} failed={failed}")
    OUT.unlink()
    rc, _ = run_tests()
    print(f"nop rc={rc} (must be non-zero)")
    ok = True
    for name, patch in SHORTCUTS.items():
        with patched(**patch):
            solve.main()
        got = {r["message_id"]: (r["decision"], r["send_at"]) for r in csv.DictReader(open(OUT))}
        wrong = sum(1 for m in truth if truth[m] != got[m])
        rc, failed = run_tests()
        ok &= bool(rc)
        groups = [f.replace("test_rule_family[", "").rstrip("]") for f in failed if "family" in f]
        print(f"{'ok ' if rc else '!! PASSES'} {name:58s} wrong={wrong:3d} groups={groups}")
    for name, patch in EQUIVALENT.items():
        with patched(**patch):
            solve.main()
        got = {r["message_id"]: (r["decision"], r["send_at"]) for r in csv.DictReader(open(OUT))}
        print(f"equivalent by design: {name}: wrong={sum(1 for m in truth if truth[m] != got[m])}")
    solve.main()
    print("ALL SHORTCUTS FAIL" if ok else "SOME SHORTCUT PASSES")


if __name__ == "__main__":
    main()
