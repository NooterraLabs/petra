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

from ..evaluate import Box, at_vertices, enclose, free_syms, point_box
from ..evidence import Point, Vector
from ..interval import Interval, Q
from ..linalg import matvec, rmatvec
from ..terms import Expr, Matrix
from .base import Fault, Invalid, RuleSpec, TooWeak


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


def _shape(goal: LinearFeasible) -> Fault | None:
    A = goal.A
    if len(goal.b) != A.rows or len(goal.lower) != A.cols or len(goal.upper) != A.cols:
        return Invalid(f"A is {A.rows}x{A.cols} but b, lower and upper have {len(goal.b)}, {len(goal.lower)} and {len(goal.upper)} entries")
    return None


def prove(goal: LinearFeasible, body: FeasiblePoints, box: Box) -> Fault | None:
    """Theorem: convexity of the feasible set in the right-hand side.

    The vertex symbols are the symbols of b, sorted. affine_coefficients writes b as
    b(h) = c + C h_V identically, where h_V is h restricted to the vertex symbols, so
    b(v) is exact at each vertex v. The rule checks, exactly, A x_v = b(v) and
    lo_i <= x_v,i <= hi_i at every vertex, where lo_i = sup of lower_i over the box and
    hi_i = inf of upper_i over the box (the far ends of their enclosures).

    Take any h in the box. h_V lies in the box spanned by the vertices, so
    h_V = sum_v theta_v v with theta_v >= 0 summing to 1 (products of one-dimensional
    barycentric weights). Put x = sum_v theta_v x_v. Then
    A x = sum_v theta_v b(v) = b(h), because b is affine and depends on h only through
    h_V. Each x_i is a convex combination of numbers in [lo_i, hi_i], so it lies there
    too, and lower_i(h) <= lo_i and hi_i <= upper_i(h) because an enclosure contains
    each value. So x is feasible at h.

    Deliberately conservative: bounds are taken at their worst over the whole box, not
    at each h, so a true goal whose bounds move with h can be unprovable here.
    """
    fault = _shape(goal)
    if fault is not None:
        return fault
    syms = tuple(sorted(free_syms(goal.b)))
    if len(body.x) != 1 << len(syms):
        return Invalid(f"{len(body.x)} points for the {1 << len(syms)} vertices over {syms}")
    lows = [None if e is None else enclose(e, box).hi for e in goal.lower]
    highs = [None if e is None else enclose(e, box).lo for e in goal.upper]
    for k, (b, x) in enumerate(zip(at_vertices(goal.b, syms, box), body.x)):
        if len(x) != goal.A.cols or matvec(goal.A, x) != b:
            return Invalid(f"A x != b at vertex {k}")
        for i, (lo, xi, hi) in enumerate(zip(lows, x, highs)):
            if (lo is not None and xi < lo) or (hi is not None and xi > hi):
                return Invalid(f"x_{i} = {xi} leaves its bounds [{lo}, {hi}] at vertex {k}")
    return None


def refute(goal: LinearFeasible, body: FarkasRay, box: Box) -> Fault | None:
    """Theorem: Farkas' lemma, the easy direction, at the point h.

    Let z = A^T y. For any x within the bounds at h, z^T x <= cap, where cap sums
    z_i * upper_i(h) over z_i > 0 and z_i * lower_i(h) over z_i < 0; the rule bounds each
    term above with the enclosure at h, and a missing bound where z_i != 0 makes the
    ray Invalid. If some x had A x = b(h) it would give y^T b(h) = z^T x <= cap. So
    y^T b(h) > cap, checked with the lower end of y^T b's enclosure, leaves no feasible
    x at h. The inequality is strict. b need not be affine here.
    """
    fault = _shape(goal)
    if fault is not None:
        return fault
    if len(body.y) != goal.A.rows:
        return Invalid(f"y has {len(body.y)} entries for {goal.A.rows} rows")
    at = point_box(body.point)
    cap = Q(0)
    for zi, lo, hi in zip(rmatvec(goal.A, body.y), goal.lower, goal.upper):
        if zi != 0:
            side = hi if zi > 0 else lo
            if side is None:
                return Invalid("the ray pushes along an unbounded variable")
            cap += (Interval.point(zi) * enclose(side, at)).hi
    yb = sum((Interval.point(yi) * enclose(bi, at) for yi, bi in zip(body.y, goal.b)), Interval.point(Q(0)))
    return None if yb.lo > cap else TooWeak(f"y^T b >= {yb.lo} does not exceed the cap {cap}")


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
