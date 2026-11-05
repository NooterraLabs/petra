"""R2 solver. Untrusted.

Proof: DefinedHyp ranges from the R3 lemma solver, reference weights r_j =
enclose(w_j, box).lo rounded down to a short dyadic, M_ref built exactly, and LDL^T
computed exactly with Fractions and no pivoting (positive definite needs none). The
evidence carries the DefinedRanges it was computed over.
Refutation, only for a statement with no DefinedHyp: at the box corner or centre whose
matrix has the smallest eigenvalue (numpy eigh), take the eigenvector, rationalise it, and
check v^T M v <= 0 exactly before offering it.
"""
from __future__ import annotations

import math
from fractions import Fraction
from typing import Iterator, Mapping

import numpy as np

from ..kernel import Evidence, Interval, KernelArithmeticError, Matrix, NotAffine, Statement, enclose
from ..kernel.rules.r2_definite import GramPositiveDefinite, LDLFactor, NegativeDirection
from .r1_linear import dense, range_box, rational, rmatvec
from .r3_hypercircle import defined_ranges

_FAILURES = (KernelArithmeticError, NotAffine, ValueError, np.linalg.LinAlgError)


def solve(statement: Statement) -> Iterator[Evidence]:
    goal = statement.goal
    try:
        defined = defined_ranges(statement)
        box = {**range_box(statement), **{d.sym: Interval(d.lo, d.hi) for d in defined}}
        weights = tuple(_floor(enclose(t.weight, box).lo) for t in goal.terms)
    except _FAILURES:
        return
    found = exact_ldl(_gram(weights, goal), goal.dim)
    if found is not None:
        yield Evidence(LDLFactor(weights, *found), defined)
    elif not defined:
        ray = _negative_direction(goal, range_box(statement))
        if ray is not None:
            yield ray


def exact_ldl(entries: dict, n: int) -> tuple | None:
    """(L, d) with L unit lower triangular and L diag(d) L^T equal to the symmetric matrix
    whose upper triangle is `entries`, or None when a pivot is not positive."""
    M = [[Fraction(0)] * n for _ in range(n)]
    for (i, j), v in entries.items():
        M[i][j] = M[j][i] = Fraction(v)
    L = [[Fraction(0)] * n for _ in range(n)]
    d: list[Fraction] = []
    for j in range(n):
        dj = M[j][j] - sum((L[j][k] * L[j][k] * d[k] for k in range(j)), Fraction(0))
        if dj <= 0:
            return None
        d.append(dj)
        for i in range(j + 1, n):
            L[i][j] = (M[i][j] - sum((L[i][k] * L[j][k] * d[k] for k in range(j)), Fraction(0))) / dj
    lower = tuple((i, j, Fraction(1) if i == j else L[i][j]) for i in range(n) for j in range(i + 1) if i == j or L[i][j])
    return Matrix(n, n, lower), tuple(d)


def _gram(weights: tuple[Fraction, ...], goal: GramPositiveDefinite) -> dict:
    """sum_j r_j V_j V_j^T by its upper triangle."""
    out: dict[tuple[int, int], Fraction] = {}
    for r, term in zip(weights, goal.terms):
        columns: dict[int, list[tuple[int, Fraction]]] = {}
        for i, j, v in term.factor.entries:
            columns.setdefault(j, []).append((i, v))
        for column in columns.values():
            for a, va in column:
                for b, vb in column:
                    if a <= b:
                        out[a, b] = out.get((a, b), Fraction(0)) + r * va * vb
    return out


def _floor(x: Fraction) -> Fraction:
    """A dyadic with about 30 significant bits, at most x."""
    if not x:
        return Fraction(0)
    grid = Fraction(2) ** (30 - (abs(x).numerator.bit_length() - abs(x).denominator.bit_length()))
    return Fraction(math.floor(x * grid)) / grid


def _negative_direction(goal: GramPositiveDefinite, box: Mapping[str, Interval]) -> Evidence | None:
    if goal.dim == 0:
        return None
    best = None
    for point in ({s: r.lo for s, r in box.items()}, {s: r.hi for s, r in box.items()}, {s: r.midpoint() for s, r in box.items()}):
        at = {s: Interval(v, v) for s, v in point.items()}
        M = np.zeros((goal.dim, goal.dim))
        try:
            for t in goal.terms:
                V = dense(t.factor)
                M += float(enclose(t.weight, at).midpoint()) * (V @ V.T)
            values, vectors = np.linalg.eigh(M)
        except _FAILURES:
            continue
        if best is None or values[0] < best[0]:
            best = (values[0], vectors[:, 0], point)
    if best is None or best[0] > 0:
        return None
    v = rational(best[1], bits=30)
    at = {s: Interval(x, x) for s, x in best[2].items()}
    total = Interval(Fraction(0), Fraction(0))
    for t in goal.terms:
        z = rmatvec(t.factor, v)
        total = total + enclose(t.weight, at) * Interval.point(sum((zi * zi for zi in z), Fraction(0)))
    if not any(v) or total.hi > 0:
        return None
    return Evidence(NegativeDirection(tuple(sorted(best[2].items())), v))
