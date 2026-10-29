"""Verifier for TASK-NAME.

Every case is recomputed by an independent model (engine.py) from the verifier's private copy of the inputs.
The engine is itself checked against published worked examples (golden.json). No agent code is executed.
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

OUT = Path("/app/output/OUTPUT_FILE.csv")
HEADER = "case_id,value_a,value_b,category,decision"          # exact header from instruction.md
REL = 0.005                                                    # tolerance for continuous columns
GOLDEN = json.loads((HERE / "golden.json").read_text())


def close(got, want):
    assert math.isfinite(got) and math.isfinite(want), (got, want)
    return abs(got - want) <= REL * abs(want)


def row_ok(g, w):
    # exact for letters, words and rounded integers; tolerance for continuous values
    return (g is not None and close(g[0], w["value_a"]) and close(g[1], w["value_b"])
            and g[2] == w["category"] and g[3] == w["decision"])


@pytest.fixture(scope="module")
def truth():
    return engine.expected()                                   # {case_id: {..., "tags": set()}} sorted


@pytest.fixture(scope="module")
def rows():
    assert OUT.is_file(), f"missing {OUT}"
    lines = OUT.read_text().splitlines()
    assert lines and lines[0] == HEADER, f"header must be exactly {HEADER}"
    assert all(line.strip() for line in lines[1:]), "blank lines are not allowed"
    out = []
    for r in csv.reader(lines[1:]):
        assert len(r) == HEADER.count(",") + 1, f"wrong column count: {r}"
        out.append(r)
    return out


@pytest.fixture(scope="module")
def got(rows):
    out = {r[0]: (float(r[1]), float(r[2]), r[3], r[4]) for r in rows}
    for cid, g in out.items():
        assert all(math.isfinite(x) for x in g[:2]), f"{cid}: non-finite value {g}"
    return out


def _bad(truth, got, pick):
    return [(cid, got.get(cid)) for cid, w in truth.items() if pick(w) and not row_ok(got.get(cid), w)]


def test_engine_matches_published_examples():
    """The engine reproduces the standard's worked examples."""
    for ex in GOLDEN["examples"]:
        v = getattr(engine, ex["check"])(*ex["args"]) if isinstance(ex["args"], list) else \
            getattr(engine, ex["check"])(**ex["args"])
        assert math.isfinite(v) and abs(v - ex["expect"]) <= ex["tol"], (ex["source"], v, ex["expect"])


def test_inputs_are_consistent():
    """Structural checks on the private inputs (ids, references, ordering)."""
    engine.load()


def test_values_are_well_formed(rows):
    """Known ids, numbers with the stated decimals, allowed words."""
    for r in rows:
        assert re.fullmatch(r"-?\d+\.\d{3}", r[1]) and re.fullmatch(r"-?\d+\.\d{3}", r[2]), r
        assert r[3] in ("below", "within", "above"), r


def test_rows_are_sorted_and_complete(truth, rows):
    """One row per case, sorted as the instruction says."""
    assert [r[0] for r in rows] == list(truth)


FAMILIES = ("family_one", "family_two", "near_thresholds")


@pytest.mark.parametrize("family", FAMILIES)
def test_rule_family(truth, got, family):
    """Every case in this method family is right."""
    assert any(family in w["tags"] for w in truth.values())
    bad = _bad(truth, got, lambda w: family in w["tags"])
    assert not bad, f"{len(bad)} wrong, e.g. {bad[:4]}"


def test_every_row(truth, got):
    """Every case is right."""
    bad = _bad(truth, got, lambda w: True)
    assert not bad, f"{len(bad)} of {len(truth)} wrong, e.g. {bad[:4]}"
