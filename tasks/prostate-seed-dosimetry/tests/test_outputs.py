"""Verifier for prostate-seed-dosimetry.

Every patient's indices are recomputed by an independent engine (engine.py) from the verifier's private copy of the
inputs. The engine is checked against the report's own Table XV, hand-worked single-seed cases and closed-form
time integrals (golden.json). case_tags.json lists, per patient and column, the misreadings that move the value past
the tolerance. No agent code is executed.
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

OUT = Path("/app/output/implant_evaluation.csv")
HEADER = ("patient_id,d90_gy,v100_pct,v150_pct,ud10_gy,ud30_gy,rv100_cc,rd2cc_gy,"
          "d90_meets,v100_meets,ud10_meets,rv100_meets")
COLS = HEADER.split(",")[1:]
REL_GY = 0.001          # relative, dose columns
ABS_PCT = 0.30          # percentage points, v100_pct and v150_pct
ABS_CC = 0.030          # cc, rv100_cc
GOLDEN = json.loads((HERE / "golden.json").read_text())
TAGS = json.loads((HERE / "case_tags.json").read_text())
PATTERN = {"gy": r"\d+\.\d{3}", "pct": r"\d{1,3}\.\d{2}", "cc": r"\d+\.\d{3}", "cat": r"yes|no"}


def kind(col):
    return "gy" if col.endswith("_gy") else "pct" if col.endswith("_pct") else "cc" if col.endswith("_cc") else "cat"


def value_ok(col, got, want):
    if got is None:
        return False
    k = kind(col)
    if k == "cat":
        return got == want
    assert math.isfinite(got) and math.isfinite(want), (col, got, want)
    if k == "gy":
        return abs(got - want) <= REL_GY * abs(want)
    return abs(got - want) <= (ABS_PCT if k == "pct" else ABS_CC)


@pytest.fixture(scope="module")
def truth():
    return engine.expected()


@pytest.fixture(scope="module")
def rows():
    assert OUT.is_file(), "missing /app/output/implant_evaluation.csv"
    lines = OUT.read_text().splitlines()
    assert lines and lines[0] == HEADER, f"header must be exactly {HEADER}"
    assert all(line.strip() for line in lines[1:]), "blank lines are not allowed"
    out = []
    for r in csv.reader(lines[1:]):
        assert len(r) == len(COLS) + 1, f"row must have {len(COLS) + 1} columns: {r}"
        out.append(r)
    return out


@pytest.fixture(scope="module")
def got(rows):
    out = {}
    for r in rows:
        vals = {}
        for col, text in zip(COLS, r[1:]):
            if kind(col) == "cat":
                vals[col] = text
            else:
                vals[col] = float(text)
                assert math.isfinite(vals[col]), (r[0], col, text)
        out[r[0]] = vals
    return out


def _bad(truth, got, pick):
    bad = []
    for pid, want in truth.items():
        g = got.get(pid)
        for col in COLS:
            if pick(pid, col) and not value_ok(col, None if g is None else g.get(col), want[col]):
                bad.append((pid, col, None if g is None else g.get(col), want[col]))
    return bad


def test_engine_matches_report_and_closed_forms():
    """Table XV dose rates, hand-worked 2D cases, and the closed-form dynamic point-source integrals."""
    src = engine.load()[0]
    for ex in GOLDEN["examples"]:
        if ex["check"] == "rate_1d":
            v = engine.rate_1d(src[ex["model"]], ex["r"])
        elif ex["check"] == "rate_per_unit":
            v = engine.rate_per_unit(src[ex["model"]], ex["r"], ex["theta"])
        elif ex["check"] == "dynamic_point_source":
            v = engine.dynamic_point_source(*ex["args"])
            ex = dict(ex, expect=engine.dynamic_point_source_closed_form(*ex["args"]))
        elif ex["check"] == "dynamic_total_tiny_edema":
            v = engine.dynamic_total_tiny_edema(src[ex["model"]], ex["r"], ex["theta"])
            ex = dict(ex, expect=engine.static_total(src[ex["model"]], ex["r"], ex["theta"]))
        else:
            raise ValueError(ex["check"])
        assert math.isfinite(v) and math.isfinite(ex["expect"])
        assert abs(v - ex["expect"]) <= ex["rel_tol"] * abs(ex["expect"]), (ex["source"], v, ex["expect"])


def test_inputs_are_consistent():
    """Ids, references, units, volume order, structure sizes and tag coverage of the private inputs."""
    src, patients, batches, seeds, contours = engine.load()
    ids = {p["patient_id"] for p in patients}
    bt = {b["batch_id"]: b for b in batches}
    assert len(ids) == len(patients) and set(contours) == ids
    assert {s["patient_id"] for s in seeds if s["review"] == "accepted"} == ids
    assert all(s["batch_id"] in bt and bt[s["batch_id"]]["patient_id"] == s["patient_id"] for s in seeds)
    assert all(b["seed_model"] in src and b["strength_unit"] in ("U_per_seed", "U_total", "mCi_apparent")
               for b in batches)
    for p in patients:
        v_pre, v_0, v_ct = (float(p[k]) for k in ("volume_preimplant_cc", "volume_postimplant_cc", "volume_ct_cc"))
        assert v_0 > v_ct > v_pre, p["patient_id"]
        st = contours[p["patient_id"]]["structures"]
        assert set(st) == {"prostate", "urethra", "rectum"}
        assert len(engine.voxel_centres(st["rectum"])) >= math.ceil(2.0 / engine.VOX_CC)
    assert set(TAGS) == ids and all(set(t) == set(COLS) for t in TAGS.values())


def test_values_are_well_formed(rows):
    """Known patients, doses with three decimals, percentages with two, volumes with three, yes or no."""
    ids = {p["patient_id"] for p in engine.load()[1]}
    for r in rows:
        assert r[0] in ids, r
        for col, text in zip(COLS, r[1:]):
            assert re.fullmatch(PATTERN[kind(col)], text), (r[0], col, text)


def test_rows_are_sorted_and_complete(truth, rows):
    """One row per patient, sorted by patient_id."""
    assert [r[0] for r in rows] == sorted(truth)


FAMILIES = (
    "static_dose", "volume_scaling", "scaled_about_preimplant_volume", "integral_from_ct", "two_d_for_single_marker",
    "nearest_neighbour_instead_of_c3", "linear_g_interpolation", "anisotropy_held_beyond_last_angle",
    "apparent_activity_unconverted", "apparent_activity_fixed_coefficient", "batch_total_as_per_seed",
    "no_decay_to_implant", "calibration_offset_ignored", "negative_decay_clamped",
    "implant_time_without_daylight_saving", "duplicates_kept", "floor_rank", "urethra_subtracted_from_prostate",
    "mean_life_144", "strict_criteria",
)


@pytest.mark.parametrize("family", FAMILIES)
def test_rule_family(truth, got, family):
    """Every value that this misreading would move is right."""
    pick = lambda pid, col: family in TAGS[pid][col]
    assert any(pick(pid, col) for pid in truth for col in COLS), f"no value depends on {family}"
    bad = _bad(truth, got, pick)
    assert not bad, f"{len(bad)} wrong, e.g. {bad[:4]}"


def test_every_value(truth, got):
    """Every index within tolerance and every criterion exact, for every patient."""
    bad = _bad(truth, got, lambda pid, col: True)
    assert not bad, f"{len(bad)} of {len(truth) * len(COLS)} wrong, e.g. {bad[:4]}"
