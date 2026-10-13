"""Verifier for TASK-NAME.

Pattern for a task whose output has one row per input record, keyed by an id column. Replace the
CAPITALISED names. Expected values come from engine.py (an independent model of the rule) run on
the verifier's private copy of the inputs; engine.py is itself checked against hand-worked planted
records (golden.json). No agent code runs.
"""
import csv
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import engine  # noqa: E402

OUT = Path("/app/output/OUTPUT_FILE.csv")
HEADER = "record_id,FIELD_ONE,FIELD_TWO"
FIELDS = HEADER.split(",")[1:]
TAGS = json.loads((HERE / "case_tags.json").read_text())        # {"R0001": ["family-a", "boundary"], ...}
GOLDEN = json.loads((HERE / "golden.json").read_text())         # {"R0001": {"FIELD_ONE": "...", ...}, ...}
GROUPS = {                                                      # test name -> tags that select records
    "family_a_rule": {"family-a"},
    "family_b_exception": {"family-b"},
}


@pytest.fixture(scope="module")
def truth():
    return engine.expected()                                    # {"R0001": {"FIELD_ONE": "...", ...}, ...}


@pytest.fixture(scope="module")
def rows():
    assert OUT.is_file(), f"missing {OUT}"
    lines = OUT.read_text().splitlines()
    assert lines and lines[0] == HEADER, f"header must be exactly {HEADER}"
    assert all(line.strip() for line in lines[1:]), "blank lines are not allowed"
    out = {}
    order = []
    for r in csv.reader(lines[1:]):
        assert len(r) == len(FIELDS) + 1, f"row must have {len(FIELDS) + 1} columns: {r}"
        order.append(r[0])
        out[r[0]] = dict(zip(FIELDS, r[1:]))
    return {"order": order, "by_id": out}


def wrong(expected, rows, ids):
    return [(i, f, rows["by_id"].get(i, {}).get(f), expected[i][f]) for i in sorted(ids) for f in FIELDS
            if rows["by_id"].get(i, {}).get(f) != expected[i][f]]


def test_engine_matches_hand_worked_cases(truth):
    """The verifier's engine reproduces every hand-worked planted record."""
    bad = [(i, v, truth[i]) for i, v in GOLDEN.items() if truth[i] != v]
    assert not bad, bad[:5]


def test_one_row_per_record_in_input_order(rows):
    """Exactly one row per input record, in input order."""
    order = [r["record_id"] for r in json.loads((engine.DATA / "INPUT_FILE.json").read_text())]
    assert rows["order"] == order


def test_values_are_well_formed(rows):
    """Value formats (adapt: regexes, vocabularies, sorting inside a cell)."""
    for i, r in rows["by_id"].items():
        assert r["FIELD_ONE"] != "", i


def test_hand_worked_cases(rows):
    """Every hand-worked planted record is right."""
    bad = wrong(GOLDEN, rows, GOLDEN)
    assert not bad, f"{len(bad)} wrong (id, field, got, expected): {bad[:8]}"


@pytest.mark.parametrize("group", sorted(GROUPS))
def test_rule_family(truth, rows, group):
    """Every record planted for this rule family is right."""
    ids = [i for i, tg in TAGS.items() if set(tg) & GROUPS[group]]
    assert ids
    bad = wrong(truth, rows, ids)
    assert not bad, f"{len(bad)} wrong: {bad[:8]}"


def test_every_record(truth, rows):
    """Every row matches exactly."""
    bad = wrong(truth, rows, truth.keys())
    assert not bad, f"{len(bad)} wrong: {bad[:8]}"
