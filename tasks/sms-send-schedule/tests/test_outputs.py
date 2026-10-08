"""Verifier for sms-send-schedule.

The expected corrected schedule is recomputed by an independent model of 47 CFR 64.1200
(engine.py) from the verifier's private copy of the inputs; the engine itself is checked against
hand-worked planted cases (golden.json). No agent code is executed.
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

OUT = Path("/app/output/send_schedule.csv")
TAGS = json.loads((HERE / "case_tags.json").read_text())
GOLDEN = json.loads((HERE / "golden.json").read_text())
HEADER = "message_id,decision,send_at"

GROUPS = {
    "calling_hours": ["calling-hours"],
    "recipient_time_zone": ["time-zone"],
    "daylight_saving_change": ["dst"],
    "not_a_telephone_solicitation": ["exempt-consent", "exempt-ebr"],
    "autodialer_written_consent": ["autodialer"],
    "written_consent_elements": ["consent-elements"],
    "revocation_replies": ["revocation"],
    "seller_do_not_call": ["seller-dnc"],
    "national_registry": ["national-dnc"],
    "business_relationship_windows": ["ebr"],
}


@pytest.fixture(scope="module")
def truth():
    return engine.expected()


@pytest.fixture(scope="module")
def rows():
    assert OUT.is_file(), "missing /app/output/send_schedule.csv"
    lines = OUT.read_text().splitlines()
    assert lines and lines[0] == HEADER, f"header must be exactly {HEADER}"
    assert all(line.strip() for line in lines[1:]), "blank lines are not allowed"
    out = []
    for r in csv.reader(lines[1:]):
        assert len(r) == 3, f"row must have 3 columns: {r}"
        out.append(r)
    return out


def _got(rows):
    return {r[0]: (r[1], r[2]) for r in rows}


def _wrong(truth, rows, ids):
    got = _got(rows)
    return [(m, got.get(m), truth[m]) for m in sorted(ids) if got.get(m) != truth[m]]


def test_engine_matches_hand_worked_cases(truth):
    """The verifier's engine reproduces every hand-worked planted case."""
    bad = [(m, tuple(v), truth[m]) for m, v in GOLDEN.items() if tuple(v) != truth[m]]
    assert not bad, bad[:5]


def test_one_row_per_message_in_input_order(rows):
    """Exactly one row per scheduled message, in the order of scheduled_messages.csv."""
    with open(engine.DATA / "scheduled_messages.csv", newline="") as fh:
        order = [r["message_id"] for r in csv.DictReader(fh)]
    assert [r[0] for r in rows] == order


def test_values_are_well_formed(rows):
    """decision is SEND/RESCHEDULE/BLOCK; send_at is YYYY-MM-DDTHH:MM:00Z, and blank only for BLOCK."""
    pat = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:00Z$")
    for mid, dec, at in rows:
        assert dec in ("SEND", "RESCHEDULE", "BLOCK"), (mid, dec)
        if dec == "BLOCK":
            assert at == "", (mid, at)
        else:
            assert pat.match(at), (mid, at)


def test_send_rows_keep_scheduled_time(rows):
    """A SEND row carries the message's own scheduled time; a RESCHEDULE row a later one."""
    with open(engine.DATA / "scheduled_messages.csv", newline="") as fh:
        sched = {r["message_id"]: r["scheduled_at"] for r in csv.DictReader(fh)}
    for mid, dec, at in rows:
        if dec == "SEND":
            assert at == sched[mid], (mid, at, sched[mid])
        if dec == "RESCHEDULE":
            assert at > sched[mid], (mid, at, sched[mid])


def test_hand_worked_cases(rows):
    """Every hand-worked planted case has the right decision and minute."""
    got = _got(rows)
    bad = [(m, got.get(m), tuple(v)) for m, v in GOLDEN.items() if got.get(m) != tuple(v)]
    assert not bad, f"{len(bad)} wrong (id, got, expected): {bad[:8]}"


@pytest.mark.parametrize("group", sorted(GROUPS))
def test_rule_family(truth, rows, group):
    """Every message planted for this rule family has the right decision and send time."""
    ids = [m for m, tags in TAGS.items() if any(t in GROUPS[group] for t in tags)]
    assert ids
    bad = _wrong(truth, rows, ids)
    assert not bad, f"{len(bad)} wrong (id, got, expected): {bad[:8]}"


def test_every_message(truth, rows):
    """Every row's decision and send time match the rule exactly."""
    bad = _wrong(truth, rows, truth.keys())
    assert not bad, f"{len(bad)} wrong (id, got, expected): {bad[:8]}"
