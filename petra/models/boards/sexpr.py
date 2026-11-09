"""KiCad s-expression text to a tree. Trusted; the boundary for board files.

A list is an `Expr`. An atom is a `Symbol`, a bare token such as a keyword or a number as
written, or a `Text`, a double-quoted string with its escapes undone. Numbers stay as written
and `number` reads them exactly, so 25.1 is 251/10. KiCad writes plain decimals and never an
exponent (dev-docs.kicad.org, s-expression format, "Syntax"), so an exponent is refused.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction

from ..base import ComponentError


class BoardError(ComponentError):
    """A board file Petra refuses. The message names the file, the line where it can, and
    the rule broken."""

    def __init__(self, path: str, problem: str) -> None:
        super().__init__((f"{path}: {problem}",))


class Symbol(str):
    """A bare token."""


class Text(str):
    """A quoted string."""


@dataclass(frozen=True)
class Expr:
    items: tuple[Symbol | Text | Expr, ...]
    line: int

    @property
    def head(self) -> str:
        return self.items[0] if self.items and isinstance(self.items[0], Symbol) else ""

    @property
    def args(self) -> tuple[Symbol | Text | Expr, ...]:
        return self.items[1:]

    def lists(self, head: str) -> tuple[Expr, ...]:
        return tuple(i for i in self.items if isinstance(i, Expr) and i.head == head)

    def one(self, head: str) -> Expr | None:
        found = self.lists(head)
        return found[0] if found else None

    def words(self) -> tuple[str, ...]:
        """The atoms among the arguments, in order."""
        return tuple(str(i) for i in self.args if not isinstance(i, Expr))


_TOKEN = re.compile(r'(\s+)|(\()|(\))|"((?:[^"\\]|\\.)*)"|([^\s()"]+)', re.S)
_ESCAPE = re.compile(r"\\(.)", re.S)
_DECIMAL = re.compile(r"[-+]?(\d+\.?\d*|\.\d+)")


def parse(text: str, path: str) -> Expr:
    """The one top-level list of `text`. Raises BoardError for an unbalanced parenthesis,
    an unclosed string, or anything but one list."""
    stack: list[list] = [[]]
    opened: list[int] = []
    pos, line = 0, 1
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if m is None:
            raise BoardError(path, f"line {line}: a string is not closed")
        _, opening, closing, quoted, bare = m.groups()
        if opening:
            stack.append([])
            opened.append(line)
        elif closing:
            if len(stack) == 1:
                raise BoardError(path, f"line {line}: a ')' closes nothing")
            items = stack.pop()
            stack[-1].append(Expr(tuple(items), opened.pop()))
        elif quoted is not None:
            stack[-1].append(Text(_ESCAPE.sub(lambda e: "\n" if e.group(1) == "n" else e.group(1), quoted)))
        elif bare is not None:
            stack[-1].append(Symbol(bare))
        line += text.count("\n", pos, m.end())
        pos = m.end()
    if len(stack) > 1:
        raise BoardError(path, f"line {opened[-1]}: a '(' is never closed")
    if len(stack[0]) != 1 or not isinstance(stack[0][0], Expr):
        raise BoardError(path, "does not hold exactly one top-level list")
    return stack[0][0]


def number(node: Symbol | Text | Expr | None, path: str, where: Expr) -> Fraction:
    """A plain decimal, read exactly."""
    if not isinstance(node, Symbol) or not _DECIMAL.fullmatch(node):
        raise BoardError(path, f"line {where.line}: ({where.head} ...) needs a decimal number, not {node!s:.20}")
    return Fraction(str(node))
