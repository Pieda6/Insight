#!/usr/bin/env python3
"""Generate the hazmat-trailer-check inputs (dev only, never shipped).

One carrier's outbound trailers for a day. Each package record carries what the shipping papers and
labels say (UN number, class/division, subsidiary hazards, packing group, physical state, PIH zone,
labels required, limited quantity, residue only, radioactive label, explosive compatibility group,
article/substance, fireworks, cyanide, acid), its gross weight, the facility where it was loaded and
the trailer bay. Planted trailers carry a hand-worked expected answer (tests/golden.json).
"""
import json
import random
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "tasks" / "hazmat-trailer-check"
ENV, TST = ROOT / "environment" / "data", ROOT / "tests" / "data"
rng = random.Random(177848)

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


def pkg(un, lb, bay, facility=0, lq=False, residue=False, rad=None, label_override=None):
    name, cls, sub, pg, state, extra = CAT[un]
    labels = [] if lq or cls == "combustible liquid" else (
        [f"RADIOACTIVE {rad}"] if cls == "7" else [LABEL[cls]] + [LABEL[s] for s in sub])
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
         "shipper": rng.choice(SHIPPERS), "bay": bay, "packaging": "non-bulk"}
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
    return S


TABLE2 = {"1.4": "EXPLOSIVES 1.4", "2.1": "FLAMMABLE GAS", "2.2": "NON-FLAMMABLE GAS", "3": "FLAMMABLE",
          "4.1": "FLAMMABLE SOLID", "4.2": "SPONTANEOUSLY COMBUSTIBLE", "5.1": "OXIDIZER",
          "5.2": "ORGANIC PEROXIDE", "6.1": "POISON", "8": "CORROSIVE"}


def ambiguous(pkgs):
    """Reject filler loads where one category reaches the single-facility amount and exactly one
    other Table 2 category remains (DANGEROUS for a single leftover category is left open)."""
    cats, per_fac = set(), {}
    for p in pkgs:
        if p["limited_quantity"] or p["hazard_class"] not in TABLE2:
            continue
        c = TABLE2[p["hazard_class"]]
        cats.add(c)
        per_fac[(c, p["loaded_at"])] = per_fac.get((c, p["loaded_at"]), 0) + p["gross_weight_lb"]
    big = {c for (c, f), w in per_fac.items() if w >= 2205}
    return bool(big) and len(cats - big) == 1


def filler(n):
    """Everyday mixes of common goods (expected values come from the verifier engine only)."""
    common = ["UN1263", "UN1993", "UN1090", "UN1760", "UN1823", "UN1950", "UN1066", "UN1013", "UN1350",
              "UN1479", "UN3107", "UN1710", "UN2783", "NA1993", "UN2796", "UN1325", "UN1376"]
    loads = []
    while len(loads) < n:
        k = rng.randint(2, 9)
        pkgs = []
        for _ in range(k):
            un = rng.choice(common)
            lb = rng.choice([45, 60, 120, 180, 250, 340, 420, 550, 800])
            pkgs.append(pkg(un, lb, rng.randint(1, 10), rng.randrange(4),
                            lq=(un == "UN1950") or (un in ("UN1263", "UN1993") and rng.random() < 0.3)))
        if ambiguous(pkgs):
            continue
        loads.append((["filler"], pkgs, None, None))
    return loads


def main():
    S = planted() + filler(70)
    rng.shuffle(S)
    trailers, golden, tags = [], {}, {}
    n_pkg = 0
    for i, (tg, pkgs, placards, pairs) in enumerate(S, 1):
        tid = f"TR{i:03d}"
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
        "weight_unit": "pounds"}, indent=1) + "\n")
    if TST.exists():
        shutil.rmtree(TST)
    shutil.copytree(ENV, TST)
    (ROOT / "tests" / "case_tags.json").write_text(json.dumps(tags, indent=1, sort_keys=True) + "\n")
    (ROOT / "tests" / "golden.json").write_text(json.dumps(golden, indent=1, sort_keys=True) + "\n")
    print(len(trailers), "trailers,", n_pkg, "packages,", len(golden), "golden")


if __name__ == "__main__":
    main()
