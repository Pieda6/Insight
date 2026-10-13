"""Verifier-side model of 49 CFR 172.500-172.505 placarding and 177.848 highway segregation, with
classification of house blends from lab data under 173.2a, 173.115-173.137, 173.150 and 172.402,
written independently of the reference solution. Reads only the verifier's private copy of the inputs.
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


def bulk(p):
    """171.8: liquid capacity over 450 L; solid net mass over 400 kg and capacity over 450 L;
    gas water capacity over 1000 lb."""
    state = p["physical_state"]
    if state == "liquid":
        return p["maximum_capacity_liters"] > 450
    if state == "solid":
        return p["maximum_net_mass_kg"] > 400 and p["maximum_capacity_liters"] > 450
    return p["water_capacity_lb"] is not None and p["water_capacity_lb"] > 1000


# ---------------------------------------------------------------- classification of house blends
# 173.2a(b) precedence of hazard table. Columns, then one line per row ("." blank, "x" impossible).
PREC_COLUMNS = ["4.2", "4.3", "5.1/I", "5.1/II", "5.1/III", "6.1/I/dermal", "6.1/I/oral", "6.1/II", "6.1/III",
                "8/I/liquid", "8/I/solid", "8/II/liquid", "8/II/solid", "8/III/liquid", "8/III/solid"]
PREC_ROWS = """
3/I               .   4.3 .   .   .   3   3   3   3   3   x   3   x   3   x
3/II              .   4.3 .   .   .   3   3   3   3   8   x   3   x   3   x
3/III             .   4.3 .   .   .   6.1 6.1 6.1 3p  8   x   8   x   3   x
4.1/II            4.2 4.3 5.1 4.1 4.1 6.1 6.1 4.1 4.1 x   8   x   4.1 x   4.1
4.1/III           4.2 4.3 5.1 4.1 4.1 6.1 6.1 6.1 4.1 x   8   x   8   x   4.1
4.2/II            .   4.3 5.1 4.2 4.2 6.1 6.1 4.2 4.2 8   8   4.2 4.2 4.2 4.2
4.2/III           .   4.3 5.1 5.1 4.2 6.1 6.1 6.1 4.2 8   8   8   8   4.2 4.2
4.3/I             .   .   5.1 4.3 4.3 6.1 4.3 4.3 4.3 4.3 4.3 4.3 4.3 4.3 4.3
4.3/II            .   .   5.1 4.3 4.3 6.1 4.3 4.3 4.3 8   8   4.3 4.3 4.3 4.3
4.3/III           .   .   5.1 5.1 4.3 6.1 6.1 6.1 4.3 8   8   8   8   4.3 4.3
5.1/I             .   .   .   .   .   5.1 5.1 5.1 5.1 5.1 5.1 5.1 5.1 5.1 5.1
5.1/II            .   .   .   .   .   6.1 5.1 5.1 5.1 8   8   5.1 5.1 5.1 5.1
5.1/III           .   .   .   .   .   6.1 6.1 6.1 5.1 8   8   8   8   5.1 5.1
6.1/I/dermal      .   .   .   .   .   .   .   .   .   8   6.1 6.1 6.1 6.1 6.1
6.1/I/oral        .   .   .   .   .   .   .   .   .   8   6.1 6.1 6.1 6.1 6.1
6.1/II/inhalation .   .   .   .   .   .   .   .   .   8   6.1 6.1 6.1 6.1 6.1
6.1/II/dermal     .   .   .   .   .   .   .   .   .   8   6.1 8   6.1 6.1 6.1
6.1/II/oral       .   .   .   .   .   .   .   .   .   8   8   8   6.1 6.1 6.1
6.1/III           .   .   .   .   .   .   .   .   .   8   8   8   8   8   8
"""
PREC = {}
for line in PREC_ROWS.strip().splitlines():
    rname, *vals = line.split()
    for cname, v in zip(PREC_COLUMNS, vals):
        if v != ".":
            PREC[(rname, cname)] = v
ROMAN = ["I", "II", "III"]


def _celsius(t):
    if t is None:
        return None
    if t["unit"] == "F":
        return (t["value"] - 32) * 5 / 9
    return t["value"]


def _band(x, cuts):
    """Packing group for a value against (I, II, III) upper limits, inclusive."""
    if x is None:
        return None
    for g, cut in zip(ROMAN, cuts):
        if x <= cut:
            return g
    return None


def gas_class(lab):
    if lab["aerosol"]:
        fl, hc = lab["aerosol"]["flammable_components_pct_mass"], lab["aerosol"]["heat_of_combustion_kj_g"]
        if fl >= 85 and hc >= 30:
            return ("2.1", [], None)
        if fl <= 1 and hc < 20:
            return ("2.2", [], None)
        raise ValueError("aerosol outside 173.115(l)(1)-(2)")
    g = lab["gas"]
    lc50 = g["lc50_ppm"]
    if lc50 is None and g["toxic_components"]:
        lc50 = 1.0 / sum(c["mole_fraction"] / c["lc50_ppm"] for c in g["toxic_components"])
    lo, hi = g["lower_flammable_limit_pct"], g["upper_flammable_limit_pct"]
    flam = lo is not None and (lo <= 13 or hi - lo >= 12)
    if lc50 is not None and lc50 <= 5000:
        zone = "A" if lc50 <= 200 else ("B" if lc50 <= 1000 else ("C" if lc50 <= 3000 else "D"))
        return ("2.3", ["2.1"] if flam else [], zone)
    if flam:
        return ("2.1", [], None)
    pr = g["gauge_pressure_20c"]
    kpa = pr["value"] * (6.894757 if pr["unit"] == "psig" else 1.0)
    if kpa >= 200 or g["liquefied"] or g["cryogenic"]:
        return ("2.2", ["5.1"] if g["oxidizing"] else [], None)
    return None


def _components_at_least(lab, flash_c, pct):
    comps = lab["components"] or []
    return bool(comps) and sum(c["volume_pct"] for c in comps if _celsius(c["flash_point"]) >= flash_c) >= pct


def liquid_flammability(p):
    """('3', pg, fp, elevated) / ('combustible',) / None for a liquid's flash point data alone."""
    lab = p["lab_data"]
    fp = _celsius(lab["flash_point"])
    if p["physical_state"] != "liquid" or fp is None:
        return None
    hot = _celsius(lab["transport_temperature"])
    above = hot is not None and hot >= fp
    elevated = lab["intentionally_heated"] and above and bulk(p) and fp >= 37.8
    if fp <= 60 or elevated:
        excluded = (not above and _components_at_least(lab, 60, 99)) or (fp > 35 and (
            lab["sustains_combustion"] is False
            or (lab["fire_point"] is not None and _celsius(lab["fire_point"]) > 100)
            or (lab["water_miscible"] and (lab["water_pct_mass"] or 0) > 90)))
        if not excluded:
            ibp = _celsius(lab["initial_boiling_point"])
            pg = "I" if ibp is not None and ibp <= 35 else ("II" if fp < 23 else "III")
            return ("3", pg, fp, elevated)
        return None
    if 60 < fp < 93 and lab["sustains_combustion"] is not False and not (not above and
                                                                      _components_at_least(lab, 93, 99)):
        return ("combustible",)
    return None


def toxicity(p):
    lab = p["lab_data"]
    by_route = {"oral": _band(lab["oral_ld50_mg_kg"], (5, 50, 300)),
                "dermal": _band(lab["dermal_ld50_mg_kg"], (50, 200, 1000))}
    dm = lab["dust_mist_lc50_mg_l"]
    dust = _band(dm["value"] * 4 if dm and dm["exposure_hours"] == 4 else (dm["value"] if dm else None),
                 (0.2, 2.0, 4.0))
    vapor, zone = None, None
    if p["physical_state"] == "liquid":
        lc50 = ratio = None
        if lab["toxic_vapor_components"]:
            cs = lab["toxic_vapor_components"]
            lc50 = 1.0 / sum(c["mole_fraction"] / c["vapor_lc50_ml_m3"] for c in cs)
            ratio = sum((c["mole_fraction"] * c["vapor_pressure_20c_kpa"] * 1e6 / 101.3) / c["vapor_lc50_ml_m3"]
                        for c in cs)
        elif lab["vapor_lc50_ml_m3"] and lab["vapor_pressure_20c"]:
            v = lab["vapor_lc50_ml_m3"]
            lc50 = v["value"] * 2 if v["exposure_hours"] == 4 else v["value"]
            vp = lab["vapor_pressure_20c"]
            kpa = vp["value"] if vp["unit"] == "kPa" else vp["value"] * 101.325 / 760
            ratio = (kpa * 1e6 / 101.3) / lc50
        if lc50 is not None:
            for g, z, r_min, lc_max in (("I", "A", 500, 200), ("I", "B", 10, 1000), ("II", None, 1, 3000),
                                        ("III", None, 0.2, 5000)):
                if ratio >= r_min and lc50 <= lc_max:
                    vapor, zone = g, z
                    break
    inh = [g for g in (dust, vapor) if g]
    by_route["inhalation"] = min(inh, key=ROMAN.index) if inh else None
    hits = {r: g for r, g in by_route.items() if g}
    if not hits:
        return None
    worst = min(hits.values(), key=ROMAN.index)
    routes = [r for r in hits if hits[r] == worst]
    assert len(routes) == 1, "tied routes"
    od = [hits[r] for r in ("oral", "dermal") if r in hits]
    return {"cls": "6.1", "pg": worst, "route": routes[0], "zone": zone if vapor == "I" else None,
            "dust": dust, "oral_dermal_worst": min(od, key=ROMAN.index) if od else None}


def corrosivity(p):
    lab = p["lab_data"]
    t = lab["skin_corrosion_oecd_404"]
    if t and t["irreversible_damage"]:
        m = t["exposure_minutes"]
        if m <= 3 and t["damage_observed_within"] == "60 minutes":
            return {"cls": "8", "pg": "I"}
        if m <= 60:
            return {"cls": "8", "pg": "II"}
        if m <= 240:
            return {"cls": "8", "pg": "III"}
    rates = lab["corrosion_rate_55c"]
    if rates and (p["physical_state"] == "liquid" or lab["may_liquefy_in_transport"]):
        def mm(r):
            return 0 if r is None else (r["value"] * 25.4 if r["unit"] == "in/yr" else r["value"])
        if mm(rates["steel"]) > 6.25 or mm(rates["aluminum"]) > 6.25:
            return {"cls": "8", "pg": "III"}
    return None


def _row_names(h, state):
    c, g = h["cls"], h["pg"]
    if c == "6.1":
        return [f"6.1/{g}/{h['route']}"] if g in ("I", "II") else ["6.1/III"]
    if c == "8":
        return []
    return [f"{c}/{g}"]


def _col_names(h, state):
    c, g = h["cls"], h["pg"]
    if c in ("4.2", "4.3"):
        return [c]
    if c == "6.1":
        return [f"6.1/I/{h['route']}"] if g == "I" else [f"6.1/{g}"]
    if c == "8":
        return [f"8/{g}/{state}"]
    if c == "5.1":
        return [f"5.1/{g}"]
    return []


def rank_two(a, b, state, pesticide):
    pair = {a["cls"], b["cls"]}
    if pair == {"6.1", "8"}:
        tox = a if a["cls"] == "6.1" else b
        cor = b if tox is a else a
        if tox["dust"] == "I":                                 # 173.2a(b) Note 2
            return tox if tox["oral_dermal_worst"] in ("I", "II") else cor
    for r, c in ((a, b), (b, a)):
        for rn in _row_names(r, state):
            for cn in _col_names(c, state):
                v = PREC.get((rn, cn))
                if v is None:
                    continue
                assert v != "x", "impossible combination"
                if v == "3p":
                    v = "6.1" if pesticide else "3"
                return r if v == r["cls"] else c
    raise AssertionError(f"precedence missing {a} {b}")


def classify(p):
    """Returns the package as the placard and segregation rules see it, or None if not regulated."""
    lab = p["lab_data"]
    if lab is None:
        return dict(p, labeled=bool(p["labels_required"]), seg_subs=list(p["subsidiary_hazards"]),
                    hexafluoride="uranium hexafluoride" in (p["proper_shipping_name"] or "").lower())
    base = dict(p, labeled=True, hexafluoride=False)
    if p["physical_state"] == "gas":
        g = gas_class(lab)
        if g is None:
            return None
        cls, subs, zone = g
        return dict(base, hazard_class=cls, subsidiary_hazards=subs, seg_subs=subs, packing_group=None,
                    poison_inhalation_hazard_zone=zone)
    flam = liquid_flammability(p)
    hazards = []
    if flam and flam[0] == "3":
        hazards.append({"cls": "3", "pg": flam[1], "fp": flam[2], "elevated": flam[3]})
    tox = toxicity(p)
    if tox:
        hazards.append(tox)
    cor = corrosivity(p)
    if cor:
        hazards.append(cor)
    for f in lab["other_findings"]:
        hazards.append({"cls": f["division"], "pg": f.get("packing_group"), "pyro": f.get("pyrophoric", False),
                        "self_reactive": f.get("self_reactive", False)})
    combustible = dict(base, hazard_class="combustible liquid", subsidiary_hazards=[], seg_subs=[],
                       packing_group="III", poison_inhalation_hazard_zone=None, labeled=False)
    if not hazards:
        return combustible if flam == ("combustible",) else None
    if len(hazards) == 1 and hazards[0]["cls"] == "3" and not hazards[0]["elevated"] and hazards[0]["fp"] >= 38:
        return combustible                                     # 173.120(b)(2), always taken by the carrier
    if tox and tox["zone"]:
        main = tox                                             # 173.2a(a)(5)
    elif any(h.get("pyro") for h in hazards):
        main = [h for h in hazards if h.get("pyro")][0]
    elif any(h.get("self_reactive") for h in hazards):
        main = [h for h in hazards if h.get("self_reactive")][0]
    elif len(hazards) == 1:
        main = hazards[0]
    else:
        assert len(hazards) == 2
        main = rank_two(hazards[0], hazards[1], p["physical_state"], lab["pesticide"])
    rest = [h for h in hazards if h is not main]
    seg_subs = [h["cls"] for h in rest]                       # every subsidiary hazard is labeled
    return dict(base, hazard_class=main["cls"], subsidiary_hazards=[h["cls"] for h in rest], seg_subs=seg_subs,
                packing_group=min((h["pg"] for h in hazards if h["pg"]), key=ROMAN.index),
                poison_inhalation_hazard_zone=tox["zone"] if (tox and tox["zone"]) else None)


def placard_set(packages):
    any_q, weighted, keep505, in_bulk = set(), [], set(), set()
    hexafluoride_lb = sum(p["gross_weight_lb"] for p in packages if p["hexafluoride"] and not p["limited_quantity"])
    for p in packages:
        c = p["hazard_class"]
        if p["limited_quantity"]:
            continue
        if c == "combustible liquid":
            if bulk(p):
                in_bulk.add("COMBUSTIBLE")
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
            if bulk(p):
                in_bulk.add(BY_WEIGHT[c])
            else:
                weighted.append(p)
            if subject_505:
                keep505.add(BY_WEIGHT[c])
    weight = sum(p["gross_weight_lb"] for p in weighted)
    shown = set(any_q)
    if weight >= THRESHOLD_LB:
        shown |= {BY_WEIGHT[p["hazard_class"]] for p in weighted}
    else:
        shown |= keep505                                     # 172.504(c) not available to 172.505 materials
    shown |= in_bulk                                         # nor to bulk packagings
    uf6 = hexafluoride_lb >= THRESHOLD_LB
    if uf6:
        shown |= {"CORROSIVE", "POISON"}                     # 172.505(b)
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
    if {"POISON GAS", "POISON INHALATION HAZARD"} & shown and not uf6:
        shown.discard("POISON")
    shown.discard("CLASS 9")
    # 172.504(b): DANGEROUS in place of table 2 placards wherever permitted
    table2_now = shown & {BY_WEIGHT[p["hazard_class"]] for p in weighted}     # non-bulk packages only
    if len(table2_now) > 1:
        loaded = {}
        for p in weighted:
            key = (BY_WEIGHT[p["hazard_class"]], p["loaded_at"])
            loaded[key] = loaded.get(key, 0) + p["gross_weight_lb"]
        must = {cat for (cat, _), lb in loaded.items() if lb >= ONE_FACILITY_LB} | keep505 | in_bulk
        if uf6:
            must |= {"CORROSIVE", "POISON"}
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
    if not (p["labeled"] and q["labeled"]):
        return False
    if (p["cyanide"] and q["acid"]) or (p["acid"] and q["cyanide"]):
        return True
    p_hz, q_hz = [p["hazard_class"]], [q["hazard_class"]]
    if p["hazard_class"].split(".")[0] != q["hazard_class"].split(".")[0]:
        p_hz += p["seg_subs"]                                  # labeled subsidiary hazards, 177.848(e)(6)
        q_hz += q["seg_subs"]
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
        pk = [c for c in map(classify, t["packages"]) if c is not None]
        pairs = []
        for i in range(len(pk)):
            for j in range(i + 1, len(pk)):
                if conflict(pk[i], pk[j], pk):
                    a, b = sorted((pk[i]["package_id"], pk[j]["package_id"]))
                    pairs.append(f"{a}+{b}")
        out[t["trailer_id"]] = {"placards": ";".join(sorted(placard_set(pk))) or "none",
                                "segregation_violations": ";".join(sorted(pairs)) or "none"}
    return out
