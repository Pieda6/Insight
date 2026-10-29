"""Verifier for vancomycin-auc-dosing.

Every patient is recomputed by an independent model (engine.py) from the verifier's private copy of the inputs.
The engine is itself checked against textbook one-compartment results (golden.json). No agent code is executed.
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

OUT = Path("/app/output/vancomycin_review.csv")
HEADER = "patient_id,ke_per_h,volume_l,auc48,auc24_ss,exposure,new_dose_mg"
REL = 0.005
GOLDEN = json.loads((HERE / "golden.json").read_text())


def close(got, want):
    return abs(got - want) <= REL * abs(want)


def row_ok(g, w):
    return (g is not None and close(g[0], w["ke"]) and close(g[1], w["volume"]) and close(g[2], w["auc48"])
            and close(g[3], w["auc24"]) and g[4] == w["exposure"] and g[5] == w["new_dose"])


@pytest.fixture(scope="module")
def truth():
    return engine.expected()


@pytest.fixture(scope="module")
def rows():
    assert OUT.is_file(), "missing /app/output/vancomycin_review.csv"
    lines = OUT.read_text().splitlines()
    assert lines and lines[0] == HEADER, f"header must be exactly {HEADER}"
    assert all(line.strip() for line in lines[1:]), "blank lines are not allowed"
    out = []
    for r in csv.reader(lines[1:]):
        assert len(r) == 7, f"row must have 7 columns: {r}"
        out.append(r)
    return out


@pytest.fixture(scope="module")
def got(rows):
    return {r[0]: (float(r[1]), float(r[2]), float(r[3]), float(r[4]), r[5], int(r[6])) for r in rows}


def _bad(truth, got, pick):
    bad = []
    for pid, w in truth.items():
        if pick(w) and not row_ok(got.get(pid), w):
            bad.append((pid, got.get(pid), (round(w["ke"], 5), round(w["volume"], 2), round(w["auc48"], 1),
                                            round(w["auc24"], 1), w["exposure"], w["new_dose"])))
    return bad


def test_engine_matches_textbook_results():
    """The engine reproduces closed-form one-compartment infusion results and the Sawchuk-Zaske elimination rate."""
    for ex in GOLDEN["examples"]:
        v = getattr(engine, ex["check"])(*ex["args"])
        assert abs(v - ex["expect"]) <= ex["tol"], (ex["source"], v, ex["expect"])


def test_inputs_are_consistent():
    """Every patient has orders and administrations, every administration starts or is marked not given."""
    pats, adm, lev, ords = engine.load()
    ids = {p["patient_id"] for p in pats}
    assert {r["patient_id"] for r in adm} == ids and {r["patient_id"] for r in ords} == ids
    assert {r["patient_id"] for r in lev} <= ids
    first = {}
    for r in adm:
        first.setdefault(r["administration_id"], r["event"])
    assert set(first.values()) <= {"start", "not_given"}


def test_values_are_well_formed(rows):
    """Known patients, numbers with the stated decimals, exposure words and whole-milligram doses."""
    ids = {p["patient_id"] for p in engine.load()[0]}
    for r in rows:
        assert r[0] in ids, r
        assert re.fullmatch(r"\d+\.\d{5}", r[1]) and re.fullmatch(r"\d+\.\d{2}", r[2]), r
        assert re.fullmatch(r"\d+\.\d", r[3]) and re.fullmatch(r"\d+\.\d", r[4]), r
        assert r[5] in ("below", "within", "above") and re.fullmatch(r"\d+", r[6]), r


def test_rows_are_sorted_and_complete(truth, rows):
    """One row per patient, sorted by patient_id."""
    assert [r[0] for r in rows] == list(truth)


FAMILIES = (
    "first_day_levels", "dose_given_between_levels", "irregular_administration_records", "mistimed_levels",
    "levels_near_one_hour_after_infusion", "rejected_or_unreportable_results", "broth_microdilution_mic",
    "mic_by_other_methods", "changed_orders", "near_target_edges", "near_rounding_steps", "exposure_below",
    "exposure_within", "exposure_above",
)


@pytest.mark.parametrize("family", FAMILIES)
def test_rule_family(truth, got, family):
    """Every patient in this family is right."""
    assert any(family in w["tags"] for w in truth.values())
    bad = _bad(truth, got, lambda w: family in w["tags"])
    assert not bad, f"{len(bad)} wrong, e.g. {bad[:4]}"


def test_every_patient(truth, got):
    """Every patient: ke, volume and AUCs within 0.5 percent, exposure and new dose exact."""
    bad = _bad(truth, got, lambda w: True)
    assert not bad, f"{len(bad)} of {len(truth)} wrong, e.g. {bad[:4]}"
