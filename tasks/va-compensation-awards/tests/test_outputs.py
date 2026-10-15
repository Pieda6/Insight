"""Verifier for va-compensation-awards.

The combined rating and the payment for every veteran and month are recomputed by an independent model of 38 CFR
Parts 3 and 4 (engine.py) from the verifier's private copy of the inputs; the engine is itself checked against the
planted veterans worked by hand (golden.json). No agent code is executed.
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

OUT = Path("/app/output/monthly_payments.csv")
HEADER = "veteran_id,month,combined_rating,payment"
FIELDS = ("combined_rating", "payment")
TAGS = json.loads((HERE / "case_tags.json").read_text())
GOLDEN = json.loads((HERE / "golden.json").read_text())
GROUPS = {
    "effective_dates_and_payment_start": lambda t: t in ("original-claim", "increase", "payment-start"),
    "combined_ratings_and_bilateral_factor": lambda t: t in ("combined-ratings", "bilateral"),
    "dependents": lambda t: t == "dependents",
    "separation_pay": lambda t: t == "separation-pay",
}


@pytest.fixture(scope="module")
def truth():
    return engine.expected()


@pytest.fixture(scope="module")
def rows():
    assert OUT.is_file(), "missing /app/output/monthly_payments.csv"
    lines = OUT.read_text().splitlines()
    assert lines and lines[0] == HEADER, f"header must be exactly {HEADER}"
    assert all(line.strip() for line in lines[1:]), "blank lines are not allowed"
    order, by_key = [], {}
    for r in csv.reader(lines[1:]):
        assert len(r) == 4, f"row must have 4 columns: {r}"
        key = f"{r[0]},{r[1]}"
        order.append(key)
        by_key[key] = dict(zip(FIELDS, r[2:]))
    return {"order": order, "by_key": by_key}


def _wrong(want, rows, keys):
    return [(k, f, rows["by_key"].get(k, {}).get(f), want[k][f]) for k in sorted(keys) for f in FIELDS
            if rows["by_key"].get(k, {}).get(f) != want[k][f]]


def test_engine_matches_hand_worked_cases(truth):
    """The verifier's engine reproduces every planted veteran worked by hand."""
    bad = [(k, v, truth[k]) for k, v in GOLDEN.items() if truth[k] != v]
    assert not bad, bad[:5]


def test_inputs_are_consistent():
    """Every decision belongs to a known disability and veteran, and the rate tables start before any payment."""
    vets = {v["veteran_id"] for v in json.loads((engine.DATA / "veterans.json").read_text())}
    dis = {d["disability_id"]: d["veteran_id"] for d in json.loads((engine.DATA / "disabilities.json").read_text())}
    assert set(dis.values()) <= vets
    for r in json.loads((engine.DATA / "rating_decisions.json").read_text()):
        assert r["disability_id"] in dis, r
    first = min(t["effective_date"] for t in json.loads((engine.DATA / "compensation_rates.json").read_text()))
    assert first <= min(v["last_day_of_active_service"] for v in json.loads((engine.DATA / "veterans.json").read_text()))


def test_one_row_per_veteran_and_month_in_order(rows):
    """One row per veteran (in the order of veterans.json) and month (January 2023 to September 2026)."""
    months = [f"{y:04d}-{m:02d}" for y in range(2023, 2027) for m in range(1, 13) if (y, m) <= (2026, 9)]
    order = [f"{v['veteran_id']},{m}" for v in json.loads((engine.DATA / "veterans.json").read_text()) for m in months]
    assert rows["order"] == order


def test_values_are_well_formed(rows):
    """Ratings are multiples of 10 from 0 to 100; payments are dollars with exactly two decimals."""
    for k, r in rows["by_key"].items():
        assert re.fullmatch(r"(0|[1-9]0|100)", r["combined_rating"]), (k, r)
        assert re.fullmatch(r"\d+\.\d{2}", r["payment"]), (k, r)


def test_hand_worked_cases(rows):
    """Every month of every planted veteran is correct."""
    bad = _wrong(GOLDEN, rows, GOLDEN)
    assert not bad, f"{len(bad)} wrong (row, field, got, expected): {bad[:8]}"


@pytest.mark.parametrize("group", sorted(GROUPS))
def test_rule_family(truth, rows, group):
    """Every month of the planted veterans for this rule family is correct."""
    keys = [k for k, tags in TAGS.items() if any(GROUPS[group](t) for t in tags)]
    assert keys
    bad = _wrong(truth, rows, keys)
    assert not bad, f"{len(bad)} wrong: {bad[:8]}"


def test_every_row(truth, rows):
    """Every row matches exactly."""
    bad = _wrong(truth, rows, truth.keys())
    assert not bad, f"{len(bad)} wrong: {bad[:8]}"
