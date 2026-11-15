"""Interval evaluation of an expression over a box.

The Python reader searches with `enclose` for the hints of proofs.json and works its own cells
out with it. That cannot pass a design: the kernel evaluates every leaf itself.
"""
from __future__ import annotations

from dataclasses import fields, is_dataclass
from functools import reduce
from typing import Mapping

from .interval import Interval, KernelArithmeticError, Q, i_cos, i_exp, i_ln, i_max, i_min, i_pi, i_sqrt
from .terms import Abs, Add, Const, Cos, Div, Exp, Expr, Ln, Max, Min, Mul, Neg, Pi, PowInt, Sqrt, Sym

Box = Mapping[str, Interval]
"""Symbol -> range. A point is a box of point intervals."""

def enclose(expr: Expr, box: Box) -> Interval:
    """Natural interval extension of expr over box. Inclusion-isotone.

    Soundness: each case below returns an interval that contains the real operation's
    value at every point of its argument intervals, so by induction on the expression
    the result contains expr's value at every point of the box, and expr is defined
    there. Raises KernelArithmeticError (from interval.py) on an undefined operation, and
    KeyError for a symbol missing from the box. check.py guarantees the box is complete
    before any rule runs. A subterm shared by identity is evaluated once.
    """
    memo: dict[int, Interval] = {}

    def ev(e: Expr) -> Interval:
        key = id(e)
        if key not in memo:
            memo[key] = _step(e, ev, box)
        return memo[key]

    return ev(expr)


def _step(e: Expr, ev, box: Box) -> Interval:
    match e:
        case Const(value=v):
            return Interval(v, v)
        case Sym(name=name):
            return box[name]
        case Pi():
            return i_pi()
        case Add(args=args):
            return reduce(Interval.__add__, map(ev, args), Interval(Q(0), Q(0)))
        case Mul(args=args):
            return reduce(Interval.__mul__, map(ev, args), Interval(Q(1), Q(1)))
        case Neg(arg=a):
            return -ev(a)
        case Div(num=num, den=den):
            return ev(num) / ev(den)
        case PowInt(base=base, exponent=n):
            return ev(base).pow_int(n)
        case Sqrt(arg=a):
            return i_sqrt(ev(a))
        case Ln(arg=a):
            return i_ln(ev(a))
        case Exp(arg=a):
            return i_exp(ev(a))
        case Cos(arg=a):
            return i_cos(ev(a))
        case Abs(arg=a):
            return ev(a).abs()
        case Min(args=args) if args:
            return reduce(i_min, map(ev, args))
        case Max(args=args) if args:
            return reduce(i_max, map(ev, args))
    raise KernelArithmeticError(f"cannot enclose {e!r}")


def free_syms(term: object) -> frozenset[str]:
    """Every Sym name inside an expression, or inside a tuple of them. A walk over the fields
    of each node, so a new node needs no case here."""
    if isinstance(term, Sym):
        return frozenset((term.name,))
    if isinstance(term, tuple):
        parts = term
    elif is_dataclass(term):
        parts = tuple(getattr(term, f.name) for f in fields(term))
    else:
        return frozenset()
    return frozenset().union(*map(free_syms, parts))
