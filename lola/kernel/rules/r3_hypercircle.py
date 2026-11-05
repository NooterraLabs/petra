"""R3. Hypercircle (Prager-Synge) bounds on a weighted least-norm minimiser.

Problem: s* = argmin { s^T W s : B s = f }, W = diag(w) > 0. KKT gives W s* = B^T u*.

Theorem used: for any s with B s = f and any u, put t = W^-1 B^T u. Then
<s - s*, s* - t>_W = (B s - B s*)^T (u* - u) = 0, so s* lies on the sphere with centre
c = (s + t)/2 and radius r = |s - t|_W / 2. Hence
    |s*_i - c_i| <= r / sqrt(w_i)        and        s*^T W s* <= s^T W s.
With interval weights the enclosure holds for every W in the box at once, and with f
affine in the vertex symbols, |scale * s*_i| and the energy are convex in f, so checking
every vertex covers the box.

R3 also registers the one v0 lemma: a range for MinimizerComponent, proved with the same
hypercircle fields. check.py finds it through rules.LEMMAS, never by name.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..evaluate import Box, at_vertices, enclose, free_syms, point_box
from ..evidence import DefinedRange, Point, Vector
from ..interval import Interval, Q, i_sqrt
from ..linalg import dot, matvec, rmatvec
from ..terms import Expr, Matrix
from .base import Fault, Invalid, Lemma, RuleSpec, TooWeak


@dataclass(frozen=True, slots=True)
class QuadraticProblem:
    """The weighted least-norm problem  s* = argmin { sum_i w_i s_i^2 : B s = f }.

    - B is m x n and exact.
    - f has m entries, each affine in RangeHyp symbols with rational coefficients.
    - w has n entries, each an Expr that must enclose to a strictly positive interval
      over the hypothesis box.
    The minimiser is unique when B s = f is solvable, because w > 0.
    """

    B: Matrix
    f: tuple[Expr, ...]
    w: tuple[Expr, ...]


@dataclass(frozen=True, slots=True)
class MinimizerComponent:
    """QuantityDef. The real quantity  scale * s*_index  of a QuadraticProblem. `scale` may
    depend on RangeHyp symbols."""

    problem: QuadraticProblem
    index: int
    scale: Expr


@dataclass(frozen=True, slots=True)
class ComponentBound:
    """lo <= scale * s*_index <= hi. Either side may be None."""

    index: int
    scale: Expr
    lo: Expr | None
    hi: Expr | None


@dataclass(frozen=True, slots=True)
class MinimizerBound:
    """Goal. For all h in the box, the minimiser s*(h) of `problem` satisfies every component
    bound, and  sum_i w_i s*_i^2 <= energy_hi  when energy_hi is not None."""

    problem: QuadraticProblem
    bounds: tuple[ComponentBound, ...]
    energy_hi: Expr | None


@dataclass(frozen=True, slots=True)
class HypercircleFields:
    """One statically admissible field s (B s = f exactly) and one displacement u per
    vertex of the problem's vertex box. The proof body of R3 and the lemma evidence for
    MinimizerComponent."""

    s: tuple[Vector, ...]
    u: tuple[Vector, ...]


@dataclass(frozen=True, slots=True)
class Hypercircle:
    """Proof."""

    fields: HypercircleFields


@dataclass(frozen=True, slots=True)
class HypercircleViolation:
    """Refutation at `point`: the hypercircle enclosure of bound `which` lies wholly
    outside the allowed range (or the energy lower bound exceeds energy_hi, which = -1)."""

    point: Point
    s: Vector
    u: Vector
    which: int


def _weights(problem: QuadraticProblem, box: Box) -> tuple[Interval, ...] | Fault:
    B = problem.B
    if len(problem.f) != B.rows or len(problem.w) != B.cols:
        return Invalid(f"B is {B.rows}x{B.cols} but f and w have {len(problem.f)} and {len(problem.w)} entries")
    w = tuple(enclose(wi, box) for wi in problem.w)
    if any(wi.lo <= 0 for wi in w):
        return Invalid("a weight is not strictly positive over the box")
    return w


def _sphere(B: Matrix, w: tuple[Interval, ...], f: Vector, s: Vector, u: Vector) -> tuple[tuple[Interval, ...], Interval] | Fault:
    """The hypercircle at one right-hand side f, valid for every weight vector in w.
    Returns the component enclosures and the enclosure of the energy s^T W s."""
    if len(s) != B.cols or len(u) != B.rows or matvec(B, s) != f:
        return Invalid("s is not statically admissible: B s != f")
    e = rmatvec(B, u)
    zero = Interval.point(Q(0))
    gap = sum((wi * Interval.point(si * si) - Interval.point(2 * si * ei) + Interval.point(ei * ei) / wi for si, ei, wi in zip(s, e, w)), zero)
    radius = i_sqrt(Interval(Q(0), gap.hi)).hi / 2
    comps = []
    for si, ei, wi in zip(s, e, w):
        centre = (Interval.point(si) + Interval.point(ei) / wi) * Interval.point(Q(1, 2))
        spread = radius / i_sqrt(wi).lo
        comps.append(Interval(centre.lo - spread, centre.hi + spread))
    return tuple(comps), sum((wi * Interval.point(si * si) for si, wi in zip(s, w)), zero)


def enclose_minimizer(problem: QuadraticProblem, fields: HypercircleFields, box: Box) -> tuple[tuple[Interval, ...], Interval] | Fault:
    """Enclosures of every component of s*(h), and of its energy, for all h in the box.

    Theorems: the Prager-Synge hypercircle identity, linearity of s* in f, and the
    primal minimum principle. Fix h and write W = W(h), which lies in the weight box w
    because every enclosure contains its value. At a vertex v the rule checks
    B s_v = f(v) exactly, so by the module identity s*(f(v), W) lies on the W-sphere with
    centre (s_v + t)/2 and radius |s_v - t|_W / 2, t = W^-1 B^T u_v. Hence
    |s*_i - centre_i| <= radius / sqrt(w_i), and `_sphere` bounds the centre, the radius
    (from the expanded square w s^2 - 2 s e + e^2 / w) and sqrt(w_i) over the whole weight
    box, so its interval holds for this W. The vertex symbols are the symbols of f,
    sorted; f is affine in them (at_vertices raises otherwise), so f(h) = sum_v theta_v
    f(v) with theta_v >= 0 summing to 1. The minimiser is characterised by the linear
    conditions B s = f and W s in range(B^T), so s*(f(h), W) = sum_v theta_v s*(f(v), W),
    which lies in the hull of the vertex intervals. The energy is a convex quadratic in f
    for fixed W, so it is at most its largest vertex value, and at a vertex
    s*^T W s* <= s_v^T W s_v because s_v is feasible and s* is the minimiser.

    Deliberately conservative: the weights range over their whole box at every vertex,
    and the bound is a hull over vertices.
    """
    w = _weights(problem, box)
    if isinstance(w, Fault):
        return w
    rhs = at_vertices(problem.f, tuple(sorted(free_syms(problem.f))), box)
    if not len(fields.s) == len(fields.u) == len(rhs):
        return Invalid(f"{len(fields.s)} fields s and {len(fields.u)} fields u for {len(rhs)} vertices")
    comps, energy = None, Q(0)
    for f, s, u in zip(rhs, fields.s, fields.u):
        sphere = _sphere(problem.B, w, f, s, u)
        if isinstance(sphere, Fault):
            return sphere
        comps = sphere[0] if comps is None else tuple(a.hull(b) for a, b in zip(comps, sphere[0]))
        energy = max(energy, sphere[1].hi)
    return comps, Interval(Q(0), energy)


def _scaled(comps: tuple[Interval, ...], index: int, scale: Expr, box: Box) -> Interval | Fault:
    """An enclosure of scale * s*_index, since both factors are enclosed."""
    if not 0 <= index < len(comps):
        return Invalid(f"there is no component {index}")
    return enclose(scale, box) * comps[index]


def prove(goal: MinimizerBound, body: Hypercircle, box: Box) -> Fault | None:
    """Theorem: the hypercircle enclosure (see enclose_minimizer), which contains
    scale(h) * s*_index(h) and the energy of s*(h) for every h in the box.

    Each component bound needs the enclosure q of scale * s*_index to satisfy
    q.lo >= sup lo and q.hi <= inf hi over the box, and the energy needs its upper end
    <= inf energy_hi. Then lo(h) <= q.lo <= scale(h) s*_index(h) <= q.hi <= hi(h) at
    every h, and likewise for the energy. Feasibility at every h follows because a
    convex combination of the admissible vertex fields is admissible.
    """
    found = enclose_minimizer(goal.problem, body.fields, box)
    if isinstance(found, Fault):
        return found
    comps, energy = found
    for k, bound in enumerate(goal.bounds):
        q = _scaled(comps, bound.index, bound.scale, box)
        if isinstance(q, Fault):
            return q
        if (bound.lo is not None and q.lo < enclose(bound.lo, box).hi) or (bound.hi is not None and q.hi > enclose(bound.hi, box).lo):
            return TooWeak(f"bound {k}: the hypercircle gives [{q.lo}, {q.hi}]")
    if goal.energy_hi is not None and energy.hi > enclose(goal.energy_hi, box).lo:
        return TooWeak(f"the energy may reach {energy.hi}")
    return None


def refute(goal: MinimizerBound, body: HypercircleViolation, box: Box) -> Fault | None:
    """At the point h, which check.py has placed in the box.

    The rule checks B s = f(h) exactly, so the problem is feasible and s*(h) exists.
    For which >= 0 the hypercircle at h encloses scale * s*_index in q, and a q wholly
    above sup hi(h) or wholly below inf lo(h), strictly, violates that bound. For
    which = -1 it uses the dual principle: for any u and any feasible s,
    0 <= |s - W^-1 B^T u|_W^2 = s^T W s - 2 f^T u + (B^T u)^T W^-1 (B^T u), so
    s*^T W s* >= 2 f^T u - (B^T u)^T W^-1 (B^T u). A lower end of that enclosure strictly
    above energy_hi(h) violates the energy bound.
    """
    at = point_box(body.point)
    w = _weights(goal.problem, at)
    if isinstance(w, Fault):
        return w
    f = at_vertices(goal.problem.f, tuple(sorted(free_syms(goal.problem.f))), at)[0]
    sphere = _sphere(goal.problem.B, w, f, body.s, body.u)
    if isinstance(sphere, Fault):
        return sphere
    if body.which == -1 and goal.energy_hi is not None:
        e = rmatvec(goal.problem.B, body.u)
        dual = Interval.point(2 * dot(f, body.u)) - sum((Interval.point(ei * ei) / wi for ei, wi in zip(e, w)), Interval.point(Q(0)))
        cap = enclose(goal.energy_hi, at).hi
        return None if dual.lo > cap else TooWeak(f"the dual energy bound {dual.lo} does not exceed {cap}")
    if not 0 <= body.which < len(goal.bounds):
        return Invalid(f"there is no bound {body.which}")
    bound = goal.bounds[body.which]
    q = _scaled(sphere[0], bound.index, bound.scale, at)
    if isinstance(q, Fault):
        return q
    if (bound.hi is not None and q.lo > enclose(bound.hi, at).hi) or (bound.lo is not None and q.hi < enclose(bound.lo, at).lo):
        return None
    return TooWeak(f"bound {body.which}: the hypercircle gives [{q.lo}, {q.hi}], which meets the allowed range")


def prove_defined(definition: MinimizerComponent, claim: DefinedRange, box: Box) -> Fault | None:
    """Prove claim.lo <= scale * s*_index <= claim.hi over the RangeHyp box, with
    claim.proof (HypercircleFields) through enclose_minimizer.

    Same theorem as `prove`: the enclosure q contains scale(h) * s*_index(h) for every h,
    so q inside [claim.lo, claim.hi] proves the range at every h.
    """
    found = enclose_minimizer(definition.problem, claim.proof, box)
    if isinstance(found, Fault):
        return found
    q = _scaled(found[0], definition.index, definition.scale, box)
    if isinstance(q, Fault):
        return q
    return None if claim.lo <= q.lo and q.hi <= claim.hi else TooWeak(f"{claim.sym}: the hypercircle gives [{q.lo}, {q.hi}]")


RULE = RuleSpec(
    id="R3",
    goal=MinimizerBound,
    proofs=(Hypercircle,),
    refutations=(HypercircleViolation,),
    tags=(
        ("quadratic_problem", QuadraticProblem),
        ("minimizer_component", MinimizerComponent),
        ("component_bound", ComponentBound),
        ("minimizer_bound", MinimizerBound),
        ("hypercircle_fields", HypercircleFields),
        ("hypercircle", Hypercircle),
        ("hypercircle_violation", HypercircleViolation),
    ),
    lemmas=(Lemma(defines=MinimizerComponent, evidence=HypercircleFields, prove=prove_defined),),
    prove=prove,
    refute=refute,
)
