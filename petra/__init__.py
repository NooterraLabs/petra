"""Petra: a checker of physical designs against decks of rules.

    import petra
    result = petra.check(card, design)      # plain data: "status" is the kernel's verdict, or UNKNOWN for a design no deck has
    checked = petra.check_file("examples/deck/lap_pass.petra")      # against examples/deck/lap_pass.card
    print(checked.text())
    checked.status            # PASS, PASS_WAIVED, FAIL or UNKNOWN: the kernel's verdict for a design of a deck
    checked.reason            # for a design no deck has: why it reads UNKNOWN

The verdict of a design is the kernel's: petra-verify, built from kernel/ (petra/verify.py).
This package parses the card and the design, writes the files the kernel reads, searches for
the hints of proofs.json, and words the report. No way into a check gives a pass or a fail
of its own. A bug in the reader of a deck costs an UNKNOWN or a difference from the kernel.
A bug in the language, the units or the exporter gives the kernel other files than the
pair's, and the verdict is then about those files: `kernel.hashes` of the JSON names them,
and the `card` and `design` lines of the text name the two texts.

petra/docs/api.md documents this API and the JSON `petra check --json` prints, and
`petra docs api` prints it from any install. `petra docs` lists every document, the
language reference among them.
"""
from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

__version__ = "0.3.0"

_API = {"load_design": "lang", "parse_design": "lang", "check_text": "pipeline"}
"""Each name of the API that a submodule defines. A name is imported when first read, and
so is a submodule such as petra.grid, so `petra mcp` answers its handshake without loading
the language or the grid."""

__all__ = ["check", "check_file", *_API]


def __getattr__(name: str) -> Any:
    if name in _API:
        value = getattr(importlib.import_module(f".{_API[name]}", __name__), name)
    else:
        try:
            value = importlib.import_module(f".{name}", __name__)
        except ModuleNotFoundError as exc:
            if exc.name != f"{__name__}.{name}":
                raise
            raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    globals()[name] = value
    return value


def check(card: str, design: str, *, path: str = "<design>") -> dict:
    """Check a design against a card, both given as text, and return plain data that
    json.dumps takes as it is: what `petra check --json` prints (petra/docs/api.md). A pair
    that is refused gives {"file", "status": "INPUT_ERROR", "error"} instead of raising.
    The status is the verdict of petra-verify: with no kernel to run, or one whose answer
    cannot be taken, this raises petra.verify.NoVerdict. A design none of whose parts is
    of a deck's type is UNKNOWN without the kernel being asked."""
    from .pipeline import check_text

    return check_text(card, design, path).to_json()


def check_file(path: str | Path, *, card: str | Path | None = None) -> Any:
    """`check` of the design at `path` against `card`, the .card file beside it when none is
    named. Returns the checked pair (grid.Checked for a design of a deck of rules, and
    pipeline.Checked for one no deck has): `status` is the kernel's verdict, or UNKNOWN for
    a design no deck has, `reason` says why such a design is UNKNOWN, `to_json()` is
    what `petra check --json` prints and `text()` what `petra check` prints. `report` is the
    grid's working behind a design of a deck, which decides nothing.

    Raises what the pair raises when it is refused (lang.LolaSyntaxError,
    lang.LoweringError, files.ComponentError, OSError), and petra.verify.NoVerdict when
    there is no kernel to run or its answer cannot be taken."""
    from .files import read_pair
    from .pipeline import check_text

    asked, text = read_pair(path, card)
    return check_text(asked, text, str(path), card_path=None if card is None else str(card), raises=True)
