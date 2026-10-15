"""Verifier for ssdi-work-review.

Every beneficiary's monthly determinations are recomputed by an independent model of 20 CFR 404.315, 404.621,
404.1574, 404.1576, 404.1592 and 404.1592a (engine.py) from the verifier's private copy of the inputs; the engine
is itself checked against hand-worked planted beneficiaries (golden.json). No agent code is executed.
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

OUT = Path("/app/output/monthly_determinations.csv")
HEADER = "beneficiary_id,month,benefit_payable,trial_work_month"
TAGS = json.loads((HERE / "case_tags.json").read_text())
GOLDEN = json.loads((HERE / "golden.json").read_text())
GROUPS = {
    "waiting_period_and_retroactivity": {"waiting-period", "retroactivity"},
    "trial_work_period": {"trial-work", "filing-month"},
    "rolling_sixty_month_window": {"rolling-window"},
    "countable_earnings": {"countable-earnings", "irwe", "subsidy", "blind"},
    "cessation_and_grace": {"cessation", "grace"},
    "extended_period_and_termination": {"extended-period", "termination"},
    "boundaries": {"boundary"},
}


@pytest.fixture(scope="module")
def truth():
    return engine.expected()


@pytest.fixture(scope="module")
def rows():
    assert OUT.is_file(), "missing /app/output/monthly_determinations.csv"
    lines = OUT.read_text().splitlines()
    assert lines and lines[0] == HEADER, f"header must be exactly {HEADER}"
    assert all(line.strip() for line in lines[1:]), "blank lines are not allowed"
    out = list(csv.reader(lines[1:]))
    assert all(len(r) == 4 for r in out), "every row must have 4 columns"
    return out


def by_ben(rs, ids):
    return [r for r in rs if r[0] in ids]


def test_engine_matches_hand_worked_beneficiaries(truth):
    """The verifier's engine reproduces every hand-worked planted beneficiary."""
    bad = [b for b, v in GOLDEN.items() if [r[1:] for r in by_ben(truth, {b})] != v]
    assert not bad, bad


def test_values_are_well_formed(rows):
    """Known beneficiaries, YYYY-MM months, yes/no values, sorted by beneficiary then month, no duplicates."""
    ids = {b["beneficiary_id"] for b in json.loads((engine.DATA / "beneficiaries.json").read_text())}
    for r in rows:
        assert r[0] in ids, r
        assert re.fullmatch(r"\d{4}-\d{2}", r[1]), r
        assert r[2] in ("yes", "no") and r[3] in ("yes", "no"), r
    assert [r[:2] for r in rows] == sorted(r[:2] for r in rows), "rows must be sorted by beneficiary_id then month"
    assert len({tuple(r[:2]) for r in rows}) == len(rows), "duplicate rows"


def test_months_listed(truth, rows):
    """Exactly the months from each beneficiary's first month of entitlement through December 2025."""
    assert [r[:2] for r in rows] == [r[:2] for r in truth]


def test_hand_worked_beneficiaries(rows):
    """Every hand-worked planted beneficiary is decided correctly month by month."""
    bad = [b for b, v in GOLDEN.items() if [r[1:] for r in by_ben(rows, {b})] != v]
    assert not bad, f"{len(bad)} beneficiaries wrong: {bad[:6]}"


@pytest.mark.parametrize("group", sorted(GROUPS))
def test_rule_family(truth, rows, group):
    """Every planted beneficiary for this rule family is decided correctly."""
    ids = {b for b, tags in TAGS.items() if set(tags) & GROUPS[group]}
    assert ids
    got, want = by_ben(rows, ids), by_ben(truth, ids)
    bad = [w for w in want if w not in got]
    assert got == want, f"{len(bad)} rows wrong or missing, e.g. {bad[:6]}"


def test_every_month(truth, rows):
    """Every row matches exactly."""
    bad = [w for w in truth if w not in rows]
    assert rows == truth, f"{len(bad)} rows wrong or missing, e.g. {bad[:8]}"
