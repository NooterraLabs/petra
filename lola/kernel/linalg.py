"""Exact rational linear algebra on terms.Matrix. No pivoting heuristics, no tolerances.

The kernel verifies factorizations; it never computes one. Solvers compute L, d and
x, y, s, u however they like.
"""
from __future__ import annotations

from .interval import Interval, Q
from .terms import Matrix

Vector = tuple[Q, ...]


def matvec(A: Matrix, x: Vector) -> Vector:
    raise NotImplementedError


def rmatvec(A: Matrix, y: Vector) -> Vector:
    """A^T y."""
    raise NotImplementedError


def dot(x: Vector, y: Vector) -> Q:
    raise NotImplementedError


def gram_sum(weights: Vector, factors: tuple[Matrix, ...], dim: int) -> dict[tuple[int, int], Q]:
    """sum_j weights_j V_j V_j^T as a sparse symmetric map, upper triangle only."""
    raise NotImplementedError


def gram_quadratic(weights: tuple[Interval, ...], factors: tuple[Matrix, ...], v: Vector) -> Interval:
    """v^T (sum_j w_j V_j V_j^T) v = sum_j w_j * |V_j^T v|^2, enclosed over interval weights."""
    raise NotImplementedError


def is_unit_lower(L: Matrix, n: int) -> bool:
    """n x n, ones on the diagonal, zeros above it."""
    raise NotImplementedError


def ldl_product(L: Matrix, d: Vector) -> dict[tuple[int, int], Q]:
    """L diag(d) L^T, upper triangle only, sparse. Compared for exact equality with
    gram_sum; both drop zeros so dict equality is matrix equality."""
    raise NotImplementedError
