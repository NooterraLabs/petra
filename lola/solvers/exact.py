"""Float-to-exact repair shared by solvers. Untrusted.

The pattern every solver uses: solve in floats, round to rationals, then repair the
equality constraints exactly so the kernel's exact equality checks pass, and keep a
margin on inequalities so rounding never lands on the wrong side.
"""
from __future__ import annotations

from fractions import Fraction

from ..kernel import Matrix, Statement

Vector = tuple[Fraction, ...]


def to_numpy(A: Matrix):
    """Dense float64 array."""
    raise NotImplementedError


def rationalize(x, max_den: int = 10**12) -> Vector:
    """Fraction.limit_denominator per entry."""
    raise NotImplementedError


def solve_exact(A: Matrix, b: Vector) -> Vector | None:
    """Exact rational solve of a square or full-row-rank system by fraction-free Gaussian
    elimination. None if singular."""
    raise NotImplementedError


def project_onto_equalities(A: Matrix, b: Vector, x: Vector, basis: tuple[int, ...]) -> Vector:
    """Fix the non-basic entries of x and solve exactly for the basic ones so A x = b
    holds exactly. `basis` comes from the LP solver's final basis.
    TODO: if the repaired x violates a bound, shrink toward the LP's interior point
    (Chebyshev centre with a small margin) and repeat once."""
    raise NotImplementedError


def range_box(statement: Statement) -> dict:
    """RangeHyp symbol -> (lo, hi) as Fractions."""
    raise NotImplementedError
