"""Verifier-side model of 14 CFR Part 250 (denied boarding compensation) and Part 260 (refunds), written
independently of the reference solution. Reads only the verifier's private inputs. Times are kept as
timezone-aware datetimes; durations are timedelta differences of instants."""
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

DATA = Path(__file__).resolve().parent / "data"
HOUR = timedelta(hours=1)
LIMITS = {"200": 107500, "400": 215000}


def instant(text, zone=None):
    if text.endswith("Z"):
        return datetime.fromisoformat(text[:-1]).replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(text).replace(tzinfo=zone).astimezone(timezone.utc)


class Timeline:
    """A flight's published schedule versions, each in force from its recording time."""

    def __init__(self, rec, zones):
        self.rec = rec
        self.origin, self.dest = rec["origin"], rec["destination"]
        self.versions = sorted(((instant(v["recorded_at"]), instant(v["departure"], zones[self.origin]),
                                 instant(v["arrival"], zones[self.dest])) for v in rec["schedule"]),
                               key=lambda v: v[0])
        self.door = instant(rec["door_opened_at_gate"], zones[self.dest]) if rec["door_opened_at_gate"] else None

    def as_of(self, when):
        current = None
        for recorded, dep, arr in self.versions:
            if recorded <= when:
                current = (dep, arr)
        return current

    def departs(self, when):
        return self.as_of(when)[0]

    def arrives(self, when):
        return self.as_of(when)[1]


class Context:
    def __init__(self):
        read = lambda name: json.loads((DATA / name).read_text())  # noqa: E731
        self.claims = read("claims.json")
        airports = read("airports.json")
        self.us = {code for code, a in airports.items() if a["country"] == "US"}
        zones = {code: ZoneInfo(a["time_zone"]) for code, a in airports.items()}
        self.flights = {f["flight_id"]: Timeline(f, zones) for f in read("flights.json")}
        self.holidays = {date.fromisoformat(d) for d in read("federal_holidays.json")["observed_dates"]}
        carrier = read("carrier.json")
        self.class_order = carrier["classes_of_service_highest_first"]

    def international(self, timelines):
        return any(t.origin not in self.us or t.dest not in self.us for t in timelines)

    def deadline(self, trigger, method):
        day = trigger
        if method == "credit_card":
            left = 7
            while left:
                day += timedelta(days=1)
                if day.weekday() < 5 and day not in self.holidays:
                    left -= 1
            return day
        return day + timedelta(days=20)


def log(claim, kind):
    return [e for e in claim["events"] if e["type"] == kind]


def unused_fees(claim):
    return sum(a["fee_cents"] for a in claim["ancillary_purchases"] if a["provided"] is False)


def asked_on(claim):
    return instant(claim["refund_requested_at"]).date() if claim["refund_requested_at"] else None


def denied_boarding(ctx, claim):
    tl = [ctx.flights[c["flight_id"]] for c in claim["ticket"]["coupons"]]
    coupons = claim["ticket"]["coupons"]
    refund = unused_fees(claim)
    gate_event = (log(claim, "volunteer_offer_accepted") + log(claim, "denied_boarding"))[0]
    idx = [c["flight_id"] for c in coupons].index(gate_event["flight_id"])
    flight = tl[idx]
    rec = flight.rec
    in_scope = flight.origin in ctx.us and rec["designed_passenger_seats"] >= 30 and rec["scheduled_service"]
    if not in_scope or gate_event["type"] == "volunteer_offer_accepted":
        return 0, refund
    gate_time = instant(gate_event["at"])
    std = flight.departs(gate_time)
    cutoff = std - timedelta(minutes=45 if flight.dest in ctx.us else 60)
    if any(instant(e["at"]) > cutoff for e in log(claim, "checked_in") if e["flight_id"] == rec["flight_id"]):
        return 0, 0
    operational = gate_event.get("required_for_operational_or_safety_reasons") is True
    excused = ((gate_event["reason"] == "aircraft_substitution" and operational) or
               (gate_event["reason"] == "weight_balance_restriction" and operational
                and rec["designed_passenger_seats"] <= 60) or
               any(o["extra_charge_cents"] == 0 for o in log(claim, "seat_offered_in_other_cabin")))
    if excused:
        return 0, refund
    journey = [idx]
    while journey[-1] + 1 < len(tl):
        nxt = journey[-1] + 1
        if tl[nxt].departs(gate_time) - tl[journey[-1]].arrives(gate_time) > 4 * HOUR:    # 250.1 stopover
            break
        journey.append(nxt)
    if claim["ticket"]["award_ticket_paid_with_miles"]:
        fare = rec["lowest_cash_fare_cents_by_cabin"][coupons[idx]["cabin"]]
    else:
        fare = sum(coupons[i]["fare_cents"] for i in journey)
    arranged = log(claim, "alternate_transportation_arranged")
    if not arranged:
        return min(fare * 4, LIMITS["400"]), refund
    made = instant(arranged[0]["at"])
    lateness = ctx.flights[arranged[0]["itinerary"][-1]].arrives(made) - tl[journey[-1]].arrives(gate_time)
    second_band_end = 4 * HOUR if ctx.international(tl) else 2 * HOUR
    if lateness <= HOUR:
        return 0, refund
    if lateness < second_band_end:
        return min(fare * 2, LIMITS["200"]), refund
    return min(fare * 4, LIMITS["400"]), refund


def is_covered(ctx, claim, tl, idx, bought):
    """260.2: a segment between two foreign points is covered only as part of an itinerary to or from the U.S.
    without a break in journey (a foreign stopover scheduled to exceed 24 hours, or a shorter one where bags
    are reclaimed and the passenger leaves the airport)."""
    if tl[idx].origin in ctx.us or tl[idx].dest in ctx.us:
        return True
    breaks = {}
    for c in claim["ticket"]["connections"]:
        a, b = c["between_coupons"]
        gap = tl[b - 1].departs(bought) - tl[a - 1].arrives(bought)
        breaks[a - 1] = gap > 24 * HOUR or c["passenger_left_airport"] or not c["bags_checked_through"]
    lo = idx
    while lo > 0 and not breaks[lo - 1]:
        lo -= 1
    hi = idx
    while hi < len(tl) - 1 and not breaks[hi]:
        hi += 1
    return tl[lo].origin in ctx.us or tl[hi].dest in ctx.us


def schedule_change(ctx, claim):
    """(compensation, refund, date the refund due date is counted from)."""
    coupons = claim["ticket"]["coupons"]
    tl = [ctx.flights[c["flight_id"]] for c in coupons]
    bought = instant(claim["ticket"]["purchased_at"])
    notices = sorted(log(claim, "itinerary_change_notice"), key=lambda e: instant(e["at"]))
    final = notices[-1]
    sent = instant(final["at"])
    offer = final["offered_itinerary"]
    new = [(ctx.flights[o["flight_id"]], o["cabin"]) for o in offer] if offer is not None else None
    kept = {t.rec["flight_id"] for t, _ in new or []}
    touched = [i for i, t in enumerate(tl) if t.rec["status"] == "cancelled" or t.rec["flight_id"] not in kept
               or t.as_of(sent) != t.as_of(bought)]
    if touched and not is_covered(ctx, claim, tl, touched[0], bought):
        return 0, 0, None
    window = timedelta(hours=6 if ctx.international(tl) else 3)
    cancelled = [t for t in tl if t.rec["status"] == "cancelled"]
    tests = [bool(cancelled)]
    if new:
        booked = ctx.class_order.index(coupons[0]["cabin"])
        tests += [tl[0].departs(bought) - new[0][0].departs(sent) >= window,
                  new[-1][0].arrives(sent) - tl[-1].arrives(bought) >= window,
                  new[0][0].origin != tl[0].origin, new[-1][0].dest != tl[-1].dest,
                  len(new) - 1 > len(tl) - 1,
                  any(ctx.class_order.index(cabin) > booked for _, cabin in new)]
    qualifies = any(tests)
    answers = [e for e in log(claim, "passenger_reply") if instant(e["at"]) >= sent]
    answer = answers[-1] if answers else None
    took_it = bool(log(claim, "boarded")) or (answer is not None and answer["choice"] in
                                               {"accepted_offered_itinerary", "accepted_voucher"})
    if qualifies and not took_it:
        if answer is not None:
            moment = instant(answer["at"])                         # rejection
        elif new:
            moment = new[0][0].departs(sent)                       # offered flight departs without them
        elif final["voucher_offered"]:
            moment = cancelled[0].departs(bought)                  # day the cancelled flight was to depart
        else:
            moment = sent                                          # cancelled with nothing offered
        dates = [moment.date()]
        if asked_on(claim):
            dates.append(asked_on(claim))
        total = sum(c["fare_cents"] for c in coupons) + sum(a["fee_cents"] for a in claim["ancillary_purchases"])
        return 0, total, min(dates)
    if qualifies or took_it:
        return 0, unused_fees(claim), asked_on(claim)
    return 0, 0, None


def baggage(ctx, claim):
    tl = [ctx.flights[c["flight_id"]] for c in claim["ticket"]["coupons"]]
    kinds = {e["type"] for e in claim["events"]}
    if "mishandled_baggage_report" not in kinds:
        return 0, 0
    exemptions = {"passenger_did_not_reclaim_and_recheck_bag_at_first_us_entry_point",
                  "passenger_ended_travel_before_ticketed_final_destination",
                  "passenger_agreed_to_travel_without_bag_after_missing_check_in_time"}
    if kinds & exemptions:
        return 0, 0
    border = [t for t in tl if (t.origin in ctx.us) != (t.dest in ctx.us)]
    if border:
        longest = max(t.versions[-1][2] - t.versions[-1][1] for t in border)
        allowed = 30 * HOUR if longest > 12 * HOUR else 15 * HOUR
    else:
        allowed = 12 * HOUR
    delivered = log(claim, "bag_delivered")
    if delivered and instant(delivered[0]["at"]) - tl[-1].door <= allowed:
        return 0, 0
    sub = claim["ticket"]["bag_fee_subscription"]
    if sub and sub.get("subscribed"):
        return 0, sub["lowest_fee_charged_to_non_subscriber_same_status_and_cabin_cents"]
    tag = (delivered + log(claim, "bag_declared_lost"))[0]["bag_tag"]
    bags = {b["bag_tag"]: b for b in claim["checked_bags"]}
    if bags[tag]["fee_linked_to_this_bag_by_unique_identifier"]:
        return 0, bags[tag]["fee_cents"]
    return 0, max(b["fee_cents"] for b in bags.values())


def ancillary(ctx, claim):
    if any(e["through_fault_of_consumer"] for e in log(claim, "service_failure")):
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
        start = result[2] if len(result) > 2 else asked_on(claim)
        out[claim["claim_id"]] = {
            "compensation": f"{comp // 100}.{comp % 100:02d}",
            "refund": f"{refund // 100}.{refund % 100:02d}",
            "refund_due_date": ctx.deadline(start, claim["ticket"]["payment_method"]).isoformat()
            if refund else "none"}
    return out
