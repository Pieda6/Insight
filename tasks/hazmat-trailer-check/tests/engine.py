"""Verifier-side model of 49 CFR 172.500-172.505 placarding and 177.848 highway segregation, written
independently of the reference solution. Reads only the verifier's private copy of the inputs.
"""
import json
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"

# ---------------------------------------------------------------- placarding (172.504 tables)
ANY_QUANTITY = {"1.1": "EXPLOSIVES 1.1", "1.2": "EXPLOSIVES 1.2", "1.3": "EXPLOSIVES 1.3",
                "2.3": "POISON GAS", "4.3": "DANGEROUS WHEN WET"}
BY_WEIGHT = {"1.4": "EXPLOSIVES 1.4", "1.5": "EXPLOSIVES 1.5", "1.6": "EXPLOSIVES 1.6",
             "2.1": "FLAMMABLE GAS", "2.2": "NON-FLAMMABLE GAS", "3": "FLAMMABLE",
             "4.1": "FLAMMABLE SOLID", "4.2": "SPONTANEOUSLY COMBUSTIBLE", "5.1": "OXIDIZER",
             "5.2": "ORGANIC PEROXIDE", "6.1": "POISON", "8": "CORROSIVE", "9": "CLASS 9"}
THRESHOLD_LB, ONE_FACILITY_LB = 1001, 2205


def placard_set(packages):
    any_q, weighted, keep505 = set(), [], set()
    for p in packages:
        c = p["hazard_class"]
        excepted = p["limited_quantity"] or c == "combustible liquid"
        if excepted:
            continue
        inhalation = bool(p["poison_inhalation_hazard_zone"])
        wet_sub = "4.3" in p["subsidiary_hazards"]
        subject_505 = inhalation or wet_sub
        if p["residue_only"] and c in BY_WEIGHT and not subject_505:
            continue
        if wet_sub:
            any_q.add("DANGEROUS WHEN WET")
        if inhalation:
            any_q.add("POISON GAS" if c == "2.3" else "POISON INHALATION HAZARD")
        if c in ANY_QUANTITY:
            any_q.add(ANY_QUANTITY[c])
        elif c == "7":
            if p["radioactive_label"] == "YELLOW-III":
                any_q.add("RADIOACTIVE")
        elif c == "6.1" and inhalation:
            pass                                             # Table 1 entry already added
        elif c in BY_WEIGHT:
            weighted.append(p)
            if subject_505:
                keep505.add(BY_WEIGHT[c])
    weight = sum(p["gross_weight_lb"] for p in weighted)
    shown = set(any_q)
    if weight >= THRESHOLD_LB:
        shown |= {BY_WEIGHT[p["hazard_class"]] for p in weighted}
    else:
        shown |= keep505                                     # 172.504(c) not available to 172.505 materials
    # 172.504(f)
    explosives = [s for s in shown if s.startswith("EXPLOSIVES ")]
    if len(explosives) > 1:
        lowest = min(explosives, key=lambda s: float(s.split()[1]))
        shown -= set(explosives) - {lowest}
    if "FLAMMABLE GAS" in shown:
        shown.discard("NON-FLAMMABLE GAS")
    if {"EXPLOSIVES 1.1", "EXPLOSIVES 1.2", "EXPLOSIVES 1.5"} & shown:
        shown.discard("OXIDIZER")
    if "POISON GAS" in shown:
        shown.discard("POISON INHALATION HAZARD")
    if {"POISON GAS", "POISON INHALATION HAZARD"} & shown:
        shown.discard("POISON")
    shown.discard("CLASS 9")
    # 172.504(b): DANGEROUS in place of table 2 placards wherever permitted
    table2_now = shown & set(BY_WEIGHT.values())
    if len(table2_now) > 1:
        loaded = {}
        for p in weighted:
            key = (BY_WEIGHT[p["hazard_class"]], p["loaded_at"])
            loaded[key] = loaded.get(key, 0) + p["gross_weight_lb"]
        must = {cat for (cat, _), lb in loaded.items() if lb >= ONE_FACILITY_LB} | keep505
        swap = table2_now - must
        if swap:
            shown = (shown - swap) | {"DANGEROUS"}
    return shown


# ---------------------------------------------------------------- segregation (177.848)
HEAD = ("1.1/1.2 1.3 1.4 1.5 1.6 2.1 2.2 2.3A 2.3B 3 4.1 4.2 4.3 5.1 5.2 6.1A 7 8L").split()
TABLE = """
1.1/1.2 * * * * * X X X X X X X X X X X X X
1.3     * * * * * X - X X X - X X X X X - X
1.4     * * * * * O - O O O - O - - - O - O
1.5     * * * * * X X X X X X X X X X X X X
1.6     * * * * * - - - - - - - - - - - - -
2.1     X X O X - - - X O - - - - - - O O -
2.2     X - - X - - - - - - - - - - - - - -
2.3A    X X O X - X - - - X X X X X X - - X
2.3B    X X O X - O - - - O O O O O O - - O
3       X X O X - - - X O - - - - O - X - -
4.1     X - - X - - - X O - - - - - - X - O
4.2     X X O X - - - X O - - - - - - X - X
4.3     X X - X - - - X O - - - - - - X - O
5.1     X X - X - - - X O O - - - - - X - O
5.2     X X - X - - - X O - - - - - - X - O
6.1A    X X O X - O - - - X X X X X X - - X
7       X - - X - O - - - - - - - - - - - -
8L      X X O X - - - X O - O X O O O X - -
"""
SEG = {}
for line in TABLE.strip().splitlines():
    name, *marks = line.split()
    for col, m in zip(HEAD, marks):
        SEG[(name, col)] = m

COMPAT_ROWS = """
A - X X X X X X X X X X X X
B X - X X X X X X X X X X 45
C X X - 2 2 X 6 X X X X 3 45
D X X 2 - 2 X 6 X X X X 3 45
E X X 2 2 - X 6 X X X X 3 45
F X X X X X - X X X X X X 45
G X X 6 6 6 X - X X X X X 45
H X X X X X X X - X X X X 45
J X X X X X X X X - X X X 45
K X X X X X X X X X - X X 45
L X X X X X X X X X X 1 X X
N X X 3 3 3 X X X X X X - 45
S X 45 45 45 45 45 45 45 45 45 X 45 -
"""
CG = "A B C D E F G H J K L N S".split()
COMPAT = {}
for line in COMPAT_ROWS.strip().splitlines():
    g, *marks = line.split()
    for h, m in zip(CG, marks):
        COMPAT[(g, h)] = m

CLASS_4_5 = {"4.1", "4.2", "4.3", "5.1", "5.2"}


def column_for(division, p):
    if division in ("1.1", "1.2"):
        return "1.1/1.2"
    if division == "2.3":
        zone = p["poison_inhalation_hazard_zone"]
        return "2.3" + zone if zone in ("A", "B") else None
    if division == "6.1":
        if (p["physical_state"], p["packing_group"], p["poison_inhalation_hazard_zone"]) == ("liquid", "I", "A"):
            return "6.1A"
        return None
    if division == "8":
        return "8L" if p["physical_state"] == "liquid" else None
    return division if division in HEAD else None


def explosive_conflict(p, q, packages):
    mark = COMPAT[(p["explosive_compatibility_group"], q["explosive_compatibility_group"])]
    if mark in ("-", "2", "3"):
        return False
    if mark == "X":
        return True
    if mark == "1":
        return p["un_number"] != q["un_number"]
    if mark == "45":
        one_s = p if p["explosive_compatibility_group"] == "S" else q
        other = q if one_s is p else p
        return one_s["fireworks"] and other["hazard_class"] in ("1.1", "1.2")
    if mark == "6":
        g_item = p if p["explosive_compatibility_group"] == "G" else q
        has_substance = any(x["hazard_class"].startswith("1.") and x["explosive_form"] == "substance"
                            for x in packages)
        return g_item["fireworks"] or has_substance
    raise ValueError(mark)


def conflict(p, q, packages):
    if not (p["labels_required"] and q["labels_required"]):
        return False
    if (p["cyanide"] and q["acid"]) or (p["acid"] and q["cyanide"]):
        return True
    p_hz, q_hz = [p["hazard_class"]], [q["hazard_class"]]
    if p["hazard_class"].split(".")[0] != q["hazard_class"].split(".")[0]:
        p_hz += p["subsidiary_hazards"]
        q_hz += q["subsidiary_hazards"]
    for hp in p_hz:
        for hq in q_hz:
            cp, cq = column_for(hp, p), column_for(hq, q)
            if not cp or not cq:
                continue
            mark = SEG[(cp, cq)]
            if mark == "*" and explosive_conflict(p, q, packages):
                return True
            if mark == "X":
                ammonium_nitrate_ok = ({cp, cq} & {"1.1/1.2", "1.5"}) and (
                    (p["un_number"] == "UN1942" and cp == "5.1") or (q["un_number"] == "UN1942" and cq == "5.1"))
                if not ammonium_nitrate_ok:
                    return True
            if mark == "O":
                gap = abs(p["bay"] - q["bay"])
                if gap == 0:
                    return True
                if gap == 1 and (("8L" == cp and cq in CLASS_4_5) or ("8L" == cq and cp in CLASS_4_5)):
                    return True
    return False


def expected():
    trailers = json.loads((DATA / "trailers.json").read_text())
    out = {}
    for t in trailers:
        pk = t["packages"]
        pairs = []
        for i in range(len(pk)):
            for j in range(i + 1, len(pk)):
                if conflict(pk[i], pk[j], pk):
                    a, b = sorted((pk[i]["package_id"], pk[j]["package_id"]))
                    pairs.append(f"{a}+{b}")
        out[t["trailer_id"]] = {"placards": ";".join(sorted(placard_set(pk))) or "none",
                                "segregation_violations": ";".join(sorted(pairs)) or "none"}
    return out
