"""Verifier for airline-claims-desk.

Expected compensation, refunds and refund due dates are recomputed by an independent model of
14 CFR Parts 250 and 260 (engine.py) from the verifier's private copy of the inputs; the engine is
itself checked against hand-worked planted claims (golden.json). No agent code is executed.
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

OUT = Path("/app/output/claim_decisions.csv")
HEADER = "claim_id,compensation,refund,refund_due_date"
FIELDS = ("compensation", "refund", "refund_due_date")
TAGS = json.loads((HERE / "case_tags.json").read_text())
GOLDEN = json.loads((HERE / "golden.json").read_text())
GROUPS = {
    "denied_boarding_time_bands_and_caps": lambda t: t in ("db-band", "db-cap"),
    "denied_boarding_fare_base": lambda t: t == "db-fare-base",
    "denied_boarding_exceptions_and_scope": lambda t: t in ("db-exception", "db-applicability"),
    "denied_boarding_unused_fees": lambda t: t == "db-ancillary",
    "cancellations_and_significant_changes": lambda t: t.startswith("sc-"),
    "refund_due_dates": lambda t: t == "due-date",
    "covered_flights_and_break_in_journey": lambda t: t == "break-in-journey",
    "delayed_and_lost_bags": lambda t: t.startswith("bag-"),
    "ancillary_services_not_provided": lambda t: t == "ancillary",
    "local_schedule_times_and_daylight_saving": lambda t: t in ("dst", "time-zone"),
}


@pytest.fixture(scope="module")
def truth():
    return engine.expected()


@pytest.fixture(scope="module")
def rows():
    assert OUT.is_file(), "missing /app/output/claim_decisions.csv"
    lines = OUT.read_text().splitlines()
    assert lines and lines[0] == HEADER, f"header must be exactly {HEADER}"
    assert all(line.strip() for line in lines[1:]), "blank lines are not allowed"
    order, by_id = [], {}
    for r in csv.reader(lines[1:]):
        assert len(r) == 4, f"row must have 4 columns: {r}"
        order.append(r[0])
        by_id[r[0]] = dict(zip(FIELDS, r[1:]))
    return {"order": order, "by_id": by_id}


def _wrong(want, rows, ids):
    return [(c, f, rows["by_id"].get(c, {}).get(f), want[c][f]) for c in sorted(ids) for f in FIELDS
            if rows["by_id"].get(c, {}).get(f) != want[c][f]]


def test_engine_matches_hand_worked_cases(truth):
    """The verifier's engine reproduces every hand-worked planted claim."""
    bad = [(c, v, truth[c]) for c, v in GOLDEN.items() if truth[c] != v]
    assert not bad, bad[:5]


def test_one_row_per_claim_in_input_order(rows):
    """Exactly one row per claim, in the order of claims.json."""
    order = [c["claim_id"] for c in json.loads((engine.DATA / "claims.json").read_text())]
    assert rows["order"] == order


def test_values_are_well_formed(rows):
    """Dollar amounts with two decimals; due date YYYY-MM-DD only when a refund is owed, else none."""
    money = re.compile(r"^\d+\.\d{2}$")
    for c, r in rows["by_id"].items():
        assert money.match(r["compensation"]) and money.match(r["refund"]), (c, r)
        if r["refund"] == "0.00":
            assert r["refund_due_date"] == "none", (c, r)
        else:
            assert re.match(r"^\d{4}-\d{2}-\d{2}$", r["refund_due_date"]), (c, r)


def test_hand_worked_cases(rows):
    """Every hand-worked planted claim is decided correctly."""
    bad = _wrong(GOLDEN, rows, GOLDEN)
    assert not bad, f"{len(bad)} wrong (claim, field, got, expected): {bad[:8]}"


@pytest.mark.parametrize("group", sorted(GROUPS))
def test_rule_family(truth, rows, group):
    """Every claim planted for this rule family is decided correctly."""
    ids = [c for c, tags in TAGS.items() if any(GROUPS[group](t) for t in tags)]
    assert ids
    bad = _wrong(truth, rows, ids)
    assert not bad, f"{len(bad)} wrong: {bad[:8]}"


def test_every_claim(truth, rows):
    """Every row matches exactly."""
    bad = _wrong(truth, rows, truth.keys())
    assert not bad, f"{len(bad)} wrong: {bad[:8]}"
