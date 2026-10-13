#!/usr/bin/env python3
"""Dev-only calibration for airline-claims-desk: oracle passes, empty output fails, and each common
misreading of 14 CFR Parts 250/260 fails at least one test."""
import contextlib
import copy
import csv
import importlib.util
import shutil
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TASK = ROOT / "tasks" / "airline-claims-desk"
OUT = Path("/app/output/claim_decisions.csv")


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


S = load("solve", TASK / "solution" / "solve.py")
E = load("engine", TASK / "tests" / "engine.py")
O = {k: getattr(S, k) for k in ("oversale", "schedule_change", "baggage", "service", "due_date", "mins",
                                "covered")}


@contextlib.contextmanager
def patched(**kw):
    old = {k: getattr(S, k) for k in kw}
    for k, v in kw.items():
        setattr(S, k, v)
    try:
        yield
    finally:
        for k, v in old.items():
            setattr(S, k, v)


def tests():
    p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                        str(TASK / "tests" / "test_outputs.py")], capture_output=True, text=True)
    return p.returncode, [ln.split("::", 1)[1].split(" ")[0] for ln in p.stdout.splitlines() if ln.startswith("FAILED")]


def ov(mutate=None, post=None):
    def f(c, flights, country):
        c2 = copy.deepcopy(c)
        fl = copy.deepcopy(flights)
        if mutate:
            mutate(c2, fl, country)
        r = O["oversale"](c2, fl, country)
        return post(c2, r, fl, country) if post else r
    return f


def old_caps(c, fl, country):
    pass


def caps_old(c, r, fl, country):
    comp, ref = r
    return ({107500: 77500, 215000: 155000}.get(comp, comp), ref)


def no_caps(c, r, fl, country):
    comp, ref = r
    if comp in (107500, 215000):
        cps = c["ticket"]["coupons"]
        fare = cps[c["incident"]["denied_coupon"] - 1]["fare_cents"]
        return (comp * 10, ref)
    return r


def domestic_bands(c, fl, country):
    for k in list(country):
        country[k] = "US"


def whole_ticket_fare(c, fl, country):
    total = sum(x["fare_cents"] for x in c["ticket"]["coupons"])
    for x in c["ticket"]["coupons"]:
        x["fare_cents"] = 0
    c["ticket"]["coupons"][c["incident"]["denied_coupon"] - 1]["fare_cents"] = total


def denied_leg_only(c, fl, country):
    k = c["incident"]["denied_coupon"] - 1
    for i, x in enumerate(c["ticket"]["coupons"]):
        if i != k:
            x["fare_cents"] = 0


def no_exceptions(c, fl, country):
    i = c["incident"]
    i["volunteered"] = False
    i["held_confirmed_reserved_space"] = True
    i["complied_with_ticketing_check_in_and_acceptability_rules"] = True
    i["cause"] = "oversale"
    i["seated_in_other_section_at_no_extra_charge"] = None


def any_substitution_excused(c, fl, country):
    if "substitution" in c["incident"]["cause"] or "weight" in c["incident"]["cause"]:
        c["incident"]["cause"] = "substitution_of_smaller_aircraft_required_for_operational_or_safety_reasons"


def no_scope(c, fl, country):
    f = fl[c["incident"]["denied_flight_id"]]
    f["designed_passenger_seats"] = max(f["designed_passenger_seats"], 30)
    country[f["origin"]] = "US"


def zero_fare_zero(c, fl, country):
    if c["ticket"]["award_ticket_paid_with_miles"]:
        c["ticket"]["award_ticket_paid_with_miles"] = False


def strict_bands(c, r, fl, country):
    comp, ref = r
    cps = c["ticket"]["coupons"]
    return r


def boundary_shift(c, fl, country):
    """Treat 'one hour' as the start of the 200% band and the 2/4 h mark as still 200%."""
    alt = c["incident"]["alternate_transportation"]
    from datetime import datetime
    t = datetime.strptime(alt["planned_arrival_at_time_arranged"], "%Y-%m-%dT%H:%MZ")
    k = c["incident"]["denied_coupon"] - 1
    a = datetime.strptime(c["ticket"]["coupons"][k]["scheduled_arrival"], "%Y-%m-%dT%H:%MZ")
    late = (t - a).total_seconds() / 60
    if late in (60, 120, 240):
        alt["planned_arrival_at_time_arranged"] = (t + timedelta(minutes=1 if late == 60 else -1)).strftime("%Y-%m-%dT%H:%MZ")


def no_ancillary_db(c, r, fl, country):
    return (r[0], 0)


def sc(mutate=None, post=None):
    def f(c, country):
        c2 = copy.deepcopy(c)
        ctry = dict(country)
        if mutate:
            mutate(c2, ctry)
        r = O["schedule_change"](c2, ctry)
        return post(c2, r) if post else r
    return f


def sc_domestic(c, ctry):
    for k in ctry:
        ctry[k] = "US"


def sc_strict(c, ctry):
    i = c["incident"]
    for k in ("new_departure_shift_minutes", "new_arrival_shift_minutes"):
        if k in i and abs(i[k]) in (180, 360):
            i[k] = i[k] - 1 if i[k] > 0 else i[k] + 1


def sc_silence_is_acceptance(c, ctry):
    if c["incident"]["consumer_response"] == "did_not_respond_before_scheduled_departure":
        c["incident"]["consumer_response"] = "accepted_voucher_affirmatively"
        c["refund_requested_on"] = c["refund_requested_on"] or c["ticket"]["coupons"][0]["scheduled_departure"][:10]


def sc_fare_only(c, r):
    comp, ref, start = r
    total = sum(x["fare_cents"] for x in c["ticket"]["coupons"])
    if ref > total:
        return (0, total, start)
    return r


def sc_only_delay(c, ctry):
    i = c["incident"]
    if i["event"] in ("airport_change", "added_connection", "downgrade"):
        i["event"] = "retimed"
        i.pop("new_origin_airport", None)
        i.pop("new_destination_airport", None)
        i["new_connection_points"] = 0


def sc_no_partial(c, r):
    if c["incident"]["consumer_response"] in ("accepted_rebooking", "flew_on_changed_flight"):
        return (0, 0, None)
    return r


def sc_voucher_waives_fees(c, r):
    """The original reading: accepting a voucher gives up the 260.4 refund of unused extras."""
    if c["incident"]["consumer_response"] == "accepted_voucher_affirmatively":
        return (0, 0, None)
    return r


def sc_declined_minor_change_refunds_extras(c, r):
    unused = sum(a["fee_cents"] for a in c["ancillary_purchases"] if not a["provided"])
    if r[1] == 0 and unused and c["incident"]["consumer_response"] == "rejected_alternatives":
        return (0, unused, c["refund_requested_on"] or c["incident"]["consumer_response_at"][:10])
    return r


def sc_due_from_request_only(c, r):
    if r[1] and c["refund_requested_on"]:
        return (r[0], r[1], c["refund_requested_on"])
    return r


def sc_due_ignores_earliest(c, r):
    """Use the 260.6(a)(2) date even when the passenger asked earlier, or the request when it is later."""
    asked = c["refund_requested_on"]
    if r[1] and asked and asked > r[2]:
        return (r[0], r[1], asked)
    return r


def sc_departed_original_date(c, ctry):
    i = c["incident"]
    if i["consumer_response"] == "did_not_respond_and_flight_departed":
        i["new_departure_shift_minutes"] = 0


def sc_cancel_none_from_request(c, ctry):
    i = c["incident"]
    if i["event"] == "cancelled" and i.get("alternative_offered") == "none":
        i["alternative_offered"] = "rebooking_on_later_flight"


def every_flight_covered(c, ctry):
    return True


def break_at_24_hours(c, ctry):
    c = copy.deepcopy(c)
    cps = c["ticket"]["coupons"]
    for x in c["ticket"].get("connections", []):
        a, b = x["between_coupons"]
        if O["mins"](cps[a - 1]["scheduled_arrival"], cps[b - 1]["scheduled_departure"]) >= 1440:
            x["passenger_left_airport"] = True
    return O["covered"](c, ctry)


def any_foreign_segment_uncovered(c, ctry):
    k = c["incident"]["affected_coupon"] - 1
    cp = c["ticket"]["coupons"][k]
    return ctry[cp["origin"]] == "US" or ctry[cp["destination"]] == "US"


def bg(mutate=None, post=None):
    def f(c, flights, country):
        c2 = copy.deepcopy(c)
        if mutate:
            mutate(c2, flights, country)
        r = O["baggage"](c2, flights, country)
        return post(c2, r) if post else r
    return f


def bag_12_everywhere(c, flights, country):
    pass


def bag_flat_threshold(limit_fn):
    def baggage(c, flights, country):
        inc = c["incident"]
        if not inc["mishandled_baggage_report_filed"] or any((inc["exemption_facts"] or {}).values()):
            return 0, 0
        lim = limit_fn(c, flights, country)
        if inc["status"] != "lost" and S.mins(inc["deplaning_opportunity_at_final_destination"],
                                              inc["delivered_or_picked_up_at"]) <= lim:
            return 0, 0
        return O["baggage"](dict(c, incident=dict(inc, delivered_or_picked_up_at="2099-01-01T00:00Z")),
                            flights, country)
    return baggage


def bag_inclusive(c, flights, country):
    inc = c["incident"]
    if inc["status"] == "delivered":
        from datetime import datetime
        t = datetime.strptime(inc["delivered_or_picked_up_at"], "%Y-%m-%dT%H:%MZ")
        inc["delivered_or_picked_up_at"] = (t + timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%MZ")


def bag_no_mbr_needed(c, flights, country):
    c["incident"]["mishandled_baggage_report_filed"] = True


def bag_ignore_exemptions(c, flights, country):
    c["incident"]["exemption_facts"] = None


def bag_always_linked(c, flights, country):
    for b in c["checked_bags"]:
        b["fee_linked_to_this_bag_by_unique_identifier"] = True


def bag_subscription_zero(c, flights, country):
    c["incident"]["bag_fee_subscription"] = None


def due_business_all(trigger, method, holidays):
    return O["due_date"](trigger, "credit_card", holidays)


def due_calendar_7(trigger, method, holidays):
    d = date.fromisoformat(trigger)
    return d + timedelta(days=7) if method == "credit_card" else d + timedelta(days=20)


def due_no_holidays(trigger, method, holidays):
    return O["due_date"](trigger, method, set())


def service_fault_ignored(c):
    c2 = copy.deepcopy(c)
    c2["incident"]["service_failure_through_fault_of_consumer"] = False
    return O["service"](c2)


SHORTCUTS = {
    "pre-2024 caps ($775/$1,550)": dict(oversale=ov(post=caps_old)),
    "no compensation caps": dict(oversale=ov(post=no_caps)),
    "domestic time bands for every trip": dict(oversale=ov(domestic_bands)),
    "fare of the whole ticket": dict(oversale=ov(whole_ticket_fare)),
    "fare of the denied leg only": dict(oversale=ov(denied_leg_only)),
    "no 250.6 exceptions or volunteer/standby checks": dict(oversale=ov(no_exceptions)),
    "any substitution or weight/balance excuses compensation": dict(oversale=ov(any_substitution_excused)),
    "Part 250 applied to every flight": dict(oversale=ov(no_scope)),
    "band boundaries off by one": dict(oversale=ov(boundary_shift)),
    "no refund of unused fees on oversale": dict(oversale=ov(post=no_ancillary_db)),
    "domestic 3 h threshold for every itinerary": dict(schedule_change=sc(sc_domestic)),
    "change threshold treated as more than 3/6 h": dict(schedule_change=sc(sc_strict)),
    "silence treated as accepting a voucher": dict(schedule_change=sc(sc_silence_is_acceptance)),
    "fare refunded without ancillary fees": dict(schedule_change=sc(post=sc_fare_only)),
    "only time changes count as significant": dict(schedule_change=sc(sc_only_delay)),
    "no fee refund after accepting rebooking": dict(schedule_change=sc(post=sc_no_partial)),
    "12 h bag standard for every itinerary": dict(baggage=bag_flat_threshold(lambda c, f, k: 720)),
    "15 h for every international itinerary": dict(baggage=bag_flat_threshold(
        lambda c, f, k: 900 if any(k[x["origin"]] != "US" or k[x["destination"]] != "US"
                                   for x in c["ticket"]["coupons"]) else 720)),
    "bag delay limit exclusive (delivered at the limit counts as late)": dict(baggage=bg(bag_inclusive)),
    "no mishandled baggage report required": dict(baggage=bg(bag_no_mbr_needed)),
    "bag exemptions ignored": dict(baggage=bg(bag_ignore_exemptions)),
    "refund the bag's own fee even when not linked": dict(baggage=bg(bag_always_linked)),
    "subscriber refunded the fee actually paid": dict(baggage=bg(bag_subscription_zero)),
    "7 business days for every payment method": dict(due_date=due_business_all),
    "7 calendar days for credit cards": dict(due_date=due_calendar_7),
    "federal holidays not excluded": dict(due_date=due_no_holidays),
    "service refunds even when consumer at fault": dict(service=service_fault_ignored),
    "accepting a voucher gives up the refund of unused extras": dict(schedule_change=sc(post=sc_voucher_waives_fees)),
    "unused extras refunded after declining a minor change": dict(
        schedule_change=sc(post=sc_declined_minor_change_refunds_extras)),
    "due date counted from the passenger's request only": dict(schedule_change=sc(post=sc_due_from_request_only)),
    "due date not counted from the earliest date": dict(schedule_change=sc(post=sc_due_ignores_earliest)),
    "unanswered change counted from the original departure": dict(schedule_change=sc(sc_departed_original_date)),
    "cancellation with nothing offered counted from the request": dict(
        schedule_change=sc(sc_cancel_none_from_request)),
    "every flight covered (break in journey ignored)": dict(covered=every_flight_covered),
    "a stopover of exactly 24 hours is a break in journey": dict(covered=break_at_24_hours),
    "every foreign-to-foreign segment uncovered": dict(covered=any_foreign_segment_uncovered),
}


def main():
    Path("/app/data").mkdir(parents=True, exist_ok=True)
    for f in Path("/app/data").iterdir():
        f.unlink()
    for f in (TASK / "environment" / "data").iterdir():
        shutil.copy(f, Path("/app/data") / f.name)
    S.main()
    print("oracle", tests())
    truth = E.expected()
    OUT.unlink()
    print("nop rc", tests()[0])
    ok = True
    for name, patch in SHORTCUTS.items():
        with patched(**patch):
            S.main()
        got = {r["claim_id"]: r for r in csv.DictReader(open(OUT))}
        wrong = sum(1 for c, v in truth.items() if any(got[c][f] != v[f] for f in v))
        rc, failed = tests()
        ok &= bool(rc)
        fams = [f.split("[")[1].rstrip("]") for f in failed if "family" in f]
        print(f"{'ok ' if rc else '!! PASSES'} {name:62s} wrong={wrong:3d} {fams}")
    S.main()
    print("ALL SHORTCUTS FAIL" if ok else "SOME SHORTCUT PASSES")


if __name__ == "__main__":
    main()
