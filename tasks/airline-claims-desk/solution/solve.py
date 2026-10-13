#!/usr/bin/env python3
"""Reference solution: airline claims desk under 14 CFR Part 250 (oversales) and Part 260 (refunds)."""
import csv
import json
from datetime import date, datetime, timedelta
from pathlib import Path

DATA = Path("/app/data")
OUT = Path("/app/output")
CAP_200, CAP_400 = 107500, 215000          # 250.5(a)(2)/(3), (b)(2)/(3)


def t(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%MZ")


def mins(a, b):
    return int((t(b) - t(a)).total_seconds() // 60)


def load():
    j = lambda n: json.loads((DATA / n).read_text())  # noqa: E731
    flights = {f["flight_id"]: f for f in j("flights.json")}
    country = {k: v["country"] for k, v in j("airports.json").items()}
    holidays = set(j("federal_holidays.json")["observed_dates"])
    return j("claims.json"), flights, country, holidays


def due_date(trigger, method, holidays):
    d = date.fromisoformat(trigger)
    if method != "credit_card":                       # 260.2 prompt refund: 20 calendar days
        return d + timedelta(days=20)
    n = 0
    while n < 7:                                      # 7 business days for credit card purchases
        d += timedelta(days=1)
        if d.weekday() < 5 and d.isoformat() not in holidays:
            n += 1
    return d


def oversale(c, flights, country):
    cps, inc = c["ticket"]["coupons"], c["incident"]
    k = inc["denied_coupon"] - 1
    f = flights[inc["denied_flight_id"]]
    unused = sum(a["fee_cents"] for a in c["ancillary_purchases"] if not a["provided"])   # 250.5(f), 260.4
    if country[f["origin"]] != "US" or f["designed_passenger_seats"] < 30 or not f["scheduled_service"]:
        return 0, unused                                                                  # 250.2
    if not inc["held_confirmed_reserved_space"] or inc["volunteered"]:
        return 0, unused
    if not inc["complied_with_ticketing_check_in_and_acceptability_rules"]:
        return 0, 0                                                                       # 250.6(a)
    cause = inc["cause"]
    if cause.startswith("substitution_of_smaller_aircraft_required_for_operational"):
        return 0, unused                                                                  # 250.6(b)
    if cause.startswith("weight_balance") and f["designed_passenger_seats"] <= 60:
        return 0, unused
    if inc["seated_in_other_section_at_no_extra_charge"]:
        return 0, unused                                                                  # 250.6(c)
    end = k                                                                               # first stopover
    while end + 1 < len(cps) and mins(cps[end]["scheduled_arrival"], cps[end + 1]["scheduled_departure"]) <= 240:
        end += 1
    span = cps[k:end + 1]
    if c["ticket"]["award_ticket_paid_with_miles"]:
        fare = f["lowest_cash_fare_cents_by_cabin"][cps[k]["cabin"]]                    # 250.5(d)
    else:
        fare = sum(x["fare_cents"] for x in span)
    international = any(country[x["origin"]] != "US" or country[x["destination"]] != "US" for x in span)
    late = mins(span[-1]["scheduled_arrival"], inc["alternate_transportation"]["planned_arrival_at_time_arranged"])
    upper = 240 if international else 120
    if late <= 60:
        return 0, unused
    if late < upper:
        return min(2 * fare, CAP_200), unused
    return min(4 * fare, CAP_400), unused


def schedule_change(c, country):
    cps, inc = c["ticket"]["coupons"], c["incident"]
    intl = any(country[x["origin"]] != "US" or country[x["destination"]] != "US" for x in cps)
    limit = 360 if intl else 180
    ev = inc["event"]
    significant = ev == "cancelled" or ev in ("airport_change", "added_connection", "downgrade")
    if ev in ("retimed", "airport_change", "added_connection", "downgrade"):
        if -inc.get("new_departure_shift_minutes", 0) >= limit or inc.get("new_arrival_shift_minutes", 0) >= limit:
            significant = True
    if ev == "airport_change" and not (inc.get("new_origin_airport") or inc.get("new_destination_airport")):
        significant = False
    resp = inc["consumer_response"]
    unused = sum(a["fee_cents"] for a in c["ancillary_purchases"] if not a["provided"])
    if significant and resp in ("rejected_alternatives", "did_not_respond_and_flight_departed",
                                "did_not_respond_before_scheduled_departure", "requested_refund"):
        return 0, sum(x["fare_cents"] for x in cps) + sum(a["fee_cents"] for a in c["ancillary_purchases"])
    if resp in ("accepted_rebooking", "flew_on_changed_flight"):
        return 0, unused
    return 0, 0


def baggage(c, flights, country):
    inc, cps = c["incident"], c["ticket"]["coupons"]
    if not inc["mishandled_baggage_report_filed"]:
        return 0, 0
    ex = inc["exemption_facts"] or {}
    if any(ex.values()):
        return 0, 0
    intl_legs = [flights[x["flight_id"]] for x in cps if country[x["origin"]] != country[x["destination"]]
                 and "US" in (country[x["origin"]], country[x["destination"]])]
    if intl_legs:
        longest = max(mins(f["scheduled_departure"], f["scheduled_arrival"]) for f in intl_legs)
        limit = 1800 if longest > 720 else 900
    else:
        limit = 720
    if inc["status"] != "lost":
        if mins(inc["deplaning_opportunity_at_final_destination"], inc["delivered_or_picked_up_at"]) <= limit:
            return 0, 0
    bags = c["checked_bags"]
    sub = inc.get("bag_fee_subscription") or {}
    if sub.get("subscribed"):
        return 0, sub["lowest_fee_charged_to_non_subscriber_same_status_and_cabin_cents"]
    bag = next(b for b in bags if b["bag_tag"] == inc["bag_tag"])
    if bag["fee_linked_to_this_bag_by_unique_identifier"]:
        return 0, bag["fee_cents"]
    return 0, max(b["fee_cents"] for b in bags)


def service(c):
    if c["incident"]["service_failure_through_fault_of_consumer"]:
        return 0, 0
    return 0, sum(a["fee_cents"] for a in c["ancillary_purchases"] if not a["provided"])


def main():
    claims, flights, country, holidays = load()
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "claim_decisions.csv", "w", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(["claim_id", "compensation", "refund", "refund_due_date"])
        for c in claims:
            kind = c["claim_type"]
            if kind == "oversale":
                comp, ref = oversale(c, flights, country)
            elif kind == "schedule_change_or_cancellation":
                comp, ref = schedule_change(c, country)
            elif kind == "baggage":
                comp, ref = baggage(c, flights, country)
            else:
                comp, ref = service(c)
            dd = due_date(c["refund_trigger_date"], c["ticket"]["payment_method"], holidays).isoformat() if ref else "none"
            w.writerow([c["claim_id"], f"{comp / 100:.2f}", f"{ref / 100:.2f}", dd])


if __name__ == "__main__":
    main()
