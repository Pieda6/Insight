"""Verifier-side shared-cache model (RFC 9111), written independently of the reference
solution. It replays the verifier's private copy of the log in /tests/data and returns the
expected (action, stored, age) for every request id.
"""
import calendar
import json
import re
import time
from fractions import Fraction
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"

CACHEABLE_BY_DEFAULT = frozenset([200, 203, 204, 206, 300, 301, 308, 404, 405, 410, 414, 501])
SAFE_METHODS = frozenset(["GET", "HEAD", "OPTIONS", "TRACE"])
_IMF = "%a, %d %b %Y %H:%M:%S GMT"


def parse_date(text):
    """IMF-fixdate (plus the two obsolete HTTP-date forms); None if invalid."""
    if text is None:
        return None
    text = text.strip()
    for fmt in (_IMF, "%A, %d-%b-%y %H:%M:%S GMT", "%a %b %d %H:%M:%S %Y"):
        try:
            return calendar.timegm(time.strptime(text, fmt))
        except ValueError:
            continue
    return None


def directives(value):
    found = {}
    for m in re.finditer(r'\s*([!#$%&\'*+\-.^_`|~0-9A-Za-z]+)\s*(?:=\s*("(?:[^"\\]|\\.)*"|[^,]*))?\s*(?:,|$)',
                         value or ""):
        name = m.group(1).lower()
        if name and name not in found:
            arg = m.group(2)
            found[name] = None if arg is None else arg.strip().strip('"')
    return found


def delta(arg):
    return int(arg) if arg is not None and re.fullmatch(r"\d+", arg) else None


class Response:
    def __init__(self, status, fields, req_time, resp_time):
        self.status = status
        self.fields = {k.lower(): v for k, v in fields.items()}
        self.req_time = req_time
        self.resp_time = resp_time

    @property
    def cc(self):
        return directives(self.fields.get("cache-control", ""))

    def date(self):
        d = parse_date(self.fields.get("date"))
        return self.resp_time if d is None else d

    def initial_age(self):
        raw = self.fields.get("age", "").split(",")[0].strip()
        age_value = int(raw) if raw.isdigit() else 0
        apparent = self.resp_time - self.date()
        if apparent < 0:
            apparent = 0
        corrected = age_value + self.resp_time - self.req_time
        return apparent if apparent > corrected else corrected

    def age_at(self, now):
        return self.initial_age() + now - self.resp_time

    def lifetime(self):
        cc = self.cc
        for name in ("s-maxage", "max-age"):
            if name in cc:
                v = delta(cc[name])
                return 0 if v is None else v
        if "expires" in self.fields:
            when = parse_date(self.fields["expires"])
            return -1 if when is None else when - self.date()
        if self.status in CACHEABLE_BY_DEFAULT or "public" in cc:
            lm = parse_date(self.fields.get("last-modified"))
            if lm is not None:
                return Fraction(max(0, self.date() - lm), 10)
        return 0

    def shared_cache_may_store(self, request_fields):
        cc = self.cc
        if self.status < 200 or self.status in (206, 304):
            return False
        if "no-store" in cc or "private" in cc:
            return False
        if "authorization" in request_fields and not ({"public", "s-maxage", "must-revalidate"} & set(cc)):
            return False
        return bool({"public", "max-age", "s-maxage"} & set(cc)) or "expires" in self.fields \
            or self.status in CACHEABLE_BY_DEFAULT

    def merge_304(self, other):
        for k, v in other.fields.items():
            if k != "content-length":
                self.fields[k] = v
        self.req_time, self.resp_time = other.req_time, other.resp_time


def expected():
    cache = {}
    answer = {}
    for line in (DATA / "requests.jsonl").read_text().splitlines():
        r = json.loads(line)
        rid, now, url = r["request_id"], r["received_at"], r["url"]
        method = r["method"].upper()
        req_fields = {k.lower(): v for k, v in r["headers"].items()}
        o = r["origin"]
        incoming = Response(o["status"], o["headers"], now, o["received_at"])

        if method not in SAFE_METHODS:
            if 200 <= incoming.status <= 399:
                cache.pop(url, None)
            answer[rid] = ("MISS", False, incoming.initial_age())
            continue

        held = cache.get(url)
        if held is None:
            keep = method == "GET" and incoming.shared_cache_may_store(req_fields)
            if keep:
                cache[url] = incoming
            answer[rid] = ("MISS", keep, incoming.initial_age())
            continue

        fresh_enough = "no-cache" not in held.cc and held.lifetime() > held.age_at(now)
        if fresh_enough:
            answer[rid] = ("HIT", False, held.age_at(now))
        elif incoming.status == 304:
            held.merge_304(incoming)
            answer[rid] = ("REVALIDATED", True, held.initial_age())
        else:
            keep = method == "GET" and incoming.shared_cache_may_store(req_fields)
            if keep:
                cache[url] = incoming
            answer[rid] = ("REVALIDATED", keep, incoming.initial_age())
    return answer
