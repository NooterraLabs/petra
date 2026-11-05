"""The .lola design language. Trusted front end: text -> Design IR."""
from __future__ import annotations

from pathlib import Path

from ..ir import Design
from .lexer import LolaSyntaxError
from .lower import LoweringError


def parse_design(text: str, path: str, registry: object) -> Design:
    """Tokenize, parse and lower. Raises LolaSyntaxError or LoweringError; never returns a
    partial design."""
    raise NotImplementedError


def load_design(path: str | Path, registry: object | None = None) -> Design:
    """Read a .lola file (UTF-8) and parse it against the default registry when none is
    given."""
    raise NotImplementedError
