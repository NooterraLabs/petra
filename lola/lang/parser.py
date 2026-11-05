"""Recursive-descent parser for the grammar in syntax.py. Trusted front end.

One function per grammar rule. No backtracking beyond one token of lookahead, except the
claim rule, which looks for "P" "(" to pick the probability form. A leading IDENT that is
not in DECLS starts a component block; whether it names a registered kind is checked by
lower.py against models.KINDS, so the parser knows no component kind.
"""
from __future__ import annotations

from .lexer import Token
from .syntax import File, Node


class Parser:
    def __init__(self, tokens: tuple[Token, ...], path: str) -> None:
        raise NotImplementedError

    def file(self) -> File:
        raise NotImplementedError

    def decl(self) -> Node:
        """Dispatch on the leading keyword through DECLS; any other IDENT followed by an
        IDENT and "{" is a component block. Anything else raises LolaSyntaxError listing
        the keywords DECLS accepts."""
        raise NotImplementedError


DECLS: tuple[str, ...] = ("design", "param", "ambient", "load", "tests", "claim", "waive")
"""Design-level keywords. Component kinds are not here: they belong to the domains."""


def parse(text: str, path: str) -> File:
    raise NotImplementedError
