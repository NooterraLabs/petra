"""`python3.11 -m bench.attack.summary OUT`: what a run kept, one line for each folder, the worst first.

A difference in which one reader says PASS comes first, then the other differences of verdict
and of cells, then crashes and hangs, then the relations, and last the differences of wording.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ORDER = ["falsepass", "verdict", "cells", "refusal", "crash", "hang", "bundle", "relation", "waived", "findings", "reason"]


def rows(out: Path) -> list[dict]:
    found = []
    for folder in sorted((out / "found").glob("*")):
        try:
            case = json.loads((folder / "case.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        verdicts = set(case.get("verdicts", {}).values())
        case["folder"] = folder.name
        case["class"] = "falsepass" if case["kind"] in ("verdict", "relation", "refusal") and "PASS" in verdicts and len(verdicts) > 1 else case["kind"]
        found.append(case)
    return sorted(found, key=lambda c: (ORDER.index(c["class"]) if c["class"] in ORDER else 99, -c.get("count", 1)))


def main(argv: list[str]) -> int:
    for c in rows(Path(argv[0])):
        print(f"{c['folder']:<22} x{c.get('count', 1):<4} {c['where']:<12} {c['recipe']:<9} {c['detail'][:150]!r} {c.get('verdicts', {})}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
