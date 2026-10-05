"""Verifier for http-cache-replay.

The expected behaviour is recomputed by an independent RFC 9111 shared-cache model
(engine.py) from the verifier's own copy of the log. No agent code is executed.
"""
import csv
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import engine  # noqa: E402

OUT = Path("/app/output/decisions.csv")
TAGS = json.loads((Path(__file__).resolve().parent / "case_tags.json").read_text())

GROUPS = {
    "authorization": ["auth-"],
    "private_and_no_store": ["private", "no-store"],
    "s_maxage": ["s-maxage-decides"],
    "expires": ["expires-", "no-date"],
    "heuristic_freshness": ["heuristic-"],
    "age_calculation": ["age-"],
    "no_cache_revalidation": ["no-cache-reuse", "revalidate", "replaced"],
    "invalidation": ["unsafe-", "after-unsafe-"],
}


@pytest.fixture(scope="module")
def truth():
    return engine.expected()


@pytest.fixture(scope="module")
def rows():
    assert OUT.is_file(), "missing /app/output/decisions.csv"
    text = OUT.read_text()
    lines = text.splitlines()
    assert lines and lines[0] == "request_id,action,stored,age", "header must be exactly request_id,action,stored,age"
    assert all(line.strip() for line in lines[1:]), "blank lines are not allowed"
    out = []
    for r in csv.reader(lines[1:]):
        assert len(r) == 4, f"row must have 4 columns: {r}"
        out.append(r)
    return out


def _parsed(rows):
    return {r[0]: (r[1], r[2], r[3]) for r in rows}


def _ids_with(prefixes):
    return [rid for rid, tags in TAGS.items() if any(t.startswith(p) for t in tags for p in prefixes)]


def _check(truth, rows, ids):
    got = _parsed(rows)
    bad = []
    for rid in sorted(ids):
        action, stored, age = truth[rid]
        want = (action, "true" if stored else "false", str(age))
        if got.get(rid) != want:
            bad.append((rid, got.get(rid), want))
    return bad


def test_one_row_per_request_in_input_order(truth, rows):
    """Exactly one row per request, in the same order as /app/data/requests.jsonl."""
    order = [json.loads(line)["request_id"]
             for line in (engine.DATA / "requests.jsonl").read_text().splitlines()]
    assert [r[0] for r in rows] == order


def test_values_are_well_formed(rows):
    """action is HIT/REVALIDATED/MISS, stored is lowercase true/false, age a whole number >= 0."""
    for rid, action, stored, age in rows:
        assert action in ("HIT", "REVALIDATED", "MISS"), (rid, action)
        assert stored in ("true", "false"), (rid, stored)
        assert age.isdigit(), (rid, age)


@pytest.mark.parametrize("group", sorted(GROUPS))
def test_rule_group(truth, rows, group):
    """Every request exercising this RFC 9111 rule gets the right action, stored flag and Age."""
    bad = _check(truth, rows, _ids_with(GROUPS[group]))
    assert not bad, f"{len(bad)} wrong rows (id, got, expected): {bad[:8]}"


def test_actions_and_stored_flags_match(truth, rows):
    """action and stored match the conforming shared cache on every row."""
    got = _parsed(rows)
    bad = [(rid, got.get(rid, (None, None))[:2], (a, 'true' if s else 'false'))
           for rid, (a, s, _) in truth.items() if got.get(rid, (None, None))[:2] != (a, "true" if s else "false")]
    assert not bad, f"{len(bad)} wrong rows: {bad[:8]}"


def test_age_values_match(truth, rows):
    """The Age value matches on every row."""
    got = _parsed(rows)
    bad = [(rid, got.get(rid, (None, None, None))[2], str(a)) for rid, (_, _, a) in truth.items()
           if got.get(rid, (None, None, None))[2] != str(a)]
    assert not bad, f"{len(bad)} wrong ages: {bad[:8]}"
