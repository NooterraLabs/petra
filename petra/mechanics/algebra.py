"""The expression builders the mechanics layer, and the code layers over it, write with:
thin constructors over the kernel's terms, where a one-term sum or product is the term."""
from __future__ import annotations

from fractions import Fraction

from ..kernel import Add, Const, Div, Exp, Expr, Ln, Mul, Neg, PowInt


def c(x: Fraction | int | str) -> Const:
    """An exact rational constant."""
    return Const(Fraction(x))


def add(*xs: Expr) -> Expr:
    return xs[0] if len(xs) == 1 else Add(tuple(xs))


def mul(*xs: Expr) -> Expr:
    return xs[0] if len(xs) == 1 else Mul(tuple(xs))


def sub(a: Expr, b: Expr) -> Expr:
    return Add((a, Neg(b)))


def div(a: Expr, b: Expr) -> Expr:
    return Div(a, b)


def sq(a: Expr) -> Expr:
    return PowInt(a, 2)


def power(a: Expr, exponent: Expr) -> Expr:
    """a ** exponent for a > 0: exp(exponent ln a)."""
    return Exp(Mul((exponent, Ln(a))))
