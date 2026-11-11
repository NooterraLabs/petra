"""What the petra arm adds: the guide the agent is given, and `petra check` on what it hands in.

The agent may put a Petra design in a fenced block that opens with ```petra and its card in
one that opens with ```card. The harness takes the first of each out of the reply, runs
`python -m petra check` on them in an empty folder, and gives the report back before the
next attempt. The blocks are not part of the answer the benchmark grades.

Every reply of the petra arm is counted as one of:

    PASS FAIL UNKNOWN MARGINAL   Petra read the design and gave that status
    REFUSED                      Petra read it and refused it as an input error (exit code 3)
    DISAGREE                     the kernel rejected a proof the Python checker took (exit code 4)
    ERROR                        `petra check` crashed or ran past its time limit
    NONE                         the agent handed in no design, so Petra said nothing

Petra "said something" on the first five. Nothing here knows any benchmark.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from bench.exam.data import ROOT

GUIDE = ROOT / "petra" / "docs" / "skill.md"
SAID = ("PASS", "FAIL", "UNKNOWN", "MARGINAL", "REFUSED")
STATUSES = (*SAID, "DISAGREE", "ERROR", "NONE")
BY_EXIT = {0: "PASS", 1: "FAIL", 2: "UNKNOWN", 5: "MARGINAL", 3: "REFUSED", 4: "DISAGREE"}
LONGEST = 20000
"""A report longer than this, in characters, is cut before it goes back to the agent."""

_BLOCK = re.compile(r"^```[ \t]*(petra|card)[ \t]*\r?\n(.*?)^```[ \t]*$\r?\n?", re.M | re.S)

OFFER = """You also have Petra, a checker for engineering designs. Its guide is below. You cannot run commands here.
If something in this task can be written as a Petra design, you may hand one in with its card, after your answer:
the design in a fenced block that opens with ```petra, and the card in a fenced block that opens with ```card.
`petra check` is then run on them and you are shown its report before your final answer.
Handing them in is optional. The two blocks are not part of your answer to the task.

"""


@dataclass(frozen=True)
class Report:
    status: str               # one of STATUSES
    handed_in: bool           # the reply held a design
    design: str | None
    card: str | None
    exit: int | None
    text: str                 # what `petra check` printed, or why there is nothing
    seconds: float

    def to_dict(self) -> dict:
        return asdict(self)


def offer(guides: list[Path]) -> str:
    """The part of the prompt that only the petra arm gets."""
    return OFFER + "\n\n".join(path.read_text(encoding="utf-8").strip() for path in guides) + "\n"


def split(reply: str) -> tuple[str, str | None, str | None]:
    """The reply without its petra and card blocks, the first design and the first card."""
    found: dict[str, str] = {}
    for kind, body in _BLOCK.findall(reply):
        found.setdefault(kind, body)
    return _BLOCK.sub("", reply), found.get("petra"), found.get("card")


def scrub(text: str, *folders: Path) -> str:
    """The text with the paths of this machine taken out: the given folders, the
    repository and the home folder, written with either slash or with doubled backslashes.
    A home folder right under the root, such as /root, is left: it names nobody, and so
    short a text would be found in ordinary words."""
    home = [Path.home()] if len(Path.home().parts) >= 3 else []
    for folder in (*folders, ROOT, *home):
        for spelt in {str(folder), folder.as_posix(), str(folder).replace("\\", "\\\\")}:
            text = re.sub(re.escape(spelt), ".", text, flags=re.I)
    return text


def check(design: str | None, card: str | None, timeout: float) -> Report:
    """Run `petra check` on what was handed in."""
    if design is None:
        why = "No Petra design was handed in, so Petra said nothing."
        if card is not None:
            why = "A card was handed in with no design. Petra checks a design against a card, so it said nothing."
        return Report("NONE", False, None, card, None, why, 0.0)
    began = time.monotonic()
    # Petra runs inside the empty folder and is given names with no folder, so that no path
    # of this machine is in a report that goes back to a model.
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    with tempfile.TemporaryDirectory() as folder:
        (Path(folder) / "design.petra").write_text(design, encoding="utf-8", newline="\n")
        if card is not None:
            (Path(folder) / "design.card").write_text(card, encoding="utf-8", newline="\n")
        try:
            done = subprocess.run([sys.executable, "-m", "petra", "check", "design.petra"], cwd=folder, env=env, capture_output=True,
                                  text=True, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL, timeout=timeout)
        except subprocess.TimeoutExpired:
            return Report("ERROR", True, design, card, None, f"petra check did not finish within {timeout:.0f} s", time.monotonic() - began)
        text = scrub((done.stdout + done.stderr).strip(), Path(folder))
    status = BY_EXIT.get(done.returncode, "ERROR")
    first = text.splitlines()[0] if text else ""
    if status in ("PASS", "FAIL", "UNKNOWN", "MARGINAL") and not first.endswith(f": {status}"):
        status = "ERROR"      # an exit code a crash can give too: only a report's own first line makes it a status
    if len(text) > LONGEST:
        text = text[:LONGEST] + f"\n[the report goes on for {len(text) - LONGEST} more characters]"
    return Report(status, True, design, card, done.returncode, text, time.monotonic() - began)
