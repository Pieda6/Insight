"""Verifier for stormwater-inspection-audit.

Every requirement of the 2022 Construction General Permit that the audit covers is recomputed by an independent
model (engine.py) from the verifier's private copy of the inputs; the engine is itself checked against the planted
sites worked by hand (golden.json). No agent code is executed.
"""
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import engine  # noqa: E402

OUT = Path("/app/output/violations.csv")
HEADER = "site_id,area_id,requirement,due,met"
KINDS = {"routine_inspection", "storm_inspection", "inspection_report", "routine_maintenance", "corrective_action",
         "ca_log_identified", "ca_log_completed", "swppp_update", "trackout_removal", "stabilization_initiation",
         "stabilization_completion"}
STAMP = r"2026-\d{2}-\d{2}T\d{2}:\d{2}"
TAGS = json.loads((HERE / "case_tags.json").read_text())
GOLDEN = json.loads((HERE / "golden.json").read_text())
GROUPS = {
    "business_days": {"business-day"},
    "routine_and_reduced_frequency_inspections": {"routine-inspection", "stabilized-area"},
    "storm_inspections_and_sensitive_waters": {"storm", "sensitive-water"},
    "reports_and_trackout": {"report", "trackout"},
    "maintenance_and_corrective_actions": {"maintenance", "corrective-action", "repeat-fix"},
    "stabilization_and_disturbed_acreage": {"stabilization", "acreage"},
}


def sort_key(r):
    return (r[0], r[1], r[3], r[2], r[4])


@pytest.fixture(scope="module")
def truth():
    return [tuple(r) for r in engine.expected()]


@pytest.fixture(scope="module")
def rows():
    assert OUT.is_file(), "missing /app/output/violations.csv"
    lines = OUT.read_text().splitlines()
    assert lines and lines[0] == HEADER, f"header must be exactly {HEADER}"
    assert all(line.strip() for line in lines[1:]), "blank lines are not allowed"
    out = []
    for r in csv.reader(lines[1:]):
        assert len(r) == 5, f"row must have 5 columns: {r}"
        out.append(tuple(r))
    return out


def _diff(want, got):
    w, g = Counter(want), Counter(got)
    return sorted((w - g).elements())[:6], sorted((g - w).elements())[:6]


def _site_rows(rows, sites):
    return [r for r in rows if r[0] in sites]


def test_engine_matches_hand_worked_sites(truth):
    """The verifier's engine reproduces every planted site worked by hand."""
    for sid, want in GOLDEN.items():
        got = sorted(_site_rows(truth, {sid}))
        assert got == sorted(tuple(r) for r in want), (sid, _diff([tuple(r) for r in want], got))


def test_inputs_are_consistent():
    """Every record names a known site and area, and inspections fall on logged days within working hours."""
    sites = {s["site_id"]: s for s in json.loads((engine.DATA / "sites.json").read_text())}
    areas = {a["area_id"]: s["site_id"] for s in sites.values() for a in s["areas"]}
    logged = {(e["site_id"], e["date"]) for e in json.loads((engine.DATA / "construction_log.json").read_text())}
    for name in ("construction_log", "stabilization_records", "findings", "trackout"):
        for r in json.loads((engine.DATA / f"{name}.json").read_text()):
            assert areas.get(r["area_id"]) == r["site_id"], (name, r)
    for i in json.loads((engine.DATA / "inspections.json").read_text()):
        assert all(areas.get(a) == i["site_id"] for a in i["areas_inspected"]), i
        assert (i["site_id"], i["completed"][:10]) in logged, i
        hours = sites[i["site_id"]]["normal_working_hours"]
        assert hours["start"] <= i["completed"][11:] <= hours["end"], i


def test_values_are_well_formed(rows):
    """Known requirement names, timestamps in the stated form, met as a timestamp or none."""
    for r in rows:
        assert re.fullmatch(r"S\d{2}", r[0]) and r[1].startswith(r[0] + "-A"), r
        assert r[2] in KINDS, r
        assert re.fullmatch(STAMP, r[3]), r
        assert r[4] == "none" or re.fullmatch(STAMP, r[4]), r


def test_rows_are_sorted(rows):
    """Rows sorted by site_id, area_id, due, requirement and met."""
    assert rows == sorted(rows, key=sort_key)


def test_hand_worked_sites(rows):
    """Every planted site worked by hand is exactly right."""
    for sid, want in GOLDEN.items():
        got = sorted(_site_rows(rows, {sid}))
        missing, extra = _diff([tuple(r) for r in want], got)
        assert not missing and not extra, f"{sid}: missing {missing}, extra {extra}"


@pytest.mark.parametrize("group", sorted(GROUPS))
def test_rule_family(truth, rows, group):
    """Every planted site for this rule family is exactly right."""
    sites = {s for s, tags in TAGS.items() if set(tags) & GROUPS[group]}
    assert sites
    missing, extra = _diff(_site_rows(truth, sites), _site_rows(rows, sites))
    assert not missing and not extra, f"missing {missing}, extra {extra}"


def test_every_row(truth, rows):
    """The whole file matches exactly."""
    missing, extra = _diff(truth, rows)
    assert not missing and not extra, f"{len(Counter(truth) - Counter(rows))} missing, " \
                                      f"{len(Counter(rows) - Counter(truth))} extra; e.g. missing {missing}, extra {extra}"
    assert rows == truth
