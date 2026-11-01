"""Verifier for tg71-mu-check.

Every beam is recomputed by an independent engine (engine.py) from the verifier's private copy of the inputs. An MU
is right when it is within 0.3 percent of an MU the protocol allows for that beam (Eq. (1) or Eq. (3) for photons,
with or without the bracket of Eq. (14), the wedge-factor field at depth or at the isocenter; either geometric mean
for the effective SSD of an electron insert). The engine is checked against the TG-71 Section 8 worked examples
(golden.json). case_tags.json lists, for each beam, the misreadings that move its MU outside the tolerance. No agent
code is executed.
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

OUT = Path("/app/output/monitor_units.csv")
HEADER = "beam_id,mu"
TOL = 0.003
GOLDEN = json.loads((HERE / "golden.json").read_text())
TAGS = json.loads((HERE / "case_tags.json").read_text())


@pytest.fixture(scope="module")
def truth():
    return engine.expected()


@pytest.fixture(scope="module")
def rows():
    assert OUT.is_file(), "missing /app/output/monitor_units.csv"
    lines = OUT.read_text().splitlines()
    assert lines and lines[0] == HEADER, f"header must be exactly {HEADER}"
    assert all(line.strip() for line in lines[1:]), "blank lines are not allowed"
    out = []
    for r in csv.reader(lines[1:]):
        assert len(r) == 2, f"row must have 2 columns: {r}"
        out.append(r)
    return out


@pytest.fixture(scope="module")
def got(rows):
    out = {}
    for k, v in rows:
        try:
            x = float(v)
        except ValueError:
            x = None
        out[k] = x if x is not None and math.isfinite(x) else None
    return out


def right(g, allowed):
    return g is not None and math.isfinite(g) and any(
        math.isfinite(w) and w > 0 and abs(g / w - 1) <= TOL for w in allowed)


def _bad(truth, got, pick):
    return [(k, got.get(k), round(min(w), 2), round(max(w), 2))
            for k, w in truth.items() if pick(k) and not right(got.get(k), w)]


def test_engine_matches_tg71_worked_examples():
    """The engine reproduces the MU of the TG-71 Section 8 photon and electron examples, as printed (whole MU)."""
    t = engine.Tables()
    for c in GOLDEN["cases"]:
        mus = engine.allowed(t, c["beam"])
        assert all(round(m) == c["mu"] for m in mus), (c["label"], mus)


def test_inputs_are_consistent():
    """Every beam is listed once, with a known modality, and has case tags."""
    _, beams = engine.load()
    ids = [b["beam_id"] for b in beams]
    assert len(ids) == len(set(ids)) and set(TAGS) == set(ids)
    assert all(b["modality"] in ("photon", "electron") for b in beams)


def test_values_are_well_formed(rows):
    """Known beams and finite, positive MU."""
    ids = {b["beam_id"] for b in engine.load()[1]}
    for k, v in rows:
        assert k in ids, k
        x = float(v)
        assert math.isfinite(x) and x > 0, (k, v)


def test_rows_are_complete_and_ordered(rows):
    """One row per beam, in the order of plans.json."""
    assert [r[0] for r in rows] == [b["beam_id"] for b in engine.load()[1]]


def test_allowed_methods_agree_within_tolerance(truth):
    """The MU the protocol allows for one beam never spread by more than the tolerance, so the band stays 0.3 percent."""
    wide = [(k, max(w) / min(w) - 1) for k, w in truth.items() if max(w) / min(w) - 1 > TOL]
    assert not wide, wide[:4]


def test_case_tags_discriminate(truth):
    """Each tagged misreading moves that beam's MU outside the tolerance of every MU the protocol allows."""
    t = engine.Tables()
    beams = {b["beam_id"]: b for b in engine.load()[1]}
    weak = []
    for k, fams in TAGS.items():
        for fam in fams:
            base = engine.allowed(t, beams[k])
            alt = engine.allowed(t, beams[k], frozenset([fam]))
            moved = [a for a, o in zip(alt, base) if abs(a - o) > 1e-9]
            if not moved or any(min(abs(a / w - 1) for w in truth[k]) <= TOL for a in moved):
                weak.append((k, fam))
    assert not weak, weak[:4]


FAMILIES = (
    "sc_shaped", "no_projection", "oar_ignored", "tray_ignored", "wf_at_10cm", "heterogeneity_ignored",
    "batho_inverted", "inverse_square_ignored", "sp_surface_field", "mayneord_ignored",
    "pdd_inverse_square_to_point", "se_equivalent_square", "isodose_ignored", "ssdeff_ignored",
    "air_gap_factor_ignored",
)


@pytest.mark.parametrize("family", FAMILIES)
def test_rule_family(truth, got, family):
    """Every beam whose MU depends on this reading is right."""
    pick = lambda k: family in TAGS[k]
    assert any(pick(k) for k in truth)
    bad = _bad(truth, got, pick)
    assert not bad, f"{len(bad)} wrong, e.g. {bad[:4]}"


def test_every_beam(truth, got):
    """Every beam within 0.3 percent of an MU the protocol allows."""
    bad = _bad(truth, got, lambda k: True)
    assert not bad, f"{len(bad)} of {len(truth)} wrong, e.g. {bad[:4]}"
