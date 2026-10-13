#!/usr/bin/env python3
"""Generate the hazmat-trailer-check inputs (dev only, never shipped).

One carrier's outbound trailers for a day. Each package record carries what the shipping papers and
labels say (UN number, class/division, subsidiary hazards, packing group, physical state, PIH zone,
labels required, limited quantity, residue only, radioactive label, explosive compatibility group,
article/substance, fireworks, cyanide, acid), its gross weight, the facility where it was loaded and
the trailer bay. Planted trailers carry a hand-worked expected answer (tests/golden.json).
"""
import importlib.util
import json
import random
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "tasks" / "hazmat-trailer-check"
ENV, TST = ROOT / "environment" / "data", ROOT / "tests" / "data"
rng = random.Random(177848)
_spec = importlib.util.spec_from_file_location("solve", ROOT / "solution" / "solve.py")
solve = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(solve)

# name, class, subsidiary, PG, state, extra
CAT = {
    "UN1263": ("Paint", "3", [], "II", "liquid", {}),
    "UN1993": ("Flammable liquid, n.o.s. (ethanol, toluene)", "3", [], "III", "liquid", {}),
    "UN1203": ("Gasoline", "3", [], "II", "liquid", {}),
    "UN1090": ("Acetone", "3", [], "II", "liquid", {}),
    "UN2924": ("Flammable liquid, corrosive, n.o.s.", "3", ["8"], "II", "liquid", {}),
    "UN1789": ("Hydrochloric acid", "8", [], "II", "liquid", {"acid": True}),
    "UN2796": ("Sulfuric acid (battery fluid)", "8", [], "II", "liquid", {"acid": True}),
    "UN1760": ("Corrosive liquid, n.o.s. (alkaline cleaner)", "8", [], "III", "liquid", {}),
    "UN1823": ("Sodium hydroxide, solid", "8", [], "II", "solid", {}),
    "UN3094": ("Corrosive liquid, water-reactive, n.o.s.", "8", ["4.3"], "II", "liquid", {}),
    "UN1744": ("Bromine", "8", ["6.1"], "I", "liquid", {"pih_zone": "A"}),
    "UN1950": ("Aerosols, flammable", "2.1", [], None, "gas", {}),
    "UN1075": ("Petroleum gases, liquefied", "2.1", [], None, "gas", {}),
    "UN1066": ("Nitrogen, compressed", "2.2", [], None, "gas", {}),
    "UN1013": ("Carbon dioxide", "2.2", [], None, "gas", {}),
    "UN1076": ("Phosgene", "2.3", ["8"], None, "gas", {"pih_zone": "A"}),
    "UN1062": ("Methyl bromide", "2.3", [], None, "gas", {"pih_zone": "C"}),
    "UN1428": ("Sodium", "4.3", [], "I", "solid", {}),
    "UN1402": ("Calcium carbide", "4.3", [], "I", "solid", {}),
    "UN1325": ("Flammable solid, organic, n.o.s.", "4.1", [], "II", "solid", {}),
    "UN1350": ("Sulfur", "4.1", [], "III", "solid", {}),
    "UN1376": ("Iron oxide, spent", "4.2", [], "III", "solid", {}),
    "UN1361": ("Carbon, animal or vegetable origin", "4.2", [], "II", "solid", {}),
    "UN1942": ("Ammonium nitrate", "5.1", [], "III", "solid", {"ammonium_nitrate": True}),
    "UN1479": ("Oxidizing solid, n.o.s.", "5.1", [], "II", "solid", {}),
    "UN2014": ("Hydrogen peroxide, aqueous solution", "5.1", ["8"], "II", "liquid", {}),
    "UN3107": ("Organic peroxide type E, liquid", "5.2", [], None, "liquid", {}),
    "UN3109": ("Organic peroxide type F, liquid", "5.2", [], None, "liquid", {}),
    "UN1710": ("Trichloroethylene", "6.1", [], "III", "liquid", {}),
    "UN2783": ("Organophosphorus pesticide, solid, toxic", "6.1", [], "III", "solid", {}),
    "UN3381": ("Toxic by inhalation liquid, n.o.s.", "6.1", [], "I", "liquid", {"pih_zone": "A"}),
    "UN3382": ("Toxic by inhalation liquid, n.o.s.", "6.1", [], "I", "liquid", {"pih_zone": "B"}),
    "UN1689": ("Sodium cyanide, solid", "6.1", [], "I", "solid", {"cyanide": True}),
    "UN1935": ("Cyanide solution, n.o.s.", "6.1", [], "II", "liquid", {"cyanide": True}),
    "UN2915": ("Radioactive material, Type A package", "7", [], None, "solid", {}),
    "UN3480": ("Lithium ion batteries", "9", [], "II", "solid", {}),
    "UN2978": ("Radioactive material, uranium hexafluoride, non fissile or fissile-excepted", "7", ["8"], None,
               "solid", {}),
    "UN3077": ("Environmentally hazardous substance, solid, n.o.s.", "9", [], "III", "solid", {}),
    "NA1993": ("Combustible liquid, n.o.s. (diesel fuel)", "combustible liquid", [], "III", "liquid", {}),
    "UN0336": ("Fireworks", "1.4", [], None, "solid", {"group": "G", "article": True, "fireworks": True}),
    "UN0335": ("Fireworks", "1.3", [], None, "solid", {"group": "G", "article": True, "fireworks": True}),
    "UN0337": ("Fireworks", "1.4", [], None, "solid", {"group": "S", "article": True, "fireworks": True}),
    "UN0012": ("Cartridges for weapons, inert projectile", "1.4", [], None, "solid",
               {"group": "S", "article": True}),
    "UN0191": ("Signal devices, hand", "1.4", [], None, "solid", {"group": "G", "article": True}),
    "UN0276": ("Cartridges, power device", "1.4", [], None, "solid", {"group": "C", "article": True}),
    "UN0027": ("Black powder", "1.1", [], None, "solid", {"group": "D", "article": False}),
    "UN0081": ("Explosive, blasting, type A", "1.1", [], None, "solid", {"group": "D", "article": False}),
    "UN0065": ("Cord, detonating, flexible", "1.1", [], None, "solid", {"group": "D", "article": True}),
    "UN0161": ("Powder, smokeless", "1.3", [], None, "solid", {"group": "C", "article": False}),
    "UN0331": ("Explosive, blasting, type B", "1.5", [], None, "solid", {"group": "D", "article": False}),
}
LABEL = {"1.1": "EXPLOSIVE 1.1", "1.3": "EXPLOSIVE 1.3", "1.4": "EXPLOSIVE 1.4", "1.5": "EXPLOSIVE 1.5",
         "2.1": "FLAMMABLE GAS", "2.2": "NONFLAMMABLE GAS", "2.3": "POISON GAS", "3": "FLAMMABLE LIQUID",
         "4.1": "FLAMMABLE SOLID", "4.2": "SPONTANEOUSLY COMBUSTIBLE", "4.3": "DANGEROUS WHEN WET",
         "5.1": "OXIDIZER", "5.2": "ORGANIC PEROXIDE", "6.1": "POISON", "7": "RADIOACTIVE",
         "8": "CORROSIVE", "9": "CLASS 9"}
FACILITIES = ["Columbus OH terminal", "Dayton OH shipper dock", "Lima OH shipper dock",
              "Springfield OH cross-dock"]
SHIPPERS = ["Buckeye Coatings", "Ohio Valley Chemical", "Midwest Pool Supply", "Allied Battery",
            "Lakeshore Ag Products", "Summit Fireworks Co.", "Great Lakes Industrial Gas",
            "Keystone Mining Supply", "Northstar Labs", "Tri-County Farm Co-op"]


DEFAULT_PACKAGING = {"liquid": ("steel drum", 208, None), "solid": ("fiberboard box", 60, None),
                     "gas": ("steel cylinder", 50, 110)}


def pkg(un, lb, bay, facility=0, lq=False, residue=False, rad=None, label_override=None, packaging=None,
        capacity_l=None, net_kg=None, water_lb=None):
    name, cls, sub, pg, state, extra = CAT[un]
    d_pack, d_cap, d_water = DEFAULT_PACKAGING[state]
    labels = [] if lq or cls == "combustible liquid" else (
        [f"RADIOACTIVE {rad}"] + [LABEL[x] for x in sub] if cls == "7" else [LABEL[cls]] + [LABEL[s] for s in sub])
    if cls.startswith("1.") and labels:
        labels = [labels[0] + extra["group"]]
    p = {"un_number": un, "proper_shipping_name": name, "hazard_class": cls, "subsidiary_hazards": sub,
         "packing_group": pg, "physical_state": state, "gross_weight_lb": lb,
         "limited_quantity": lq, "residue_only": residue, "labels_required": labels,
         "poison_inhalation_hazard_zone": extra.get("pih_zone"),
         "radioactive_label": f"{rad}" if cls == "7" else None,
         "explosive_compatibility_group": extra.get("group"),
         "explosive_form": ("article" if extra.get("article") else "substance") if "group" in extra else None,
         "fireworks": bool(extra.get("fireworks")), "cyanide": bool(extra.get("cyanide")),
         "acid": bool(extra.get("acid")), "loaded_at": FACILITIES[facility],
         "shipper": rng.choice(SHIPPERS), "bay": bay,
         "packaging_type": packaging or d_pack,
         "maximum_capacity_liters": capacity_l if capacity_l is not None else d_cap,
         "maximum_net_mass_kg": net_kg if net_kg is not None else max(1, round(lb * 0.4536 * 0.9)),
         "water_capacity_lb": (water_lb if water_lb is not None else d_water) if state == "gas" else None,
         "product_name": name, "lab_data": None, "_split": packaging is None}
    if label_override is not None:
        p["labels_required"] = label_override
    return p


def planted():
    """(tags, packages, expected placards, expected violating pairs as index pairs)."""
    P = pkg
    S = []
    # ---------------- table 2 threshold: < 1001 lb exempt, 1001 required -------------------
    S.append((["threshold"], [P("UN1263", 600, 1), P("UN1760", 400, 4)], [], []))
    S.append((["threshold"], [P("UN1263", 601, 1), P("UN1760", 400, 4)], ["DANGEROUS"], []))
    S.append((["threshold"], [P("UN1263", 1001, 2)], ["FLAMMABLE"], []))
    S.append((["threshold"], [P("UN1263", 1000, 2)], [], []))
    S.append((["threshold", "limited-quantity"], [P("UN1263", 700, 1), P("UN1950", 900, 3, lq=True)], [], []))
    S.append((["threshold", "combustible"], [P("UN1993", 500, 1), P("NA1993", 1600, 3)], [], []))
    S.append((["threshold", "residue"], [P("UN1203", 800, 1), P("UN1203", 450, 2, residue=True)], [], []))
    S.append((["threshold", "residue"], [P("UN1203", 800, 1), P("UN1203", 450, 2)], ["FLAMMABLE"], []))
    # ---------------- table 1 any quantity --------------------------------------------------
    S.append((["table1"], [P("UN1428", 40, 1)], ["DANGEROUS WHEN WET"], []))
    S.append((["table1"], [P("UN1062", 120, 1)], ["POISON GAS"], []))
    S.append((["table1"], [P("UN3382", 55, 1)], ["POISON INHALATION HAZARD"], []))
    S.append((["table1", "radioactive"], [P("UN2915", 60, 2, rad="YELLOW-III")], ["RADIOACTIVE"], []))
    S.append((["table1", "radioactive"], [P("UN2915", 60, 2, rad="YELLOW-II"), P("UN2915", 80, 3, rad="WHITE-I")],
              [], []))
    S.append((["table1", "threshold"], [P("UN1402", 300, 1), P("UN1263", 500, 4)], ["DANGEROUS WHEN WET"], []))
    S.append((["table1", "threshold"], [P("UN1402", 300, 1), P("UN1263", 1200, 4)],
              ["DANGEROUS WHEN WET", "FLAMMABLE"], []))
    # ---------------- DANGEROUS and the 2,205 lb single-facility rule --------------------------
    S.append((["dangerous"], [P("UN1263", 900, 1), P("UN1760", 700, 4), P("UN1066", 300, 6)], ["DANGEROUS"], []))
    S.append((["dangerous", "single-facility"],
              [P("UN1263", 2205, 1, 0), P("UN1760", 700, 4, 1), P("UN1013", 300, 7, 2)],
              ["DANGEROUS", "FLAMMABLE"], []))
    S.append((["dangerous", "single-facility"],
              [P("UN1263", 1200, 1, 0), P("UN1263", 1005, 2, 1), P("UN1760", 700, 4, 1), P("UN1013", 300, 7, 2)],
              ["DANGEROUS"], []))
    S.append((["dangerous", "single-facility"],
              [P("UN1263", 2204, 1, 0), P("UN1760", 700, 4, 1), P("UN1013", 300, 7, 2)], ["DANGEROUS"], []))
    S.append((["dangerous", "single-facility"],
              [P("UN1760", 1500, 1, 2), P("UN1760", 800, 2, 2), P("UN1263", 400, 5, 0), P("UN3109", 200, 8, 1)],
              ["CORROSIVE", "DANGEROUS"], []))
    S.append((["dangerous", "single-category"], [P("UN1263", 700, 1, 0), P("UN1263", 650, 3, 1)], ["FLAMMABLE"], []))
    # ---------------- placard exceptions in 172.504(f) -----------------------------------------
    S.append((["exceptions", "poison"], [P("UN1062", 100, 1), P("UN3382", 50, 5)], ["POISON GAS"], []))
    S.append((["exceptions", "poison"], [P("UN3382", 50, 1), P("UN1710", 1200, 5)], ["POISON INHALATION HAZARD"], []))
    S.append((["exceptions", "poison"], [P("UN1710", 1200, 5)], ["POISON"], []))
    S.append((["exceptions", "explosives"], [P("UN0335", 200, 1), P("UN0336", 1100, 3)], ["EXPLOSIVES 1.3"], []))
    S.append((["exceptions", "explosives"], [P("UN0336", 1100, 3)], ["EXPLOSIVES 1.4"], []))
    S.append((["exceptions", "explosives"], [P("UN0336", 900, 3)], [], []))
    S.append((["exceptions", "oxidizer", "note-a"], [P("UN0081", 500, 1), P("UN1942", 1500, 5)],
              ["EXPLOSIVES 1.1"], []))
    S.append((["exceptions", "oxidizer", "note-a"], [P("UN0331", 2300, 1, 0), P("UN1942", 1500, 5, 1)],
              ["EXPLOSIVES 1.5"], []))
    S.append((["exceptions", "gases"], [P("UN1075", 2300, 1, 0), P("UN1066", 400, 4, 1)], ["FLAMMABLE GAS"], []))
    S.append((["exceptions", "class9"], [P("UN3480", 3000, 1), P("UN3077", 1500, 4)], [], []))
    # ---------------- subsidiary placards (172.505) ---------------------------------------------
    S.append((["subsidiary"], [P("UN1744", 120, 2)], ["CORROSIVE", "POISON INHALATION HAZARD"], []))
    S.append((["subsidiary"], [P("UN3094", 150, 2)], ["CORROSIVE", "DANGEROUS WHEN WET"], []))
    S.append((["subsidiary"], [P("UN2924", 1400, 2)], ["FLAMMABLE"], []))
    S.append((["subsidiary"], [P("UN1076", 60, 2)], ["POISON GAS"], []))
    S.append((["subsidiary", "segregation"], [P("UN3094", 150, 2), P("UN1789", 300, 6)],
              ["CORROSIVE", "DANGEROUS WHEN WET"], []))
    # ---------------- segregation: table X and O, separation, notes -----------------------------
    S.append((["segregation", "x"], [P("UN1062", 100, 1), P("UN1263", 300, 7)], ["POISON GAS"], []))
    S.append((["segregation", "x"], [P("UN1076", 60, 1), P("UN1263", 300, 7)], ["POISON GAS"], [(0, 1)]))
    S.append((["segregation", "x"], [P("UN1361", 200, 1), P("UN1789", 300, 7)], [], [(0, 1)]))
    S.append((["segregation", "x"], [P("UN1361", 200, 1), P("UN1823", 300, 7)], [], []))
    S.append((["segregation", "o"], [P("UN1263", 300, 2), P("UN1479", 300, 5)], [], []))
    S.append((["segregation", "o"], [P("UN1263", 300, 2), P("UN1479", 300, 2)], [], [(0, 1)]))
    S.append((["segregation", "o", "corrosive-adjacent"], [P("UN1789", 300, 3), P("UN1479", 300, 4)], [],
              [(0, 1)]))
    S.append((["segregation", "o", "corrosive-adjacent"], [P("UN1789", 300, 3), P("UN1479", 300, 5)], [], []))
    S.append((["segregation", "o", "corrosive-adjacent"], [P("UN1823", 300, 3), P("UN1479", 300, 4)], [], []))
    S.append((["segregation", "o", "corrosive-adjacent"], [P("UN1789", 300, 6), P("UN1325", 200, 7)], [],
              [(0, 1)]))
    S.append((["segregation", "o"], [P("UN1789", 300, 6), P("UN1350", 200, 6)], [], [(0, 1)]))
    S.append((["segregation", "pih"], [P("UN3381", 40, 1), P("UN1263", 300, 8)], ["POISON INHALATION HAZARD"],
              [(0, 1)]))
    S.append((["segregation", "pih"], [P("UN3382", 40, 1), P("UN1263", 300, 8)], ["POISON INHALATION HAZARD"], []))
    S.append((["segregation", "cyanide"], [P("UN1689", 150, 1), P("UN1789", 300, 8)], [], [(0, 1)]))
    S.append((["segregation", "cyanide"], [P("UN1689", 150, 1), P("UN1760", 300, 8)], [], []))
    S.append((["segregation", "cyanide"], [P("UN1935", 150, 1), P("UN2796", 300, 8)], [], [(0, 1)]))
    S.append((["segregation", "subsidiary-hazard"], [P("UN2924", 300, 2), P("UN1361", 200, 7)], [], [(0, 1)]))
    S.append((["segregation", "subsidiary-hazard"], [P("UN2014", 300, 2), P("UN1350", 200, 3)], [], [(0, 1)]))
    S.append((["segregation", "subsidiary-hazard"], [P("UN2014", 300, 2), P("UN1350", 200, 6)], [], []))
    S.append((["segregation", "same-class"], [P("UN3094", 150, 2), P("UN1760", 300, 2)],
              ["CORROSIVE", "DANGEROUS WHEN WET"], []))
    S.append((["segregation", "unlabeled"], [P("UN1789", 300, 3, lq=True), P("UN1479", 300, 3)], [], []))
    S.append((["segregation", "unlabeled"], [P("UN1361", 200, 3), P("UN1789", 300, 3, lq=True)], [], []))
    S.append((["segregation", "radioactive"], [P("UN2915", 50, 1, rad="YELLOW-II"), P("UN1075", 300, 8)], [],
              []))
    S.append((["segregation", "radioactive"], [P("UN2915", 50, 1, rad="YELLOW-II"), P("UN1075", 300, 1)], [],
              [(0, 1)]))
    S.append((["segregation", "zone"], [P("UN1062", 100, 1), P("UN1428", 40, 8)], ["DANGEROUS WHEN WET",
                                                                                   "POISON GAS"], []))
    S.append((["segregation", "zone"], [P("UN1076", 60, 1), P("UN1428", 40, 8)], ["DANGEROUS WHEN WET",
                                                                                  "POISON GAS"], [(0, 1)]))
    # ---------------- explosives ----------------------------------------------------------------
    S.append((["explosives", "note-a"], [P("UN0027", 300, 1), P("UN1942", 900, 6)], ["EXPLOSIVES 1.1"], []))
    S.append((["explosives", "x"], [P("UN0027", 300, 1), P("UN1479", 300, 8)], ["EXPLOSIVES 1.1"], [(0, 1)]))
    S.append((["explosives", "o"], [P("UN0336", 500, 1), P("UN1263", 300, 1)], [], [(0, 1)]))
    S.append((["explosives", "o"], [P("UN0336", 500, 1), P("UN1263", 300, 5)], [], []))
    S.append((["explosives", "blank"], [P("UN0336", 500, 1), P("UN1350", 300, 1)], [], []))
    S.append((["explosives", "compat-2"], [P("UN0161", 200, 1), P("UN0065", 100, 2)], ["EXPLOSIVES 1.1"], []))
    S.append((["explosives", "compat-6"], [P("UN0191", 300, 1), P("UN0065", 100, 4), P("UN0276", 100, 6)],
              ["EXPLOSIVES 1.1"], []))
    S.append((["explosives", "compat-6"], [P("UN0191", 300, 1), P("UN0027", 100, 4)], ["EXPLOSIVES 1.1"],
              [(0, 1)]))
    S.append((["explosives", "compat-6"], [P("UN0336", 300, 1), P("UN0065", 100, 4)], ["EXPLOSIVES 1.1"],
              [(0, 1)]))
    S.append((["explosives", "compat-5"], [P("UN0337", 200, 1), P("UN0027", 100, 4)], ["EXPLOSIVES 1.1"],
              [(0, 1)]))
    S.append((["explosives", "compat-5"], [P("UN0012", 200, 1), P("UN0027", 100, 4)], ["EXPLOSIVES 1.1"], []))
    S.append((["explosives", "compat-x"], [P("UN0161", 200, 1), P("UN0336", 300, 4)], ["EXPLOSIVES 1.3"],
              [(0, 1)]))
    # ---------------- bulk packaging (171.8) -------------------------------------------------------
    IBC = dict(packaging="rigid intermediate bulk container", capacity_l=1040)
    S.append((["bulk"], [P("UN1760", 900, 3, **IBC, net_kg=380)], ["CORROSIVE"], []))
    S.append((["bulk"], [P("UN1760", 900, 3)], [], []))
    S.append((["bulk"], [P("UN1760", 950, 3, packaging="composite intermediate bulk container", capacity_l=450,
                           net_kg=420)], [], []))
    S.append((["bulk"], [P("UN1760", 950, 3, packaging="composite intermediate bulk container", capacity_l=460,
                           net_kg=420)], ["CORROSIVE"], []))
    S.append((["bulk", "dangerous"], [P("UN1350", 1984, 1, 1, packaging="flexible intermediate bulk container",
                                        capacity_l=1000, net_kg=900),
                                      P("UN1263", 700, 6, 0), P("UN1760", 600, 9, 0)],
              ["DANGEROUS", "FLAMMABLE SOLID"], []))
    S.append((["bulk", "dangerous"], [P("UN1350", 1984, 1, 1, packaging="flexible intermediate bulk container",
                                        capacity_l=400, net_kg=900),
                                      P("UN1263", 700, 6, 0), P("UN1760", 600, 9, 0)], ["DANGEROUS"], []))
    S.append((["bulk"], [P("UN1350", 838, 1, packaging="flexible intermediate bulk container", capacity_l=1000,
                           net_kg=380)], [], []))
    S.append((["bulk"], [P("UN1350", 880, 1, packaging="flexible intermediate bulk container", capacity_l=1000,
                           net_kg=401)], ["FLAMMABLE SOLID"], []))
    S.append((["bulk", "combustible"], [P("NA1993", 1900, 2, **IBC, net_kg=850)], ["COMBUSTIBLE"], []))
    S.append((["bulk", "combustible"], [P("NA1993", 1900, 2)], [], []))
    S.append((["bulk", "dangerous", "gases"], [P("UN1013", 1500, 1, 1, packaging="steel tube", capacity_l=600,
                                                 water_lb=1200),
                                               P("UN1263", 700, 6, 0), P("UN1760", 600, 9, 0)],
              ["DANGEROUS", "NON-FLAMMABLE GAS"], []))
    S.append((["bulk", "dangerous", "gases"], [P("UN1013", 1500, 1, 1, packaging="steel cylinder bundle",
                                                 capacity_l=400, water_lb=950),
                                               P("UN1263", 700, 6, 0), P("UN1760", 600, 9, 0)], ["DANGEROUS"], []))
    S.append((["bulk"], [P("UN1263", 1800, 1, **IBC, net_kg=780), P("UN1263", 300, 5)], ["FLAMMABLE"], []))
    S.append((["bulk", "segregation"], [P("UN1789", 2200, 4, **IBC, net_kg=990), P("UN1479", 1100, 5)],
              ["CORROSIVE", "OXIDIZER"], [(0, 1)]))
    # ---------------- uranium hexafluoride (172.505(b)) ---------------------------------------------
    S.append((["uf6"], [P("UN2978", 210, b, rad="YELLOW-II", packaging="steel cylinder (8A)", capacity_l=40,
                          water_lb=95) for b in (1, 1, 2, 2, 3)], ["CORROSIVE", "POISON"], []))
    S.append((["uf6"], [P("UN2978", 210, b, rad="YELLOW-II", packaging="steel cylinder (8A)", capacity_l=40,
                          water_lb=95) for b in (1, 1, 2, 2)], [], []))
    S.append((["uf6", "table1"], [P("UN2978", 210, b, rad="YELLOW-III", packaging="steel cylinder (8A)",
                                    capacity_l=40, water_lb=95) for b in (1, 2, 3, 4, 5)],
              ["CORROSIVE", "POISON", "RADIOACTIVE"], []))
    return S


# ------------------------------------------------------------------ house blends (classified from lab data)
LAB_KEYS = ["flash_point", "initial_boiling_point", "fire_point", "sustains_combustion", "water_miscible",
            "water_pct_mass", "components", "intentionally_heated", "transport_temperature", "oral_ld50_mg_kg",
            "dermal_ld50_mg_kg", "dust_mist_lc50_mg_l", "vapor_lc50_ml_m3", "vapor_pressure_20c",
            "toxic_vapor_components", "skin_corrosion_oecd_404", "corrosion_rate_55c",
            "may_liquefy_in_transport", "other_findings", "pesticide", "gas", "aerosol"]


def C(v):
    return {"value": v, "unit": "C"}


def F(v):
    return {"value": v, "unit": "F"}


def skin(minutes):
    if minutes is None:
        return {"irreversible_damage": False, "exposure_minutes": 240, "damage_observed_within": None}
    return {"irreversible_damage": True, "exposure_minutes": minutes,
            "damage_observed_within": "60 minutes" if minutes <= 3 else "14 days"}


def lab(**kw):
    d = {k: None for k in LAB_KEYS}
    d.update(kw)
    for k in ("sustains_combustion",):
        d.setdefault(k, None)
    d["water_miscible"] = bool(d["water_miscible"])
    d["intentionally_heated"] = bool(d["intentionally_heated"])
    d["may_liquefy_in_transport"] = bool(d["may_liquefy_in_transport"])
    d["pesticide"] = bool(d["pesticide"])
    d["other_findings"] = d["other_findings"] or []
    return d


def gas(lfl=None, ufl=None, kpa=None, psig=None, liquefied=False, lc50=None, comps=None, oxidizing=False, bp=-40):
    return {"boiling_point_c": bp, "lower_flammable_limit_pct": lfl, "upper_flammable_limit_pct": ufl,
            "gauge_pressure_20c": {"value": kpa, "unit": "kPa"} if kpa is not None else {"value": psig,
                                                                                          "unit": "psig"},
            "liquefied": liquefied, "cryogenic": False, "lc50_ppm": lc50,
            "toxic_components": comps, "oxidizing": oxidizing}


BLEND_NAMES = ["HB-{:03d} {}".format(i, n) for i, n in enumerate(
    ["parts wash", "degreaser", "line cleaner", "booth stripper", "coil flush", "tank rinse", "solder flux",
     "etch bath", "floor sealer", "mold release", "ink reducer", "resin cut", "descaler", "boiler treat",
     "fumigant base", "lab reagent", "shop blend", "metal prep", "sanitizer base", "coating thinner"], 101)]


def blend(lab_data, lb, bay, facility=0, state="liquid", packaging=None, capacity_l=None, net_kg=None,
          water_lb=None, acid=False, name=None):
    d_pack, d_cap, d_water = DEFAULT_PACKAGING[state]
    if lab_data.get("aerosol"):
        d_pack, d_cap, d_water = "aerosol cases on pallet", 60, 0.5
    return {"un_number": None, "proper_shipping_name": None, "hazard_class": None, "subsidiary_hazards": None,
            "packing_group": None, "physical_state": state, "gross_weight_lb": lb,
            "limited_quantity": False, "residue_only": False, "labels_required": None,
            "poison_inhalation_hazard_zone": None, "radioactive_label": None,
            "explosive_compatibility_group": None, "explosive_form": None, "fireworks": False, "cyanide": False,
            "acid": acid, "loaded_at": FACILITIES[facility], "shipper": "Heartland house blend", "bay": bay,
            "packaging_type": packaging or d_pack,
            "maximum_capacity_liters": capacity_l if capacity_l is not None else d_cap,
            "maximum_net_mass_kg": net_kg if net_kg is not None else max(1, round(lb * 0.4536 * 0.9)),
            "water_capacity_lb": (water_lb if water_lb is not None else d_water) if state == "gas" else None,
            "product_name": name or rng.choice(BLEND_NAMES), "lab_data": lab_data, "_split": packaging is None}


TOTE = dict(packaging="rigid intermediate bulk container", capacity_l=1040, net_kg=820)


def planted_blends():
    B, P, S = blend, pkg, []
    fl = dict(initial_boiling_point=C(150))
    # ---------------- Class 3, combustible liquid, reclassing and the 173.120 exclusions -------------
    S.append((["blend", "flammability"], [B(lab(flash_point=C(18), initial_boiling_point=C(80)), 1100, 2)],
              ["FLAMMABLE"], []))
    S.append((["blend", "flammability", "reclass"], [B(lab(flash_point=F(113), **fl), 1100, 2)], [], []))
    S.append((["blend", "flammability", "reclass", "bulk"], [B(lab(flash_point=F(113), **fl), 1900, 2, **TOTE)],
              ["COMBUSTIBLE"], []))
    S.append((["blend", "flammability", "exclusion"],
              [B(lab(flash_point=F(95), sustains_combustion=False, **fl), 1200, 2)], ["FLAMMABLE"], []))
    S.append((["blend", "flammability", "exclusion", "bulk"],
              [B(lab(flash_point=C(40), sustains_combustion=False, **fl), 1900, 2, **TOTE)], [], []))
    S.append((["blend", "flammability", "exclusion", "bulk"],
              [B(lab(flash_point=C(50), fire_point=C(105), **fl), 1900, 2, **TOTE)], [], []))
    S.append((["blend", "flammability", "exclusion", "bulk"],
              [B(lab(flash_point=C(50), fire_point=C(95), **fl), 1900, 2, **TOTE)], ["COMBUSTIBLE"], []))
    S.append((["blend", "flammability", "exclusion", "bulk"],
              [B(lab(flash_point=C(42), water_miscible=True, water_pct_mass=92, **fl), 1950, 3, **TOTE)], [], []))
    S.append((["blend", "flammability", "exclusion", "bulk"],
              [B(lab(flash_point=C(42), water_miscible=True, water_pct_mass=88, **fl), 1950, 3, **TOTE)],
              ["COMBUSTIBLE"], []))
    oil = lambda pct: [{"name": "paraffinic base oil", "volume_pct": pct, "flash_point": C(110)},
                       {"name": "naphtha", "volume_pct": round(100 - pct, 1), "flash_point": C(12)}]
    S.append((["blend", "flammability", "exclusion", "bulk"],
              [B(lab(flash_point=C(52), components=oil(99.4), **fl), 1900, 4, **TOTE)], [], []))
    S.append((["blend", "flammability", "exclusion", "bulk"],
              [B(lab(flash_point=C(52), components=oil(98.5), **fl), 1900, 4, **TOTE)], ["COMBUSTIBLE"], []))
    heavy = [{"name": "heavy base oil", "volume_pct": 99.5, "flash_point": C(120)},
             {"name": "mineral spirits", "volume_pct": 0.5, "flash_point": C(40)}]
    S.append((["blend", "flammability", "combustible", "bulk"],
              [B(lab(flash_point=C(75), components=heavy, **fl), 1900, 4, **TOTE)], [], []))
    S.append((["blend", "flammability", "combustible", "bulk"],
              [B(lab(flash_point=C(75), **fl), 1900, 4, **TOTE)], ["COMBUSTIBLE"], []))
    S.append((["blend", "flammability", "combustible", "bulk"],
              [B(lab(flash_point=C(75), sustains_combustion=False, **fl), 1900, 4, **TOTE)], [], []))
    hot = dict(flash_point=C(80), intentionally_heated=True, **fl)
    S.append((["blend", "flammability", "elevated", "bulk"],
              [B(lab(transport_temperature=C(90), **hot), 1900, 5, **TOTE)], ["FLAMMABLE"], []))
    S.append((["blend", "flammability", "elevated"],
              [B(lab(transport_temperature=C(90), **hot), 1100, 5)], [], []))
    S.append((["blend", "flammability", "elevated", "bulk"],
              [B(lab(transport_temperature=C(75), **hot), 1900, 5, **TOTE)], ["COMBUSTIBLE"], []))
    S.append((["blend", "precedence"], [B(lab(flash_point=C(60), skin_corrosion_oecd_404=skin(120), **fl), 1200, 2)],
              ["FLAMMABLE"], []))
    S.append((["blend", "precedence"], [B(lab(flash_point=F(140), skin_corrosion_oecd_404=skin(120), **fl), 1200, 2)],
              ["FLAMMABLE"], []))
    S.append((["blend", "precedence"], [B(lab(flash_point=C(61), skin_corrosion_oecd_404=skin(120), **fl), 1200, 2)],
              ["CORROSIVE"], []))
    # ---------------- packing groups feeding the precedence table ----------------------------------
    S.append((["blend", "precedence"], [B(lab(flash_point=C(10), initial_boiling_point=C(35),
                                              skin_corrosion_oecd_404=skin(2)), 1200, 2)], ["FLAMMABLE"], []))
    S.append((["blend", "precedence"], [B(lab(flash_point=C(10), initial_boiling_point=C(36),
                                              skin_corrosion_oecd_404=skin(2)), 1200, 2)], ["CORROSIVE"], []))
    S.append((["blend", "subsidiary-label"], [B(lab(flash_point=C(10), initial_boiling_point=C(35),
                                                    skin_corrosion_oecd_404=skin(2)), 300, 2),
                                              P("UN1361", 200, 8)], [], [(0, 1)]))
    S.append((["blend", "precedence"], [B(lab(flash_point=F(75), initial_boiling_point=C(120), oral_ld50_mg_kg=30),
                                          1200, 2)], ["POISON"], []))
    S.append((["blend", "precedence"], [B(lab(flash_point=F(72), initial_boiling_point=C(120), oral_ld50_mg_kg=30),
                                          1200, 2)], ["FLAMMABLE"], []))
    S.append((["blend", "subsidiary-label"], [B(lab(flash_point=C(45), oral_ld50_mg_kg=30, **fl), 600, 3),
                                              P("UN1479", 300, 3)], [], [(0, 1)]))
    S.append((["blend", "subsidiary-label"], [B(lab(flash_point=C(30), oral_ld50_mg_kg=30, **fl), 600, 3),
                                              P("UN1479", 300, 3)], [], [(0, 1)]))
    S.append((["blend", "precedence", "pesticide"],
              [B(lab(flash_point=C(40), oral_ld50_mg_kg=200, pesticide=True, **fl), 1200, 2)], ["POISON"], []))
    S.append((["blend", "precedence", "pesticide"],
              [B(lab(flash_point=C(40), oral_ld50_mg_kg=200, **fl), 1200, 2)], ["FLAMMABLE"], []))
    mist = {"value": 0.15, "exposure_hours": 1}
    S.append((["blend", "precedence", "note-2"],
              [B(lab(skin_corrosion_oecd_404=skin(30), dust_mist_lc50_mg_l=mist, oral_ld50_mg_kg=400,
                     dermal_ld50_mg_kg=1500), 1100, 2)], ["CORROSIVE"], []))
    S.append((["blend", "precedence", "note-2"],
              [B(lab(skin_corrosion_oecd_404=skin(30), dust_mist_lc50_mg_l=mist, oral_ld50_mg_kg=40,
                     dermal_ld50_mg_kg=1500), 1100, 2)], ["POISON"], []))
    S.append((["blend", "precedence"], [B(lab(oral_ld50_mg_kg=5.0, skin_corrosion_oecd_404=skin(30)), 1100, 2)],
              ["POISON"], []))
    S.append((["blend", "precedence"], [B(lab(oral_ld50_mg_kg=5.5, skin_corrosion_oecd_404=skin(30)), 1100, 2)],
              ["CORROSIVE"], []))
    dust2 = {"value": 1.0, "exposure_hours": 1}
    S.append((["blend", "precedence", "corrosive"],
              [B(lab(dust_mist_lc50_mg_l=dust2, skin_corrosion_oecd_404=skin(3)), 1100, 2)], ["CORROSIVE"], []))
    S.append((["blend", "precedence", "corrosive"],
              [B(lab(dust_mist_lc50_mg_l=dust2, skin_corrosion_oecd_404=skin(4)), 1100, 2)], ["POISON"], []))
    # ---------------- Division 6.1 by inhalation of vapors -----------------------------------------
    vp = lambda v, u="kPa": {"value": v, "unit": u}
    S.append((["blend", "toxicity"], [B(lab(vapor_lc50_ml_m3={"value": 900, "exposure_hours": 4},
                                            vapor_pressure_20c=vp(20)), 300, 2)], [], []))
    S.append((["blend", "toxicity"], [B(lab(vapor_lc50_ml_m3={"value": 900, "exposure_hours": 1},
                                            vapor_pressure_20c=vp(20)), 300, 2)], ["POISON INHALATION HAZARD"], []))
    S.append((["blend", "toxicity", "zone"], [B(lab(vapor_lc50_ml_m3={"value": 100, "exposure_hours": 1},
                                                    vapor_pressure_20c=vp(15, "mmHg")), 200, 1),
                                              P("UN1263", 300, 8)], ["POISON INHALATION HAZARD"], []))
    S.append((["blend", "toxicity", "zone"], [B(lab(vapor_lc50_ml_m3={"value": 100, "exposure_hours": 1},
                                                    vapor_pressure_20c=vp(15)), 200, 1),
                                              P("UN1263", 300, 8)], ["POISON INHALATION HAZARD"], [(0, 1)]))
    mixB = [{"name": "chloro solvent", "mole_fraction": 0.10, "vapor_pressure_20c_kpa": 30, "vapor_lc50_ml_m3": 300},
            {"name": "amine", "mole_fraction": 0.05, "vapor_pressure_20c_kpa": 10, "vapor_lc50_ml_m3": 2000}]
    S.append((["blend", "toxicity", "mixture"], [B(lab(toxic_vapor_components=mixB), 500, 2)], [], []))
    mixA = [{"name": "isocyanate", "mole_fraction": 0.30, "vapor_pressure_20c_kpa": 40, "vapor_lc50_ml_m3": 50},
            {"name": "nitrile", "mole_fraction": 0.20, "vapor_pressure_20c_kpa": 5, "vapor_lc50_ml_m3": 400}]
    S.append((["blend", "toxicity", "mixture", "zone"], [B(lab(toxic_vapor_components=mixA), 200, 2),
                                                         P("UN1789", 300, 9)],
              ["POISON INHALATION HAZARD"], [(0, 1)]))
    S.append((["blend", "toxicity", "precedence"],
              [B(lab(flash_point=C(45), oral_ld50_mg_kg=200, vapor_lc50_ml_m3={"value": 2000, "exposure_hours": 1},
                     vapor_pressure_20c=vp(1.0), **fl), 1200, 2)], ["POISON"], []))
    S.append((["blend", "toxicity", "boundary"], [B(lab(flash_point=C(50), oral_ld50_mg_kg=300, **fl), 1200, 2)],
              ["FLAMMABLE"], []))
    S.append((["blend", "toxicity", "boundary"], [B(lab(flash_point=C(50), oral_ld50_mg_kg=310, **fl), 1200, 2)],
              [], []))
    S.append((["blend", "toxicity", "boundary"],
              [B(lab(dust_mist_lc50_mg_l={"value": 1.0, "exposure_hours": 4}), 1200, 2, state="solid")],
              ["POISON"], []))
    S.append((["blend", "toxicity", "boundary"],
              [B(lab(dust_mist_lc50_mg_l={"value": 1.1, "exposure_hours": 4}), 1200, 2, state="solid")], [], []))
    S.append((["blend", "toxicity", "boundary"], [B(lab(vapor_lc50_ml_m3={"value": 2500, "exposure_hours": 4},
                                                        vapor_pressure_20c=vp(0.45)), 1200, 2)], ["POISON"], []))
    S.append((["blend", "toxicity", "boundary"], [B(lab(vapor_lc50_ml_m3={"value": 2600, "exposure_hours": 4},
                                                        vapor_pressure_20c=vp(0.45)), 1200, 2)], [], []))
    S.append((["blend", "toxicity", "pih", "subsidiary-label"],
              [B(lab(vapor_lc50_ml_m3={"value": 400, "exposure_hours": 1}, vapor_pressure_20c=vp(8),
                     flash_point=C(15), initial_boiling_point=C(90)), 300, 3), P("UN1479", 300, 3)],
              ["POISON INHALATION HAZARD"], [(0, 1)]))
    # ---------------- Class 8 --------------------------------------------------------------------
    rate = lambda st, al: {"steel": st, "aluminum": al}
    mm = lambda v: {"value": v, "unit": "mm/yr"}
    inch = lambda v: {"value": v, "unit": "in/yr"}
    S.append((["blend", "corrosive", "bulk"], [B(lab(skin_corrosion_oecd_404=skin(None),
                                                     corrosion_rate_55c=rate(inch(0.3), mm(2.0))), 1900, 3, **TOTE)],
              ["CORROSIVE"], []))
    S.append((["blend", "corrosive", "bulk"], [B(lab(skin_corrosion_oecd_404=skin(None),
                                                     corrosion_rate_55c=rate(inch(0.2), mm(3.0))), 1900, 3, **TOTE)],
              [], []))
    S.append((["blend", "corrosive", "bulk"], [B(lab(skin_corrosion_oecd_404=skin(None),
                                                     corrosion_rate_55c=rate(mm(1.0), mm(6.6))), 1900, 3, **TOTE)],
              ["CORROSIVE"], []))
    BAG = dict(packaging="flexible intermediate bulk container", capacity_l=1000, net_kg=900)
    S.append((["blend", "corrosive", "bulk"], [B(lab(skin_corrosion_oecd_404=skin(None),
                                                     corrosion_rate_55c=rate(mm(9.0), mm(2.0))), 2050, 3,
                                                 state="solid", **BAG)], [], []))
    S.append((["blend", "corrosive", "bulk"], [B(lab(skin_corrosion_oecd_404=skin(None), may_liquefy_in_transport=True,
                                                     corrosion_rate_55c=rate(mm(9.0), mm(2.0))), 2050, 3,
                                                 state="solid", **BAG)], ["CORROSIVE"], []))
    S.append((["blend", "corrosive", "segregation"], [B(lab(skin_corrosion_oecd_404=skin(45)), 300, 4),
                                                      P("UN1479", 300, 5)], [], [(0, 1)]))
    S.append((["blend", "corrosive", "segregation"], [B(lab(skin_corrosion_oecd_404=skin(45)), 300, 4,
                                                        state="solid"), P("UN1479", 300, 5)], [], []))
    # ---------------- 4.x findings, subsidiary dangerous-when-wet -----------------------------------
    S.append((["blend", "precedence", "subsidiary-label"],
              [B(lab(flash_point=C(10), initial_boiling_point=C(60),
                     other_findings=[{"division": "4.3", "packing_group": "II"}]), 200, 4), P("UN1479", 300, 4)],
              ["DANGEROUS WHEN WET"], [(0, 1)]))
    S.append((["blend", "precedence", "subsidiary"],
              [B(lab(skin_corrosion_oecd_404=skin(2), other_findings=[{"division": "4.3", "packing_group": "II"}]),
                 150, 4)], ["CORROSIVE", "DANGEROUS WHEN WET"], []))
    S.append((["blend", "precedence", "subsidiary"],
              [B(lab(skin_corrosion_oecd_404=skin(2), other_findings=[{"division": "4.3", "packing_group": "I"}]),
                 150, 4)], ["DANGEROUS WHEN WET"], []))
    S.append((["blend", "precedence", "pyrophoric"],
              [B(lab(flash_point=C(5), initial_boiling_point=C(70),
                     other_findings=[{"division": "4.2", "packing_group": "I", "pyrophoric": True}]), 300, 2),
               P("UN1760", 300, 9)], [], [(0, 1)]))
    S.append((["blend", "precedence", "pyrophoric"],
              [B(lab(flash_point=C(5), initial_boiling_point=C(70),
                     other_findings=[{"division": "4.2", "packing_group": "I", "pyrophoric": True}]), 1100, 2)],
              ["SPONTANEOUSLY COMBUSTIBLE"], []))
    # ---------------- Class 2 -----------------------------------------------------------------------
    G = dict(state="gas")
    S.append((["blend", "gas"], [B(lab(gas=gas(lfl=14, ufl=27, kpa=1500)), 1100, 2, **G)], ["FLAMMABLE GAS"], []))
    S.append((["blend", "gas"], [B(lab(gas=gas(lfl=14, ufl=24, kpa=1500)), 1100, 2, **G)], ["NON-FLAMMABLE GAS"],
              []))
    S.append((["blend", "gas"], [B(lab(gas=gas(psig=25)), 600, 2, **G), P("UN1263", 500, 6)], [], []))
    S.append((["blend", "gas"], [B(lab(gas=gas(psig=35)), 600, 2, **G), P("UN1263", 500, 6)], ["DANGEROUS"], []))
    S.append((["blend", "gas", "zone"], [B(lab(gas=gas(kpa=3000, comps=[{"name": "phosphine", "mole_fraction": 0.025,
                                                                         "lc50_ppm": 20}])), 100, 1, **G),
                                         P("UN1263", 300, 8)], ["POISON GAS"], []))
    S.append((["blend", "gas", "zone"], [B(lab(gas=gas(kpa=3000, comps=[{"name": "phosphine", "mole_fraction": 0.15,
                                                                         "lc50_ppm": 20}])), 100, 1, **G),
                                         P("UN1263", 300, 8)], ["POISON GAS"], [(0, 1)]))
    S.append((["blend", "gas", "subsidiary-label"], [B(lab(gas=gas(lfl=3, ufl=12, kpa=900, lc50=2000)), 100, 5, **G),
                                                     P("UN2915", 50, 5, rad="YELLOW-II")], ["POISON GAS"], [(0, 1)]))
    S.append((["blend", "gas"], [B(lab(gas=gas(lfl=3, ufl=12, kpa=900, lc50=5200)), 1100, 5, **G)],
              ["FLAMMABLE GAS"], []))
    S.append((["blend", "gas", "subsidiary-label"], [B(lab(gas=gas(kpa=15000, oxidizing=True)), 300, 6, **G),
                                                     P("UN1263", 300, 6)], [], [(0, 1)]))
    S.append((["blend", "gas", "aerosol"], [B(lab(aerosol={"flammable_components_pct_mass": 90,
                                                           "heat_of_combustion_kj_g": 35}), 1100, 2, **G)],
              ["FLAMMABLE GAS"], []))
    S.append((["blend", "gas", "aerosol"], [B(lab(aerosol={"flammable_components_pct_mass": 0.5,
                                                           "heat_of_combustion_kj_g": 12}), 1100, 2, **G)],
              ["NON-FLAMMABLE GAS"], []))
    return S


# Everyday house blends for filler loads (each well away from every threshold).
FILLER_BLENDS = [
    lambda: lab(flash_point=C(rng.choice([8, 12, 15])), initial_boiling_point=C(rng.choice([70, 95]))),
    lambda: lab(flash_point=C(rng.choice([27, 31])), initial_boiling_point=C(140)),
    lambda: lab(flash_point=C(rng.choice([44, 48, 55])), initial_boiling_point=C(170)),
    lambda: lab(flash_point=F(rng.choice([115, 125])), initial_boiling_point=F(330)),
    lambda: lab(flash_point=C(rng.choice([70, 82])), initial_boiling_point=C(240)),
    lambda: lab(skin_corrosion_oecd_404=skin(rng.choice([20, 45]))),
    lambda: lab(skin_corrosion_oecd_404=skin(rng.choice([90, 180]))),
    lambda: lab(skin_corrosion_oecd_404=skin(None), corrosion_rate_55c={"steel": {"value": 1.2, "unit": "mm/yr"},
                                                                         "aluminum": {"value": 0.8, "unit": "mm/yr"}}),
    lambda: lab(oral_ld50_mg_kg=rng.choice([120, 180, 240]), dermal_ld50_mg_kg=2000),
    lambda: lab(flash_point=C(33), initial_boiling_point=C(150), oral_ld50_mg_kg=25),
    lambda: lab(flash_point=C(12), initial_boiling_point=C(80), skin_corrosion_oecd_404=skin(150)),
    lambda: lab(flash_point=C(47), initial_boiling_point=C(150), skin_corrosion_oecd_404=skin(30)),
    lambda: lab(vapor_lc50_ml_m3={"value": 2000, "exposure_hours": 1}, vapor_pressure_20c={"value": 1.0,
                                                                                            "unit": "kPa"}),
]


TABLE2 = {"1.4": "EXPLOSIVES 1.4", "2.1": "FLAMMABLE GAS", "2.2": "NON-FLAMMABLE GAS", "3": "FLAMMABLE",
          "4.1": "FLAMMABLE SOLID", "4.2": "SPONTANEOUSLY COMBUSTIBLE", "5.1": "OXIDIZER",
          "5.2": "ORGANIC PEROXIDE", "6.1": "POISON", "8": "CORROSIVE"}


def ambiguous(pkgs):
    """Reject filler loads where one category is forced (single-facility amount or bulk) and exactly one
    other Table 2 category remains (DANGEROUS for a single leftover category is left open), and loads
    mixing bulk with under 1,001 lb of non-bulk Table 2 material."""
    norm = [x for x in (solve.normalize(p) for p in pkgs) if x is not None]
    cats, per_fac, bulk_cats, nonbulk_t2 = set(), {}, set(), 0
    for p in norm:
        c = TABLE2.get(p["hazard_class"])
        if p["limited_quantity"] or c is None or (p["poison_inhalation_hazard_zone"] and p["hazard_class"] == "6.1"):
            continue
        if solve.is_bulk(p):
            bulk_cats.add(c)
            continue
        nonbulk_t2 += p["gross_weight_lb"]
        cats.add(c)
        per_fac[(c, p["loaded_at"])] = per_fac.get((c, p["loaded_at"]), 0) + p["gross_weight_lb"]
    if (bulk_cats or any(p["hazard_class"] == "combustible liquid" and solve.is_bulk(p) for p in norm)) \
            and 0 < nonbulk_t2 < 1001:
        return True
    big = {c for (c, f), w in per_fac.items() if w >= 2205} | bulk_cats
    return bool(big) and len(cats - big) == 1


def filler(n):
    """Everyday mixes of common goods and house blends (expected values come from the verifier engine only)."""
    common = ["UN1263", "UN1993", "UN1090", "UN1760", "UN1823", "UN1950", "UN1066", "UN1013", "UN1350",
              "UN1479", "UN3107", "UN1710", "UN2783", "NA1993", "UN2796", "UN1325", "UN1376"]
    loads = []
    while len(loads) < n:
        k = rng.randint(2, 9)
        pkgs = []
        for _ in range(k):
            lb = rng.choice([45, 60, 120, 180, 250, 340, 420, 550, 800])
            if rng.random() < 0.4:
                tote = rng.random() < 0.15
                pkgs.append(blend(rng.choice(FILLER_BLENDS)(), rng.choice([1500, 1900]) if tote else lb,
                                  rng.randint(1, 10), rng.randrange(4), **(TOTE if tote else {})))
                continue
            un = rng.choice(common)
            if CAT[un][4] == "liquid" and rng.random() < 0.12:
                pkgs.append(pkg(un, rng.choice([1500, 1900, 2300]), rng.randint(1, 10), rng.randrange(4),
                                packaging="rigid intermediate bulk container", capacity_l=1040,
                                net_kg=rng.choice([600, 800, 950])))
                continue
            pkgs.append(pkg(un, lb, rng.randint(1, 10), rng.randrange(4),
                            lq=(un == "UN1950") or (un in ("UN1263", "UN1993") and rng.random() < 0.3)))
        if ambiguous(pkgs):
            continue
        loads.append((["filler"], pkgs, None, None))
    return loads


def split_heavy(pkgs):
    """Real packages: drums up to 550 lb, boxes and cases of limited quantities or explosives up to 60 lb,
    cylinders up to 150 lb. A heavier default-packed load becomes several identical packages in its bay."""
    out, index = [], []
    for p in pkgs:
        default = p.pop("_split")
        lb, state = p["gross_weight_lb"], p["physical_state"]
        aerosol = bool(p["lab_data"] and p["lab_data"].get("aerosol")) or p["un_number"] == "UN1950"
        if not default:
            cap, form = lb, None
        elif p["limited_quantity"]:
            cap, form = 60, ("fiberboard box of inner packagings", 30, None)
        elif state == "gas":
            cap, form = (55, ("fiberboard case of aerosols", 30, 0.5)) if aerosol else \
                (150, ("steel cylinder", 50, 110))
        elif state == "liquid":
            cap, form = 550, ("steel drum", 208, None)
        elif (p["hazard_class"] or "").startswith("1.") or lb <= 120:
            cap, form = 60 if (p["hazard_class"] or "").startswith("1.") else 120, ("fiberboard box", 60, None)
        else:
            cap, form = 550, ("steel drum, open head", 208, None)
        n = -(-lb // cap)
        parts = [lb // n + (1 if k < lb % n else 0) for k in range(n)]
        ids = []
        for w in parts:
            q = dict(p, gross_weight_lb=w)
            if form:
                q["packaging_type"], q["maximum_capacity_liters"] = form[0], form[1]
                q["maximum_net_mass_kg"] = max(1, round(w * 0.4536 * 0.9))
                if state == "gas":
                    q["water_capacity_lb"] = form[2]
            ids.append(len(out))
            out.append(q)
        index.append(ids)
    return out, index


def main():
    S = planted() + planted_blends() + filler(80)
    rng.shuffle(S)
    trailers, golden, tags = [], {}, {}
    n_pkg = 0
    for i, (tg, pkgs, placards, pairs) in enumerate(S, 1):
        tid = f"TR{i:03d}"
        pkgs, index = split_heavy(pkgs)
        if pairs is not None:
            pairs = [(x, y) for a, b in pairs for x in index[a] for y in index[b]]
        ids = []
        for p in pkgs:
            n_pkg += 1
            p["package_id"] = f"PK{n_pkg:04d}"
            ids.append(p["package_id"])
        order = list(range(len(pkgs)))
        rng.shuffle(order)
        trailers.append({"trailer_id": tid, "route": "domestic highway, Ohio to Indiana and Michigan",
                         "bays": 10, "packages": [{"package_id": pkgs[j].pop("package_id"), **pkgs[j]}
                                                  for j in order]})
        tags[tid] = tg
        if placards is not None:
            viol = sorted("+".join(sorted((ids[a], ids[b]))) for a, b in pairs)
            golden[tid] = {"placards": ";".join(sorted(placards)) or "none",
                           "segregation_violations": ";".join(viol) or "none"}
    ENV.mkdir(parents=True, exist_ok=True)
    (ENV / "trailers.json").write_text(json.dumps(trailers, indent=1) + "\n")
    (ENV / "carrier.json").write_text(json.dumps({
        "carrier": "Heartland Freight Lines", "mode": "highway", "transport": "domestic",
        "trailer": "53 ft dry van, 10 floor bays numbered 1 (nose) to 10 (doors), single tier",
        "packaging_units": "maximum capacity in liters, maximum net mass in kilograms, water capacity in pounds",
        "weight_unit": "pounds",
        "house_blends": "Packages with lab_data are Heartland's own blends, offered by Heartland and not named in "
                        "the 172.101 table; they carry no recorded classification, packing group or labels.",
        "combustible_reclass": "Heartland reclasses as a combustible liquid every flammable liquid that the "
                               "regulations allow it to reclass."}, indent=1) + "\n")
    if TST.exists():
        shutil.rmtree(TST)
    shutil.copytree(ENV, TST)
    (ROOT / "tests" / "case_tags.json").write_text(json.dumps(tags, indent=1, sort_keys=True) + "\n")
    (ROOT / "tests" / "golden.json").write_text(json.dumps(golden, indent=1, sort_keys=True) + "\n")
    print(len(trailers), "trailers,", n_pkg, "packages,", len(golden), "golden")


if __name__ == "__main__":
    main()
