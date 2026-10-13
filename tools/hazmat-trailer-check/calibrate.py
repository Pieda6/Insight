#!/usr/bin/env python3
"""Dev-only calibration for hazmat-trailer-check (never uploaded): oracle passes, empty output fails,
and each common misreading of 49 CFR 172.500-172.505 / 177.848 fails at least one test."""
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
O = {k: getattr(S, k) for k in ("placards", "violates", "seg_key", "explosives_clash", "cell")}


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
        if p["labels_required"]:
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
            p["subsidiary_hazards"], q["subsidiary_hazards"] = [], []
        if flags.get("unlabeled"):
            p["labels_required"] = p["labels_required"] or ["X"]
            q["labels_required"] = q["labels_required"] or ["X"]
        if flags.get("no_cyanide"):
            p["cyanide"] = q["cyanide"] = False
        if flags.get("no_same_class") and p["hazard_class"].split(".")[0] == q["hazard_class"].split(".")[0]:
            p["hazard_class"], q["hazard_class"] = p["hazard_class"] + "", q["hazard_class"] + ""
            res = False
            for a in [p["hazard_class"]] + p["subsidiary_hazards"]:
                for b in [q["hazard_class"]] + q["subsidiary_hazards"]:
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


SHORTCUTS = {
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
    for name, patch in SHORTCUTS.items():
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
