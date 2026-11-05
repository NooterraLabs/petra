"""R2. Positive definiteness of a weighted Gram sum, by exact LDL^T.

Theorems used:
- Loewner order: V V^T >= 0, so w V V^T >= r V V^T whenever w >= r. Hence for every h,
  M(h) = sum_j w_j(h) V_j V_j^T  >=  M_ref = sum_j r_j V_j V_j^T  when r_j <= inf w_j.
- Sylvester's law of inertia: M_ref = L D L^T with L unit lower triangular has the
  inertia of D, so every d_i > 0 means M_ref > 0, hence M(h) > 0.

A load-factor range [0, lambda] enters as a hypothesis in the weights of the geometric
terms, so one certificate covers every factor below lambda. No pencil lemma is needed.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..evaluate import Box, enclose
from ..evidence import Point, Vector
from ..linalg import gram_quadratic, gram_sum, is_unit_lower, ldl_product
from ..terms import Expr, Matrix
from .base import Fault, Invalid, RuleSpec, TooWeak


@dataclass(frozen=True, slots=True)
class GramTerm:
    """weight * V V^T, where V is an n x r exact matrix, so V V^T is positive semidefinite
    by construction."""

    weight: Expr
    factor: Matrix


@dataclass(frozen=True, slots=True)
class GramPositiveDefinite:
    """Goal. For all h in the box, the n x n matrix  sum_j weight_j(h) V_j V_j^T  is positive definite."""

    dim: int
    terms: tuple[GramTerm, ...]


@dataclass(frozen=True, slots=True)
class LDLFactor:
    """Proof. reference_weights r_j <= enclosure(weight_j).lo, and
    L diag(d) L^T = sum_j r_j V_j V_j^T exactly, L unit lower triangular, every d_i > 0.
    Reference weights let a family certificate serve every sub-box (library reuse)."""

    reference_weights: Vector
    L: Matrix
    d: Vector


@dataclass(frozen=True, slots=True)
class NegativeDirection:
    """Refutation at `point`: v != 0 and v^T M(point) v <= 0."""

    point: Point
    v: Vector


def _shape(goal: GramPositiveDefinite) -> Fault | None:
    if goal.dim < 0 or any(t.factor.rows != goal.dim for t in goal.terms):
        return Invalid(f"every factor needs dim = {goal.dim} rows")
    return None


def prove(goal: GramPositiveDefinite, body: LDLFactor, box: Box) -> Fault | None:
    """Theorems: the Loewner order and Sylvester's law of inertia.

    The rule checks r_j <= enclose(w_j, box).lo, L unit lower triangular, every d_i > 0,
    and L diag(d) L^T = M_ref = sum_j r_j V_j V_j^T, all exactly. L^T is invertible, so
    for x != 0, x^T M_ref x = sum_i d_i (L^T x)_i^2 > 0: M_ref has the inertia of
    diag(d), all positive. For any h in the box w_j(h) >= r_j, since the enclosure
    contains w_j(h), so M(h) - M_ref = sum_j (w_j(h) - r_j) V_j V_j^T is a non-negative
    sum of positive semidefinite matrices. Hence x^T M(h) x >= x^T M_ref x > 0.

    Deliberately conservative: one reference matrix below every M(h) in the Loewner
    order must exist, and each weight is taken at its lower bound independently.
    """
    fault = _shape(goal)
    if fault is not None:
        return fault
    r = body.reference_weights
    if len(r) != len(goal.terms):
        return Invalid(f"{len(r)} reference weights for {len(goal.terms)} terms")
    for j, (rj, term) in enumerate(zip(r, goal.terms)):
        if rj > enclose(term.weight, box).lo:
            return Invalid(f"reference weight {j} is above the weight's lower bound")
    if not is_unit_lower(body.L, goal.dim) or len(body.d) != goal.dim:
        return Invalid("L must be unit lower triangular and d must have dim entries")
    if any(di <= 0 for di in body.d):
        return Invalid("a pivot of D is not positive")
    if ldl_product(body.L, body.d) != gram_sum(r, tuple(t.factor for t in goal.terms)):
        return Invalid("L D L^T differs from the reference Gram sum")
    return None


def refute(goal: GramPositiveDefinite, body: NegativeDirection, box: Box) -> Fault | None:
    """At every point p of the box, which fixes each RangeHyp at the evidence point and
    spans each DefinedHyp's proven range, v^T M(p) v = sum_j w_j(p) |V_j^T v|^2 is exact
    except for the weights, and each weight's enclosure over the box contains w_j(p). So
    the enclosure q contains v^T M(p) v at every p. If v != 0 and q.hi <= 0, then
    v^T M(p) v <= 0, so M(p) is not positive definite at any point of the box."""
    fault = _shape(goal)
    if fault is not None:
        return fault
    if len(body.v) != goal.dim or not any(body.v):
        return Invalid("v must be a nonzero vector with dim entries")
    q = gram_quadratic(tuple(enclose(t.weight, box) for t in goal.terms), tuple(t.factor for t in goal.terms), body.v)
    return None if q.hi <= 0 else TooWeak(f"v^T M v may be as large as {q.hi}")


RULE = RuleSpec(
    id="R2",
    goal=GramPositiveDefinite,
    proofs=(LDLFactor,),
    refutations=(NegativeDirection,),
    tags=(
        ("gram_term", GramTerm),
        ("gram_positive_definite", GramPositiveDefinite),
        ("ldl", LDLFactor),
        ("negative_direction", NegativeDirection),
    ),
    lemmas=(),
    prove=prove,
    refute=refute,
)
