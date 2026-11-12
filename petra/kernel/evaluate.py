"""Interval evaluation and structural queries over Expr. Shared by every rule.

Untrusted solvers may import `enclose` to search (the R4 box solver does), because using
the kernel's own evaluator cannot make a check pass that should fail: the kernel
re-evaluates every leaf itself.
"""
from __future__ import annotations

import math
from dataclasses import fields, is_dataclass
from functools import reduce
from typing import Mapping

from .interval import Interval, KernelArithmeticError, Q, i_cos, i_exp, i_ln, i_max, i_min, i_pi, i_sqrt
from .terms import Abs, Add, Const, Cos, Div, Exp, Expr, Ln, Matrix, Max, Min, Mul, Neg, Pi, PowInt, Sqrt, Sym

Box = Mapping[str, Interval]
"""Symbol -> range. A point is a box of point intervals."""

Vector = tuple[Q, ...]


class NotAffine(ValueError):
    """Raised by `affine_coefficients` when an expression is not affine in the requested
    symbols with rational coefficients."""


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
    """Every Sym name inside any kernel term: an Expr, a goal, a QuantityDef, or a tuple of
    them. A generic walk over dataclass fields, so a new rule's goal needs no case here."""
    if isinstance(term, Sym):
        return frozenset((term.name,))
    if isinstance(term, tuple):
        parts = term
    elif is_dataclass(term):
        parts = tuple(getattr(term, f.name) for f in fields(term))
    else:
        return frozenset()
    return frozenset().union(*map(free_syms, parts))


def rename(term: object, renaming: Mapping[str, str]) -> object:
    """The statement term with every symbol renamed: each Sym's name and each str field
    named sym, the hypothesis and bound-variable binders. A label or any other string is
    not a symbol and stays. Raises KeyError for a symbol `renaming` does not map. Every
    Sym is renamed, so free_syms(rename(t, r)) is {r[s] for s in free_syms(t)}."""
    if isinstance(term, Sym):
        return Sym(renaming[term.name])
    if isinstance(term, tuple):
        return tuple(rename(t, renaming) for t in term)
    if not is_dataclass(term) or isinstance(term, Matrix):
        return term
    parts = ((f.name, getattr(term, f.name)) for f in fields(term))
    return type(term)(*(renaming[v] if name == "sym" and isinstance(v, str) else rename(v, renaming) for name, v in parts))


def affine_coefficients(expr: Expr, syms: tuple[str, ...]) -> tuple[Q, tuple[Q, ...]]:
    """Return (c0, (c_1..c_k)) with expr == c0 + sum c_i * syms[i] identically.

    Structural recursion through Const, Sym, Add, Neg, Mul (at most one factor with a
    nonzero linear part), Div by a constant, and PowInt with exponent 0 or 1 or a constant
    base. Any other subterm must fold to an exact constant: its enclosure over the empty
    box must be a point, which is then its value, since an enclosure contains the value.
    Anything else raises NotAffine.
    """
    index = {s: i for i, s in enumerate(syms)}
    zero = (Q(0),) * len(syms)

    def scaled(form: tuple[Q, Vector], c: Q) -> tuple[Q, Vector]:
        return form[0] * c, tuple(x * c for x in form[1])

    def aff(e: Expr) -> tuple[Q, Vector]:
        match e:
            case Const(value=v):
                return v, zero
            case Sym(name=name) if name in index:
                i = index[name]
                return Q(0), zero[:i] + (Q(1),) + zero[i + 1:]
            case Add(args=args):
                parts = [aff(a) for a in args]
                return sum((c for c, _ in parts), Q(0)), tuple(map(sum, zip(zero, *(v for _, v in parts))))
            case Neg(arg=a):
                return scaled(aff(a), Q(-1))
            case Mul(args=args):
                parts = [aff(a) for a in args]
                linear = [p for p in parts if any(p[1])]
                if len(linear) > 1:
                    raise NotAffine(f"a product of two non-constant factors in {syms}")
                c = math.prod((p[0] for p in parts if not any(p[1])), start=Q(1))
                return scaled(linear[0] if linear else (Q(1), zero), c)
            case Div(num=num, den=den):
                c, v = aff(den)
                if any(v) or c == 0:
                    raise NotAffine("division by a non-constant or by zero")
                return scaled(aff(num), 1 / c)
            case PowInt(base=base, exponent=n) if n >= 0:
                c, v = aff(base)
                if n == 1:
                    return c, v
                if any(v) and n != 0:
                    raise NotAffine(f"a power of a non-constant in {syms}")
                return c ** n, zero
        try:
            value = enclose(e, {})
        except (KeyError, KernelArithmeticError):
            raise NotAffine(f"{type(e).__name__} is not affine in {syms}") from None
        if value.lo != value.hi:
            raise NotAffine(f"{type(e).__name__} does not fold to an exact constant")
        return value.lo, zero

    return aff(expr)


def vertices(box: Box, syms: tuple[str, ...]) -> tuple[dict[str, Q], ...]:
    """The 2**k vertices of the sub-box over sorted `syms`, in the canonical order the
    evidence module documents: bit k of the vertex index selects hi (1) or lo (0) of
    syms[k]."""
    return tuple(
        {s: box[s].hi if v >> k & 1 else box[s].lo for k, s in enumerate(syms)} for v in range(1 << len(syms))
    )


def at_vertices(exprs: tuple[Expr, ...], syms: tuple[str, ...], box: Box) -> tuple[Vector, ...]:
    """The exact value of every expr at each vertex of the box over syms, in vertex order.
    Raises NotAffine unless every expr is affine in syms with rational coefficients."""
    forms = [affine_coefficients(e, syms) for e in exprs]
    return tuple(
        tuple(c0 + sum((c * v[s] for c, s in zip(cs, syms)), Q(0)) for c0, cs in forms) for v in vertices(box, syms)
    )


def point_box(point: tuple[tuple[str, Q], ...]) -> dict[str, Interval]:
    return {s: Interval(v, v) for s, v in point}
