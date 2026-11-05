"""Interval evaluation and printing of registry expressions, for the deck tools. Untrusted.

`enclose` has kernel.enclose's contract, a rigorous enclosure of an Expr over a box of
rational intervals, for the Expr variants registry derivations and consistency relations
use. The deck tools keep their own evaluator so the registry does not depend on the
kernel's arithmetic; nothing a verdict uses passes through this module. Like the kernel,
it uses exact Fractions and never a float: sqrt and ln are bounded with integer square
roots and a series with a proven remainder, then rounded outward.
"""
from __future__ import annotations

import dataclasses
from fractions import Fraction
from math import isqrt
from typing import Mapping

from ..kernel import Add, Const, Div, Expr, Interval, Ln, Mul, Neg, Pi, PowInt, Sqrt, Sym

PRECISION_BITS = 80
_PI = Interval(Fraction(314159265358979323846, 10**20), Fraction(314159265358979323847, 10**20))
_LN_TERMS = 40


class EvaluationError(ArithmeticError):
    """An undefined operation: division by an interval containing 0, sqrt of a negative,
    ln of a non-positive number."""


def enclose(expr: Expr, box: Mapping[str, Interval]) -> Interval:
    """Natural interval extension of expr over box. KeyError for a symbol not in box."""
    match expr:
        case Const(value=v):
            return Interval(Fraction(v), Fraction(v))
        case Sym(name=name):
            return box[name]
        case Pi():
            return _PI
        case Add(args=args):
            parts = [enclose(a, box) for a in args]
            return Interval(sum((p.lo for p in parts), Fraction(0)), sum((p.hi for p in parts), Fraction(0)))
        case Mul(args=args):
            result = Interval(Fraction(1), Fraction(1))
            for a in args:
                result = _mul(result, enclose(a, box))
            return result
        case Neg(arg=a):
            x = enclose(a, box)
            return Interval(-x.hi, -x.lo)
        case Div(num=n, den=d):
            den = enclose(d, box)
            if den.lo <= 0 <= den.hi:
                raise EvaluationError("division by an interval that contains 0")
            return _mul(enclose(n, box), Interval(1 / den.hi, 1 / den.lo))
        case PowInt(base=b, exponent=k):
            return _pow(enclose(b, box), k)
        case Sqrt(arg=a):
            x = enclose(a, box)
            if x.lo < 0:
                raise EvaluationError("sqrt of an interval that reaches below 0")
            return Interval(_sqrt_down(x.lo), _sqrt_up(x.hi))
        case Ln(arg=a):
            x = enclose(a, box)
            if x.lo <= 0:
                raise EvaluationError("ln of an interval that reaches 0 or below")
            return Interval(_ln_bounds(x.lo)[0], _ln_bounds(x.hi)[1])
    raise TypeError(f"registry expressions do not use {type(expr).__name__}")


def free_syms(expr: Expr) -> frozenset[str]:
    if isinstance(expr, Sym):
        return frozenset({expr.name})
    found: set[str] = set()
    for f in dataclasses.fields(expr):
        value = getattr(expr, f.name)
        for child in value if isinstance(value, tuple) else (value,):
            if dataclasses.is_dataclass(child):
                found |= free_syms(child)
    return frozenset(found)


def render(expr: Expr) -> str:
    """Infix text with every compound operand in parentheses, for records and messages."""
    match expr:
        case Const(value=v):
            return str(v)
        case Sym(name=name):
            return name
        case Pi():
            return "pi"
        case Add(args=args):
            text = _operand(args[0]) if args else "0"
            for a in args[1:]:
                text += f" - {_operand(a.arg)}" if isinstance(a, Neg) else f" + {_operand(a)}"
            return text
        case Mul(args=args):
            return " * ".join(_operand(a) for a in args) if args else "1"
        case Neg(arg=a):
            return f"-{_operand(a)}"
        case Div(num=n, den=d):
            return f"{_operand(n)} / {_operand(d)}"
        case PowInt(base=b, exponent=k):
            return f"{_operand(b)}^{k}"
        case Sqrt(arg=a):
            return f"sqrt({render(a)})"
        case Ln(arg=a):
            return f"ln({render(a)})"
    raise TypeError(f"registry expressions do not use {type(expr).__name__}")


def decimal(x: Fraction, digits: int = 6) -> str:
    """x in scientific notation with `digits` significant digits, from exact integer
    arithmetic."""
    if x == 0:
        return "0"
    sign, x = ("-" if x < 0 else ""), abs(x)
    e = len(str(x.numerator)) - len(str(x.denominator))
    if Fraction(10) ** e > x:
        e -= 1
    mantissa = round(x / Fraction(10) ** (e - digits + 1))
    if mantissa == 10**digits:
        mantissa, e = mantissa // 10, e + 1
    text = str(mantissa)
    tail = text[1:].rstrip("0")
    return f"{sign}{text[0]}{'.' + tail if tail else ''}e{e}"


def interval_text(x: Interval) -> str:
    return decimal(x.lo) if x.lo == x.hi else f"[{decimal(x.lo)}, {decimal(x.hi)}]"


def _operand(expr: Expr) -> str:
    text = render(expr)
    return f"({text})" if isinstance(expr, (Add, Mul, Div, Neg)) else text


def _mul(a: Interval, b: Interval) -> Interval:
    products = (a.lo * b.lo, a.lo * b.hi, a.hi * b.lo, a.hi * b.hi)
    return Interval(min(products), max(products))


def _pow(x: Interval, k: int) -> Interval:
    if k < 0:
        raise TypeError("registry expressions use only non-negative integer powers")
    if k == 0:
        return Interval(Fraction(1), Fraction(1))
    lo, hi = x.lo**k, x.hi**k
    if k % 2 == 1 or x.lo >= 0:
        return Interval(lo, hi)
    if x.hi <= 0:
        return Interval(hi, lo)
    return Interval(Fraction(0), max(lo, hi))


def _shift(x: Fraction) -> int:
    """Power of 4 that lifts x to about 4**PRECISION_BITS, so the integer square root
    keeps PRECISION_BITS significant bits."""
    return max(0, PRECISION_BITS - (x.numerator.bit_length() - x.denominator.bit_length()) // 2)


def _sqrt_down(x: Fraction) -> Fraction:
    if x == 0:
        return Fraction(0)
    s = _shift(x)
    return Fraction(isqrt(x.numerator * 4**s // x.denominator), 2**s)


def _sqrt_up(x: Fraction) -> Fraction:
    if x == 0:
        return Fraction(0)
    s = _shift(x)
    n = -(-x.numerator * 4**s // x.denominator)
    r = isqrt(n)
    return Fraction(r if r * r == n else r + 1, 2**s)


def _round_down(x: Fraction) -> Fraction:
    return Fraction(x.numerator * 2**PRECISION_BITS // x.denominator, 2**PRECISION_BITS)


def _round_up(x: Fraction) -> Fraction:
    return Fraction(-(-x.numerator * 2**PRECISION_BITS // x.denominator), 2**PRECISION_BITS)


def _ln_near_one(m: Fraction) -> tuple[Fraction, Fraction]:
    """ln m = 2 atanh(z) with z = (m - 1)/(m + 1). For m in (1/2, 2], |z| <= 1/3 and the
    tail after N terms is at most 2 |z|^(2N+1) / ((2N + 1)(1 - z^2))."""
    z = (m - 1) / (m + 1)
    z2, term, total = z * z, z, Fraction(0)
    for k in range(_LN_TERMS):
        total += term / (2 * k + 1)
        term *= z2
    tail = 2 * abs(term) / ((2 * _LN_TERMS + 1) * (1 - z2))
    return 2 * total - tail, 2 * total + tail


_LN2 = _ln_near_one(Fraction(2))


def _ln_bounds(x: Fraction) -> tuple[Fraction, Fraction]:
    e = x.numerator.bit_length() - x.denominator.bit_length()
    lo, hi = _ln_near_one(x / Fraction(2) ** e)
    if e >= 0:
        lo, hi = lo + e * _LN2[0], hi + e * _LN2[1]
    else:
        lo, hi = lo + e * _LN2[1], hi + e * _LN2[0]
    return _round_down(lo), _round_up(hi)
