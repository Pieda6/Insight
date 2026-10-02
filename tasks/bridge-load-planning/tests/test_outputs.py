"""Verifier for bridge-load-planning.

Every number is recomputed from the agent's pallet positions with an independent engine
(engine.py) on the verifier's own copy of the inputs. No agent code is executed.
"""
import csv
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import engine  # noqa: E402

OUT = Path("/app/output")
EXPECTED = json.loads((Path(__file__).resolve().parent / "expected.json").read_text())


def _csv(name, header):
    path = OUT / name
    assert path.is_file(), f"missing {path}"
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames is not None
        assert [h.strip() for h in reader.fieldnames] == header, f"{name} header must be {header}"
        return [{k.strip(): (v or "").strip() for k, v in r.items()} for r in reader]


@pytest.fixture(scope="module")
def inputs():
    return engine.load()


@pytest.fixture(scope="module")
def plan(inputs):
    units, sliders, pallets = inputs
    rows = _csv("load_plan.csv", ["pallet_id", "unit_id", "position_in"])
    out = {}
    for r in rows:
        assert r["pallet_id"] not in out, f"pallet {r['pallet_id']} listed twice"
        assert r["position_in"].lstrip("-").isdigit(), f"position must be a whole number: {r}"
        out[r["pallet_id"]] = (r["unit_id"], int(r["position_in"]))
    return out


@pytest.fixture(scope="module")
def unit_sliders():
    rows = _csv("units.csv", ["unit_id", "slider_position_id"])
    out = {}
    for r in rows:
        assert r["unit_id"] not in out, f"unit {r['unit_id']} listed twice"
        out[r["unit_id"]] = r["slider_position_id"]
    return out


@pytest.fixture(scope="module")
def summary():
    path = OUT / "summary.json"
    assert path.is_file(), "missing /app/output/summary.json"
    doc = json.loads(path.read_text())
    assert isinstance(doc, dict) and set(doc) >= {"units_used", "axle_loads_lb"}
    return doc


@pytest.fixture(scope="module")
def trucks(inputs, plan, unit_sliders):
    units, sliders, pallets = inputs
    by_unit = {}
    for pid, (uid, pos) in plan.items():
        by_unit.setdefault(uid, []).append((pallets[pid][0], pos, pallets[pid][1], pid))
    result = {}
    for uid, items in by_unit.items():
        if uid in units and unit_sliders.get(uid) in sliders:
            u, s = units[uid], sliders[unit_sliders[uid]]
            result[uid] = (u, s, items, engine.axle_loads(u, s, [i[:3] for i in items]))
    return result


def test_every_pallet_assigned_once_to_a_real_unit(inputs, plan):
    """Each pallet in pallets.csv appears exactly once, on a unit that exists."""
    units, _, pallets = inputs
    assert set(plan) == set(pallets)
    assert all(uid in units for uid, _ in plan.values())


def test_units_file_matches_plan_and_sliders_are_valid(inputs, plan, unit_sliders):
    """units.csv lists exactly the units carrying pallets, each with one of its own slider settings."""
    units, sliders, _ = inputs
    assert set(unit_sliders) == {uid for uid, _ in plan.values()}
    for uid, sid in unit_sliders.items():
        assert sid in sliders and sliders[sid]["unit_id"] == uid, f"{sid} is not a slider setting of {uid}"


def test_pallets_fit_and_do_not_overlap(inputs, trucks):
    """Pallets sit inside the trailer's inside length and never overlap."""
    for uid, (u, _, items, _) in trucks.items():
        length = int(u["trailer_inside_length_in"])
        spans = sorted((pos, pos + ln, pid) for _, pos, ln, pid in items)
        for a, b, pid in spans:
            assert 0 <= a and b <= length, f"{pid} on {uid} sticks out of the trailer"
        for (a1, b1, p1), (a2, b2, p2) in zip(spans, spans[1:]):
            assert a2 >= b1, f"{p1} and {p2} overlap on {uid}"


def test_axle_tandem_and_gross_limits(trucks):
    """Steer axle <= 20,000 lb, each tandem <= 34,000 lb, gross <= 80,000 lb on every truck."""
    bad = {}
    for uid, (u, s, _, loads) in trucks.items():
        v = [m for m in engine.violations(u, s, loads) if not m.startswith("bridge")]
        if v:
            bad[uid] = v
    assert not bad, bad


def test_bridge_formula_on_every_axle_group(trucks):
    """Every group of two or more consecutive axles meets the Bridge Formula (with the
    34,000 + 34,000 lb two-tandem allowance on axles 2-5 at 36 ft or more)."""
    bad = {}
    for uid, (u, s, _, loads) in trucks.items():
        v = [m for m in engine.violations(u, s, loads) if m.startswith("bridge")]
        if v:
            bad[uid] = v
    assert not bad, bad


def test_minimum_number_of_units(plan):
    """The plan uses the minimum possible number of units."""
    used = len({uid for uid, _ in plan.values()})
    assert used == EXPECTED["min_units"], f"used {used} units, minimum is {EXPECTED['min_units']}"


def test_summary_units_used(summary, plan):
    """summary.json units_used equals the number of units carrying pallets."""
    assert summary["units_used"] == len({uid for uid, _ in plan.values()})


def test_reported_axle_loads_match(summary, trucks):
    """Reported axle loads (steer, drive 1, drive 2, trailer 1, trailer 2) match the
    recomputed exact loads within 1 lb."""
    rep = summary["axle_loads_lb"]
    assert isinstance(rep, dict) and set(rep) == set(trucks)
    for uid, (_, _, _, loads) in trucks.items():
        vals = rep[uid]
        assert isinstance(vals, list) and len(vals) == 5 and all(isinstance(v, int) for v in vals), uid
        for got, exact in zip(vals, loads):
            assert abs(got - exact) <= 1, f"{uid}: reported {vals}, expected {[round(float(v)) for v in loads]}"
