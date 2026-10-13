#!/usr/bin/env python3
"""Generate the airline-claims-desk inputs (dev only, never shipped). Version 5.

Lakeshore Air (fictional U.S. carrier, merchant of record for every ticket and fee) claim queue, built from
operational records instead of pre-classified facts: every flight has a schedule history (local wall times,
each version stamped with the UTC time it was recorded), cancellations, gate events and door times; every
claim has the ticket, the notices Lakeshore sent, the passenger's replies and the gate and baggage events.
Rules: 14 CFR Part 250 (oversales) and Part 260 (refunds). Planted claims carry a hand-worked expected
answer (tests/golden.json); filler claims are random and answered by the engine only.

Everything is built in UTC; local wall times are produced only when the data is written. Wall times in a
repeated daylight-saving hour are never written (claims that would need one are rebuilt).
"""
import json
import random
import shutil
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2] / "tasks" / "airline-claims-desk"
ENV, TST = ROOT / "environment" / "data", ROOT / "tests" / "data"
rng = random.Random(26050)
UTC = timezone.utc
PUBLISHED = datetime(2026, 5, 4, 15, 0, tzinfo=UTC)        # winter schedule first loaded

AIRPORTS = {
    "ORD": ("Chicago", "US", "America/Chicago"), "MDW": ("Chicago", "US", "America/Chicago"),
    "MKE": ("Milwaukee", "US", "America/Chicago"), "MSP": ("Minneapolis", "US", "America/Chicago"),
    "DFW": ("Dallas", "US", "America/Chicago"), "LGA": ("New York", "US", "America/New_York"),
    "EWR": ("Newark", "US", "America/New_York"), "BOS": ("Boston", "US", "America/New_York"),
    "ATL": ("Atlanta", "US", "America/New_York"), "DEN": ("Denver", "US", "America/Denver"),
    "PHX": ("Phoenix", "US", "America/Phoenix"), "SFO": ("San Francisco", "US", "America/Los_Angeles"),
    "LAX": ("Los Angeles", "US", "America/Los_Angeles"), "SEA": ("Seattle", "US", "America/Los_Angeles"),
    "HNL": ("Honolulu", "US", "Pacific/Honolulu"), "YYZ": ("Toronto", "CA", "America/Toronto"),
    "CUN": ("Cancun", "MX", "America/Cancun"), "LHR": ("London", "GB", "Europe/London"),
    "FRA": ("Frankfurt", "DE", "Europe/Berlin"), "NRT": ("Tokyo", "JP", "Asia/Tokyo")}
BLOCK = {("ORD", "LGA"): 135, ("ORD", "EWR"): 130, ("ORD", "BOS"): 140, ("ORD", "ATL"): 120,
         ("ORD", "DFW"): 150, ("ORD", "DEN"): 160, ("ORD", "MSP"): 85, ("ORD", "MKE"): 45,
         ("ORD", "SFO"): 280, ("ORD", "SEA"): 270, ("ORD", "LAX"): 270, ("ORD", "PHX"): 225,
         ("ORD", "HNL"): 530, ("ORD", "YYZ"): 90, ("ORD", "CUN"): 230, ("ORD", "LHR"): 485,
         ("ORD", "FRA"): 520, ("ORD", "NRT"): 790,
         ("DEN", "SFO"): 150, ("DEN", "SEA"): 165, ("DEN", "LAX"): 140, ("DEN", "PHX"): 105,
         ("DEN", "ATL"): 195, ("DEN", "BOS"): 235, ("DEN", "LGA"): 230, ("DEN", "MSP"): 125,
         ("DEN", "DFW"): 120, ("DFW", "LAX"): 200, ("DFW", "SFO"): 230, ("DFW", "PHX"): 130,
         ("DFW", "CUN"): 150, ("DFW", "LGA"): 200, ("DFW", "ATL"): 125, ("DFW", "BOS"): 230,
         ("DFW", "MSP"): 150, ("DFW", "SEA"): 260, ("ATL", "LGA"): 130, ("ATL", "BOS"): 155,
         ("ATL", "CUN"): 170, ("ATL", "SFO"): 330, ("ATL", "LAX"): 300, ("ATL", "MSP"): 155,
         ("ATL", "EWR"): 125, ("MSP", "SEA"): 215, ("MSP", "LAX"): 230, ("MSP", "LGA"): 165,
         ("MSP", "BOS"): 170, ("MSP", "YYZ"): 120, ("PHX", "LAX"): 85, ("PHX", "SFO"): 115,
         ("PHX", "SEA"): 165, ("SEA", "NRT"): 610, ("SFO", "HNL"): 340, ("LAX", "HNL"): 345,
         ("LHR", "FRA"): 95, ("BOS", "LGA"): 75, ("DFW", "EWR"): 205}
WIDE = ("Boeing 787-9", 290)
AIRCRAFT = [("Airbus A321neo", 196), ("Boeing 737-800", 166), ("Embraer E175", 76), ("Airbus A320", 150),
            ("Boeing 737 MAX 8", 172)]
NAMES = ["A. Okafor", "B. Lindqvist", "C. Ramirez", "D. Chen", "E. Novak", "F. Haddad", "G. Moreau",
         "H. Tanaka", "I. Kowalski", "J. Mensah", "K. Patel", "L. Rossi", "M. Byrne", "N. Silva",
         "O. Ahmed", "P. Schultz", "Q. Nguyen", "R. Dubois", "S. Kim", "T. Oyelaran"]
PAY = ["credit_card", "credit_card", "credit_card", "debit_card", "cash", "check"]
HOLIDAYS = ["2026-10-12", "2026-11-11", "2026-11-26", "2026-12-25", "2027-01-01", "2027-01-18",
            "2027-02-15"]
CABINS = ["first", "business", "premium_economy", "economy"]


class Ambiguous(Exception):
    pass


def foreign(ap):
    return AIRPORTS[ap][1] != "US"


def local(t, ap):
    z = ZoneInfo(AIRPORTS[ap][2])
    wall = t.astimezone(z).replace(tzinfo=None)
    if wall.replace(tzinfo=z, fold=0).utcoffset() != wall.replace(tzinfo=z, fold=1).utcoffset():
        raise Ambiguous((t, ap))
    return wall.strftime("%Y-%m-%dT%H:%M")


def iso(t):
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%MZ")


def T(day, h=0, m=0):
    """UTC instant; day 1 = 2026-10-01, day 32 = 2026-11-01."""
    return datetime(2026, 10, 1, tzinfo=UTC) + timedelta(days=day - 1, hours=h, minutes=m)


def mins(n):
    return timedelta(minutes=n)


def block(a, b):
    return BLOCK.get((a, b)) or BLOCK[(b, a)]


def has_block(a, b):
    return (a, b) in BLOCK or (b, a) in BLOCK


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


def sched(f, t):
    """(departure, arrival) of the schedule version in force at t."""
    v = [x for x in f["versions"] if x[0] <= t]
    return v[-1][1], v[-1][2]


def anc(service, fee, coupon, provided):
    return {"service": service, "fee_cents": fee, "coupon": coupon, "provided": provided}


class W:
    def __init__(self):
        self.flights, self.claims, self.golden, self.tags = {}, [], {}, {}
        self.n_claim = self.n_flight = 0

    def flight(self, a, b, dep, aircraft=None, rec=PUBLISHED):
        self.n_flight += 1
        num = 100 + self.n_flight
        blk = block(a, b)
        if aircraft is None:
            aircraft = WIDE if blk > 420 else rng.choice(AIRCRAFT)
        f = {"id": f"LS{num}-{local(dep, a)[:10].replace('-', '')}", "num": num, "a": a, "b": b, "ac": aircraft,
             "versions": [(rec, dep, dep + mins(blk))], "status": "operated", "cancelled_at": None, "door": None,
             "sub": None, "low": {"economy": rng.randrange(8900, 42000, 100), "first": rng.randrange(45000, 120000, 100)}}
        self.flights[f["id"]] = f
        return f

    def retime(self, f, at, dshift, ashift=None):
        _, d, a = f["versions"][-1]
        f["versions"].append((at, d + mins(dshift), a + mins(dshift if ashift is None else ashift)))

    def ticket(self, fl, purchased, cabin="economy", pay=None, zero=False, fares=None):
        coupons = [{"coupon": i + 1, "flight_id": f["id"], "origin": f["a"], "destination": f["b"], "cabin": cabin,
                    "fare_cents": 0 if zero else (fares[i] if fares else rng.randrange(7900, 39900, 100)),
                    "reservation_status": "confirmed"} for i, f in enumerate(fl)]
        conns = [{"airport": fl[i]["b"], "between_coupons": [i + 1, i + 2], "bags_checked_through": True,
                  "passenger_left_airport": False} for i in range(len(fl) - 1)]
        return {"ticket_number": f"016{rng.randrange(10**9, 10**10)}", "purchased_at": iso(purchased),
                "payment_method": pay or rng.choice(PAY), "award_ticket_paid_with_miles": zero,
                "coupons": coupons, "connections": conns, "bag_fee_subscription": None}

    def add(self, ctype, ticket, events, ancillary, bags, requested, tags, expected, count_from):
        self.n_claim += 1
        cid = f"CL{self.n_claim:04d}"
        events = sorted(events, key=lambda e: e["at"])
        c = {"claim_id": cid, "claim_type": ctype, "passenger": rng.choice(NAMES), "ticket": ticket,
             "ancillary_purchases": list(ancillary), "checked_bags": list(bags),
             "events": [{"at": iso(e["at"]), **{k: v for k, v in e.items() if k != "at"}} for e in events],
             "refund_requested_at": iso(requested) if requested else None}
        self.claims.append(c)
        self.tags[cid] = list(tags)
        if expected is not None:
            comp, ref = expected
            self.golden[cid] = {"compensation": f"{comp / 100:.2f}", "refund": f"{ref / 100:.2f}",
                                "refund_due_date": due(count_from, ticket["payment_method"]) if ref else "none"}
        return cid

    def check(self, f):
        for _, d, a in f["versions"]:
            local(d, f["a"])
            local(a, f["b"])
        if f["door"]:
            local(f["door"], f["b"])

    def attempt(self, fn, *args, **kw):
        """Build one filler claim; roll it back if any of its wall times would fall in a repeated hour."""
        snap = (set(self.flights), len(self.claims), self.n_claim, self.n_flight)
        try:
            ok = fn(self, *args, **kw)
            for fid in set(self.flights) - snap[0]:
                self.check(self.flights[fid])
            if ok is False:
                raise Ambiguous("rejected")
            return True
        except Ambiguous:
            for fid in set(self.flights) - snap[0]:
                del self.flights[fid]
            for c in self.claims[snap[1]:]:
                self.tags.pop(c["claim_id"], None)
                self.golden.pop(c["claim_id"], None)
            del self.claims[snap[1]:]
            self.n_claim = snap[2]
            return False


# ---------------------------------------------------------------- claim builders ------------------------------
def oversale(w, legs, denied, alt_delay, tags, expected=None, *, fares=None, cabin="economy", zero=False, pay=None,
             volunteer=False, accepted_offer=False, checkin=90, reason="oversold", ops=True, reseat=None,
             ancillary=(), alt_nonstop=False, alt_later=0, sub=None):
    """legs: (origin, destination, UTC departure[, aircraft]); denied: 1-based coupon; alt_delay: minutes the
    replacement is planned to arrive after the original arrival at the destination or first stopover
    (None: nothing arranged). alt_later: a later schedule change to the replacement (after it was arranged)."""
    fl = [w.flight(x[0], x[1], x[2], x[3] if len(x) > 3 else None) for x in legs]
    t = w.ticket(fl, fl[0]["versions"][0][1] - timedelta(days=30, hours=5), cabin, pay, zero, fares)
    k = denied - 1
    f = fl[k]
    dep = f["versions"][-1][1]
    end = k
    while end + 1 < len(fl) and fl[end + 1]["versions"][-1][1] - fl[end]["versions"][-1][2] <= mins(240):
        end += 1
    gate = dep - mins(15)
    ev = [{"at": dep - mins(checkin), "type": "checked_in", "flight_id": f["id"]}]
    if volunteer:
        ev.append({"at": gate, "type": "volunteer_offer_accepted", "flight_id": f["id"]})
    else:
        d = {"at": gate, "type": "denied_boarding", "flight_id": f["id"], "reason": reason}
        if reason != "oversold":
            d["required_for_operational_or_safety_reasons"] = ops
        ev.append(d)
        if accepted_offer:
            ev.append({"at": gate + mins(4), "type": "compensation_offer_accepted", "flight_id": f["id"]})
    if reseat:
        ev.append({"at": gate + mins(2), "type": "seat_offered_in_other_cabin", "flight_id": f["id"],
                   "cabin": reseat, "extra_charge_cents": 0})
    if sub:
        f["sub"] = sub
        if f["ac"][1] >= sub["scheduled_designed_passenger_seats"]:
            f["ac"] = ("Boeing 737-800", 166)
    if alt_delay is not None:
        arranged = dep - mins(10)
        target = fl[end]["versions"][-1][2] + mins(alt_delay)
        if alt_nonstop or end == k:
            a, b = f["a"], fl[end]["b"]
            alt = [w.flight(a, b, target - mins(block(a, b)))]
        else:
            alt = [w.flight(x["a"], x["b"], x["versions"][-1][1] + mins(alt_delay)) for x in fl[k:end + 1]]
        if alt_later:
            w.retime(alt[-1], arranged + mins(rng.choice([45, 80, 130])), alt_later)
        ev.append({"at": arranged, "type": "alternate_transportation_arranged", "itinerary": [x["id"] for x in alt]})
    return w.add("oversale", t, ev, ancillary, (), gate, tags, expected, gate.date().isoformat())


def change(w, legs, notices, reply, tags, expected=None, count_from=None, *, fares=None, cabin="economy", pay=None,
           purchased=None, requested=None, ancillary=(), pre=(), reply_after=20):
    """notices: dicts with before (timedelta before the first leg's original departure, default 3 d 1 h),
    retime [(leg, dshift, ashift)], cancel [leg], itinerary (list of kept leg indexes or new (a, b, dep[, cabin])
    flights; None = no flight offered) and voucher (bool). pre: [(leg, recorded_at, dshift, ashift)] schedule
    changes made before the ticket was bought. reply: declined_offer / accepted_offered_itinerary /
    accepted_voucher / boarded / None."""
    fl = [w.flight(x[0], x[1], x[2], x[3] if len(x) > 3 else None) for x in legs]
    first0 = fl[0]["versions"][0][1]
    for i, at, ds, as_ in pre:
        w.retime(fl[i], at, ds, as_)
    t = w.ticket(fl, purchased or first0 - timedelta(days=40, hours=3), cabin, pay, fares=fares)
    ev, offered = [], None
    for n in notices:
        at = first0 - n.get("before", timedelta(days=3, hours=1))
        for i, ds, as_ in n.get("retime", ()):
            w.retime(fl[i], at - mins(7), ds, as_)
        for i in n.get("cancel", ()):
            fl[i]["status"], fl[i]["cancelled_at"] = "cancelled", at - mins(7)
        offered = None
        if n.get("itinerary") is not None:
            offered = []
            for item in n["itinerary"]:
                if isinstance(item, int):
                    offered.append((fl[item], cabin))
                elif isinstance(item[0], int):
                    offered.append((fl[item[0]], item[1]))
                else:                          # new flight (a, b, dep[, aircraft][, cabin])
                    ac = next((x for x in item[3:] if isinstance(x, tuple)), None)
                    cb = next((x for x in item[3:] if isinstance(x, str)), cabin)
                    offered.append((w.flight(item[0], item[1], item[2], ac), cb))
        ev.append({"at": at, "type": "itinerary_change_notice",
                   "reason": "cancellation" if n.get("cancel") else "schedule_change",
                   "offered_itinerary": None if offered is None else [{"flight_id": f["id"], "cabin": c}
                                                                      for f, c in offered],
                   "voucher_offered": n.get("voucher", False)})
    last = ev[-1]["at"]
    if reply in ("declined_offer", "accepted_offered_itinerary", "accepted_voucher"):
        ev.append({"at": last + timedelta(hours=reply_after), "type": "passenger_reply", "choice": reply})
    elif reply == "boarded":
        f0 = offered[0][0]
        ev.append({"at": sched(f0, last)[0] - mins(25), "type": "boarded", "flight_id": f0["id"]})
    if requested == "notice":
        requested = ev[0]["at"] + mins(50)
    return w.add("schedule_change_or_cancellation", t, ev, ancillary, (), requested, tags, expected, count_from)


def bag_limit(fl):
    legs = [f for f in fl if foreign(f["a"]) != foreign(f["b"])]
    if not legs:
        return 720
    return 1800 if max(block(f["a"], f["b"]) for f in legs) > 720 else 900


def bag(w, legs, delay, tags, expected=None, *, door_late=12, mbr=True, lost=False, fees=(3500,), linked=True,
        which=0, exemption=None, subscription=None, pay=None):
    """delay: minutes from the door opening at the final destination to delivery."""
    fl = [w.flight(x[0], x[1], x[2], x[3] if len(x) > 3 else None) for x in legs]
    t = w.ticket(fl, fl[0]["versions"][0][1] - timedelta(days=21, hours=2), pay=pay)
    t["bag_fee_subscription"] = subscription
    door = fl[-1]["versions"][-1][2] + mins(door_late)
    fl[-1]["door"] = door
    bags = [{"bag_tag": f"LS{rng.randrange(100000, 999999)}", "fee_cents": fee,
             "fee_linked_to_this_bag_by_unique_identifier": linked} for fee in fees]
    tag = bags[which]["bag_tag"]
    lim = bag_limit(fl)
    ev = []
    if mbr:
        ev.append({"at": door + mins(35), "type": "mishandled_baggage_report", "bag_tag": tag})
    if lost:
        ev.append({"at": door + timedelta(days=5), "type": "bag_declared_lost", "bag_tag": tag})
    else:
        ev.append({"at": door + mins(delay), "type": "bag_delivered", "bag_tag": tag})
    if exemption:
        ev.append({"at": door + mins(20), "type": exemption, "bag_tag": tag})
    req = door + mins(lim + 1) if (lost or delay > lim) else door + mins(delay)
    return w.add("baggage", t, ev, (), bags, req, tags, expected, req.date().isoformat())


def service(w, legs, items, tags, expected=None, pay=None, fault=False):
    fl = [w.flight(x[0], x[1], x[2]) for x in legs]
    t = w.ticket(fl, fl[0]["versions"][0][1] - timedelta(days=12), pay=pay)
    dep = fl[0]["versions"][-1][1]
    ev = [{"at": dep + mins(40), "type": "service_failure", "coupon": 1, "through_fault_of_consumer": fault}]
    return w.add("ancillary_service_not_provided", t, ev, items, (), dep + mins(300), tags, expected,
                 (dep + mins(300)).date().isoformat())


def day(t):
    return t.date().isoformat()


# ---------------------------------------------------------------- planted, hand-worked claims -------------------
def planted(w):
    # ---------------- denied boarding: bands, caps, fare base (250.5) ----------------------------------------
    # ORD-LGA scheduled 13:00Z, arrives 15:15Z. A replacement planned 60 min late owes nothing; 61 to 119 min
    # owes 200%; 120 min or more owes 400% (domestic). Fare 249.00.
    oversale(w, [("ORD", "LGA", T(5, 13))], 1, 60, ["db-band", "domestic"], (0, 0), fares=[24900])
    oversale(w, [("ORD", "LGA", T(5, 14))], 1, 61, ["db-band", "domestic"], (49800, 0), fares=[24900])
    oversale(w, [("ORD", "LGA", T(5, 15))], 1, 119, ["db-band", "domestic"], (49800, 0), fares=[24900])
    oversale(w, [("ORD", "LGA", T(5, 16))], 1, 120, ["db-band", "domestic"], (99600, 0), fares=[24900])
    # caps: 2 x 619.00 = 1238.00 -> 1075.00; 4 x 619.00 = 2476.00 -> 2150.00
    oversale(w, [("ORD", "DEN", T(6, 13))], 1, 95, ["db-band", "db-cap"], (107500, 0), fares=[61900])
    oversale(w, [("ORD", "DEN", T(6, 14))], 1, 300, ["db-band", "db-cap"], (215000, 0), fares=[61900])
    # foreign air transportation: 200% up to (not including) 4 h, 400% from 4 h
    oversale(w, [("ORD", "LHR", T(7, 22), WIDE)], 1, 200, ["db-band", "international"], (97400, 0), fares=[48700])
    oversale(w, [("ORD", "LHR", T(8, 22), WIDE)], 1, 240, ["db-band", "international"], (194800, 0), fares=[48700])
    oversale(w, [("ORD", "YYZ", T(9, 12))], 1, 150, ["db-band", "international"], (42600, 0), fares=[21300])
    # nothing arranged at all: 400%
    oversale(w, [("ORD", "BOS", T(9, 15))], 1, None, ["db-band", "no-alternate"], (70400, 0), fares=[17600])
    # MSP-ORD 12:00-13:25Z, ORD-LHR 15:00Z (95 min connection): fare to London 159.00 + 312.00 = 471.00,
    # replacement 210 min late at LHR, international: 200% = 942.00
    oversale(w, [("MSP", "ORD", T(10, 12)), ("ORD", "LHR", T(10, 15), WIDE)], 1, 210,
             ["db-fare-base", "international"], (94200, 0), fares=[15900, 31200])
    # stopover (> 4 h) at Denver: fare to Denver only, 188.00; 130 min late, domestic: 400% = 752.00
    oversale(w, [("ORD", "DEN", T(11, 13)), ("DEN", "SFO", T(12, 15))], 1, 130, ["db-fare-base", "stopover"],
             (75200, 0), fares=[18800, 14200])
    # exactly 4 h at Denver is not a stopover: fare 188.00 + 142.00 = 330.00, 70 min late: 200% = 660.00
    oversale(w, [("ORD", "DEN", T(13, 12)), ("DEN", "SFO", T(13, 12) + mins(160 + 240))], 1, 70,
             ["db-fare-base", "stopover"], (66000, 0), fares=[18800, 14200])
    # round trip: the return is not part of the fare to destination; 100 min late: 200% of 176.00
    oversale(w, [("ORD", "BOS", T(14, 13)), ("BOS", "ORD", T(18, 20))], 1, 100, ["db-fare-base", "round-trip"],
             (35200, 0), fares=[17600, 17600])
    # MSP-ORD 12:00-13:25Z, ORD-LGA 14:30-16:45Z; replaced by a MSP-LGA nonstop arriving 18:50Z, 125 min late:
    # fare 129.00 + 189.00 = 318.00, 400% = 1272.00
    oversale(w, [("MSP", "ORD", T(20, 12)), ("ORD", "LGA", T(20, 14, 30))], 1, 125, ["db-fare-base", "domestic"],
             (127200, 0), fares=[12900, 18900], alt_nonstop=True)
    # award ticket: lowest cash fare in the cabin on that flight (139.00); 140 min late: 400% = 556.00
    cid = oversale(w, [("ORD", "ATL", T(15, 13))], 1, 140, ["db-fare-base", "zero-fare"], zero=True)
    f = w.flights[w.claims[-1]["ticket"]["coupons"][0]["flight_id"]]
    f["low"]["economy"] = 13900
    w.golden[cid] = {"compensation": "556.00", "refund": "0.00", "refund_due_date": "none"}
    # the replacement's planned arrival is the one planned when it was arranged: 110 min late then (200%),
    # 150 min late after a later schedule change (which does not count)
    oversale(w, [("ORD", "LGA", T(16, 18))], 1, 110, ["db-band", "db-arranged"], (49800, 0), fares=[24900],
             alt_later=40)
    oversale(w, [("ORD", "LHR", T(16, 22), WIDE)], 1, 250, ["db-band", "db-arranged", "international"],
             (194800, 0), fares=[48700], alt_later=-30)

    # ---------------- denied boarding: exceptions and scope (250.2, 250.2b, 250.6) --------------------------
    oversale(w, [("ORD", "LGA", T(17, 13))], 1, 300, ["db-exception", "volunteer"], (0, 0), fares=[24900],
             volunteer=True)
    # accepting the offered compensation does not make an involuntary passenger a volunteer (250.2b(a))
    oversale(w, [("ORD", "LGA", T(17, 15))], 1, 130, ["db-exception", "accepted-offer"], (99600, 0),
             fares=[24900], accepted_offer=True)
    # check-in closes 45 min before a domestic departure and 60 min before an international one
    oversale(w, [("ORD", "LGA", T(18, 13))], 1, 300, ["db-exception", "check-in"], (0, 0), fares=[24900], checkin=44)
    oversale(w, [("ORD", "LGA", T(18, 15))], 1, 300, ["db-exception", "check-in"], (99600, 0), fares=[24900],
             checkin=45)
    oversale(w, [("ORD", "LHR", T(18, 22), WIDE)], 1, 300, ["db-exception", "check-in"], (0, 0), fares=[48700],
             checkin=59)
    oversale(w, [("ORD", "LHR", T(19, 22), WIDE)], 1, 300, ["db-exception", "check-in", "international"],
             (194800, 0), fares=[48700], checkin=60)
    oversale(w, [("ORD", "LGA", T(19, 13))], 1, 300, ["db-exception", "equipment"], (0, 0), fares=[24900],
             reason="aircraft_substitution", ops=True,
             sub={"scheduled_aircraft": "Airbus A321neo", "scheduled_designed_passenger_seats": 196})
    oversale(w, [("ORD", "LGA", T(19, 15))], 1, 300, ["db-exception", "equipment"], (99600, 0), fares=[24900],
             reason="aircraft_substitution", ops=False,
             sub={"scheduled_aircraft": "Airbus A321neo", "scheduled_designed_passenger_seats": 196})
    oversale(w, [("ORD", "MSP", T(21, 13), ("Embraer E145", 50))], 1, 300, ["db-exception", "weight-balance"], (0, 0),
             fares=[15900], reason="weight_balance_restriction", ops=True)
    oversale(w, [("ORD", "MSP", T(21, 15), ("Embraer E175", 76))], 1, 300, ["db-exception", "weight-balance"],
             (63600, 0), fares=[15900], reason="weight_balance_restriction", ops=True)
    oversale(w, [("ORD", "LGA", T(22, 13))], 1, 300, ["db-exception", "other-cabin"], (0, 0), fares=[24900],
             reseat="first")
    oversale(w, [("ORD", "MKE", T(22, 15), ("Beechcraft 1900D", 19))], 1, 300, ["db-applicability"], (0, 0),
             fares=[9900])
    oversale(w, [("CUN", "ORD", T(22, 18))], 1, 300, ["db-applicability"], (0, 0), fares=[33900])

    # ---------------- denied boarding: unused paid extras (250.5(f)) ---------------------------------------
    oversale(w, [("ORD", "SFO", T(23, 14))], 1, 150, ["db-ancillary"], (119600, 4500), fares=[29900],
             pay="credit_card", ancillary=[anc("advance_seat_selection", 4500, 1, False), anc("wifi", 1200, 1, True),
                                           anc("first_checked_bag", 3500, 1, True)])
    oversale(w, [("ORD", "SFO", T(24, 14))], 1, 40, ["db-ancillary", "volunteer"], (0, 7000), fares=[29900],
             pay="debit_card", volunteer=True,
             ancillary=[anc("advance_seat_selection", 4500, 1, False), anc("priority_boarding", 2500, 1, False)])

    # ---------------- denied boarding across the 2026 clock changes ---------------------------------------
    # DEN-ORD leaves 02:40Z Nov 1, arrives 05:20Z (00:20 CDT); replacement arrives 08:10Z (02:10 CST):
    # 2 h 50 m late, 400% of 233.00 = 932.00 (the wall clocks show 1 h 50 m)
    oversale(w, [("DEN", "ORD", T(32, 2, 40))], 1, 170, ["db-band", "dst"], (93200, 0), fares=[23300])
    # ORD-DEN arrives 05:40Z (23:40 MDT Oct 31); DEN-SFO leaves 10:00Z (03:00 MST): 4 h 20 m is a stopover,
    # so the fare runs to Denver only (188.00); replacement 300 min late: 400% = 752.00
    oversale(w, [("ORD", "DEN", T(32, 3, 0)), ("DEN", "SFO", T(32, 10, 0))], 1, 300,
             ["db-fare-base", "stopover", "dst"], (75200, 0), fares=[18800, 14200])
    # check-in at 16:45Z for a 17:30Z ORD-LGA departure on Nov 3 (11:30 CST): 45 min before, on time
    oversale(w, [("ORD", "LGA", T(34, 17, 30))], 1, 61, ["db-exception", "check-in", "time-zone"], (39800, 0),
             fares=[19900], checkin=45)

    # ---------------- cancellations and significant changes (260.2, 260.6) ---------------------------------
    def rday(dep, before=timedelta(days=3, hours=1), after=20):     # date of a reply 20 h after the notice
        return day(dep - before + timedelta(hours=after))

    def nday(dep, before=timedelta(days=3, hours=1)):
        return day(dep - before)

    fare = [21800]
    a1 = [anc("advance_seat_selection", 3900, 1, False), anc("first_checked_bag", 3500, 1, False)]
    D = T(25, 13)
    later = lambda m: (D + mins(m))  # noqa: E731
    # cancelled ORD-LGA, rebooking offered and declined: fare 218.00 + extras 74.00, from the reply date
    change(w, [("ORD", "LGA", D)], [{"cancel": [0], "itinerary": [("ORD", "LGA", later(300))]}],
           "declined_offer", ["sc-cancel"], (0, 29200), rday(D), fares=fare, ancillary=a1)
    D2 = T(25, 15)
    # rebooking accepted: only the unused seat fee (39.00), from the request made at the notice
    change(w, [("ORD", "LGA", D2)], [{"cancel": [0], "itinerary": [("ORD", "LGA", D2 + mins(240))]}],
           "accepted_offered_itinerary", ["sc-cancel", "sc-accepted"], (0, 3900), nday(D2), fares=fare,
           ancillary=[anc("advance_seat_selection", 3900, 1, False), anc("first_checked_bag", 3500, 1, True)],
           requested="notice")
    D3 = T(25, 17)
    # voucher accepted: the unused extras are still refunded (260.4)
    change(w, [("ORD", "LGA", D3)], [{"cancel": [0], "itinerary": None, "voucher": True}], "accepted_voucher",
           ["sc-cancel", "sc-voucher"], (0, 7400), nday(D3), fares=fare, ancillary=a1, requested="notice")
    D4 = T(26, 13)
    # voucher offer never answered: due from the day the cancelled flight was to depart
    change(w, [("ORD", "LGA", D4)], [{"cancel": [0], "itinerary": None, "voucher": True}], None,
           ["sc-cancel", "sc-voucher", "due-date"], (0, 29200), day(D4), fares=fare, ancillary=a1)
    D5 = T(26, 15)
    # nothing offered: due from the cancellation notice, not from the later request
    change(w, [("ORD", "LGA", D5)], [{"cancel": [0], "itinerary": None}], None, ["sc-cancel", "due-date"],
           (0, 21800), nday(D5), fares=fare, requested=D5 + timedelta(days=4))
    # retimed: arrival 180 min later is significant (domestic), 175 min is not
    D6 = T(27, 13)
    change(w, [("ORD", "LGA", D6)], [{"retime": [(0, 180, 180)], "itinerary": [0]}], "declined_offer",
           ["sc-delay", "sc-threshold", "domestic"], (0, 21800), rday(D6), fares=fare)
    D7 = T(27, 15)
    change(w, [("ORD", "LGA", D7)], [{"retime": [(0, 175, 175)], "itinerary": [0]}], "declined_offer",
           ["sc-delay", "sc-threshold", "domestic"], (0, 0), fares=fare)
    # declining a change that is not significant: the unused extra was the passenger's own choice
    D8 = T(27, 17)
    change(w, [("ORD", "LGA", D8)], [{"retime": [(0, 120, 120)], "itinerary": [0]}], "declined_offer",
           ["sc-delay", "sc-not-significant"], (0, 0), fares=fare, ancillary=[anc("first_checked_bag", 3500, 1, False)],
           requested=D8 - timedelta(days=1))
    # departure 180 min earlier is significant
    D9 = T(28, 13)
    change(w, [("ORD", "LGA", D9)], [{"retime": [(0, -180, -180)], "itinerary": [0]}], "declined_offer",
           ["sc-earlier", "sc-threshold", "domestic"], (0, 21800), rday(D9), fares=fare)
    # departure 185 min later but arrival only 175 min later: a later departure is not one of the tests
    D10 = T(28, 15)
    change(w, [("ORD", "LGA", D10)], [{"retime": [(0, 185, 175)], "itinerary": [0]}], "declined_offer",
           ["sc-delay", "sc-threshold"], (0, 0), fares=fare)
    # international itinerary: 6 h
    D11 = T(28, 22)
    change(w, [("ORD", "LHR", D11, WIDE)], [{"retime": [(0, 300, 300)], "itinerary": [0]}], "declined_offer",
           ["sc-delay", "sc-threshold", "international"], (0, 0), fares=[55600])
    D12 = T(29, 22)
    change(w, [("ORD", "LHR", D12, WIDE)], [{"retime": [(0, 360, 360)], "itinerary": [0]}], "declined_offer",
           ["sc-delay", "sc-threshold", "international"], (0, 55600), rday(D12), fares=[55600])
    D13 = T(29, 13)
    change(w, [("ORD", "YYZ", D13)], [{"retime": [(0, 240, 240)], "itinerary": [0]}], "declined_offer",
           ["sc-delay", "sc-threshold", "international"], (0, 0), fares=[19900])
    # the change is measured from the itinerary as bought, through every later notice: +120 then +70 = 190
    D14 = T(30, 13)
    change(w, [("ORD", "LGA", D14)], [{"before": timedelta(days=9), "retime": [(0, 120, 120)], "itinerary": [0]},
                                      {"retime": [(0, 70, 70)], "itinerary": [0]}], "declined_offer",
           ["sc-delay", "sc-cumulative"], (0, 21800), rday(D14), fares=fare)
    # +120 then +50 = 170: not significant
    D15 = T(30, 15)
    change(w, [("ORD", "LGA", D15)], [{"before": timedelta(days=9), "retime": [(0, 120, 120)], "itinerary": [0]},
                                      {"retime": [(0, 50, 50)], "itinerary": [0]}], "declined_offer",
           ["sc-delay", "sc-cumulative"], (0, 0), fares=fare)
    # schedule moved +120 before the ticket was bought; the notice adds +150: 150 from the itinerary as bought
    D16 = T(31, 13)
    change(w, [("ORD", "LGA", D16)], [{"retime": [(0, 150, 150)], "itinerary": [0]}], "declined_offer",
           ["sc-delay", "sc-as-bought"], (0, 0), fares=fare, pre=[(0, D16 - timedelta(days=60), 120, 120)])
    # moved -100 before purchase, then +190: significant (+90 against the first published time)
    D17 = T(31, 16)
    change(w, [("ORD", "BOS", D17)], [{"retime": [(0, 190, 190)], "itinerary": [0]}], "declined_offer",
           ["sc-delay", "sc-as-bought"], (0, 18400), rday(D17), fares=[18400],
           pre=[(0, D17 - timedelta(days=55), -100, -100)])
    # whole-itinerary test. MSP-ORD 12:00-13:25Z, ORD-LGA 15:00-17:15Z. MSP-ORD retimed +240 (arrives 17:25Z),
    # rebooked on ORD-LGA 17:55-20:10Z: arrival 175 min later, not significant
    D18 = T(33, 12)
    change(w, [("MSP", "ORD", D18), ("ORD", "LGA", D18 + mins(180))],
           [{"retime": [(0, 240, 240)], "itinerary": [0, ("ORD", "LGA", D18 + mins(355))]}], "declined_offer",
           ["sc-itinerary", "sc-delay"], (0, 0), fares=[12900, 18900])
    # same, with the new ORD-LGA arriving 180 min after the original arrival: significant, 129.00 + 189.00
    D19 = T(33, 14)
    change(w, [("MSP", "ORD", D19), ("ORD", "LGA", D19 + mins(180))],
           [{"retime": [(0, 240, 240)], "itinerary": [0, ("ORD", "LGA", D19 + mins(360))]}], "declined_offer",
           ["sc-itinerary", "sc-delay"], (0, 31800), rday(D19), fares=[12900, 18900])
    # ORD-LGA second leg moved 200 min earlier, first leg 150 min earlier: departure from origin 150 earlier
    D20 = T(34, 13)
    change(w, [("MSP", "ORD", D20), ("ORD", "LGA", D20 + mins(180))],
           [{"retime": [(0, -150, -150), (1, -200, -200)], "itinerary": [0, 1]}], "declined_offer",
           ["sc-itinerary", "sc-earlier"], (0, 0), fares=[12900, 18900])
    # misconnect rebooked via another hub, same number of connections, 40 min later: not significant
    D21 = T(35, 13)
    change(w, [("ORD", "DEN", D21), ("DEN", "SFO", D21 + mins(250))],
           [{"retime": [(0, 200, 200)], "itinerary": [("ORD", "DFW", D21), ("DFW", "SFO", D21 + mins(210))]}],
           "declined_offer", ["sc-itinerary", "sc-connection"], (0, 0), fares=[18800, 14200])
    # ... but an extra connection point is significant even though it arrives only 145 min later
    D22 = T(35, 16)
    change(w, [("ORD", "DEN", D22), ("DEN", "SFO", D22 + mins(250))],
           [{"retime": [(0, 200, 200)], "itinerary": [("ORD", "DFW", D22 + mins(20)), ("DFW", "PHX", D22 + mins(240)),
                                                         ("PHX", "SFO", D22 + mins(430))]}],
           "declined_offer", ["sc-itinerary", "sc-connection"], (0, 33000), rday(D22), fares=[18800, 14200])
    # rebooked to Newark instead of LaGuardia, 40 min later: a different destination airport is significant
    D23 = T(36, 12)
    change(w, [("DEN", "ORD", D23), ("ORD", "LGA", D23 + mins(250))],
           [{"retime": [(0, 150, 150)], "itinerary": [0, ("ORD", "EWR", D23 + mins(295))]}], "declined_offer",
           ["sc-airport"], (0, 30400), rday(D23), fares=[14600, 15800])
    # downgraded from first to economy on the changed flight
    D24 = T(36, 15)
    change(w, [("ORD", "BOS", D24)], [{"retime": [(0, 30, 30)], "itinerary": [(0, "economy")]}],
           "declined_offer", ["sc-downgrade"], (0, 68900), rday(D24), fares=[68900], cabin="first")
    # a cancelled leg is a cancellation even when the rebooking arrives 30 min later
    D25 = T(37, 13)
    change(w, [("MSP", "ORD", D25), ("ORD", "BOS", D25 + mins(150))],
           [{"cancel": [1], "itinerary": [0, ("ORD", "BOS", D25 + mins(180))]}], "declined_offer",
           ["sc-cancel", "sc-itinerary"], (0, 33100), rday(D25), fares=[12900, 20200])
    # international itinerary through a U.S. hub: MSP-ORD-LHR arrives 330 min late: under 6 h
    D26 = T(38, 15)
    change(w, [("MSP", "ORD", D26), ("ORD", "LHR", D26 + mins(180), WIDE)],
           [{"retime": [(0, 300, 300)], "itinerary": [0, ("ORD", "LHR", D26 + mins(510), WIDE)]}], "declined_offer",
           ["sc-itinerary", "international"], (0, 0), fares=[13900, 46100])
    D27 = T(39, 15)
    change(w, [("MSP", "ORD", D27), ("ORD", "LHR", D27 + mins(180), WIDE)],
           [{"retime": [(0, 300, 300)], "itinerary": [0, ("ORD", "LHR", D27 + mins(540), WIDE)]}], "declined_offer",
           ["sc-itinerary", "international"], (0, 60000), rday(D27), fares=[13900, 46100])
    # flew on the changed flight: accepted, nothing unused
    D28 = T(40, 13)
    change(w, [("ORD", "BOS", D28)], [{"retime": [(0, 240, 240)], "itinerary": [0]}], "boarded",
           ["sc-delay", "sc-accepted"], (0, 0), fares=[18400], ancillary=[anc("advance_seat_selection", 3900, 1, True)])
    # no answer and the changed flight left: counted from the UTC day it departed. ORD-BOS 22:30Z + 200 min
    # = 01:50Z next day; 184.00 + seat 39.00, debit card, 20 days
    D29 = T(40, 22, 30)
    change(w, [("ORD", "BOS", D29)], [{"retime": [(0, 200, 200)], "itinerary": [0]}], None,
           ["sc-delay", "due-date"], (0, 22300), day(D29 + mins(200)), fares=[18400], pay="debit_card",
           ancillary=[anc("advance_seat_selection", 3900, 1, False)], requested=D29 + timedelta(days=3))
    # a later written request does not move the start: the rejection came first
    D30 = T(41, 13)
    change(w, [("ORD", "DFW", D30)], [{"cancel": [0], "itinerary": [("ORD", "DFW", D30 + mins(300))]}],
           "declined_offer", ["sc-cancel", "due-date"], (0, 26100), rday(D30), fares=[26100], pay="credit_card",
           requested=D30 + timedelta(days=6))
    # a written request before the rejection moves the start earlier
    D31 = T(41, 23)
    change(w, [("ORD", "DFW", D31)], [{"cancel": [0], "itinerary": [("ORD", "DFW", D31 + mins(300))]}],
           "declined_offer", ["sc-cancel", "due-date"], (0, 26100), nday(D31), fares=[26100], pay="credit_card",
           requested=D31 - timedelta(days=3, hours=1) + mins(40), reply_after=50)
    # voucher offer unanswered for a cancelled second leg: due from the day that leg was to depart.
    # MSP-ORD 22:00-23:25Z Nov 15, ORD-LGA 00:30Z Nov 16 (cancelled): from 2026-11-16, credit card
    D32 = T(46, 22)
    change(w, [("MSP", "ORD", D32), ("ORD", "LGA", D32 + mins(150))],
           [{"cancel": [1], "itinerary": None, "voucher": True}], None, ["sc-cancel", "sc-voucher", "due-date"],
           (0, 31800), "2026-11-16", fares=[12900, 18900], pay="credit_card")
    # retimed across the U.S. clock change: ORD-LGA arrives 04:30Z Nov 1 (00:30 EDT); new arrival 07:30Z
    # (02:30 EST) is 3 h later, significant; the wall clocks show 2 h
    D33 = T(32, 2, 15)
    change(w, [("ORD", "LGA", D33)], [{"retime": [(0, 180, 180)], "itinerary": [0]}], "declined_offer",
           ["sc-delay", "sc-threshold", "dst"], (0, 21800), rday(D33), fares=[21800])
    # voucher unanswered for ORD-DFW leaving 01:30Z Nov 1 (20:30 CDT Oct 31): from 2026-11-01, debit card
    D34 = T(32, 1, 30)
    change(w, [("ORD", "DFW", D34)], [{"cancel": [0], "itinerary": None, "voucher": True}], None,
           ["sc-cancel", "due-date", "time-zone"], (0, 26100), "2026-11-01", fares=[26100], pay="debit_card")
    # Phoenix keeps standard time: PHX-DEN leaves 14:00Z (07:00 MST), arrives 15:45Z; retimed +180/+180
    D35 = T(36, 14)
    change(w, [("PHX", "DEN", D35)], [{"retime": [(0, 180, 180)], "itinerary": [0]}], "declined_offer",
           ["sc-delay", "sc-threshold", "time-zone"], (0, 16400), rday(D35), fares=[16400])

    # ---------------- covered flights: break in journey at a foreign point (260.2) ---------------------------
    def euro(gap, notice, tags, expected, reply="declined_offer", inbound=False, first=T(50, 22)):
        if not inbound:
            legs = [("ORD", "LHR", first, WIDE), ("LHR", "FRA", first + mins(block("ORD", "LHR") + gap))]
        else:
            legs = [("FRA", "LHR", first), ("LHR", "ORD", first + mins(block("LHR", "FRA") + gap), WIDE)]
        before = timedelta(days=5, hours=1) - (mins(block("ORD", "LHR") + gap) if not inbound else timedelta(0))
        n = dict(notice, before=before)
        dep = legs[1][2] if not inbound else legs[0][2]
        return change(w, legs, [n], reply, tags, expected, rday(dep, timedelta(days=5, hours=1)),
                      fares=[48700, 14900])

    first = T(50, 22)
    cx2 = {"cancel": [1], "itinerary": [0, ("LHR", "FRA", first + mins(485 + 180 + 300))]}
    euro(180, cx2, ["sc-covered", "break-in-journey"], (0, 63600))
    cx2 = {"cancel": [1], "itinerary": [0, ("LHR", "FRA", first + mins(485 + 3 * 1440 + 300))]}
    euro(3 * 1440, cx2, ["sc-covered", "break-in-journey"], (0, 0))
    cx2 = {"cancel": [1], "itinerary": [0, ("LHR", "FRA", first + mins(485 + 1440 + 300))]}
    euro(1440, cx2, ["sc-covered", "break-in-journey"], (0, 63600))
    cx2 = {"cancel": [1], "itinerary": [0, ("LHR", "FRA", first + mins(485 + 1445 + 300))]}
    euro(1445, cx2, ["sc-covered", "break-in-journey"], (0, 0))
    cx1 = {"cancel": [0], "itinerary": [("FRA", "LHR", first + mins(240)), 1]}
    euro(2 * 1440, cx1, ["sc-covered", "break-in-journey"], (0, 0), inbound=True)
    euro(150, {"retime": [(1, 0, 400)], "itinerary": [0, 1]}, ["sc-covered", "break-in-journey", "sc-delay"],
         (0, 63600))
    euro(2 * 1440, {"retime": [(1, 0, 400)], "itinerary": [0, 1]}, ["sc-covered", "break-in-journey", "sc-delay"],
         (0, 0))
    # ORD-LHR arrives 06:00Z Oct 24 (07:00 BST); LHR-FRA leaves 07:00Z Oct 25 (07:00 GMT): the stopover is
    # 25 h, a break in journey, so the LHR-FRA cancellation is not a covered flight (the wall clocks show 24 h)
    legs = [("ORD", "LHR", T(23, 21, 55), WIDE), ("LHR", "FRA", T(25, 7, 0))]
    change(w, legs, [{"before": timedelta(days=2), "cancel": [1], "itinerary": [0, ("LHR", "FRA", T(25, 12, 0))]}],
           "declined_offer", ["sc-covered", "break-in-journey", "dst"], (0, 0), fares=[48700, 14900])

    # ---------------- bags (260.2, 260.5) ---------------------------------------------------------------------
    bag(w, [("ORD", "LGA", T(42, 13))], 720, ["bag-threshold", "domestic"], (0, 0))
    bag(w, [("ORD", "LGA", T(42, 15))], 721, ["bag-threshold", "domestic"], (0, 3500))
    # the delay runs from the door opening (the chance to deplane), not from the scheduled arrival
    bag(w, [("ORD", "LGA", T(43, 13))], 700, ["bag-threshold", "bag-deplane"], (0, 0), door_late=50)
    bag(w, [("ORD", "BOS", T(43, 15))], 730, ["bag-threshold", "bag-deplane"], (0, 3500), door_late=-20)
    bag(w, [("ORD", "LHR", T(44, 22), WIDE)], 800, ["bag-threshold", "international"], (0, 0), fees=(7500,))
    bag(w, [("ORD", "LHR", T(44, 23), WIDE)], 901, ["bag-threshold", "international"], (0, 7500), fees=(7500,))
    bag(w, [("ORD", "LHR", T(45, 22), WIDE)], 900, ["bag-threshold", "international"], (0, 0), fees=(7500,))
    bag(w, [("ORD", "NRT", T(45, 23), WIDE)], 1500, ["bag-threshold", "long-haul"], (0, 0), fees=(10000,))
    bag(w, [("ORD", "NRT", T(46, 1), WIDE)], 1801, ["bag-threshold", "long-haul"], (0, 10000), fees=(10000,))
    bag(w, [("MSP", "ORD", T(46, 13)), ("ORD", "NRT", T(46, 16), WIDE)], 1700,
        ["bag-threshold", "long-haul", "domestic-leg"], (0, 0), fees=(10000,))
    # Chicago-Frankfurt is 8 h 40 m and Chicago-London 8 h 05 m (14 h 40 m and 14 h 05 m on the wall clocks)
    bag(w, [("ORD", "FRA", T(27, 22), WIDE)], 1000, ["bag-threshold", "international", "time-zone"], (0, 7500),
        fees=(7500,))
    bag(w, [("ORD", "LHR", T(28, 22), WIDE)], 1300, ["bag-threshold", "international", "time-zone"], (0, 7500),
        fees=(7500,))
    # Honolulu is domestic (12 h) however long the flight
    bag(w, [("ORD", "HNL", T(47, 15), WIDE)], 721, ["bag-threshold", "domestic", "time-zone"], (0, 4000),
        fees=(4000,))
    bag(w, [("ORD", "LGA", T(47, 13))], 2000, ["bag-mbr"], (0, 0), mbr=False)
    bag(w, [("ORD", "LGA", T(47, 15))], 0, ["bag-lost"], (0, 3500), lost=True)
    bag(w, [("ORD", "LGA", T(48, 13))], 900, ["bag-amount", "escalated"], (0, 4500), fees=(3500, 4500), linked=True,
        which=1)
    bag(w, [("ORD", "LGA", T(48, 15))], 900, ["bag-amount", "escalated"], (0, 4500), fees=(3500, 4500), linked=False,
        which=0)
    bag(w, [("ORD", "LGA", T(49, 13))], 900, ["bag-amount", "escalated"], (0, 3500), fees=(3500, 4500), linked=True,
        which=0)
    bag(w, [("ORD", "LGA", T(49, 15))], 900, ["bag-amount", "subscription"], (0, 3500), fees=(0,),
        subscription={"subscribed": True, "lowest_fee_charged_to_non_subscriber_same_status_and_cabin_cents": 3500})
    bag(w, [("LHR", "ORD", T(50, 13), WIDE), ("ORD", "DEN", T(50, 23))], 1600, ["bag-exemption", "customs"], (0, 0),
        fees=(7500,), exemption="passenger_did_not_reclaim_and_recheck_bag_at_first_us_entry_point")
    bag(w, [("ORD", "LGA", T(51, 13))], 900, ["bag-exemption", "voluntary"], (0, 0),
        exemption="passenger_agreed_to_travel_without_bag_after_missing_check_in_time")
    bag(w, [("ORD", "LGA", T(51, 15))], 900, ["bag-exemption", "hidden-city"], (0, 0),
        exemption="passenger_ended_travel_before_ticketed_final_destination")

    # ---------------- ancillary services not provided (260.4) ----------------------------------------------
    service(w, [("ORD", "SFO", T(52, 14))], [anc("wifi", 1900, 1, False), anc("advance_seat_selection", 4900, 1, True)],
            ["ancillary"], (0, 1900))
    service(w, [("ORD", "SFO", T(52, 16))], [anc("advance_seat_selection", 4900, 1, False)], ["ancillary"], (0, 4900))
    service(w, [("ORD", "SFO", T(53, 14))], [anc("lounge_access", 5900, 1, False)], ["ancillary", "fault"], (0, 0),
            fault=True)


# ---------------------------------------------------------------- filler ---------------------------------------
DOM_NONSTOP = [("ORD", "LGA"), ("ORD", "BOS"), ("ORD", "ATL"), ("ORD", "DFW"), ("ORD", "DEN"), ("ORD", "SFO"),
               ("ORD", "SEA"), ("ORD", "LAX"), ("ORD", "PHX"), ("ORD", "HNL"), ("DEN", "SFO"), ("DFW", "LAX"),
               ("ATL", "LGA"), ("DEN", "PHX"), ("MSP", "SEA"), ("DFW", "PHX"), ("LAX", "HNL")]
INTL_NONSTOP = [("ORD", "LHR"), ("ORD", "FRA"), ("ORD", "NRT"), ("ORD", "YYZ"), ("ORD", "CUN"), ("DFW", "CUN"),
                ("SEA", "NRT"), ("ATL", "CUN"), ("MSP", "YYZ")]
CONNECT = [("MSP", "ORD", "LGA"), ("MSP", "ORD", "BOS"), ("DEN", "ORD", "BOS"), ("ORD", "DEN", "SFO"),
           ("ORD", "DEN", "SEA"), ("ATL", "DFW", "LAX"), ("ATL", "DEN", "SFO"), ("MSP", "ORD", "LHR"),
           ("DEN", "ORD", "FRA"), ("ATL", "ORD", "NRT"), ("DFW", "ORD", "YYZ"), ("DFW", "ATL", "BOS"),
           ("ORD", "DFW", "CUN"), ("PHX", "DEN", "ORD"), ("LAX", "DEN", "ORD"), ("SFO", "DEN", "ATL"),
           ("ORD", "PHX", "LAX"), ("BOS", "ORD", "DEN")]


def hubs(a, b, avoid):
    return [h for h in AIRPORTS if h not in (a, b) and h not in avoid and has_block(a, h) and has_block(h, b)
            and not foreign(h)]


def pick_dep():
    if rng.random() < 0.4:      # around the EU (Oct 25 01:00Z) and US (Nov 1, 06:00-09:00Z) clock changes
        base = rng.choice([T(24, 16), T(25, 0), T(31, 16), T(32, 0), T(32, 6)])
        return base + mins(rng.randrange(0, 10 * 60, 5))
    return T(rng.randint(5, 60), rng.randrange(0, 24), rng.choice([0, 10, 20, 30, 40, 50]))


def gen_sig(orig, offered, purchased, at, cancelled, cabin):
    if cancelled:
        return True
    if offered is None:
        return False
    intl = any(foreign(f["a"]) or foreign(f["b"]) for f in orig)
    lim = mins(360 if intl else 180)
    od, oa = sched(orig[0], purchased)[0], sched(orig[-1], purchased)[1]
    nd, na = sched(offered[0][0], at)[0], sched(offered[-1][0], at)[1]
    return (od - nd >= lim or na - oa >= lim or offered[0][0]["a"] != orig[0]["a"]
            or offered[-1][0]["b"] != orig[-1]["b"] or len(offered) > len(orig)
            or any(CABINS.index(c) > CABINS.index(cabin) for _, c in offered))


def near(intl):
    if intl:
        return rng.choice([240, 300, 330, 350, 355, 360, 360, 365, 380, 420, -300, -355, -360, -365, -380])
    return rng.choice([60, 120, 150, 170, 175, 175, 180, 180, 185, 190, 200, 240, -150, -175, -180, -185, -200])


def filler_change(w):
    cabin = "first" if rng.random() < 0.12 else "economy"
    dep1 = pick_dep()
    if rng.random() < 0.4:
        a, b = rng.choice(DOM_NONSTOP + INTL_NONSTOP)
        legs = [(a, b, dep1)]
    else:
        a, h, b = rng.choice(CONNECT)
        legs = [(a, h, dep1), (h, b, dep1 + mins(block(a, h) + rng.choice([45, 60, 75, 90, 120, 150, 200])))]
    fl = [w.flight(x[0], x[1], x[2]) for x in legs]
    intl = any(foreign(f["a"]) or foreign(f["b"]) for f in fl)
    purchased = dep1 - timedelta(days=rng.randint(20, 80), minutes=rng.randrange(0, 1440))
    if rng.random() < 0.35:            # a schedule change before the ticket was bought
        p = rng.choice([-120, -90, -60, -45, 45, 60, 90, 120, 150])
        rec = purchased - timedelta(days=rng.randint(2, 15), minutes=rng.randrange(0, 1440))
        for f in fl:
            w.retime(f, rec, p)
    t = w.ticket(fl, purchased, cabin)
    notice_at = dep1 - timedelta(days=rng.choice([1, 2, 4, 6]), hours=rng.randrange(1, 20))
    ev, cancelled, voucher = [], False, False
    scen = rng.choice(["retime"] * 3 + ["split"] * 2 + ["cumulative"] * 2 + ["cancel"] * 2 + ["late_leg"] * 3 +
                      ["reroute"] * 2 + ["earlier_leg", "extra", "downgrade"])
    if scen in ("late_leg", "reroute", "earlier_leg") and len(fl) < 2:
        scen = rng.choice(["retime", "split"])
    if scen == "downgrade" and cabin != "first":
        scen = "retime"
    offered = [(f, cabin) for f in fl]
    if scen == "retime":
        s = near(intl)
        for f in fl:
            w.retime(f, notice_at - mins(9), s)
    elif scen == "split":              # departure and arrival move by different amounts
        ds = rng.choice([360, 365, 370, 375, 380] if intl else [180, 185, 190, 195, 200])
        as_ = ds - rng.choice([5, 10, 15, 20])
        for f in fl:
            w.retime(f, notice_at - mins(9), ds, as_ if f is fl[-1] else ds)
    elif scen == "earlier_leg":        # second leg moved earlier, first leg moved earlier to keep the connection
        gap = sched(fl[1], purchased)[0] - sched(fl[0], purchased)[1]
        e2 = rng.choice([150, 175, 180, 200, 240, 300])
        e1 = max(rng.choice([90, 150, 170, 175, 180, 185]), e2 - gap // timedelta(minutes=1) + 40)
        w.retime(fl[0], notice_at - mins(9), -e1)
        w.retime(fl[1], notice_at - mins(9), -e2)
    elif scen == "cumulative":
        s = near(intl)
        s1 = rng.choice([40, 60, 90, 120, 140]) * (1 if s > 0 else -1)
        n1 = notice_at - timedelta(days=rng.randint(3, 9))
        for f in fl:
            w.retime(f, n1 - mins(9), s1)
        ev.append({"at": n1, "type": "itinerary_change_notice", "reason": "schedule_change",
                   "offered_itinerary": [{"flight_id": f["id"], "cabin": cabin} for f in fl], "voucher_offered": False})
        for f in fl:
            w.retime(f, notice_at - mins(9), s - s1)
    elif scen == "cancel":
        i = rng.randrange(len(fl))
        f = fl[i]
        f["status"], f["cancelled_at"] = "cancelled", notice_at - mins(9)
        cancelled = True
        mode = rng.choice(["rebook", "rebook", "voucher", "both", "none"])
        if mode in ("rebook", "both"):
            d0 = sched(f, purchased)[0]
            if len(fl) == 2 and i == 0:
                gap = sched(fl[1], purchased)[0] - sched(f, purchased)[1]
                nd = d0 - mins(rng.choice([60, 120, 180])) if gap < mins(150) else d0 + mins(rng.choice([30, 60]))
            else:
                nd = d0 + mins(rng.choice([45, 120, 200, 300, 420, 600]))
            nf = w.flight(f["a"], f["b"], nd)
            offered[i] = (nf, cabin)
        else:
            offered = None
        voucher = mode in ("voucher", "both")
    elif scen == "late_leg":
        s1 = rng.choice([90, 120, 180, 240, 300])
        w.retime(fl[0], notice_at - mins(9), s1)
        d1, a1 = sched(fl[0], notice_at)
        target = near(intl)
        oa = sched(fl[1], purchased)[1]
        nd2 = oa + mins(abs(target)) - mins(block(fl[1]["a"], fl[1]["b"]))
        if nd2 < a1 + mins(40):
            nd2 = a1 + mins(rng.choice([40, 55, 70]))
        offered[1] = (w.flight(fl[1]["a"], fl[1]["b"], nd2), cabin)
    elif scen == "reroute":
        a, h, b = fl[0]["a"], fl[0]["b"], fl[1]["b"]
        options = hubs(a, b, {h})
        if not options:
            return False
        h2 = rng.choice(options)
        w.retime(fl[0], notice_at - mins(9), rng.choice([150, 200, 240]))
        n1 = w.flight(a, h2, dep1 + mins(rng.choice([-60, -30, 0, 30, 60, 90])))
        n2 = w.flight(h2, b, sched(n1, notice_at)[1] + mins(rng.choice([45, 60, 90, 120])))
        offered = [(n1, cabin), (n2, cabin)]
    elif scen == "extra":
        if intl:
            return False
        a, b = fl[0]["a"], fl[-1]["b"]
        w.retime(fl[0], notice_at - mins(9), rng.choice([120, 200, 260]))
        if len(fl) == 1:                       # nonstop replaced by a one-stop routing
            options = hubs(a, b, set())
            if not options:
                return False
            h2 = rng.choice(options)
            n1 = w.flight(a, h2, dep1 + mins(rng.choice([-30, 0, 30, 60])))
            n2 = w.flight(h2, b, sched(n1, notice_at)[1] + mins(rng.choice([50, 70, 100])))
            offered = [(n1, cabin), (n2, cabin)]
        else:                                  # one-stop replaced by a two-stop routing from the same hub
            h = fl[0]["b"]
            options = [x for x in hubs(h, b, {a}) if x != h]
            if not options:
                return False
            h2 = rng.choice(options)
            m2 = w.flight(h, h2, sched(fl[0], notice_at)[1] + mins(rng.choice([50, 70])))
            m3 = w.flight(h2, b, sched(m2, notice_at)[1] + mins(rng.choice([45, 60])))
            offered = [(fl[0], cabin), (m2, cabin), (m3, cabin)]
    elif scen == "downgrade":
        s = rng.choice([0, 30, 60, 90])
        for f in fl:
            w.retime(f, notice_at - mins(9), s)
        k = rng.randrange(len(fl))
        offered[k] = (fl[k], "economy")
    ev.append({"at": notice_at, "type": "itinerary_change_notice",
               "reason": "cancellation" if cancelled else "schedule_change",
               "offered_itinerary": None if offered is None else [{"flight_id": f["id"], "cabin": c} for f, c in offered],
               "voucher_offered": voucher})
    sig = gen_sig(fl, offered, purchased, notice_at, cancelled, cabin)
    if offered is not None and sched(offered[0][0], notice_at)[0] <= notice_at + timedelta(hours=6):
        return False
    if offered is None and not voucher:
        choices = [None]
    else:
        choices = []
        if offered is not None:
            choices += ["declined_offer"] * 3 + ["accepted_offered_itinerary", "boarded"]
        if voucher:
            choices += ["accepted_voucher"] + ([] if offered is not None else ["declined_offer"])
        if sig and (offered is None or not voucher):      # silence only where exactly one kind of offer was made
            choices += [None, None]
    reply = rng.choice(choices)
    # every reply comes well before the first flight that could leave without the passenger
    leaves = min([sched(fl[0], notice_at)[0]] + ([sched(offered[0][0], notice_at)[0]] if offered else []))
    waits = [h for h in (2, 9, 20, 30) if notice_at + timedelta(hours=h) < leaves - timedelta(hours=1)]
    reply_at = notice_at + timedelta(hours=rng.choice(waits or [1]))
    if reply in ("declined_offer", "accepted_offered_itinerary", "accepted_voucher"):
        ev.append({"at": reply_at, "type": "passenger_reply", "choice": reply})
    elif reply == "boarded":
        f0 = offered[0][0]
        ev.append({"at": sched(f0, notice_at)[0] - mins(25), "type": "boarded", "flight_id": f0["id"]})
    accepted = reply in ("accepted_offered_itinerary", "accepted_voucher", "boarded")
    items = []
    if rng.random() < 0.45:
        items.append(anc("advance_seat_selection", rng.choice([2900, 3900, 4900]), 1,
                         accepted and rng.random() < 0.5))
    if rng.random() < 0.2:
        items.append(anc("first_checked_bag", 3500, len(fl), accepted and rng.random() < 0.5))
    if accepted:
        requested = notice_at + mins(rng.choice([30, 75]))
    elif rng.random() < 0.55:
        requested = rng.choice([notice_at + mins(rng.choice([40, 300, 900])),
                                dep1 + timedelta(days=rng.choice([0, 1, 3, 8]))])
    else:
        requested = None
    w.add("schedule_change_or_cancellation", t, ev, items, (), requested, ["filler"], None, None)
    return True


def filler_oversale(w):
    dep = pick_dep()
    if rng.random() < 0.55:
        a, b = rng.choice(DOM_NONSTOP + INTL_NONSTOP)
        legs = [(a, b, dep)]
    else:
        a, h, b = rng.choice(CONNECT)
        gap = rng.choice([45, 60, 90, 180, 230, 235, 240, 245, 250, 300, 420])
        legs = [(a, h, dep), (h, b, dep + mins(block(a, h) + gap))]
    denied = rng.randrange(1, len(legs) + 1)
    if foreign(legs[denied - 1][0]):
        denied = 1
    seats_small = rng.random() < 0.07
    if seats_small and len(legs) == 1 and block(legs[0][0], legs[0][1]) < 200:
        legs[0] = legs[0] + (rng.choice([("Embraer E145", 50), ("Beechcraft 1900D", 19)]),)
    intl = any(foreign(x[0]) or foreign(x[1]) for x in legs)
    # the span to the destination or first stopover must have the same domestic/international character
    end = denied - 1
    while end + 1 < len(legs) and legs[end + 1][2] - (legs[end][2] + mins(block(legs[end][0], legs[end][1]))) <= mins(240):
        end += 1
    span_intl = any(foreign(x[0]) or foreign(x[1]) for x in legs[denied - 1:end + 1])
    if span_intl != intl:
        return False
    lim = 60 if any(foreign(x[1]) for x in legs[denied - 1:denied]) else 45
    checkin = rng.choice([lim - 1, lim, lim + 1, lim + 15, 90, 120, 120, 150])
    volunteer = rng.random() < 0.15
    reason, ops, sub = "oversold", True, None
    r = rng.random()
    if r < 0.1:
        reason, ops = "aircraft_substitution", rng.random() < 0.6
        sub = {"scheduled_aircraft": "Airbus A321neo", "scheduled_designed_passenger_seats": 196}
    elif r < 0.16:
        reason, ops = "weight_balance_restriction", rng.random() < 0.7
    late = rng.choice([45, 55, 60, 65, 75, 100, 115, 120, 125, 150, 200, 235, 240, 245, 300, None])
    ancillary = []
    small = len(legs[denied - 1]) > 3 and legs[denied - 1][3][1] < 30
    if checkin >= lim and not small and rng.random() < 0.4:
        ancillary = [anc("advance_seat_selection", rng.choice([2900, 3900, 4500]), denied, False)]
        if rng.random() < 0.3:
            ancillary.append(anc("wifi", 1200, denied, True))
    zero = len(legs) == 1 and rng.random() < 0.08
    alt_later = rng.choice([0, 0, 0, 30, -25, 60, 90, 15, -10]) if late is not None else 0
    oversale(w, legs, denied, late, ["filler"], zero=zero, volunteer=volunteer,
             accepted_offer=(not volunteer and rng.random() < 0.2), checkin=checkin, reason=reason, ops=ops, sub=sub,
             ancillary=ancillary, alt_later=alt_later,
             alt_nonstop=(end > denied - 1 and has_block(legs[denied - 1][0], legs[end][1]) and rng.random() < 0.5))
    return True


def filler_bag(w):
    dep = pick_dep()
    if rng.random() < 0.55:
        a, b = rng.choice(DOM_NONSTOP + INTL_NONSTOP)
        legs = [(a, b, dep)]
    else:
        a, h, b = rng.choice(CONNECT)
        legs = [(a, h, dep), (h, b, dep + mins(block(a, h) + rng.choice([50, 70, 90])))]
    fl_legs = [{"a": x[0], "b": x[1]} for x in legs]
    lim = bag_limit(fl_legs)
    delay = max(0, lim + rng.choice([-120, -30, -2, -1, 0, 1, 2, 30, 61, 300, rng.randrange(-600, 900)]))
    bag(w, legs, delay, ["filler"], door_late=rng.choice([-25, -10, 0, 8, 15, 30, 55, 90]),
        mbr=rng.random() < 0.88, lost=rng.random() < 0.05, fees=(rng.choice([3500, 4000, 7500]),))
    return True


def filler_service(w):
    dep = pick_dep()
    a, b = rng.choice(DOM_NONSTOP)
    items = [anc(rng.choice(["wifi", "advance_seat_selection", "inflight_meal"]), rng.choice([900, 1900, 2900, 4900]),
                 1, rng.random() < 0.5)]
    service(w, [(a, b, dep)], items, ["filler"], fault=rng.random() < 0.2)
    return True


def main():
    w = W()
    planted(w)
    for f in w.flights.values():
        w.check(f)
    n_planted = len(w.claims)
    made = {filler_change: 0, filler_oversale: 0, filler_bag: 0, filler_service: 0}
    want = {filler_change: 130, filler_oversale: 45, filler_bag: 45, filler_service: 8}
    rejected = 0
    while any(made[k] < want[k] for k in want):
        fn = rng.choice([k for k in want if made[k] < want[k]])
        if w.attempt(fn):
            made[fn] += 1
        else:
            rejected += 1
    order = list(range(len(w.claims)))
    rng.shuffle(order)
    remap, claims = {}, []
    for i, j in enumerate(order, 1):
        c = w.claims[j]
        remap[c["claim_id"]] = f"CL{i:04d}"
        c["claim_id"] = remap[c["claim_id"]]
        claims.append(c)
    flights = []
    for f in sorted(w.flights.values(), key=lambda x: x["id"]):
        if f["status"] == "operated" and f["door"] is None:
            arr = f["versions"][-1][2]
            for off in [rng.choice([-14, -6, 3, 9, 17, 28, 44]), 70, 130]:
                try:
                    local(arr + mins(off), f["b"])
                    f["door"] = arr + mins(off)
                    break
                except Ambiguous:
                    continue
        flights.append({
            "flight_id": f["id"], "flight_number": f"LS{f['num']}", "origin": f["a"], "destination": f["b"],
            "aircraft": f["ac"][0], "designed_passenger_seats": f["ac"][1], "scheduled_service": True,
            "aircraft_substitution": f["sub"], "lowest_cash_fare_cents_by_cabin": f["low"],
            "schedule": [{"recorded_at": iso(r), "departure": local(d, f["a"]), "arrival": local(a, f["b"])}
                         for r, d, a in f["versions"]],
            "status": f["status"], "cancellation_recorded_at": iso(f["cancelled_at"]) if f["cancelled_at"] else None,
            "door_opened_at_gate": local(f["door"], f["b"]) if f["door"] else None})
    ENV.mkdir(parents=True, exist_ok=True)
    for old in ENV.iterdir():
        old.unlink()
    (ENV / "claims.json").write_text(json.dumps(claims, indent=1) + "\n")
    (ENV / "flights.json").write_text(json.dumps(flights, indent=1) + "\n")
    (ENV / "airports.json").write_text(json.dumps({k: {"city": v[0], "country": v[1], "time_zone": v[2]}
                                                   for k, v in AIRPORTS.items()}, indent=1) + "\n")
    (ENV / "carrier.json").write_text(json.dumps({
        "carrier": "Lakeshore Air", "type": "U.S. air carrier, scheduled passenger service",
        "merchant_of_record": "Lakeshore Air for every ticket and every ancillary fee in this queue",
        "money_unit": "cents (USD)",
        "times": "schedule and door times are local wall times at the airport concerned; timestamps ending in Z are UTC",
        "classes_of_service_highest_first": CABINS,
        "contract_of_carriage_check_in": "Check-in must be completed no later than 45 minutes before the scheduled "
                                         "departure of a flight within the United States and no later than 60 "
                                         "minutes before the scheduled departure of a flight to a foreign point.",
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
    print(len(claims), "claims,", len(flights), "flights,", len(w.golden), "golden,", n_planted, "planted,",
          rejected, "filler rebuilt")


if __name__ == "__main__":
    main()
