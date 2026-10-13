#!/usr/bin/env python3
"""Reference solution: classify house blends from lab data (49 CFR 173.2a, 173.115-173.137, 173.150,
172.402), then placards and segregation for hazmat trailers (49 CFR 172 subpart F, 177.848)."""
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
    if not p["labeled"] or not q["labeled"]:
        return False                                        # 177.848(a)
    if (p["cyanide"] and q["acid"]) or (q["cyanide"] and p["acid"]):
        return True                                         # 177.848(c)
    same_class = p["hazard_class"].split(".")[0] == q["hazard_class"].split(".")[0]
    ka = [p["hazard_class"]] + ([] if same_class else p["labeled_subs"])     # 177.848(e)(6)
    kb = [q["hazard_class"]] + ([] if same_class else q["labeled_subs"])
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


def is_bulk(p):
    """49 CFR 171.8 bulk packaging."""
    if p["physical_state"] == "gas":
        return (p["water_capacity_lb"] or 0) > 1000
    if p["physical_state"] == "liquid":
        return p["maximum_capacity_liters"] > 450
    return p["maximum_net_mass_kg"] > 400 and p["maximum_capacity_liters"] > 450


# ------------------------------------------------------------------ classification of house blends
# 173.2a(b) precedence of hazard table, as published (tab separated; "( 3)" impossible, blank not ranked)
PRECEDENCE_TEXT = """\
4.2\t4.3\t5.1 I\t5.1 II\t5.1 III\t6.1 I dermal\t6.1 I oral\t6.1 II\t6.1 III\t8 I liquid\t8 I solid\t8 II liquid\t8 II solid\t8 III liquid\t8 III solid
3 I\t\t4.3\t\t\t\t3\t3\t3\t3\t3\t( 3)\t3\t( 3)\t3\t( 3)
3 II\t\t4.3\t\t\t\t3\t3\t3\t3\t8\t( 3)\t3\t( 3)\t3\t( 3)
3 III\t\t4.3\t\t\t\t6.1\t6.1\t6.1\t3 4\t8\t( 3)\t8\t( 3)\t3\t( 3)
4.1 II\t4.2\t4.3\t5.1\t4.1\t4.1\t6.1\t6.1\t4.1\t4.1\t( 3)\t8\t( 3)\t4.1\t( 3)\t4.1
4.1 III\t4.2\t4.3\t5.1\t4.1\t4.1\t6.1\t6.1\t6.1\t4.1\t( 3)\t8\t( 3)\t8\t( 3)\t4.1
4.2 II\t\t4.3\t5.1\t4.2\t4.2\t6.1\t6.1\t4.2\t4.2\t8\t8\t4.2\t4.2\t4.2\t4.2
4.2 III\t\t4.3\t5.1\t5.1\t4.2\t6.1\t6.1\t6.1\t4.2\t8\t8\t8\t8\t4.2\t4.2
4.3 I\t\t\t5.1\t4.3\t4.3\t6.1\t4.3\t4.3\t4.3\t4.3\t4.3\t4.3\t4.3\t4.3\t4.3
4.3 II\t\t\t5.1\t4.3\t4.3\t6.1\t4.3\t4.3\t4.3\t8\t8\t4.3\t4.3\t4.3\t4.3
4.3 III\t\t\t5.1\t5.1\t4.3\t6.1\t6.1\t6.1\t4.3\t8\t8\t8\t8\t4.3\t4.3
5.1 I\t\t\t\t\t\t5.1\t5.1\t5.1\t5.1\t5.1\t5.1\t5.1\t5.1\t5.1\t5.1
5.1 II\t\t\t\t\t\t6.1\t5.1\t5.1\t5.1\t8\t8\t5.1\t5.1\t5.1\t5.1
5.1 III\t\t\t\t\t\t6.1\t6.1\t6.1\t5.1\t8\t8\t8\t8\t5.1\t5.1
6.1 I dermal\t\t\t\t\t\t\t\t\t\t8\t6.1\t6.1\t6.1\t6.1\t6.1
6.1 I oral\t\t\t\t\t\t\t\t\t\t8\t6.1\t6.1\t6.1\t6.1\t6.1
6.1 II inhalation\t\t\t\t\t\t\t\t\t\t8\t6.1\t6.1\t6.1\t6.1\t6.1
6.1 II dermal\t\t\t\t\t\t\t\t\t\t8\t6.1\t8\t6.1\t6.1\t6.1
6.1 II oral\t\t\t\t\t\t\t\t\t\t8\t8\t8\t6.1\t6.1\t6.1
6.1 III\t\t\t\t\t\t\t\t\t\t8\t8\t8\t8\t8\t8
"""
_lines = PRECEDENCE_TEXT.splitlines()
PREC_COLS = _lines[0].split("\t")
PRECEDENCE = {}
for _ln in _lines[1:]:
    _row, *_cells = _ln.split("\t")
    for _c, _v in zip(PREC_COLS, _cells):
        PRECEDENCE[(_row, _c)] = _v.strip()
PG_RANK = {"I": 1, "II": 2, "III": 3}


def deg_c(t):
    if t is None:
        return None
    return t["value"] if t["unit"] == "C" else (t["value"] - 32) * 5 / 9


def gauge_kpa(t):
    return t["value"] if t["unit"] == "kPa" else t["value"] * 6.894757


def vapor_kpa(t):
    return t["value"] if t["unit"] == "kPa" else t["value"] * 101.325 / 760


def mm_per_year(t):
    if t is None:
        return 0.0
    return t["value"] if t["unit"] == "mm/yr" else t["value"] * 25.4


def pg_by(value, limits):
    for pg, lim in zip(("I", "II", "III"), limits):
        if value is not None and value <= lim:
            return pg
    return None


def mixture_lc50(parts):
    """173.133(b)(1)(i): parts are (mole fraction, LC50)."""
    return 1 / sum(f / lc for f, lc in parts)


def gas_flammable(g):
    """173.115(a): ignitable at 13 percent or less, or a flammable range of at least 12 points."""
    lo, hi = g["lower_flammable_limit_pct"], g["upper_flammable_limit_pct"]
    return lo is not None and (lo <= 13 or hi - lo >= 12)


def classify_gas(lab):
    g = lab.get("gas")
    if lab.get("aerosol"):
        a = lab["aerosol"]
        if a["flammable_components_pct_mass"] >= 85 and a["heat_of_combustion_kj_g"] >= 30:
            return "2.1", [], None                           # 173.115(l)(1)
        if a["flammable_components_pct_mass"] <= 1 and a["heat_of_combustion_kj_g"] < 20:
            return "2.2", [], None                           # 173.115(l)(2)
        raise ValueError("aerosol needs UN tests")
    lc50 = g.get("lc50_ppm")
    if lc50 is None and g.get("toxic_components"):
        lc50 = mixture_lc50([(c["mole_fraction"], c["lc50_ppm"]) for c in g["toxic_components"]])
    flammable = gas_flammable(g)
    if lc50 is not None and lc50 <= 5000:                    # 173.115(c), 173.2a(a)(2)
        zone = "A" if lc50 <= 200 else "B" if lc50 <= 1000 else "C" if lc50 <= 3000 else "D"
        return "2.3", (["2.1"] if flammable else []), zone   # 172.402(g)(1)
    if flammable:
        return "2.1", [], None
    if gauge_kpa(g["gauge_pressure_20c"]) >= 200 or g["liquefied"] or g.get("cryogenic"):
        return "2.2", (["5.1"] if g.get("oxidizing") else []), None     # 172.402(f)
    return None, [], None


def class3_hazard(lab, p, bulk):
    if p["physical_state"] != "liquid" or lab.get("flash_point") is None:
        return None
    fp, ibp = deg_c(lab["flash_point"]), deg_c(lab.get("initial_boiling_point"))
    tt = deg_c(lab.get("transport_temperature"))
    at_or_above_fp = tt is not None and tt >= fp
    elevated = bool(lab.get("intentionally_heated")) and at_or_above_fp and bulk and fp >= 37.8
    if not (fp <= 60 or elevated):
        return None
    comps = lab.get("components") or []
    if comps and not at_or_above_fp and sum(c["volume_pct"] for c in comps if deg_c(c["flash_point"]) >= 60) >= 99:
        return None                                          # 173.120(a)(2)
    if fp > 35:
        if lab.get("sustains_combustion") is False:
            return None                                      # (a)(3)
        if lab.get("fire_point") is not None and deg_c(lab["fire_point"]) > 100:
            return None                                      # (a)(4)
        if lab.get("water_miscible") and (lab.get("water_pct_mass") or 0) > 90:
            return None                                      # (a)(5)
    if ibp is not None and ibp <= 35:
        pg = "I"
    elif fp < 23:
        pg = "II"
    else:
        pg = "III"
    return {"class": "3", "pg": pg, "fp": fp, "elevated": elevated}


def combustible(lab, p):
    if p["physical_state"] != "liquid" or lab.get("flash_point") is None:
        return False
    fp = deg_c(lab["flash_point"])
    if not 60 < fp < 93:
        return False
    if lab.get("sustains_combustion") is False:
        return False                                         # 173.120(b)(3)
    comps = lab.get("components") or []
    tt = deg_c(lab.get("transport_temperature"))
    if comps and not (tt is not None and tt >= fp) and \
            sum(c["volume_pct"] for c in comps if deg_c(c["flash_point"]) >= 93) >= 99:
        return False                                         # 173.150(f)(4)
    return True


def toxic_hazard(lab, p):
    routes = {}
    routes["oral"] = pg_by(lab.get("oral_ld50_mg_kg"), (5, 50, 300))
    routes["dermal"] = pg_by(lab.get("dermal_ld50_mg_kg"), (50, 200, 1000))
    dm = lab.get("dust_mist_lc50_mg_l")
    dust_pg = pg_by(dm["value"] * (4 if dm["exposure_hours"] == 4 else 1), (0.2, 2.0, 4.0)) if dm else None
    vap_pg, zone = None, None
    if p["physical_state"] == "liquid":
        comps = lab.get("toxic_vapor_components")
        vl = lab.get("vapor_lc50_ml_m3")
        if comps:
            lc50 = mixture_lc50([(c["mole_fraction"], c["vapor_lc50_ml_m3"]) for c in comps])
            ratio = sum(c["mole_fraction"] * c["vapor_pressure_20c_kpa"] * 1e6 / 101.3 / c["vapor_lc50_ml_m3"]
                        for c in comps)
        elif vl and lab.get("vapor_pressure_20c"):
            lc50 = vl["value"] * (2 if vl["exposure_hours"] == 4 else 1)
            ratio = vapor_kpa(lab["vapor_pressure_20c"]) * 1e6 / 101.3 / lc50
        else:
            lc50 = ratio = None
        if lc50 is not None:
            if ratio >= 500 and lc50 <= 200:
                vap_pg, zone = "I", "A"
            elif ratio >= 10 and lc50 <= 1000:
                vap_pg, zone = "I", "B"
            elif ratio >= 1 and lc50 <= 3000:
                vap_pg = "II"
            elif ratio >= 0.2 and lc50 <= 5000:
                vap_pg = "III"
    inh = [x for x in (dust_pg, vap_pg) if x]
    routes["inhalation"] = min(inh, key=PG_RANK.get) if inh else None
    found = {r: g for r, g in routes.items() if g}
    if not found:
        return None
    pg = min(found.values(), key=PG_RANK.get)
    route = [r for r, g in found.items() if g == pg]
    if len(route) != 1:
        raise ValueError("tied routes")
    return {"class": "6.1", "pg": pg, "route": route[0], "pih_zone": zone if vap_pg == "I" else None,
            "dust_pg": dust_pg, "oral_dermal": min([g for r, g in found.items() if r != "inhalation"] or ["IV"],
                                                   key=lambda x: PG_RANK.get(x, 4))}


def corrosive_hazard(lab, p):
    skin = lab.get("skin_corrosion_oecd_404")
    if skin and skin["irreversible_damage"]:
        m = skin["exposure_minutes"]                         # 173.137(a)-(c)(1)
        if m <= 3 and skin["damage_observed_within"] == "60 minutes":
            return {"class": "8", "pg": "I"}
        if m <= 60:
            return {"class": "8", "pg": "II"}
        if m <= 240:
            return {"class": "8", "pg": "III"}
    rates = lab.get("corrosion_rate_55c") or {}
    liquidish = p["physical_state"] == "liquid" or lab.get("may_liquefy_in_transport")
    if liquidish and max(mm_per_year(rates.get("steel")), mm_per_year(rates.get("aluminum"))) > 6.25:
        return {"class": "8", "pg": "III"}                   # 173.137(c)(2)
    return None


def prec_label(h, as_row, state):
    c, pg = h["class"], h["pg"]
    if c == "6.1":
        if pg == "III":
            return "6.1 III"
        if as_row:
            return f"6.1 {pg} {h['route']}"
        return "6.1 II" if pg == "II" else f"6.1 I {h['route']}"
    if c == "8":
        return f"8 {pg} {state}"
    if c in ("4.2", "4.3") and not as_row:
        return c
    return f"{c} {pg}"


def precedence(a, b, state, pesticide):
    if {a["class"], b["class"]} == {"6.1", "8"}:
        t = a if a["class"] == "6.1" else b
        if t["dust_pg"] == "I":                                          # 173.2a(b) Note 2
            return t if t["oral_dermal"] in ("I", "II") else (b if t is a else a)
    for row, col in ((a, b), (b, a)):
        key = (prec_label(row, True, state), prec_label(col, False, state))
        if key in PRECEDENCE and PRECEDENCE[key]:
            v = PRECEDENCE[key]
            if v == "( 3)":
                raise ValueError("impossible combination")
            if v == "3 4":
                v = "6.1" if pesticide else "3"
            return row if v == row["class"] else col
    raise ValueError(f"no precedence for {a} {b}")


def classify_blend(p):
    """(class, subsidiary hazards, labeled subsidiary hazards, PG, PIH zone), with class
    "combustible liquid" for a combustible liquid, or None when the blend is not regulated."""
    lab, bulk = p["lab_data"], is_bulk(p)
    if p["physical_state"] == "gas":
        cls, subs, zone = classify_gas(lab)
        if cls is None:
            return None
        return cls, subs, subs, None, zone
    findings = lab.get("other_findings") or []
    hz = []
    f3 = class3_hazard(lab, p, bulk)
    t = toxic_hazard(lab, p)
    c8 = corrosive_hazard(lab, p)
    for x in (f3, t, c8):
        if x:
            hz.append(x)
    for f in findings:
        hz.append({"class": f["division"], "pg": f.get("packing_group"), "pyrophoric": f.get("pyrophoric"),
                   "self_reactive": f.get("self_reactive")})
    if not hz:
        return ("combustible liquid", [], [], "III", None) if combustible(lab, p) else None
    if reclass_ok(hz, f3):
        return "combustible liquid", [], [], "III", None
    pih = bool(t and t["pih_zone"])
    primary = primary_hazard(hz, t, p["physical_state"], lab.get("pesticide"))
    others = [h for h in hz if h is not primary]
    pg = min([h["pg"] for h in hz if h.get("pg")], key=PG_RANK.get)          # Note 1
    subs = [h["class"] for h in others]
    labeled = [h["class"] for h in others if subsidiary_label_required(h)]
    return primary["class"], subs, labeled, pg, (t["pih_zone"] if pih and primary is t else None)


def reclass_ok(hz, f3):
    """173.120(b)(2): the carrier reclasses every flammable liquid it may as combustible."""
    return len(hz) == 1 and f3 is not None and not f3["elevated"] and f3["fp"] >= 38


def primary_hazard(hz, t, state, pesticide):
    if t and t["pih_zone"]:
        return t                                             # 173.2a(a)(5)
    if any(h.get("pyrophoric") for h in hz):
        return next(h for h in hz if h.get("pyrophoric"))    # (a)(6)
    if any(h.get("self_reactive") for h in hz):
        return next(h for h in hz if h.get("self_reactive"))  # (a)(7)
    if len(hz) == 1:
        return hz[0]
    if len(hz) == 2:
        return precedence(hz[0], hz[1], state, pesticide)    # (a)(8), (b)
    raise ValueError("more than two hazards")


def subsidiary_label_required(h):
    """Every subsidiary hazard of a house blend is labeled (its multi-hazard entry lists it)."""
    return True


def normalize(p):
    """One view of every package: listed products as recorded, house blends as classified."""
    if p.get("lab_data") is None:
        return {**p, "labeled": bool(p["labels_required"]), "labeled_subs": p["subsidiary_hazards"],
                "uf6": "uranium hexafluoride" in (p["proper_shipping_name"] or "").lower()}
    c = classify_blend(p)
    if c is None:
        return None
    cls, subs, labeled, pg, zone = c
    return {**p, "hazard_class": cls, "subsidiary_hazards": subs, "labeled_subs": labeled, "packing_group": pg,
            "poison_inhalation_hazard_zone": zone, "labeled": cls != "combustible liquid", "uf6": False}


def placards(trailer):
    req1, t2 = set(), []
    subsidiary_505 = set()
    bulk_forced = set()
    uf6 = 0
    for p in trailer["packages"]:
        cls = p["hazard_class"]
        if p["limited_quantity"]:
            continue                                        # 172.500(b)(2)
        if cls == "combustible liquid":
            if is_bulk(p):
                bulk_forced.add("COMBUSTIBLE")              # 172.500(b)(5) covers non-bulk only
            continue
        if p["uf6"]:
            uf6 += p["gross_weight_lb"]
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
            if is_bulk(p):
                bulk_forced.add(TABLE2[cls])                # 172.504(c) excludes bulk packagings
            else:
                t2.append(p)
            if is505:
                subsidiary_505.add(TABLE2[cls])
        if pih and cls != "2.3":
            req1.add("POISON INHALATION HAZARD")            # 172.505(a)
    total = sum(p["gross_weight_lb"] for p in t2)
    cats = {TABLE2[p["hazard_class"]] for p in t2} if total >= 1001 else set(subsidiary_505)   # 172.504(c)
    placed = req1 | cats | bulk_forced
    if uf6 >= 1001:
        placed |= {"CORROSIVE", "POISON"}                   # 172.505(b)
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
    if placed & {"POISON GAS", "POISON INHALATION HAZARD"} and uf6 < 1001:
        placed.discard("POISON")
    placed.discard("CLASS 9")
    # 172.504(b) DANGEROUS, used wherever permitted
    t2_shown = {TABLE2[p["hazard_class"]] for p in t2} & placed     # non-bulk categories only (172.504(b))
    if len(t2_shown) >= 2:
        per = defaultdict(int)
        for p in t2:
            per[(TABLE2[p["hazard_class"]], p["loaded_at"])] += p["gross_weight_lb"]
        forced = {c for (c, f), w in per.items() if w >= 2205} | subsidiary_505 | bulk_forced
        if uf6 >= 1001:
            forced |= {"CORROSIVE", "POISON"}
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
            t = {**t, "packages": [x for x in map(normalize, t["packages"]) if x is not None]}
            pl = ";".join(sorted(placards(t))) or "none"
            bad = sorted("+".join(sorted((p["package_id"], q["package_id"])))
                         for p, q in combinations(t["packages"], 2) if violates(p, q, t))
            w.writerow([t["trailer_id"], pl, ";".join(bad) or "none"])


if __name__ == "__main__":
    main()
