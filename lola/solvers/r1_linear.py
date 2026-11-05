"""R1 solver: scipy.optimize.linprog (HiGHS) per vertex, then exact repair. Untrusted.

Proof: for each vertex, maximise the minimum slack to the bounds (a Chebyshev-style LP)
so the rounded point stays strictly inside, then repair A x = b exactly in rationals.
Refutation: if a vertex LP is infeasible, solve the alternative LP
    max  b^T y - sum_i (hi_i p_i - lo_i n_i)   s.t.  A^T y = p - n,  p, n >= 0,  |y| <= 1,
rationalise y, choose the point, and evaluate the Farkas inequality exactly before
offering it. In truss terms y is a collapse mechanism.

The exact helpers below (range_box, vertices, values_at, rational, solve_exact) serve the
R2 and R3 solvers too.
"""
from __future__ import annotations

import math
from fractions import Fraction
from typing import Iterable, Iterator, Mapping

import numpy as np
from scipy.optimize import linprog

from ..kernel import (
    Evidence,
    Expr,
    Interval,
    KernelArithmeticError,
    Matrix,
    NotAffine,
    RangeHyp,
    Statement,
    affine_coefficients,
    enclose,
    free_syms,
)
from ..kernel.rules.r1_linear import FarkasRay, FeasiblePoints, LinearFeasible

Vector = tuple[Fraction, ...]
_ZERO = Fraction(0)


def range_box(statement: Statement) -> dict[str, Interval]:
    """RangeHyp symbol -> range, in the statement's (sorted) order."""
    return {h.sym: Interval(h.lo, h.hi) for h in statement.hyps if isinstance(h, RangeHyp)}


def vertices(box: Mapping[str, Interval], syms: tuple[str, ...]) -> tuple[dict[str, Fraction], ...]:
    """The kernel's vertex order: bit k of the vertex index selects hi of syms[k]."""
    return tuple({s: box[s].hi if v >> k & 1 else box[s].lo for k, s in enumerate(syms)} for v in range(1 << len(syms)))


def values_at(exprs: tuple[Expr, ...], syms: tuple[str, ...], point: Mapping[str, Fraction]) -> Vector:
    """Exact values of expressions affine in `syms`. Raises NotAffine otherwise."""
    out = []
    for e in exprs:
        c0, cs = affine_coefficients(e, syms)
        out.append(c0 + sum((c * point[s] for c, s in zip(cs, syms)), _ZERO))
    return tuple(out)


def dense(A: Matrix) -> np.ndarray:
    M = np.zeros((A.rows, A.cols))
    for i, j, v in A.entries:
        M[i, j] = float(v)
    return M


def matvec(A: Matrix, x: Vector) -> Vector:
    y = [_ZERO] * A.rows
    for i, j, v in A.entries:
        y[i] += v * x[j]
    return tuple(y)


def rmatvec(A: Matrix, y: Vector) -> Vector:
    z = [_ZERO] * A.cols
    for i, j, v in A.entries:
        z[j] += v * y[i]
    return tuple(z)


def rational(values: Iterable[float], bits: int = 44) -> Vector:
    """Each float rounded to the dyadic grid `bits` below the largest magnitude, so the
    rationals stay short. Raises ValueError for a non-finite value."""
    values = [float(v) for v in values]
    if not all(math.isfinite(v) for v in values):
        raise ValueError("a float solve returned a non-finite value")
    scale = max(map(abs, values), default=0.0)
    if scale == 0:
        return tuple(_ZERO for _ in values)
    grid = Fraction(2) ** (bits - math.frexp(scale)[1])
    return tuple(Fraction(round(Fraction(v) * grid)) / grid for v in values)


def solve_exact(A: Matrix, b: Vector) -> Vector | None:
    """One exact solution of A x = b by Gauss-Jordan elimination in Fractions, free
    variables at 0. None when the system is inconsistent."""
    rows = [[_ZERO] * A.cols + [Fraction(bi)] for bi in b]
    for i, j, v in A.entries:
        rows[i][j] = v
    pivots: list[int] = []
    for c in range(A.cols):
        r = len(pivots)
        p = next((k for k in range(r, A.rows) if rows[k][c] != 0), None)
        if p is None:
            continue
        rows[r], rows[p] = rows[p], rows[r]
        rows[r] = [x / rows[r][c] for x in rows[r]]
        for k in range(A.rows):
            if k != r and rows[k][c] != 0:
                f = rows[k][c]
                rows[k] = [x - f * y for x, y in zip(rows[k], rows[r])]
        pivots.append(c)
    if any(rows[k][-1] != 0 for k in range(len(pivots), A.rows)):
        return None
    x = [_ZERO] * A.cols
    for k, c in enumerate(pivots):
        x[c] = rows[k][-1]
    return tuple(x)


def repair(A: Matrix, b: Vector, x: Vector) -> Vector | None:
    """x moved by an exact correction so that A x = b holds exactly, or None."""
    fix = solve_exact(A, tuple(bi - ri for bi, ri in zip(b, matvec(A, x))))
    return None if fix is None else tuple(xi + ci for xi, ci in zip(x, fix))


def _bounds(goal: LinearFeasible, box: Mapping[str, Interval]) -> tuple[list, list]:
    """The kernel's bounds for a vertex check: each at its worst over `box`."""
    return [None if e is None else enclose(e, box).hi for e in goal.lower], [None if e is None else enclose(e, box).lo for e in goal.upper]


def solve(statement: Statement) -> Iterator[Evidence]:
    goal = statement.goal
    box = range_box(statement)
    syms = tuple(sorted(free_syms(goal.b)))
    try:
        lows, highs = _bounds(goal, box)
        rhs = [values_at(goal.b, syms, v) for v in vertices(box, syms)]
    except (KernelArithmeticError, NotAffine):
        return
    points = []
    for vertex, b in zip(vertices(box, syms), rhs):
        x = _inside(goal.A, b, lows, highs)
        if x is None:
            ray = farkas_ray(statement, vertex)
            if ray is not None:
                yield ray
            return
        points.append(x)
    yield Evidence(FeasiblePoints(tuple(points)))


def _inside(A: Matrix, b: Vector, lows: list, highs: list) -> Vector | None:
    """A point with A x = b exactly and lows <= x <= highs, or None."""
    n = A.cols
    rows, rhs = [], []
    for i, (lo, hi) in enumerate(zip(lows, highs)):
        for bound, sign in ((lo, -1.0), (hi, 1.0)):
            if bound is not None:
                row = np.zeros(n + 1)
                row[i], row[n] = sign, 1.0
                rows.append(row)
                rhs.append(sign * float(bound))
    scale = max([abs(float(v)) for v in (*b, *rhs)], default=1.0) or 1.0
    res = linprog(
        np.r_[np.zeros(n), -1.0],
        A_ub=np.array(rows) if rows else None,
        b_ub=np.array(rhs) if rows else None,
        A_eq=np.hstack([dense(A), np.zeros((A.rows, 1))]) if A.rows else None,
        b_eq=np.array([float(v) for v in b]) if A.rows else None,
        bounds=[(None, None)] * n + [(0, scale)],
        method="highs",
    )
    if res.status != 0:
        return None
    x = repair(A, b, rational(res.x[:n]))
    if x is None or any(lo is not None and xi < lo for xi, lo in zip(x, lows)) or any(hi is not None and xi > hi for xi, hi in zip(x, highs)):
        return None
    return x


def farkas_ray(statement: Statement, vertex: dict) -> Evidence | None:
    """A FarkasRay at `vertex` (values for the symbols of b), checked exactly here with the
    kernel's own inequality, or None. The other hypotheses take the end of their range
    that lowers the cap for the ray found with worst-case bounds."""
    goal = statement.goal
    box = range_box(statement)
    syms = tuple(sorted(free_syms(goal.b)))
    try:
        b = values_at(goal.b, syms, vertex)
        lows, highs = _bounds(goal, box)
        rays = [_ray(goal.A, b, lows, highs)]
        point = {s: vertex.get(s, r.lo) for s, r in box.items()}
        if rays[0] is not None:
            for s, r in box.items():
                if s not in vertex and r.lo < r.hi:
                    point[s] = min((r.lo, r.hi), key=lambda v: _cap(goal, rays[0], {**point, s: v}))
        lows, highs = _bounds(goal, {s: Interval(v, v) for s, v in point.items()})
        rays.insert(0, _ray(goal.A, b, lows, highs))
        for y in rays:
            if y is not None and _refutes(goal, y, point):
                return Evidence(FarkasRay(tuple(sorted(point.items())), y))
    except (KernelArithmeticError, NotAffine, ValueError):
        return None
    return None


def _ray(A: Matrix, b: Vector, lows: list, highs: list) -> Vector | None:
    m, n = A.rows, A.cols
    if m == 0:
        return None
    c = np.r_[
        [-float(v) for v in b],
        [0.0 if hi is None else float(hi) for hi in highs],
        [0.0 if lo is None else -float(lo) for lo in lows],
    ]
    res = linprog(
        c,
        A_eq=np.hstack([dense(A).T, -np.eye(n), np.eye(n)]),
        b_eq=np.zeros(n),
        bounds=[(-1, 1)] * m + [(0, 0) if hi is None else (0, None) for hi in highs] + [(0, 0) if lo is None else (0, None) for lo in lows],
        method="highs",
    )
    if res.status != 0 or -res.fun <= 0:
        return None
    return rational(res.x[:m], bits=30)


def _cap(goal: LinearFeasible, y: Vector, point: Mapping[str, Fraction]) -> Fraction | float:
    """The kernel's cap: sum over z_i != 0 of z_i times the bound z pushes along, at the point."""
    at = {s: Interval(v, v) for s, v in point.items()}
    cap = _ZERO
    for zi, lo, hi in zip(rmatvec(goal.A, y), goal.lower, goal.upper):
        if zi != 0:
            side = hi if zi > 0 else lo
            if side is None:
                return math.inf
            cap += (Interval(zi, zi) * enclose(side, at)).hi
    return cap


def _refutes(goal: LinearFeasible, y: Vector, point: Mapping[str, Fraction]) -> bool:
    at = {s: Interval(v, v) for s, v in point.items()}
    yb = sum((Interval(yi, yi) * enclose(bi, at) for yi, bi in zip(y, goal.b)), Interval(_ZERO, _ZERO))
    return yb.lo > _cap(goal, y, point)
