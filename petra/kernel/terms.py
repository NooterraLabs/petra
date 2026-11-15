"""The nodes of an expression. Evaluated by interval arithmetic in evaluate.py.

This file contains no physics. A symbol is an opaque name. deck.py, rule.py and grid.py build
expressions from a deck's rows and rules with these, and the kernel builds its own from the
same deck (kernel/Petra/Tape.lean).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Union

from .interval import Q

# ---------------------------------------------------------------------------
# Expressions. Evaluated by interval arithmetic in evaluate.py.
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Const:
    value: Q


@dataclass(frozen=True, slots=True)
class Sym:
    name: str


@dataclass(frozen=True, slots=True)
class Pi:
    """The real number pi, enclosed by interval.i_pi()."""


@dataclass(frozen=True, slots=True)
class Add:
    args: tuple["Expr", ...]


@dataclass(frozen=True, slots=True)
class Mul:
    args: tuple["Expr", ...]


@dataclass(frozen=True, slots=True)
class Neg:
    arg: "Expr"


@dataclass(frozen=True, slots=True)
class Div:
    num: "Expr"
    den: "Expr"


@dataclass(frozen=True, slots=True)
class PowInt:
    base: "Expr"
    exponent: int


@dataclass(frozen=True, slots=True)
class Sqrt:
    arg: "Expr"


@dataclass(frozen=True, slots=True)
class Ln:
    arg: "Expr"


@dataclass(frozen=True, slots=True)
class Exp:
    arg: "Expr"


@dataclass(frozen=True, slots=True)
class Cos:
    """The cosine of an angle in radians, enclosed by interval.i_cos()."""

    arg: "Expr"


@dataclass(frozen=True, slots=True)
class Abs:
    arg: "Expr"


@dataclass(frozen=True, slots=True)
class Min:
    args: tuple["Expr", ...]


@dataclass(frozen=True, slots=True)
class Max:
    args: tuple["Expr", ...]


Expr = Union[Const, Sym, Pi, Add, Mul, Neg, Div, PowInt, Sqrt, Ln, Exp, Cos, Abs, Min, Max]
