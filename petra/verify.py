"""The kernel's word on a checked design. Untrusted shell around petra-verify (kernel/).

`verify` writes the files of docs/format.md for a report, runs the kernel on them and reads
its answer. The kernel checks again every proof it has a rule for. Where it has none, the
Python checker's word stands alone, and `Kernel.proofs - Kernel.checked` counts those
proofs. A proof the kernel rejects after the Python checker accepted it is a bug in one of
the two, and raises Disagreement, which no caller catches. A pair the kernel finds ill
formed raises ComponentError, the input error every caller reports.

For a design checked against a deck of rules the kernel reads the deck and works out every
cell itself, and `differs` compares its cells with the grid's, one by one.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from . import export
from .models.base import ComponentError
from .verdict import Discharged, Refuted, WithinMargin

BUILT = Path(__file__).resolve().parent.parent / "kernel" / ".lake" / "build" / "bin" / ("petra-verify.exe" if os.name == "nt" else "petra-verify")
"""Where `lake build` puts the kernel in a source tree."""


NO_KERNEL = "not run: there is no petra-verify here, so the Python checker alone stands behind this verdict"
"""What a report says in place of the kernel's word. PETRA_VERIFY names a kernel to run."""


class Disagreement(RuntimeError):
    """The kernel rejects a proof, a refutation or a waiver that the Python checker accepted."""


@dataclass(frozen=True)
class Kernel:
    """What the kernel said of one report. `checked` of the `proofs` the report's verdict
    rests on went through the kernel, which accepted each. `hashes` are of the files it
    read, by the names docs/format.md gives them."""

    verdict: str
    checked: int
    proofs: int
    hashes: Mapping[str, str]

    def line(self, status: str) -> str:
        """What a report prints of the kernel, for a design whose status is `status`. A
        refutation counts as a proof here."""
        rest = self.proofs - self.checked
        if not self.checked:
            said = [f"petra-verify has no rule yet for any of the {self.proofs} proofs"]
        else:
            said = [f"petra-verify checked {self.checked} of {self.proofs} proofs and agrees", *([f"it has no rule yet for the other {rest}"] if rest else [])]
        if self.verdict != status:
            said.append(f"its own verdict is {self.verdict}")
        return "; ".join(said)

    def to_json(self) -> dict[str, Any]:
        return {"verdict": self.verdict, "checked": self.checked, "proofs": self.proofs, "hashes": dict(self.hashes)}


def binary() -> str | None:
    """The kernel to run: the file PETRA_VERIFY names, else the one built in this source
    tree, else none."""
    return os.environ.get("PETRA_VERIFY") or (str(BUILT) if BUILT.is_file() else None)


def behind(report: Any) -> int:
    """How many proofs and refutations the report's verdict rests on: each obligation's
    own, its margin's, and one per validity row of its model."""
    count = 0
    for outcome in report.outcomes:
        count += len(getattr(outcome, "validity", ()))
        if isinstance(outcome, (Discharged, Refuted)):
            count += 1 + (getattr(outcome, "margin_theorem", None) is not None)
        elif isinstance(outcome, WithinMargin):
            count += 1 + (outcome.theorem is not None)
    return count


def ask(kernel: str, files: Mapping[str, str]) -> dict[str, Any]:
    """The kernel's answer to the files, each given as its text under its name."""
    with tempfile.TemporaryDirectory() as tmp:
        command = [kernel]
        for name, body in files.items():
            path = Path(tmp, f"{name}.json")
            path.write_text(body, encoding="utf-8", newline="\n")
            command += [f"--{name}", str(path)]
        done = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True)
    try:
        return json.loads(done.stdout.decode("utf-8"))
    except ValueError:
        raise RuntimeError(f"{kernel} exited {done.returncode} with no verdict: {done.stderr.decode('utf-8', 'replace')[-300:]}") from None


def refusal(path: str, said: Mapping[str, Any]) -> tuple[str, ...]:
    """Why the kernel finds the files of the design at `path` ill formed: each finding it
    kept, and how many more it counted (docs/format.md, "Limits")."""
    more = said.get("more_findings", 0)
    return (*(f"{path}: petra-verify refuses the {f['file']}: {f['item']}: {f['why']}" for f in said["findings"]),
            *([f"{path}: petra-verify refuses it for {more} more reasons"] if more else []))


def differs(mine: list[tuple[str, str, str, str]], status: str, rules: str, said: Mapping[str, Any]) -> str:
    """Where the kernel's answer to a design checked against a deck of rules differs from
    the grid's (grid.py). `mine` is the grid's cells in order, each its subject, mechanism,
    entry and state, `status` its verdict and `rules` the hash of the deck's file. The
    kernel works the cells out itself, so every cell is the same at the same place, or
    this says which is not. Empty when the two agree."""
    its = [(c["subject"], c["mechanism"], c["entry"], c["state"]) for c in said["cells"]]
    found = [f"cell {n}: the grid has {'/'.join(a)} and petra-verify {'/'.join(b)}" + (f" ({c['reason']})" if c.get("reason") else "")
             for n, (a, b, c) in enumerate(zip(mine, its, said["cells"])) if a != b]
    if len(mine) != len(its):
        found.append(f"the grid has {len(mine)} cells and petra-verify {len(its)}")
    if said["verdict"] != status:
        found.append(f"the grid gives {status} and petra-verify {said['verdict']}")
    if said["hashes"].get("rules") != rules:
        found.append(f"petra-verify read the rules {said['hashes'].get('rules')}, and the deck is {rules}")
    return "; ".join(found)


def verify(design: Any, registry: Any, report: Any, proofs: export.Proofs) -> Kernel | None:
    """The kernel's word on `report`, or None when there is no kernel to run."""
    kernel = binary()
    if kernel is None:
        return None
    files = export.bundle(design, registry, report, proofs)
    said = ask(kernel, files)
    if said["verdict"] == "ILL-FORMED":
        raise ComponentError(refusal(design.path, said))
    cells = json.loads(files["proofs"])["cells"]
    rejected = [f"{mine['subject']}/{mine['mechanism']}/{mine['entry']}: {its.get('reason', its['state'])}"
                for mine, its in zip(cells, said["cells"]) if ("tape" in mine or mine["state"] == "waived") and its["state"] != mine["state"]]
    if rejected or len(cells) != len(said["cells"]):
        raise Disagreement(f"{design.path}: petra-verify does not accept what the Python checker did: {'; '.join(rejected) or 'it read other cells'}")
    return Kernel(said["verdict"], sum("tape" in cell for cell in cells), behind(report), said["hashes"])
