"""R4. Interval enclosure over a box with a branch-and-bound partition.

Theorem used: the leaves of a binary split tree cover the root box (each split covers
its cell by [lo, at] and [at, hi]), and the natural interval extension encloses the
range of an expression on each leaf. If every expr encloses <= 0 on every leaf, every
expr is <= 0 on the box.

Closed-form checks (wire temperature, voltage drop, k-factor, bolt tension, member
Euler buckling, port contract inclusion) and family certificates all reduce to this.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..evaluate import Box, enclose
from ..evidence import Leaf, Partition, Point
from ..interval import Interval
from ..terms import Expr
from .base import Fault, Invalid, RuleSpec, TooWeak

MAX_DEPTH = 64
"""Guards evidence size and the walk, not soundness: any finite split tree covers its box."""


@dataclass(frozen=True, slots=True)
class AllNonpositive:
    """Goal. For all h in the box,  e_k(h) <= 0  for every k."""

    exprs: tuple[Expr, ...]


@dataclass(frozen=True, slots=True)
class Enclosure:
    """Proof. A partition of the hypothesis box; every expr encloses <= 0 on every leaf."""

    partition: Partition


@dataclass(frozen=True, slots=True)
class PointWitness:
    """Refutation: expr `which` encloses strictly above 0 at `point`, with each DefinedHyp
    over the range its lemma proves there."""

    point: Point
    which: int


def leaves(partition: Partition, box: Box) -> tuple[dict, ...] | Fault:
    """Cells of the partition, or Invalid (unknown sym, split point not strictly inside
    the cell, depth over MAX_DEPTH).

    Each split replaces its cell C by the halves where sym <= at and sym >= at, whose
    union is C. By induction on the tree the leaves cover the box they started from.
    """
    found, stack = [], [(partition, dict(box), 0)]
    while stack:
        node, cell, depth = stack.pop()
        if isinstance(node, Leaf):
            found.append(cell)
            continue
        if depth >= MAX_DEPTH:
            return Invalid(f"the partition is deeper than {MAX_DEPTH}")
        r = cell.get(node.sym)
        if r is None or not r.lo < node.at < r.hi:
            return Invalid(f"split on {node.sym} at {node.at} is not strictly inside its cell {r}")
        stack.append((node.right, {**cell, node.sym: Interval(node.at, r.hi)}, depth + 1))
        stack.append((node.left, {**cell, node.sym: Interval(r.lo, node.at)}, depth + 1))
    return tuple(found)


def all_nonpositive_on(exprs: tuple[Expr, ...], partition: Partition, box: Box) -> Fault | None:
    """Shared by R4 and R5: walk the leaves, require enclose(e, cell).hi <= 0 (TooWeak
    names the first leaf that fails)."""
    cells = leaves(partition, box)
    if isinstance(cells, Invalid):
        return cells
    for n, cell in enumerate(cells):
        for k, e in enumerate(exprs):
            hi = enclose(e, cell).hi
            if hi > 0:
                return TooWeak(f"expression {k} encloses up to {hi} on leaf {n}")
    return None


def prove(goal: AllNonpositive, body: Enclosure, box: Box) -> Fault | None:
    """Theorem: the leaves of a split tree cover the box (see `leaves`), and the natural
    interval extension contains an expression's value at every point of a cell
    (evaluate.enclose). So if enclose(e, cell).hi <= 0 for every expression on every
    leaf, then e(h) <= 0 at every h in the box: h lies in some leaf, and there e(h) is
    at most that leaf's upper enclosure. The enclosure also certifies that each
    expression is defined everywhere on the box, since it raises otherwise.

    Conservative in one way: the natural extension overestimates the range when a symbol
    occurs more than once, so a true goal may need a finer partition (TooWeak until
    then).
    """
    return all_nonpositive_on(goal.exprs, body.partition, box)


def refute(goal: AllNonpositive, body: PointWitness, box: Box) -> Fault | None:
    """At every point p of the box, which fixes each RangeHyp at the evidence point and
    spans each DefinedHyp's proven range, enclose(e, box).lo > 0 means the real e(p) > 0,
    since the enclosure contains it. So e <= 0 fails at every point of the box."""
    if not 0 <= body.which < len(goal.exprs):
        return Invalid(f"there is no expression {body.which}")
    lo = enclose(goal.exprs[body.which], box).lo
    return None if lo > 0 else TooWeak(f"expression {body.which} encloses down to {lo} at the point")


RULE = RuleSpec(
    id="R4",
    goal=AllNonpositive,
    proofs=(Enclosure,),
    refutations=(PointWitness,),
    tags=(
        ("all_nonpositive", AllNonpositive),
        ("enclosure", Enclosure),
        ("point_witness", PointWitness),
    ),
    lemmas=(),
    prove=prove,
    refute=refute,
)
