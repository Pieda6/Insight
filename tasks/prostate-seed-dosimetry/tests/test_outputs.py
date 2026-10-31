"""Verifier for prostate-seed-dosimetry.

Every point dose is recomputed by an independent engine (engine.py) from the verifier's private copy of the inputs.
The engine is checked against the report's own Table XV and hand-worked single-seed cases (golden.json).
case_tags.json lists, for each point, the rule families whose misreading moves its dose by more than 0.15 percent.
No agent code is executed.
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

OUT = Path("/app/output/point_doses.csv")
HEADER = "patient_id,point_id,dose_gy"
REL = 0.001
ABS = 0.0005
GOLDEN = json.loads((HERE / "golden.json").read_text())
TAGS = json.loads((HERE / "case_tags.json").read_text())


def close(got, want):
    assert math.isfinite(got) and math.isfinite(want), (got, want)
    return abs(got - want) <= max(REL * abs(want), ABS)


@pytest.fixture(scope="module")
def truth():
    return engine.expected()


@pytest.fixture(scope="module")
def rows():
    assert OUT.is_file(), "missing /app/output/point_doses.csv"
    lines = OUT.read_text().splitlines()
    assert lines and lines[0] == HEADER, f"header must be exactly {HEADER}"
    assert all(line.strip() for line in lines[1:]), "blank lines are not allowed"
    out = []
    for r in csv.reader(lines[1:]):
        assert len(r) == 3, f"row must have 3 columns: {r}"
        out.append(r)
    return out


@pytest.fixture(scope="module")
def got(rows):
    out = {(r[0], r[1]): float(r[2]) for r in rows}
    for key, v in out.items():
        assert math.isfinite(v), f"{key}: non-finite dose {v}"
    return out


def _bad(truth, got, pick):
    return [(k, got.get(k), round(w, 4)) for k, w in truth.items()
            if pick(k) and (got.get(k) is None or not close(got[k], w))]


def test_engine_matches_report_and_hand_worked_cases():
    """The engine reproduces the report's Table XV dose rates and hand-worked single-seed 2D dose rates."""
    src = engine.load()[0]
    for ex in GOLDEN["examples"]:
        d = src[ex["model"]]
        v = engine.rate_1d(d, ex["r"]) if ex["check"] == "rate_1d" else engine.rate_per_unit(d, ex["r"], ex["theta"])
        assert math.isfinite(v) and abs(v - ex["expect"]) <= ex["rel_tol"] * ex["expect"], (ex["source"], v)


def test_inputs_are_consistent():
    """Every point's patient has accepted seeds, every seed's batch exists, every unit is known."""
    src, patients, batches, seeds, points = engine.load()
    ids = {p["patient_id"] for p in patients}
    bt = {b["batch_id"]: b for b in batches}
    assert {p["patient_id"] for p in points} == ids
    assert {s["patient_id"] for s in seeds if s["review"] == "accepted"} == ids
    assert all(s["batch_id"] in bt for s in seeds)
    assert all(b["seed_model"] in src and b["strength_unit"] in ("U_per_seed", "U_total", "mCi_apparent")
               for b in batches)
    assert set(TAGS) == {f"{p['patient_id']}/{p['point_id']}" for p in points}


def test_values_are_well_formed(rows):
    """Known points and doses in Gy with four decimals."""
    keys = {(p["patient_id"], p["point_id"]) for p in engine.load()[4]}
    for r in rows:
        assert (r[0], r[1]) in keys, r
        assert re.fullmatch(r"\d+\.\d{4}", r[2]), r


def test_rows_are_sorted_and_complete(truth, rows):
    """One row per point, sorted by patient_id then point_id."""
    assert [(r[0], r[1]) for r in rows] == sorted(truth)


FAMILIES = (
    "linear_g_interpolation", "point_source_radial_dose_function", "point_source_geometry",
    "anisotropy_held_beyond_last_angle", "anisotropy_extrapolated_in_r", "radial_dose_extrapolated",
    "one_dimensional_anisotropy_factor",
    "no_mirror_beyond_90", "capsule_length_for_L", "mean_life_144", "apparent_activity_unconverted",
    "apparent_activity_fixed_coefficient", "batch_total_as_per_seed", "no_decay_to_implant",
    "calibration_offset_ignored", "implant_time_without_daylight_saving", "duplicates_kept", "first_marker_as_centre",
)


@pytest.mark.parametrize("family", FAMILIES)
def test_rule_family(truth, got, family):
    """Every point whose dose depends on this rule is right."""
    pick = lambda k: family in TAGS[f"{k[0]}/{k[1]}"]
    assert any(pick(k) for k in truth)
    bad = _bad(truth, got, pick)
    assert not bad, f"{len(bad)} wrong, e.g. {bad[:4]}"


def test_every_point(truth, got):
    """Every point dose within 0.1 percent (or 0.0005 Gy for the smallest doses)."""
    bad = _bad(truth, got, lambda k: True)
    assert not bad, f"{len(bad)} of {len(truth)} wrong, e.g. {bad[:4]}"
