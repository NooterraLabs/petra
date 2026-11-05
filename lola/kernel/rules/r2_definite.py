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

from ..evaluate import Box
from ..evidence import Point, Vector
from ..terms import Expr, Matrix
from .base import Fault, RuleSpec


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


def prove(goal: GramPositiveDefinite, body: LDLFactor, box: Box) -> Fault | None:
    """TODO:
      require len(reference_weights) == len(terms); each factor has goal.dim rows
      require r_j <= enclose(w_j, box).lo for all j
      require is_unit_lower(L, dim) and len(d) == dim and all d_i > 0
      require ldl_product(L, d) == gram_sum(r, factors, dim)
    """
    raise NotImplementedError


def refute(goal: GramPositiveDefinite, body: NegativeDirection, box: Box) -> Fault | None:
    """TODO:
      require v != 0 and len(v) == dim
      w = [enclose(w_j, point_box(point))]
      require gram_quadratic(w, factors, v).hi <= 0
    """
    raise NotImplementedError


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
