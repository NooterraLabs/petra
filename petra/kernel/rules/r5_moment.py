"""R5. Moment-problem duality: a probability bound from support and moment intervals.

Theorem used: if g(x) = y0 + sum_j y_j fn_j(x) satisfies g >= 1_{fail > 0} on the
support (for every h), then for every admissible measure mu,
    mu{fail > 0} = E[1_fail] <= E[g] = y0 + sum_j y_j E[fn_j]
                <= y0 + sum_j max(y_j lo_j, y_j hi_j).
Domination is checked cell by cell on a partition of (support x hypothesis box): on each
leaf either g >= 1, or g >= 0 and fail <= 0.

No distribution is assumed. "Load known only by range and mean" is fn_1(x) = x with
lo_1 = hi_1 = mean.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..evaluate import Box, enclose
from ..evidence import Partition, Vector
from ..interval import Interval, Q
from ..terms import Add, Const, Expr, Max, Min, Mul, Neg
from .base import Fault, Invalid, RuleSpec, TooWeak
from .r4_enclosure import all_nonpositive_on


@dataclass(frozen=True, slots=True)
class RandomVar:
    """A random variable bound inside a MomentBound goal, supported on [lo, hi].

    lo and hi are Exprs over RangeHyp symbols so that the owner's signed range enters
    through a labelled hypothesis and shows up in the footprint. The rule partitions the
    hull [enclose(lo).lo, enclose(hi).hi], a superset of every admissible support."""

    sym: str
    lo: Expr
    hi: Expr


@dataclass(frozen=True, slots=True)
class MomentConstraint:
    """E[fn(X)] lies in [lo, hi]. fn mentions only RandomVar symbols; lo and hi are Exprs
    over RangeHyp symbols (a signed mean is a point hypothesis)."""

    fn: Expr
    lo: Expr
    hi: Expr


@dataclass(frozen=True, slots=True)
class MomentBound:
    """Goal. For all h in the box and every probability measure mu on the support box of
    `random` that meets every moment constraint:  mu{ x : fail(x, h) > 0 } <= p."""

    random: tuple[RandomVar, ...]
    moments: tuple[MomentConstraint, ...]
    fail: Expr
    p: Q


@dataclass(frozen=True, slots=True)
class MomentDual:
    """Proof. g(x) = y0 + sum_j y_j fn_j(x). On every leaf of `partition` (over random
    and hypothesis symbols) either g >= 1, or g >= 0 and fail <= 0."""

    y0: Q
    y: Vector
    partition: Partition


def binds(goal: MomentBound) -> frozenset[str]:
    """The random variables are bound by the goal, not hypotheses of the statement."""
    return frozenset(x.sym for x in goal.random)


def prove(goal: MomentBound, body: MomentDual, box: Box) -> Fault | None:
    """Theorem: weak duality for the moment problem (module docstring).

    Fix h in the box and an admissible measure mu. With L_j = inf lo_j and H_j = sup hi_j
    over the box, E[fn_j] lies in [lo_j(h), hi_j(h)], inside [L_j, H_j], and y_j m is
    largest at an end of that interval, so E[g] <= y0 + sum_j max(y_j L_j, y_j H_j),
    which the rule requires to be <= p exactly. Domination is the R4 goal
    min(1 - g, max(-g, fail)) <= 0, walked over the partition of the support hull times
    the hypothesis box. At any point where that holds, g >= 1, or g >= 0 and fail <= 0,
    so g >= 1_{fail > 0}. Every admissible support lies in the hull, so
    mu{fail > 0} <= E[g] <= p. The walk also shows every fn_j is defined and bounded on
    the hull, so E[g] exists. If no measure is admissible the goal holds vacuously.

    On a cell, the walk's test is exactly G.lo >= 1, or G.lo >= 0 and F.hi <= 0, for the
    enclosures G of g and F of fail. Conservative: the moments are taken at their worst
    over the whole box, and domination must hold over the whole hull.
    """
    syms = [x.sym for x in goal.random]
    if len(set(syms)) != len(syms) or set(syms) & set(box) or len(body.y) != len(goal.moments):
        return Invalid(f"random variables {syms} must be distinct and new, with one y per moment")
    bound = body.y0
    for yj, m in zip(body.y, goal.moments):
        bound += max(yj * enclose(m.lo, box).lo, yj * enclose(m.hi, box).hi)
    if bound > goal.p:
        return TooWeak(f"the dual bound {bound} exceeds p = {goal.p}")
    support = {x.sym: Interval(enclose(x.lo, box).lo, enclose(x.hi, box).hi) for x in goal.random}
    g = Add((Const(body.y0),) + tuple(Mul((Const(yj), m.fn)) for yj, m in zip(body.y, goal.moments)))
    dominated = Min((Add((Const(Q(1)), Neg(g))), Max((Neg(g), goal.fail))))
    return all_nonpositive_on((dominated,), body.partition, {**box, **support})


RULE = RuleSpec(
    id="R5",
    goal=MomentBound,
    proofs=(MomentDual,),
    refutations=(),
    tags=(
        ("random_var", RandomVar),
        ("moment_constraint", MomentConstraint),
        ("moment_bound", MomentBound),
        ("moment_dual", MomentDual),
    ),
    lemmas=(),
    prove=prove,
    refute=None,
    binds=binds,
)
