#!/usr/bin/env python3
"""Run shortcut versions of the reference solution against the tests.

Usage: python3 calibrate.py      (from authoring/)

Each shortcut is a plausible misreading made by editing solution/solve.py text. A shortcut is caught when at
least one test fails; the number of wrong rows shows how widely it shows up.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TASK = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(TASK / "tests"))
from local_check import run_solution, run_tests  # noqa: E402
import engine  # noqa: E402

# name -> list of (exact text in solve.py, replacement)
SHORTCUTS = {
    "the textbook shortcut": [("OLD TEXT", "NEW TEXT")],
    "constant from memory instead of the printed one": [("KU = 1.486", "KU = 1.49")],
}


def count_wrong(out_dir):
    """Compare the shortcut's output file with engine.expected(); return (wrong, total)."""
    raise NotImplementedError


def main():
    src = (TASK / "solution" / "solve.py").read_text()
    caught = 0
    for name, edits in SHORTCUTS.items():
        # a shortcut keeps going where the reference would raise; replace raises with a fallback here
        s = src
        for a, b in edits:
            assert s.count(a) >= 1, (name, a)
            s = s.replace(a, b)
        try:
            out = run_solution(TASK, source=s)
        except Exception as e:                      # noqa: BLE001
            print(f"CRASHED ({type(e).__name__}: {str(e)[:80]})  {name}")
            caught += 1
            continue
        passed, failed = run_tests(TASK, out)
        wrong, total = count_wrong(out)
        caught += bool(failed)
        print(f"{'CAUGHT' if failed else 'MISSED'}  {wrong:4d} of {total} rows wrong  {name}")
    print(f"{caught} of {len(SHORTCUTS)} shortcuts caught")
    sys.exit(0 if caught == len(SHORTCUTS) else 1)


if __name__ == "__main__":
    main()
