"""R1. Linear feasibility for every load in a box, and its Farkas refutation.

Theorem used (convexity): if b is affine in the vertex symbols and x_v is feasible at
every vertex v, then for any h the convex combination sum theta_v(h) x_v is feasible at
b(h), because the bound box (evaluated over the whole hypothesis box) does not move.

Theorem used (Farkas): if y^T b > sum_i max_{l_i <= x_i <= u_i} (A^T y)_i x_i then no x
satisfies A x = b within the bounds.

The rule knows nothing about trusses. The truss elaborator maps "static field below
capacity at load factor lambda" onto this goal; the mechanism FAIL is a Farkas ray.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..evaluate import Box
from ..evidence import Point, Vector
from ..terms import Expr, Matrix
from .base import Fault, RuleSpec


@dataclass(frozen=True, slots=True)
class LinearFeasible:
    """Goal. For all h in the box there is x with  A x = b(h)  and  lower_i(h) <= x_i <= upper_i(h).

    b must be affine in the RangeHyp symbols it mentions ("vertex symbols"). Bounds may
    mention any hypothesis and are evaluated over the whole box. None means unbounded.
    """

    A: Matrix
    b: tuple[Expr, ...]
    lower: tuple[Expr | None, ...]
    upper: tuple[Expr | None, ...]


@dataclass(frozen=True, slots=True)
class FeasiblePoints:
    """Proof. One x per vertex, in the kernel's vertex order (see evidence.py)."""

    x: tuple[Vector, ...]


@dataclass(frozen=True, slots=True)
class FarkasRay:
    """Refutation at `point`: y^T b(point) > sum_i max_{x_i in bounds} (A^T y)_i x_i."""

    point: Point
    y: Vector


def prove(goal: LinearFeasible, body: FeasiblePoints, box: Box) -> Fault | None:
    """TODO:
      vsyms = sorted RangeHyp syms occurring in goal.b
      coeffs = [affine_coefficients(b_i, vsyms) for b_i in goal.b]
      verts = vertices(box, vsyms); require len(body.x) == len(verts)
      lo_i = enclose(lower_i, box).hi  ;  hi_i = enclose(upper_i, box).lo   (conservative)
      for v, x in zip(verts, body.x):
          require len(x) == A.cols
          require matvec(A, x) == b(v) exactly                    Invalid otherwise
          require lo_i <= x_i <= hi_i for every bounded i          Invalid otherwise
    """
    raise NotImplementedError


def refute(goal: LinearFeasible, body: FarkasRay, box: Box) -> Fault | None:
    """TODO:
      pbox = point_box(body.point); b = [enclose(b_i, pbox)] must all be points
      z = rmatvec(A, y)
      cap = sum over i of: z_i > 0 -> z_i * enclose(upper_i, pbox).hi (None -> Invalid)
                           z_i < 0 -> z_i * enclose(lower_i, pbox).lo (None -> Invalid)
      require dot(y, b) > cap   (strict; TooWeak when the ray is valid but the gap closes)
    """
    raise NotImplementedError


RULE = RuleSpec(
    id="R1",
    goal=LinearFeasible,
    proofs=(FeasiblePoints,),
    refutations=(FarkasRay,),
    tags=(
        ("linear_feasible", LinearFeasible),
        ("feasible_points", FeasiblePoints),
        ("farkas_ray", FarkasRay),
    ),
    lemmas=(),
    prove=prove,
    refute=refute,
)
