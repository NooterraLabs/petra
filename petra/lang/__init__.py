"""The Petra language. Trusted front end: the text of a card and of a design -> Design IR."""
from __future__ import annotations

from pathlib import Path

from ..files import card_of, read_pair, read_text
from ..ir import Design
from .lexer import LolaSyntaxError
from .lower import LoweringError, lower, lower_card
from .parser import parse


def parse_design(card: str, design: str, path: str, card_path: str | None = None) -> Design:
    """Tokenize, parse and lower the text of a card and of the design that answers it.
    `path` names the design in messages, and the card is the file beside it unless
    `card_path` says otherwise. Raises LolaSyntaxError or LoweringError; never returns a
    partial design."""
    return lower(parse(card, card_path or card_of(path), True), parse(design, path, False))


def load_design(path: str | Path, card: str | Path | None = None) -> Design:
    """Read a design file and its card, the .card file beside it unless `card` names
    another, and parse them."""
    return parse_design(*read_pair(path, card), str(path), None if card is None else str(card))


def load_card(card: str | Path) -> Design:
    """Read a card with no design, as a design of no component (lower.lower_card). What
    the card says of a component is then not checked against any."""
    return lower_card(parse(read_text(card), str(card), True))
