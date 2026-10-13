#!/usr/bin/env python3
"""Reference solution: airline claims desk under 14 CFR Part 250 (oversales) and Part 260 (refunds).

Every time is turned into whole minutes since 1970-01-01 UTC on load: schedule and door times are local wall
times at their airport, everything ending in Z is UTC.
"""
import csv
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

DATA = Path("/app/data")
OUT = Path("/app/output")
CAP_200, CAP_400 = 107500, 215000          # 250.5(a)(2)/(3), (b)(2)/(3)
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def j(name):
    return json.loads((DATA / name).read_text())


AIRPORTS, US, RANK, HOLIDAYS, FLIGHTS = {}, set(), {}, set(), {}


def utc(s):
    return int((datetime.strptime(s, "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc) - EPOCH).total_seconds() // 60)


def wall(s, airport):
    t = datetime.strptime(s, "%Y-%m-%dT%H:%M").replace(tzinfo=ZoneInfo(AIRPORTS[airport]["time_zone"]))
    return int((t - EPOCH).total_seconds() // 60)


def utc_date(m):
    return (EPOCH + timedelta(minutes=m)).date()


class Flight:
    def __init__(self, f):
        self.id, self.a, self.b = f["flight_id"], f["origin"], f["destination"]
        self.seats, self.scheduled, self.low = f["designed_passenger_seats"], f["scheduled_service"], \
            f["lowest_cash_fare_cents_by_cabin"]
        self.versions = [(utc(v["recorded_at"]), wall(v["departure"], self.a), wall(v["arrival"], self.b))
                         for v in f["schedule"]]
        self.cancelled = f["status"] == "cancelled"
        self.door = wall(f["door_opened_at_gate"], self.b) if f["door_opened_at_gate"] else None

    def at(self, m):
        """(departure, arrival) as scheduled at minute m."""
        v = [x for x in self.versions if x[0] <= m]
        return v[-1][1], v[-1][2]


def load():
    AIRPORTS.update(j("airports.json"))
    US.update(k for k, v in AIRPORTS.items() if v["country"] == "US")
    RANK.update({c: i for i, c in enumerate(j("carrier.json")["classes_of_service_highest_first"])})
    HOLIDAYS.update(j("federal_holidays.json")["observed_dates"])
    FLIGHTS.update({f["flight_id"]: Flight(f) for f in j("flights.json")})


def intl(flights):
    return any(f.a not in US or f.b not in US for f in flights)


def due_date(trigger, method):
    d = trigger
    if method != "credit_card":                       # prompt refund: 20 calendar days
        return d + timedelta(days=20)
    n = 0
    while n < 7:                                      # 7 business days for credit card purchases
        d += timedelta(days=1)
        if d.weekday() < 5 and d.isoformat() not in HOLIDAYS:
            n += 1
    return d


def events(c, kind):
    return [e for e in c["events"] if e["type"] == kind]


def unused_fees(c):
    return sum(a["fee_cents"] for a in c["ancillary_purchases"] if not a["provided"])


def requested(c):
    return utc_date(utc(c["refund_requested_at"])) if c["refund_requested_at"] else None


def oversale(c):
    cps = c["ticket"]["coupons"]
    legs = [FLIGHTS[x["flight_id"]] for x in cps]
    unused = unused_fees(c)
    vol = events(c, "volunteer_offer_accepted")
    den = (vol or events(c, "denied_boarding"))[0]
    gate = utc(den["at"])
    k = next(i for i, x in enumerate(cps) if x["flight_id"] == den["flight_id"])
    f = legs[k]
    if f.a not in US or f.seats < 30 or not f.scheduled:                                 # 250.2
        return 0, unused
    if vol:                                                                              # 250.2b volunteer
        return 0, unused
    dep = f.at(gate)[0]
    close = 60 if f.b not in US else 45                                                  # contract of carriage
    if utc(events(c, "checked_in")[0]["at"]) > dep - close:                              # 250.6(a)
        return 0, 0
    if den["reason"] == "aircraft_substitution" and den["required_for_operational_or_safety_reasons"]:
        return 0, unused                                                                 # 250.6(b)
    if den["reason"] == "weight_balance_restriction" and den["required_for_operational_or_safety_reasons"] \
            and f.seats <= 60:
        return 0, unused
    if any(e["extra_charge_cents"] == 0 for e in events(c, "seat_offered_in_other_cabin")):
        return 0, unused                                                                 # 250.6(c)
    end = k                                                                              # first stopover (250.1)
    while end + 1 < len(legs) and legs[end + 1].at(gate)[0] - legs[end].at(gate)[1] <= 240:
        end += 1
    if c["ticket"]["award_ticket_paid_with_miles"]:
        fare = f.low[cps[k]["cabin"]]                                                    # 250.5(d)
    else:
        fare = sum(x["fare_cents"] for x in cps[k:end + 1])
    upper = 240 if intl(legs) else 120                                                   # 250.5(b) vs (a)
    alt = events(c, "alternate_transportation_arranged")
    if not alt:
        return min(4 * fare, CAP_400), unused
    when = utc(alt[0]["at"])
    late = FLIGHTS[alt[0]["itinerary"][-1]].at(when)[1] - legs[end].at(gate)[1]         # planned when arranged
    if late <= 60:
        return 0, unused
    if late < upper:
        return min(2 * fare, CAP_200), unused
    return min(4 * fare, CAP_400), unused


def covered(c, legs, k):
    """260.2 covered flight: to, from or within the U.S., or a foreign-to-foreign segment joined to a U.S. one
    by stopovers of 24 hours or less (bags through, passenger airside, one ticket, one carrier)."""
    if legs[k].a in US or legs[k].b in US:
        return True
    bought = utc(c["ticket"]["purchased_at"])
    conns = {tuple(x["between_coupons"]): x for x in c["ticket"]["connections"]}

    def brief(i):
        x = conns[(i + 1, i + 2)]
        gap = legs[i + 1].at(bought)[0] - legs[i].at(bought)[1]
        return gap <= 1440 and x["bags_checked_through"] and not x["passenger_left_airport"]

    i = k
    while i > 0 and brief(i - 1):
        i -= 1
        if legs[i].a in US:
            return True
    i = k
    while i + 1 < len(legs) and brief(i):
        i += 1
        if legs[i].b in US:
            return True
    return False


def schedule_change(c):
    """Returns (compensation, refund, day the due date runs from)."""
    cps = c["ticket"]["coupons"]
    legs = [FLIGHTS[x["flight_id"]] for x in cps]
    bought = utc(c["ticket"]["purchased_at"])
    notice = events(c, "itinerary_change_notice")[-1]
    at = utc(notice["at"])
    offered = [(FLIGHTS[x["flight_id"]], x["cabin"]) for x in notice["offered_itinerary"]] \
        if notice["offered_itinerary"] is not None else None
    kept = {f.id for f, _ in offered or []}
    cancelled = [f for f in legs if f.cancelled]
    affected = [i for i, f in enumerate(legs) if f.cancelled or f.id not in kept or f.at(at) != f.at(bought)]
    if affected and not covered(c, legs, affected[0]):
        return 0, 0, None
    limit = 360 if intl(legs) else 180                                                   # 260.2 significant
    significant = bool(cancelled)
    if offered:
        o_dep, o_arr = legs[0].at(bought)[0], legs[-1].at(bought)[1]
        n_dep, n_arr = offered[0][0].at(at)[0], offered[-1][0].at(at)[1]
        cabin = RANK[cps[0]["cabin"]]
        significant = significant or o_dep - n_dep >= limit or n_arr - o_arr >= limit \
            or offered[0][0].a != legs[0].a or offered[-1][0].b != legs[-1].b \
            or len(offered) > len(legs) or any(RANK[cb] > cabin for _, cb in offered)
    replies = [e for e in events(c, "passenger_reply") if utc(e["at"]) >= at]
    choice = replies[-1]["choice"] if replies else None
    accepted = choice in ("accepted_offered_itinerary", "accepted_voucher") or bool(events(c, "boarded"))
    asked = requested(c)
    if significant and not accepted and (choice == "declined_offer" or choice is None):
        if choice == "declined_offer":
            start = utc_date(utc(replies[-1]["at"]))                                     # 260.6(a)(2)(ii)
        elif offered:
            start = utc_date(offered[0][0].at(at)[0])                                    # (iii)(A)
        elif notice["voucher_offered"]:
            start = utc_date(cancelled[0].at(bought)[0])                                 # (iii)(B)
        else:
            start = utc_date(at)                                                         # (i)
        if asked and asked < start:
            start = asked
        total = sum(x["fare_cents"] for x in cps) + sum(a["fee_cents"] for a in c["ancillary_purchases"])
        return 0, total, start
    if significant or accepted:
        return 0, unused_fees(c), asked                                                  # 260.4
    return 0, 0, None                                                                    # declined a minor change


def baggage(c):
    cps = c["ticket"]["coupons"]
    legs = [FLIGHTS[x["flight_id"]] for x in cps]
    if not events(c, "mishandled_baggage_report"):                                       # 260.5(b)
        return 0, 0
    if any(e["type"].startswith("passenger_") for e in c["events"]):                     # 260.5(f)
        return 0, 0
    cross = [f for f in legs if (f.a in US) != (f.b in US)]
    if cross:
        longest = max(f.versions[-1][2] - f.versions[-1][1] for f in cross)
        limit = 1800 if longest > 720 else 900
    else:
        limit = 720
    delivered = events(c, "bag_delivered")
    if delivered and utc(delivered[0]["at"]) - legs[-1].door <= limit:                   # 260.5(a)
        return 0, 0
    sub = c["ticket"]["bag_fee_subscription"] or {}
    if sub.get("subscribed"):
        return 0, sub["lowest_fee_charged_to_non_subscriber_same_status_and_cabin_cents"]
    tag = (delivered or events(c, "bag_declared_lost"))[0]["bag_tag"]
    bag = next(b for b in c["checked_bags"] if b["bag_tag"] == tag)
    if bag["fee_linked_to_this_bag_by_unique_identifier"]:
        return 0, bag["fee_cents"]
    return 0, max(b["fee_cents"] for b in c["checked_bags"])


def service(c):
    if any(e["through_fault_of_consumer"] for e in events(c, "service_failure")):
        return 0, 0
    return 0, unused_fees(c)


def main():
    load()
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "claim_decisions.csv", "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["claim_id", "compensation", "refund", "refund_due_date"])
        for c in j("claims.json"):
            kind = c["claim_type"]
            start = requested(c)
            if kind == "oversale":
                comp, ref = oversale(c)
            elif kind == "schedule_change_or_cancellation":
                comp, ref, start = schedule_change(c)
            elif kind == "baggage":
                comp, ref = baggage(c)
            else:
                comp, ref = service(c)
            dd = due_date(start, c["ticket"]["payment_method"]).isoformat() if ref else "none"
            w.writerow([c["claim_id"], f"{comp / 100:.2f}", f"{ref / 100:.2f}", dd])


if __name__ == "__main__":
    main()
