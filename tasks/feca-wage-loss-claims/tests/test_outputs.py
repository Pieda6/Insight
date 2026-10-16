"""Verifier for feca-wage-loss-claims.

Continuation of pay and wage-loss compensation for every claim are recomputed by an independent model of the FECA and
20 CFR Part 10 (engine.py) from the verifier's private copy of the inputs; the engine is itself checked against the
planted claims worked by hand (golden.json). No agent code is executed.
"""
import csv
import json
import re
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import engine  # noqa: E402

OUT = Path("/app/output/claim_determinations.csv")
HEADER = "claim_id,cop_days,last_cop_day,compensation_days,compensation"
FIELDS = ("cop_days", "last_cop_day", "compensation_days", "compensation")
TAGS = json.loads((HERE / "case_tags.json").read_text())
GOLDEN = json.loads((HERE / "golden.json").read_text())
GROUPS = {
    "continuation_of_pay_days": {"cop-days", "injury-day", "days-off", "partial-days", "part-time"},
    "forty_five_day_limit_and_leave": {"cop-cap", "leave-counted"},
    "eligibility_and_time_limits": {"eligibility", "boundary"},
    "returns_to_work": {"recurrence"},
    "waiting_period": {"waiting-period"},
    "pay_rate_dependents_and_cola": {"pay-rate", "dependents", "cola", "compensation"},
}


@pytest.fixture(scope="module")
def truth():
    return engine.expected()


@pytest.fixture(scope="module")
def rows():
    assert OUT.is_file(), "missing /app/output/claim_determinations.csv"
    lines = OUT.read_text().splitlines()
    assert lines and lines[0] == HEADER, f"header must be exactly {HEADER}"
    assert all(line.strip() for line in lines[1:]), "blank lines are not allowed"
    order, by_id = [], {}
    for r in csv.reader(lines[1:]):
        assert len(r) == 5, f"row must have 5 columns: {r}"
        order.append(r[0])
        by_id[r[0]] = dict(zip(FIELDS, r[1:]))
    return {"order": order, "by_id": by_id}


def _wrong(want, rows, ids):
    return [(c, f, rows["by_id"].get(c, {}).get(f), want[c][f]) for c in sorted(ids) for f in FIELDS
            if rows["by_id"].get(c, {}).get(f) != want[c][f]]


def test_engine_matches_hand_worked_claims(truth):
    """The verifier's engine reproduces every claim worked by hand."""
    bad = [(c, v, truth[c]) for c, v in GOLDEN.items() if truth[c] != v]
    assert not bad, bad[:5]


def test_inputs_are_consistent():
    """Every claim has an employee, absence records do not overlap, and every absence follows the injury."""
    emps = {e["employee_id"] for e in json.loads((engine.DATA / "employees.json").read_text())}
    claims = {c["claim_id"]: c for c in json.loads((engine.DATA / "claims.json").read_text())}
    assert all(c["employee_id"] in emps for c in claims.values())
    by_claim = {}
    for r in json.loads((engine.DATA / "time_and_attendance.json").read_text()):
        by_claim.setdefault(r["claim_id"], []).append((r["from"], r["to"]))
        assert r["from"] >= claims[r["claim_id"]]["injury_date_time"][:10], r
    for spans in by_claim.values():
        spans.sort()
        assert all(a[1] < b[0] for a, b in zip(spans, spans[1:])), spans


def test_one_row_per_claim_in_input_order(rows):
    """Exactly one row per claim, in the order of claims.json."""
    assert rows["order"] == [c["claim_id"] for c in json.loads((engine.DATA / "claims.json").read_text())]


def test_values_are_well_formed(rows):
    """Whole-number day counts, a date or none, and dollars with two decimals."""
    for c, r in rows["by_id"].items():
        assert re.fullmatch(r"\d+", r["cop_days"]) and int(r["cop_days"]) <= 45, (c, r)
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}|none", r["last_cop_day"]), (c, r)
        assert re.fullmatch(r"\d+", r["compensation_days"]), (c, r)
        assert re.fullmatch(r"\d+\.\d{2}", r["compensation"]), (c, r)


def test_hand_worked_claims(rows):
    """Every claim worked by hand is correct."""
    bad = _wrong(GOLDEN, rows, GOLDEN)
    assert not bad, f"{len(bad)} wrong (claim, field, got, expected): {bad[:8]}"


@pytest.mark.parametrize("group", sorted(GROUPS))
def test_rule_family(truth, rows, group):
    """Every planted claim for this rule family is correct."""
    ids = [c for c, tags in TAGS.items() if set(tags) & GROUPS[group]]
    assert ids
    bad = _wrong(truth, rows, ids)
    assert not bad, f"{len(bad)} wrong: {bad[:8]}"


def test_every_claim(truth, rows):
    """Every row matches exactly."""
    bad = _wrong(truth, rows, truth.keys())
    assert not bad, f"{len(bad)} wrong: {bad[:8]}"
