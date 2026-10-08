#!/usr/bin/env python3
"""Generate the sms-send-schedule inputs (dev only, never shipped).

A retailer's scheduled promotional SMS batch plus the records a marketing-ops team would pull
before launch: contacts, carrier area-code table, sending platforms, consent records, inbound
replies, the seller's internal do-not-call list, national registry matches, and purchase /
inquiry / application history. Planted scenarios exercise one rule family each and carry a
hand-worked expected answer (tests/golden.json); filler contacts are random.

Writes environment/data/*, an identical tests/data copy, tests/case_tags.json and
tests/golden.json.
"""
import csv
import json
import random
import shutil
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2] / "tasks" / "sms-send-schedule"
ENV = ROOT / "environment" / "data"
TST = ROOT / "tests" / "data"
UTC = timezone.utc
rng = random.Random(64120)

SELLER = "Harbor & Pine Home Goods, Inc."
AFFILIATES = ["Harbor & Pine Outlet LLC", "Pine Rewards Card Services, LLC"]

AREA = [  # npa, state, city, zone
    ("212", "NY", "New York", "America/New_York"), ("646", "NY", "New York", "America/New_York"),
    ("718", "NY", "Brooklyn", "America/New_York"), ("617", "MA", "Boston", "America/New_York"),
    ("404", "GA", "Atlanta", "America/New_York"), ("305", "FL", "Miami", "America/New_York"),
    ("919", "NC", "Raleigh", "America/New_York"), ("202", "DC", "Washington", "America/New_York"),
    ("317", "IN", "Indianapolis", "America/Indiana/Indianapolis"),
    ("312", "IL", "Chicago", "America/Chicago"), ("612", "MN", "Minneapolis", "America/Chicago"),
    ("615", "TN", "Nashville", "America/Chicago"), ("713", "TX", "Houston", "America/Chicago"),
    ("214", "TX", "Dallas", "America/Chicago"), ("303", "CO", "Denver", "America/Denver"),
    ("801", "UT", "Salt Lake City", "America/Denver"), ("505", "NM", "Albuquerque", "America/Denver"),
    ("208", "ID", "Boise", "America/Boise"), ("602", "AZ", "Phoenix", "America/Phoenix"),
    ("480", "AZ", "Mesa", "America/Phoenix"), ("520", "AZ", "Tucson", "America/Phoenix"),
    ("213", "CA", "Los Angeles", "America/Los_Angeles"), ("415", "CA", "San Francisco", "America/Los_Angeles"),
    ("206", "WA", "Seattle", "America/Los_Angeles"), ("503", "OR", "Portland", "America/Los_Angeles"),
    ("702", "NV", "Las Vegas", "America/Los_Angeles"), ("907", "AK", "Anchorage", "America/Anchorage"),
    ("808", "HI", "Honolulu", "Pacific/Honolulu"), ("787", "PR", "San Juan", "America/Puerto_Rico"),
]
BY_NPA = {a[0]: a for a in AREA}
FIRST = ["Ava", "Liam", "Mia", "Noah", "Zoe", "Ethan", "Ivy", "Lucas", "Nora", "Owen", "Ruby", "Eli",
         "Maya", "Leo", "Aria", "Caleb", "Jade", "Mason", "Lena", "Ravi", "Sofia", "Diego", "Hana",
         "Omar", "Priya", "Tariq", "Grace", "Wei", "Elena", "Malik", "Chloe", "Aiden", "Nia", "Jonah"]
LAST = ["Nguyen", "Garcia", "Smith", "Patel", "Kim", "Johnson", "Lopez", "Brown", "Okafor", "Rossi",
        "Chen", "Davis", "Martinez", "Wilson", "Singh", "Clark", "Reyes", "Turner", "Ali", "Moore"]

PLATFORMS = [
    ("P1", "Harbor Messenger (in-house campaign tool)",
     "Sends only to the phone numbers in the contact list uploaded for each campaign. The equipment "
     "does not have the capacity to store or produce telephone numbers using a random or sequential "
     "number generator, and it cannot dial numbers that are not in the uploaded list."),
    ("P2", "BlastLine SMS Gateway (legacy vendor)",
     "Sends to uploaded contact lists. The equipment has the capacity to store and to produce "
     "telephone numbers using a random or sequential number generator and to dial such numbers; the "
     "vendor's number-generation module is installed and active on the retailer's account."),
]
CAMPAIGNS = [
    ("C01", "Fall Home Refresh Sale", "P1", (2026, 10, 27, 10, 0)),
    ("C02", "Weekend Doorbusters Reminder", "P1", (2026, 10, 30, 8, 0)),
    ("C03", "Halloween Flash Sale", "P2", (2026, 10, 31, 18, 0)),
    ("C04", "Member Preview Night", "P1", (2026, 11, 2, 19, 30)),
    ("C05", "Early Holiday Deals", "P2", (2026, 11, 4, 9, 0)),
    ("C06", "Personalized Picks (send-time optimized)", "P1", None),
    ("C07", "Last Call: Fall Refresh", "P2", (2026, 10, 28, 20, 45)),
]
HQ = ZoneInfo("America/New_York")
PER_SE = ["stop", "quit", "end", "revoke", "opt out", "cancel", "unsubscribe"]
NON_REVOKE = ["Thanks! See you Saturday", "Is the oak dining table back in stock?", "ok",
              "Love this sale", "What time do you open on Sunday?", "Got it, thank you",
              "Do you deliver to Tucson?", "Yes", "Can I use this coupon online?", "lol nice"]
EXPLICIT = ["please stop texting me", "Do not text this number again.", "Remove me from your list",
            "No more texts please"]


def utc(y, mo, d, h=0, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=UTC)


def loc(zone, y, mo, d, h, mi):
    """Local wall time in zone -> aware UTC datetime (never called on a skipped/repeated time)."""
    return datetime(y, mo, d, h, mi, tzinfo=ZoneInfo(zone)).astimezone(UTC)


def iso(dt):
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class World:
    def __init__(self):
        self.contacts, self.consents, self.replies, self.dnc, self.registry = [], [], [], [], []
        self.history, self.messages = [], []
        self.tags, self.golden = {}, {}
        self.used_phones = set()
        self.n_contact = self.n_msg = self.n_cons = self.n_rep = self.n_dnc = self.n_hist = 0

    def phone(self, npa):
        while True:
            p = f"+1{npa}5550{rng.randint(100, 199)}"
            if p not in self.used_phones:
                self.used_phones.add(p)
                return p

    def contact(self, addr_npa, phone_npa=None):
        self.n_contact += 1
        cid = f"K{self.n_contact:04d}"
        a = BY_NPA[addr_npa]
        ph = self.phone(phone_npa or addr_npa)
        self.contacts.append(dict(contact_id=cid, name=f"{rng.choice(FIRST)} {rng.choice(LAST)}",
                                  phone=ph, address_city=a[2], address_state=a[1],
                                  address_time_zone=a[3]))
        return cid, ph, a[3]

    def consent(self, cid, ph, when, kind="valid"):
        self.n_cons += 1
        rec = dict(consent_id=f"W{self.n_cons:04d}", contact_id=cid, obtained_at=iso(when),
                   seller_named=SELLER, phone_number=ph, in_writing="true",
                   signature=rng.choice(["electronic", "electronic", "wet_ink"]),
                   discloses_autodialed_marketing="true",
                   discloses_not_condition_of_purchase="true",
                   source=None)
        rec["source"] = "paper_form_in_store" if rec["signature"] == "wet_ink" else \
            rng.choice(["web_checkout_form", "in_store_tablet", "sms_keyword_double_opt_in_web_form"])
        if kind == "verbal":
            rec.update(in_writing="false", signature="none", source="phone_call_with_associate")
        elif kind == "unsigned":
            rec.update(signature="none", source="web_newsletter_form")
        elif kind == "wrong_number":
            old = self.phone(rng.choice(list(BY_NPA)))
            rec.update(phone_number=old)
        elif kind == "affiliate":
            rec.update(seller_named=rng.choice(AFFILIATES))
        elif kind == "no_autodialer_disclosure":
            rec.update(discloses_autodialed_marketing="false")
        elif kind == "no_condition_disclosure":
            rec.update(discloses_not_condition_of_purchase="false")
        self.consents.append(rec)

    def reply(self, cid, when, text):
        self.n_rep += 1
        self.replies.append(dict(reply_id=f"R{self.n_rep:04d}", contact_id=cid,
                                 received_at=iso(when), text=text))

    def dnc_request(self, cid, when, channel="customer_service_call"):
        self.n_dnc += 1
        self.dnc.append(dict(request_id=f"D{self.n_dnc:04d}", contact_id=cid,
                             received_at=iso(when), channel=channel))

    def registry_entry(self, ph, reg, cancelled=None):
        self.registry.append(dict(phone=ph, registered_at=iso(reg),
                                  cancelled_at=iso(cancelled) if cancelled else ""))

    def event(self, cid, d, kind):
        self.n_hist += 1
        note = {"purchase": rng.choice(["in-store purchase", "online order", "delivery order"]),
                "inquiry": rng.choice(["asked about sofa delivery times", "price question via web chat",
                                        "called store about rug sizes"]),
                "application": rng.choice(["applied for Harbor & Pine store credit account",
                                            "submitted design-service application"])}[kind]
        self.history.append(dict(event_id=f"H{self.n_hist:05d}", contact_id=cid,
                                 event_date=d.isoformat(), event_type=kind, note=note))

    def message(self, cid, when, platform, campaign, tags=(), expect=None):
        self.n_msg += 1
        mid = f"M{self.n_msg:04d}"
        self.messages.append(dict(message_id=mid, contact_id=cid, campaign_id=campaign,
                                  platform_id=platform, scheduled_at=iso(when)))
        self.tags[mid] = list(tags)
        if expect is not None:
            dec, t = expect
            self.golden[mid] = [dec, iso(t) if t else ""]
        return mid


def past(days_lo, days_hi):
    return utc(2026, 10, 25) - timedelta(days=rng.randint(days_lo, days_hi), minutes=rng.randint(0, 1439))


def after(stamp, lo=2, hi=200):
    t0 = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    t = t0 + timedelta(days=rng.randint(lo, hi), minutes=rng.randint(0, 1439))
    return min(t, utc(2026, 10, 25, 12))


def planted(w):
    S, R, B = "SEND", "RESCHEDULE", "BLOCK"
    NY, CHI, DEN, PHX, LA = "212", "312", "303", "602", "213"

    def plain(npa, phone_npa=None):
        """No consent, no relationship, no lists: every message is a telephone solicitation."""
        return w.contact(npa, phone_npa)

    # --- calling hours (solicitations, recipient local time) -----------------------------
    for npa, (y, mo, d, h, mi), exp in [
        (NY, (2026, 10, 28, 7, 40), (R, (2026, 10, 28, 8, 0))),
        (NY, (2026, 10, 28, 21, 0), (S, None)),
        (CHI, (2026, 10, 29, 21, 1), (R, (2026, 10, 30, 8, 0))),
        (DEN, (2026, 10, 29, 8, 0), (S, None)),
        (CHI, (2026, 10, 30, 20, 59), (S, None)),
        (DEN, (2026, 10, 27, 23, 15), (R, (2026, 10, 28, 8, 0))),
        (LA, (2026, 10, 30, 7, 59), (R, (2026, 10, 30, 8, 0))),
        ("615", (2026, 11, 3, 12, 5), (S, None)),
    ]:
        cid, ph, z = plain(npa)
        sched = loc(z, y, mo, d, h, mi)
        t = sched if exp[0] == S else loc(z, *exp[1])
        w.message(cid, sched, "P1", "C06", ["calling-hours"], (exp[0], t))

    # --- time zones: HQ blasts, zones without DST, area code differs from address ---------
    blast = loc("America/New_York", 2026, 10, 29, 10, 0)                       # 14:00Z
    for npa, local_open in [(LA, (2026, 10, 29, 8, 0)), ("808", (2026, 10, 29, 8, 0)),
                            ("907", (2026, 10, 29, 8, 0)), (PHX, (2026, 10, 29, 8, 0))]:
        cid, ph, z = plain(npa)
        w.message(cid, blast, "P1", "C01", ["time-zone", "hq-blast"], (R, loc(z, *local_open)))
    late = loc("America/New_York", 2026, 11, 2, 20, 30)                       # 01:30Z Nov 3
    cid, ph, z = plain("787")      # Puerto Rico stays UTC-4: 21:30 local
    w.message(cid, late, "P1", "C04", ["time-zone", "no-dst-zone"], (R, loc(z, 2026, 11, 3, 8, 0)))
    cid, ph, z = plain(NY)
    w.message(cid, late, "P1", "C04", ["time-zone"], (S, late))
    # address zone governs, area code points elsewhere, close to a boundary
    cid, ph, z = plain(PHX, "212")
    s = utc(2026, 10, 30, 14, 30)                                             # 07:30 MST
    w.message(cid, s, "P1", "C06", ["time-zone", "area-code-mismatch"], (R, loc(z, 2026, 10, 30, 8, 0)))
    cid, ph, z = plain(NY, "213")
    s = utc(2026, 10, 30, 12, 10)                                             # 08:10 EDT
    w.message(cid, s, "P1", "C06", ["time-zone", "area-code-mismatch"], (S, s))
    cid, ph, z = plain(LA, "305")
    s = utc(2026, 10, 30, 4, 30)                                              # 21:30 PDT Oct 29
    w.message(cid, s, "P1", "C06", ["time-zone", "area-code-mismatch"], (R, loc(z, 2026, 10, 30, 8, 0)))
    cid, ph, z = plain("808", "206")
    s = utc(2026, 11, 2, 7, 30)                                               # 21:30 HST Nov 1
    w.message(cid, s, "P1", "C06", ["time-zone", "area-code-mismatch"], (R, loc(z, 2026, 11, 2, 8, 0)))
    cid, ph, z = plain("317", "312")
    s = utc(2026, 11, 3, 1, 50)                                               # 20:50 EST Nov 2
    w.message(cid, s, "P1", "C06", ["time-zone", "area-code-mismatch"], (S, s))

    # --- daylight saving change (Sunday Nov 1, 2026) ----------------------------------------
    cid, ph, z = plain(NY)
    s = loc(z, 2026, 10, 31, 21, 30)
    w.message(cid, s, "P1", "C06", ["dst"], (R, loc(z, 2026, 11, 1, 8, 0)))             # 13:00Z
    cid, ph, z = plain(NY)
    s = utc(2026, 11, 2, 11, 30)                                                         # 06:30 EST
    w.message(cid, s, "P1", "C06", ["dst"], (R, utc(2026, 11, 2, 13, 0)))
    cid, ph, z = plain(LA)
    s = utc(2026, 11, 1, 13, 0)                                                          # 05:00 PST
    w.message(cid, s, "P1", "C06", ["dst"], (R, utc(2026, 11, 1, 16, 0)))
    cid, ph, z = plain(PHX)
    s = utc(2026, 11, 2, 13, 30)                                                         # 06:30 MST
    w.message(cid, s, "P1", "C06", ["dst", "no-dst-zone"], (R, utc(2026, 11, 2, 15, 0)))
    cid, ph, z = plain(CHI)
    s = utc(2026, 11, 1, 12, 30)                                                         # 06:30 CST
    w.message(cid, s, "P1", "C06", ["dst"], (R, utc(2026, 11, 1, 14, 0)))
    cid, ph, z = plain(NY)
    s = utc(2026, 11, 3, 2, 0)                                                           # 21:00 EST
    w.message(cid, s, "P1", "C06", ["dst"], (S, s))
    cid, ph, z = plain(NY)
    s = utc(2026, 11, 3, 2, 1)                                                           # 21:01 EST
    w.message(cid, s, "P1", "C06", ["dst"], (R, utc(2026, 11, 3, 13, 0)))

    # --- not a telephone solicitation: hours and national registry do not apply ------------
    def consented(npa, phone_npa=None, kind="valid"):
        cid, ph, z = w.contact(npa, phone_npa)
        w.consent(cid, ph, past(40, 700), kind)
        return cid, ph, z

    cid, ph, z = consented(NY)
    s = loc(z, 2026, 10, 28, 22, 45)
    w.message(cid, s, "P2", "C06", ["exempt-consent"], (S, s))
    cid, ph, z = consented(CHI)
    s = loc(z, 2026, 10, 29, 6, 10)
    w.message(cid, s, "P1", "C06", ["exempt-consent"], (S, s))
    cid, ph, z = consented(DEN)
    w.registry_entry(ph, past(400, 2000))
    s = loc(z, 2026, 10, 30, 12, 0)
    w.message(cid, s, "P1", "C06", ["exempt-consent", "national-dnc"], (S, s))
    cid, ph, z = consented(LA)
    w.registry_entry(ph, past(400, 2000))
    s = loc(z, 2026, 11, 3, 21, 40)
    w.message(cid, s, "P2", "C06", ["exempt-consent", "national-dnc"], (S, s))

    def with_event(npa, kind, d, phone_npa=None):
        cid, ph, z = w.contact(npa, phone_npa)
        w.event(cid, d, kind)
        return cid, ph, z

    cid, ph, z = with_event(NY, "purchase", date(2026, 5, 14))
    s = loc(z, 2026, 10, 27, 23, 30)
    w.message(cid, s, "P1", "C06", ["exempt-ebr"], (S, s))
    cid, ph, z = with_event(CHI, "inquiry", date(2026, 9, 20))
    w.registry_entry(ph, past(400, 2000))
    s = loc(z, 2026, 10, 28, 7, 0)
    w.message(cid, s, "P1", "C06", ["exempt-ebr", "national-dnc"], (S, s))
    cid, ph, z = with_event(DEN, "purchase", date(2025, 11, 2))
    w.registry_entry(ph, past(400, 2000))
    s = loc(z, 2026, 10, 31, 14, 0)
    w.message(cid, s, "P1", "C06", ["exempt-ebr", "national-dnc"], (S, s))
    cid, ph, z = with_event(LA, "application", date(2026, 8, 29))
    s = loc(z, 2026, 11, 4, 5, 50)
    w.message(cid, s, "P1", "C06", ["exempt-ebr"], (S, s))

    # --- autodialer platform needs prior express written consent ---------------------------
    cid, ph, z = with_event(NY, "purchase", date(2026, 9, 1))
    w.message(cid, loc(z, 2026, 10, 31, 18, 0), "P2", "C03", ["autodialer"], (B, None))
    cid, ph, z = plain(CHI)
    w.message(cid, loc(z, 2026, 10, 31, 17, 0), "P2", "C03", ["autodialer"], (B, None))
    cid, ph, z = plain(DEN)
    s = loc(z, 2026, 10, 30, 11, 0)
    w.message(cid, s, "P1", "C06", ["autodialer", "non-autodialer-no-consent"], (S, s))
    cid, ph, z = consented(LA)
    s = loc(z, 2026, 10, 31, 15, 0)
    w.message(cid, s, "P2", "C03", ["autodialer"], (S, s))
    cid, ph, z = plain("404")
    w.registry_entry(ph, past(400, 2000))
    w.message(cid, loc(z, 2026, 11, 4, 9, 0), "P2", "C05", ["autodialer", "national-dnc"], (B, None))
    cid, ph, z = with_event("615", "inquiry", date(2026, 10, 1))
    w.message(cid, loc(z, 2026, 11, 4, 8, 0), "P2", "C05", ["autodialer"], (B, None))

    # --- consent record elements ------------------------------------------------------------
    for kind in ["verbal", "unsigned", "wrong_number", "affiliate", "no_autodialer_disclosure",
                 "no_condition_disclosure"]:
        cid, ph, z = consented(rng.choice([NY, CHI, DEN, LA, "617", "713"]), kind=kind)
        w.message(cid, loc(z, 2026, 11, 4, 12, 0), "P2", "C05", ["consent-elements", kind], (B, None))
    cid, ph, z = consented(NY, kind="affiliate")
    s = loc(z, 2026, 10, 28, 22, 10)
    w.message(cid, s, "P1", "C06", ["consent-elements", "affiliate"], (R, loc(z, 2026, 10, 29, 8, 0)))
    cid, ph, z = consented(CHI, kind="wrong_number")
    s = loc(z, 2026, 10, 29, 6, 30)
    w.message(cid, s, "P1", "C06", ["consent-elements", "wrong_number"], (R, loc(z, 2026, 10, 29, 8, 0)))
    cid, ph, z = consented(DEN, kind="verbal")
    w.registry_entry(ph, past(400, 2000))
    w.message(cid, loc(z, 2026, 10, 30, 13, 0), "P1", "C06", ["consent-elements", "verbal",
                                                               "national-dnc"], (B, None))
    for sig in ["electronic", "wet_ink"]:
        cid, ph, z = w.contact(rng.choice([NY, LA]))
        w.consent(cid, ph, past(40, 700))
        w.consents[-1].update(signature=sig, source="web_checkout_form" if sig == "electronic"
                              else "paper_form_in_store")
        s = loc(z, 2026, 11, 4, 22, 15)
        w.message(cid, s, "P2", "C06", ["consent-elements", f"valid-{sig}"], (S, s))

    # --- replies: per se revocation words, explicit requests, ordinary replies -----------
    revoking = ["Revoke", "opt out", "Quit.", "END", "Cancel", "unsubscribe", "STOP"] + EXPLICIT[:3]
    for i, text in enumerate(revoking):
        cid, ph, z = consented(rng.choice([NY, CHI, DEN, LA, "404", "206"]))
        w.reply(cid, after(w.consents[-1]["obtained_at"]), text)
        plat = "P2" if i % 2 == 0 else "P1"
        w.message(cid, loc(z, 2026, 11, 2, 12, 30), plat, "C06", ["revocation", "per-se" if i < 7
                                                                  else "explicit"], (B, None))
    for text in NON_REVOKE[:5]:
        cid, ph, z = consented(rng.choice([NY, CHI, LA]))
        w.reply(cid, after(w.consents[-1]["obtained_at"]), text)
        s = loc(z, 2026, 11, 2, 21, 50)
        w.message(cid, s, "P2", "C06", ["revocation", "not-a-revocation"], (S, s))

    # --- seller-specific do-not-call list ------------------------------------------------------
    cid, ph, z = consented(NY)
    w.consents[-1]["obtained_at"] = iso(utc(2023, 12, 5, 19, 12))
    w.dnc_request(cid, utc(2024, 8, 14, 16, 2))
    w.message(cid, loc(z, 2026, 11, 2, 12, 0), "P2", "C06", ["seller-dnc"], (B, None))
    cid, ph, z = with_event(CHI, "purchase", date(2026, 7, 20))
    w.dnc_request(cid, utc(2026, 9, 3, 15, 40))
    w.message(cid, loc(z, 2026, 10, 30, 13, 0), "P1", "C06", ["seller-dnc", "ebr-terminated"], (B, None))
    cid, ph, z = with_event(LA, "inquiry", date(2026, 9, 25))
    w.reply(cid, utc(2026, 10, 2, 18, 0), "STOP")
    w.message(cid, loc(z, 2026, 10, 31, 23, 0), "P1", "C06", ["seller-dnc", "ebr-terminated"], (B, None))
    cid, ph, z = plain(DEN)
    w.dnc_request(cid, utc(2020, 6, 11, 17, 25))
    s = loc(z, 2026, 10, 29, 14, 0)
    w.message(cid, s, "P1", "C06", ["seller-dnc", "lapsed"], (S, s))
    cid, ph, z = consented(NY)
    w.consents[-1]["obtained_at"] = iso(utc(2019, 4, 2, 15, 0))
    w.reply(cid, utc(2020, 9, 9, 22, 41), "unsubscribe")
    w.message(cid, loc(z, 2026, 10, 29, 14, 0), "P2", "C06", ["seller-dnc", "lapsed",
                                                              "consent-stays-revoked"], (B, None))
    cid, ph, z = plain(NY)
    w.dnc_request(cid, utc(2021, 11, 2, 15, 37))                     # lapses 10:37 EST Nov 2
    w.message(cid, utc(2026, 11, 1, 15, 0), "P1", "C06", ["seller-dnc", "lapse-in-horizon"],
              (R, utc(2026, 11, 2, 15, 37)))
    cid, ph, z = plain(NY)
    w.dnc_request(cid, utc(2021, 11, 4, 3, 12))                      # lapses 22:12 EST Nov 3
    w.message(cid, utc(2026, 11, 2, 16, 0), "P1", "C06", ["seller-dnc", "lapse-in-horizon"],
              (R, utc(2026, 11, 4, 13, 0)))
    cid, ph, z = plain(CHI)
    w.reply(cid, utc(2021, 10, 29, 16, 20), "Stop")                  # lapses 11:20 CDT Oct 29
    w.message(cid, utc(2026, 10, 28, 15, 0), "P1", "C06", ["seller-dnc", "lapse-in-horizon",
                                                           "revocation"], (R, utc(2026, 10, 29, 16, 20)))
    cid, ph, z = plain(DEN)
    w.dnc_request(cid, utc(2021, 10, 30, 18, 5))
    w.registry_entry(ph, past(400, 2000))
    w.message(cid, utc(2026, 10, 28, 18, 0), "P1", "C06", ["seller-dnc", "lapse-in-horizon",
                                                           "national-dnc"], (B, None))
    cid, ph, z = plain(LA)
    w.dnc_request(cid, utc(2021, 11, 20, 19, 0))                     # lapses after the horizon
    w.message(cid, utc(2026, 10, 28, 19, 0), "P1", "C06", ["seller-dnc", "horizon"], (B, None))

    # --- national registry ------------------------------------------------------------------
    cid, ph, z = plain(NY)
    w.registry_entry(ph, utc(2019, 3, 3, 14, 0))
    w.message(cid, loc(z, 2026, 10, 29, 12, 0), "P1", "C06", ["national-dnc"], (B, None))
    cid, ph, z = plain(CHI)
    w.registry_entry(ph, utc(2018, 1, 9, 20, 0), utc(2024, 6, 1, 15, 0))
    s = loc(z, 2026, 10, 29, 12, 0)
    w.message(cid, s, "P1", "C06", ["national-dnc", "cancelled"], (S, s))
    cid, ph, z = plain(LA)
    w.registry_entry(ph, utc(2017, 5, 9, 20, 0), utc(2025, 2, 11, 15, 0))
    s = loc(z, 2026, 10, 29, 6, 20)
    w.message(cid, s, "P1", "C06", ["national-dnc", "cancelled"], (R, loc(z, 2026, 10, 29, 8, 0)))
    cid, ph, z = with_event(DEN, "purchase", date(2025, 2, 20))
    w.registry_entry(ph, past(400, 2000))
    w.message(cid, loc(z, 2026, 10, 30, 12, 0), "P1", "C06", ["national-dnc", "ebr-expired"], (B, None))
    cid, ph, z = with_event(NY, "inquiry", date(2026, 6, 15))
    w.registry_entry(ph, past(400, 2000))
    w.message(cid, loc(z, 2026, 10, 30, 12, 0), "P1", "C06", ["national-dnc", "ebr-expired",
                                                              "inquiry-window"], (B, None))

    # --- established business relationship windows -------------------------------------------
    cid, ph, z = with_event(NY, "purchase", date(2025, 4, 30))
    s = loc(z, 2026, 10, 30, 22, 30)                                  # date Oct 30 -> Apr 30, 2025
    w.message(cid, s, "P1", "C06", ["ebr", "boundary"], (S, s))
    cid, ph, z = with_event(NY, "purchase", date(2025, 4, 29))
    s = loc(z, 2026, 10, 30, 22, 30)
    w.message(cid, s, "P1", "C06", ["ebr", "boundary"], (R, loc(z, 2026, 10, 31, 8, 0)))
    cid, ph, z = with_event(LA, "purchase", date(2025, 4, 28))
    s = loc(z, 2026, 10, 28, 21, 30)                                  # 04:30Z Oct 29; local date Oct 28
    w.message(cid, s, "P1", "C06", ["ebr", "local-date"], (S, s))
    cid, ph, z = with_event(NY, "purchase", date(2025, 4, 30))
    s = loc(z, 2026, 10, 31, 22, 0)                                   # Oct 31 -> Apr 30 (no Apr 31)
    w.message(cid, s, "P1", "C06", ["ebr", "month-end"], (S, s))
    cid, ph, z = with_event(CHI, "inquiry", date(2026, 8, 3))
    s = loc(z, 2026, 11, 3, 6, 0)
    w.message(cid, s, "P1", "C06", ["ebr", "inquiry-window", "boundary"], (S, s))
    cid, ph, z = with_event(CHI, "inquiry", date(2026, 8, 2))
    s = loc(z, 2026, 11, 3, 6, 0)
    w.message(cid, s, "P1", "C06", ["ebr", "inquiry-window", "boundary"], (R, loc(z, 2026, 11, 3, 8, 0)))
    cid, ph, z = with_event(DEN, "application", date(2026, 6, 20))
    s = loc(z, 2026, 10, 29, 21, 45)
    w.message(cid, s, "P1", "C06", ["ebr", "inquiry-window", "application"],
              (R, loc(z, 2026, 10, 30, 8, 0)))
    cid, ph, z = with_event(LA, "application", date(2026, 9, 1))
    s = loc(z, 2026, 10, 29, 21, 45)
    w.message(cid, s, "P1", "C06", ["ebr", "inquiry-window", "application"], (S, s))
    # relationship ends at local midnight
    cid, ph, z = with_event(NY, "purchase", date(2025, 4, 29))
    s = loc(z, 2026, 10, 29, 23, 40)
    w.message(cid, s, "P1", "C06", ["ebr", "expires-at-midnight"], (S, s))
    cid, ph, z = with_event(NY, "purchase", date(2025, 4, 29))
    w.registry_entry(ph, past(400, 2000))
    w.message(cid, loc(z, 2026, 10, 30, 0, 20), "P1", "C06", ["ebr", "expires-at-midnight",
                                                              "national-dnc"], (B, None))
    cid, ph, z = with_event(NY, "purchase", date(2025, 4, 29))
    s = loc(z, 2026, 10, 30, 0, 20)
    w.message(cid, s, "P1", "C06", ["ebr", "expires-at-midnight"], (R, loc(z, 2026, 10, 30, 8, 0)))
    cid, ph, z = with_event(LA, "purchase", date(2025, 4, 27))
    s = loc(z, 2026, 10, 27, 21, 50)                                  # 04:50Z Oct 28; local date Oct 27
    w.message(cid, s, "P1", "C06", ["ebr", "local-date"], (S, s))


def filler(w, n_contacts=170):
    npas = [a[0] for a in AREA]
    weights = [6, 3, 3, 3, 4, 4, 3, 2, 2, 5, 3, 3, 4, 4, 3, 2, 2, 1, 3, 2, 2, 6, 3, 3, 3, 2, 1, 1, 1]
    for _ in range(n_contacts):
        addr = rng.choices(npas, weights)[0]
        moved = rng.random() < 0.22
        cid, ph, z = w.contact(addr, rng.choice(npas) if moved else None)
        r = rng.random()
        if r < 0.55:
            w.consent(cid, ph, past(20, 1500))
        elif r < 0.67:
            w.consent(cid, ph, past(20, 1500), rng.choice(["verbal", "unsigned", "wrong_number",
                                                           "affiliate", "no_autodialer_disclosure",
                                                           "no_condition_disclosure"]))
        for _ in range(rng.choice([0, 0, 1, 1, 2, 3])):
            kind = rng.choices(["purchase", "inquiry", "application"], [6, 3, 1])[0]
            w.event(cid, (utc(2026, 10, 25) - timedelta(days=rng.randint(3, 800))).date(), kind)
        if rng.random() < 0.18:
            w.registry_entry(ph, past(200, 4000),
                             past(10, 150) if rng.random() < 0.2 else None)
        if rng.random() < 0.2:
            w.reply(cid, past(3, 400), rng.choice(NON_REVOKE))
        rr = rng.random()
        if rr < 0.08:
            floor = [c["obtained_at"] for c in w.consents if c["contact_id"] == cid]
            floor += [h["event_date"] + "T23:59:00Z" for h in w.history if h["contact_id"] == cid]
            start = max(floor) if floor else iso(past(300, 1500))
            when = after(start, 1, 120)
            if when < utc(2026, 10, 25, 12):
                if rr < 0.05:
                    w.reply(cid, when, rng.choice(["STOP", "Stop", "stop", "End", "CANCEL",
                                                   "Unsubscribe", "quit"]))
                else:
                    w.dnc_request(cid, when)
        for camp in rng.sample(CAMPAIGNS, rng.choice([1, 2, 2, 3])):
            cid_, name, plat, when = camp
            if when is None:
                d = rng.randint(27, 36)
                day = date(2026, 10, 1) + timedelta(days=d - 1)
                h = rng.choice([6, 7, 9, 11, 13, 17, 19, 20, 21, 22])
                when_utc = loc(z, day.year, day.month, day.day, h, rng.randint(0, 59))
            else:
                when_utc = datetime(*when, tzinfo=HQ).astimezone(UTC)
            w.message(cid, when_utc, plat, cid_, ["filler"])


def write_csv(path, rows, fields):
    with open(path, "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        wr.writeheader()
        wr.writerows(rows)


def main():
    w = World()
    planted(w)
    filler(w)
    # interleave: messages sorted by schedule; ids renumbered in that order
    order = sorted(w.messages, key=lambda m: (m["scheduled_at"], m["contact_id"]))
    remap = {}
    for i, m in enumerate(order, 1):
        remap[m["message_id"]] = f"M{i:04d}"
        m["message_id"] = remap[m["message_id"]]
    tags = {remap[k]: v for k, v in w.tags.items()}
    golden = {remap[k]: v for k, v in w.golden.items()}
    # contact ids must not reveal which contacts are planted: renumber in random order
    ids = [c["contact_id"] for c in w.contacts]
    new_ids = [f"K{i:04d}" for i in rng.sample(range(1, len(ids) + 1), len(ids))]
    cmap = dict(zip(ids, new_ids))
    for table in (w.contacts, w.consents, w.replies, w.dnc, w.history, order):
        for r in table:
            r["contact_id"] = cmap[r["contact_id"]]
    for table, key, pre in ((w.consents, "consent_id", "W"), (w.replies, "reply_id", "R"),
                            (w.dnc, "request_id", "D"), (w.history, "event_id", "H")):
        stamp = "event_date" if key == "event_id" else ("obtained_at" if key == "consent_id" else "received_at")
        table.sort(key=lambda r: (r[stamp], r["contact_id"]))
        for i, r in enumerate(table, 1):
            r[key] = f"{pre}{i:05d}" if pre == "H" else f"{pre}{i:04d}"
    ENV.mkdir(parents=True, exist_ok=True)
    write_csv(ENV / "contacts.csv", sorted(w.contacts, key=lambda c: c["contact_id"]),
              ["contact_id", "name", "phone", "address_city", "address_state", "address_time_zone"])
    write_csv(ENV / "area_codes.csv", [dict(npa=a[0], state=a[1], rate_center_city=a[2],
                                            time_zone=a[3]) for a in AREA],
              ["npa", "state", "rate_center_city", "time_zone"])
    write_csv(ENV / "platforms.csv", [dict(platform_id=p[0], name=p[1], equipment=p[2]) for p in PLATFORMS],
              ["platform_id", "name", "equipment"])
    write_csv(ENV / "campaigns.csv", [dict(campaign_id=c[0], name=c[1], platform_id=c[2],
                                           content="promotional offer") for c in CAMPAIGNS],
              ["campaign_id", "name", "platform_id", "content"])
    write_csv(ENV / "consents.csv", sorted(w.consents, key=lambda r: r["consent_id"]),
              ["consent_id", "contact_id", "obtained_at", "seller_named", "phone_number", "in_writing",
               "signature", "discloses_autodialed_marketing", "discloses_not_condition_of_purchase",
               "source"])
    write_csv(ENV / "replies.csv", sorted(w.replies, key=lambda r: r["received_at"]),
              ["reply_id", "contact_id", "received_at", "text"])
    write_csv(ENV / "seller_dnc_requests.csv", sorted(w.dnc, key=lambda r: r["received_at"]),
              ["request_id", "contact_id", "received_at", "channel"])
    write_csv(ENV / "national_dnc_matches.csv", sorted(w.registry, key=lambda r: r["phone"]),
              ["phone", "registered_at", "cancelled_at"])
    write_csv(ENV / "customer_history.csv", sorted(w.history, key=lambda r: r["event_id"]),
              ["event_id", "contact_id", "event_date", "event_type", "note"])
    write_csv(ENV / "scheduled_messages.csv", order,
              ["message_id", "contact_id", "campaign_id", "platform_id", "scheduled_at"])
    (ENV / "seller.json").write_text(json.dumps({
        "seller_legal_name": SELLER, "brand": "Harbor & Pine",
        "headquarters_time_zone": "America/New_York",
        "affiliates": AFFILIATES}, indent=2) + "\n")
    if TST.exists():
        shutil.rmtree(TST)
    shutil.copytree(ENV, TST)
    (ROOT / "tests" / "case_tags.json").write_text(json.dumps(tags, indent=1, sort_keys=True) + "\n")
    (ROOT / "tests" / "golden.json").write_text(json.dumps(golden, indent=1, sort_keys=True) + "\n")
    print(len(w.contacts), "contacts,", len(order), "messages,", len(golden), "golden")


if __name__ == "__main__":
    main()
