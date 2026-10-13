#!/usr/bin/env python3
"""Reference solution: placards and segregation for hazmat trailers (49 CFR 172 subpart F, 177.848)."""
import csv
import json
from collections import defaultdict
from itertools import combinations
from pathlib import Path

DATA = Path("/app/data")
OUT = Path("/app/output")

TABLE1 = {"1.1": "EXPLOSIVES 1.1", "1.2": "EXPLOSIVES 1.2", "1.3": "EXPLOSIVES 1.3", "2.3": "POISON GAS",
          "4.3": "DANGEROUS WHEN WET"}
TABLE2 = {"1.4": "EXPLOSIVES 1.4", "1.5": "EXPLOSIVES 1.5", "1.6": "EXPLOSIVES 1.6", "2.1": "FLAMMABLE GAS",
          "2.2": "NON-FLAMMABLE GAS", "3": "FLAMMABLE", "4.1": "FLAMMABLE SOLID",
          "4.2": "SPONTANEOUSLY COMBUSTIBLE", "5.1": "OXIDIZER", "5.2": "ORGANIC PEROXIDE", "6.1": "POISON",
          "8": "CORROSIVE", "9": "CLASS 9"}

# 177.848(d) segregation table (symmetric); keys as in the table's columns
COLS = ["1.1/1.2", "1.3", "1.4", "1.5", "1.6", "2.1", "2.2", "2.3A", "2.3B", "3", "4.1", "4.2", "4.3", "5.1",
        "5.2", "6.1A", "7", "8L"]
ROWS = {
    "1.1/1.2": "*****XXXXXXXXXXXXX", "1.3": "*****X.XXX.XXXXX.X", "1.4": "*****O.OOO.O...O.O",
    "1.5": "*****XXXXXXXXXXXXX", "1.6": "*****.............", "2.1": "XXOX...XO......OO.",
    "2.2": "X..X..............", "2.3A": "XXOX.X...XXXXXX..X", "2.3B": "XXOX.O...OOOOOO..O",
    "3": "XXOX...XO....O.X..", "4.1": "X..X...XO......X.O", "4.2": "XXOX...XO......X.X",
    "4.3": "XX.X...XO......X.O", "5.1": "XX.X...XOO.....X.O", "5.2": "XX.X...XO......X.O",
    "6.1A": "XXOX.O...XXXXXX..X", "7": "X..X.O............", "8L": "XXOX...XO.OXOOOX..",
}
NOTE_A = {"1.1/1.2", "1.5", "5.1"}
GROUPS = "ABCDEFGHJKLNS"
COMPAT = {  # 177.848(f)
    "A": ".XXXXXXXXXXXX", "B": "X.XqXXXXXXXXf", "C": "XX.22X6XXXX3f", "D": "XX2.2X6XXXX3f",
    "E": "XX22.X6XXXX3f", "F": "XXXXX.XXXXXXf", "G": "XX666X.XXXXXf", "H": "XXXXXXX.XXXXf",
    "J": "XXXXXXXX.XXXf", "K": "XXXXXXXXX.XXf", "L": "XXXXXXXXXX1XX", "N": "XX333XXXXXX.f",
    "S": "XfffffffffXf.",
}


def seg_key(cls, p):
    if cls in ("1.1", "1.2"):
        return "1.1/1.2"
    if cls in ("1.3", "1.4", "1.5", "1.6", "2.1", "2.2", "3", "4.1", "4.2", "4.3", "5.1", "5.2", "7"):
        return cls
    if cls == "2.3":
        return {"A": "2.3A", "B": "2.3B"}.get(p["poison_inhalation_hazard_zone"])
    if cls == "6.1":
        ok = p["physical_state"] == "liquid" and p["packing_group"] == "I" and p["poison_inhalation_hazard_zone"] == "A"
        return "6.1A" if ok else None
    if cls == "8":
        return "8L" if p["physical_state"] == "liquid" else None
    return None


def cell(a, b):
    return ROWS[a][COLS.index(b)]


def explosives_clash(p, q, trailer):
    ga, gb = p["explosive_compatibility_group"], q["explosive_compatibility_group"]
    c = COMPAT[ga][GROUPS.index(gb)]
    if c in ".23":
        return False
    if c in "Xq":
        return True
    if c == "1":
        return p["un_number"] != q["un_number"]
    if c == "f":   # "4/5": detonators (none here) / 1.4S fireworks with 1.1 or 1.2
        s, other = (p, q) if ga == "S" else (q, p)
        return s["fireworks"] and s["hazard_class"] == "1.4" and other["hazard_class"] in ("1.1", "1.2")
    if c == "6":
        g = p if ga == "G" else q
        substances = any(x["explosive_form"] == "substance" for x in trailer["packages"]
                         if x["hazard_class"].startswith("1."))
        return g["fireworks"] or substances
    raise ValueError(c)


def violates(p, q, trailer):
    if not p["labels_required"] or not q["labels_required"]:
        return False                                        # 177.848(a)
    if (p["cyanide"] and q["acid"]) or (q["cyanide"] and p["acid"]):
        return True                                         # 177.848(c)
    same_class = p["hazard_class"].split(".")[0] == q["hazard_class"].split(".")[0]
    ka = [p["hazard_class"]] + ([] if same_class else p["subsidiary_hazards"])
    kb = [q["hazard_class"]] + ([] if same_class else q["subsidiary_hazards"])
    for ca in ka:
        for cb in kb:
            a, b = seg_key(ca, p), seg_key(cb, q)
            if a is None or b is None:
                continue
            c = cell(a, b)
            if c == "*":
                if explosives_clash(p, q, trailer):
                    return True
            elif c == "X":
                an = (a in NOTE_A and q.get("un_number") == "UN1942" and b == "5.1") or \
                     (b in NOTE_A and p.get("un_number") == "UN1942" and a == "5.1")
                if not an:
                    return True
            elif c == "O":
                if p["bay"] == q["bay"]:
                    return True
                pair = {a, b}
                if "8L" in pair and pair & {"4.1", "4.2", "4.3", "5.1", "5.2"} and abs(p["bay"] - q["bay"]) <= 1:
                    return True
    return False


def placards(trailer):
    req1, t2 = set(), []
    subsidiary_505 = set()
    for p in trailer["packages"]:
        cls = p["hazard_class"]
        if p["limited_quantity"] or cls == "combustible liquid":
            continue                                        # 172.500(b)
        pih = p["poison_inhalation_hazard_zone"] is not None
        is505 = pih or "4.3" in p["subsidiary_hazards"]
        if p["residue_only"] and not is505 and cls in TABLE2:
            continue                                        # 172.504(d)(1)
        if "4.3" in p["subsidiary_hazards"]:
            req1.add("DANGEROUS WHEN WET")                  # 172.505(c)
        if cls == "7":
            if p["radioactive_label"] == "YELLOW-III":
                req1.add("RADIOACTIVE")
        elif cls in TABLE1:
            req1.add(TABLE1[cls])
        elif cls == "6.1" and pih:
            req1.add("POISON INHALATION HAZARD")
        elif cls in TABLE2:
            t2.append(p)
            if is505:
                subsidiary_505.add(TABLE2[cls])
        if pih and cls != "2.3":
            req1.add("POISON INHALATION HAZARD")            # 172.505(a)
    total = sum(p["gross_weight_lb"] for p in t2)
    cats = {TABLE2[p["hazard_class"]] for p in t2} if total >= 1001 else set(subsidiary_505)   # 172.504(c)
    placed = req1 | cats
    # 172.504(f) exceptions
    expl = sorted(x for x in placed if x.startswith("EXPLOSIVES"))
    for x in expl[1:]:
        placed.discard(x)
    if "FLAMMABLE GAS" in placed:
        placed.discard("NON-FLAMMABLE GAS")
    if placed & {"EXPLOSIVES 1.1", "EXPLOSIVES 1.2", "EXPLOSIVES 1.5"}:
        placed.discard("OXIDIZER")
    if "POISON GAS" in placed:
        placed.discard("POISON INHALATION HAZARD")
    if placed & {"POISON GAS", "POISON INHALATION HAZARD"}:
        placed.discard("POISON")
    placed.discard("CLASS 9")
    # 172.504(b) DANGEROUS, used wherever permitted
    t2_shown = {x for x in placed if x in TABLE2.values()}
    if len(t2_shown) >= 2:
        per = defaultdict(int)
        for p in t2:
            per[(TABLE2[p["hazard_class"]], p["loaded_at"])] += p["gross_weight_lb"]
        forced = {c for (c, f), w in per.items() if w >= 2205} | subsidiary_505
        rest = t2_shown - forced
        if rest:
            placed -= rest
            placed.add("DANGEROUS")
    return placed


def main():
    trailers = json.loads((DATA / "trailers.json").read_text())
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "trailer_check.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["trailer_id", "placards", "segregation_violations"])
        for t in trailers:
            pl = ";".join(sorted(placards(t))) or "none"
            bad = sorted("+".join(sorted((p["package_id"], q["package_id"])))
                         for p, q in combinations(t["packages"], 2) if violates(p, q, t))
            w.writerow([t["trailer_id"], pl, ";".join(bad) or "none"])


if __name__ == "__main__":
    main()
