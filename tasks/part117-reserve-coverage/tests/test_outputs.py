"""Verifier for part117-reserve-coverage.

Ground truth is recomputed here by an independent Part 117 engine (engine.py) from the
verifier's own copy of the inputs in /tests/data. Nothing the agent wrote is executed.
"""
import csv
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import engine  # noqa: E402

OUT = Path("/app/output")
LEGALITY = OUT / "legality.csv"
ASSIGNMENT = OUT / "assignment.json"
TRAPS = json.loads((Path(__file__).resolve().parent / "trap_pairs.json").read_text())


@pytest.fixture(scope="module")
def data():
    return engine.Data()


@pytest.fixture(scope="module")
def truth(data):
    return engine.legality_matrix(data)


@pytest.fixture(scope="module")
def submitted():
    assert LEGALITY.is_file(), "missing /app/output/legality.csv"
    with open(LEGALITY, newline="") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames is not None
        assert [h.strip() for h in reader.fieldnames] == ["pilot_id", "trip_id", "legal"]
        rows = [{k.strip(): (v or "").strip() for k, v in r.items()} for r in reader]
    out = {}
    for r in rows:
        key = (r["pilot_id"], r["trip_id"])
        assert key not in out, f"duplicate row for {key}"
        assert r["legal"].lower() in ("true", "false"), f"bad legal value {r['legal']!r}"
        out[key] = r["legal"].lower() == "true"
    return out


@pytest.fixture(scope="module")
def plan():
    assert ASSIGNMENT.is_file(), "missing /app/output/assignment.json"
    doc = json.loads(ASSIGNMENT.read_text())
    assert isinstance(doc, dict)
    assert isinstance(doc.get("assignments"), list)
    pairs = []
    for a in doc["assignments"]:
        assert isinstance(a, dict) and isinstance(a.get("trip_id"), str) and isinstance(a.get("pilot_id"), str)
        pairs.append((a["pilot_id"], a["trip_id"]))
    return doc, pairs


def _mismatches(truth, submitted, pairs):
    return [(p, t, truth[(p, t)]) for p, t in pairs if submitted.get((p, t)) != truth[(p, t)]]


def test_legality_has_exactly_one_row_per_pilot_trip_pair(data, submitted):
    """legality.csv lists every pilot x trip combination exactly once and nothing else."""
    expected = {(p, t) for p in data.pilots for t in data.trips}
    assert set(submitted) == expected


def test_acclimatization_and_time_zone_cases(truth, submitted):
    """Pairs whose answer depends on acclimatization state and on reading Table A/B on the
    correct local clock (including the US DST change) are classified correctly."""
    bad = _mismatches(truth, submitted, TRAPS["time_zones_and_acclimatization"])
    assert not bad, f"wrong legality (pilot, trip, correct): {bad}"


def test_reserve_and_rest_cases(truth, submitted):
    """Pairs decided by the reserve-plus-FDP cap, the 10 h pre-reserve rest, or the
    30-hours-free-in-168 rule (applied before both the reserve period and the FDP)."""
    bad = _mismatches(truth, submitted, TRAPS["reserve_and_rest"])
    assert not bad, f"wrong legality (pilot, trip, correct): {bad}"


def test_cumulative_limit_cases(truth, submitted):
    """Pairs decided by the 60 h/168 h, 190 h/672 h FDP and 100 h/672 h flight-time
    look-backs, where only FDP time counts and duty straddling the window is pro-rated."""
    bad = _mismatches(truth, submitted, TRAPS["cumulative_limits"])
    assert not bad, f"wrong legality (pilot, trip, correct): {bad}"


def test_flight_time_limit_cases(truth, submitted):
    """Pairs decided by the Table A flight-time limit."""
    bad = _mismatches(truth, submitted, TRAPS["flight_time_limit"])
    assert not bad, f"wrong legality (pilot, trip, correct): {bad}"


def test_full_legality_matrix(truth, submitted):
    """Every pilot x trip legality value matches the independently computed Part 117 answer."""
    bad = _mismatches(truth, submitted, sorted(truth))
    assert not bad, f"{len(bad)} wrong pairs, e.g. {bad[:10]}"


def test_assignment_ids_and_uniqueness(data, plan):
    """Assignments reference real pilots and trips; no pilot or trip is used twice."""
    _, pairs = plan
    pilots = [p for p, _ in pairs]
    trips = [t for _, t in pairs]
    assert all(p in data.pilots for p in pilots)
    assert all(t in data.trips for t in trips)
    assert len(set(pilots)) == len(pilots), "a pilot is assigned more than once"
    assert len(set(trips)) == len(trips), "a trip is assigned more than once"


def test_every_assignment_is_legal(truth, plan):
    """Each assigned pilot is legal for the trip under the verifier's own Part 117 check
    (the agent's legality.csv is not trusted for this)."""
    _, pairs = plan
    illegal = [pt for pt in pairs if not truth.get(pt, False)]
    assert not illegal, f"illegal assignments: {illegal}"


def test_coverage_is_maximum(data, truth, plan):
    """The plan covers as many open trips as any legal one-trip-per-reserve plan can."""
    _, pairs = plan
    best, _ = engine.optimum(data, truth)
    assert len(pairs) == best, f"covered {len(pairs)} trips, maximum is {best}"


def test_callout_cost_is_minimum_at_maximum_coverage(data, truth, plan):
    """Among maximum-coverage plans, the total call-out cost is the minimum possible."""
    _, pairs = plan
    _, best_cost = engine.optimum(data, truth)
    cost = sum(data.pilots[p]["cost"] for p, _ in pairs if p in data.pilots)
    assert cost == best_cost, f"cost {cost}, minimum is {best_cost}"


def test_reported_totals_match_assignments(data, plan):
    """trips_covered and total_callout_cost agree with the listed assignments."""
    doc, pairs = plan
    assert doc.get("trips_covered") == len(pairs)
    assert doc.get("total_callout_cost") == sum(data.pilots[p]["cost"] for p, _ in pairs if p in data.pilots)
