"""Local runner for the repaired tg51calc (used by the authoring checks; solve.sh is the real entry point)."""
import sys
from pathlib import Path

DATA = Path("/app/data")
OUT = Path("/app/output")


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    for name in [m for m in sys.modules if m == "tg51calc" or m.startswith("tg51calc.")]:
        del sys.modules[name]
    from tg51calc.review import main as review
    OUT.mkdir(parents=True, exist_ok=True)
    review([str(DATA), str(OUT / "dose_per_mu.csv")])
    sys.path.pop(0)


if __name__ == "__main__":
    main()
