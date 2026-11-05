"""Exact rational linear algebra on terms.Matrix. No pivoting heuristics, no tolerances.

The kernel verifies factorizations; it never computes one. Solvers compute L, d and
x, y, s, u however they like.

Every function trusts that its matrices are canonical (entries sorted, in range, nonzero,
no duplicates), which check.py establishes through the strict codec before any rule runs.
"""
from __future__ import annotations

from .interval import Interval, Q
from .terms import Matrix

Vector = tuple[Q, ...]
Upper = dict[tuple[int, int], Q]
"""A symmetric matrix by its nonzero upper-triangle entries, so dict equality is matrix
equality."""


def matvec(A: Matrix, x: Vector) -> Vector:
    y = [Q(0)] * A.rows
    for i, j, v in A.entries:
        y[i] += v * x[j]
    return tuple(y)


def rmatvec(A: Matrix, y: Vector) -> Vector:
    """A^T y."""
    z = [Q(0)] * A.cols
    for i, j, v in A.entries:
        z[j] += v * y[i]
    return tuple(z)


def dot(x: Vector, y: Vector) -> Q:
    return sum((a * b for a, b in zip(x, y, strict=True)), Q(0))


def _columns(M: Matrix) -> list[list[tuple[int, Q]]]:
    columns: list[list[tuple[int, Q]]] = [[] for _ in range(M.cols)]
    for i, j, v in M.entries:
        columns[j].append((i, v))
    return columns


def _outer_sum(terms) -> Upper:
    """sum of w c c^T over (w, column c) pairs, upper triangle, zeros dropped."""
    out: Upper = {}
    for w, column in terms:
        for a, va in column:
            for b, vb in column:
                if a <= b:
                    out[a, b] = out.get((a, b), Q(0)) + w * va * vb
    return {k: v for k, v in out.items() if v}


def gram_sum(weights: Vector, factors: tuple[Matrix, ...]) -> Upper:
    """sum_j weights_j V_j V_j^T, as the outer products of every column of every V_j."""
    return _outer_sum((w, c) for w, V in zip(weights, factors, strict=True) for c in _columns(V))


def gram_quadratic(weights: tuple[Interval, ...], factors: tuple[Matrix, ...], v: Vector) -> Interval:
    """v^T (sum_j w_j V_j V_j^T) v = sum_j w_j * |V_j^T v|^2, enclosed over interval weights."""
    total = Interval(Q(0), Q(0))
    for w, V in zip(weights, factors, strict=True):
        z = rmatvec(V, v)
        total = total + w * Interval.point(dot(z, z))
    return total


def is_unit_lower(L: Matrix, n: int) -> bool:
    """n x n, ones on the diagonal, zeros above it."""
    diagonal = [i for i, j, v in L.entries if i == j and v == 1]
    return L.rows == L.cols == n and all(j <= i for i, j, _ in L.entries) and diagonal == list(range(n))


def ldl_product(L: Matrix, d: Vector) -> Upper:
    """L diag(d) L^T = sum_k d_k l_k l_k^T over the columns l_k of L. Compared for exact
    equality with gram_sum."""
    return _outer_sum(zip(d, _columns(L), strict=True))
