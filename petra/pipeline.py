"""A card and a design, from their text to the kernel's verdict. Untrusted.

Three steps, and none of them decides anything:

1. Parse the pair (petra.lang). A pair the language refuses is an input error.
2. Find the deck of rules whose types its parts are (grid.owner), and have the Python
   reader work the design out against it (grid.check): its cells word the report, and its
   proofs go to the kernel as hints.
3. Hand the files to petra-verify and take its verdict (verify.ask). The kernel reads the
   deck and works out every cell itself, and `grid.checked` holds the reader's cells to the
   kernel's one by one.

A design with a part of a kind no shipped deck has cannot be worked out: there is no rule
to read. It still goes to the kernel, with its card, its quantities and no deck of rules.
The kernel holds the two to the type rules, works out no cell, and never passes such files
(kernel/Petra/Check.lean), so the design reads UNKNOWN with the reason that no deck has its
kind (verify.no_deck). Nothing in Python can print a pass: a status here is the kernel's
verdict, or INPUT_ERROR for a pair that was refused.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from . import export, grid, verify
from .files import HALF, ComponentError, card_of, headed
from .lang import LolaSyntaxError, LoweringError, parse_design

INPUT_ERRORS = (LolaSyntaxError, LoweringError, ComponentError)
"""What a pair raises when the language, a deck's types, the type rules or the kernel refuse
it. Every way into a check reports each as an input error."""

NO_DECK = "none: no deck of rules has this design's kinds of part, so the kernel worked out no cell"
"""The `path` line of a design the kernel was handed no deck of rules for."""


@dataclass(frozen=True)
class Checked:
    """A pair checked from its text that no deck of rules was read for: one the language or
    the kernel refused, with the `error` and nothing else, or a design with a part of a kind
    no shipped deck has, with what the kernel said of its files. A design of a deck's types
    gives a grid.Checked, which has the same members.

    `status` is INPUT_ERROR for a refused pair and else the kernel's verdict, which for
    these files is UNKNOWN: `ask` takes no pass from a kernel that was handed no deck of
    rules. `reason` says which kinds no deck has. `report` is None: there are no cells to
    report."""

    path: str
    error: str | None = None
    name: str = ""
    card: str = ""
    hashes: Mapping[str, str] | None = None
    kernel: Mapping[str, Any] | None = None
    kinds: tuple[str, ...] = ()
    report: None = None

    @property
    def status(self) -> str:
        return "INPUT_ERROR" if self.error is not None else verify.status(self.kernel)

    @property
    def reason(self) -> str | None:
        """Why the design reads UNKNOWN, and None for a pair that was refused."""
        return None if self.error is not None else verify.no_deck(self.kinds)

    def to_json(self) -> dict[str, Any]:
        """{"file", "status": "INPUT_ERROR", "error"} for a refused pair. Else the keys of a
        design of a deck (grid.Checked.to_json) that have a value here: no deck, no counts,
        and no cells."""
        if self.error is not None:
            return {"file": self.path, "status": "INPUT_ERROR", "error": self.error}
        return {"file": self.path, "design": self.name, "status": self.status, "reason": self.reason, "card": self.card, "hashes": dict(self.hashes),
                "path": "none", "kernel": dict(self.kernel), "kinds": list(self.kinds), "deck": None, "cells": [], "waived": []}

    def text(self) -> str:
        """What `petra check` prints: the kernel's verdict on the first line, the reason on
        the second, what the pair was checked against, and what the kernel said."""
        if self.error is not None:
            return f"{self.path}: INPUT_ERROR\n{self.error}"
        return "\n".join([headed(self.name, self.status), f"reason     {self.reason}", f"card       {self.hashes['card']}  {self.card}",
                          f"design     {self.hashes['design']}  {self.path}",
                          f"kernel     petra-verify gives {self.kernel['verdict']}: it was handed no deck of rules and worked out no cell",
                          f"path       {NO_DECK}"])


def undecked(design: Any, card: str, text: str, card_path: str) -> Checked:
    """The kernel's verdict on a design with a part of a kind no shipped deck has. Raises
    ComponentError for a pair the kernel finds ill formed, and verify.NoVerdict when there
    is no kernel to run, when it gives no answer, or when it gives these files any verdict
    but UNKNOWN: it was handed no cell, so it has none to refute."""
    known = grid.kinds()
    kernel = verify.need()
    said = verify.ask(kernel, export.bare(design))
    if said["verdict"] == "ILL-FORMED":
        raise ComponentError(verify.refusal(design.path, said))
    if said["verdict"] != "UNKNOWN" or said["cells"]:
        raise verify.BadAnswer(f"{design.path}: {kernel} printed {said['verdict']} with {len(said['cells'])} cells for files with no deck of rules and no "
                               "proofs, where petra-verify works out no cell and gives UNKNOWN")
    said = {"verdict": said["verdict"], "checked": 0, "hashes": {name: h for name, h in said["hashes"].items() if h is not None},
            "cells_from": said["cells_from"], "waived": said["waived"]}
    return Checked(design.path, None, design.name, card_path, {"card": export.sha256(card), "design": export.sha256(text)}, said,
                   tuple(sorted({c.kind for c in design.components.values() if c.kind not in known})))


def check_text(card: str, text: str, path: str, *, card_path: str | None = None, raises: bool = False) -> Checked | grid.Checked:
    """Check the design `text` against the card and take the kernel's verdict on it
    (verify.py). `path` names the design in messages, and `card_path` the card when it is
    not the file beside it. Raises verify.NoVerdict when there is no kernel to run or it
    gives no answer. A pair that is refused gives a Checked with the error, or with `raises`
    its own exception, one of INPUT_ERRORS."""
    for what, body in (("card", card), ("design", text)):
        if HALF.search(body):      # a text read from a file never holds one, and one given as text can
            problem = f"the {what} holds half a surrogate pair, which is no character: it cannot be written, so it has no hash"
            if raises:
                raise ComponentError((problem,))
            return Checked(path, problem)
    try:
        design = parse_design(card, text, path, card_path)
        verify.need()      # with no kernel there is no verdict, so nothing is searched for one
        rules = grid.owner(design)
        if rules is not None:
            return grid.checked(design, rules, card, text, card_path or card_of(path))
        return undecked(design, card, text, card_path or card_of(path))
    except INPUT_ERRORS as exc:
        if raises:
            raise
        return Checked(path, str(exc))
