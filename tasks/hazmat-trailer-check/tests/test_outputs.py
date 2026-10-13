"""Verifier for hazmat-trailer-check.

Expected placards and segregation violations are recomputed by an independent model of
49 CFR 172.500-172.505 and 177.848 (engine.py) from the verifier's private copy of the inputs; the
engine is itself checked against hand-worked planted trailers (golden.json). No agent code runs.
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

OUT = Path("/app/output/trailer_check.csv")
HEADER = "trailer_id,placards,segregation_violations"
TAGS = json.loads((HERE / "case_tags.json").read_text())
GOLDEN = json.loads((HERE / "golden.json").read_text())
NAMES = {"EXPLOSIVES 1.1", "EXPLOSIVES 1.2", "EXPLOSIVES 1.3", "EXPLOSIVES 1.4", "EXPLOSIVES 1.5",
         "EXPLOSIVES 1.6", "POISON GAS", "DANGEROUS WHEN WET", "ORGANIC PEROXIDE", "POISON INHALATION HAZARD",
         "RADIOACTIVE", "FLAMMABLE GAS", "NON-FLAMMABLE GAS", "OXYGEN", "FLAMMABLE", "COMBUSTIBLE",
         "FLAMMABLE SOLID", "SPONTANEOUSLY COMBUSTIBLE", "OXIDIZER", "POISON", "CORROSIVE", "CLASS 9",
         "DANGEROUS"}

GROUPS = {
    "weight_threshold_and_excepted_materials": (["threshold"], "placards"),
    "any_quantity_placards": (["table1"], "placards"),
    "dangerous_placard_and_single_facility_rule": (["dangerous"], "placards"),
    "placard_exceptions": (["exceptions"], "placards"),
    "subsidiary_hazard_placards": (["subsidiary"], "placards"),
    "segregation_table": (["segregation"], "segregation_violations"),
    "explosives_placards_and_compatibility": (["explosives"], None),
}


@pytest.fixture(scope="module")
def truth():
    return engine.expected()


@pytest.fixture(scope="module")
def rows():
    assert OUT.is_file(), "missing /app/output/trailer_check.csv"
    lines = OUT.read_text().splitlines()
    assert lines and lines[0] == HEADER, f"header must be exactly {HEADER}"
    assert all(line.strip() for line in lines[1:]), "blank lines are not allowed"
    order, by_id = [], {}
    for r in csv.reader(lines[1:]):
        assert len(r) == 3, f"row must have 3 columns: {r}"
        order.append(r[0])
        by_id[r[0]] = {"placards": r[1], "segregation_violations": r[2]}
    return {"order": order, "by_id": by_id}


def _wrong(truth, rows, ids, field=None):
    fields = [field] if field else ["placards", "segregation_violations"]
    return [(t, f, rows["by_id"].get(t, {}).get(f), truth[t][f]) for t in sorted(ids) for f in fields
            if rows["by_id"].get(t, {}).get(f) != truth[t][f]]


def test_engine_matches_hand_worked_cases(truth):
    """The verifier's engine reproduces every hand-worked planted trailer."""
    bad = [(t, v, truth[t]) for t, v in GOLDEN.items() if truth[t] != v]
    assert not bad, bad[:5]


def test_one_row_per_trailer_in_input_order(rows):
    """Exactly one row per trailer, in the order of trailers.json."""
    order = [t["trailer_id"] for t in json.loads((engine.DATA / "trailers.json").read_text())]
    assert rows["order"] == order


def test_values_are_well_formed(rows):
    """Placard names from the regulation, sorted and ';'-joined (or none); violations as sorted id pairs."""
    for t, r in rows["by_id"].items():
        p = r["placards"]
        if p != "none":
            parts = p.split(";")
            assert set(parts) <= NAMES and parts == sorted(parts) and len(set(parts)) == len(parts), (t, p)
        v = r["segregation_violations"]
        if v != "none":
            parts = v.split(";")
            assert parts == sorted(parts) and len(set(parts)) == len(parts), (t, v)
            for pair in parts:
                m = re.fullmatch(r"(PK\d{4})\+(PK\d{4})", pair)
                assert m and m.group(1) < m.group(2), (t, pair)


def test_hand_worked_cases(rows):
    """Every hand-worked planted trailer has the right placards and violations."""
    bad = _wrong(dict(GOLDEN), rows, GOLDEN)
    assert not bad, f"{len(bad)} wrong (trailer, field, got, expected): {bad[:8]}"


@pytest.mark.parametrize("group", sorted(GROUPS))
def test_rule_family(truth, rows, group):
    """Every trailer planted for this rule family is right on the field the family decides."""
    tags, field = GROUPS[group]
    ids = [t for t, tg in TAGS.items() if set(tg) & set(tags)]
    assert ids
    bad = _wrong(truth, rows, ids, field)
    assert not bad, f"{len(bad)} wrong: {bad[:8]}"


def test_every_trailer(truth, rows):
    """Every row's placards and segregation violations match exactly."""
    bad = _wrong(truth, rows, truth.keys())
    assert not bad, f"{len(bad)} wrong: {bad[:8]}"
