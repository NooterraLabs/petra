"""Exact rationals and closed rational intervals with rigorous elementary functions.

Everything in the kernel bottoms out here. There is no float anywhere in the kernel:
`Q` is `fractions.Fraction`, and every function that cannot return an exact rational
(sqrt, ln, exp, pi) returns an `Interval` whose endpoints are rationals that provably
enclose the real value.

Invariants:
- `Interval.lo <= Interval.hi`, both `Fraction`. A point is `Interval(x, x)`.
- Every operation is inclusion-isotone: if A ⊆ A' and B ⊆ B' then op(A, B) ⊆ op(A', B').
  Library reuse (lola/library/transport.py) depends on this to re-check a sub-cell of a
  family partition, so outward rounding must be monotone too.
- Endpoints are rounded outward to dyadic rationals with `PRECISION_BITS` fractional
  bits after transcendental operations, so denominators stay bounded in deep
  expressions. Rounding outward never shrinks an interval.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

Q = Fraction

PRECISION_BITS = 96
"""Fractional bits kept by `round_out`. Fixed in the kernel so verdicts are reproducible."""


class KernelArithmeticError(ValueError):
    """Raised for an undefined operation: division by an interval containing 0, sqrt of a
    negative, ln of a non-positive. Rule checkers turn it into a Rejection."""


def parse_q(text: str) -> Q:
    """Parse the canonical JSON rational spelling: "n" or "p/q" with q > 1 and gcd(p, q) = 1.

    Rejects floats, decimals, exponents, spaces and non-reduced fractions, so one rational
    has exactly one spelling and statement hashes are stable.
    """
    raise NotImplementedError


def format_q(x: Q) -> str:
    """Inverse of `parse_q`."""
    raise NotImplementedError


def round_out(lo: Q, hi: Q, bits: int = PRECISION_BITS) -> "Interval":
    """Smallest dyadic interval with `bits` fractional bits that contains [lo, hi].

    TODO: lo' = floor(lo * 2**bits) / 2**bits ; hi' = ceil(hi * 2**bits) / 2**bits.
    """
    raise NotImplementedError


@dataclass(frozen=True, slots=True)
class Interval:
    """Closed interval [lo, hi] of rationals."""

    lo: Q
    hi: Q

    def __post_init__(self) -> None:
        # TODO: require both Fraction (never float, never int subclass bool), lo <= hi.
        pass

    @staticmethod
    def point(x: Q) -> "Interval":
        raise NotImplementedError

    def contains(self, x: Q) -> bool:
        raise NotImplementedError

    def subset_of(self, other: "Interval") -> bool:
        raise NotImplementedError

    def width(self) -> Q:
        raise NotImplementedError

    def midpoint(self) -> Q:
        raise NotImplementedError

    def hull(self, other: "Interval") -> "Interval":
        raise NotImplementedError

    def __add__(self, other: "Interval") -> "Interval":
        raise NotImplementedError

    def __sub__(self, other: "Interval") -> "Interval":
        raise NotImplementedError

    def __neg__(self) -> "Interval":
        raise NotImplementedError

    def __mul__(self, other: "Interval") -> "Interval":
        """Min and max of the four endpoint products. Exact, no rounding."""
        raise NotImplementedError

    def __truediv__(self, other: "Interval") -> "Interval":
        """Raises KernelArithmeticError if 0 ∈ other."""
        raise NotImplementedError

    def pow_int(self, n: int) -> "Interval":
        """x**n for integer n >= 0, tight for even n over intervals that straddle 0."""
        raise NotImplementedError

    def abs(self) -> "Interval":
        raise NotImplementedError


def i_min(a: Interval, b: Interval) -> Interval:
    raise NotImplementedError


def i_max(a: Interval, b: Interval) -> Interval:
    raise NotImplementedError


def i_sqrt(x: Interval) -> Interval:
    """Rigorous enclosure of sqrt over x. Requires x.lo >= 0.

    TODO: for an endpoint p/q, sqrt(p/q) = sqrt(p*q)/q.
      s = isqrt(p * q * 4**bits)        # math.isqrt, exact integer
      lower = s / (q * 2**bits)         # <= true sqrt
      upper = (s + 1) / (q * 2**bits)   # >= true sqrt (exact if s*s == p*q*4**bits)
    sqrt is monotone, so the result is [lower(x.lo), upper(x.hi)].
    """
    raise NotImplementedError


def i_ln(x: Interval) -> Interval:
    """Rigorous enclosure of the natural log. Requires x.lo > 0.

    TODO: reduce y = 2**e * m with m in [1/2, 2]; ln y = e*ln2 + ln m.
      ln m = 2*atanh(z), z = (m-1)/(m+1), |z| <= 1/3.
      Partial sum S_N = 2 * sum_{k<N} z**(2k+1)/(2k+1).
      Tail bound |R_N| <= 2*|z|**(2N+1) / ((2N+1)*(1-z*z)).
      ln2 is computed by the same series at m = 2 (z = 1/3) once and cached.
    Monotone: result is [lower(ln x.lo), upper(ln x.hi)].
    """
    raise NotImplementedError


def i_exp(x: Interval) -> Interval:
    """Rigorous enclosure of exp.

    TODO: reduce x = k*ln2 + r with |r| <= ln2/2 using an enclosure of ln2.
      Taylor sum to N terms with Lagrange remainder |r|**(N+1) * 3 / (N+1)!.
      Multiply by 2**k exactly.
    """
    raise NotImplementedError


def i_pi() -> Interval:
    """Rigorous enclosure of pi by Machin's formula 16*atan(1/5) - 4*atan(1/239) with
    alternating-series remainder bounds. Cached; width < 2**-PRECISION_BITS."""
    raise NotImplementedError
