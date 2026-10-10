"""Verifier for auto-ad-clearance.

Expected figures and decisions are recomputed by an independent Regulation Z model (engine.py) from
the verifier's private copy of the inputs; the engine itself is checked against hand-worked planted
cases (golden.json). No agent code is executed.
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

OUT = Path("/app/output/ad_clearance.csv")
HEADER = "ad_id,finance_charge,amount_financed,apr,apr_accurate,missing_disclosures,cleared"
TAGS = json.loads((HERE / "case_tags.json").read_text())
GOLDEN = json.loads((HERE / "golden.json").read_text())
EXACT = ("finance_charge", "amount_financed", "apr_accurate", "missing_disclosures", "cleared")
APR_TOL = 0.01

GROUPS = {
    "finance_charge_classification": (lambda t: t.startswith("fc-"), ("finance_charge", "amount_financed")),
    "apr_computation_odd_first_period": (lambda t: t in ("apr-method", "odd-first-period"),
                                         ("apr", "apr_accurate")),
    "apr_tolerance": (lambda t: t in ("tolerance", "contract-rate-as-apr"), ("apr", "apr_accurate")),
    "triggering_terms": (lambda t: t.startswith("trigger-") or t in ("non-trigger", "zero-down"),
                         ("missing_disclosures", "cleared")),
    "required_disclosures": (lambda t: t.startswith("disclosure-"), ("missing_disclosures", "cleared")),
    "rate_statement_and_increase": (lambda t: t in ("rate-label", "rate-increase"),
                                    ("missing_disclosures", "cleared")),
    "broadcast_alternative": (lambda t: t.startswith("broadcast"), ("missing_disclosures", "cleared")),
}


@pytest.fixture(scope="module")
def truth():
    return engine.expected()


@pytest.fixture(scope="module")
def rows():
    assert OUT.is_file(), "missing /app/output/ad_clearance.csv"
    lines = OUT.read_text().splitlines()
    assert lines and lines[0] == HEADER, f"header must be exactly {HEADER}"
    assert all(line.strip() for line in lines[1:]), "blank lines are not allowed"
    out = {}
    order = []
    for r in csv.reader(lines[1:]):
        assert len(r) == 7, f"row must have 7 columns: {r}"
        out[r[0]] = dict(zip(HEADER.split(",")[1:], r[1:]))
        order.append(r[0])
    return {"by_id": out, "order": order}


def _mismatches(truth, rows, ids, fields):
    bad = []
    for aid in sorted(ids):
        got, want = rows["by_id"].get(aid), truth[aid]
        if got is None:
            bad.append((aid, "missing row"))
            continue
        for f in fields:
            if f == "apr":
                try:
                    ok = abs(float(got["apr"]) - want["apr"]) <= APR_TOL
                except ValueError:
                    ok = False
                if not ok:
                    bad.append((aid, "apr", got["apr"], round(want["apr"], 4)))
            elif got[f] != want[f]:
                bad.append((aid, f, got[f], want[f]))
    return bad


def test_engine_matches_hand_worked_cases(truth):
    """The verifier's engine reproduces every hand-worked planted case."""
    bad = [(a, f, truth[a][f], v[f]) for a, v in GOLDEN.items() for f in v if truth[a][f] != v[f]]
    assert not bad, bad[:5]


def test_one_row_per_ad_in_input_order(rows):
    """Exactly one row per ad, in the order of ads.csv."""
    with open(engine.DATA / "ads.csv", newline="") as fh:
        order = [r["ad_id"] for r in csv.DictReader(fh)]
    assert rows["order"] == order


def test_values_are_well_formed(rows):
    """Money as dollars with two decimals, APR with two decimals, flags and disclosure names as specified."""
    money = re.compile(r"^-?\d+\.\d{2}$")
    names = {"apr", "downpayment", "repayment_terms", "rate_increase"}
    for aid, r in rows["by_id"].items():
        assert money.match(r["finance_charge"]) and money.match(r["amount_financed"]), (aid, r)
        assert re.match(r"^\d+\.\d{2}$", r["apr"]), (aid, r["apr"])
        assert r["apr_accurate"] in ("true", "false", "n/a"), (aid, r["apr_accurate"])
        assert r["cleared"] in ("true", "false"), (aid, r["cleared"])
        m = r["missing_disclosures"]
        if m != "none":
            parts = m.split(";")
            assert set(parts) <= names and parts == sorted(parts) and len(parts) == len(set(parts)), (aid, m)


def test_hand_worked_cases(rows):
    """Every hand-worked planted case has the right figures and decisions."""
    bad = [(a, f, rows["by_id"].get(a, {}).get(f), v[f]) for a, v in GOLDEN.items() for f in v
           if rows["by_id"].get(a, {}).get(f) != v[f]]
    assert not bad, f"{len(bad)} wrong (ad, field, got, expected): {bad[:8]}"


@pytest.mark.parametrize("group", sorted(GROUPS))
def test_rule_family(truth, rows, group):
    """Every ad planted for this rule family has the right values for the fields the family decides."""
    pred, fields = GROUPS[group]
    ids = [a for a, tags in TAGS.items() if any(pred(t) for t in tags)]
    assert ids
    bad = _mismatches(truth, rows, ids, fields)
    assert not bad, f"{len(bad)} wrong: {bad[:8]}"


def test_every_ad(truth, rows):
    """Every row matches: money and decisions exactly, APR within 0.01 percentage point."""
    bad = _mismatches(truth, rows, truth.keys(), EXACT + ("apr",))
    assert not bad, f"{len(bad)} wrong: {bad[:8]}"
