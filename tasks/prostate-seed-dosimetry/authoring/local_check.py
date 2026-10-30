#!/usr/bin/env python3
"""Run a task's reference solution and its tests without Docker and without a writable /app.

Usage:  python3 local_check.py tasks/<task-name>

It copies environment/data to a scratch folder, runs solution/solve.py with DATA and OUT redirected
there, then runs every test in tests/test_outputs.py with OUT redirected (oracle run), and again with
no output file (nop run). It needs no pytest: a tiny stand-in for pytest.fixture and
pytest.mark.parametrize is used, so it works in ChatGPT's and Claude's sandboxes.

Also importable: run_solution(task_dir, source=None) and run_tests(task_dir, out_dir), used by
calibrate.py to run shortcut versions of solve.py.
"""
import sys
sys.dont_write_bytecode = True       # never leave __pycache__ in the submitted task folder
import inspect
import shutil
import sys
import tempfile
import types
from pathlib import Path


def _stub_pytest():
    mod = types.ModuleType("pytest")

    def fixture(*args, **kwargs):
        if args and callable(args[0]):
            return args[0]
        return lambda f: f

    class Mark:
        def parametrize(self, name, values):
            def deco(f):
                f._params = (name, list(values))
                return f
            return deco

    mod.fixture = fixture
    mod.mark = Mark()
    return mod


def run_solution(task_dir, source=None):
    """Run solve.py (or a modified source text) on a scratch copy of the data. Returns the output dir."""
    task_dir = Path(task_dir)
    work = Path(tempfile.mkdtemp(prefix="localcheck_"))
    data = work / "data"
    shutil.copytree(task_dir / "environment" / "data", data)
    out = work / "output"
    out.mkdir()
    src = source if source is not None else (task_dir / "solution" / "solve.py").read_text()
    mod = types.ModuleType("solve_under_test")
    mod.__file__ = str(task_dir / "solution" / "solve.py")
    exec(compile(src, "solve.py", "exec"), mod.__dict__)
    mod.DATA, mod.OUT = data, out
    mod.main()
    return out


def run_tests(task_dir, out_dir):
    """Run every test function. Returns (passed, failed) lists of test names."""
    task_dir = Path(task_dir)
    tests_dir = task_dir / "tests"
    saved = sys.modules.get("pytest")
    sys.modules["pytest"] = _stub_pytest()
    sys.path.insert(0, str(tests_dir))
    for name in ("engine", "test_outputs"):
        sys.modules.pop(name, None)
    try:
        import test_outputs as t
    finally:
        sys.path.remove(str(tests_dir))
        if saved is not None:
            sys.modules["pytest"] = saved
        else:
            sys.modules.pop("pytest", None)
    t.OUT = Path(out_dir) / t.OUT.name
    fixtures = {n: f for n, f in vars(t).items() if callable(f) and not n.startswith("test_")
                and inspect.isfunction(f) and f.__module__ == t.__name__}
    cache = {}

    def resolve(name):
        if name not in cache:
            fn = fixtures[name]
            cache[name] = fn(*[resolve(p) for p in inspect.signature(fn).parameters])
        return cache[name]

    passed, failed = [], []
    for name, fn in vars(t).items():
        if not (name.startswith("test_") and inspect.isfunction(fn)):
            continue
        params = getattr(fn, "_params", None)
        cases = [(f"{name}[{v}]", {params[0]: v}) for v in params[1]] if params else [(name, {})]
        for label, extra in cases:
            try:
                args = [extra[p] if p in extra else resolve(p) for p in inspect.signature(fn).parameters]
                fn(*args)
                passed.append(label)
            except Exception as e:                      # noqa: BLE001
                failed.append(f"{label}: {type(e).__name__}: {str(e)[:200]}")
    return passed, failed


def main():
    task_dir = Path(sys.argv[1])
    out = run_solution(task_dir)
    passed, failed = run_tests(task_dir, out)
    print(f"ORACLE: {len(passed)} passed, {len(failed)} failed")
    for f in failed:
        print("  FAIL", f)
    empty = Path(tempfile.mkdtemp(prefix="localcheck_nop_"))
    passed, failed = run_tests(task_dir, empty)
    print(f"NOP:    {len(passed)} passed, {len(failed)} failed (must have at least one failure)")
    ok = not run_tests(task_dir, out)[1] and failed
    print("RESULT:", "OK" if ok else "PROBLEM")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
