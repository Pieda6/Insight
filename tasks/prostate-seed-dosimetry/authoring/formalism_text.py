"""Write data/tg43u1_formalism.txt (both copies): the report's Section III (pages 637 to 640) and Appendices C, D
and E (pages 669 to 672) as extracted by pdftotext -layout in sources/tg43u1_excerpt.txt, with the PDF's private
glyphs mapped back to the characters they stand for. Nothing else is changed."""
import sys
sys.dont_write_bytecode = True
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAGES = [5, 6, 7, 8, 37, 38, 40]          # PDF pages: Sec. III A and B (637-640), Appendices C to E (669-672)
GLYPHS = {"共": "(", "兲": ")", "关": "[", "兴": "]", "兩": "{", "冉": "(", "冊": ")", "再": "{", "冑": "}", "兰": "[",
          "兺": "sum", "兵": "integral", "其": "}", "冦": "{", "␪": "θ", "␾": "φ", "␴": "ρ",
          "␦": "δ", "␮": "λ", "␲": "π", "␤": "β", "⳵": "λ", "⌳": "Λ", "⌫": "Γ",
          "⌬": "Δ", "⫽": "=", "⫺": "-", "⫹": "+", "⫾": "±", "⫻": "×", "⬍": "<", "⬎": ">", "⭐": "<=", "⭓": ">=",
          "⬘": "~", "⬇": "->", "⬃": "~", "⬅": "<-", "•": "·", "–": "-", "—": "-", "’": "'", "‘": "'"}


def main():
    text = (HERE / "sources" / "tg43u1_excerpt.txt").read_text(encoding="utf-8")
    parts = re.split(r"^=== PDF PAGE (\d+) ===\n", text, flags=re.M)
    pages = {int(parts[i]): parts[i + 1] for i in range(1, len(parts), 2)}
    out = ["AAPM TG-43U1 (Rivard et al., Med Phys 2004;31:633-674): Section III (dose-calculation formalism) and "
           "Appendices C (dose rate at small and large distances), D (anisotropy constant) and E (apparent activity), "
           "text extracted from the PDF with pdftotext -layout. Two-column pages read column by column; glyphs the PDF "
           "encodes privately are written as the characters they stand for.\n"]
    for p in PAGES:
        body = pages[p]
        for k, v in GLYPHS.items():
            body = body.replace(k, v)
        out.append(f"=== PDF PAGE {p} ===\n{body}")
    joined = "".join(out)
    for target in (HERE / "../environment/data", HERE / "../tests/data"):
        (target / "tg43u1_formalism.txt").write_text(joined, encoding="utf-8")
    odd = sorted({ch for ch in joined if ord(ch) > 0x24F})
    print(f"{len(joined.splitlines())} lines; characters above U+024F left: {odd}")


if __name__ == "__main__":
    main()
