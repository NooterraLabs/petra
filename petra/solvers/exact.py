"""Float-to-exact repair shared by solvers. Untrusted.

The pattern every solver uses: solve in floats, round to rationals, then repair the
equality constraints exactly so the kernel's exact equality checks pass, and keep a
margin on inequalities so rounding never lands on the wrong side. Bounds are each
solver's own business: these helpers know only matrices and equalities.
"""
from __future__ import annotations

from fractions import Fraction

import numpy as np

from ..kernel import Matrix, RangeHyp, Statement

Vector = tuple[Fraction, ...]


def to_numpy(A: Matrix):
    """Dense float64 array."""
    dense = np.zeros((A.rows, A.cols))
    for i, j, v in A.entries:
        dense[i, j] = float(v)
    return dense


def rationalize(x, max_den: int = 10**12) -> Vector:
    """Fraction.limit_denominator per entry."""
    return tuple(Fraction(float(v)).limit_denominator(max_den) for v in np.ravel(x))


def solve_exact(A: Matrix, b: Vector) -> Vector | None:
    """An exact rational solution of A x = b by Gauss-Jordan elimination over Fractions,
    with every free variable at 0, so a square nonsingular system gets its one solution
    and a full-row-rank system gets a basic one. None when no solution exists."""
    if len(b) != A.rows:
        raise ValueError(f"b has {len(b)} entries for a matrix with {A.rows} rows")
    n = A.cols
    rows = [[Fraction(0)] * n + [Fraction(bi)] for bi in b]
    for i, j, v in A.entries:
        rows[i][j] = Fraction(v)
    pivots: list[int] = []
    for c in range(n):
        r = len(pivots)
        p = next((k for k in range(r, A.rows) if rows[k][c] != 0), None)
        if p is None:
            continue
        rows[r], rows[p] = rows[p], rows[r]
        pivot = rows[r][c]
        rows[r] = [x / pivot for x in rows[r]]
        for k in range(A.rows):
            if k != r and rows[k][c] != 0:
                factor = rows[k][c]
                rows[k] = [x - factor * y for x, y in zip(rows[k], rows[r])]
        pivots.append(c)
        if len(pivots) == A.rows:
            break
    if any(rows[k][n] != 0 for k in range(len(pivots), A.rows)):
        return None
    x = [Fraction(0)] * n
    for r, c in enumerate(pivots):
        x[c] = rows[r][n]
    return tuple(x)


def project_onto_equalities(A: Matrix, b: Vector, x: Vector, basis: tuple[int, ...]) -> Vector:
    """Fix the non-basic entries of x and change only the basic ones, by an exact
    correction, so A x = b holds exactly. `basis` comes from the LP solver's final basis.
    Raises ValueError when the basic columns cannot absorb the residual."""
    residual = tuple(bi - ax for bi, ax in zip(b, _product(A, x)))
    if not any(residual):
        return tuple(x)
    column = {j: k for k, j in enumerate(basis)}
    entries = tuple((i, column[j], v) for i, j, v in A.entries if j in column)
    delta = solve_exact(Matrix(A.rows, len(basis), tuple(sorted(entries))), residual)
    if delta is None:
        raise ValueError("the basic columns cannot absorb the equality residual")
    repaired = list(x)
    for j, k in column.items():
        repaired[j] += delta[k]
    return tuple(repaired)


def range_box(statement: Statement) -> dict:
    """RangeHyp symbol -> (lo, hi) as Fractions."""
    return {h.sym: (h.lo, h.hi) for h in statement.hyps if isinstance(h, RangeHyp)}


def _product(A: Matrix, x: Vector) -> Vector:
    y = [Fraction(0)] * A.rows
    for i, j, v in A.entries:
        y[i] += v * x[j]
    return tuple(y)
