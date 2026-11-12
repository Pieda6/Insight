"""Verifier for tg51-output-audit.

Every beam is recomputed by an independent engine (engine.py) from the verifier's private copy of the inputs. A row is
right when both values are within 0.3 percent of one value pair the documents allow for that beam (kQ by Eq. (1) or by
interpolating the addendum's tabulated values; Eq. (13)/(14) or Eq. (15) for a flattened beam of 10 MV or more; the
chamber-length average of the profile taken as a mean of the samples or by the trapezoid rule). The engine's formulas
are checked against hand-worked values (golden.json). case_tags.json lists, for each beam, the misreadings that move
it outside the tolerance; the tests check that list against the engine. No agent code is executed.
"""
import csv
import json
import math
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import engine  # noqa: E402

OUT = Path("/app/output/dose_per_mu.csv")
HEADER = "beam_id,dose_ref_cgy_per_mu,dose_dmax_cgy_per_mu"
TOL = 0.003
GOLDEN = json.loads((HERE / "golden.json").read_text())
TAGS = json.loads((HERE / "case_tags.json").read_text())


@pytest.fixture(scope="module")
def data():
    return engine.Data()


@pytest.fixture(scope="module")
def truth(data):
    return {b["beam_id"]: engine.allowed(data, b) for b in data.beams}


@pytest.fixture(scope="module")
def rows():
    assert OUT.is_file(), "missing /app/output/dose_per_mu.csv"
    lines = OUT.read_text().splitlines()
    assert lines and lines[0] == HEADER, f"header must be exactly {HEADER}"
    assert all(line.strip() for line in lines[1:]), "blank lines are not allowed"
    out = []
    for r in csv.reader(lines[1:]):
        assert len(r) == 3, f"row must have 3 columns: {r}"
        out.append(r)
    return out


def _num(v):
    try:
        x = float(v)
    except ValueError:
        return None
    return x if math.isfinite(x) else None


@pytest.fixture(scope="module")
def got(rows):
    return {r[0]: (_num(r[1]), _num(r[2])) for r in rows}


def right(g, allowed):
    if g is None or g[0] is None or g[1] is None:
        return False
    return any(all(math.isfinite(w) and w > 0 for w in pair) and abs(g[0] / pair[0] - 1) <= TOL
               and abs(g[1] / pair[1] - 1) <= TOL for pair in allowed)


def _bad(truth, got, pick):
    return [(k, got.get(k), [round(v, 5) for v in w[0]]) for k, w in truth.items() if pick(k) and not right(got.get(k), w)]


def test_engine_matches_hand_worked_values():
    """Eqs. (10), (12)-(15), (19)-(20) and addendum Eq. (1) reproduce hand-worked values."""
    g = GOLDEN
    for c in g["ptp"]:
        assert abs(engine.ptp(c["T"], c["unit_T"], c["P"], c["unit_P"]) - c["value"]) < 2e-6
    for c in g["eq13"]:
        x = (0.8905 + 0.00150 * c["pb"]) * c["pb"] if c["pb"] >= 73 else c["pb"]
        assert abs(x - c["x"]) < 1e-6
    for c in g["eq14"]:
        assert abs((0.8116 + 0.00264 * c["pb"]) * c["pb"] - c["x"]) < 1e-6
    d = engine.Data()
    for c in g["kq_fit"] + g["kq_below_63"] + g["kq_tg51"]:
        assert abs(engine.kq(d, c["chamber"], c["x"], "fit", frozenset()) - c["value"]) < 2e-6
    for c in g["kr50"]:
        assert abs(engine.krp(c["r50"], c["type"], frozenset()) - c["value"]) < 2e-6
    for c in g["pion"]:
        r = c["ratio"]
        assert abs((1 - r) / (c["mh"] / c["ml"] - r) - c["value"]) < 1e-9


def test_inputs_are_consistent(data):
    """Every beam is listed once, its chambers exist, and it has case tags."""
    ids = [b["beam_id"] for b in data.beams]
    assert len(ids) == len(set(ids)) and set(TAGS) == set(ids)
    for b in data.beams:
        assert b["reference_chamber"] in data.chambers
        assert all(s in data.chambers for s in b["scans"].values())


def test_allowed_values_agree_within_tolerance(truth):
    """The value pairs the documents allow for one beam never spread by more than the tolerance."""
    wide = [k for k, w in truth.items()
            if max(p[0] for p in w) / min(p[0] for p in w) - 1 > TOL or max(p[1] for p in w) / min(p[1] for p in w) - 1 > TOL]
    assert not wide, wide[:4]


def test_case_tags_discriminate(data, truth):
    """Each tagged misreading moves that beam outside the tolerance of every value pair the documents allow."""
    beams = {b["beam_id"]: b for b in data.beams}
    weak = []
    for k, fams in TAGS.items():
        for fam in fams:
            base = engine.allowed(data, beams[k])
            alt = engine.allowed(data, beams[k], frozenset([fam]))
            moved = [a for a, o in zip(alt, base) if max(abs(a[0] - o[0]), abs(a[1] - o[1])) > 1e-12]
            if not moved or any(right(a, truth[k]) for a in moved):
                weak.append((k, fam))
    assert not weak, weak[:4]


def test_values_are_well_formed(rows, data):
    """Known beams and finite, positive doses."""
    ids = {b["beam_id"] for b in data.beams}
    for r in rows:
        assert r[0] in ids, r
        assert _num(r[1]) is not None and _num(r[1]) > 0 and _num(r[2]) is not None and _num(r[2]) > 0, r


def test_rows_are_complete_and_ordered(rows, data):
    """One row per beam, in the order of audit.json."""
    assert [r[0] for r in rows] == [b["beam_id"] for b in data.beams]


FAMILIES = (
    "temp_unit", "pressure_unit", "pelec_wrong_range", "ppol_ignored", "ppol_wrong_reading", "pion_ignored",
    "pion_continuous", "prp_ignored", "prp_full_profile", "no_shift", "tg51_kq", "dmax_with_dd10x", "sad_with_pdd",
    "kr50_swapped", "crosscal_pelec",
)


@pytest.mark.parametrize("family", FAMILIES)
def test_rule_family(truth, got, family):
    """Every beam whose values depend on this reading is right."""
    pick = lambda k: family in TAGS[k]
    assert any(pick(k) for k in truth)
    bad = _bad(truth, got, pick)
    assert not bad, f"{len(bad)} wrong, e.g. {bad[:3]}"


def test_every_beam(truth, got):
    """Every beam: both values within 0.3 percent of a value pair the documents allow."""
    bad = _bad(truth, got, lambda k: True)
    assert not bad, f"{len(bad)} of {len(truth)} wrong, e.g. {bad[:3]}"
