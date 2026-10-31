"""Verifier for vancomycin-hemodialysis-monitoring.

Every session is recomputed by an independent engine (engine.py) from the verifier's private copy of the inputs.
The engine is checked against a hand-worked patient (golden.json). case_tags.json lists, for each session, the
protocol readings whose misreading changes that session's row. No agent code is executed.
"""
import csv
import json
import math
import re
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import engine  # noqa: E402

OUT = Path("/app/output/session_doses.csv")
HEADER = "patient_id,session_id,predialysis_level_mg_l,status,dose_mg"
GOLDEN = json.loads((HERE / "golden.json").read_text())
TAGS = json.loads((HERE / "case_tags.json").read_text())


@pytest.fixture(scope="module")
def truth():
    return engine.expected()


@pytest.fixture(scope="module")
def rows():
    assert OUT.is_file(), "missing /app/output/session_doses.csv"
    lines = OUT.read_text().splitlines()
    assert lines and lines[0] == HEADER, f"header must be exactly {HEADER}"
    assert all(line.strip() for line in lines[1:]), "blank lines are not allowed"
    out = []
    for r in csv.reader(lines[1:]):
        assert len(r) == 5, f"row must have 5 columns: {r}"
        out.append(r)
    return out


@pytest.fixture(scope="module")
def got(rows):
    out = {}
    for r in rows:
        level = None if r[2] == "" else float(r[2])
        assert level is None or math.isfinite(level), r
        out[r[1]] = (level, r[3], int(r[4]))
    return out


def right(g, w):
    if g is None or g[1:] != w[1:] or (g[0] is None) != (w[0] is None):
        return False
    return g[0] is None or abs(g[0] - w[0]) <= 0.051


def _bad(truth, got, pick):
    return [(k, got.get(k), (None if w[0] is None else round(w[0], 1), w[1], w[2]))
            for k, w in truth.items() if pick(k) and not right(got.get(k), w)]


def test_engine_matches_hand_worked_patient():
    """The engine reproduces a hand-worked five-session patient."""
    res = engine.evaluate(GOLDEN["sessions"], GOLDEN["levels"])
    for sid, (lv, st, dose) in GOLDEN["expect"].items():
        g = res[sid]
        assert g[1:] == (st, dose), (sid, g)
        assert (lv is None and g[0] is None) or abs(g[0] - lv) < 1e-3, (sid, g)


def test_inputs_are_consistent():
    """Every level belongs to a patient with sessions; dialyzers, timings and units are known."""
    sessions, levels = engine.load()
    ids = {s["patient_id"] for s in sessions}
    assert {r["patient_id"] for r in levels} <= ids
    assert all(s["dialyzer"] in ("high", "low") and s["vancomycin_timing"] in ("intradialytic", "after_dialysis")
               for s in sessions)
    assert all(r["units"] in ("mg/L", "umol/L") and r["status"] in ("final", "corrected") for r in levels)
    assert set(TAGS) == {s["session_id"] for s in sessions}


def test_values_are_well_formed(rows):
    """Known sessions, levels with one decimal or blank, status words and whole-milligram doses."""
    ids = {s["session_id"]: s["patient_id"] for s in engine.load()[0]}
    for r in rows:
        assert ids.get(r[1]) == r[0], r
        assert r[2] == "" or re.fullmatch(r"\d+\.\d", r[2]), r
        assert r[3] in ("none", "below", "within", "above") and re.fullmatch(r"\d+", r[4]), r


def test_rows_are_complete_and_ordered(truth, rows):
    """One row per session, sorted by patient_id and then session time."""
    sessions = engine.load()[0]
    order = sorted(sessions, key=lambda s: (s["patient_id"], engine.to_utc(s["start"])))
    assert [r[1] for r in rows] == [s["session_id"] for s in order]


FAMILIES = (
    "two_hours_after_dialysis_ignored", "umol_read_as_mg", "original_kept_over_correction", "range_ends_exclusive", "scaled_to_15", "scaled_to_20",
    "rounded_down", "loading_not_capped", "intradialytic_range_low_end", "weight_based_after_levels",
    "unrounded_dose_carried", "loading_dose_carried",
    "first_session_weight_throughout",
)


@pytest.mark.parametrize("family", FAMILIES)
def test_rule_family(truth, got, family):
    """Every session whose row depends on this reading is right."""
    pick = lambda k: family in TAGS[k]
    assert any(pick(k) for k in truth)
    bad = _bad(truth, got, pick)
    assert not bad, f"{len(bad)} wrong, e.g. {bad[:4]}"


def test_every_session(truth, got):
    """Every session: level within 0.05 mg/L of the unrounded value, status and dose exact."""
    bad = _bad(truth, got, lambda k: True)
    assert not bad, f"{len(bad)} of {len(truth)} wrong, e.g. {bad[:4]}"
