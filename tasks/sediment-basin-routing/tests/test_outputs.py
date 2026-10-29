"""Verifier for sediment-basin-routing.

Every basin and storm is recomputed by an independent model (engine.py) from the verifier's private copy of the
inputs. The engine is itself checked against published NEH Part 630 and HEC-22 worked examples and against peak
inflows of planted storms worked by hand (golden.json). No agent code is executed.
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
HEADER = "site_id,basin_id,storm_start,peak_inflow_cfs,peak_outflow_cfs,peak_stage_ft,spillway_flow"
GOLDEN = json.loads((HERE / "golden.json").read_text())
SITES = {s["site_id"]: s for s in json.loads((engine.DATA / "sites.json").read_text())}
BASINS = {b["basin_id"]: b for s in SITES.values() for b in s["basins"]}
UPSTREAM = {b["discharges_to"] for b in BASINS.values() if b["discharges_to"]}


def flow_ok(got, want):
    return abs(got - want) <= max(0.01, 0.005 * abs(want))


def row_ok(got, want):
    return (got is not None and flow_ok(got[0], want[3]) and flow_ok(got[1], want[4])
            and abs(got[2] - want[5]) <= 0.005 and got[3] == want[6])


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
        assert len(r) == 7, f"row must have 7 columns: {r}"
        out.append(r)
    return out


@pytest.fixture(scope="module")
def got(rows):
    by = {}
    for r in rows:
        by[(r[0], r[1], r[2])] = (float(r[3]), float(r[4]), float(r[5]), r[6])
    return by


def _bad(truth, got, pick):
    bad = []
    for w in truth:
        if pick(w) and not row_ok(got.get((w[0], w[1], w[2])), w):
            bad.append((w[0], w[1], w[2], got.get((w[0], w[1], w[2])),
                        (round(w[3], 3), round(w[4], 3), round(w[5], 3), w[6])))
    return bad


def test_engine_matches_published_examples():
    """The engine's runoff, unit hydrograph, rating and storage functions reproduce NEH and HEC-22 examples."""
    for ex in GOLDEN["examples"]:
        c = ex["check"]
        if c == "runoff":
            v = engine.runoff_in(ex["rain_in"], ex["cn"])
        elif c == "tp":
            v = engine.time_to_peak(ex["tc_h"], ex["dd_h"])
        elif c == "qp":
            v = engine.peak_rate(ex["sq_mi"], ex["tc_h"], ex["dd_h"])
        elif c == "orifice":
            v = engine.orifice_q(ex["c"], ex["diameter_ft"], ex["depth_ft"] - ex["diameter_ft"] / 2)
        elif c == "riser":
            v = engine.riser_q(ex["cw"], ex["co"], ex["weir_length_ft"], ex["diameter_ft"], ex["head_ft"])
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
    """Areas drain to known basins, basin chains end, and gauge intervals sit on the 6-minute grid."""
    for s in SITES.values():
        ids = {b["basin_id"] for b in s["basins"]}
        assert all(a["drains_to"] in ids for a in s["drainage_areas"])
        assert all(b["discharges_to"] in ids | {None} for b in s["basins"])
    for r in json.loads((engine.DATA / "rain_gauge.json").read_text()):
        assert int(r["interval_start"][-2:]) % 6 == 0 and float(r["rain_in"]) > 0, r


def test_values_are_well_formed(rows):
    """Known ids, timestamps, three-decimal numbers, yes or no."""
    for r in rows:
        assert r[0] in SITES and r[1] in BASINS and r[1].startswith(r[0] + "-"), r
        assert re.fullmatch(r"2026-\d{2}-\d{2}T\d{2}:\d{2}", r[2]), r
        assert all(re.fullmatch(r"-?\d+\.\d{3}", x) for x in r[3:6]), r
        assert r[6] in ("yes", "no"), r


def test_rows_are_sorted_and_complete(truth, rows):
    """One row per basin and storm, sorted by site_id, basin_id and storm_start."""
    assert [tuple(r[:3]) for r in rows] == [(w[0], w[1], w[2]) for w in truth]


def test_hand_worked_storms(got):
    """The planted storms worked by hand have the right peak inflow."""
    for key, want in GOLDEN["rows"].items():
        g = got.get(tuple(key.split("|")))
        assert g is not None and flow_ok(g[0], want["peak_inflow_cfs"]), (key, g, want)


FAMILIES = {
    "peak_inflow": lambda w: True,
    "stays_below_riser": lambda w: w[5] <= BASINS[w[1]]["riser"]["crest_elevation_ft"],
    "riser_flow": lambda w: BASINS[w[1]]["riser"]["crest_elevation_ft"] < w[5] <= BASINS[w[1]]["emergency_spillway"]["crest_elevation_ft"],
    "spillway_flow": lambda w: w[6] == "yes",
    "basins_in_series": lambda w: w[1] in UPSTREAM,
    "carryover_from_earlier_storms": lambda w: w[7] > BASINS[w[1]]["dewatering_orifice"]["invert_elevation_ft"]
    + BASINS[w[1]]["dewatering_orifice"]["diameter_in"] / 24 + 0.05,
}


@pytest.mark.parametrize("family", sorted(FAMILIES))
def test_rule_family(truth, got, family):
    """Every basin-storm in this family is within tolerance."""
    pick = FAMILIES[family]
    assert any(pick(w) for w in truth)
    if family == "peak_inflow":
        bad = [(w[:3], got.get((w[0], w[1], w[2])), round(w[3], 3)) for w in truth
               if got.get((w[0], w[1], w[2])) is None or not flow_ok(got[(w[0], w[1], w[2])][0], w[3])]
    else:
        bad = _bad(truth, got, pick)
    assert not bad, f"{len(bad)} wrong, e.g. {bad[:5]}"


def test_every_row(truth, got):
    """Every basin and storm is within tolerance."""
    bad = _bad(truth, got, lambda w: True)
    assert not bad, f"{len(bad)} of {len(truth)} wrong, e.g. {bad[:5]}"
