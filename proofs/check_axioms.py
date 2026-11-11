"""Build the proofs and hold them to Lean's three standard axioms.

    python proofs/check_axioms.py [--lake PATH] [--no-build]

Run after `lake exe cache get` in proofs/, which fetches Mathlib's prebuilt files. It

1. builds `PetraProofs` with lake, unless --no-build says it is built;
2. checks `PetraProofs/Axioms.lean`, which prints the axioms each main theorem rests on;
3. fails when a theorem rests on an axiom other than `propext`, `Classical.choice` and
   `Quot.sound`. `sorryAx`, the axiom of an unfinished proof, is one of the others;
4. fails when a theorem of MUST is not among those printed, so that a line dropped from
   Axioms.lean does not pass;
5. fails when a source file of the proofs, or one of the two kernel files they read, holds
   `sorry`, `admit` or an `axiom`, or when one of those kernel files holds a `partial def`,
   a `while`, or an attribute that gives a definition other code to run than the code the
   proofs read;
6. fails when docs/proved.md holds other lines than step 2 printed.

Prints the lines of step 2 as docs/proved.md holds them, and exits 0 when every check holds.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
KERNEL = HERE.parent / "kernel" / "Petra"
DOC = HERE.parent / "docs" / "proved.md"
STANDARD = ("propext", "Classical.choice", "Quot.sound")
MUST = ("Petra.Tape.proved_sound", "Petra.Tape.refuted_sound", "Petra.Tape.proved_sound_exact", "Petra.Tape.refuted_sound_exact",
        "Petra.Loops.isqrt_spec", "Petra.Loops.oddSeries_spec", "Petra.Loops.expAt_spec",
        "Petra.iSqrt_sound", "Petra.piIv_sound", "Petra.iLn_sound", "Petra.iExp_sound", "Petra.pick_sound", "Petra.Node.enclose_sound")
"""The theorems docs/proved.md states as the result, and the ones they stand on."""
READ = ("Num.lean", "Tape.lean")
"""The kernel files the proofs are about."""

UNFINISHED = re.compile(r"\b(sorry|admit)\b|^\s*(?:private\s+|protected\s+)?axiom\s", re.MULTILINE)
UNREADABLE = re.compile(r"\bpartial\s+def\b|\bwhile\b|\bunsafe\b|\bimplemented_by\b|\bextern\b|\bcsimp\b|\bopaque\b")
COMMENT = re.compile(r"/-.*?-/|--[^\n]*", re.DOTALL)
LINE = re.compile(r"'([^'\s]+)' (?:depends on axioms: \[(.*?)\]|does not depend on any axioms)", re.DOTALL)


def code(path: Path) -> str:
    """The file without its comments, which may say `sorry` or `while` in prose."""
    return COMMENT.sub("", path.read_text(encoding="utf-8"))


def sources() -> list[str]:
    """Each problem a source file has."""
    found = []
    for path in [*sorted(HERE.glob("*.lean")), *sorted((HERE / "PetraProofs").rglob("*.lean")), *(KERNEL / name for name in READ)]:
        text, name = code(path), path.relative_to(HERE.parent).as_posix()
        found += [f"{name}: holds `{match.group(0).strip()}`" for match in UNFINISHED.finditer(text)]
        if path.parent == KERNEL:
            found += [f"{name}: holds `{match.group(0)}`, which the proofs cannot read" for match in UNREADABLE.finditer(text)]
    return found


def printed(output: str) -> dict[str, list[str]]:
    """Each theorem `#print axioms` named, with the axioms it rests on: the standard three
    in their usual order, and then any other."""
    found = {}
    for name, axioms in LINE.findall(output):
        names = {a.strip() for a in axioms.split(",") if a.strip()}
        found[name] = [a for a in STANDARD if a in names] + sorted(names - set(STANDARD))
    return found


def line(name: str, axioms: list[str]) -> str:
    return f"'{name}' depends on axioms: [{', '.join(axioms)}]" if axioms else f"'{name}' does not depend on any axioms"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--lake", default="lake", help="the lake to run")
    parser.add_argument("--no-build", action="store_true", help="PetraProofs is built already")
    args = parser.parse_args()
    problems = sources()
    if not args.no_build:
        built = subprocess.run([args.lake, "build", "PetraProofs"], cwd=HERE)
        if built.returncode != 0:
            print("check_axioms: lake build PetraProofs failed", file=sys.stderr)
            return 1
    checked = subprocess.run([args.lake, "env", "lean", "PetraProofs/Axioms.lean"], cwd=HERE, capture_output=True, text=True, encoding="utf-8")
    output = checked.stdout + checked.stderr
    if checked.returncode != 0:
        problems.append(f"PetraProofs/Axioms.lean does not check (exit {checked.returncode}): {output.strip()[-400:]}")
    asked = re.findall(r"^#print axioms (\S+)", (HERE / "PetraProofs" / "Axioms.lean").read_text(encoding="utf-8"), re.MULTILINE)
    found = printed(output)
    lines = [line(name, found[name]) for name in asked if name in found]
    print("\n".join(lines))
    problems += [f"{name}: Axioms.lean asks for its axioms, and lean printed none" for name in asked if name not in found]
    problems += [f"{name}: rests on {', '.join(a for a in axioms if a not in STANDARD)}" for name, axioms in found.items() if set(axioms) - set(STANDARD)]
    problems += [f"{name}: Axioms.lean does not print its axioms" for name in MUST if name not in asked]
    documented = [line(name, axioms) for name, axioms in printed(DOC.read_text(encoding="utf-8")).items()]
    if documented != lines:
        problems.append("docs/proved.md holds other lines under \"The axioms\" than these: paste the lines above into it")
    for problem in problems:
        print(f"check_axioms: {problem}", file=sys.stderr)
    print(f"{len(found)} theorems, {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
