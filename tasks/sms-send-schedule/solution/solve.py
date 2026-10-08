#!/usr/bin/env python3
"""Reference solution: clear a scheduled promotional SMS batch under 47 CFR 64.1200.

For each message, the send is allowed at instant t when:
  * no seller-specific do-not-call request is being honored at t (64.1200(d)(3), (d)(6));
    a revoking reply counts as such a request and also revokes consent (64.1200(a)(10));
  * if the platform is an automatic telephone dialing system (64.1200(f)(2)), the recipient has
    unrevoked prior express written consent meeting 64.1200(f)(9) (64.1200(a)(2));
  * if the message is a telephone solicitation (64.1200(f)(15): no permission and no established
    business relationship under 64.1200(f)(5)), the number is not on the national registry
    (64.1200(c)(2)) and local time is between 8 a.m. and 9 p.m. (64.1200(c)(1)).
The earliest allowed minute at or after the scheduled time, within 7 days, is the send time.
Allowed status can only switch on at a local 08:00 or when a seller do-not-call period ends,
so only those instants (plus the scheduled time) need checking.
"""
import csv
import json
import re
import string
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

DATA = Path("/app/data")
OUT = Path("/app/output")
UTC = timezone.utc
HORIZON = timedelta(days=7)
EBR_PURCHASE_MONTHS = 18     # 64.1200(f)(5): purchase or transaction
EBR_INQUIRY_MONTHS = 3       # 64.1200(f)(5): inquiry or application
SELLER_DNC_YEARS = 5         # 64.1200(d)(6)
PER_SE = {"stop", "quit", "end", "revoke", "opt out", "cancel", "unsubscribe"}   # 64.1200(a)(10)
EXPLICIT = re.compile(r"\b(stop|don'?t|do not|no more|remove me)\b.*\b(text|texting|texts|message|messages|list)\b")


def read(name):
    with open(DATA / name, newline="") as f:
        return list(csv.DictReader(f))


def ts(s):
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def months_before(d, n):
    y, m = divmod(d.year * 12 + d.month - 1 - n, 12)
    m += 1
    last = (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)).day
    return date(y, m, min(d.day, last))


def add_years(t, n):
    return t.replace(year=t.year + n)


def revokes(text):
    norm = " ".join(text.lower().translate(str.maketrans("", "", string.punctuation.replace("'", ""))).split())
    return norm in PER_SE or bool(EXPLICIT.search(norm))


def load():
    seller = json.loads((DATA / "seller.json").read_text())["seller_legal_name"]
    contacts = {c["contact_id"]: c for c in read("contacts.csv")}
    autodialer = {}
    for p in read("platforms.csv"):
        eq = p["equipment"].lower()
        autodialer[p["platform_id"]] = "does not have the capacity" not in eq and "random or sequential" in eq
    info = {cid: dict(consent=[], requests=[], purchases=[], inquiries=[], registry=[]) for cid in contacts}
    for r in read("consents.csv"):
        c = contacts[r["contact_id"]]
        ok = (r["in_writing"] == "true" and r["signature"] in ("electronic", "wet_ink")
              and r["seller_named"] == seller and r["phone_number"] == c["phone"]
              and r["discloses_autodialed_marketing"] == "true"
              and r["discloses_not_condition_of_purchase"] == "true")
        if ok:
            info[r["contact_id"]]["consent"].append(ts(r["obtained_at"]))
    for r in read("replies.csv"):
        if revokes(r["text"]):
            info[r["contact_id"]]["requests"].append(ts(r["received_at"]))
    for r in read("seller_dnc_requests.csv"):
        info[r["contact_id"]]["requests"].append(ts(r["received_at"]))
    for r in read("customer_history.csv"):
        key = "purchases" if r["event_type"] == "purchase" else "inquiries"
        info[r["contact_id"]][key].append(date.fromisoformat(r["event_date"]))
    by_phone = {c["phone"]: cid for cid, c in contacts.items()}
    for r in read("national_dnc_matches.csv"):
        if r["phone"] in by_phone:
            info[by_phone[r["phone"]]]["registry"].append(
                (ts(r["registered_at"]), ts(r["cancelled_at"]) if r["cancelled_at"] else None))
    return contacts, autodialer, info


def allowed(t, c, k, is_atdms):
    zone = ZoneInfo(c["address_time_zone"])
    local = t.astimezone(zone)
    if any(r <= t < add_years(r, SELLER_DNC_YEARS) for r in k["requests"]):
        return False
    first_request = min(k["requests"], default=None)
    consent = any(o <= t for o in k["consent"]) and (first_request is None or first_request > t)
    if is_atdms and not consent:
        return False
    d = local.date()
    ebr = False
    if first_request is None or first_request > t:
        ebr = any(months_before(d, EBR_PURCHASE_MONTHS) <= e <= d for e in k["purchases"]) or \
            any(months_before(d, EBR_INQUIRY_MONTHS) <= e <= d for e in k["inquiries"])
    if consent or ebr:
        return True
    if any(reg <= t and (can is None or t < can) for reg, can in k["registry"]):
        return False
    minutes = local.hour * 60 + local.minute
    return 8 * 60 <= minutes <= 21 * 60


def candidates(sched, c, k):
    zone = ZoneInfo(c["address_time_zone"])
    out = {sched}
    day = sched.astimezone(zone).date()
    for i in range(9):
        d = day + timedelta(days=i)
        out.add(datetime(d.year, d.month, d.day, 8, 0, tzinfo=zone).astimezone(UTC))
    out.update(add_years(r, SELLER_DNC_YEARS) for r in k["requests"])
    return sorted(t for t in out if sched <= t <= sched + HORIZON)


def main():
    contacts, autodialer, info = load()
    rows = []
    for m in read("scheduled_messages.csv"):
        c, k = contacts[m["contact_id"]], info[m["contact_id"]]
        sched = ts(m["scheduled_at"])
        found = next((t for t in candidates(sched, c, k) if allowed(t, c, k, autodialer[m["platform_id"]])), None)
        if found == sched:
            rows.append((m["message_id"], "SEND", sched))
        elif found is not None:
            rows.append((m["message_id"], "RESCHEDULE", found))
        else:
            rows.append((m["message_id"], "BLOCK", None))
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "send_schedule.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["message_id", "decision", "send_at"])
        for mid, dec, t in rows:
            w.writerow([mid, dec, t.strftime("%Y-%m-%dT%H:%M:%SZ") if t else ""])


if __name__ == "__main__":
    main()
