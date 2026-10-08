"""Verifier-side model of 47 CFR 64.1200 for a promotional SMS batch, written independently of
the reference solution. It walks every UTC minute from the scheduled time to the end of the
7-day horizon and returns the first minute at which every applicable rule permits the send.
Reads only the verifier's private copy of the inputs in /tests/data.
"""
import calendar
import csv
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

DATA = Path(__file__).resolve().parent / "data"
Z = timezone.utc
FMT = "%Y-%m-%dT%H:%M:%SZ"

# 64.1200(a)(10): words that revoke consent per se when sent in reply to a text.
REVOCATION_WORDS = ("stop", "quit", "end", "revoke", "opt out", "cancel", "unsubscribe")
# Unambiguous, explicitly worded requests to stop (the only non-keyword form in the data).
REQUEST_PHRASES = ("stop texting", "do not text", "don't text", "remove me", "no more texts")


def rows(name):
    with open(DATA / name, newline="") as fh:
        return list(csv.DictReader(fh))


def when(text):
    return datetime.strptime(text, FMT).replace(tzinfo=Z)


def shift_months(day, months):
    total = day.year * 12 + (day.month - 1) + months
    y, m = total // 12, total % 12 + 1
    return date(y, m, min(day.day, calendar.monthrange(y, m)[1]))


def is_revocation(text):
    t = text.strip().lower()
    while t and not t[-1].isalnum():
        t = t[:-1]
    while t and not t[0].isalnum():
        t = t[1:]
    if t in REVOCATION_WORDS:
        return True
    return any(p in t for p in REQUEST_PHRASES)


def platform_is_atds(equipment):
    # 64.1200(f)(2): capacity to store or produce numbers with a random or sequential number
    # generator, and to dial them.
    e = equipment.lower()
    return "has the capacity" in e and "random or sequential number generator" in e


class Recipient:
    def __init__(self, row):
        self.tz = ZoneInfo(row["address_time_zone"])
        self.phone = row["phone"]
        self.written_consents = []
        self.dnc_requests = []
        self.purchases = []
        self.inquiries = []
        self.registry = []

    def request_active(self, t):
        for r in self.dnc_requests:
            end = r.replace(year=r.year + 5)                 # 64.1200(d)(6)
            if r <= t < end:
                return True
        return False

    def first_request(self):
        return min(self.dnc_requests) if self.dnc_requests else None

    def has_consent(self, t):
        fr = self.first_request()
        if fr is not None and fr <= t:
            return False                                    # revoked, never restored
        return any(c <= t for c in self.written_consents)

    def has_ebr(self, t):
        fr = self.first_request()
        if fr is not None and fr <= t:
            return False                                    # 64.1200(f)(5)(i)
        today = t.astimezone(self.tz).date()
        p_from, i_from = shift_months(today, -18), shift_months(today, -3)
        return any(p_from <= d <= today for d in self.purchases) or \
            any(i_from <= d <= today for d in self.inquiries)

    def registered(self, t):
        return any(a <= t and (b is None or t < b) for a, b in self.registry)

    def within_hours(self, t):
        lt = t.astimezone(self.tz)
        hm = (lt.hour, lt.minute)
        return (8, 0) <= hm <= (21, 0)

    def may_send(self, t, atds):
        if self.request_active(t):
            return False
        consent = self.has_consent(t)
        if atds and not consent:
            return False
        solicitation = not (consent or self.has_ebr(t))
        if solicitation and (self.registered(t) or not self.within_hours(t)):
            return False
        return True


def expected():
    seller = json.loads((DATA / "seller.json").read_text())["seller_legal_name"]
    people = {r["contact_id"]: Recipient(r) for r in rows("contacts.csv")}
    phone_owner = {p.phone: cid for cid, p in people.items()}
    atds = {r["platform_id"]: platform_is_atds(r["equipment"]) for r in rows("platforms.csv")}
    for r in rows("consents.csv"):
        p = people[r["contact_id"]]
        elements = (r["in_writing"] == "true", r["signature"] != "none", r["seller_named"] == seller,
                    r["phone_number"] == p.phone, r["discloses_autodialed_marketing"] == "true",
                    r["discloses_not_condition_of_purchase"] == "true")
        if all(elements):
            p.written_consents.append(when(r["obtained_at"]))
    for r in rows("replies.csv"):
        if is_revocation(r["text"]):
            people[r["contact_id"]].dnc_requests.append(when(r["received_at"]))
    for r in rows("seller_dnc_requests.csv"):
        people[r["contact_id"]].dnc_requests.append(when(r["received_at"]))
    for r in rows("customer_history.csv"):
        p = people[r["contact_id"]]
        (p.purchases if r["event_type"] == "purchase" else p.inquiries).append(
            date.fromisoformat(r["event_date"]))
    for r in rows("national_dnc_matches.csv"):
        cid = phone_owner.get(r["phone"])
        if cid:
            people[cid].registry.append((when(r["registered_at"]),
                                         when(r["cancelled_at"]) if r["cancelled_at"] else None))

    answer = {}
    for m in rows("scheduled_messages.csv"):
        p, a = people[m["contact_id"]], atds[m["platform_id"]]
        start = when(m["scheduled_at"])
        t, stop, hit = start, start + timedelta(days=7), None
        while t <= stop:
            if p.may_send(t, a):
                hit = t
                break
            t += timedelta(minutes=1)
        if hit is None:
            answer[m["message_id"]] = ("BLOCK", "")
        else:
            answer[m["message_id"]] = ("SEND" if hit == start else "RESCHEDULE", hit.strftime(FMT))
    return answer
