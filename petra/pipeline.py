"""A card and a design, from their text to the kernel's verdict. Untrusted.

Three steps, and none of them decides anything:

1. Parse the pair (petra.lang). A pair the language refuses is an input error.
2. Find the deck of rules whose types its parts are (grid.owner), and have the Python
   reader work the design out against it (grid.check): its cells word the report, and its
   proofs go to the kernel as hints.
3. Hand the files to petra-verify and take its verdict (verify.ask). The kernel reads the
   deck and works out every cell itself, and `grid.checked` holds the reader's cells to the
   kernel's one by one.

A design none of whose parts is of a deck's type cannot be checked: there is no rule to
read, and no type that says what its lines mean. The kernel is not asked about it, so it
reads the same with a kernel and without one: UNKNOWN, with the reason that no deck has its
kinds (verify.no_deck). Beside INPUT_ERROR that is the one status Python gives on its own,
and it is never a pass or a fail.

No status given here is a pass or a fail but the kernel's own. A bug in step 1 or in the
files of step 3 gives the kernel other files than the pair's, and the verdict is then about
those files: `kernel.hashes` of the JSON names the files the kernel read, and the report's
`card` and `design` lines name the two texts.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from . import export, grid, verify
from .files import HALF, MAX_PROBLEMS, ComponentError, card_of, headed
from .lang import LolaSyntaxError, LoweringError, parse_design

INPUT_ERRORS = (LolaSyntaxError, LoweringError, ComponentError)
"""What a pair raises when the language, a deck's types, the type rules or the kernel refuse
it. Every way into a check reports each as an input error."""

NO_DECK = "none: no deck of rules has this design's kinds of part, so there was nothing to hand the kernel"
"""The `path` line of a design no deck of rules was read for."""


@dataclass(frozen=True)
class Checked:
    """A pair checked from its text that no deck of rules was read for: one the language
    refused, with the `error` and nothing else, or a design none of whose parts is of a
    deck's type. A design of a deck's types gives a grid.Checked, which has the same members.

    `status` is INPUT_ERROR for a refused pair and else UNKNOWN: nothing can pass or fail a
    design that no rule reads. `reason` says which kinds no deck has. `report` and `kernel`
    are None: there are no cells, and the kernel was not asked."""

    path: str
    error: str | None = None
    name: str = ""
    card: str = ""
    hashes: Mapping[str, str] | None = None
    kinds: tuple[str, ...] = ()
    report: None = None
    kernel: None = None

    @property
    def status(self) -> str:
        return "INPUT_ERROR" if self.error is not None else "UNKNOWN"

    @property
    def reason(self) -> str | None:
        """Why the design reads UNKNOWN, and None for a pair that was refused."""
        return None if self.error is not None else verify.no_deck(self.kinds)

    def to_json(self) -> dict[str, Any]:
        """{"file", "status": "INPUT_ERROR", "error"} for a refused pair. Else the keys of a
        design of a deck (grid.Checked.to_json) that have a value here: no deck, no kernel,
        no counts, and no cells. `kinds` holds at most MAX_PROBLEMS of the kinds, each cut as
        the reason cuts it, and `more_kinds` how many more there are."""
        if self.error is not None:
            return {"file": self.path, "status": "INPUT_ERROR", "error": self.error}
        return {"file": self.path, "design": self.name, "status": self.status, "reason": self.reason, "card": self.card, "hashes": dict(self.hashes),
                "path": "none", "kernel": None, "kinds": [verify.clipped(k) for k in self.kinds[:MAX_PROBLEMS]],
                "more_kinds": max(0, len(self.kinds) - MAX_PROBLEMS), "deck": None, "cells": [], "waived": []}

    def text(self) -> str:
        """What `petra check` prints: UNKNOWN on the first line, the reason on the second,
        and what the pair was."""
        if self.error is not None:
            return f"{self.path}: INPUT_ERROR\n{self.error}"
        return "\n".join([headed(self.name, self.status), f"reason     {self.reason}", f"card       {self.hashes['card']}  {self.card}",
                          f"design     {self.hashes['design']}  {self.path}", f"path       {NO_DECK}"])


def check_text(card: str, text: str, path: str, *, card_path: str | None = None, raises: bool = False) -> Checked | grid.Checked:
    """Check the design `text` against the card and take the kernel's verdict on it
    (verify.py). `path` names the design in messages, and `card_path` the card when it is
    not the file beside it. For a design of a deck's types it raises verify.NoVerdict when
    there is no kernel to run or it gives no answer. A pair that is refused gives a Checked
    with the error, or with `raises` its own exception, one of INPUT_ERRORS."""
    for what, body in (("card", card), ("design", text)):
        if HALF.search(body):      # a text read from a file never holds one, and one given as text can
            problem = f"the {what} holds half a surrogate pair, which is no character: it cannot be written, so it has no hash"
            if raises:
                raise ComponentError((problem,))
            return Checked(path, problem)
    try:
        design = parse_design(card, text, path, card_path)
        rules = grid.owner(design)
        if rules is not None:
            verify.need()      # with no kernel there is no verdict, so nothing is searched for one
            return grid.checked(design, rules, card, text, card_path or card_of(path))
        kinds = tuple(sorted({c.kind for c in design.components.values()}))      # none of them is a deck's, or `owner` had refused the mix
        return Checked(design.path, None, design.name, card_path or card_of(path), {"card": export.sha256(card), "design": export.sha256(text)}, kinds)
    except INPUT_ERRORS as exc:
        if raises:
            raise
        return Checked(path, str(exc))
