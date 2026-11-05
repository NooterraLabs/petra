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

from ..evaluate import Box
from ..evidence import DefinedRange, Point, Vector
from ..interval import Interval
from ..terms import Expr, Matrix
from .base import Fault, Lemma, RuleSpec


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


def enclose_minimizer(problem: QuadraticProblem, fields: HypercircleFields, box: Box) -> tuple[tuple[Interval, ...], Interval] | Fault:
    """Per-vertex hypercircle enclosure, hulled over vertices. Returns (component
    enclosures, energy upper enclosure) or a fault.

    TODO:
      vsyms = sorted RangeHyp syms in problem.f; verts = vertices(box, vsyms)
      require len(fields.s) == len(fields.u) == len(verts)
      w = [enclose(w_i, box)]; require every w_i.lo > 0
      for each vertex v with (s, u):
          require matvec(B, s) == f(v) exactly                    Invalid otherwise
          e = rmatvec(B, u)                         # exact
          t_i = Interval.point(e_i) / w_i
          r2 = sum_i w_i * (s_i - t_i)^2            # interval, using the expanded form
                                                    #   w s^2 - 2 s e + e^2 / w
          r = i_sqrt(r2.hull(0)) / 2
          comp_i = (s_i + t_i)/2 +- r / i_sqrt(w_i)
          energy = sum_i w_i * s_i^2
      return hull over vertices of comp_i, and max over vertices of energy.hi
    """
    raise NotImplementedError


def prove(goal: MinimizerBound, body: Hypercircle, box: Box) -> Fault | None:
    """TODO: comps, energy = enclose_minimizer(...)
      for each ComponentBound: q = enclose(scale, box) * comps[index]
          require q.lo >= enclose(lo, box).hi and q.hi <= enclose(hi, box).lo   TooWeak otherwise
      if energy_hi: require energy.hi <= enclose(energy_hi, box).lo           TooWeak otherwise
    """
    raise NotImplementedError


def refute(goal: MinimizerBound, body: HypercircleViolation, box: Box) -> Fault | None:
    """At a single point: the enclosure of bound `which` lies wholly outside its allowed
    range, or (which == -1) the energy lower bound 2 f.u - u^T K u exceeds energy_hi.

    TODO: lower energy bound uses the dual principle: for any u,
      s*^T W s* >= 2 f^T u - (B^T u)^T W^-1 (B^T u).
    """
    raise NotImplementedError


def prove_defined(definition: MinimizerComponent, claim: DefinedRange, box: Box) -> Fault | None:
    """Prove claim.lo <= scale * s*_index <= claim.hi over the RangeHyp box, with
    claim.proof (HypercircleFields) through enclose_minimizer."""
    raise NotImplementedError


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
