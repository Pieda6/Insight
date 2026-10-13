#!/usr/bin/env python3
"""Generate the airline-claims-desk inputs (dev only, never shipped).

Lakeshore Air (fictional U.S. carrier, merchant of record for every ticket and fee) claim queue:
oversales (14 CFR 250), cancellations and schedule changes (14 CFR 260.6), delayed/lost bags
(260.5) and ancillary services not provided (260.4). Planted claims carry a hand-worked expected
answer (tests/golden.json); filler claims are random.
"""
import json
import random
import shutil
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "tasks" / "airline-claims-desk"
ENV, TST = ROOT / "environment" / "data", ROOT / "tests" / "data"
rng = random.Random(25026)
UTC = timezone.utc

AIRPORTS = {"ORD": ("Chicago", "US"), "LGA": ("New York", "US"), "DFW": ("Dallas", "US"),
            "DEN": ("Denver", "US"), "MSP": ("Minneapolis", "US"), "BOS": ("Boston", "US"),
            "ATL": ("Atlanta", "US"), "SFO": ("San Francisco", "US"), "SEA": ("Seattle", "US"),
            "MDW": ("Chicago", "US"), "EWR": ("Newark", "US"), "MKE": ("Milwaukee", "US"),
            "YYZ": ("Toronto", "CA"), "CUN": ("Cancun", "MX"), "LHR": ("London", "GB"),
            "NRT": ("Tokyo", "JP"), "FRA": ("Frankfurt", "DE")}
ZONES = {"ORD": "America/Chicago", "MDW": "America/Chicago", "MKE": "America/Chicago", "DFW": "America/Chicago",
         "MSP": "America/Chicago", "LGA": "America/New_York", "EWR": "America/New_York", "BOS": "America/New_York",
         "ATL": "America/New_York", "DEN": "America/Denver", "SFO": "America/Los_Angeles",
         "SEA": "America/Los_Angeles", "YYZ": "America/Toronto", "CUN": "America/Cancun", "LHR": "Europe/London",
         "NRT": "Asia/Tokyo", "FRA": "Europe/Berlin"}
AMBIGUOUS = []


def local(text, airport):
    """UTC 'YYYY-MM-DDTHH:MMZ' -> local wall time at the airport 'YYYY-MM-DDTHH:MM' (as an airline publishes
    it). Records any wall time that falls in a repeated daylight-saving hour, which the data must not contain."""
    from zoneinfo import ZoneInfo
    z = ZoneInfo(ZONES[airport])
    t = datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(z)
    wall = t.replace(tzinfo=None)
    if wall.replace(tzinfo=z, fold=0).utcoffset() != wall.replace(tzinfo=z, fold=1).utcoffset():
        AMBIGUOUS.append((text, airport))
    return wall.strftime("%Y-%m-%dT%H:%M")


def repeated_hour(text, airport):
    from zoneinfo import ZoneInfo
    z = ZoneInfo(ZONES[airport])
    wall = datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(z).replace(tzinfo=None)
    return wall.replace(tzinfo=z, fold=0).utcoffset() != wall.replace(tzinfo=z, fold=1).utcoffset()


def schedule_times(c):
    """Every (UTC time, airport) pair that becomes a local wall time in the published data."""
    cps, inc = c["ticket"]["coupons"], c["incident"]
    out = []
    for k in cps:
        out += [(k["scheduled_departure"], k["origin"]), (k["scheduled_arrival"], k["destination"])]
    if c["claim_type"] == "oversale":
        alt = inc["alternate_transportation"]
        out.append((alt["planned_arrival_at_time_arranged"], alt["arrival_airport"]))
    if c["claim_type"] == "schedule_change_or_cancellation" and "new_departure_shift_minutes" in inc:
        k = cps[inc["affected_coupon"] - 1]
        dep = datetime.fromisoformat(k["scheduled_departure"].replace("Z", "+00:00"))
        arr = datetime.fromisoformat(k["scheduled_arrival"].replace("Z", "+00:00"))
        out.append((iso(dep + timedelta(minutes=inc["new_departure_shift_minutes"])),
                    inc.get("new_origin_airport") or k["origin"]))
        out.append((iso(arr + timedelta(minutes=inc["new_arrival_shift_minutes"])),
                    inc.get("new_destination_airport") or k["destination"]))
    return out


BLOCK = {("ORD", "LGA"): 135, ("ORD", "DFW"): 150, ("ORD", "DEN"): 160, ("ORD", "MSP"): 85,
         ("ORD", "BOS"): 140, ("ORD", "ATL"): 120, ("ORD", "SFO"): 280, ("ORD", "SEA"): 270,
         ("ORD", "YYZ"): 90, ("ORD", "CUN"): 230, ("ORD", "LHR"): 485, ("ORD", "NRT"): 790,
         ("ORD", "FRA"): 520, ("DEN", "SFO"): 150, ("LGA", "BOS"): 75, ("DFW", "CUN"): 150,
         ("ORD", "MKE"): 45, ("SEA", "NRT"): 610, ("ORD", "EWR"): 130, ("LHR", "FRA"): 95}
AIRCRAFT = [("Airbus A321neo", 196), ("Boeing 737-800", 166), ("Embraer E175", 76),
            ("Boeing 787-9", 290), ("Embraer E145", 50), ("Beechcraft 1900D", 19), ("Airbus A320", 150)]
NAMES = ["A. Okafor", "B. Lindqvist", "C. Ramirez", "D. Chen", "E. Novak", "F. Haddad", "G. Moreau",
         "H. Tanaka", "I. Kowalski", "J. Mensah", "K. Patel", "L. Rossi", "M. Byrne", "N. Silva",
         "O. Ahmed", "P. Schultz", "Q. Nguyen", "R. Dubois", "S. Kim", "T. Oyelaran"]
PAY = ["credit_card", "credit_card", "credit_card", "debit_card", "cash", "check"]
HOLIDAYS = ["2026-10-12", "2026-11-11", "2026-11-26", "2026-12-25", "2027-01-01", "2027-01-18",
            "2027-02-15"]


def block(a, b):
    return BLOCK.get((a, b)) or BLOCK[(b, a)]


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%MZ")


def foreign(code):
    return AIRPORTS[code][1] != "US"


def due(trigger, method):
    d = date.fromisoformat(trigger)
    if method != "credit_card":
        return (d + timedelta(days=20)).isoformat()
    n = 0
    while n < 7:
        d += timedelta(days=1)
        if d.weekday() < 5 and d.isoformat() not in HOLIDAYS:
            n += 1
    return d.isoformat()


class W:
    def __init__(self):
        self.flights, self.claims, self.golden, self.tags = {}, [], {}, {}
        self.n_claim = 0
        self.n_flight = 0

    def flight(self, a, b, dep, aircraft=None, low=None):
        self.n_flight += 1
        ac = aircraft or rng.choice(AIRCRAFT[:4] + [AIRCRAFT[6]])
        fid = f"LS{1000 + self.n_flight}-{dep.strftime('%m%d')}"
        arr = dep + timedelta(minutes=block(a, b))
        low = low or {"economy": rng.randrange(8900, 42000, 100), "first": rng.randrange(45000, 120000, 100)}
        self.flights[fid] = {"flight_id": fid, "flight_number": f"LS{1000 + self.n_flight}",
                             "origin": a, "destination": b, "scheduled_departure": iso(dep),
                             "scheduled_arrival": iso(arr), "aircraft": ac[0], "designed_passenger_seats": ac[1],
                             "scheduled_service": True, "lowest_cash_fare_cents_by_cabin": low}
        return fid, dep, arr

    def ticket(self, legs, cabin="economy", pay=None, zero=False, fares=None):
        """legs: list of (a, b, dep_datetime[, aircraft]) -> coupons."""
        coupons = []
        for i, leg in enumerate(legs):
            a, b, dep = leg[:3]
            fid, d, ar = self.flight(a, b, dep, leg[3] if len(leg) > 3 else None)
            fare = 0 if zero else (fares[i] if fares else rng.randrange(7900, 39900, 100))
            coupons.append({"coupon": i + 1, "flight_id": fid, "origin": a, "destination": b,
                            "scheduled_departure": iso(d), "scheduled_arrival": iso(ar),
                            "cabin": cabin, "fare_cents": fare})
        conns = [{"airport": coupons[i]["destination"], "between_coupons": [i + 1, i + 2],
                  "bags_checked_through": True, "passenger_left_airport": False}
                 for i in range(len(coupons) - 1)]
        return {"ticket_number": f"016{rng.randrange(10**9, 10**10)}", "payment_method": pay or rng.choice(PAY),
                "award_ticket_paid_with_miles": zero, "cabin": cabin, "coupons": coupons, "connections": conns}

    def add(self, ctype, ticket, incident, ancillary, tags, expected=None, request_date=None, bags=None,
            count_from=None):
        """count_from: the hand-worked day the refund due date is counted from (defaults to the request)."""
        self.n_claim += 1
        cid = f"CL{self.n_claim:04d}"
        c = {"claim_id": cid, "claim_type": ctype, "passenger": rng.choice(NAMES), "ticket": ticket,
             "ancillary_purchases": ancillary, "checked_bags": bags or [], "incident": incident,
             "refund_requested_on": request_date}
        self.claims.append(c)
        self.tags[cid] = tags
        if expected is not None:
            comp, ref = expected
            base = count_from or request_date
            self.golden[cid] = {"compensation": f"{comp / 100:.2f}", "refund": f"{ref / 100:.2f}",
                                "refund_due_date": due(base, ticket["payment_method"]) if ref else "none"}
        return cid


def bag_limit(w, ticket):
    """Minutes allowed before a checked bag is significantly delayed (260.2), from the itinerary."""
    legs = [c for c in ticket["coupons"] if foreign(c["origin"]) != foreign(c["destination"])]
    if not legs:
        return 720
    return 1800 if max(block(c["origin"], c["destination"]) for c in legs) > 720 else 900


def asked_on(w, ticket, arr, delay, lost):
    """The passenger asks for the bag-fee refund on the day the bag became significantly delayed (or lost),
    so the request date and the day the refund fell due are the same; otherwise on delivery."""
    lim = bag_limit(w, ticket)
    if lost or delay > lim:
        return (arr + timedelta(minutes=lim + 1)).date().isoformat()
    return (arr + timedelta(minutes=delay)).date().isoformat()


def T(day, h, m=0):
    return datetime(2026, 10, day, h, m, tzinfo=UTC) if day <= 31 else \
        datetime(2026, 11, day - 31, h, m, tzinfo=UTC)


def anc(service, fee, coupon, provided):
    return {"service": service, "fee_cents": fee, "coupon": coupon, "provided": provided}


def oversale(w, legs, db_coupon, alt_delay_min, tags, cabin="economy", zero=False, fares=None,
             volunteer=False, checkin_ok=True, confirmed=True, reason="oversale", other_section=None,
             ancillary=(), expected=None, pay=None, arrival_point=None):
    t = w.ticket(legs, cabin, pay=pay, zero=zero, fares=fares)
    cps = t["coupons"]
    # end of the compensation span: first stopover (> 4 h) or destination
    end = db_coupon - 1
    while end + 1 < len(cps):
        gap = (datetime.fromisoformat(cps[end + 1]["scheduled_departure"].replace("Z", "+00:00")) -
               datetime.fromisoformat(cps[end]["scheduled_arrival"].replace("Z", "+00:00")))
        if gap > timedelta(hours=4):
            break
        end += 1
    planned = datetime.fromisoformat(cps[end]["scheduled_arrival"].replace("Z", "+00:00"))
    inc = {"denied_flight_id": cps[db_coupon - 1]["flight_id"], "denied_coupon": db_coupon,
           "held_confirmed_reserved_space": confirmed, "volunteered": volunteer,
           "complied_with_ticketing_check_in_and_acceptability_rules": checkin_ok,
           "cause": reason, "seated_in_other_section_at_no_extra_charge": other_section,
           "alternate_transportation": {"arrival_airport": arrival_point or cps[end]["destination"],
                                        "planned_arrival_at_time_arranged": iso(planned + timedelta(minutes=alt_delay_min)),
                                        "arranged_at": cps[db_coupon - 1]["scheduled_departure"]}}
    trigger = cps[db_coupon - 1]["scheduled_departure"][:10]
    return w.add("oversale", t, inc, list(ancillary), tags, expected, trigger)


def planted(w):
    # ---------------- oversale: bands, caps, fare base ----------------------------------------
    D = lambda d, h: T(d, h)  # noqa: E731
    oversale(w, [("ORD", "LGA", D(5, 13))], 1, 60, ["db-band", "domestic"], fares=[24900], expected=(0, 0))
    oversale(w, [("ORD", "LGA", D(5, 14))], 1, 61, ["db-band", "domestic"], fares=[24900], expected=(49800, 0))
    oversale(w, [("ORD", "LGA", D(5, 15))], 1, 119, ["db-band", "domestic"], fares=[24900], expected=(49800, 0))
    oversale(w, [("ORD", "LGA", D(5, 16))], 1, 120, ["db-band", "domestic"], fares=[24900], expected=(99600, 0))
    oversale(w, [("ORD", "DEN", D(6, 13))], 1, 95, ["db-band", "db-cap", "domestic"], fares=[61900],
             expected=(107500, 0))
    oversale(w, [("ORD", "DEN", D(6, 14))], 1, 300, ["db-band", "db-cap", "domestic"], fares=[61900],
             expected=(215000, 0))
    oversale(w, [("ORD", "LHR", D(7, 22), AIRCRAFT[3])], 1, 200, ["db-band", "international"], fares=[48700],
             expected=(97400, 0))
    oversale(w, [("ORD", "LHR", D(8, 22), AIRCRAFT[3])], 1, 240, ["db-band", "international"], fares=[48700],
             expected=(194800, 0))
    oversale(w, [("ORD", "YYZ", D(9, 12))], 1, 150, ["db-band", "international"], fares=[21300],
             expected=(42600, 0))
    # connecting itinerary: fare through the destination, measured at the destination
    oversale(w, [("MSP", "ORD", D(10, 12)), ("ORD", "LHR", D(10, 15, ), AIRCRAFT[3])], 1, 210,
             ["db-fare-base", "international"], fares=[15900, 31200], expected=(94200, 0))
    # stopover > 4 h: fare only to the first stopover; domestic band applies
    oversale(w, [("ORD", "DEN", D(11, 13)), ("DEN", "SFO", D(12, 15))], 1, 130, ["db-fare-base", "stopover"],
             fares=[18800, 14200], expected=(75200, 0))
    # exactly 4 h connection is not a stopover
    oversale(w, [("ORD", "DEN", D(13, 12)), ("DEN", "SFO", T(13, 12) + timedelta(minutes=160 + 240))], 1, 70,
             ["db-fare-base", "stopover"], fares=[18800, 14200], expected=(66000, 0))
    # round trip: the return is not part of the fare to destination
    oversale(w, [("ORD", "BOS", D(14, 13)), ("BOS", "ORD", D(18, 20))], 1, 100, ["db-fare-base", "round-trip"],
             fares=[17600, 17600], expected=(35200, 0))
    # award ticket: lowest cash fare in the same cabin on that flight
    cid = oversale(w, [("ORD", "ATL", D(15, 13))], 1, 140, ["db-fare-base", "zero-fare"], zero=True,
                   expected=None)
    f = w.flights[w.claims[-1]["ticket"]["coupons"][0]["flight_id"]]
    f["lowest_cash_fare_cents_by_cabin"]["economy"] = 13900
    w.golden[cid] = {"compensation": f"{4 * 13900 / 100:.2f}", "refund": "0.00", "refund_due_date": "none"}
    # ---------------- oversale: exceptions and applicability ------------------------------------
    oversale(w, [("ORD", "LGA", D(16, 13))], 1, 300, ["db-exception", "volunteer"], fares=[24900],
             volunteer=True, expected=(0, 0))
    oversale(w, [("ORD", "LGA", D(16, 15))], 1, 300, ["db-exception", "check-in"], fares=[24900],
             checkin_ok=False, expected=(0, 0))
    oversale(w, [("ORD", "LGA", D(16, 17))], 1, 300, ["db-exception", "standby"], fares=[24900],
             confirmed=False, expected=(0, 0))
    oversale(w, [("ORD", "LGA", D(17, 13))], 1, 300, ["db-exception", "equipment"], fares=[24900],
             reason="substitution_of_smaller_aircraft_required_for_operational_or_safety_reasons", expected=(0, 0))
    oversale(w, [("ORD", "LGA", D(17, 15))], 1, 300, ["db-exception", "equipment"], fares=[24900],
             reason="substitution_of_smaller_aircraft_for_commercial_reasons", expected=(99600, 0))
    oversale(w, [("ORD", "MSP", D(18, 13), AIRCRAFT[4])], 1, 300, ["db-exception", "weight-balance"],
             fares=[15900], reason="weight_balance_restriction_required_for_operational_or_safety_reasons",
             expected=(0, 0))
    oversale(w, [("ORD", "MSP", D(18, 15), AIRCRAFT[2])], 1, 300, ["db-exception", "weight-balance"],
             fares=[15900], reason="weight_balance_restriction_required_for_operational_or_safety_reasons",
             expected=(63600, 0))
    oversale(w, [("ORD", "LGA", D(19, 13))], 1, 300, ["db-exception", "other-section"], fares=[24900],
             other_section="first", expected=(0, 0))
    oversale(w, [("ORD", "MKE", D(19, 15), AIRCRAFT[5])], 1, 300, ["db-applicability", "small-aircraft"],
             fares=[9900], expected=(0, 0))
    oversale(w, [("CUN", "ORD", D(20, 18))], 1, 300, ["db-applicability", "foreign-origin"], fares=[33900],
             expected=(0, 0))
    # ---------------- oversale: unused ancillary fees (250.5(f) / 260.4) ------------------------
    oversale(w, [("ORD", "SFO", D(21, 14))], 1, 150, ["db-ancillary"], fares=[29900], pay="credit_card",
             ancillary=[anc("advance_seat_selection", 4500, 1, False), anc("wifi", 1200, 1, True),
                        anc("first_checked_bag", 3500, 1, True)], expected=(119600, 4500))
    oversale(w, [("ORD", "SFO", D(22, 14))], 1, 40, ["db-ancillary", "volunteer"], fares=[29900],
             pay="debit_card", volunteer=True,
             ancillary=[anc("advance_seat_selection", 4500, 1, False), anc("priority_boarding", 2500, 1, False)],
             expected=(0, 7000))

    # ---------------- schedule changes and cancellations (260.6) ---------------------------------
    def change(legs, inc, response, tags, ancillary=(), expected=None, pay=None, fares=None, cabin="economy",
               affected=1, notice_days=3, respond_hours=20, requested=None, count_from=None):
        """Notice goes out notice_days before the affected flight; a response comes respond_hours later.
        requested: date the passenger asked for a refund (None = never asked). count_from: hand-worked
        day the due date runs from (for planted claims with a refund)."""
        t = w.ticket(legs, cabin, pay=pay, fares=fares)
        dep = datetime.fromisoformat(t["coupons"][affected - 1]["scheduled_departure"].replace("Z", "+00:00"))
        notice = dep - timedelta(days=notice_days, hours=1)
        answered = response not in ("did_not_respond_and_flight_departed", "did_not_respond_before_scheduled_departure",
                                    "flew_on_changed_flight")
        inc = dict(inc, affected_coupon=affected, carrier_notice_at=iso(notice), consumer_response=response,
                   consumer_response_at=iso(notice + timedelta(hours=respond_hours)) if answered else None)
        if requested == "notice":
            requested = notice.date().isoformat()
            count_from = count_from and requested
        if response == "requested_refund" and requested is None:
            requested = (notice + timedelta(hours=respond_hours)).date().isoformat()
        cid = w.add("schedule_change_or_cancellation", t, inc, list(ancillary), tags, None, requested)
        if expected is not None:
            comp, ref = expected
            w.golden[cid] = {"compensation": f"{comp / 100:.2f}", "refund": f"{ref / 100:.2f}",
                             "refund_due_date": due(count_from, t["payment_method"]) if ref else "none"}
        return cid

    def resp_day(day, h):        # the date a response sent respond_hours=20 after a notice 3 days + 1 h before
        return (T(day, h) - timedelta(days=3, hours=1) + timedelta(hours=20)).date().isoformat()

    fare = [21800]
    a1 = [anc("advance_seat_selection", 3900, 1, False), anc("first_checked_bag", 3500, 1, False)]
    change([("ORD", "LGA", T(23, 13))], {"event": "cancelled", "alternative_offered": "rebooking_on_later_flight"},
           "rejected_alternatives", ["sc-cancel"], a1, (0, 21800 + 7400), fares=fare, count_from=resp_day(23, 13))
    change([("ORD", "LGA", T(23, 15))], {"event": "cancelled", "alternative_offered": "rebooking_on_later_flight"},
           "accepted_rebooking", ["sc-cancel", "sc-accepted"],
           [anc("advance_seat_selection", 3900, 1, False), anc("first_checked_bag", 3500, 1, True)],
           (0, 3900), fares=fare, requested="notice", count_from="2026-10-20")
    # 260.4: an unused prepaid extra on a cancelled flight is refunded even when a voucher is accepted
    change([("ORD", "LGA", T(23, 17))], {"event": "cancelled", "alternative_offered": "travel_voucher"},
           "accepted_voucher_affirmatively", ["sc-cancel", "sc-voucher"], a1, (0, 7400), fares=fare,
           requested="notice", count_from="2026-10-20")
    change([("ORD", "LGA", T(24, 13))], {"event": "cancelled", "alternative_offered": "travel_voucher"},
           "did_not_respond_before_scheduled_departure", ["sc-cancel", "sc-voucher"], a1, (0, 29200), fares=fare,
           count_from="2026-10-24")
    change([("ORD", "LGA", T(24, 15))], {"event": "cancelled", "alternative_offered": "none"},
           "requested_refund", ["sc-cancel", "due-date"], [], (0, 21800), fares=fare, count_from="2026-10-21")
    change([("ORD", "LGA", T(25, 13))], {"event": "retimed", "new_departure_shift_minutes": 0,
                                         "new_arrival_shift_minutes": 180},
           "rejected_alternatives", ["sc-delay", "sc-threshold", "domestic"], [], (0, 21800), fares=fare,
           count_from=resp_day(25, 13))
    change([("ORD", "LGA", T(25, 15))], {"event": "retimed", "new_departure_shift_minutes": 0,
                                         "new_arrival_shift_minutes": 179},
           "rejected_alternatives", ["sc-delay", "sc-threshold", "domestic"], [], (0, 0), fares=fare)
    # declining a change that is not significant: the unused extra was the passenger's own choice
    change([("ORD", "LGA", T(25, 17))], {"event": "retimed", "new_departure_shift_minutes": 0,
                                         "new_arrival_shift_minutes": 120},
           "rejected_alternatives", ["sc-delay", "sc-not-significant"], [anc("first_checked_bag", 3500, 1, False)],
           (0, 0), fares=fare, requested="2026-10-24")
    change([("ORD", "LGA", T(26, 13))], {"event": "retimed", "new_departure_shift_minutes": -180,
                                         "new_arrival_shift_minutes": -180},
           "rejected_alternatives", ["sc-earlier", "sc-threshold", "domestic"], [], (0, 21800), fares=fare,
           count_from=resp_day(26, 13))
    change([("ORD", "LHR", T(26, 22), AIRCRAFT[3])], {"event": "retimed", "new_departure_shift_minutes": 0,
                                                       "new_arrival_shift_minutes": 300},
           "rejected_alternatives", ["sc-delay", "sc-threshold", "international"], [], (0, 0), fares=[55600])
    change([("ORD", "LHR", T(27, 22), AIRCRAFT[3])], {"event": "retimed", "new_departure_shift_minutes": 0,
                                                       "new_arrival_shift_minutes": 360},
           "rejected_alternatives", ["sc-delay", "sc-threshold", "international"], [], (0, 55600), fares=[55600],
           count_from=resp_day(27, 22))
    change([("ORD", "YYZ", T(27, 13))], {"event": "retimed", "new_departure_shift_minutes": 240,
                                         "new_arrival_shift_minutes": 240},
           "rejected_alternatives", ["sc-delay", "sc-threshold", "international"], [], (0, 0), fares=[19900])
    change([("ORD", "LGA", T(28, 13))], {"event": "airport_change", "new_destination_airport": "EWR",
                                         "new_departure_shift_minutes": 0, "new_arrival_shift_minutes": 20},
           "rejected_alternatives", ["sc-airport"], [], (0, 21800), fares=fare, count_from=resp_day(28, 13))
    change([("ORD", "LGA", T(28, 15))], {"event": "airport_change", "new_origin_airport": "MDW",
                                         "new_departure_shift_minutes": 0, "new_arrival_shift_minutes": 0},
           "rejected_alternatives", ["sc-airport"], [], (0, 21800), fares=fare, count_from=resp_day(28, 15))
    change([("ORD", "BOS", T(29, 13))], {"event": "added_connection", "new_connection_points": 1,
                                         "new_departure_shift_minutes": 0, "new_arrival_shift_minutes": 95},
           "rejected_alternatives", ["sc-connection"], [], (0, 18400), fares=[18400], count_from=resp_day(29, 13))
    change([("ORD", "BOS", T(29, 15))], {"event": "downgrade", "new_cabin": "economy",
                                         "new_departure_shift_minutes": 0, "new_arrival_shift_minutes": 0},
           "rejected_alternatives", ["sc-downgrade"], [], (0, 68900), fares=[68900], cabin="first",
           count_from=resp_day(29, 15))
    change([("ORD", "BOS", T(30, 13))], {"event": "retimed", "new_departure_shift_minutes": 0,
                                         "new_arrival_shift_minutes": 240},
           "flew_on_changed_flight", ["sc-delay", "sc-accepted"],
           [anc("advance_seat_selection", 3900, 1, True)], (0, 0), fares=[18400])
    # no response and the changed flight left: counted from the day it departed (here after midnight UTC)
    change([("ORD", "BOS", T(30, 22, 30))], {"event": "retimed", "new_departure_shift_minutes": 200,
                                             "new_arrival_shift_minutes": 200},
           "did_not_respond_and_flight_departed", ["sc-delay", "due-date"],
           [anc("advance_seat_selection", 3900, 1, False)], (0, 22300), fares=[18400], pay="debit_card",
           requested="2026-11-03", count_from="2026-10-31")
    # a later written request does not move the start: the rejection came first
    change([("ORD", "DFW", T(31, 13))], {"event": "cancelled", "alternative_offered": "rebooking_on_later_flight"},
           "rejected_alternatives", ["sc-cancel", "due-date"], [], (0, 26100), fares=[26100], pay="credit_card",
           requested="2026-11-06", count_from=resp_day(31, 13))
    change([("ORD", "DFW", T(31, 15))], {"event": "cancelled", "alternative_offered": "rebooking_on_later_flight"},
           "rejected_alternatives", ["sc-cancel", "due-date"], [], (0, 26100), fares=[26100], pay="debit_card",
           requested="2026-11-06", count_from=resp_day(31, 15))
    # voucher offer left unanswered: counted from the day the cancelled flight was to depart
    change([("ORD", "DFW", T(37, 23, 30))], {"event": "cancelled", "alternative_offered": "travel_voucher"},
           "did_not_respond_before_scheduled_departure", ["sc-cancel", "sc-voucher", "due-date"], [],
           (0, 26100), fares=[26100], pay="credit_card", count_from="2026-11-06")
    # nothing offered for a cancellation: due from the cancellation, not from the later request
    change([("ORD", "DFW", T(32, 13))], {"event": "cancelled", "alternative_offered": "none"},
           "requested_refund", ["sc-cancel", "due-date"], [], (0, 26100), fares=[26100], pay="credit_card",
           requested="2026-11-03", respond_hours=130, count_from="2026-10-29")

    # ---------------- covered flights: break in journey at a foreign point (260.2) ---------------
    def euro(gap_minutes, inc, tags, expected, response="rejected_alternatives", inbound=False):
        first = T(40, 22)
        if not inbound:
            legs = [("ORD", "LHR", first, AIRCRAFT[3]),
                    ("LHR", "FRA", first + timedelta(minutes=block("ORD", "LHR") + gap_minutes))]
            affected = 2
        else:
            legs = [("FRA", "LHR", first),
                    ("LHR", "ORD", first + timedelta(minutes=block("LHR", "FRA") + gap_minutes), AIRCRAFT[3])]
            affected = 1
        dep = legs[affected - 1][2]
        rd = (dep - timedelta(days=5, hours=1) + timedelta(hours=20)).date().isoformat()
        return change(legs, inc, response, tags, (), expected, fares=[48700, 14900], affected=affected,
                      notice_days=5, count_from=rd)

    cx = {"event": "cancelled", "alternative_offered": "rebooking_on_later_flight"}
    euro(180, cx, ["sc-covered", "break-in-journey"], (0, 63600))
    euro(3 * 1440, cx, ["sc-covered", "break-in-journey"], (0, 0))
    euro(1440, cx, ["sc-covered", "break-in-journey"], (0, 63600))
    euro(1445, cx, ["sc-covered", "break-in-journey"], (0, 0))
    euro(2 * 1440, cx, ["sc-covered", "break-in-journey"], (0, 0), inbound=True)
    euro(150, {"event": "retimed", "new_departure_shift_minutes": 0, "new_arrival_shift_minutes": 400},
         ["sc-covered", "break-in-journey", "sc-delay"], (0, 63600))
    euro(2 * 1440, {"event": "retimed", "new_departure_shift_minutes": 0, "new_arrival_shift_minutes": 400},
         ["sc-covered", "break-in-journey", "sc-delay"], (0, 0))

    # ---------------- bags (260.5) ----------------------------------------------------------------
    def bag(legs, delay_min, tags, expected, mbr=True, lost=False, fees=(3500,), linked=True, which=0,
            exemption=None, subscription=None, pay=None, trigger=None):
        t = w.ticket(legs, pay=pay)
        last = t["coupons"][-1]
        arr = datetime.fromisoformat(last["scheduled_arrival"].replace("Z", "+00:00")) + timedelta(minutes=12)
        bags = [{"bag_tag": f"LS{rng.randrange(100000, 999999)}", "fee_cents": f,
                 "fee_linked_to_this_bag_by_unique_identifier": linked} for f in fees]
        inc = {"deplaning_opportunity_at_final_destination": iso(arr), "bag_tag": bags[which]["bag_tag"],
               "status": "lost" if lost else "delivered",
               "delivered_or_picked_up_at": None if lost else iso(arr + timedelta(minutes=delay_min)),
               "mishandled_baggage_report_filed": mbr, "exemption_facts": exemption,
               "bag_fee_subscription": subscription}
        trig = trigger or asked_on(w, t, arr, delay_min, lost)
        return w.add("baggage", t, inc, [], tags, expected, trig, bags)

    # ---------------- local schedule times across the 2026 daylight-saving changes ----------------
    # US clocks fall back Nov 1 2026 at 2:00 local (Chicago 07:00Z); EU clocks Oct 25 2026 at 01:00Z.
    # DEN-ORD leaves 02:40Z Nov 1, arrives 05:20Z = 00:20 CDT; replacement arrives 08:10Z = 02:10 CST.
    # Real lateness 2 h 50 m (400%, 4 x 233.00 = 932.00); reading the wall clocks gives 1 h 50 m (200%).
    oversale(w, [("DEN", "ORD", T(32, 2, 40))], 1, 170, ["db-band", "dst"], fares=[23300], expected=(93200, 0))
    # ORD-DEN arrives 05:40Z = 23:40 MDT Oct 31; DEN-SFO leaves 10:00Z = 03:00 MST Nov 1. The real gap is
    # 4 h 20 m, a stopover, so the fare runs to Denver only: 4 x 188.00 = 752.00 (replacement 09:00Z,
    # 200 min late). Wall clocks show 3 h 20 m, which would wrongly add the SFO coupon.
    oversale(w, [("ORD", "DEN", T(32, 3, 0)), ("DEN", "SFO", T(32, 10, 0))], 1, 200,
             ["db-fare-base", "stopover", "dst"], fares=[18800, 14200], expected=(75200, 0))
    # ORD-LGA arrives 04:30Z = 00:30 EDT Nov 1; new arrival 07:30Z = 02:30 EST. Real shift 3 h, significant
    # for a domestic trip, so the fare is refunded; wall clocks show 2 h.
    change([("ORD", "LGA", T(32, 2, 15))], {"event": "retimed", "new_departure_shift_minutes": 180,
                                           "new_arrival_shift_minutes": 180},
           "rejected_alternatives", ["sc-delay", "sc-threshold", "dst"], [], (0, 21800), fares=[21800],
           count_from=resp_day(32, 2))
    # ORD-LHR arrives 06:00Z Oct 24 = 07:00 BST; LHR-FRA leaves 07:00Z Oct 25 = 07:00 GMT. The real
    # stopover is 25 h, a break in journey, so the LHR-FRA cancellation is not a covered flight: 0.
    # Wall clocks show exactly 24 h, which would make it covered.
    legs = [("ORD", "LHR", T(23, 21, 55), AIRCRAFT[3]), ("LHR", "FRA", T(25, 7, 0))]
    change(legs, {"event": "cancelled", "alternative_offered": "rebooking_on_later_flight"}, "rejected_alternatives",
           ["sc-covered", "break-in-journey", "dst"], [], (0, 0), fares=[48700, 14900], affected=2, notice_days=5)
    # voucher offer unanswered for ORD-DFW leaving 01:30Z Nov 1 (20:30 CDT Oct 31): the due date runs from
    # the UTC date of the scheduled departure, Nov 1; debit card, 20 days: 2026-11-21.
    change([("ORD", "DFW", T(32, 1, 30))], {"event": "cancelled", "alternative_offered": "travel_voucher"},
           "did_not_respond_before_scheduled_departure", ["sc-cancel", "due-date", "time-zone"], [], (0, 26100),
           fares=[26100], pay="debit_card", count_from="2026-11-01")
    # bag to London: ORD-LHR block 8 h 05 m (wall clocks 14 h 05 m), so the 15-hour limit applies.
    bag([("ORD", "FRA", T(27, 22), AIRCRAFT[3])], 1000, ["bag-threshold", "international", "time-zone"],
        (0, 7500), fees=(7500,))
    bag([("ORD", "LHR", T(28, 22), AIRCRAFT[3])], 1300, ["bag-threshold", "international", "time-zone"],
        (0, 7500), fees=(7500,))

    bag([("ORD", "LGA", T(33, 13))], 720, ["bag-threshold", "domestic"], (0, 0))
    bag([("ORD", "LGA", T(33, 15))], 721, ["bag-threshold", "domestic"], (0, 3500))
    bag([("ORD", "LHR", T(34, 22), AIRCRAFT[3])], 800, ["bag-threshold", "international"], (0, 0), fees=(7500,))
    bag([("ORD", "LHR", T(34, 23), AIRCRAFT[3])], 901, ["bag-threshold", "international"], (0, 7500), fees=(7500,))
    bag([("ORD", "LHR", T(35, 22), AIRCRAFT[3])], 900, ["bag-threshold", "international"], (0, 0), fees=(7500,))
    bag([("ORD", "NRT", T(35, 23), AIRCRAFT[3])], 1500, ["bag-threshold", "long-haul"], (0, 0), fees=(10000,))
    bag([("ORD", "NRT", T(36, 1), AIRCRAFT[3])], 1801, ["bag-threshold", "long-haul"], (0, 10000), fees=(10000,))
    bag([("MSP", "ORD", T(36, 13)), ("ORD", "NRT", T(36, 16), AIRCRAFT[3])], 1700,
        ["bag-threshold", "long-haul", "domestic-leg"], (0, 0), fees=(10000,))
    bag([("ORD", "LGA", T(37, 13))], 2000, ["bag-mbr"], (0, 0), mbr=False)
    bag([("ORD", "LGA", T(37, 15))], 0, ["bag-lost"], (0, 3500), lost=True)
    bag([("ORD", "LGA", T(38, 13))], 900, ["bag-amount", "escalated"], (0, 4500), fees=(3500, 4500), linked=True,
        which=1)
    bag([("ORD", "LGA", T(38, 15))], 900, ["bag-amount", "escalated"], (0, 4500), fees=(3500, 4500), linked=False,
        which=0)
    bag([("ORD", "LGA", T(39, 13))], 900, ["bag-amount", "escalated"], (0, 3500), fees=(3500, 4500), linked=True,
        which=0)
    bag([("ORD", "LGA", T(39, 15))], 900, ["bag-amount", "subscription"], (0, 3500), fees=(0,),
        subscription={"subscribed": True, "lowest_fee_charged_to_non_subscriber_same_status_and_cabin_cents": 3500})
    bag([("LHR", "ORD", T(40, 13), AIRCRAFT[3]), ("ORD", "DEN", T(40, 23))], 1600, ["bag-exemption", "customs"],
        (0, 0), fees=(7500,), exemption={"passenger_failed_to_recheck_bag_at_first_us_entry_point": True})
    bag([("ORD", "LGA", T(41, 13))], 900, ["bag-exemption", "voluntary"], (0, 0),
        exemption={"passenger_voluntarily_agreed_to_travel_without_bag_after_missing_check_in_time": True})
    bag([("ORD", "LGA", T(41, 15))], 900, ["bag-exemption", "hidden-city"], (0, 0),
        exemption={"passenger_ended_travel_before_ticketed_final_destination": True})

    # ---------------- ancillary services not provided (260.4) -----------------------------------
    def service(legs, items, tags, expected, pay=None, fault=False):
        t = w.ticket(legs, pay=pay)
        inc = {"service_failure_through_fault_of_consumer": fault}
        return w.add("ancillary_service_not_provided", t, inc, items, tags, expected,
                     t["coupons"][0]["scheduled_departure"][:10])

    service([("ORD", "SFO", T(42, 14))], [anc("wifi", 1900, 1, False), anc("advance_seat_selection", 4900, 1, True)],
            ["ancillary"], (0, 1900))
    service([("ORD", "SFO", T(42, 16))], [anc("advance_seat_selection", 4900, 1, False)], ["ancillary"], (0, 4900))
    service([("ORD", "SFO", T(43, 14))], [anc("lounge_access", 5900, 1, False)], ["ancillary", "fault"], (0, 0),
            fault=True)


def filler(w, n):
    made = 0
    while made < n:
        before = (len(w.claims), set(w.flights))
        filler_one(w)
        c = w.claims[-1]
        if any(repeated_hour(t, ap) for t, ap in schedule_times(c)):
            w.claims.pop()
            w.tags.pop(c["claim_id"], None)
            w.golden.pop(c["claim_id"], None)
            for fid in set(w.flights) - before[1]:
                del w.flights[fid]
            w.n_claim -= 1
            continue
        made += 1


def filler_one(w):
    if True:
        kind = rng.choice(["oversale", "change", "bag", "bag", "service"])
        day = rng.choice([rng.randint(5, 50), rng.choice([23, 24, 25, 30, 31, 32, 33])])
        dep = T(min(day, 61), rng.randrange(0, 24), rng.choice([0, 15, 30, 45]))
        if rng.random() < 0.35:      # around the EU (Oct 25) and US (Nov 1) clock changes
            dep = rng.choice([T(24, rng.randrange(16, 24)), T(25, rng.randrange(0, 8)),
                              T(31, rng.randrange(16, 24)), T(32, rng.randrange(0, 12))]) + \
                timedelta(minutes=rng.choice([0, 15, 30, 45]))
        route = rng.choice([("ORD", "LGA"), ("ORD", "DFW"), ("ORD", "DEN"), ("ORD", "BOS"), ("ORD", "ATL"),
                            ("ORD", "SFO"), ("ORD", "YYZ"), ("ORD", "LHR"), ("ORD", "CUN"), ("ORD", "FRA"),
                            ("ORD", "NRT"), ("SEA", "NRT"), ("DEN", "SFO"), ("DFW", "CUN")])
        intl = foreign(route[1])
        legs = [(route[0], route[1], dep)]
        if kind in ("oversale", "bag") and route[0] == "ORD" and rng.random() < 0.4:
            first = rng.choice(["MSP", "DEN", "BOS", "ATL"])
            gap = rng.choice([90, 180, 230, 250, 300, 420])
            legs = [(first, "ORD", dep - timedelta(minutes=block(first, "ORD") + gap)), (route[0], route[1], dep)]
            if route[1] in ("LHR", "NRT", "FRA"):
                legs[1] = legs[1] + (AIRCRAFT[3],)
        if kind == "oversale":
            delay = rng.choice([45, 75, 110, 150, 200, 260, 400])
            oversale(w, legs, len(legs), delay, ["filler"],
                     ancillary=[anc("advance_seat_selection", 3900, 1, rng.random() < 0.5)] if rng.random() < 0.4 else [])
        elif kind == "change":
            ev = rng.choice(["cancelled", "retimed", "retimed"] + ([] if intl else ["airport_change"]))
            inc = {"event": ev}
            if ev == "cancelled":
                inc["alternative_offered"] = rng.choice(["rebooking_on_later_flight", "travel_voucher", "none"])
                resp = {"rebooking_on_later_flight": rng.choice(["rejected_alternatives", "accepted_rebooking"]),
                        "travel_voucher": rng.choice(["accepted_voucher_affirmatively",
                                                      "did_not_respond_before_scheduled_departure"]),
                        "none": "requested_refund"}[inc["alternative_offered"]]
            elif ev == "retimed":
                sh = rng.choice([60, 120, 170, 200, 250, 330, 400, 500])
                inc.update(new_departure_shift_minutes=sh, new_arrival_shift_minutes=sh)
                resp = rng.choice(["rejected_alternatives", "flew_on_changed_flight",
                                   "did_not_respond_and_flight_departed"])
            else:
                inc.update(new_destination_airport="EWR" if route[1] == "LGA" else "MDW",
                           new_departure_shift_minutes=0, new_arrival_shift_minutes=15)
                if route[0] == "ORD" and route[1] != "LGA":
                    inc.pop("new_destination_airport")
                    inc["new_origin_airport"] = "MDW"
                resp = rng.choice(["rejected_alternatives", "flew_on_changed_flight"])
            t = w.ticket(legs)
            notice = dep - timedelta(days=rng.choice([1, 2, 4, 6]), hours=rng.choice([2, 5, 9]))
            answered = resp not in ("did_not_respond_before_scheduled_departure", "flew_on_changed_flight",
                                    "did_not_respond_and_flight_departed")
            at = notice + timedelta(hours=rng.choice([3, 11, 26])) if answered else None
            inc = dict(inc, affected_coupon=1, carrier_notice_at=iso(notice), consumer_response=resp,
                       consumer_response_at=iso(at) if at else None)
            if resp == "requested_refund":
                req = at.date().isoformat()
            elif resp.startswith("accepted") or resp == "flew_on_changed_flight":
                req = notice.date().isoformat()      # 260.4 refunds: asked for when Lakeshore gave notice
            elif rng.random() < 0.6:
                req = (dep + timedelta(days=rng.choice([0, 1, 3, 8]))).date().isoformat()
            else:
                req = None
            w.add("schedule_change_or_cancellation", t, inc,
                  [anc("first_checked_bag", 3500, 1, resp in ("accepted_rebooking", "flew_on_changed_flight"))]
                  if rng.random() < 0.4 else [], ["filler"], None, req)
        elif kind == "bag":
            t = w.ticket(legs)
            last = t["coupons"][-1]
            arr = datetime.fromisoformat(last["scheduled_arrival"].replace("Z", "+00:00")) + timedelta(minutes=10)
            d = rng.choice([200, 600, 760, 1000, 1400, 2000])
            bags = [{"bag_tag": f"LS{rng.randrange(100000, 999999)}", "fee_cents": rng.choice([3500, 4000, 7500]),
                     "fee_linked_to_this_bag_by_unique_identifier": True}]
            inc = {"deplaning_opportunity_at_final_destination": iso(arr), "bag_tag": bags[0]["bag_tag"],
                   "status": "delivered", "delivered_or_picked_up_at": iso(arr + timedelta(minutes=d)),
                   "mishandled_baggage_report_filed": rng.random() < 0.85, "exemption_facts": None,
                   "bag_fee_subscription": None}
            w.add("baggage", t, inc, [], ["filler"], None, asked_on(w, t, arr, d, False), bags)
        else:
            t = w.ticket(legs)
            items = [anc(rng.choice(["wifi", "advance_seat_selection", "inflight_meal"]),
                         rng.choice([900, 1900, 2900, 4900]), 1, rng.random() < 0.5)]
            w.add("ancillary_service_not_provided", t, {"service_failure_through_fault_of_consumer": False},
                  items, ["filler"], None, legs[0][2].date().isoformat())


def main():
    w = W()
    planted(w)
    filler(w, 90)
    order = list(range(len(w.claims)))
    rng.shuffle(order)
    remap, claims = {}, []
    for i, j in enumerate(order, 1):
        c = w.claims[j]
        remap[c["claim_id"]] = f"CL{i:04d}"
        c["claim_id"] = remap[c["claim_id"]]
        claims.append(c)
    # published schedules are local wall times at each airport; record timestamps stay in UTC
    for f in w.flights.values():
        f["scheduled_departure"] = local(f["scheduled_departure"], f["origin"])
        f["scheduled_arrival"] = local(f["scheduled_arrival"], f["destination"])
    for c in claims:
        cps, inc = c["ticket"]["coupons"], c["incident"]
        utc = {k["coupon"]: (k["scheduled_departure"], k["scheduled_arrival"]) for k in cps}
        for k in cps:
            k["scheduled_departure"] = local(k["scheduled_departure"], k["origin"])
            k["scheduled_arrival"] = local(k["scheduled_arrival"], k["destination"])
        if c["claim_type"] == "oversale":
            alt = inc["alternate_transportation"]
            alt["planned_arrival_at_time_arranged"] = local(alt["planned_arrival_at_time_arranged"], alt["arrival_airport"])
        if c["claim_type"] == "schedule_change_or_cancellation" and "new_departure_shift_minutes" in inc:
            k = cps[inc["affected_coupon"] - 1]
            dep, arr = (datetime.fromisoformat(x.replace("Z", "+00:00")) for x in utc[k["coupon"]])
            new_dep = iso(dep + timedelta(minutes=inc.pop("new_departure_shift_minutes")))
            new_arr = iso(arr + timedelta(minutes=inc.pop("new_arrival_shift_minutes")))
            inc["new_scheduled_departure"] = local(new_dep, inc.get("new_origin_airport") or k["origin"])
            inc["new_scheduled_arrival"] = local(new_arr, inc.get("new_destination_airport") or k["destination"])
    assert not AMBIGUOUS, f"local times in a repeated hour: {AMBIGUOUS}"
    ENV.mkdir(parents=True, exist_ok=True)
    (ENV / "claims.json").write_text(json.dumps(claims, indent=1) + "\n")
    (ENV / "flights.json").write_text(json.dumps(sorted(w.flights.values(), key=lambda f: f["flight_id"]),
                                                 indent=1) + "\n")
    (ENV / "airports.json").write_text(json.dumps({k: {"city": v[0], "country": v[1], "time_zone": ZONES[k]}
                                                   for k, v in AIRPORTS.items()},
                                                  indent=1) + "\n")
    (ENV / "carrier.json").write_text(json.dumps({
        "carrier": "Lakeshore Air", "type": "U.S. air carrier, scheduled passenger service",
        "merchant_of_record": "Lakeshore Air for every ticket and every ancillary fee in this queue",
        "money_unit": "cents (USD)",
        "times": "flight schedule times are local at the airport; record timestamps ending in Z are UTC",
        "coupon_fare_cents": "price paid for that coupon including all mandatory taxes and fees, excluding ancillary fees",
        "bag_fees": "escalating per-bag scale; some fees are linked to a specific bag by unique identifier",
        "tickets": "every itinerary was bought as one ticket in a single transaction; Lakeshore operates every flight"},
        indent=1) + "\n")
    (ENV / "federal_holidays.json").write_text(json.dumps({"source": "OPM federal holiday schedule",
                                                           "observed_dates": HOLIDAYS}, indent=1) + "\n")
    if TST.exists():
        shutil.rmtree(TST)
    shutil.copytree(ENV, TST)
    (ROOT / "tests" / "case_tags.json").write_text(json.dumps({remap[k]: v for k, v in w.tags.items()},
                                                              indent=1, sort_keys=True) + "\n")
    (ROOT / "tests" / "golden.json").write_text(json.dumps({remap[k]: v for k, v in w.golden.items()},
                                                           indent=1, sort_keys=True) + "\n")
    print(len(claims), "claims,", len(w.flights), "flights,", len(w.golden), "golden")


if __name__ == "__main__":
    main()
