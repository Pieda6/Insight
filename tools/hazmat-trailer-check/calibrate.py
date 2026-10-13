#!/usr/bin/env python3
"""Dev-only calibration for hazmat-trailer-check (never uploaded): oracle passes, empty output fails,
and each common misreading of the blend classification rules (49 CFR 173.2a, 173.115-173.137, 173.150,
172.402) and of 172.500-172.505 / 177.848 fails at least one test."""
import contextlib
import copy
import csv
import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TASK = ROOT / "tasks" / "hazmat-trailer-check"
OUT = Path("/app/output/trailer_check.csv")


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


S = load("solve", TASK / "solution" / "solve.py")
E = load("engine", TASK / "tests" / "engine.py")
O = {k: getattr(S, k) for k in ("placards", "violates", "seg_key", "explosives_clash", "cell", "is_bulk", "deg_c",
                                "class3_hazard", "combustible", "toxic_hazard", "corrosive_hazard", "classify_gas",
                                "precedence", "reclass_ok", "primary_hazard", "subsidiary_label_required",
                                "mixture_lc50", "gas_flammable", "vapor_kpa", "mm_per_year", "gauge_kpa",
                                "classify_blend", "pg_by")}


@contextlib.contextmanager
def patched(**kw):
    old = {k: getattr(S, k) for k in kw}
    for k, v in kw.items():
        setattr(S, k, v)
    try:
        yield
    finally:
        for k, v in old.items():
            setattr(S, k, v)


def tests():
    p = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                        str(TASK / "tests" / "test_outputs.py")], capture_output=True, text=True)
    return p.returncode, [ln.split("::", 1)[1].split(" ")[0] for ln in p.stdout.splitlines() if ln.startswith("FAILED")]


def with_trailer(fn):
    def pl(t):
        return O["placards"](fn(copy.deepcopy(t)))
    return pl


def heavier(t, lb=5000):
    """Placard every class present: pretend table 2 weight is always over the threshold."""
    if not t["packages"]:
        return t
    t["packages"].append({**t["packages"][0], "hazard_class": "9", "subsidiary_hazards": [],
                          "gross_weight_lb": lb, "limited_quantity": False, "residue_only": False,
                          "poison_inhalation_hazard_zone": None, "loaded_at": "__ghost__"})
    return t


def strict_threshold(t):
    w = sum(p["gross_weight_lb"] for p in t["packages"] if p["hazard_class"] in S.TABLE2
            and not p["limited_quantity"] and not p["residue_only"])
    if w == 1001:
        for p in t["packages"]:
            if p["hazard_class"] in S.TABLE2:
                p["gross_weight_lb"] -= 1
                break
    return t


def count_lq(t):
    for p in t["packages"]:
        p["limited_quantity"] = False
    return t


def count_combustible(t):
    for p in t["packages"]:
        if p["hazard_class"] == "combustible liquid":
            p["hazard_class"] = "3"
    return t


def count_residue(t):
    for p in t["packages"]:
        p["residue_only"] = False
    return t


def never_dangerous(t):
    res = O["placards"](t)
    if "DANGEROUS" not in res:
        return res
    with patched(placards=O["placards"]):
        pass
    full = set()
    for p in t["packages"]:
        if p["limited_quantity"] or p["hazard_class"] == "combustible liquid" or p["residue_only"]:
            continue
        if p["hazard_class"] in S.TABLE2 and p["hazard_class"] != "9":
            full.add(S.TABLE2[p["hazard_class"]])
    return (res - {"DANGEROUS"}) | full


def dangerous_no_facility_rule(t):
    t = copy.deepcopy(t)
    for i, p in enumerate(t["packages"]):
        p["loaded_at"] = f"f{i}"
    return O["placards"](t)


def facility_summed(t):
    t = copy.deepcopy(t)
    for p in t["packages"]:
        p["loaded_at"] = "one"
    return O["placards"](t)


def all_subsidiaries(t):
    res = O["placards"](t)
    for p in t["packages"]:
        if p["labeled"]:
            for s in p["subsidiary_hazards"]:
                res.add(S.TABLE1.get(s) or S.TABLE2.get(s))
    res.discard(None)
    res.discard("CLASS 9")
    return res


def no_505(t):
    t = copy.deepcopy(t)
    for p in t["packages"]:
        if p["hazard_class"] != "6.1" and p["hazard_class"] != "2.3":
            p["poison_inhalation_hazard_zone"] = None
            p["subsidiary_hazards"] = [s for s in p["subsidiary_hazards"] if s != "4.3"]
    return O["placards"](t)


def any_radioactive(t):
    t = copy.deepcopy(t)
    for p in t["packages"]:
        if p["hazard_class"] == "7":
            p["radioactive_label"] = "YELLOW-III"
    return O["placards"](t)


def no_exceptions(t):
    res = O["placards"](t)
    for p in t["packages"]:
        if p["limited_quantity"] or p["hazard_class"] == "combustible liquid":
            continue
        c = p["hazard_class"]
        if c in S.TABLE1:
            res.add(S.TABLE1[c])
        if c == "6.1" and p["poison_inhalation_hazard_zone"]:
            res.add("POISON INHALATION HAZARD")
    return res


def class9_shown(t):
    res = O["placards"](t)
    w = sum(p["gross_weight_lb"] for p in t["packages"] if p["hazard_class"] in S.TABLE2
            and not p["limited_quantity"] and not p["residue_only"])
    if w >= 1001 and any(p["hazard_class"] == "9" for p in t["packages"]):
        res.add("CLASS 9")
    return res


def seg(**flags):
    def v(p, q, t):
        p, q = dict(p), dict(q)
        if flags.get("no_subs"):
            p["labeled_subs"], q["labeled_subs"] = [], []
        if flags.get("unlabeled"):
            p["labeled"] = q["labeled"] = True
        if flags.get("no_cyanide"):
            p["cyanide"] = q["cyanide"] = False
        if flags.get("no_same_class") and p["hazard_class"].split(".")[0] == q["hazard_class"].split(".")[0]:
            p["hazard_class"], q["hazard_class"] = p["hazard_class"] + "", q["hazard_class"] + ""
            res = False
            for a in [p["hazard_class"]] + p["labeled_subs"]:
                for b in [q["hazard_class"]] + q["labeled_subs"]:
                    ka, kb = S.seg_key(a, p), S.seg_key(b, q)
                    if ka and kb and S.cell(ka, kb) == "O" and p["bay"] == q["bay"]:
                        res = True
            return res or O["violates"](p, q, t)
        return O["violates"](p, q, t)
    return v


def cell_variant(mode):
    def c(a, b):
        x = O["cell"](a, b)
        if mode == "o_as_x" and x == "O":
            return "X"
        if mode == "o_blank" and x == "O":
            return "."
        return x
    return c


def no_adjacent(p, q, t):
    if p["bay"] != q["bay"]:
        pp, qq = dict(p), dict(q)
        qq["bay"] = p["bay"] + 5
        return O["violates"](pp, qq, t)
    return O["violates"](p, q, t)


def zones_all_a(cls, p):
    if cls == "2.3":
        return "2.3A"
    if cls == "6.1":
        return "6.1A" if p["physical_state"] == "liquid" and p["packing_group"] == "I" else None
    return O["seg_key"](cls, p)


def solids_count(cls, p):
    if cls == "8":
        return "8L"
    return O["seg_key"](cls, p)


def no_bulk(p):
    return False


def ibc_is_bulk(p):
    return "bulk container" in p["packaging_type"] or O["is_bulk"](p)


def solid_or_rule(p):
    if p["physical_state"] == "solid":
        return p["maximum_net_mass_kg"] > 400 or p["maximum_capacity_liters"] > 450
    return O["is_bulk"](p)


def inclusive_450(p):
    if p["physical_state"] == "liquid":
        return p["maximum_capacity_liters"] >= 450
    return O["is_bulk"](p)


def no_uf6(t):
    t = copy.deepcopy(t)
    for p in t["packages"]:
        p["uf6"] = False
    return O["placards"](t)


def bulk_under_dangerous(t):
    res = O["placards"](t)
    nb = [p for p in t["packages"] if not p["limited_quantity"] and p["hazard_class"] in S.TABLE2]
    cats = {S.TABLE2[p["hazard_class"]] for p in nb}
    bulk_cats = {S.TABLE2[p["hazard_class"]] for p in nb if O["is_bulk"](p)}
    if "DANGEROUS" in res and bulk_cats:
        res -= bulk_cats
    return res


SHORTCUTS = {
    "every packaging treated as non-bulk": dict(is_bulk=no_bulk),
    "every IBC treated as bulk": dict(is_bulk=ibc_is_bulk),
    "solid bulk if mass OR capacity exceeds the limit": dict(is_bulk=solid_or_rule),
    "450 L itself treated as bulk": dict(is_bulk=inclusive_450),
    "uranium hexafluoride rule ignored": dict(placards=no_uf6),
    "DANGEROUS also covers bulk packagings": dict(placards=bulk_under_dangerous),
    "placard every class present (no weight threshold)": dict(placards=with_trailer(heavier)),
    "1,001 lb itself treated as under the threshold": dict(placards=with_trailer(strict_threshold)),
    "limited quantities counted": dict(placards=with_trailer(count_lq)),
    "non-bulk combustible liquid counted as flammable": dict(placards=with_trailer(count_combustible)),
    "residue-only packages counted": dict(placards=with_trailer(count_residue)),
    "never use DANGEROUS": dict(placards=never_dangerous),
    "DANGEROUS without the single-facility rule": dict(placards=dangerous_no_facility_rule),
    "single-facility weight summed across facilities": dict(placards=facility_summed),
    "every subsidiary hazard placarded": dict(placards=all_subsidiaries),
    "no 172.505 subsidiary placards": dict(placards=no_505),
    "RADIOACTIVE for any label": dict(placards=any_radioactive),
    "no 172.504(f) exceptions": dict(placards=no_exceptions),
    "CLASS 9 placard shown": dict(placards=class9_shown),
    "segregation ignores subsidiary hazards": dict(violates=seg(no_subs=True)),
    "segregation applied to unlabeled packages": dict(violates=seg(unlabeled=True)),
    "cyanide/acid rule ignored": dict(violates=seg(no_cyanide=True)),
    "same-class exemption not applied": dict(violates=seg(no_same_class=True)),
    "O treated as X": dict(cell=cell_variant("o_as_x")),
    "O treated as no restriction": dict(cell=cell_variant("o_blank")),
    "corrosive liquid adjacency ignored": dict(violates=no_adjacent),
    "every 2.3 and PG I 6.1 liquid treated as zone A": dict(seg_key=zones_all_a),
    "corrosive solids treated as liquids": dict(seg_key=solids_count),
    "explosives compatibility ignored": dict(explosives_clash=lambda p, q, t: False),
}


# ------------------------------------------------------------------ misreadings of the classification rules
def lab_wrap(fn_name, edit):
    """Run the original helper on an edited copy of the lab data."""
    def f(lab, *a):
        lab = copy.deepcopy(lab)
        edit(lab)
        return O[fn_name](lab, *a)
    return f


def strip(*keys):
    def e(lab):
        for k in keys:
            lab[k] = None if k != "water_miscible" else False
    return e


def fp35_inclusive(lab, p, bulk):
    r = O["class3_hazard"](lab, p, bulk)
    fp = S.deg_c(lab.get("flash_point")) if lab.get("flash_point") else None
    if r and fp == 35 and lab.get("sustains_combustion") is False:
        return None
    return r


def fp60_exclusive(lab, p, bulk):
    r = O["class3_hazard"](lab, p, bulk)
    if r and r["fp"] == 60 and not r["elevated"]:
        return None
    return r


def no_pg_i_by_boiling_point(lab, p, bulk):
    r = O["class3_hazard"](lab, p, bulk)
    if r and r["pg"] == "I":
        r["pg"] = "II" if r["fp"] < 23 else "III"
    return r


def elevated_ignored(lab, p, bulk):
    lab = dict(lab, intentionally_heated=False)
    return O["class3_hazard"](lab, p, bulk)


def elevated_any_packaging(lab, p, bulk):
    return O["class3_hazard"](lab, p, True)


def reclass_with_other_hazards(hz, f3):
    return f3 is not None and not f3["elevated"] and f3["fp"] >= 38


def no_vapor_conversion(lab, p):
    lab = copy.deepcopy(lab)
    for k in ("vapor_lc50_ml_m3", "dust_mist_lc50_mg_l"):
        if lab.get(k):
            lab[k]["exposure_hours"] = 1
    return O["toxic_hazard"](lab, p)


def zone_by_lc50_only(lab, p):
    r = O["toxic_hazard"](lab, p)
    if r and r["pih_zone"]:
        v = lab.get("vapor_lc50_ml_m3")
        lc = v["value"] * (2 if v["exposure_hours"] == 4 else 1) if v else S.mixture_lc50(
            [(c["mole_fraction"], c["vapor_lc50_ml_m3"]) for c in lab["toxic_vapor_components"]])
        r["pih_zone"] = "A" if lc <= 200 else "B"
    return r


def exclusive_ld50(value, limits):
    if value is not None and value in limits:
        value = value + 1e-9
    return O["pg_by"](value, limits)


def pg_from_first_route(lab, p):
    r = O["toxic_hazard"](lab, p)
    if r and lab.get("oral_ld50_mg_kg") is not None:
        g = O["pg_by"](lab["oral_ld50_mg_kg"], (5, 50, 300))
        if g:
            r["pg"], r["route"] = g, "oral"
    return r


def skin_three_minutes_exclusive(lab, p):
    r = O["corrosive_hazard"](lab, p)
    sk = lab.get("skin_corrosion_oecd_404")
    if r and sk and sk["irreversible_damage"] and sk["exposure_minutes"] == 3:
        r["pg"] = "II"
    return r


def skin_four_minutes_pg_i(lab, p):
    r = O["corrosive_hazard"](lab, p)
    sk = lab.get("skin_corrosion_oecd_404")
    if r and sk and sk["irreversible_damage"] and sk["exposure_minutes"] <= 5:
        r["pg"] = "I"
    return r


def corrosion_both_metals(lab, p):
    r = O["corrosive_hazard"](lab, p)
    rates = lab.get("corrosion_rate_55c")
    sk = lab.get("skin_corrosion_oecd_404")
    if r and rates and not (sk and sk["irreversible_damage"]):
        if min(S.mm_per_year(rates["steel"]), S.mm_per_year(rates["aluminum"])) <= 6.25:
            return None
    return r


def corrosion_solids_too(lab, p):
    return O["corrosive_hazard"](dict(lab, may_liquefy_in_transport=True), p)


def lower_number_wins(a, b, state, pesticide):
    return min((a, b), key=lambda h: float(h["class"]))


def precedence_no_note2(a, b, state, pesticide):
    if {a["class"], b["class"]} == {"6.1", "8"} and "I" in (a.get("dust_pg"), b.get("dust_pg")):
        return a if a["class"] == "6.1" else b          # PG I toxicity simply outranks
    return O["precedence"](a, b, state, pesticide)


def no_pesticide(a, b, state, pesticide):
    return O["precedence"](a, b, state, False)


def pih_not_first(hz, t, state, pesticide):
    if t and t["pih_zone"] and len(hz) == 2:
        proxy = dict(t, route="dermal")                  # read as a PG I 6.1 row of the table
        other = hz[1] if hz[0] is t else hz[0]
        return t if O["precedence"](proxy, other, state, pesticide) is proxy else other
    return O["primary_hazard"](hz, t, state, pesticide)


def pyrophoric_not_first(hz, t, state, pesticide):
    if any(h.get("pyrophoric") for h in hz) and len(hz) == 2 and not (t and t["pih_zone"]):
        return next(h for h in hz if not h.get("pyrophoric"))
    return O["primary_hazard"](hz, t, state, pesticide)


def gas_lfl_only(g):
    lo = g["lower_flammable_limit_pct"]
    return lo is not None and lo <= 13


def psig_as_kpa(t):
    return t["value"]


def mixture_most_toxic(parts):
    return min(lc for f, lc in parts)


def mmhg_as_kpa(t):
    return t["value"]


def inches_as_mm(t):
    return 0.0 if t is None else t["value"]


def fahrenheit_as_celsius(t):
    return None if t is None else t["value"]


def gas_no_2_1_subsidiary(lab):
    cls, subs, zone = O["classify_gas"](lab)
    return cls, [x for x in subs if x != "2.1"], zone


def gas_no_oxidizer(lab):
    cls, subs, zone = O["classify_gas"](lab)
    return cls, [x for x in subs if x != "5.1"], zone


def gas_no_pressure_test(lab):
    r = O["classify_gas"](lab)
    if r[0] is None:
        return "2.2", [], None
    return r


def aerosol_always_flammable(lab):
    if lab.get("aerosol"):
        return "2.1", [], None
    return O["classify_gas"](lab)


def blends_unregulated(p):
    return None


def blends_flammable(p):
    return "3", [], [], "II", None


BLEND_SHORTCUTS = {
    "blends ignored (only listed products checked)": dict(classify_blend=blends_unregulated),
    "every blend treated as Class 3": dict(classify_blend=blends_flammable),
    "Fahrenheit read as Celsius": dict(deg_c=fahrenheit_as_celsius),
    "173.120(a)(2) mixture exclusion ignored": dict(class3_hazard=lab_wrap("class3_hazard", strip("components"))),
    "173.120(a)(3) sustained combustion ignored": dict(class3_hazard=lab_wrap("class3_hazard",
                                                                              strip("sustains_combustion"))),
    "173.120(a)(4) fire point ignored": dict(class3_hazard=lab_wrap("class3_hazard", strip("fire_point"))),
    "173.120(a)(5) water-miscible solution ignored": dict(class3_hazard=lab_wrap("class3_hazard",
                                                                                 strip("water_miscible"))),
    "173.120(a)(3)-(5) applied at 35 C itself": dict(class3_hazard=fp35_inclusive),
    "60 C itself treated as not flammable": dict(class3_hazard=fp60_exclusive),
    "packing group I by boiling point ignored": dict(class3_hazard=no_pg_i_by_boiling_point),
    "elevated temperature liquids ignored": dict(class3_hazard=elevated_ignored),
    "elevated temperature applied to non-bulk": dict(class3_hazard=elevated_any_packaging),
    "173.150(f)(4) and 173.120(b)(3) ignored": dict(combustible=lab_wrap("combustible", strip(
        "components", "sustains_combustion"))),
    "no reclassing as combustible": dict(reclass_ok=lambda hz, f3: False),
    "reclassed although another hazard is present": dict(reclass_ok=reclass_with_other_hazards),
    "highway exception for Class 3 PG III subsidiary labels applied": dict(
        subsidiary_label_required=lambda h: not (h["class"] == "3" and h["pg"] == "III" and h["fp"] >= 38)),
    "subsidiary hazards of blends never labeled": dict(subsidiary_label_required=lambda h: False),
    "4-hour LC50 used without conversion": dict(toxic_hazard=no_vapor_conversion),
    "hazard zone from LC50 alone": dict(toxic_hazard=zone_by_lc50_only),
    "toxicity limits treated as exclusive": dict(pg_by=exclusive_ld50),
    "6.1 packing group from oral toxicity only": dict(toxic_hazard=pg_from_first_route),
    "mixture LC50 taken from the most toxic component": dict(mixture_lc50=mixture_most_toxic),
    "mmHg read as kPa": dict(vapor_kpa=mmhg_as_kpa),
    "3-minute exposure not packing group I": dict(corrosive_hazard=skin_three_minutes_exclusive),
    "packing group I up to 5 minutes": dict(corrosive_hazard=skin_four_minutes_pg_i),
    "corrosion must exceed the limit on both metals": dict(corrosive_hazard=corrosion_both_metals),
    "inches per year read as millimetres": dict(mm_per_year=inches_as_mm),
    "corrosion rate applied to every solid": dict(corrosive_hazard=corrosion_solids_too),
    "precedence: lower class number wins": dict(precedence=lower_number_wins),
    "173.2a Note 2 ignored": dict(precedence=precedence_no_note2),
    "pesticide footnote ignored": dict(precedence=no_pesticide),
    "poison inhalation hazard ranked by the table": dict(primary_hazard=pih_not_first),
    "pyrophoric ranked by the table": dict(primary_hazard=pyrophoric_not_first),
    "flammable gas by lower limit only": dict(gas_flammable=gas_lfl_only),
    "psig read as kPa": dict(gauge_kpa=psig_as_kpa),
    "every non-flammable non-toxic gas regulated": dict(classify_gas=gas_no_pressure_test),
    "2.3 gas flammable subsidiary ignored": dict(classify_gas=gas_no_2_1_subsidiary),
    "oxidizing gas subsidiary ignored": dict(classify_gas=gas_no_oxidizer),
    "every aerosol Division 2.1": dict(classify_gas=aerosol_always_flammable),
}


def main():
    Path("/app/data").mkdir(parents=True, exist_ok=True)
    for f in Path("/app/data").iterdir():
        f.unlink()
    for f in (TASK / "environment" / "data").iterdir():
        shutil.copy(f, Path("/app/data") / f.name)
    S.main()
    print("oracle", tests())
    truth = E.expected()
    OUT.unlink()
    print("nop rc", tests()[0])
    ok = True
    for name, patch in {**SHORTCUTS, **BLEND_SHORTCUTS}.items():
        with patched(**patch):
            S.main()
        got = {r["trailer_id"]: r for r in csv.DictReader(open(OUT))}
        wrong = sum(1 for t, v in truth.items() if got[t]["placards"] != v["placards"]
                    or got[t]["segregation_violations"] != v["segregation_violations"])
        rc, failed = tests()
        ok &= bool(rc)
        fams = [f.split("[")[1].rstrip("]") for f in failed if "family" in f]
        print(f"{'ok ' if rc else '!! PASSES'} {name:55s} wrong={wrong:3d} {fams}")
    S.main()
    print("ALL SHORTCUTS FAIL" if ok else "SOME SHORTCUT PASSES")


if __name__ == "__main__":
    main()
