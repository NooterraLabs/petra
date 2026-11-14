"""Plant a fault in a scratch copy of a reader, so that the attacker can be shown to find it.

    python3.11 -m bench.attack.plant FAULT SCRATCH_DIR

writes the copy under SCRATCH_DIR and prints the command that runs the attacker against it.
Nothing is changed in this checkout, and the copy is never committed. The faults:

  twin_lt      the third reading (bench/twin/verify.mjs): a proof needs the upper end of a root
               under zero, where the pages say at most zero. A design exactly on a limit is
               then open in the twin and proved in the others.
  unit         the Python reader (petra/units.py): the pound-force written with a standard
               gravity of 9.8 and not 9.80665 m/s2, so a kip, a ksi and a psi are 0.07 percent
               low in every number it converts.
  grid_line    the Python reader (petra/grid.py): the line of the grid for the flexure of the
               plies is left out of the cells of a part whose card waives it.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

FAULTS = {
    "twin_lt": ("bench/twin/verify.mjs", "        if (!v || v[1].n > 0n) return false;\n      }\n      return true;\n    }\n    if (!isObj(P)",
                "        if (!v || v[1].n >= 0n) return false;\n      }\n      return true;\n    }\n    if (!isObj(P)"),
    "unit": ("petra/units.py", "_LBF = _LB * Fraction(980665, 10**5)", "_LBF = _LB * Fraction(98, 10)"),
    "grid_line": ("petra/grid.py", "        for ask in (a for a in deck.asks if a.type == part.type.name):\n            anchor, line, prefer",
                  "        for ask in (a for a in deck.asks if a.type == part.type.name and not (a.mechanism == \"lap.ply_flexure\" and waived.get((part.name, a.mechanism)))):\n            anchor, line, prefer"),
}


def plant(fault: str, scratch: Path) -> str:
    path, old, new = FAULTS[fault]
    scratch.mkdir(parents=True, exist_ok=True)
    if path.startswith("petra/"):
        target = scratch / "petra"
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(ROOT / "petra", target, ignore=shutil.ignore_patterns("__pycache__", "bin"))
        file = scratch / path
    else:
        file = scratch / "verify.mjs"
        shutil.copy(ROOT / path, file)
    text = file.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"{fault}: the line to change is not there exactly once in {path}"
    file.write_text(text.replace(old, new), encoding="utf-8")
    if path.startswith("petra/"):
        return f"python3.11 -m bench.attack.run --petra {scratch} --out {scratch}/out --log {scratch}/log.jsonl --until verdict,cells,bundle,relation --budget 3000"
    return f"python3.11 -m bench.attack.run --twin {scratch}/verify.mjs --out {scratch}/out --log {scratch}/log.jsonl --until verdict,cells --budget 3000"


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in FAULTS:
        sys.exit(__doc__)
    print(plant(sys.argv[1], Path(sys.argv[2])))
