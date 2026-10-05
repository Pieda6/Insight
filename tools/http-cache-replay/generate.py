#!/usr/bin/env python3
"""Generate the http-cache-replay request log (not shipped).

Each scenario is a short request sequence on its own URL that exercises one RFC 9111 rule
for a shared cache; scenarios are instantiated several times with random parameters and
interleaved by time into one log. Cases the RFC leaves to the implementer (request
Cache-Control, Vary, qualified private/no-cache, HEAD, ranges, Location invalidation) are
deliberately absent. Writes environment/data/requests.jsonl, an identical tests/data copy
and tests/case_tags.json (request_id -> rule tags, used by the verifier's grouped tests).
"""
import json
import random
import shutil
from email.utils import formatdate
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "tasks" / "http-cache-replay"
ENV = ROOT / "environment" / "data"
TST = ROOT / "tests" / "data"

T0 = 1_780_000_000          # cache clock origin of the log
SKEW = -23                  # origin clock runs 23 s behind the cache clock
rng = random.Random(9111)


def httpdate(cache_time):
    return formatdate(cache_time + SKEW, usegmt=True)


class Seq:
    """Builds the requests of one scenario on one URL."""

    def __init__(self, url, tags):
        self.url, self.tags, self.events = url, tags, []

    def req(self, t, method="GET", headers=None, status=200, rh=None, gen=1, delay=None,
            date=True, tags=(), last_modified=None):
        """t: request arrival (s from scenario start); gen: s until origin generates it;
        delay: s until the cache receives it (>= gen)."""
        delay = delay if delay is not None else gen + rng.randint(0, 2)
        h = dict(rh or {})
        if date:
            h.setdefault("Date", ("@", gen))
        if last_modified is not None:
            h["Last-Modified"] = ("@", last_modified)
        self.events.append(dict(t=t, method=method, headers=headers or {}, status=status,
                                rheaders=h, delay=delay, tags=list(self.tags) + list(tags)))
        return self


def body_headers(extra=None):
    h = {"Content-Type": rng.choice(["text/html; charset=utf-8", "application/json",
                                     "image/png", "text/css", "application/javascript"]),
         "Content-Length": str(rng.randint(300, 90000))}
    h.update(extra or {})
    return h


def client():
    return {"User-Agent": rng.choice(["Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                                      "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5)",
                                      "curl/8.7.1", "okhttp/4.12.0"]),
            "Accept": "*/*"}


def etag():
    return '"%08x"' % rng.getrandbits(32)


# ---------------------------------------------------------------- scenarios
def sc_maxage(url):
    """max-age hit, then stale -> conditional -> 304 refresh -> hit."""
    ma = rng.choice([60, 120, 300])
    e = etag()
    s = Seq(url, ["max-age"])
    s.req(0, headers=client(), rh=body_headers({"Cache-Control": f"max-age={ma}", "ETag": e}))
    s.req(ma // 3, headers=client(), tags=["hit"])
    s.req(ma + 40, headers=client(), status=304,
          rh={"Cache-Control": f"max-age={ma}", "ETag": e}, tags=["revalidate"])
    s.req(ma + 70, headers=client(), tags=["hit"])
    return s


def sc_smaxage(url):
    """s-maxage overrides max-age (and Expires) for a shared cache."""
    longer = rng.random() < 0.5
    ma, sma = (30, 240) if longer else (600, 45)
    e = etag()
    s = Seq(url, ["s-maxage"])
    rh = {"Cache-Control": f"public, max-age={ma}, s-maxage={sma}", "ETag": e}
    if rng.random() < 0.5:
        rh["Expires"] = ("@", 3600)
    s.req(0, headers=client(), rh=body_headers(rh))
    probe = (ma + sma) // 2
    s.req(probe, headers=client(), status=304, rh={"ETag": e, "Cache-Control": rh["Cache-Control"]},
          tags=["s-maxage-decides"])
    return s


def sc_expires_skew(url):
    """Expires lifetime is Expires minus Date (origin clock), not Expires minus cache time."""
    life = rng.choice([90, 150])
    e = etag()
    s = Seq(url, ["expires"])
    s.req(0, headers=client(), rh=body_headers({"Expires": ("@", life), "ETag": e}))
    # The origin clock is behind, so this probe is still fresh against Date but would look
    # stale if Expires were compared with the cache's receive time.
    s.req(life - 30, headers=client(), tags=["expires-edge"])
    s.req(life + 30, headers=client(), status=304, rh={"ETag": e, "Expires": ("@", life + 200)},
          tags=["expires-stale"])
    return s


def sc_expires_with_maxage(url):
    """max-age present: Expires must be ignored."""
    e = etag()
    s = Seq(url, ["expires", "max-age"])
    s.req(0, headers=client(), rh=body_headers({"Cache-Control": "max-age=40",
                                                "Expires": ("@", 4000), "ETag": e}))
    s.req(100, headers=client(), status=304, rh={"ETag": e, "Cache-Control": "max-age=40"},
          tags=["expires-ignored"])
    return s


def sc_expires_invalid(url):
    """Expires: 0 is an invalid date: stored, but already stale."""
    e = etag()
    s = Seq(url, ["expires"])
    s.req(0, headers=client(), rh=body_headers({"Expires": "0", "ETag": e}))
    s.req(5, headers=client(), status=304, rh={"ETag": e, "Cache-Control": "max-age=60"},
          tags=["expires-invalid"])
    s.req(20, headers=client(), tags=["hit"])
    return s


def sc_auth(url):
    """Authorized request: shared cache may store only with public / s-maxage / must-revalidate."""
    kind = rng.choice(["max-age", "public", "s-maxage", "must-revalidate", "max-age", "private"])
    cc = {"max-age": "max-age=300", "public": "public, max-age=300", "s-maxage": "s-maxage=300",
          "must-revalidate": "max-age=300, must-revalidate", "private": "private, max-age=300"}[kind]
    e = etag()
    h = client()
    h["Authorization"] = "Bearer " + "%016x" % rng.getrandbits(64)
    s = Seq(url, ["authorization"])
    s.req(0, headers=h, rh=body_headers({"Cache-Control": cc, "ETag": e}), tags=[f"auth-{kind}"])
    s.req(60, headers=client(), rh=body_headers({"Cache-Control": cc, "ETag": e}),
          tags=[f"auth-{kind}-followup"])
    return s


def sc_private_nostore(url):
    kind = rng.choice(["private", "no-store"])
    cc = {"private": "private, max-age=600", "no-store": "no-store"}[kind]
    s = Seq(url, [kind])
    s.req(0, headers=client(), rh=body_headers({"Cache-Control": cc}))
    s.req(30, headers=client(), rh=body_headers({"Cache-Control": cc}), tags=[f"{kind}-followup"])
    return s


def sc_nocache(url):
    """no-cache response: stored, but every reuse needs validation."""
    e = etag()
    s = Seq(url, ["no-cache"])
    s.req(0, headers=client(), rh=body_headers({"Cache-Control": "no-cache, max-age=600", "ETag": e}))
    s.req(10, headers=client(), status=304, rh={"ETag": e, "Cache-Control": "no-cache, max-age=600"},
          tags=["no-cache-reuse"])
    s.req(25, headers=client(), status=304, rh={"ETag": e, "Cache-Control": "no-cache, max-age=600"},
          tags=["no-cache-reuse"])
    return s


def sc_heuristic(url, force_public=False):
    """Heuristic freshness only for heuristically cacheable codes (or public)."""
    status = rng.choice([302, 307]) if force_public else rng.choice([200, 301, 404, 302, 307, 302])
    public = force_public
    lm_age = rng.choice([2000, 3000, 4500])          # Date - Last-Modified
    e = etag()
    rh = body_headers({"ETag": e})
    if status in (301, 302, 307):
        rh["Location"] = url + "/next"
    if public:
        rh["Cache-Control"] = "public"
    s = Seq(url, ["heuristic"])
    s.req(0, headers=client(), status=status, rh=rh, last_modified=-lm_age,
          tags=[f"heuristic-{status}{'-public' if public else ''}"])
    probe = lm_age // 10 - rng.choice([30, 60])
    rh2 = dict(rh)
    s.req(probe, headers=client(), status=status, rh=rh2, last_modified=-lm_age,
          tags=[f"heuristic-{status}{'-public' if public else ''}-followup"])
    return s


def sc_age_math(url):
    """Upstream Age header plus response delay; boundary where lifetime == current_age."""
    ma = rng.choice([100, 200])
    upstream_age = rng.choice([15, 35, 50])
    gen, delay = 2, rng.choice([4, 6, 9])
    e = etag()
    s = Seq(url, ["age"])
    s.req(0, headers=client(), gen=gen, delay=delay,
          rh=body_headers({"Cache-Control": f"max-age={ma}", "Age": str(upstream_age), "ETag": e}),
          tags=["age-first"])
    # corrected_initial_age = max(apparent, upstream_age + delay); pick the boundary exactly
    apparent = max(0, delay - gen)
    cia = max(apparent, upstream_age + delay)
    edge = ma - cia + delay                      # request time where current_age == ma
    s.req(edge - 20, headers=client(), tags=["age-hit"])
    s.req(edge, headers=client(), status=304, rh={"ETag": e, "Cache-Control": f"max-age={ma}", "Age": "0"},
          tags=["age-boundary"])
    return s


def sc_invalidation(url):
    """Unsafe method: a non-error response invalidates; an error response does not."""
    ok = rng.random() < 0.6
    e = etag()
    s = Seq(url, ["invalidation"])
    s.req(0, headers=client(), rh=body_headers({"Cache-Control": "max-age=900", "ETag": e}))
    method = rng.choice(["POST", "PUT", "DELETE"])
    st = rng.choice([200, 204, 303]) if ok else rng.choice([400, 409, 500, 503])
    s.req(40, method=method, headers=client(), status=st,
          rh=body_headers({"Cache-Control": "no-store"}), tags=[f"unsafe-{'ok' if ok else 'error'}"])
    s.req(80, headers=client(), rh=body_headers({"Cache-Control": "max-age=900", "ETag": e}),
          tags=[f"after-unsafe-{'ok' if ok else 'error'}"])
    return s


def sc_no_date(url):
    """No Date header: the receive time stands in for it."""
    e = etag()
    s = Seq(url, ["no-date"])
    s.req(0, headers=client(), date=False, delay=5,
          rh=body_headers({"Expires": ("@", 120), "ETag": e}), tags=["no-date"])
    s.req(100, headers=client(), status=304, rh={"ETag": e, "Expires": ("@", 400)}, tags=["no-date-followup"])
    return s


def sc_replace(url):
    """Validation answered with a full 200: the new response replaces the stored one."""
    e1, e2 = etag(), etag()
    s = Seq(url, ["replace"])
    s.req(0, headers=client(), rh=body_headers({"Cache-Control": "max-age=50", "ETag": e1}))
    s.req(70, headers=client(), rh=body_headers({"Cache-Control": "max-age=400", "ETag": e2}),
          tags=["replaced"])
    s.req(300, headers=client(), tags=["hit"])
    return s


SCENARIOS = [(sc_maxage, 4), (sc_smaxage, 6), (sc_expires_skew, 4), (sc_expires_with_maxage, 4),
             (sc_expires_invalid, 3), (sc_auth, 10), (sc_private_nostore, 5), (sc_nocache, 3),
             (sc_heuristic, 12), (lambda u: sc_heuristic(u, True), 4), (sc_age_math, 6), (sc_invalidation, 7), (sc_no_date, 3),
             (sc_replace, 3)]
PATHS = ["/assets/app", "/static/css/site", "/api/v2/catalog", "/img/hero", "/account/summary",
         "/news/article", "/docs/guide", "/api/v2/prices", "/media/thumb", "/legacy/redirect"]


def build():
    seqs = []
    n = 0
    for fn, count in SCENARIOS:
        for _ in range(count):
            n += 1
            seqs.append(fn(f"https://www.example-shop.com{rng.choice(PATHS)}/{n:03d}"))
    rows = []
    for s in seqs:
        start = T0 + rng.randint(0, 3000)
        for ev in s.events:
            t = start + ev["t"]
            gen_time = t + 1
            rh = {}
            for k, v in ev["rheaders"].items():
                if isinstance(v, tuple):          # ("@", offset): HTTP-date relative to the request
                    off = v[1]
                    v = httpdate(gen_time + off - 1 if k != "Date" else t + off)
                rh[k] = v
            rows.append(dict(received_at=t, method=ev["method"], url=s.url, headers=ev["headers"],
                             origin=dict(status=ev["status"], headers=rh, received_at=t + ev["delay"]),
                             tags=ev["tags"]))
    rows.sort(key=lambda r: (r["received_at"], r["url"]))
    tags = {}
    out = []
    for i, r in enumerate(rows, 1):
        rid = f"R{i:04d}"
        tags[rid] = r.pop("tags")
        out.append(dict(request_id=rid, **r))
    return out, tags


def main():
    import sys
    if "--seed" in sys.argv:  # dev cross-check only: alternate log written to --out
        rng.seed(int(sys.argv[sys.argv.index("--seed") + 1]))
        out = Path(sys.argv[sys.argv.index("--out") + 1])
        out.mkdir(parents=True, exist_ok=True)
        rows, _ = build()
        (out / "requests.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        return
    rows, tags = build()
    for d in (ENV, TST):
        d.mkdir(parents=True, exist_ok=True)
    (ENV / "requests.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    shutil.copy(ENV / "requests.jsonl", TST / "requests.jsonl")
    (ROOT / "tests" / "case_tags.json").write_text(json.dumps(tags, indent=1, sort_keys=True) + "\n")
    print(len(rows), "requests")


if __name__ == "__main__":
    main()
