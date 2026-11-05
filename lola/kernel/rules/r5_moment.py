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

from ..evaluate import Box
from ..evidence import Partition, Vector
from ..interval import Q
from ..terms import Expr
from .base import Fault, RuleSpec


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
    """TODO:
      require len(y) == len(moments); random syms disjoint from hyp syms
      Lj = enclose(lo_j, box).lo ; Hj = enclose(hi_j, box).hi
      bound = y0 + sum_j max(y_j * Lj, y_j * Hj)        # exact rationals
      require bound <= goal.p                           # TooWeak otherwise
      support = {x.sym: Interval(enclose(x.lo, box).lo, enclose(x.hi, box).hi)}
      cells = r4_enclosure.leaves(partition, box | support)
      for each cell: G = enclose(g, cell); F = enclose(fail, cell)
          require G.lo >= 1  or  (G.lo >= 0 and F.hi <= 0)
    """
    raise NotImplementedError


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
