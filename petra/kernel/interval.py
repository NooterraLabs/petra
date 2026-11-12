"""Exact rationals and closed rational intervals with rigorous elementary functions.

Everything in the kernel bottoms out here. There is no float anywhere in the kernel:
`Q` is `fractions.Fraction`, and every function that cannot return an exact rational
(sqrt, ln, exp, cos, pi) returns an `Interval` whose endpoints are rationals that provably
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
  the same endpoints whatever series it sums. The root of a point that is the square of a
  fraction is that fraction (`i_sqrt`): a point holds no other interval, so this keeps
  isotonicity too.
- cos rounds to the same grid. It falls and rises by turns between the multiples of pi,
  so its ends over [a, b] are the grid points around cos a and cos b, or 1 or -1 where the
  cosine may turn in the interval (`i_cos`). Which of these it is rests on comparisons
  with the enclosure of pi, which both kernels make alike.
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


def _root(q: Q) -> Q | None:
    """The square root of a fraction that is the square of one, or None: the root of its
    numerator over the root of its denominator, when that squares back to it."""
    r = Q(math.isqrt(q.numerator), math.isqrt(q.denominator))
    return r if r * r == q else None


def i_sqrt(x: Interval) -> Interval:
    """[floor(sqrt(x.lo)), ceil(sqrt(x.hi))] on the grid, computed exactly. Requires x.lo >= 0.

    With y = x * 4**PRECISION_BITS, sqrt(x) * 2**PRECISION_BITS = sqrt(y). For real y >= 0,
    floor(sqrt(y)) = isqrt(floor(y)), and ceil(sqrt(y)) is that integer when its square is
    y and the next integer otherwise.

    The root of a point that is the square of a fraction is that fraction at both ends, so
    that sqrt(3^2 + 4^2) is 5 and a strict inequality at it is decided. Only a point: an end
    of a wider interval at a square still rounds to the grid, which keeps the root isotone.
    """
    if x.lo < 0:
        raise KernelArithmeticError(f"sqrt over [{x.lo}, {x.hi}], which has negative values")
    if x.lo == x.hi and (root := _root(x.lo)) is not None:
        return Interval(root, root)
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
    error each time and exp x < 4**x, so the working precision q grows with s and x. The
    factorial (n + 1)! is kept as n grows, as `expPos` in kernel/Petra/Num.lean keeps it.
    """
    if x < 0:
        return Interval.point(Q(1)) / _exp_at(-x, p)
    s = math.ceil(x).bit_length() + 1
    q, r = p + 2 * s + 2 * math.ceil(x), x / (1 << s)
    one = 1 << q
    ta, tb, a, b, n, fact = one, one, one, one, 0, 1
    while (1 << n) * fact <= one:
        n += 1
        fact *= n + 1
        ta, tb = _scale(ta, tb, r / n)
        a, b = a + ta, b + tb
    b += -(-one // ((1 << n) * fact))
    for _ in range(s):
        a, b = a * a >> q, -(-(b * b) >> q)
    return Interval(Q(a, one), Q(b, one))


def _cos_at(x: Q, p: int) -> Interval:
    """cos x for any x, as `cosAt` in kernel/Petra/Num.lean computes it, step for step.

    The cosine is even, so it is that of y = |x|, and cos y = cos(2**s r) with
    r = y / 2**s < 1/2. [a, b] * 2**-q encloses the partial sum of
    sum_n (-1)**n r**(2n)/(2n)!. After the term n the rest of the series is at most
    1/(4**n (2n+2)!) in size, whatever its sign. Then s doublings of the angle by
    cos 2t = 2 cos(t)**2 - 1: the square of [a, b] is rounded outward, from 0 when the
    enclosure holds 0, and the upper end is kept at 1, which no cosine passes. Each
    doubling takes the error times four at most, so q grows by two bits with each, and
    eight more pay for the rounding of the terms.
    """
    y = abs(x)
    s = math.ceil(y).bit_length() + 1
    q = p + 2 * s + 8
    one, r = 1 << q, y / (1 << s)
    m = -(r * r)
    ta, tb, a, b, n, fact = one, one, one, one, 0, 2
    while (1 << 2 * n) * fact <= one:
        ta, tb = _scale(ta, tb, m / ((2 * n + 1) * (2 * n + 2)))
        a, b = a + ta, b + tb
        fact *= (2 * n + 3) * (2 * n + 4)
        n += 1
    rest = -(-one // ((1 << 2 * n) * fact))
    a, b = a - rest, b + rest
    for _ in range(s):
        low = a * a if a >= 0 else b * b if b <= 0 else 0
        high = max(a * a, b * b)
        a, b = 2 * (low // one) - one, min(2 * -(-high // one) - one, one)
    return Interval(Q(a, one), Q(b, one))


def _pi_at(_: None, p: int) -> Interval:
    """Machin's formula pi = 16 atan(1/5) - 4 atan(1/239)."""
    return Interval.point(Q(16)) * _odd_series(Q(1, 5), -1, p) - Interval.point(Q(4)) * _odd_series(Q(1, 239), -1, p)


def _text(x: Q) -> str:
    """The number as a text that only it has: its numerator and its denominator in base 16,
    which costs their length to write. The caches below are keyed by this text and not by
    the number. Python hashes a whole number by its remainder on division by 2^61 - 1, so
    a file can list many numbers of one hash, and a table keyed by them would compare each
    with all the others. It hashes a text with a key no file knows."""
    return f"{x.numerator:x}/{x.denominator:x}"


@lru_cache(maxsize=4096)
def _ln_cached(text: str) -> tuple[Q, Q]:
    numerator, _, denominator = text.partition("/")
    return _grid(_ln_at, Q(int(numerator, 16), int(denominator, 16)))


@lru_cache(maxsize=4096)
def _exp_cached(text: str) -> tuple[Q, Q]:
    numerator, _, denominator = text.partition("/")
    return _grid(_exp_at, Q(int(numerator, 16), int(denominator, 16)))


@lru_cache(maxsize=4096)
def _cos_cached(text: str) -> tuple[Q, Q]:
    numerator, _, denominator = text.partition("/")
    return _grid(_cos_at, Q(int(numerator, 16), int(denominator, 16)))


def _ln_point(x: Q) -> tuple[Q, Q]:
    return (Q(0), Q(0)) if x == 1 else _ln_cached(_text(x))


def _exp_point(x: Q) -> tuple[Q, Q]:
    return (Q(1), Q(1)) if x == 0 else _exp_cached(_text(x))


def _cos_point(x: Q) -> tuple[Q, Q]:
    """The grid points around cos x. cos 0 is 1, a point of the grid, and the cosine of
    any other rational is irrational. An end and its negative have one cosine."""
    return (Q(1), Q(1)) if x == 0 else _cos_cached(_text(abs(x)))


def i_ln(x: Interval) -> Interval:
    """[floor(ln x.lo), ceil(ln x.hi)] on the grid. Requires x.lo > 0."""
    if x.lo <= 0:
        raise KernelArithmeticError(f"ln over [{x.lo}, {x.hi}], which has non-positive values")
    return Interval(_ln_point(x.lo)[0], _ln_point(x.hi)[1])


MAX_ARGUMENT = 65_536
"""The largest magnitude `i_exp` and `i_cos` take, as the kernel's step does (`MAX_BITS` in
kernel/Petra/Tape.lean). The time of an exponential grows as the square of its argument: one of
65,536 takes seconds, and one of a million did not end."""


def i_exp(x: Interval) -> Interval:
    """[floor(exp x.lo), ceil(exp x.hi)] on the grid, for an interval within MAX_ARGUMENT of zero."""
    if x.lo < -MAX_ARGUMENT or x.hi > MAX_ARGUMENT:
        raise KernelArithmeticError(f"exp of a value beyond {MAX_ARGUMENT}")
    return Interval(_exp_point(x.lo)[0], _exp_point(x.hi)[1])


def i_cos(x: Interval) -> Interval:
    """The cosine over [x.lo, x.hi], for any interval within MAX_ARGUMENT of zero, as `iCos`
    in kernel/Petra/Num.lean finds it.

    Between k pi and (k + 1) pi the cosine falls for an even k and rises for an odd one,
    and at k pi it is 1 or -1. The enclosure of pi places the interval: i is a whole
    number with i pi at or under x.lo, and j one with x.hi at or under j pi, each tested
    against the whole number times the end of the enclosure of pi that makes the product
    greater for i, and less for j. With j <= i + 1 the
    cosine goes one way over the interval, and its ends are the grid points around the
    cosines of the two ends. With j = i + 2 the cosine may turn in the interval, at
    (i + 1) pi, so one end is -1 or 1 and the other is the greater, or the lesser, of the
    grid points of the two ends. With j > i + 2 the enclosure is [-1, 1].
    """
    if x.lo < -MAX_ARGUMENT or x.hi > MAX_ARGUMENT:
        raise KernelArithmeticError(f"cos of a value beyond {MAX_ARGUMENT}")
    pi = i_pi()
    i = math.floor(x.lo / (pi.hi if x.lo >= 0 else pi.lo))
    j = math.ceil(x.hi / (pi.lo if x.hi > 0 else pi.hi))
    if not (i * (pi.hi if i >= 0 else pi.lo) <= x.lo and x.hi <= j * (pi.lo if j >= 0 else pi.hi)):
        raise KernelArithmeticError("cos over an interval that the enclosure of pi does not place between two of its multiples")
    if j > i + 2:
        return Interval(Q(-1), Q(1))
    a, b = _cos_point(x.lo), _cos_point(x.hi)
    if j <= i + 1:
        return Interval(b[0], a[1]) if i % 2 == 0 else Interval(a[0], b[1])
    return Interval(Q(-1), max(a[1], b[1])) if i % 2 == 0 else Interval(min(a[0], b[0]), Q(1))


@lru_cache(maxsize=None)
def i_pi() -> Interval:
    """The two grid points around pi, from Machin's formula with series remainder bounds.
    Cached; width 2**-PRECISION_BITS."""
    return Interval(*_grid(_pi_at, None))
