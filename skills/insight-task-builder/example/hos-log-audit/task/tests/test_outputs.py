"""Verifier for hos-log-audit.

Expected violations are recomputed by an independent model of 49 CFR 395.1-395.3 (engine.py) from the
verifier's private copy of the inputs; the engine is itself checked against hand-worked planted drivers
(golden.json). No agent code runs.
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

OUT = Path("/app/output/violations.csv")
HEADER = "driver_id,violation_start,rule"
RULES = {"11_HOUR_DRIVING", "14_HOUR_WINDOW", "30_MINUTE_BREAK", "60_70_HOUR"}
TAGS = json.loads((HERE / "case_tags.json").read_text())
GOLDEN = json.loads((HERE / "golden.json").read_text())
GROUPS = {
    "eleven_hour_driving": {"driving-11"},
    "fourteen_hour_window": {"window-14"},
    "thirty_minute_break": {"break-30"},
    "short_haul_exception": {"short-haul"},
    "adverse_driving_conditions": {"adverse"},
    "sleeper_berth_periods_and_resets": {"sleeper-split", "reset-10"},
    "sixty_and_seventy_hour_limits": {"cycle-70", "cycle-60", "carrier-day"},
    "restarts_and_travel_time": {"restart", "travel-time"},
    "sixteen_hour_exception": {"sixteen-hour"},
}


@pytest.fixture(scope="module")
def truth():
    return engine.expected()


@pytest.fixture(scope="module")
def rows():
    assert OUT.is_file(), "missing /app/output/violations.csv"
    lines = OUT.read_text().splitlines()
    assert lines and lines[0] == HEADER, f"header must be exactly {HEADER}"
    assert all(line.strip() for line in lines[1:]), "blank lines are not allowed"
    out = [r for r in csv.reader(lines[1:])]
    assert all(len(r) == 3 for r in out), "every row must have 3 columns"
    return out


def by_driver(rows, ids):
    return sorted(r for r in rows if r[0] in ids)


def test_engine_matches_hand_worked_drivers(truth):
    """The verifier's engine reproduces every hand-worked planted driver."""
    bad = [d for d, v in GOLDEN.items() if by_driver(truth, {d}) != v]
    assert not bad, bad[:5]


def test_values_are_well_formed(rows):
    """Known drivers and rules, UTC minutes, no duplicates, sorted by driver, time and rule."""
    drivers = {d["driver_id"] for d in json.loads((engine.DATA / "drivers.json").read_text())}
    for r in rows:
        assert r[0] in drivers, r
        assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\dZ", r[1]), r
        assert r[2] in RULES, r
    assert rows == sorted(rows), "rows must be sorted by driver_id, then violation_start, then rule"
    assert len({tuple(r) for r in rows}) == len(rows), "duplicate rows"


def test_hand_worked_drivers(rows):
    """Every hand-worked planted driver has exactly the expected violations."""
    bad = [(d, by_driver(rows, {d}), v) for d, v in GOLDEN.items() if by_driver(rows, {d}) != v]
    assert not bad, f"{len(bad)} drivers wrong (driver, got, expected): {bad[:4]}"


@pytest.mark.parametrize("group", sorted(GROUPS))
def test_rule_family(truth, rows, group):
    """Every driver planted for this rule family has exactly the expected violations."""
    ids = {d for d, tg in TAGS.items() if set(tg) & GROUPS[group]}
    assert ids
    got, want = by_driver(rows, ids), by_driver(truth, ids)
    assert got == want, f"missing {sorted(set(map(tuple, want)) - set(map(tuple, got)))[:6]}, " \
                        f"extra {sorted(set(map(tuple, got)) - set(map(tuple, want)))[:6]}"


def test_every_violation(truth, rows):
    """The file lists exactly the violations in the records, no more and no fewer."""
    got, want = set(map(tuple, rows)), set(map(tuple, truth))
    assert got == want, f"missing {sorted(want - got)[:6]}, extra {sorted(got - want)[:6]}"
