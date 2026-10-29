"""Verifier for storm-drain-energy-grade.

Every pipe and event is recomputed by an independent model (engine.py) from the verifier's private copy of the
inputs. The engine is itself checked against the worked numbers of HEC-22 Examples 9.1 and 9.2 and Table 9.5
(golden.json). No agent code is executed.
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

OUT = Path("/app/output/pipe_grades.csv")
HEADER = "system_id,event,pipe_id,ds_case,us_condition,egl_ds_ft,egl_us_ft,structure_egl_ft,surcharged"
TOL = 0.002
GOLDEN = json.loads((HERE / "golden.json").read_text())
SYSTEMS, FLOWS, TAILWATER = engine.load()
EVENTS = ("10-year", "100-year")


def row_ok(g, w):
    return (g is not None and g[0] == w[3] and g[1] in w[5] and abs(g[2] - w[6]) <= TOL
            and abs(g[3] - w[7]) <= TOL and abs(g[4] - w[8]) <= TOL and g[5] == w[9])


@pytest.fixture(scope="module")
def truth():
    return engine.expected(with_tags=True)


@pytest.fixture(scope="module")
def rows():
    assert OUT.is_file(), "missing /app/output/pipe_grades.csv"
    lines = OUT.read_text().splitlines()
    assert lines and lines[0] == HEADER, f"header must be exactly {HEADER}"
    assert all(line.strip() for line in lines[1:]), "blank lines are not allowed"
    out = []
    for r in csv.reader(lines[1:]):
        assert len(r) == 9, f"row must have 9 columns: {r}"
        out.append(r)
    return out


@pytest.fixture(scope="module")
def got(rows):
    return {(r[0], r[1], r[2]): (r[3], r[4], float(r[5]), float(r[6]), float(r[7]), r[8]) for r in rows}


def _bad(truth, got, pick):
    rows, tags = truth
    bad = []
    for w in rows:
        g = got.get(w[:3])
        if pick(w, tags[w[:3]]) and not row_ok(g, w):
            bad.append((w[:3], g, (w[3], w[4], round(w[6], 3), round(w[7], 3), round(w[8], 3), w[9])))
    return bad


def test_engine_matches_published_examples():
    """The engine reproduces HEC-22 Example 9.1 and 9.2 values and the Table 9.5 interpolation."""
    for ex in GOLDEN["examples"]:
        fn = getattr(engine, ex["check"])
        args = ex["args"]
        if isinstance(args, dict):
            kw = dict(args)
            kw["joined"] = [tuple(x) for x in kw["joined"]]
            kw["plunging"] = [tuple(x) for x in kw["plunging"]]
            v = fn(**kw)
        else:
            v = fn(*[[tuple(x) for x in a] if isinstance(a, list) else a for a in args])
        assert abs(v - ex["expect"]) <= ex["tol"], (ex["source"], v, ex["expect"])


def test_inputs_are_consistent():
    """Each system is a tree draining to one outfall, flows are given for inlets, every event has a tailwater."""
    for s in SYSTEMS:
        ids = {x["structure_id"] for x in s["structures"]}
        froms = [p["from_structure"] for p in s["pipes"]]
        assert sorted(froms) == sorted(ids), s["system_id"]
        assert sum(p["to_structure"] is None for p in s["pipes"]) == 1
        down = {p["from_structure"]: p["to_structure"] for p in s["pipes"]}
        for sid in ids:
            seen = set()
            while sid is not None:
                assert sid not in seen and sid in ids
                seen.add(sid)
                sid = down[sid]
        for p in s["pipes"]:
            assert p["upstream_invert_ft"] > p["downstream_invert_ft"] and p["length_ft"] > 0
        inlets = {x["structure_id"] for x in s["structures"] if x["type"] == "inlet"}
        for ev in EVENTS:
            assert {k for k in FLOWS[ev] if k.startswith(s["system_id"] + "-")} == inlets
            assert (s["system_id"], ev) in TAILWATER


def test_values_are_well_formed(rows):
    """Known ids, case letters, three-decimal elevations, yes or no."""
    pipes = {p["pipe_id"]: s["system_id"] for s in SYSTEMS for p in s["pipes"]}
    for r in rows:
        assert pipes.get(r[2]) == r[0] and r[1] in EVENTS, r
        assert r[3] in "ABCDE" and len(r[3]) == 1 and r[4] in "ABCD" and len(r[4]) == 1, r
        assert all(re.fullmatch(r"-?\d+\.\d{3}", x) for x in r[5:8]), r
        assert r[8] in ("yes", "no"), r


def test_rows_are_sorted_and_complete(truth, rows):
    """One row per pipe and event, sorted by system_id, event and pipe_id."""
    assert [tuple(r[:3]) for r in rows] == [w[:3] for w in truth[0]]


FAMILIES = (
    "outfall_pipes", "submerged_outlets", "partly_full_outlets", "normal_depth_outlets", "full_flow_upstream",
    "supercritical_reset", "plunging_inflow_pipes", "angled_inflows", "terminal_structures",
    "benching_interpolated", "drops_over_10_diameters", "outflow_energy_governs", "surcharged_structures",
    "near_thresholds",
)


@pytest.mark.parametrize("family", FAMILIES)
def test_rule_family(truth, got, family):
    """Every pipe and event in this method family is right."""
    assert any(family in t for t in truth[1].values())
    bad = _bad(truth, got, lambda w, t: family in t)
    assert not bad, f"{len(bad)} wrong, e.g. {bad[:4]}"


def test_every_row(truth, got):
    """Every pipe and event: case and condition letters and surcharge exact, elevations within 0.002 ft."""
    bad = _bad(truth, got, lambda w, t: True)
    assert not bad, f"{len(bad)} of {len(truth[0])} wrong, e.g. {bad[:4]}"
