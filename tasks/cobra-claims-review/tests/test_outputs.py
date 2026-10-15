"""Verifier for cobra-claims-review.

Whether each claim falls inside COBRA continuation coverage is recomputed by an independent model of 26 CFR
54.4980B (engine.py) from the verifier's private copy of the inputs; the engine is itself checked against
hand-worked planted claims (golden.json). No agent code is executed.
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

OUT = Path("/app/output/claim_payments.csv")
HEADER = "claim_id,plan_payment"
FIELDS = ("plan_payment",)
TAGS = json.loads((HERE / "case_tags.json").read_text())
GOLDEN = {k: {"plan_payment": v} for k, v in json.loads((HERE / "golden.json").read_text()).items()}
GROUPS = {
    "maximum_coverage_periods": lambda t: t == "maximum-period",
    "election_period": lambda t: t == "election",
    "premium_payment": lambda t: t in ("premiums", "grace", "initial-payment", "shortfall"),
    "disability_extension": lambda t: t == "disability-extension",
    "second_qualifying_events": lambda t: t == "second-event",
    "medicare": lambda t: t in ("medicare", "medicare-before"),
    "early_termination": lambda t: t == "early-termination",
    "fmla_leave": lambda t: t == "fmla-leave",
    "waiver_and_revocation": lambda t: t == "waiver",
    "incapable_child": lambda t: t == "incapable-child",
    "deductible_credit": lambda t: t == "deductible-credit",
}


@pytest.fixture(scope="module")
def truth():
    return engine.expected()


@pytest.fixture(scope="module")
def rows():
    assert OUT.is_file(), "missing /app/output/claim_payments.csv"
    lines = OUT.read_text().splitlines()
    assert lines and lines[0] == HEADER, f"header must be exactly {HEADER}"
    assert all(line.strip() for line in lines[1:]), "blank lines are not allowed"
    order, by_id = [], {}
    for r in csv.reader(lines[1:]):
        assert len(r) == 2, f"row must have 2 columns: {r}"
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


def test_inputs_are_consistent():
    """Every claim belongs to a person in a family with a qualifying event, every payment follows the election,
    every waiver comes before the election, and all Medicare and other-coverage dates fall on the first of a month."""
    people = {p["person_id"]: p for p in json.loads((engine.DATA / "people.json").read_text())}
    families = {e["family_id"] for e in json.loads((engine.DATA / "events.json").read_text())}
    elections = {e["person_id"]: e for e in json.loads((engine.DATA / "elections.json").read_text())}
    for c in json.loads((engine.DATA / "claims.json").read_text()):
        assert people[c["person_id"]]["family_id"] in families, c
    for x in json.loads((engine.DATA / "premium_payments.json").read_text()):
        assert elections[x["person_id"]]["elected_on"] <= x["sent_on"], x
    for e in elections.values():
        assert e["waived_on"] is None or e["elected_on"] is None or e["waived_on"] < e["elected_on"], e
    for p in people.values():
        for key in ("medicare_entitlement_date", "other_group_health_coverage_start"):
            assert p[key] is None or p[key].endswith("-01"), (p["person_id"], key)


def test_no_person_has_two_claims_on_one_day():
    """Claims of one person never share a date of service, so the order of the ledger is fixed."""
    seen = set()
    for c in json.loads((engine.DATA / "claims.json").read_text()):
        key = (c["person_id"], c["date_of_service"])
        assert key not in seen, key
        seen.add(key)


def test_one_row_per_claim_in_input_order(rows):
    """Exactly one row per claim, in the order of claims.json."""
    order = [c["claim_id"] for c in json.loads((engine.DATA / "claims.json").read_text())]
    assert rows["order"] == order


def test_values_are_well_formed(rows):
    """Payments in dollars with exactly two decimals."""
    for c, r in rows["by_id"].items():
        assert re.fullmatch(r"\d+\.\d{2}", r["plan_payment"]), (c, r)


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
