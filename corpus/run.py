"""Run the corpus: check every design in expected.tsv and compare the verdict.

    python corpus/run.py [--kernel BINARY] [--jobs N] [--only TEXT]

Each line of expected.tsv names a design by its path from the repository root, the verdict
it must get, the wrong verdict `petra check` gives today when it gives one, the wrong
verdict the kernel gives today when it gives one, and a note. The card a design answers
is the .card file beside it. NOT_PASS stands for any of FAIL, UNKNOWN, MARGINAL and
INPUT_ERROR.

Without --kernel the verdict is the one `petra check` exits with. With it, the pair is
exported (petra/export.py) and the verdict is the one that petra-verify binary exits
with, where ILL-FORMED reads as INPUT_ERROR. A pair the language refuses is INPUT_ERROR
too: the kernel reads files, and that text gives it none. The kernel sees the card and
the design before any physics runs, and the proofs only for a design it found well formed.
For a design of a deck of rules the export also writes rules.json, the deck's own file,
and the kernel gets it as --rules and works out the cells itself.

A run fails when a design gets a verdict that is neither the expected one nor the known
wrong one. It also fails when a known wrong verdict has come right, so that the line loses
that field and the case cannot go wrong again without failing the run.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial
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
    kernel: str
    note: str


def cases() -> list[Case]:
    out = []
    for number, line in enumerate((ROOT / "corpus" / "expected.tsv").read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        path, expect, today, kernel, note = (line.split("\t") + [""] * 3)[:5]
        if expect not in EXPECTABLE or not (ROOT / path).is_file():
            raise SystemExit(f"expected.tsv:{number}: no such design, or no such verdict: {line}")
        out.append(Case(path, expect, today, kernel, note))
    return out


def _run(command: list[str]) -> int | None:
    """The exit code, or None past the limit."""
    try:
        return subprocess.run(command, cwd=ROOT, timeout=LIMIT_S, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL).returncode
    except subprocess.TimeoutExpired:
        return None


def _verdict(code: int | None) -> str:
    return "TIMEOUT" if code is None else VERDICTS.get(code, f"EXIT_{code}")


def by_petra(case: Case) -> str:
    return _verdict(_run([sys.executable, "-m", "petra", "check", case.path]))


def by_kernel(binary: str, case: Case) -> str:
    """INPUT_ERROR when the language refuses the pair, and NO_FILES when the exporter
    fails any other way."""
    refused = EXIT_CODES["INPUT_ERROR"]
    with tempfile.TemporaryDirectory() as tmp:
        def verify(*names: str) -> str:
            there = [*names, *(["rules"] if Path(tmp, "rules.json").is_file() else [])]
            return _verdict(_run([binary, *(part for name in there for part in (f"--{name}", str(Path(tmp, f"{name}.json"))))]))

        export = [sys.executable, "-m", "petra.export", case.path, "--out", tmp]
        code = _run([*export, "--no-physics"])
        if code != 0:
            return "INPUT_ERROR" if code == refused else "NO_FILES"
        typed = verify("card", "design", "deck")
        if typed == "INPUT_ERROR":
            return typed
        code = _run(export)
        if code != 0:
            return "TIMEOUT" if code is None else "INPUT_ERROR" if code == refused else "NO_FILES"
        return verify("card", "design", "deck", "proofs")


def meets(expect: str, got: str) -> bool:
    return got == expect or (expect == "NOT_PASS" and got in NOT_PASS)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--kernel", metavar="BINARY", help="the petra-verify binary to take verdicts from")
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 1)
    parser.add_argument("--only", default="", help="run the designs whose path contains TEXT")
    args = parser.parse_args()
    chosen = [c for c in cases() if args.only in c.path]
    with ThreadPoolExecutor(args.jobs) as pool:
        got = list(pool.map(partial(by_kernel, str(Path(args.kernel).resolve())) if args.kernel else by_petra, chosen))
    known, fixed, wrong = [], [], []
    for case, found in zip(chosen, got):
        marked = case.kernel if args.kernel else case.today
        line = f"{case.path}: {found}, must be {case.expect}" + (f" ({case.note})" if case.note else "")
        if meets(case.expect, found):
            if marked:
                fixed.append(f"{case.path}: now {found}. Remove {marked} from its line.")
        elif found == marked:
            known.append(line)
        else:
            wrong.append(line)
    for title, lines in (("known wrong verdict", known), ("came right", fixed), ("WRONG", wrong)):
        for line in lines:
            print(f"{title}: {line}")
    print(f"{len(chosen)} designs by {'the kernel' if args.kernel else 'petra check'}: {len(chosen) - len(known) - len(fixed) - len(wrong)} right, "
          f"{len(known)} known wrong, {len(fixed)} came right, {len(wrong)} wrong")
    return 1 if wrong or fixed else 0


if __name__ == "__main__":
    sys.exit(main())
