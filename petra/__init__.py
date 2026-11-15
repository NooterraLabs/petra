"""Petra: a checker of physical designs against decks of rules.

    import petra
    result = petra.check(card, design)      # plain data: "status" is the kernel's verdict
    checked = petra.check_file("examples/deck/lap_pass.petra")      # against examples/deck/lap_pass.card
    print(checked.text())
    checked.status            # the kernel's verdict: PASS, PASS_WAIVED, FAIL or UNKNOWN
    checked.reason            # for a design with a part of a kind no deck has: why it reads UNKNOWN

The verdict of a design is the kernel's: petra-verify, built from kernel/ (petra/verify.py).
Everything in this package is untrusted. It parses the card and the design, writes the files
the kernel reads, searches for the hints of proofs.json, and words the report. A bug here
costs an input error, an UNKNOWN or a difference from the kernel, never a pass: nothing in
Python can print one.

petra/docs/api.md documents this API and the JSON `petra check --json` prints, and
`petra docs api` prints it from any install. `petra docs` lists every document, the
language reference among them.
"""
from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

__version__ = "0.1.2"

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
    cannot be taken, this raises petra.verify.NoVerdict."""
    from .pipeline import check_text

    return check_text(card, design, path).to_json()


def check_file(path: str | Path, *, card: str | Path | None = None) -> Any:
    """`check` of the design at `path` against `card`, the .card file beside it when none is
    named. Returns the checked pair (grid.Checked for a design of a deck of rules, and
    pipeline.Checked for one with a part of a kind no deck has): `status` is the kernel's
    verdict, `reason` says why a design no deck was read for is UNKNOWN, `to_json()` is
    what `petra check --json` prints and `text()` what `petra check` prints. `report` is the
    grid's working behind a design of a deck, which decides nothing.

    Raises what the pair raises when it is refused (lang.LolaSyntaxError,
    lang.LoweringError, files.ComponentError, OSError), and petra.verify.NoVerdict when
    there is no kernel to run or its answer cannot be taken."""
    from .files import read_pair
    from .pipeline import check_text

    asked, text = read_pair(path, card)
    return check_text(asked, text, str(path), card_path=None if card is None else str(card), raises=True)
