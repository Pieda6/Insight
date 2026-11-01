"""Verifier for kdigo-aki-staging.

Every admission is recomputed by an independent engine (engine.py) from the verifier's private copy of the inputs.
The engine is checked against a hand-worked admission (golden.json). case_tags.json lists, for each admission, the
misreadings that change its row. No agent code is executed.
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

OUT = Path("/app/output/aki_staging.csv")
HEADER = "patient_id,max_stage,aki_onset,stage_reached"
GOLDEN = json.loads((HERE / "golden.json").read_text())
TAGS = json.loads((HERE / "case_tags.json").read_text())
TIME = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}")


@pytest.fixture(scope="module")
def truth():
    return engine.expected()


@pytest.fixture(scope="module")
def rows():
    assert OUT.is_file(), "missing /app/output/aki_staging.csv"
    lines = OUT.read_text().splitlines()
    assert lines and lines[0] == HEADER, f"header must be exactly {HEADER}"
    assert all(line.strip() for line in lines[1:]), "blank lines are not allowed"
    out = []
    for r in csv.reader(lines[1:]):
        assert len(r) == 4, f"row must have 4 columns: {r}"
        out.append(r)
    return out


@pytest.fixture(scope="module")
def got(rows):
    return {r[0]: r for r in rows}


def same_time(text, want):
    if want is None:
        return text == "none"
    return bool(TIME.fullmatch(text)) and math.isfinite(want) and abs(engine.to_min(text) - want) <= 1.0


def right(g, w):
    return g is not None and g[1] == str(w[0]) and same_time(g[2], w[1]) and same_time(g[3], w[2])


def _bad(truth, got, pick):
    return [(k, got.get(k), (w[0], w[1] and engine.to_text(w[1]), w[2] and engine.to_text(w[2])))
            for k, w in truth.items() if pick(k) and not right(got.get(k), w)]


def test_engine_matches_hand_worked_admission():
    """The engine reproduces a hand-worked admission (urine output periods and a umol/L creatinine rise)."""
    g = GOLDEN
    top, onset, reached = engine.evaluate(g["patient"], g["creatinine"], g["urine"], g["rrt"])
    assert top == g["expect"][0]
    assert abs(onset - engine.to_min(g["expect"][1])) < 1e-6 and abs(reached - engine.to_min(g["expect"][2])) < 1e-6


def test_inputs_are_consistent():
    """Every record belongs to a listed admission and units are known."""
    pats, creat, urine, rrt = engine.load()
    ids = {p["patient_id"] for p in pats}
    assert {r["patient_id"] for r in creat} <= ids and {r["patient_id"] for r in urine} == ids
    assert {r["patient_id"] for r in rrt} <= ids
    assert all(r["units"] in ("mg/dL", "umol/L") and r["status"] in ("final", "corrected") for r in creat)
    assert set(TAGS) == ids


def test_values_are_well_formed(rows):
    """Known admissions, stages 0 to 3, times to the minute or none."""
    ids = {p["patient_id"] for p in engine.load()[0]}
    for r in rows:
        assert r[0] in ids and r[1] in ("0", "1", "2", "3"), r
        assert all(x == "none" or TIME.fullmatch(x) for x in r[2:]), r
        assert (r[1] == "0") == (r[2] == "none") == (r[3] == "none"), r


def test_rows_are_complete_and_ordered(rows):
    """One row per admission, in the order of patients.json."""
    assert [r[0] for r in rows] == [p["patient_id"] for p in engine.load()[0]]


FAMILIES = (
    "umol_read_as_mg", "original_kept_over_correction", "rise_window_24h", "rise_measured_from_first_result",
    "creatinine_4_rule_ignored", "renal_replacement_ignored", "urine_windows_at_charting_times_only",
    "anuria_ignored", "stage1_urine_needs_12h",
)


@pytest.mark.parametrize("family", FAMILIES)
def test_rule_family(truth, got, family):
    """Every admission whose row depends on this reading is right."""
    pick = lambda k: family in TAGS[k]
    assert any(pick(k) for k in truth)
    bad = _bad(truth, got, pick)
    assert not bad, f"{len(bad)} wrong, e.g. {bad[:4]}"


def test_every_admission(truth, got):
    """Every admission: stage exact, times within 1 minute."""
    bad = _bad(truth, got, lambda k: True)
    assert not bad, f"{len(bad)} of {len(truth)} wrong, e.g. {bad[:4]}"
