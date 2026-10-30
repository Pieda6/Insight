"""Transcribe the TG-43U1 consensus datasets from the report text and check them against the report's Table XV.

Reads sources/tg43u1_excerpt.txt (pdftotext -layout of the report pages) and writes source_data.json for both data
copies. Values are taken exactly as printed: Table I (dose-rate constants), Tables II and III (g_L and g_P), Tables
IV to XI (F(r, theta) for 0 to 80 or 85 degrees, and phi_an(r)), Table XIII (half-lives) and the active lengths in
the headers of Tables II and III.
"""
import sys
sys.dont_write_bytecode = True       # never leave __pycache__ in the submitted task folder
import json
import math
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEXT = (HERE / "sources" / "tg43u1_excerpt.txt").read_text()
LINES = TEXT.splitlines()

MODELS = ["6702", "6711", "2301", "MED3631-A/M", "I25.S06", "IS-12501", "200", "MED3633"]
INFO = {   # manufacturer, radionuclide, active length (cm) from the Table II and III headers
    "6702": ("Amersham", "I-125", 0.30), "6711": ("Amersham", "I-125", 0.30), "2301": ("Best", "I-125", 0.40),
    "MED3631-A/M": ("NASI", "I-125", 0.42), "I25.S06": ("Bebig/Theragenics", "I-125", 0.35),
    "IS-12501": ("Imagyn", "I-125", 0.34), "200": ("Theragenics", "Pd-103", 0.423), "MED3633": ("NASI", "Pd-103", 0.42)}
LAMBDA = {"6702": 1.036, "6711": 0.965, "2301": 1.018, "MED3631-A/M": 1.036, "I25.S06": 1.012, "IS-12501": 0.940,
          "200": 0.686, "MED3633": 0.688}                                    # Table I, cGy h-1 U-1
HALF_LIFE = {"I-125": 59.40, "Pd-103": 16.991}                             # Table XIII, days
NUM = re.compile(r"\d+\.\d+")


def find(title):
    return next(i for i, line in enumerate(LINES) if title in line)


def tokens(line):
    return [(m.start() + len(m.group()) / 2, float(m.group())) for m in NUM.finditer(line)]


def column_table(title, ncols, ref_r):
    """Rows of a g(r) table with blank cells: each number goes to the nearest column of the complete row ref_r."""
    i = find(title)
    rows = []
    for line in LINES[i:i + 60]:
        m = re.match(r"\s*(\d+\.\d+)\s", line)
        if m and (rows or float(m.group(1)) == 0.10):
            rows.append(line)
            if float(m.group(1)) == 10.0:
                break
    ref = next(r for r in rows if float(r.split()[0]) == ref_r)
    centers = [c for c, _ in tokens(ref)[1:]]
    assert len(centers) == ncols, (title, centers)
    out = []
    for line in rows:
        tk = tokens(line)
        r, cells = tk[0][1], [None] * ncols
        for c, v in tk[1:]:
            j = min(range(ncols), key=lambda k: abs(centers[k] - c))
            assert cells[j] is None and abs(centers[j] - c) < 4, (title, line)
            cells[j] = v
        out.append((r, cells))
    return out


def f_table(title):
    i = find(title)
    head = next(j for j in range(i, i + 12) if "degrees" in LINES[j])
    radii = [float(x) for x in NUM.findall(LINES[head].replace("0.5 ", "0.5 ")) or []]
    radii = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", LINES[head].split("兲", 1)[1])]
    angles, values, phi = [], [], None
    for line in LINES[head + 1:head + 40]:
        if "an(r)" in line:
            phi = [float(x) for x in NUM.findall(line)]
            break
        parts = line.split()
        if parts and re.fullmatch(r"\d+", parts[0]):
            row = [float(x) for x in parts[1:]]
            assert len(row) == len(radii), (title, line)
            angles.append(float(parts[0]))
            values.append(row)
    assert phi and len(phi) == len(radii), title
    return radii, angles, values, phi


def build():
    t2 = column_table("TABLE II. Consensus g(r) values for six", 12, 0.25)
    t3 = column_table("TABLE III. Consensus g(r) values for two", 4, 0.25)
    gl, gp = {}, {}
    for r, cells in t2:
        for k, m in enumerate(MODELS[:6]):
            if cells[k] is not None:
                gl.setdefault(m, []).append([r, cells[k]])
            if cells[6 + k] is not None:
                gp.setdefault(m, []).append([r, cells[6 + k]])
    for r, cells in t3:
        for k, m in enumerate(MODELS[6:]):
            if cells[k] is not None:
                gl.setdefault(m, []).append([r, cells[k]])
            if cells[2 + k] is not None:
                gp.setdefault(m, []).append([r, cells[2 + k]])
    titles = {"6702": "TABLE IV. F(r", "6711": "TABLE V. F(r", "2301": "TABLE VI. F(r", "MED3631-A/M": "TABLE VII. F(r",
              "I25.S06": "TABLE VIII. F(r", "IS-12501": "TABLE IX. F(r", "200": "TABLE X. F(r", "MED3633": "TABLE XI. F(r"}
    data = {}
    for m in MODELS:
        maker, nuc, length = INFO[m]
        radii, angles, values, phi = f_table(titles[m])
        data[m] = {
            "manufacturer": maker, "radionuclide": nuc, "half_life_days": HALF_LIFE[nuc],
            "active_length_cm": length, "dose_rate_constant_cGy_per_h_per_U": LAMBDA[m],
            "radial_dose_function_line_source": gl[m], "radial_dose_function_point_source": gp[m],
            "anisotropy_function": {"r_cm": radii, "theta_deg": angles, "F": values},
            "anisotropy_factor_1d": [[r, v] for r, v in zip(radii, phi)]}
    return data


def g_loglin(table, r):
    rs = [a for a, _ in table]
    if r <= rs[0]:
        return table[0][1]
    if r >= rs[-1]:
        return table[-1][1]
    j = max(k for k in range(len(rs)) if rs[k] <= r)
    (r1, g1), (r2, g2) = table[j], table[j + 1]
    return math.exp(math.log(g1) + (math.log(g2) - math.log(g1)) * (r - r1) / (r2 - r1))


def lin(table, r):
    rs = [a for a, _ in table]
    if r <= rs[0]:
        return table[0][1]
    if r >= rs[-1]:
        return table[-1][1]
    j = max(k for k in range(len(rs)) if rs[k] <= r)
    (r1, g1), (r2, g2) = table[j], table[j + 1]
    return g1 + (g2 - g1) * (r - r1) / (r2 - r1)


def table_xv():
    i = find("TABLE XV. Dose rates")
    out = {}
    for line in LINES[i:i + 20]:
        p = line.split()
        if p and re.fullmatch(r"\d\.\d", p[0]) and len(p) == 9:
            out[float(p[0])] = [float(x) for x in p[1:]]
    return out


def check_table_xv(data):
    """1D dose rate per unit S_K by Eq. (11) at r = 0.5 to 7 cm, against the report's Table XV (3 significant digits)."""
    worst = 0.0
    lines = []
    for r, printed in table_xv().items():
        for m, want in zip(MODELS, printed):
            d = data[m]
            L = d["active_length_cm"]
            beta = 2 * math.atan(L / 2 / r)
            ratio = (beta / (L * r)) / (2 * math.atan(L / 2) / L)
            for scheme, g in (("log-linear g", g_loglin), ("linear g", lin)):
                v = d["dose_rate_constant_cGy_per_h_per_U"] * ratio * g(d["radial_dose_function_line_source"], r) \
                    * lin(d["anisotropy_factor_1d"], r)
                if scheme == "log-linear g":
                    rel = abs(v - want) / want
                    worst = max(worst, rel)
                    lines.append(f"r={r:4.1f} {m:12s} computed {v:.5g} printed {want:.5g} rel {rel:.4f}")
    return worst, lines


if __name__ == "__main__":
    data = build()
    for m in MODELS:
        d = data[m]
        F = d["anisotropy_function"]
        print(m, "g_L", d["radial_dose_function_line_source"][0], "...", d["radial_dose_function_line_source"][-1],
              f"({len(d['radial_dose_function_line_source'])} values)", "F r", F["r_cm"], "theta", F["theta_deg"])
    worst, lines = check_table_xv(data)
    print("\n".join(lines))
    print(f"Table XV agreement: worst relative difference {worst:.4f}")
    text = json.dumps(data, indent=1)
    for dest in ("../environment/data", "../tests/data"):
        (HERE / dest / "source_data.json").write_text(text + "\n")
