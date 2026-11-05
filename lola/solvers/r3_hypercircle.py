"""R3 solver and DefinedHyp lemmas. Untrusted.

Per vertex: solve the weighted least-norm problem in floats with weights at their
midpoints, u~ = (B W^-1 B^T)^+ f and s~ = W^-1 B^T u~. Repair s~ exactly onto
B s = f(v); u needs no repair (any u is admissible). The bound tightness depends only on
how close s and t = W^-1 B^T u are to s*, so float accuracy matters for sharpness, never
for soundness.

Refutation: at each vertex, with every other hypothesis at its low end and then at its
high end, the same fields at that point, offered when the hypercircle there lies wholly
outside a bound.
"""
from __future__ import annotations

import math
from fractions import Fraction
from typing import Iterator, Mapping

import numpy as np

from ..kernel import DefinedHyp, DefinedRange, Evidence, Interval, KernelArithmeticError, NotAffine, Statement, enclose, free_syms
from ..kernel.rules.r3_hypercircle import (
    Hypercircle,
    HypercircleFields,
    HypercircleViolation,
    MinimizerBound,
    MinimizerComponent,
    QuadraticProblem,
    enclose_minimizer,
)
from .r1_linear import dense, range_box, rational, repair, rmatvec, values_at, vertices

_FAILURES = (KernelArithmeticError, NotAffine, ValueError, np.linalg.LinAlgError)


def solve(statement: Statement) -> Iterator[Evidence]:
    goal = statement.goal
    box = range_box(statement)
    try:
        defined = defined_ranges(statement)
        fields = fields_for(goal.problem, {**box, **{d.sym: Interval(d.lo, d.hi) for d in defined}})
    except _FAILURES:
        fields = None
    if fields is not None:
        yield Evidence(Hypercircle(fields), defined)
    if not defined:
        yield from _violations(goal, box)


def fields_for(problem: QuadraticProblem, box: dict) -> HypercircleFields:
    """HypercircleFields for a QuadraticProblem over the box. Raises ValueError when
    B s = f has no exact solution at some vertex."""
    syms = tuple(sorted(free_syms(problem.f)))
    weights = np.array([float(enclose(w, box).midpoint()) for w in problem.w])
    solved: dict[tuple, tuple] = {}
    fields = []
    for vertex in vertices(box, syms):
        key = tuple(vertex.values())
        if key not in solved:
            solved[key] = _field(problem, weights, values_at(problem.f, syms, vertex))
        fields.append(solved[key])
    return HypercircleFields(tuple(s for s, _ in fields), tuple(u for _, u in fields))


def _field(problem: QuadraticProblem, weights: np.ndarray, f: tuple[Fraction, ...]) -> tuple[tuple, tuple]:
    B = problem.B
    if B.rows == 0:
        return tuple(Fraction(0) for _ in range(B.cols)), ()
    M = dense(B)
    stiffness = (M / weights) @ M.T
    u = np.linalg.lstsq(stiffness, np.array([float(v) for v in f]), rcond=None)[0]
    s = repair(B, f, rational((M.T @ u) / weights))
    if s is None:
        raise ValueError("B s = f has no solution")
    return s, rational(u)


def defined_ranges(statement: Statement, box: Mapping[str, Interval] | None = None) -> tuple[DefinedRange, ...]:
    """For each DefinedHyp: compute fields and their enclosure once per problem, enclose
    the component with the kernel's own formula, round outward by about a relative 1e-9
    to a short dyadic, and propose that range. The box is the statement's RangeHyp box
    unless one is given; a point box gives the ranges the kernel checks a refutation at
    that point with. Raises ValueError when a problem has no admissible field."""
    box = range_box(statement) if box is None else box
    found: dict[QuadraticProblem, tuple[HypercircleFields, tuple]] = {}
    out = []
    for h in statement.hyps:
        if isinstance(h, DefinedHyp):
            problem = h.definition.problem
            if problem not in found:
                fields = fields_for(problem, box)
                enclosure = enclose_minimizer(problem, fields, box)
                if not isinstance(enclosure, tuple):
                    raise ValueError(enclosure.reason)
                found[problem] = fields, enclosure
            out.append(_range(h.sym, h.definition, *found[problem], box))
    return tuple(out)


def _range(sym: str, definition: MinimizerComponent, fields: HypercircleFields, found: tuple, box: Mapping[str, Interval]) -> DefinedRange:
    q = enclose(definition.scale, box) * found[0][definition.index]
    scale = max(abs(q.lo), abs(q.hi))
    grid = Fraction(2) ** (30 - (scale.numerator.bit_length() - scale.denominator.bit_length()) if scale else 30)
    return DefinedRange(sym, Fraction(math.floor(q.lo * grid)) / grid, Fraction(math.ceil(q.hi * grid)) / grid, fields)


def _violations(goal: MinimizerBound, box: Mapping[str, Interval]) -> Iterator[Evidence]:
    problem = goal.problem
    syms = tuple(sorted(free_syms(problem.f)))
    for vertex in vertices(box, syms):
        for end in ("lo", "hi"):
            point = {s: vertex.get(s, getattr(r, end)) for s, r in box.items()}
            at = {s: Interval(v, v) for s, v in point.items()}
            try:
                fields = fields_for(problem, at)
                which = _violated(goal, fields, at)
            except _FAILURES:
                continue
            if which is not None:
                yield Evidence(HypercircleViolation(tuple(sorted(point.items())), fields.s[0], fields.u[0], which))
                return


def _violated(goal: MinimizerBound, fields: HypercircleFields, at: Mapping[str, Interval]) -> int | None:
    """The bound the hypercircle at a point lies wholly outside (-1 for the energy), as the
    kernel decides it, or None."""
    found = enclose_minimizer(goal.problem, fields, at)
    if not isinstance(found, tuple):
        return None
    for k, bound in enumerate(goal.bounds):
        q = enclose(bound.scale, at) * found[0][bound.index]
        if (bound.hi is not None and q.lo > enclose(bound.hi, at).hi) or (bound.lo is not None and q.hi < enclose(bound.lo, at).lo):
            return k
    if goal.energy_hi is not None:
        syms = tuple(sorted(free_syms(goal.problem.f)))
        f = values_at(goal.problem.f, syms, {s: r.lo for s, r in at.items()})
        u = fields.u[0]
        e = rmatvec(goal.problem.B, u)
        dual = Interval.point(2 * sum((fi * ui for fi, ui in zip(f, u)), Fraction(0))) - sum(
            (Interval.point(ei * ei) / enclose(w, at) for ei, w in zip(e, goal.problem.w)), Interval.point(Fraction(0))
        )
        if dual.lo > enclose(goal.energy_hi, at).hi:
            return -1
    return None
