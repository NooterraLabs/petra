"""Run the corpus: check every design in expected.tsv and compare the verdict.

    python corpus/run.py [--jobs N] [--only TEXT]

Each line of expected.tsv names a design by its path from the repository root, the verdict
it must get, the wrong verdict the checker gives today when it gives one, and a note. The
verdict is the one `petra check` exits with. NOT_PASS stands for any of FAIL, UNKNOWN,
MARGINAL and INPUT_ERROR.

A run fails when a design gets a verdict that is neither the expected one nor the known
wrong one. It also fails when a known wrong verdict has come right, so that the line loses
its third field and the case cannot go wrong again without failing the run.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from petra.cli import EXIT_CODES  # noqa: E402

VERDICTS = {code: name for name, code in EXIT_CODES.items()}
NOT_PASS = frozenset({"FAIL", "UNKNOWN", "MARGINAL", "INPUT_ERROR"})
EXPECTABLE = frozenset({"PASS", "NOT_PASS"}) | NOT_PASS

LIMIT_S = 120
"""A check that runs this long counts as TIMEOUT. The slowest design in the corpus that
finishes took 28 s on a desktop busy with other runs, so this is about four times that."""


@dataclass(frozen=True)
class Case:
    path: str
    expect: str
    today: str
    note: str


def cases() -> list[Case]:
    out = []
    for number, line in enumerate((ROOT / "corpus" / "expected.tsv").read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        path, expect, today, note = (line.split("\t") + ["", ""])[:4]
        if expect not in EXPECTABLE or not (ROOT / path).is_file():
            raise SystemExit(f"expected.tsv:{number}: no such design, or no such verdict: {line}")
        out.append(Case(path, expect, today, note))
    return out


def verdict(case: Case) -> str:
    try:
        done = subprocess.run([sys.executable, "-m", "petra", "check", case.path], cwd=ROOT, timeout=LIMIT_S,
                              stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return "TIMEOUT"
    return VERDICTS.get(done.returncode, f"EXIT_{done.returncode}")


def meets(expect: str, got: str) -> bool:
    return got == expect or (expect == "NOT_PASS" and got in NOT_PASS)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 1)
    parser.add_argument("--only", default="", help="run the designs whose path contains TEXT")
    args = parser.parse_args()
    chosen = [c for c in cases() if args.only in c.path]
    with ThreadPoolExecutor(args.jobs) as pool:
        got = list(pool.map(verdict, chosen))
    known, fixed, wrong = [], [], []
    for case, found in zip(chosen, got):
        line = f"{case.path}: {found}, must be {case.expect}" + (f" ({case.note})" if case.note else "")
        if meets(case.expect, found):
            if case.today:
                fixed.append(f"{case.path}: now {found}. Remove {case.today} from its line.")
        elif found == case.today:
            known.append(line)
        else:
            wrong.append(line)
    for title, lines in (("known wrong verdict", known), ("came right", fixed), ("WRONG", wrong)):
        for line in lines:
            print(f"{title}: {line}")
    print(f"{len(chosen)} designs: {len(chosen) - len(known) - len(fixed) - len(wrong)} right, {len(known)} known wrong, "
          f"{len(fixed)} came right, {len(wrong)} wrong")
    return 1 if wrong or fixed else 0


if __name__ == "__main__":
    sys.exit(main())
