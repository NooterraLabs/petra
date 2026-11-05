"""Check the LoLa v0 definition of done (docs/frame.md) item by item.

Usage: python scripts/predicate.py
Prints one line per item, VERIFIED or NOT VERIFIED, with the evidence, and exits 0 only if every item is VERIFIED.
"""
from __future__ import annotations

import ast
import glob
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES = {"R1", "R2", "R3", "R4", "R5", "R6"}


def run(args: list[str], timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, *args], cwd=ROOT, capture_output=True, text=True, timeout=timeout
    )


def tail(text: str, n: int = 3) -> str:
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    return " | ".join(lines[-n:])


def p1_tests() -> tuple[bool, str]:
    r = run(["-m", "unittest", "discover", "-s", "tests", "-t", "."])
    return r.returncode == 0 and "OK" in r.stderr, tail(r.stderr)


def check_examples() -> list[dict]:
    out = []
    for path in sorted(glob.glob(os.path.join(ROOT, "examples", "*.lola"))):
        r = run(["-m", "lola", "check", os.path.relpath(path, ROOT), "--json"])
        if r.returncode not in (0, 1):
            raise RuntimeError(f"{path}: exit {r.returncode}: {tail(r.stderr)}")
        out.append(json.loads(r.stdout))
    return out


def p2_verdicts(reports: list[dict]) -> tuple[bool, str]:
    statuses = [v["status"] for rep in reports for v in rep["verdicts"]]
    every_has_footprint = all("footprint" in v for rep in reports for v in rep["verdicts"])
    seen = {s: statuses.count(s) for s in ("PASS", "FAIL", "UNKNOWN")}
    ok = all(seen[s] > 0 for s in seen) and every_has_footprint and len(reports) > 0
    return ok, f"{len(reports)} files, verdicts {seen}, footprints on all: {every_has_footprint}"


def p3_kernel_stdlib() -> tuple[bool, str]:
    files = glob.glob(os.path.join(ROOT, "lola", "kernel", "**", "*.py"), recursive=True)
    if not files:
        return False, "no lola/kernel files"
    bad = []
    lines = 0
    for f in files:
        src = open(f, encoding="utf-8").read()
        lines += src.count("\n")
        for node in ast.walk(ast.parse(src)):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            for name in names:
                top = name.split(".")[0]
                if top not in sys.stdlib_module_names and top != "lola":
                    bad.append(f"{os.path.relpath(f, ROOT)} imports {name}")
                if top == "lola" and not name.startswith("lola.kernel"):
                    bad.append(f"{os.path.relpath(f, ROOT)} imports untrusted {name}")
    r = run(["-m", "unittest", "tests.test_kernel_mutations"])
    mut_ok = r.returncode == 0
    ok = not bad and mut_ok
    return ok, f"{len(files)} files, {lines} lines, non-stdlib imports: {bad or 'none'}, mutation suite: {tail(r.stderr, 1)}"


def p4_rules(reports: list[dict]) -> tuple[bool, str]:
    used = {rule for rep in reports for v in rep["verdicts"] for rule in v.get("rules", [])}
    return RULES <= used, f"rules exercised from .lola files: {sorted(used)}, missing: {sorted(RULES - used)}"


def p5_registry() -> tuple[bool, str]:
    r = run(["-m", "lola", "registry", "check"])
    t = run(["-m", "unittest", "tests.test_registry_consistency"])
    return r.returncode == 0 and t.returncode == 0, f"registry check exit {r.returncode}: {tail(r.stdout, 1)}; corruption tests: {tail(t.stderr, 1)}"


def p6_coverage(reports: list[dict]) -> tuple[bool, str]:
    unknown = [v for rep in reports for v in rep["verdicts"] if v["status"] == "UNKNOWN"]
    named = [o for v in unknown for o in v.get("obligations", [])]
    return bool(unknown) and all(v.get("obligations") for v in unknown), f"{len(unknown)} UNKNOWN verdicts, obligations named: {named[:3]}"


def p7_family_bench() -> tuple[bool, str]:
    r = run([os.path.join("scripts", "bench_family.py")])
    return r.returncode == 0 and "reuse" in r.stdout, tail(r.stdout, 4)


def p8_gym() -> tuple[bool, str]:
    r = run(["-m", "lola", "gym", "--episodes", "20", "--seed", "0"])
    return r.returncode == 0 and "solved" in r.stdout, tail(r.stdout, 3)


def main() -> int:
    results: list[tuple[str, bool, str]] = []

    def record(name, fn, *a):
        try:
            ok, ev = fn(*a)
        except Exception as e:  # a crash is a NOT VERIFIED item, not a crashed checker
            ok, ev = False, f"{type(e).__name__}: {e}"
        results.append((name, ok, ev))

    record("1 unit tests", p1_tests)
    try:
        reports = check_examples()
        err = None
    except Exception as e:
        reports, err = [], f"{type(e).__name__}: {e}"
    if err:
        for name in ("2 example verdicts", "4 rules end to end", "6 coverage"):
            results.append((name, False, err))
    else:
        record("2 example verdicts", p2_verdicts, reports)
        record("4 rules end to end", p4_rules, reports)
        record("6 coverage", p6_coverage, reports)
    record("3 kernel stdlib and mutations", p3_kernel_stdlib)
    record("5 registry consistency", p5_registry)
    record("7 family certification bench", p7_family_bench)
    record("8 gym and baseline agent", p8_gym)

    results.sort(key=lambda r: r[0])
    for name, ok, ev in results:
        print(f"{'VERIFIED    ' if ok else 'NOT VERIFIED'}  {name}: {ev}")
    return 0 if all(ok for _, ok, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main())
