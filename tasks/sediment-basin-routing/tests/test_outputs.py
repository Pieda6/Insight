"""Verifier for sediment-basin-routing.

Every cell and storm is recomputed by an independent model (engine.py) from the verifier's private copy of the
inputs. The engine is itself checked against published NEH Part 630, TR-55 and HEC-22 worked examples and against
peak inflows of planted storms worked by hand (golden.json). No agent code is executed.
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

OUT = Path("/app/output/basin_storms.csv")
HEADER = ("site_id,basin_id,storm_start,peak_inflow_cfs,peak_outflow_cfs,peak_stage_ft,time_of_peak_stage,"
          "spillway_flow,spill_volume_cf")
GOLDEN = json.loads((HERE / "golden.json").read_text())
SITES = {s["site_id"]: s for s in json.loads((engine.DATA / "sites.json").read_text())}
CELLS = {b["basin_id"]: b for s in SITES.values() for b in s["basins"]}
FED = {b["discharges_to"] for b in CELLS.values() if b["cell"] == "main" and b["discharges_to"]}
PAIRED = {b["basin_id"] for b in CELLS.values() if b["cell"] == "forebay"} | \
    {b["divider"]["drains_into"] for b in CELLS.values() if b["cell"] == "forebay"}
STAMP = r"2026-\d{2}-\d{2}T\d{2}:\d{2}"


def flow_ok(got, want):
    return abs(got - want) <= max(0.01, 0.005 * abs(want))


def row_ok(g, w):
    return (g is not None and flow_ok(g[0], w[3]) and flow_ok(g[1], w[4]) and abs(g[2] - w[5]) <= 0.005
            and g[3] in w[10] and g[4] == w[7] and abs(g[5] - w[8]) <= max(5.0, 0.01 * w[8]))


@pytest.fixture(scope="module")
def truth():
    return engine.expected(full=True)


@pytest.fixture(scope="module")
def rows():
    assert OUT.is_file(), "missing /app/output/basin_storms.csv"
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
    return {(r[0], r[1], r[2]): (float(r[3]), float(r[4]), float(r[5]), r[6], r[7], float(r[8])) for r in rows}


def _bad(truth, got, pick):
    bad = []
    for w in truth:
        g = got.get((w[0], w[1], w[2]))
        if pick(w) and not row_ok(g, w):
            bad.append((w[0], w[1], w[2], g, (round(w[3], 3), round(w[4], 3), round(w[5], 3), w[6], w[7], round(w[8], 1))))
    return bad


def test_engine_matches_published_examples():
    """The engine reproduces NEH, TR-55 and HEC-22 worked examples."""
    for ex in GOLDEN["examples"]:
        c = ex["check"]
        if c == "runoff":
            v = engine.runoff_in(ex["rain_in"], ex["cn"])
        elif c == "tp":
            v = engine.time_to_peak(ex["tc_h"], ex["dd_h"])
        elif c == "qp":
            v = engine.peak_rate(ex["sq_mi"], ex["tc_h"], ex["dd_h"])
        elif c == "tc":
            v = engine.tc_tr55(ex["path"], ex["surface"], ex["p2_in"])
        elif c == "orifice":
            v = engine.orifice_q(ex["c"], ex["diameter_ft"], ex["depth_ft"] - ex["diameter_ft"] / 2)
        elif c == "riser":
            v = engine.riser_q(ex["cw"], ex["co"], ex["weir_length_ft"], ex["diameter_ft"], ex["head_ft"])
        elif c == "conic":
            v = engine.conic(ex["a1"], ex["a2"], ex["d"])
        elif c == "villemonte":
            v = engine.villemonte(ex["h1"], ex["h2"])
        else:
            v = engine.trapezoid_volume(ex["L"], ex["W"], ex["Z"], ex["D"])
        assert abs(v - ex["expect"]) <= ex["tol"], (ex["source"], v, ex["expect"])


def test_engine_matches_hand_worked_storms(truth):
    """The engine reproduces the peak inflows of the planted storms worked by hand."""
    idx = {(w[0], w[1], w[2]): w for w in truth}
    for key, want in GOLDEN["rows"].items():
        w = idx[tuple(key.split("|"))]
        assert abs(w[3] - want["peak_inflow_cfs"]) <= 0.002, (key, w[3], want)


def test_inputs_are_consistent():
    """Areas drain to known cells, dividers and outfalls name known cells, gauge intervals are on the grid."""
    for s in SITES.values():
        ids = {b["basin_id"] for b in s["basins"]}
        assert all(a["drains_to"] in ids for a in s["drainage_areas"])
        for b in s["basins"]:
            if b["cell"] == "forebay":
                assert b["divider"]["drains_into"] in ids
            else:
                assert b["discharges_to"] in ids | {None}
    for r in json.loads((engine.DATA / "rain_gauge.json").read_text()):
        assert int(r["interval_start"][-2:]) % 6 == 0 and float(r["rain_in"]) > 0, r


def test_values_are_well_formed(rows):
    """Known ids, timestamps, three-decimal numbers, yes or no."""
    for r in rows:
        assert r[0] in SITES and r[1] in CELLS and r[1].startswith(r[0] + "-"), r
        assert re.fullmatch(STAMP, r[2]) and re.fullmatch(STAMP, r[6]), r
        assert all(re.fullmatch(r"-?\d+\.\d{3}", x) for x in (r[3], r[4], r[5], r[8])), r
        assert r[7] in ("yes", "no"), r


def test_rows_are_sorted_and_complete(truth, rows):
    """One row per cell and storm, sorted by site_id, basin_id and storm_start."""
    assert [tuple(r[:3]) for r in rows] == [(w[0], w[1], w[2]) for w in truth]


def test_hand_worked_storms(got):
    """The planted storms worked by hand have the right peak inflow."""
    for key, want in GOLDEN["rows"].items():
        g = got.get(tuple(key.split("|")))
        assert g is not None and flow_ok(g[0], want["peak_inflow_cfs"]), (key, g, want)


def _main(w):
    return CELLS[w[1]]["cell"] == "main"


FAMILIES = {
    "peak_inflow": None,
    "stays_below_riser": lambda w: _main(w) and w[5] <= CELLS[w[1]]["riser"]["crest_elevation_ft"],
    "riser_flow": lambda w: _main(w) and CELLS[w[1]]["riser"]["crest_elevation_ft"] < w[5]
    <= CELLS[w[1]]["emergency_spillway"]["crest_elevation_ft"],
    "spillway_flow_and_volume": lambda w: w[7] == "yes",
    "forebays_and_their_main_cells": lambda w: w[1] in PAIRED,
    "cells_fed_by_other_main_cells": lambda w: w[1] in FED,
    "surveyed_contour_cells": lambda w: CELLS[w[1]]["geometry"]["type"] != "trapezoid",
    "carryover_from_earlier_storms": lambda w: w[9] > min(c["elevation_ft"] for c in CELLS[w[1]]["geometry"]["contours"])
    + 0.2 if CELLS[w[1]]["geometry"]["type"] != "trapezoid" else w[9] > CELLS[w[1]]["geometry"]["bottom_elevation_ft"] + 0.2,
}


@pytest.mark.parametrize("family", sorted(FAMILIES))
def test_rule_family(truth, got, family):
    """Every cell-storm in this family is within tolerance."""
    pick = FAMILIES[family]
    if pick is None:
        bad = [(w[:3], got.get((w[0], w[1], w[2])), round(w[3], 3)) for w in truth
               if got.get((w[0], w[1], w[2])) is None or not flow_ok(got[(w[0], w[1], w[2])][0], w[3])]
    else:
        assert any(pick(w) for w in truth)
        bad = _bad(truth, got, pick)
    assert not bad, f"{len(bad)} wrong, e.g. {bad[:4]}"


def test_every_row(truth, got):
    """Every cell and storm is within tolerance."""
    bad = _bad(truth, got, lambda w: True)
    assert not bad, f"{len(bad)} of {len(truth)} wrong, e.g. {bad[:4]}"
