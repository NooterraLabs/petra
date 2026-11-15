"""The kernel's verdict on a design. Untrusted shell around petra-verify (kernel/).

The verdict of a check is the kernel's, and nothing here or in a caller gives one of its
own. `ask` writes the files of docs/format.md, runs the kernel on them and takes its answer
only when the answer holds together: one JSON object with one of the four verdicts, the exit
code of that verdict, and nothing on the error stream. Anything else raises NoVerdict, and
so does having no kernel to run. Every way into a check then reports that there is no
verdict: `petra check` prints nothing to stdout and exits 4, and the server's tool answers
with an error.

`status` is what a caller reports for an answer: the kernel's verdict, where a PASS with a
waiver the kernel lists reads PASS_WAIVED. A pair the kernel finds ill formed raises
ComponentError, the input error every caller reports. A design whose cells the kernel did
not work out from a deck of rules is never a pass: it reads UNKNOWN with the reason of
`no_deck`, or FAIL where the kernel checked a refutation.

For a design checked against a deck of rules the kernel reads the deck and works out every
cell itself, and `differs` compares its cells with the grid's, one by one. For a design of
the models' kinds the kernel has no deck of rules. It checks the tape of each proof the
Python checker wrote, and its verdict is then never PASS (kernel/Petra/Check.lean): the
Python checker chose the cells, and it decides nothing. A proof the kernel rejects after
the Python checker accepted it is a bug in one of the two, and raises Disagreement.
"""
from __future__ import annotations

import functools
import hashlib
import json
import os
import subprocess
import tempfile
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from . import export
from .models.base import ComponentError
from .verdict import Discharged, Refuted, WithinMargin

EXE = "petra-verify.exe" if os.name == "nt" else "petra-verify"

PACKAGED = Path(__file__).resolve().parent / "bin" / EXE
"""Where a wheel built for one platform carries the kernel (_build/petra_build.py). A wheel
built from an sdist carries none."""

BUILT = Path(__file__).resolve().parent.parent / "kernel" / ".lake" / "build" / "bin" / EXE
"""Where `lake build` puts the kernel in a source tree."""


EXITS: Mapping[str, int] = {"PASS": 0, "FAIL": 1, "UNKNOWN": 2, "ILL-FORMED": 3}
"""The four verdicts of the kernel, each with the code it exits with (kernel/Main.lean)."""


HASHED = ("card", "design", "deck", "rules")
"""The files whose hashes the kernel prints (kernel/Petra/Check.lean)."""

STATES = ("proved", "refuted", "not_applicable", "waived", "open")
"""The states the kernel settles a cell in (docs/format.md, proofs.json)."""

SHAPES: Mapping[str, tuple[str, ...]] = {"cells": ("subject", "mechanism", "entry", "state"), "findings": ("rule", "file", "item", "why"),
                                         "waived": ("subject", "mechanism", "by", "reason")}
"""The keys of each item of a list of the kernel's answer, each a text (kernel/Main.lean)."""


class NoVerdict(RuntimeError):
    """There is no verdict: no kernel ran, or what it answered cannot be taken. No caller
    gives a verdict of its own in its place."""


class NoKernel(NoVerdict):
    """There is no kernel to run, or the one that is named cannot be started."""


class BadAnswer(NoVerdict):
    """The kernel ran, and what it gave is not an answer: no JSON object, no verdict of the
    four, an exit code that is not its verdict's, or text on its error stream."""


class Disagreement(NoVerdict):
    """The kernel rejects a proof, a refutation or a waiver that the Python checker accepted,
    or its cells are not the grid's. It is a bug in one of the two, and the command line
    lets it through as a crash, with its traceback."""


@dataclass(frozen=True)
class Kernel:
    """What the kernel said of a design of the models' kinds. `verdict` is its own, and the
    design's status. `checked` of the `proofs` the Python checker's report rests on had a
    tape, which the kernel checked and accepted. `hashes` are of the files it read, by the
    names docs/format.md gives them: the kernel had no deck of rules, and its null for one
    is left out. `cells_from` is `proofs`, since it took the cells of proofs.json."""

    verdict: str
    checked: int
    proofs: int
    hashes: Mapping[str, str]
    cells_from: str = "proofs"

    def line(self) -> str:
        """What a report prints of the kernel. A refutation counts as a proof here."""
        rest = self.proofs - self.checked
        if not self.checked:
            tapes = f"it has no rule yet for any of the {self.proofs} proofs"
        else:
            tapes = f"it checked {self.checked} of {self.proofs} proofs" + (f" and has no rule yet for the other {rest}" if rest else "")
        return f"petra-verify gives {self.verdict}: {tapes}, and with no deck of rules for this design it passes nothing"

    def to_json(self) -> dict[str, Any]:
        return {"verdict": self.verdict, "checked": self.checked, "proofs": self.proofs, "hashes": dict(self.hashes), "cells_from": self.cells_from}


@functools.cache
def runs(kernel: str) -> bool:
    """Whether the kernel a wheel carries can run on this machine. A wheel's tag promises
    it on Linux and macOS, where an installer holds the glibc or the macOS to the tag, so
    there this only looks at the file's mode. A Windows tag names no version of Windows,
    and the kernel imports icu.dll, which Windows has carried since Windows 10 version
    1903. So on Windows this starts the kernel once: with no arguments it prints its usage
    and exits 64. A kernel that cannot run is warned of once and passed over: `binary` goes
    on to the one built in a source tree, and with none there a check has no kernel and
    gives no verdict. The answer is kept for the life of the process."""
    if os.name == "nt":
        import ctypes

        # Windows shows a box for a DLL it cannot find, and waits for a click. These three bits
        # of the error mode turn the box off, and the kernel's process inherits them.
        shown = ctypes.windll.kernel32.SetErrorMode(0x8003)
        try:
            ran = subprocess.run([kernel], stdin=subprocess.DEVNULL, capture_output=True, timeout=60).returncode == 64
        except (OSError, subprocess.TimeoutExpired):
            ran = False
        finally:
            ctypes.windll.kernel32.SetErrorMode(shown)
    else:
        ran = os.access(kernel, os.X_OK)
    if not ran:
        warnings.warn(f"{kernel} cannot run on this machine, so it is passed over", RuntimeWarning, stacklevel=3)
    return ran


def binary() -> str | None:
    """The kernel to run: the file PETRA_VERIFY names, else the one this package carries,
    else the one built in this source tree, else none."""
    named = os.environ.get("PETRA_VERIFY")
    if named:
        return named
    if PACKAGED.is_file() and runs(str(PACKAGED)):
        return str(PACKAGED)
    return str(BUILT) if BUILT.is_file() else None


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


def need() -> str:
    """The kernel to run, as `binary` finds it. Raises NoKernel when there is none."""
    kernel = binary()
    if kernel is None:
        raise NoKernel(f"there is no petra-verify to run, and nothing else gives a verdict. PETRA_VERIFY names none, this install "
                       f"carries none at {PACKAGED}, and none is built at {BUILT}")
    return kernel


def run(command: list[str]) -> tuple[int, bytes, bytes]:
    """Run the kernel: its exit code, what it printed and what it wrote to its error stream.
    The one place a kernel is started. Raises NoKernel for a file that cannot be started."""
    try:
        done = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True)
    except OSError as exc:
        raise NoKernel(f"{command[0]} cannot be run as petra-verify: {exc}") from None
    return done.returncode, done.stdout, done.stderr


def taken(kernel: str, code: int, out: bytes, err: bytes) -> dict[str, Any]:
    """The kernel's answer, when it is one: a JSON object with one of the four verdicts,
    printed by a kernel that exited with that verdict's code and wrote nothing to its error
    stream, whose cells, findings and waivers have their keys and whose verdict is the one
    those findings and cells give. A kernel that panics writes there and goes on, and one that is stopped exits
    with another code, so neither may be read past. A PASS is taken only with `cells_from`
    at `rules` and the hash of the deck of rules it read: the kernel gives none without a
    deck of rules, and one that did would be another kernel than this one. Raises BadAnswer."""
    if err:      # anything at all: a blank is not nothing, and this reads past none of it
        raise BadAnswer(f"{kernel} exited {code} and wrote to its error stream: {err.decode('utf-8', 'replace').strip()[-300:] or 'blanks'}")

    def once(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        """An object of the answer. The kernel writes each key once, and of a key written twice a reader would have to pick."""
        found = dict(pairs)
        if len(found) != len(pairs):
            raise ValueError("a key is written twice")
        return found

    try:
        said = json.loads(out.decode("utf-8"), object_pairs_hook=once)
    except (ValueError, RecursionError):
        raise BadAnswer(f"{kernel} exited {code} and printed no verdict, or one with a key written twice") from None
    if not isinstance(said, dict) or not isinstance(said.get("verdict"), str) or said["verdict"] not in EXITS:
        raise BadAnswer(f"{kernel} exited {code} and printed no verdict of {', '.join(EXITS)}")
    if code != EXITS[said["verdict"]]:
        raise BadAnswer(f"{kernel} printed {said['verdict']} and exited {code}, where {said['verdict']} exits {EXITS[said['verdict']]}")
    shape = {"hashes": dict, "cells_from": str, "findings": list, "waived": list, "cells": list}
    wrong = [key for key, kind in shape.items() if not isinstance(said.get(key), kind)]
    if wrong:
        raise BadAnswer(f"{kernel} printed {said['verdict']} without {', '.join(wrong)}")
    # Every cell, finding and waiver has the keys the kernel prints for it, each a text (kernel/Main.lean). A caller reads them
    # by name, so an answer that lacks one is not one to stop on with an error of Python's: it is no answer.
    for key, texts in SHAPES.items():
        if not all(isinstance(item, dict) and all(isinstance(item.get(name), str) for name in texts) for item in said[key]):
            raise BadAnswer(f"{kernel} printed {said['verdict']} with an item of {key} that lacks its {', '.join(texts)}")
    if not all(cell["state"] in STATES and isinstance(cell.get("reason", ""), str) for cell in said["cells"]):
        raise BadAnswer(f"{kernel} printed {said['verdict']} with a cell whose state is none of {', '.join(STATES)}")
    if not all(isinstance(name, str) and (h is None or isinstance(h, str)) for name, h in said["hashes"].items()):
        raise BadAnswer(f"{kernel} printed {said['verdict']} with a hash that is no text")
    # The verdict is what the findings and the cells of the same answer give (docs/format.md, The verdict): ILL-FORMED with
    # a finding and with no other, FAIL with a refuted cell and with no other, and PASS with no cell open.
    states = {cell["state"] for cell in said["cells"]}
    held = {"ILL-FORMED": bool(said["findings"]), "FAIL": not said["findings"] and "refuted" in states,
            "UNKNOWN": not said["findings"] and "refuted" not in states,
            "PASS": not said["findings"] and not states & {"refuted", "open"} and "proved" in states}
    if not held[said["verdict"]]:
        raise BadAnswer(f"{kernel} printed {said['verdict']}, which its own findings and cells do not give")
    if said["verdict"] == "PASS" and (said["cells_from"] != "rules" or not isinstance(said["hashes"].get("rules"), str)):
        raise BadAnswer(f"{kernel} printed PASS with no deck of rules, which petra-verify never does")
    return said


def ask(kernel: str, files: Mapping[str, str]) -> dict[str, Any]:
    """The kernel's answer to the files, each given as its text under its name. Raises
    NoVerdict when the kernel cannot be run or gives no answer (`taken`), and when it prints
    PASS for files that hold no deck of rules, whatever it says its cells came from."""
    with tempfile.TemporaryDirectory() as tmp:
        command = [kernel]
        for name, body in files.items():
            path = Path(tmp, f"{name}.json")
            path.write_text(body, encoding="utf-8", newline="\n")
            command += [f"--{name}", str(path)]
        code, out, err = run(command)
    said = taken(kernel, code, out, err)
    if said["verdict"] == "PASS" and "rules" not in files:
        raise BadAnswer(f"{kernel} printed PASS for files with no deck of rules, which petra-verify never does")
    # The answer is about the files it was handed: the kernel prints the hash of the bytes of each, with null for a deck of
    # rules it was given none of, and says where its cells came from. An answer with other hashes is about other files.
    handed = {name: (f"sha256:{hashlib.sha256(files[name].encode('utf-8')).hexdigest()}" if name in files else None) for name in HASHED}
    if said["hashes"] != handed:
        raise BadAnswer(f"{kernel} printed the hashes of other files than the ones it was handed")
    if said["cells_from"] != ("rules" if "rules" in files else "proofs"):
        raise BadAnswer(f"{kernel} says its cells are from {said['cells_from']}, which is not what it was handed")
    return said


def status(said: Mapping[str, Any]) -> str:
    """What every way into a check reports for the kernel's answer to a pair it found well
    formed: the kernel's verdict. A PASS reads PASS_WAIVED when the kernel lists a waiver
    that a cell rests on, by the kernel's own list and no other. The waived pass is to be
    retired, and until then a pass that rests on a signature is not printed as a plain one."""
    return "PASS_WAIVED" if said["verdict"] == "PASS" and said["waived"] else said["verdict"]


def no_deck(kinds: Any) -> str:
    """Why a design whose cells the kernel did not work out from a deck of rules reads
    UNKNOWN: its kinds of part, which no deck of rules has. Every way into a check gives
    this reason with the status."""
    names = sorted(set(kinds))
    of = f"a part of kind {', '.join(names)}" if names else "the parts of this design"
    return f"no deck of rules has {of}, so the kernel worked out none of its checks and nothing can pass it"


def held(status: str) -> str:
    """A status of the Python checker as it is printed outside a check: in a recall, in a
    calculation package, in the JSON under the kernel's verdict. It is no verdict, and its
    PASS and MARGINAL are no pass of a design that has no deck of rules: each reads UNKNOWN.
    FAIL and UNKNOWN stand."""
    return status if status in ("FAIL", "UNKNOWN") else "UNKNOWN"


def refusal(path: str, said: Mapping[str, Any]) -> tuple[str, ...]:
    """Why the kernel finds the files of the design at `path` ill formed: each finding it
    kept, and how many more it counted (docs/format.md, "Limits")."""
    more = said.get("more_findings", 0)
    return (*(f"{path}: petra-verify refuses the {f['file']}: {f['item']}: {f['why']}" for f in said["findings"]),
            *([f"{path}: petra-verify refuses it for {more} more reasons"] if more else []))


def differs(mine: list[tuple[str, str, str, str]], status: str, rules: str, said: Mapping[str, Any], waived: list[Mapping[str, str]],
            completions: list[Mapping[str, Any] | None] | None = None) -> str:
    """Where the kernel's answer to a design checked against a deck of rules differs from
    the grid's (grid.py). `mine` is the grid's cells in order, each its subject, mechanism,
    entry and state, `status` its verdict, `rules` the hash of the deck's file and `waived`
    the waivers its cells rest on, as Report.waived lists them. `completions`, when given,
    is what each cell rests on, as Report.completions lists them. The kernel works the cells
    out itself, so every cell is the same at the same place, rests on the same completion,
    and the two list the same waivers, or this says which is not. Empty when the two agree."""
    its = [(c["subject"], c["mechanism"], c["entry"], c["state"]) for c in said["cells"]]
    found = [f"cell {n}: the grid has {'/'.join(a)} and petra-verify {'/'.join(b)}" + (f" ({c['reason']})" if c.get("reason") else "")
             for n, (a, b, c) in enumerate(zip(mine, its, said["cells"])) if a != b]
    found += [f"cell {n}: the grid rests it on {json.dumps(a)} and petra-verify on {json.dumps(c.get('completion'))}"
              for n, (a, c) in enumerate(zip(completions or [], said["cells"])) if a != c.get("completion")]
    if len(mine) != len(its):
        found.append(f"the grid has {len(mine)} cells and petra-verify {len(its)}")
    if said["verdict"] != status:
        found.append(f"the grid gives {status} and petra-verify {said['verdict']}")
    if said.get("waived") != waived:
        found.append(f"the grid rests cells on {len(waived)} waivers and petra-verify on {len(said.get('waived') or [])}, or on others")
    if said["hashes"].get("rules") != rules:
        found.append(f"petra-verify read the rules {said['hashes'].get('rules')}, and the deck is {rules}")
    if said.get("cells_from") != "rules":
        found.append(f"petra-verify took its cells from {said.get('cells_from')} and not from the deck of rules")
    return "; ".join(found)


def verify(design: Any, registry: Any, report: Any, proofs: export.Proofs) -> Kernel:
    """The kernel's verdict on a design of the models' kinds, with the proofs of the Python
    checker's `report` as its cells. Raises NoVerdict when there is no kernel to run or it
    gives no answer."""
    kernel = need()
    files = export.bundle(design, registry, report, proofs)
    said = ask(kernel, files)
    if said["verdict"] == "ILL-FORMED":
        raise ComponentError(refusal(design.path, said))
    if said["verdict"] == "PASS":      # `ask` refuses it too: these files hold no deck of rules
        raise BadAnswer(f"{design.path}: {kernel} printed PASS for a design with no deck of rules, which petra-verify never does")
    cells = json.loads(files["proofs"])["cells"]
    rejected = [f"{mine['subject']}/{mine['mechanism']}/{mine['entry']}: {its.get('reason', its['state'])}"
                for mine, its in zip(cells, said["cells"]) if ("tape" in mine or mine["state"] == "waived") and its["state"] != mine["state"]]
    if rejected or len(cells) != len(said["cells"]):
        raise Disagreement(f"{design.path}: petra-verify does not accept what the Python checker did: {'; '.join(rejected) or 'it read other cells'}")
    return Kernel(status(said), sum("tape" in cell for cell in cells), behind(report), {name: h for name, h in said["hashes"].items() if h is not None},
                  said["cells_from"])
