#!/usr/bin/env python3
"""Dev-only calibration for airline-claims-desk (never uploaded): oracle passes, empty output fails, and each
common misreading of 14 CFR Parts 250 and 260 fails at least one test. Each misreading is a small source edit
of the reference solution. Needs a writable /app."""
import csv
import shutil
import subprocess
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TASK = ROOT / "tasks" / "airline-claims-desk"
OUT = Path("/app/output/claim_decisions.csv")
SRC = (TASK / "solution" / "solve.py").read_text()

NAIVE = 'ZoneInfo(AIRPORTS[airport]["time_zone"])'
SHORTCUTS = {
    # ---- time handling
    "schedule wall times read as UTC": [(NAIVE, 'timezone.utc')],
    "fixed summer-time offsets (clock changes ignored)": [
        (NAIVE, 'timezone(ZoneInfo(AIRPORTS[airport]["time_zone"]).utcoffset(datetime(2026, 7, 1)))')],
    "fixed standard-time offsets (clock changes ignored)": [
        (NAIVE, 'timezone(ZoneInfo(AIRPORTS[airport]["time_zone"]).utcoffset(datetime(2026, 1, 15)))')],
    "due dates from local departure dates": [
        ('start = utc_date(offered[0][0].at(at)[0])', 'start = utc_date(offered[0][0].at(at)[0] + LOCAL(offered[0][0].a))'),
        ('start = utc_date(cancelled[0].at(bought)[0])', 'start = utc_date(cancelled[0].at(bought)[0] + LOCAL(cancelled[0].a))'),
        ('def utc_date(m):', 'def LOCAL(ap):\n    return int(ZoneInfo(AIRPORTS[ap]["time_zone"]).utcoffset(datetime(2026, 10, 31)).total_seconds() // 60)\n\n\ndef utc_date(m):')],
    # ---- schedule history
    "latest schedule version used everywhere": [('v = [x for x in self.versions if x[0] <= m]', 'v = self.versions')],
    "original itinerary = first published schedule": [
        ('o_dep, o_arr = legs[0].at(bought)[0], legs[-1].at(bought)[1]',
         'o_dep, o_arr = legs[0].versions[0][1], legs[-1].versions[0][2]')],
    "change measured from the previous notice only": [
        ('o_dep, o_arr = legs[0].at(bought)[0], legs[-1].at(bought)[1]',
         'o_dep, o_arr = legs[0].at(at - 1)[0], legs[-1].at(at - 1)[1]')],
    "replacement's planned arrival from its latest schedule": [
        ('late = FLIGHTS[alt[0]["itinerary"][-1]].at(when)[1]', 'late = FLIGHTS[alt[0]["itinerary"][-1]].versions[-1][2]')],
    # ---- significant change (260.2)
    "significance judged flight by flight": [
        ('significant = significant or o_dep - n_dep >= limit or n_arr - o_arr >= limit \\',
         'significant = significant or any(f.at(bought)[0] - f.at(at)[0] >= limit or f.at(at)[1] - f.at(bought)[1] >= limit for f in legs if f.id in kept) or (offered[-1][0].id not in {x.id for x in legs} and n_arr - o_arr >= limit) \\')],
    "a later departure counts as a significant change": [
        ('or offered[0][0].a != legs[0].a', 'or n_dep - o_dep >= limit or offered[0][0].a != legs[0].a')],
    "a different connecting airport counts": [
        ('or len(offered) > len(legs)', 'or [f.b for f, _ in offered[:-1]] != [f.b for f in legs[:-1]] or len(offered) > len(legs)')],
    "more connections not counted": [('or len(offered) > len(legs) or', 'or')],
    "downgrade not counted": [('or any(RANK[cb] > cabin for _, cb in offered)', '')],
    "airport change not counted": [('or offered[0][0].a != legs[0].a or offered[-1][0].b != legs[-1].b \\', '\\')],
    "3-hour threshold for every itinerary": [('limit = 360 if intl(legs) else 180', 'limit = 180')],
    "threshold exclusive (more than 3 / 6 hours)": [
        ('o_dep - n_dep >= limit or n_arr - o_arr >= limit', 'o_dep - n_dep > limit or n_arr - o_arr > limit')],
    "a cancellation needs a late rebooking to count": [('significant = bool(cancelled)', 'significant = not offered and bool(cancelled)')],
    # ---- responses and refunds (260.4, 260.6)
    "silence treated as acceptance": [('accepted = choice in', 'accepted = choice is None or choice in'),
                                      ('return 0, unused_fees(c), asked', 'return 0, unused_fees(c), asked or utc_date(at)')],
    "accepting a voucher gives up the refund of unused extras": [
        ('return 0, unused_fees(c), asked', 'return 0, (0 if choice == "accepted_voucher" else unused_fees(c)), asked')],
    "unused extras refunded after declining a minor change": [
        ('return 0, 0, None                                                                    # declined',
         'return 0, unused_fees(c), asked or utc_date(at)                                       # declined')],
    "fare refunded without ancillary fees": [
        ('total = sum(x["fare_cents"] for x in cps) + sum(a["fee_cents"] for a in c["ancillary_purchases"])',
         'total = sum(x["fare_cents"] for x in cps)')],
    "boarding the new flight not treated as acceptance": [('or bool(events(c, "boarded"))', '')],
    # ---- refund due dates
    "due date counted from the passenger's request only": [('if asked and asked < start:', 'if asked:')],
    "earliest date ignored (the 260.6(a)(2) date always)": [('if asked and asked < start:', 'if False:')],
    "unanswered change counted from the original departure": [
        ('start = utc_date(offered[0][0].at(at)[0])', 'start = utc_date(legs[0].at(bought)[0])')],
    "unanswered voucher counted from the first flight": [
        ('start = utc_date(cancelled[0].at(bought)[0])', 'start = utc_date(legs[0].at(bought)[0])')],
    "nothing offered counted from the request": [('start = utc_date(at)                                                         # (i)',
                                                  'start = asked or utc_date(at)')],
    "7 business days for every payment method": [('if method != "credit_card":', 'if False:')],
    "federal holidays not excluded": [('and d.isoformat() not in HOLIDAYS', '')],
    # ---- covered flights
    "every flight covered (break in journey ignored)": [('if affected and not covered(c, legs, affected[0]):', 'if False:')],
    "a 24-hour stopover is a break in journey": [('return gap <= 1440 and', 'return gap < 1440 and')],
    # ---- denied boarding (250)
    "accepting the offered compensation makes a volunteer": [
        ('vol = events(c, "volunteer_offer_accepted")', 'vol = events(c, "volunteer_offer_accepted") + events(c, "compensation_offer_accepted")')],
    "check-in deadline ignored": [('if utc(events(c, "checked_in")[0]["at"]) > dep - close:', 'if False:')],
    "check-in at the deadline counts as late": [('> dep - close:', '>= dep - close:')],
    "45-minute check-in for every flight": [('close = 60 if f.b not in US else 45', 'close = 45')],
    "any substitution or weight/balance excuses compensation": [
        ('if den["reason"] == "aircraft_substitution" and den["required_for_operational_or_safety_reasons"]:',
         'if den["reason"] != "oversold":')],
    "weight/balance excuse on any aircraft": [('\\\n            and f.seats <= 60:', ':')],
    "domestic bands for every trip": [('upper = 240 if intl(legs) else 120', 'upper = 120')],
    "band boundaries: 2 h and 4 h still 200%": [('if late < upper:', 'if late <= upper:')],
    "band boundaries: 1 h already 200%": [('if late <= 60:', 'if late < 60:')],
    "fare of the whole ticket": [('fare = sum(x["fare_cents"] for x in cps[k:end + 1])', 'fare = sum(x["fare_cents"] for x in cps)')],
    "fare of the denied flight only": [('fare = sum(x["fare_cents"] for x in cps[k:end + 1])', 'fare = cps[k]["fare_cents"]')],
    "stopover at 4 h or more": [('<= 240:\n        end += 1', '< 240:\n        end += 1')],
    "pre-2024 caps": [('CAP_200, CAP_400 = 107500, 215000', 'CAP_200, CAP_400 = 77500, 155000')],
    "no compensation without a replacement": [('return min(4 * fare, CAP_400), unused\n    when', 'return 0, unused\n    when')],
    "Part 250 applied to every flight": [('if f.a not in US or f.seats < 30 or not f.scheduled:', 'if False:')],
    "no refund of unused extras on oversale": [('unused = unused_fees(c)\n    vol', 'unused = 0\n    vol')],
    # ---- bags (260.5)
    "bag delay from the scheduled arrival": [('- legs[-1].door <= limit', '- legs[-1].versions[-1][2] <= limit')],
    "12-hour bag standard for every itinerary": [('limit = 1800 if longest > 720 else 900', 'limit = 720')],
    "15 hours for every international itinerary": [('limit = 1800 if longest > 720 else 900', 'limit = 900')],
    "segment length from the wall clocks": [
        ('longest = max(f.versions[-1][2] - f.versions[-1][1] for f in cross)',
         'longest = max(f.versions[-1][2] - f.versions[-1][1] + (int(ZoneInfo(AIRPORTS[f.b]["time_zone"]).utcoffset(datetime(2026, 10, 10)).total_seconds()) - int(ZoneInfo(AIRPORTS[f.a]["time_zone"]).utcoffset(datetime(2026, 10, 10)).total_seconds())) // 60 for f in cross)')],
    "bag delivered at the limit counts as late": [('<= limit:                   # 260.5(a)', '< limit:')],
    "no mishandled baggage report required": [('if not events(c, "mishandled_baggage_report"):', 'if False:')],
    "bag exemptions ignored": [('if any(e["type"].startswith("passenger_") for e in c["events"]):', 'if False:')],
    "refund the bag's own fee even when not linked": [('if bag["fee_linked_to_this_bag_by_unique_identifier"]:', 'if True:')],
    "subscriber refunded the fee actually paid": [('if sub.get("subscribed"):', 'if False:')],
    "service refunds even when consumer at fault": [('if any(e["through_fault_of_consumer"]', 'if False and any(e["through_fault_of_consumer"]')],
}


def tests():
    p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                        str(TASK / "tests" / "test_outputs.py")], capture_output=True, text=True)
    return p.returncode, [ln.split("::", 1)[1].split(" ")[0] for ln in p.stdout.splitlines() if ln.startswith("FAILED")]


def run(src):
    mod = types.ModuleType("solve_variant")
    exec(compile(src, "solve_variant", "exec"), mod.__dict__)
    mod.main()


def main():
    Path("/app/data").mkdir(parents=True, exist_ok=True)
    for f in Path("/app/data").iterdir():
        f.unlink()
    for f in (TASK / "environment" / "data").iterdir():
        shutil.copy(f, Path("/app/data") / f.name)
    run(SRC)
    truth = {r["claim_id"]: r for r in csv.DictReader(open(OUT))}
    print("oracle", tests())
    OUT.unlink()
    print("nop rc", tests()[0])
    ok = True
    for name, edits in SHORTCUTS.items():
        src = SRC
        for old, new in edits:
            assert old in src, (name, old)
            src = src.replace(old, new)
        try:
            run(src)
        except Exception as e:  # noqa: BLE001
            print(f"!! CRASH {name}: {e!r}")
            ok = False
            continue
        got = {r["claim_id"]: r for r in csv.DictReader(open(OUT))}
        wrong = sum(1 for c, v in truth.items() if got.get(c) != v)
        rc, failed = tests()
        ok &= bool(rc)
        fams = [f.split("[")[1].rstrip("]") for f in failed if "family" in f]
        print(f"{'ok ' if rc else '!! PASSES'} {name:60s} wrong={wrong:3d} {fams}")
    run(SRC)
    print("ALL SHORTCUTS FAIL" if ok else "SOME SHORTCUT PASSES")


if __name__ == "__main__":
    main()
