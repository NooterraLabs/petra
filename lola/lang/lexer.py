"""Tokenizer for .lola. Trusted front end.

Tokens: IDENT ([A-Za-z_][A-Za-z0-9_]*), NUMBER (optional sign, integer, decimal, or p/q;
never an exponent, so every literal is exact), STRING ("..." with \\" and \\\\ escapes),
punctuation { } ( ) [ ] , : . -> -- <= >= > %, and NEWLINE. Line ends are tokens
because a component block is a list of attribute lines; runs of blank lines and comment
lines collapse into one NEWLINE, and a NEWLINE inside ( ) or [ ] is dropped. Other
whitespace separates tokens. Comments run from # to end of line. Units are IDENTs (kN,
mm2, degC, Nm) or "%".
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Kind(Enum):
    IDENT = "ident"
    NUMBER = "number"
    STRING = "string"
    PUNCT = "punct"
    NEWLINE = "newline"
    EOF = "eof"


@dataclass(frozen=True, slots=True)
class Token:
    kind: Kind
    text: str
    line: int
    col: int


class LolaSyntaxError(ValueError):
    """Carries path, line, col and a message that names the expected token."""

    def __init__(self, path: str, line: int, col: int, message: str) -> None:
        super().__init__(f"{path}:{line}:{col}: {message}")
        self.path = path
        self.line = line
        self.col = col


def tokenize(text: str, path: str) -> tuple[Token, ...]:
    raise NotImplementedError
