"""Verifier-side axle-load engine, written independently of the reference solution.

Axle loads are computed pallet by pallet from static equilibrium (moments about the
trailer tandem centre, then about the drive tandem centre), in exact fractions, from the
verifier's private copy of the inputs in /tests/data.
"""
import csv
from fractions import Fraction
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"


def _rows(name):
    with open(DATA / name, newline="") as f:
        return list(csv.DictReader(f))


def load():
    units = {r["unit_id"]: r for r in _rows("units.csv")}
    sliders = {r["slider_position_id"]: r for r in _rows("sliders.csv")}
    pallets = {r["pallet_id"]: (int(r["weight_lb"]), int(r["length_in"])) for r in _rows("pallets.csv")}
    return units, sliders, pallets


def axle_x(unit, slider):
    return [int(unit["steer_x_in"]), int(unit["drive1_x_in"]), int(unit["drive2_x_in"]),
            int(slider["trailer1_x_in"]), int(slider["trailer2_x_in"])]


def axle_loads(unit, slider, items):
    """Exact loads on axles 1..5 for items = [(weight, front_edge_in, length_in)]."""
    x = axle_x(unit, slider)
    kp = Fraction(int(unit["kingpin_x_in"]))
    drive_c = Fraction(x[1] + x[2], 2)
    trail_c = Fraction(x[3] + x[4], 2)
    steer = Fraction(x[0])
    trailer_tandem = Fraction(0)
    kingpin = Fraction(0)
    for w, front, length in items:
        cg = front + Fraction(length, 2)
        # Moments about the kingpin give the trailer tandem's share.
        share = Fraction(w) * (cg - kp) / (trail_c - kp)
        trailer_tandem += share
        kingpin += w - share
    drive = kingpin * (kp - steer) / (drive_c - steer)
    front_axle = kingpin - drive
    tare = [int(slider[k]) for k in ("tare_steer_lb", "tare_drive1_lb", "tare_drive2_lb",
                                     "tare_trailer1_lb", "tare_trailer2_lb")]
    return [tare[0] + front_axle, tare[1] + drive / 2, tare[2] + drive / 2,
            tare[3] + trailer_tandem / 2, tare[4] + trailer_tandem / 2]


def feet_half_up(inches):
    return (2 * inches + 12) // 24


def formula_limit(span_in, n):
    feet = feet_half_up(span_in)
    units_of_500 = Fraction(feet * n, n - 1) + 12 * n + 36
    return 500 * ((2 * units_of_500 + 1) // 2)


def violations(unit, slider, loads):
    """List of human-readable limit violations for one truck."""
    x = axle_x(unit, slider)
    out = []
    if loads[0] > 20000:
        out.append(f"steer axle {float(loads[0]):.1f} > 20000")
    for name, (i, j) in (("drive tandem", (1, 2)), ("trailer tandem", (3, 4))):
        if loads[i] + loads[j] > 34000:
            out.append(f"{name} {float(loads[i] + loads[j]):.1f} > 34000")
    if sum(loads) > 80000:
        out.append(f"gross {float(sum(loads)):.1f} > 80000")
    for i in range(5):
        for j in range(i + 1, 5):
            span = x[j] - x[i]
            lim = formula_limit(span, j - i + 1)
            if (i, j) == (1, 4) and feet_half_up(span) >= 36:
                lim = max(lim, 68000)
            grp = sum(loads[i:j + 1])
            if grp > lim:
                out.append(f"bridge axles {i + 1}-{j + 1} {float(grp):.1f} > {lim}")
    return out
