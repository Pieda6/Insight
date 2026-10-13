"""Verifier for medicare-inpatient-claims.

Expected benefit periods, covered days, reserve days, deductibles, coinsurance and blood deductibles are
recomputed by an independent model of 42 CFR 409 (engine.py) from the verifier's private copy of the inputs;
the engine is itself checked against hand-worked planted claims (golden.json). No agent code is executed.
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
HEADER = "claim_id,benefit_period_start,covered_days,reserve_days,deductible,coinsurance,blood"
FIELDS = ("benefit_period_start", "covered_days", "reserve_days", "deductible", "coinsurance", "blood")
TAGS = json.loads((HERE / "case_tags.json").read_text())
GOLDEN = json.loads((HERE / "golden.json").read_text())
GROUPS = {
    "benefit_periods": lambda t: t in ("benefit-period", "custodial"),
    "hospital_days_and_coinsurance": lambda t: t in ("hospital-days", "deductible"),
    "lifetime_reserve_days": lambda t: t == "reserve-days",
    "amounts_by_calendar_year": lambda t: t == "year-rates",
    "history_before_the_queue": lambda t: t == "history",
    "skilled_nursing_facility": lambda t: t in ("snf", "three-day", "thirty-day", "snf-100", "observation", "cah"),
    "psychiatric_limits": lambda t: t in ("psych-190", "initial-period"),
    "entitlement": lambda t: t in ("entitlement", "initial-period"),
    "blood_deductible": lambda t: t == "blood",
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
        assert len(r) == 7, f"row must have 7 columns: {r}"
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
    """ISO dates, whole-number day counts, dollar amounts with two decimals."""
    money = re.compile(r"^\d+\.\d{2}$")
    for c, r in rows["by_id"].items():
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", r["benefit_period_start"]), (c, r)
        assert re.fullmatch(r"\d+", r["covered_days"]) and re.fullmatch(r"\d+", r["reserve_days"]), (c, r)
        assert int(r["reserve_days"]) <= int(r["covered_days"]), (c, r)
        assert all(money.match(r[f]) for f in ("deductible", "coinsurance", "blood")), (c, r)


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
