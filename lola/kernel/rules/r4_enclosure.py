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

from ..evaluate import Box
from ..evidence import Partition, Point
from ..terms import Expr
from .base import Fault, RuleSpec


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
    """Refutation: expr `which` encloses strictly above 0 at `point`."""

    point: Point
    which: int


def leaves(partition: Partition, box: Box) -> tuple[dict, ...] | Fault:
    """Cells of the partition, or Invalid (unknown sym, split point not strictly inside
    the cell, depth over MAX_DEPTH).

    TODO: iterative walk with an explicit stack; MAX_DEPTH = 64 guards recursion and
      evidence size, not soundness.
    """
    raise NotImplementedError


def all_nonpositive_on(exprs: tuple[Expr, ...], partition: Partition, box: Box) -> Fault | None:
    """Shared by R4 and R5: walk the leaves, require enclose(e, cell).hi <= 0 (TooWeak
    names the first leaf that fails)."""
    raise NotImplementedError


def prove(goal: AllNonpositive, body: Enclosure, box: Box) -> Fault | None:
    raise NotImplementedError


def refute(goal: AllNonpositive, body: PointWitness, box: Box) -> Fault | None:
    """require enclose(exprs[which], point_box(point)).lo > 0."""
    raise NotImplementedError


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
