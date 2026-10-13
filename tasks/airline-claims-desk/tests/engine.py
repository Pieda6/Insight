"""Verifier-side model of 14 CFR Part 250 (denied boarding compensation) and Part 260 (refunds),
written independently of the reference solution. Reads only the verifier's private inputs."""
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
HOUR = timedelta(hours=1)
LIMITS = {"200": 107500, "400": 215000}


def ts(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)


class Context:
    def __init__(self):
        read = lambda name: json.loads((DATA / name).read_text())  # noqa: E731
        self.claims = read("claims.json")
        self.flights = {f["flight_id"]: f for f in read("flights.json")}
        self.us = {code for code, a in read("airports.json").items() if a["country"] == "US"}
        self.holidays = {date.fromisoformat(d) for d in read("federal_holidays.json")["observed_dates"]}

    def crosses_border(self, legs):
        return any((l["origin"] in self.us) != (l["destination"] in self.us) or
                   (l["origin"] not in self.us and l["destination"] not in self.us) for l in legs)

    def deadline(self, trigger, method):
        day = date.fromisoformat(trigger)
        if method == "credit_card":
            left = 7
            while left:
                day += timedelta(days=1)
                if day.isoformat() and day.weekday() < 5 and day not in self.holidays:
                    left -= 1
            return day
        return day + timedelta(days=20)


def unused_fees(claim):
    return sum(a["fee_cents"] for a in claim["ancillary_purchases"] if a["provided"] is False)


def denied_boarding(ctx, claim):
    inc, legs = claim["incident"], claim["ticket"]["coupons"]
    flight = ctx.flights[inc["denied_flight_id"]]
    refund = unused_fees(claim)
    covered = flight["origin"] in ctx.us and flight["designed_passenger_seats"] >= 30 and flight["scheduled_service"]
    if not covered or inc["volunteered"] or not inc["held_confirmed_reserved_space"]:
        return 0, refund
    if not inc["complied_with_ticketing_check_in_and_acceptability_rules"]:
        return 0, 0
    reason = inc["cause"]
    excused = (reason == "substitution_of_smaller_aircraft_required_for_operational_or_safety_reasons" or
               (reason == "weight_balance_restriction_required_for_operational_or_safety_reasons"
                and flight["designed_passenger_seats"] <= 60) or
               bool(inc["seated_in_other_section_at_no_extra_charge"]))
    if excused:
        return 0, refund
    first = inc["denied_coupon"] - 1
    journey = [legs[first]]
    for nxt in legs[first + 1:]:
        stop = ts(nxt["scheduled_departure"]) - ts(journey[-1]["scheduled_arrival"])
        if stop > 4 * HOUR:                     # 250.1 stopover
            break
        journey.append(nxt)
    if claim["ticket"]["award_ticket_paid_with_miles"]:
        fare = flight["lowest_cash_fare_cents_by_cabin"][journey[0]["cabin"]]
    else:
        fare = sum(l["fare_cents"] for l in journey)
    lateness = ts(inc["alternate_transportation"]["planned_arrival_at_time_arranged"]) - \
        ts(journey[-1]["scheduled_arrival"])
    second_band_end = 4 * HOUR if ctx.crosses_border(journey) else 2 * HOUR
    if lateness <= HOUR:
        return 0, refund
    if lateness < second_band_end:
        return min(fare * 2, LIMITS["200"]), refund
    return min(fare * 4, LIMITS["400"]), refund


def schedule_change(ctx, claim):
    inc, legs = claim["incident"], claim["ticket"]["coupons"]
    threshold = 6 * 60 if ctx.crosses_border(legs) else 3 * 60
    event = inc["event"]
    changes = [event == "cancelled",
               bool(inc.get("new_origin_airport")), bool(inc.get("new_destination_airport")),
               inc.get("new_connection_points", 0) > 0,
               event == "downgrade",
               -inc.get("new_departure_shift_minutes", 0) >= threshold,
               inc.get("new_arrival_shift_minutes", 0) >= threshold]
    qualifies = any(changes)
    response = inc["consumer_response"]
    declined = response in {"rejected_alternatives", "did_not_respond_and_flight_departed",
                            "did_not_respond_before_scheduled_departure", "requested_refund"}
    if qualifies and declined:
        total = sum(l["fare_cents"] for l in legs) + sum(a["fee_cents"] for a in claim["ancillary_purchases"])
        return 0, total
    if response in {"accepted_rebooking", "flew_on_changed_flight"}:
        return 0, unused_fees(claim)
    return 0, 0


def baggage(ctx, claim):
    inc = claim["incident"]
    if not inc["mishandled_baggage_report_filed"]:
        return 0, 0
    if inc["exemption_facts"] and any(inc["exemption_facts"].values()):
        return 0, 0
    longest_cross = timedelta(0)
    border = False
    for leg in claim["ticket"]["coupons"]:
        if ctx.crosses_border([leg]):
            border = True
            f = ctx.flights[leg["flight_id"]]
            longest_cross = max(longest_cross, ts(f["scheduled_arrival"]) - ts(f["scheduled_departure"]))
    allowed = (30 * HOUR if longest_cross > 12 * HOUR else 15 * HOUR) if border else 12 * HOUR
    if inc["status"] == "delivered":
        waited = ts(inc["delivered_or_picked_up_at"]) - ts(inc["deplaning_opportunity_at_final_destination"])
        if waited <= allowed:
            return 0, 0
    sub = inc.get("bag_fee_subscription")
    if sub and sub.get("subscribed"):
        return 0, sub["lowest_fee_charged_to_non_subscriber_same_status_and_cabin_cents"]
    bags = {b["bag_tag"]: b for b in claim["checked_bags"]}
    the_bag = bags[inc["bag_tag"]]
    if the_bag["fee_linked_to_this_bag_by_unique_identifier"]:
        return 0, the_bag["fee_cents"]
    return 0, max(b["fee_cents"] for b in bags.values())


def ancillary(ctx, claim):
    if claim["incident"]["service_failure_through_fault_of_consumer"]:
        return 0, 0
    return 0, unused_fees(claim)


HANDLERS = {"oversale": denied_boarding, "schedule_change_or_cancellation": schedule_change,
            "baggage": baggage, "ancillary_service_not_provided": ancillary}


def expected():
    ctx = Context()
    out = {}
    for claim in ctx.claims:
        comp, refund = HANDLERS[claim["claim_type"]](ctx, claim)
        out[claim["claim_id"]] = {
            "compensation": f"{comp // 100}.{comp % 100:02d}",
            "refund": f"{refund // 100}.{refund % 100:02d}",
            "refund_due_date": ctx.deadline(claim["refund_trigger_date"],
                                            claim["ticket"]["payment_method"]).isoformat() if refund else "none"}
    return out
