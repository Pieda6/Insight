#!/usr/bin/env python3
"""Reference solution: replay a request log through a shared cache conforming to RFC 9111.

Times are integer seconds on the cache clock (received_at); Date/Expires/Last-Modified are
HTTP-dates on the origin clock. Heuristic lifetimes are kept as exact fractions.
"""
import csv
import json
from email.utils import parsedate_to_datetime
from fractions import Fraction
from pathlib import Path

DATA = Path("/app/data")
OUT = Path("/app/output")

SAFE = {"GET", "HEAD", "OPTIONS", "TRACE"}
# RFC 9110 Section 15.1: status codes that are heuristically cacheable.
HEURISTIC = {200, 203, 204, 206, 300, 301, 308, 404, 405, 410, 414, 501}
# RFC 9111 Section 3.5: directives that let a shared cache reuse a response to an
# authorized request.
AUTH_OK = ("must-revalidate", "public", "s-maxage")


def lower(headers):
    return {k.lower(): v for k, v in headers.items()}


def http_date(value):
    if value is None:
        return None
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    if dt is None or dt.tzinfo is None:
        return None
    return int(dt.timestamp())


def cache_control(headers):
    """Directive name -> argument (None if absent); first occurrence wins."""
    out = {}
    for part in headers.get("cache-control", "").split(","):
        part = part.strip()
        if not part:
            continue
        name, _, arg = part.partition("=")
        name = name.strip().lower()
        if name not in out:
            out[name] = arg.strip().strip('"') if arg else None
    return out


def seconds(cc, name):
    v = cc.get(name)
    return int(v) if v is not None and v.isdigit() else None


class Stored:
    def __init__(self, status, headers, request_time, response_time):
        self.status = status
        self.headers = dict(headers)
        self.request_time = request_time
        self.response_time = response_time

    def update(self, headers, request_time, response_time):
        """RFC 9111 Section 3.2: replace fields present in the 304 (except Content-Length)."""
        for k, v in headers.items():
            if k != "content-length":
                self.headers[k] = v
        self.request_time = request_time
        self.response_time = response_time

    def date_value(self):
        d = http_date(self.headers.get("date"))
        return self.response_time if d is None else d

    def corrected_initial_age(self):
        age = self.headers.get("age", "").split(",")[0].strip()
        age_value = int(age) if age.isdigit() else 0
        apparent_age = max(0, self.response_time - self.date_value())
        corrected_age_value = age_value + (self.response_time - self.request_time)
        return max(apparent_age, corrected_age_value)

    def current_age(self, now):
        return self.corrected_initial_age() + (now - self.response_time)

    def freshness_lifetime(self):
        cc = cache_control(self.headers)
        if "s-maxage" in cc:
            v = seconds(cc, "s-maxage")
            return v if v is not None else 0
        if "max-age" in cc:
            v = seconds(cc, "max-age")
            return v if v is not None else 0
        if "expires" in self.headers:
            exp = http_date(self.headers["expires"])
            if exp is None:  # invalid dates, including "0", mean already expired
                return -1
            return exp - self.date_value()
        if self.status in HEURISTIC or "public" in cc:
            lm = http_date(self.headers.get("last-modified"))
            if lm is not None:
                return Fraction(max(0, self.date_value() - lm), 10)
        return 0

    def reusable_without_validation(self, now):
        if "no-cache" in cache_control(self.headers):
            return False
        return self.freshness_lifetime() > self.current_age(now)


def storable(request_headers, status, headers):
    """RFC 9111 Section 3 for a shared cache (request method already known to be GET)."""
    if status in (206, 304) or status < 200:
        return False
    cc = cache_control(headers)
    if "no-store" in cc or "private" in cc:
        return False
    if "authorization" in request_headers and not any(d in cc for d in AUTH_OK):
        return False
    return ("public" in cc or "expires" in headers or "max-age" in cc
            or "s-maxage" in cc or status in HEURISTIC)


def replay(lines):
    store = {}
    rows = []
    for line in lines:
        req = json.loads(line)
        now = req["received_at"]
        method = req["method"].upper()
        url = req["url"]
        rh = lower(req["headers"])
        origin = req["origin"]
        o_status, o_headers, o_time = origin["status"], lower(origin["headers"]), origin["received_at"]

        if method not in SAFE:  # write-through; invalidate on a non-error response
            if 200 <= o_status < 400:
                store.pop(url, None)
            age = Stored(o_status, o_headers, now, o_time).corrected_initial_age()
            rows.append((req["request_id"], "MISS", False, age))
            continue

        entry = store.get(url)
        if entry is not None and entry.reusable_without_validation(now):
            rows.append((req["request_id"], "HIT", False, entry.current_age(now)))
            continue

        if entry is not None:  # stored but not usable as is: validate with the origin
            if o_status == 304:
                entry.update(o_headers, now, o_time)
                rows.append((req["request_id"], "REVALIDATED", True, entry.corrected_initial_age()))
                continue
            fresh = Stored(o_status, o_headers, now, o_time)
            stored = method == "GET" and storable(rh, o_status, o_headers)
            if stored:
                store[url] = fresh
            rows.append((req["request_id"], "REVALIDATED", stored, fresh.corrected_initial_age()))
            continue

        fresh = Stored(o_status, o_headers, now, o_time)
        stored = method == "GET" and storable(rh, o_status, o_headers)
        if stored:
            store[url] = fresh
        rows.append((req["request_id"], "MISS", stored, fresh.corrected_initial_age()))
    return rows


def main():
    rows = replay((DATA / "requests.jsonl").read_text().splitlines())
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "decisions.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["request_id", "action", "stored", "age"])
        for rid, action, stored, age in rows:
            w.writerow([rid, action, "true" if stored else "false", age])


if __name__ == "__main__":
    main()
