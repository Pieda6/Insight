#!/usr/bin/env python3
"""Shortcut calibration (dev only, never uploaded): each shortcut is a small edit of the reference
solution that encodes a common misreading. Every shortcut must fail at least one test.

Usage:  python3 tools/<task>/calibrate.py
Put local_check.py next to this file (or adjust the import path).
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from local_check import run_solution, run_tests  # noqa: E402

TASK = HERE.parents[1] / "tasks" / HERE.name                    # tools/<task>/ -> tasks/<task>/
SRC = (TASK / "solution" / "solve.py").read_text()

# name -> list of (exact text in solve.py, replacement). Each old text must appear in solve.py.
SHORTCUTS = {
    "boundary: >= read as >": [("if driven >= LIMIT", "if driven > LIMIT")],
    "exception X ignored": [("if exception_applies(rec):", "if False:")],
    # ... 20 to 40 of these, one or more per rule family
}


def main():
    out = run_solution(TASK)
    passed, failed = run_tests(TASK, out)
    print("oracle:", "OK" if not failed else failed)
    all_fail = True
    for name, edits in SHORTCUTS.items():
        src = SRC
        for old, new in edits:
            assert old in src, f"{name}: text not found in solve.py: {old!r}"
            src = src.replace(old, new)
        try:
            out = run_solution(TASK, src)
            _, failed = run_tests(TASK, out)
        except Exception as e:                          # a crash also counts as failing
            failed = [f"crash: {e}"]
        families = [f.split(":")[0] for f in failed if "rule_family" in f]
        all_fail &= bool(failed)
        print(f"{'ok ' if failed else '!! PASSES'} {name:60s} {families}")
    print("ALL SHORTCUTS FAIL" if all_fail else "SOME SHORTCUT PASSES: add a hand-worked case that separates it")


if __name__ == "__main__":
    main()
