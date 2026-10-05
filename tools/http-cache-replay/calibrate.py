#!/usr/bin/env python3
"""Dev-only calibration for http-cache-replay (never uploaded).

1. Cross-checks the verifier engine against the reference solution on the shipped log and on
   many freshly generated logs (different seeds).
2. Runs common RFC 9111 shortcuts (patched copies of the reference solution) through the real
   tests and reports which tests each one fails. Every shortcut must fail at least one test.
3. Checks that the oracle passes and an empty output fails.

Run from the repo root:  python3 tools/http-cache-replay/calibrate.py
Needs /app/data and /app/output to be writable (it copies the log there).
"""
import contextlib
import csv
import importlib.util
import shutil
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TASK = ROOT / "tasks" / "http-cache-replay"
OUT = Path("/app/output/decisions.csv")


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


solve = load("solve", TASK / "solution" / "solve.py")
engine = load("engine", TASK / "tests" / "engine.py")


def write(rows):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["request_id", "action", "stored", "age"])
        for rid, action, stored, age in rows:
            w.writerow([rid, action, "true" if stored else "false", age])


def run_tests():
    p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-rf", "-p", "no:cacheprovider",
                        str(TASK / "tests" / "test_outputs.py")], capture_output=True, text=True)
    failed = [ln.split("::", 1)[1].split(" ")[0] for ln in p.stdout.splitlines() if ln.startswith("FAILED")]
    return p.returncode, failed


def lines():
    return (Path("/app/data") / "requests.jsonl").read_text().splitlines()


@contextlib.contextmanager
def patched(obj, name, value):
    old = getattr(obj, name)
    setattr(obj, name, value)
    try:
        yield
    finally:
        setattr(obj, name, old)


S = solve.Stored
orig_storable = solve.storable
orig_lifetime = S.freshness_lifetime
orig_cia = S.corrected_initial_age


def browser_cache(rh, status, h):  # private cache semantics: private allowed, auth ignored
    cc = solve.cache_control(h)
    if status in (206, 304) or status < 200 or "no-store" in cc:
        return False
    return "public" in cc or "private" in cc or "expires" in h or "max-age" in cc or status in solve.HEURISTIC


def auth_never(rh, status, h):
    return "authorization" not in rh and orig_storable(rh, status, h)


def auth_always(rh, status, h):
    return orig_storable({}, status, h) and "private" not in solve.cache_control(h)


def nocache_is_nostore(rh, status, h):
    return "no-cache" not in solve.cache_control(h) and orig_storable(rh, status, h)


def invalid_expires_unstorable(rh, status, h):
    if "expires" in h and solve.http_date(h["expires"]) is None:
        return False
    return orig_storable(rh, status, h)


def ignore_smaxage(self):
    h = dict(self.headers)
    cc = solve.cache_control(h)
    if "s-maxage" in cc:
        h["cache-control"] = ", ".join(p for p in h["cache-control"].split(",") if "s-maxage" not in p)
    tmp = S(self.status, h, self.request_time, self.response_time)
    return orig_lifetime(tmp)


def store_any_with_last_modified(rh, status, h):
    return orig_storable(rh, status, h) or (
        "last-modified" in h and status >= 200 and status not in (206, 304)
        and not ({"no-store", "private"} & set(solve.cache_control(h))))


def heuristic_any_status(self):
    cc = solve.cache_control(self.headers)
    if any(d in cc for d in ("s-maxage", "max-age")) or "expires" in self.headers:
        return orig_lifetime(self)
    lm = solve.http_date(self.headers.get("last-modified"))
    return Fraction(max(0, self.date_value() - lm), 10) if lm is not None else 0


def expires_over_maxage(self):
    if "expires" in self.headers and "s-maxage" not in solve.cache_control(self.headers):
        exp = solve.http_date(self.headers["expires"])
        return -1 if exp is None else exp - self.date_value()
    return orig_lifetime(self)


def expires_vs_cache_clock(self):
    cc = solve.cache_control(self.headers)
    if "expires" in self.headers and not any(d in cc for d in ("s-maxage", "max-age")):
        exp = solve.http_date(self.headers["expires"])
        return -1 if exp is None else exp - self.response_time
    return orig_lifetime(self)


def age_now_minus_date(self):
    return max(0, self.response_time - self.date_value())


def age_no_delay(self):
    a = self.headers.get("age", "").split(",")[0].strip()
    age_value = int(a) if a.isdigit() else 0
    return max(max(0, self.response_time - self.date_value()), age_value)


def age_corrected_only(self):
    a = self.headers.get("age", "").split(",")[0].strip()
    return (int(a) if a.isdigit() else 0) + self.response_time - self.request_time


def age_ignore_header(self):
    return max(max(0, self.response_time - self.date_value()), self.response_time - self.request_time)


def fresh_ge(self, now):
    if "no-cache" in solve.cache_control(self.headers):
        return False
    return self.freshness_lifetime() >= self.current_age(now)


def run_replay_variant(**kw):
    """Variants that need control-flow changes."""
    store, rows = {}, []
    import json
    for line in lines():
        req = json.loads(line)
        now, method, url = req["received_at"], req["method"].upper(), req["url"]
        rh = solve.lower(req["headers"])
        o = req["origin"]
        st, oh, ot = o["status"], solve.lower(o["headers"]), o["received_at"]
        if method not in solve.SAFE:
            if kw.get("invalidate_any") or 200 <= st < 400:
                if not kw.get("no_invalidation"):
                    store.pop(url, None)
            rows.append((req["request_id"], "MISS", False, S(st, oh, now, ot).corrected_initial_age()))
            continue
        e = store.get(url)
        if e is not None and e.reusable_without_validation(now):
            rows.append((req["request_id"], "HIT", False, e.current_age(now)))
            continue
        if e is not None:
            if st == 304:
                if kw.get("304_keeps_old"):
                    rows.append((req["request_id"], "REVALIDATED", True, e.current_age(now)))
                else:
                    e.update(oh, now, ot)
                    rows.append((req["request_id"], "REVALIDATED", True, e.corrected_initial_age()))
                continue
            f = S(st, oh, now, ot)
            ok = solve.storable(rh, st, oh)
            if ok:
                store[url] = f
            rows.append((req["request_id"], "REVALIDATED", ok, f.corrected_initial_age()))
            continue
        f = S(st, oh, now, ot)
        ok = solve.storable(rh, st, oh)
        if ok:
            store[url] = f
        rows.append((req["request_id"], "MISS", ok, f.corrected_initial_age()))
    return rows


SHORTCUTS = {
    "browser/private-cache semantics": [(solve, "storable", browser_cache)],
    "authorization responses never stored": [(solve, "storable", auth_never)],
    "authorization ignored": [(solve, "storable", auth_always)],
    "no-cache treated as no-store": [(solve, "storable", nocache_is_nostore)],
    "invalid Expires treated as unstorable": [(solve, "storable", invalid_expires_unstorable)],
    "s-maxage ignored": [(S, "freshness_lifetime", ignore_smaxage)],
    "heuristic on any status": [(S, "freshness_lifetime", heuristic_any_status),
                                (solve, "storable", store_any_with_last_modified)],
    "Expires preferred over max-age": [(S, "freshness_lifetime", expires_over_maxage)],
    "Expires measured on cache clock": [(S, "freshness_lifetime", expires_vs_cache_clock)],
    "age = now - Date only": [(S, "corrected_initial_age", age_now_minus_date)],
    "age without response delay": [(S, "corrected_initial_age", age_no_delay)],
    "corrected age value only (no max)": [(S, "corrected_initial_age", age_corrected_only)],
    "upstream Age header ignored": [(S, "corrected_initial_age", age_ignore_header)],
    "fresh when lifetime >= age": [(S, "reusable_without_validation", fresh_ge)],
    "invalidate on any status": {"invalidate_any": True},
    "never invalidate": {"no_invalidation": True},
    "304 does not refresh stored response": {"304_keeps_old": True},
}


def main():
    Path("/app/data").mkdir(parents=True, exist_ok=True)
    shutil.copy(TASK / "environment" / "data" / "requests.jsonl", "/app/data/requests.jsonl")

    want = engine.expected()
    got = {r[0]: r[1:] for r in solve.replay(lines())}
    mism = [k for k in want if want[k] != got.get(k)]
    print(f"engine vs solve on shipped log: {len(want)} rows, {len(mism)} mismatches {mism[:5]}")

    gen = ROOT / "tools" / "http-cache-replay" / "generate.py"
    if "--seeds" in sys.argv:
        n = int(sys.argv[sys.argv.index("--seeds") + 1])
        tmp = Path("/tmp/hcr-seeds")
        total = bad = 0
        for seed in range(n):
            subprocess.run([sys.executable, str(gen), "--seed", str(seed), "--out", str(tmp)], check=True,
                           capture_output=True)
            engine.DATA = tmp
            e = engine.expected()
            s = {r[0]: r[1:] for r in solve.replay((tmp / "requests.jsonl").read_text().splitlines())}
            total += len(e)
            bad += sum(1 for k in e if e[k] != s.get(k))
        engine.DATA = TASK / "tests" / "data"
        print(f"engine vs solve over {n} seeds: {total} rows, {bad} mismatches")

    write(solve.replay(lines()))
    rc, failed = run_tests()
    print(f"oracle: rc={rc} failed={failed}")
    OUT.unlink()
    rc, failed = run_tests()
    print(f"nop: rc={rc} (must be non-zero)")

    ok = True
    for name, spec in SHORTCUTS.items():
        if isinstance(spec, dict):
            rows = run_replay_variant(**spec)
        else:
            with contextlib.ExitStack() as st:
                for obj, attr, fn in spec:
                    st.enter_context(patched(obj, attr, fn))
                rows = solve.replay(lines())
        nwrong = sum(1 for r in rows if want[r[0]] != tuple(r[1:]))
        write(rows)
        rc, failed = run_tests()
        flag = "ok " if rc else "!! PASSES"
        ok &= bool(rc)
        print(f"{flag} {name:45s} wrong rows={nwrong:3d}  failed={failed}")
    write(solve.replay(lines()))
    print("ALL SHORTCUTS FAIL" if ok else "SOME SHORTCUT PASSES")


if __name__ == "__main__":
    main()
