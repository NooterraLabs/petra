#!/usr/bin/env python3
"""Run the Python checker and the Lean checker on every file and report where they differ.

    python3 compare.py DIR_OR_FILE ... [--json OUT.json] [--strip PREFIX]

Two files agree when both say PROVED or neither does. The first lines are compared too. A
refusal for the file's form is worded differently by the two, so those count as the same
line when both refuse for the form.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PY = os.path.join(HERE, "reference", "check_clearance.py")
LEAN = os.path.join(HERE, ".lake", "build", "bin", "check-clearance")
FORM = "REFUSED: the file is not in the format"


def run(cmd: list[str]) -> tuple[bool, str]:
    p = subprocess.run(cmd, capture_output=True, text=True)
    out = p.stdout.strip().splitlines()
    first = out[0] if out else ""
    if p.returncode != 0 and not first.startswith("REFUSED"):
        first = FORM + " (it ended in an error)"
    return p.returncode == 0 and first.startswith("PROVED"), first


def main(argv: list[str]) -> int:
    out = None
    strip = HERE + os.sep
    paths: list[str] = []
    rest = argv[1:]
    while rest:
        a = rest.pop(0)
        if a == "--json":
            out = rest.pop(0)
        elif a == "--strip":
            strip = os.path.abspath(rest.pop(0)) + os.sep
        elif os.path.isdir(a):
            paths += sorted(os.path.join(a, f) for f in os.listdir(a) if f.endswith(".json"))
        else:
            paths.append(a)
    rows = []
    for path in paths:
        py_ok, py_line = run([sys.executable, PY, path])
        lean_ok, lean_line = run([LEAN, path])
        same_line = py_line == lean_line or (py_line.startswith(FORM) and lean_line.startswith(FORM))
        name = os.path.abspath(path)
        name = name[len(strip):] if name.startswith(strip) else (name[len(HERE) + 1:] if name.startswith(HERE + os.sep) else name)
        rows.append({"file": name, "python": "proved" if py_ok else "refused",
                     "lean": "proved" if lean_ok else "refused", "same_verdict": py_ok == lean_ok,
                     "same_line": same_line, "python_says": py_line, "lean_says": lean_line})
    differ = [r for r in rows if not r["same_verdict"]]
    worded = [r for r in rows if r["same_verdict"] and not r["same_line"]]
    print(f"{len(rows)} files: {sum(r['python'] == 'proved' for r in rows)} proved and "
          f"{sum(r['python'] == 'refused' for r in rows)} refused by Python; "
          f"{len(differ)} verdicts differ; {len(worded)} agree in verdict with a different first line")
    for r in differ:
        print(f"  DIFFER {r['file']}\n    python: {r['python_says']}\n    lean:   {r['lean_says']}")
    for r in worded:
        print(f"  worded {r['file']}\n    python: {r['python_says']}\n    lean:   {r['lean_says']}")
    if out:
        with open(out, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=1)
    return 1 if differ else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
