"""Verifier for fmla-absence-claims.

FMLA hours for every absence are recomputed by an independent model of 29 CFR Part 825 (engine.py) from the
verifier's private copy of the inputs; the engine is itself checked against hand-worked planted absences
(golden.json). No agent code is executed.
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

OUT = Path("/app/output/fmla_hours.csv")
HEADER = "absence_id,fmla_hours"
FIELDS = ("fmla_hours",)
TAGS = json.loads((HERE / "case_tags.json").read_text())
GOLDEN = {k: {"fmla_hours": v} for k, v in json.loads((HERE / "golden.json").read_text()).items()}
GROUPS = {
    "twelve_month_methods": lambda t: t in ("calendar-year", "rolling", "forward", "fixed-year"),
    "exhaustion": lambda t: t == "exhaustion",
    "holidays_full_weeks_and_closures": lambda t: t in ("holiday", "full-week", "closure"),
    "eligibility": lambda t: t == "eligibility",
    "bonding_window": lambda t: t == "bonding",
    "military_caregiver": lambda t: t == "caregiver",
}


@pytest.fixture(scope="module")
def truth():
    return engine.expected()


@pytest.fixture(scope="module")
def rows():
    assert OUT.is_file(), "missing /app/output/fmla_hours.csv"
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


def test_one_row_per_claim_in_input_order(rows):
    """Exactly one row per absence, in the order of absences.json."""
    order = [a["absence_id"] for a in json.loads((engine.DATA / "absences.json").read_text())]
    assert rows["order"] == order


def test_values_are_well_formed(rows):
    """Hours with exactly two decimals."""
    for c, r in rows["by_id"].items():
        assert re.fullmatch(r"\d+\.\d{2}", r["fmla_hours"]), (c, r)


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
