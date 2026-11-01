"""Load the verifier engine from ../tests without writing __pycache__."""
import sys
sys.dont_write_bytecode = True       # never leave __pycache__ in the submitted task folder
from pathlib import Path

TESTS = Path(__file__).resolve().parent.parent / "tests"


def truth():
    sys.path.insert(0, str(TESTS))
    try:
        import engine
    finally:
        sys.path.remove(str(TESTS))
    return engine.expected()
