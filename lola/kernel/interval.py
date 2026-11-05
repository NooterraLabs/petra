"""Exact rationals and closed rational intervals with rigorous elementary functions.

Everything in the kernel bottoms out here. There is no float anywhere in the kernel:
`Q` is `fractions.Fraction`, and every function that cannot return an exact rational
(sqrt, ln, exp, pi) returns an `Interval` whose endpoints are rationals that provably
enclose the real value.

Invariants:
- `Interval.lo <= Interval.hi`, both `Fraction`. A point is `Interval(x, x)`.
- Every operation is inclusion-isotone: if A ⊆ A' and B ⊆ B' then op(A, B) ⊆ op(A', B').
  An enclosure over a cell then also holds over every sub-cell, so outward rounding must
  be monotone too.
- +, -, *, / and integer powers are exact. sqrt, ln, exp and pi round outward to the
  grid of dyadic rationals with `PRECISION_BITS` fractional bits, and the rounding is
  directed and exact: the lower endpoint of f over [a, b] is the largest grid point at or
  below f(a), and the upper endpoint the smallest grid point at or above f(b) (f
  increasing). Both are monotone in a and b, which gives isotonicity, and both are fixed
  by the mathematics alone, so another kernel that follows this rule (a Lean port) gets
  the same endpoints whatever series it sums.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache

Q = Fraction

PRECISION_BITS = 96
"""Fractional bits of the rounding grid. Fixed in the kernel so verdicts are reproducible."""

_GRID = 1 << PRECISION_BITS
_RATIONAL = re.compile(r"-?(0|[1-9][0-9]*)(/[1-9][0-9]*)?")


class KernelArithmeticError(ValueError):
    """Raised for an undefined operation: division by an interval containing 0, sqrt of a
    negative, ln of a non-positive. Rule checkers turn it into a Rejection."""


def parse_q(text: str) -> Q:
    """Parse the canonical JSON rational spelling: "n" or "p/q" with q > 1 and gcd(p, q) = 1.

    Rejects floats, decimals, exponents, spaces and non-reduced fractions, so one rational
    has exactly one spelling and statement hashes are stable. Raises ValueError.
    """
    if type(text) is str and _RATIONAL.fullmatch(text):
        x = Fraction(text)
        if format_q(x) == text:
            return x
    raise ValueError(f"not a canonical rational: {text!r}")


def format_q(x: Q) -> str:
    """Inverse of `parse_q`."""
    return str(x.numerator) if x.denominator == 1 else f"{x.numerator}/{x.denominator}"


def round_out(lo: Q, hi: Q, bits: int = PRECISION_BITS) -> "Interval":
    """Smallest dyadic interval with `bits` fractional bits that contains [lo, hi]."""
    scale = 1 << bits
    return Interval(Q(math.floor(lo * scale), scale), Q(math.ceil(hi * scale), scale))


@dataclass(frozen=True, slots=True)
class Interval:
    """Closed interval [lo, hi] of rationals."""

    lo: Q
    hi: Q

    def __post_init__(self) -> None:
        if not (isinstance(self.lo, Fraction) and isinstance(self.hi, Fraction)):
            raise TypeError(f"interval endpoints must be Fractions, got {self.lo!r} and {self.hi!r}")
        if self.lo > self.hi:
            raise ValueError(f"empty interval [{self.lo}, {self.hi}]")

    @staticmethod
    def point(x: Q) -> "Interval":
        return Interval(x, x)

    def contains(self, x: Q) -> bool:
        return self.lo <= x <= self.hi

    def subset_of(self, other: "Interval") -> bool:
        return other.lo <= self.lo and self.hi <= other.hi

    def width(self) -> Q:
        return self.hi - self.lo

    def midpoint(self) -> Q:
        return (self.lo + self.hi) / 2

    def hull(self, other: "Interval") -> "Interval":
        return Interval(min(self.lo, other.lo), max(self.hi, other.hi))

    def __add__(self, other: "Interval") -> "Interval":
        return Interval(self.lo + other.lo, self.hi + other.hi)

    def __sub__(self, other: "Interval") -> "Interval":
        return Interval(self.lo - other.hi, self.hi - other.lo)

    def __neg__(self) -> "Interval":
        return Interval(-self.hi, -self.lo)

    def __mul__(self, other: "Interval") -> "Interval":
        """Min and max of the four endpoint products. Exact, no rounding."""
        products = (self.lo * other.lo, self.lo * other.hi, self.hi * other.lo, self.hi * other.hi)
        return Interval(min(products), max(products))

    def __truediv__(self, other: "Interval") -> "Interval":
        """Raises KernelArithmeticError if 0 ∈ other."""
        if other.lo <= 0 <= other.hi:
            raise KernelArithmeticError(f"division by [{other.lo}, {other.hi}], which contains 0")
        return self * Interval(1 / other.hi, 1 / other.lo)

    def pow_int(self, n: int) -> "Interval":
        """x**n for integer n >= 0, tight for even n over intervals that straddle 0."""
        if n < 0:
            raise KernelArithmeticError(f"negative exponent {n}")
        a, b = self.lo ** n, self.hi ** n
        if n == 0 or n % 2 or self.lo >= 0:
            return Interval(a, b)
        if self.hi <= 0:
            return Interval(b, a)
        return Interval(Q(0), max(a, b))

    def abs(self) -> "Interval":
        if self.lo >= 0:
            return self
        if self.hi <= 0:
            return -self
        return Interval(Q(0), max(-self.lo, self.hi))


def i_min(a: Interval, b: Interval) -> Interval:
    return Interval(min(a.lo, b.lo), min(a.hi, b.hi))


def i_max(a: Interval, b: Interval) -> Interval:
    return Interval(max(a.lo, b.lo), max(a.hi, b.hi))


def i_sqrt(x: Interval) -> Interval:
    """[floor(sqrt(x.lo)), ceil(sqrt(x.hi))] on the grid, computed exactly. Requires x.lo >= 0.

    With y = x * 4**PRECISION_BITS, sqrt(x) * 2**PRECISION_BITS = sqrt(y). For real y >= 0,
    floor(sqrt(y)) = isqrt(floor(y)), and ceil(sqrt(y)) is that integer when its square is
    y and the next integer otherwise.
    """
    if x.lo < 0:
        raise KernelArithmeticError(f"sqrt over [{x.lo}, {x.hi}], which has negative values")
    top = x.hi * _GRID * _GRID
    hi = math.isqrt(math.floor(top))
    lo = math.isqrt(math.floor(x.lo * _GRID * _GRID))
    return Interval(Q(lo, _GRID), Q(hi if hi * hi == top else hi + 1, _GRID))


def _grid(enclosure, x) -> tuple[Q, Q]:
    """The grid points just below and just above the real v that `enclosure(x, p)` encloses
    to within about 2**-p.

    Soundness needs only that each enclosure contains v: the result contains the
    enclosure. Exactness (the result is floor and ceil of v) needs v off the grid. Every
    caller passes an irrational v (ln x for rational x != 1, exp x for rational x != 0,
    and pi, by Lindemann's theorem), so a fine enough enclosure always separates it.
    """
    for extra in (32, 128, 512, 2048):
        e = enclosure(x, PRECISION_BITS + extra)
        lo, hi = math.floor(e.lo * _GRID), math.ceil(e.hi * _GRID)
        if hi - lo <= 1:
            return Q(lo, _GRID), Q(hi, _GRID)
    raise KernelArithmeticError(f"no enclosure of the value at {x} separated it from the rounding grid")


def _scale(a: int, b: int, c: Q) -> tuple[int, int]:
    """[a, b] * c rounded outward to integers: one interval step on numbers held as
    integer multiples of a fixed 2**-p."""
    lo, hi = (a, b) if c >= 0 else (b, a)
    return lo * c.numerator // c.denominator, -(-hi * c.numerator // c.denominator)


def _odd_series(x: Q, sign: int, p: int) -> Interval:
    """Encloses sum_k sign**k x**(2k+1)/(2k+1) for |x| <= 1/3: atanh x for sign 1, atan x
    for sign -1. [a, b] * 2**-p encloses the current power and [lo, hi] * 2**-p the partial
    sum. Whatever the signs, the tail after k terms is at most
    sum_{j>=k} |x|**(2j+1) <= (9/8) 3**-(2k+1)."""
    one, step = 1 << p, sign * x * x
    (a, b), lo, hi, k = _scale(1 << p, 1 << p, x), 0, 0, 0
    while 3 ** (2 * k + 1) <= 2 * one:
        ta, tb = _scale(a, b, Q(1, 2 * k + 1))
        lo, hi = lo + ta, hi + tb
        (a, b), k = _scale(a, b, step), k + 1
    tail = Q(9, 8) / 3 ** (2 * k + 1)
    return Interval(Q(lo, one) - tail, Q(hi, one) + tail)


@lru_cache(maxsize=None)
def _ln2(p: int) -> Interval:
    return Interval.point(Q(2)) * _odd_series(Q(1, 3), 1, p)


def _ln_at(x: Q, p: int) -> Interval:
    """ln x = 2 atanh(z) + e ln 2, where x = m 2**e with m in (1/2, 2) and
    z = (m - 1)/(m + 1), so |z| < 1/3, and ln 2 = 2 atanh(1/3)."""
    e = x.numerator.bit_length() - x.denominator.bit_length()
    m = x / Q(2) ** e
    return Interval.point(Q(2)) * _odd_series((m - 1) / (m + 1), 1, p) + Interval.point(Q(e)) * _ln2(p)


def _exp_at(x: Q, p: int) -> Interval:
    """exp x = exp(r)**(2**s) with r = x / 2**s < 1/2 for x >= 0, and 1 / exp(-x) for x < 0.

    [a, b] * 2**-q encloses the partial Taylor sum of exp(r). The tail after the r**n/n!
    term lies in [0, 2 r**(n+1)/(n+1)!], which is at most 2**-n/(n+1)!. Squaring a
    positive enclosure keeps it an enclosure. Squaring s times doubles the relative
    error each time and exp x < 4**x, so the working precision q grows with s and x.
    """
    if x < 0:
        return Interval.point(Q(1)) / _exp_at(-x, p)
    s = math.ceil(x).bit_length() + 1
    q, r = p + 2 * s + 2 * math.ceil(x), x / (1 << s)
    one = 1 << q
    ta, tb, a, b, n = one, one, one, one, 0
    while (1 << n) * math.factorial(n + 1) <= one:
        n += 1
        ta, tb = _scale(ta, tb, r / n)
        a, b = a + ta, b + tb
    b += -(-one // ((1 << n) * math.factorial(n + 1)))
    for _ in range(s):
        a, b = a * a >> q, -(-(b * b) >> q)
    return Interval(Q(a, one), Q(b, one))


def _pi_at(_: None, p: int) -> Interval:
    """Machin's formula pi = 16 atan(1/5) - 4 atan(1/239)."""
    return Interval.point(Q(16)) * _odd_series(Q(1, 5), -1, p) - Interval.point(Q(4)) * _odd_series(Q(1, 239), -1, p)


@lru_cache(maxsize=4096)
def _ln_point(x: Q) -> tuple[Q, Q]:
    return (Q(0), Q(0)) if x == 1 else _grid(_ln_at, x)


@lru_cache(maxsize=4096)
def _exp_point(x: Q) -> tuple[Q, Q]:
    return (Q(1), Q(1)) if x == 0 else _grid(_exp_at, x)


def i_ln(x: Interval) -> Interval:
    """[floor(ln x.lo), ceil(ln x.hi)] on the grid. Requires x.lo > 0."""
    if x.lo <= 0:
        raise KernelArithmeticError(f"ln over [{x.lo}, {x.hi}], which has non-positive values")
    return Interval(_ln_point(x.lo)[0], _ln_point(x.hi)[1])


def i_exp(x: Interval) -> Interval:
    """[floor(exp x.lo), ceil(exp x.hi)] on the grid."""
    return Interval(_exp_point(x.lo)[0], _exp_point(x.hi)[1])


@lru_cache(maxsize=None)
def i_pi() -> Interval:
    """The two grid points around pi, from Machin's formula with series remainder bounds.
    Cached; width 2**-PRECISION_BITS."""
    return Interval(*_grid(_pi_at, None))
