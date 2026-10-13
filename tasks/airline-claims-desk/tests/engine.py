"""Verifier-side model of 14 CFR Part 250 (denied boarding compensation) and Part 260 (refunds),
written independently of the reference solution. Reads only the verifier's private inputs."""
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

DATA = Path(__file__).resolve().parent / "data"
HOUR = timedelta(hours=1)
LIMITS = {"200": 107500, "400": 215000}


ZONE = {}


def ts(text, airport=None):
    """Record timestamps end in Z (UTC); flight schedule times are local wall times at the airport."""
    if text.endswith("Z"):
        return datetime.fromisoformat(text[:-1]).replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(text).replace(tzinfo=ZONE[airport]).astimezone(timezone.utc)


def dep(leg):
    return ts(leg["scheduled_departure"], leg["origin"])


def arr(leg):
    return ts(leg["scheduled_arrival"], leg["destination"])


class Context:
    def __init__(self):
        read = lambda name: json.loads((DATA / name).read_text())  # noqa: E731
        self.claims = read("claims.json")
        self.flights = {f["flight_id"]: f for f in read("flights.json")}
        airports = read("airports.json")
        self.us = {code for code, a in airports.items() if a["country"] == "US"}
        ZONE.update({code: ZoneInfo(a["time_zone"]) for code, a in airports.items()})
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
        stop = dep(nxt) - arr(journey[-1])
        if stop > 4 * HOUR:                     # 250.1 stopover
            break
        journey.append(nxt)
    if claim["ticket"]["award_ticket_paid_with_miles"]:
        fare = flight["lowest_cash_fare_cents_by_cabin"][journey[0]["cabin"]]
    else:
        fare = sum(l["fare_cents"] for l in journey)
    alt = inc["alternate_transportation"]
    lateness = ts(alt["planned_arrival_at_time_arranged"], alt["arrival_airport"]) - arr(journey[-1])
    second_band_end = 4 * HOUR if ctx.crosses_border(journey) else 2 * HOUR
    if lateness <= HOUR:
        return 0, refund
    if lateness < second_band_end:
        return min(fare * 2, LIMITS["200"]), refund
    return min(fare * 4, LIMITS["400"]), refund


def is_covered_flight(ctx, claim):
    """260.2: a flight to, from or within the U.S. is covered; a segment between two foreign points is covered
    only as part of an itinerary to or from the U.S. with no break in journey (a foreign stopover scheduled to
    exceed 24 hours, or a shorter one where the passenger reclaims bags and leaves the airport)."""
    legs = claim["ticket"]["coupons"]
    idx = claim["incident"]["affected_coupon"] - 1
    if legs[idx]["origin"] in ctx.us or legs[idx]["destination"] in ctx.us:
        return True
    stops = {}
    for c in claim["ticket"]["connections"]:
        a, b = c["between_coupons"]
        gap = dep(legs[b - 1]) - arr(legs[a - 1])
        stops[a - 1] = gap > 24 * HOUR or c["passenger_left_airport"] or not c["bags_checked_through"]
    lo = idx
    while lo > 0 and not stops[lo - 1]:
        lo -= 1
    hi = idx
    while hi < len(legs) - 1 and not stops[hi]:
        hi += 1
    piece = legs[lo:hi + 1]
    return piece[0]["origin"] in ctx.us or piece[-1]["destination"] in ctx.us


def schedule_change(ctx, claim):
    """(compensation, refund, date the refund due date is counted from)."""
    inc, legs = claim["incident"], claim["ticket"]["coupons"]
    if not is_covered_flight(ctx, claim):
        return 0, 0, None
    threshold = 6 * 60 if ctx.crosses_border(legs) else 3 * 60
    event = inc["event"]
    leg = legs[inc["affected_coupon"] - 1]
    early = late = timedelta(0)
    if inc.get("new_scheduled_departure"):
        early = dep(leg) - ts(inc["new_scheduled_departure"], inc.get("new_origin_airport") or leg["origin"])
        late = ts(inc["new_scheduled_arrival"], inc.get("new_destination_airport") or leg["destination"]) - arr(leg)
    changes = [event == "cancelled",
               bool(inc.get("new_origin_airport")), bool(inc.get("new_destination_airport")),
               inc.get("new_connection_points", 0) > 0,
               event == "downgrade",
               early >= timedelta(minutes=threshold),
               late >= timedelta(minutes=threshold)]
    qualifies = any(changes)
    response = inc["consumer_response"]
    declined = response in {"rejected_alternatives", "did_not_respond_and_flight_departed",
                            "did_not_respond_before_scheduled_departure", "requested_refund"}
    if qualifies and declined:
        total = sum(l["fare_cents"] for l in legs) + sum(a["fee_cents"] for a in claim["ancillary_purchases"])
        if response == "did_not_respond_and_flight_departed":
            moment = dep(leg) - early
        elif response == "did_not_respond_before_scheduled_departure":
            moment = dep(leg)
        elif event == "cancelled" and inc.get("alternative_offered") == "none":
            moment = ts(inc["carrier_notice_at"])
        else:
            moment = ts(inc["consumer_response_at"])
        dates = [moment.date()]
        if claim["refund_requested_on"]:
            dates.append(date.fromisoformat(claim["refund_requested_on"]))
        return 0, total, min(dates).isoformat()
    if qualifies or response in {"accepted_rebooking", "flew_on_changed_flight"}:
        return 0, unused_fees(claim), claim["refund_requested_on"]
    return 0, 0, None


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
            longest_cross = max(longest_cross, arr(f) - dep(f))
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
        result = HANDLERS[claim["claim_type"]](ctx, claim)
        comp, refund = result[:2]
        start = result[2] if len(result) > 2 else claim["refund_requested_on"]
        out[claim["claim_id"]] = {
            "compensation": f"{comp // 100}.{comp % 100:02d}",
            "refund": f"{refund // 100}.{refund % 100:02d}",
            "refund_due_date": ctx.deadline(start, claim["ticket"]["payment_method"]).isoformat()
            if refund else "none"}
    return out
