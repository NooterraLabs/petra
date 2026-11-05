"""R5 solver. Untrusted.

Solves the range-and-mean form the uncertainty elaborator builds: one random variable x
on the support [a, b], one moment E[x] in [L, H], and a failure margin. Any other
MomentBound gets no evidence.

1. Find t, the largest load up to which the kernel's own enclosure shows fail <= 0 for
   every hypothesis value, by exact bisection.
2. The dual is closed form. For a < c <= t, g(x) = (x - a) / (c - a) is >= 0 on the
   support and >= 1 wherever fail > 0, and E[g] <= (H - a) / (c - a). At c = t this is
   the Markov-type bound. A two-point law at a and just above the threshold attains it,
   so when t is the threshold no dual does better. The solver takes the smallest c whose
   bound is exactly p. That leaves the widest band [c, t] in which g >= 1 and fail <= 0
   both hold, so a finite partition exists.
3. Build that partition with r4_enclosure.search on the R4 goal the kernel walks,
   min(1 - g, max(-g, fail)) <= 0 over the box and the support.

Offers nothing when no c fits below t, which is when p is at or below the Markov-type
bound: the range and mean do not support a tighter claim, and no partition changes that.
"""
from __future__ import annotations

from typing import Iterable

from ..kernel import Add, Const, Evidence, Expr, Interval, Leaf, Max, Min, Mul, Neg, Q, RangeHyp, Split, Statement, Sym, Vector, enclose
from ..kernel.rules.r5_moment import MomentBound, MomentDual
from .r4_enclosure import search

_BISECTIONS = 60
"""t to within 2^-60 of the support width, far below any margin a claim turns on."""


def solve(statement: Statement, max_cells: int = 20000) -> Iterable[Evidence]:
    goal = statement.goal
    if not isinstance(goal, MomentBound) or len(goal.random) != 1 or len(goal.moments) != 1:
        return ()
    (x,), (moment,) = goal.random, goal.moments
    if moment.fn != Sym(x.sym):
        return ()
    box = {h.sym: Interval(h.lo, h.hi) for h in statement.hyps if isinstance(h, RangeHyp)}
    try:
        support = Interval(enclose(x.lo, box).lo, enclose(x.hi, box).hi)
        mean_hi = enclose(moment.hi, box).hi
    except (ArithmeticError, ValueError):
        return ()
    dual = _markov_dual(goal.fail, x.sym, support, mean_hi, goal.p, box)
    if dual is None:
        return ()
    y0, y = dual
    partition = search((_dominated(goal, y0, y),), {**box, x.sym: support}, max_cells)
    if not isinstance(partition, (Leaf, Split)):
        return ()
    return (Evidence(MomentDual(y0, y, partition)),)


def _markov_dual(fail: Expr, sym: str, support: Interval, mean_hi: Q, p: Q, box: dict) -> tuple[Q, Vector] | None:
    """(y0, (y1,)) for g(x) = y0 + y1 x with E[g] <= p (module docstring, step 2).

    g = 0 when fail <= 0 on the whole support. When the mean sits at a, all mass is at a
    and every c in (a, t) gives E[g] = 0, so c is the middle of that range."""
    a = support.lo
    t = _safe_up_to(fail, sym, support, box)
    if t is None:
        return None
    if t == support.hi:
        return Q(0), (Q(0),)
    if mean_hi > a and p > 0:
        c = a + (mean_hi - a) / p
    elif mean_hi == a:
        c = (a + t) / 2
    else:
        return None
    if not a < c < t:
        return None
    y1 = 1 / (c - a)
    return -a * y1, (y1,)


def _safe_up_to(fail: Expr, sym: str, support: Interval, box: dict) -> Q | None:
    """The largest t found such that the kernel encloses fail <= 0 over [support.lo, t]
    for every hypothesis value, or None when it cannot show that even at x = support.lo."""

    def safe(t: Q) -> bool:
        try:
            return enclose(fail, {**box, sym: Interval(support.lo, t)}).hi <= 0
        except (ArithmeticError, ValueError):
            return False

    if safe(support.hi):
        return support.hi
    if not safe(support.lo):
        return None
    lo, hi = support.lo, support.hi
    for _ in range(_BISECTIONS):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if safe(mid) else (lo, mid)
    return lo


def _dominated(goal: MomentBound, y0: Q, y: Vector) -> Expr:
    """The expression kernel.rules.r5_moment.prove walks, built the same way, so every
    leaf search accepts is a leaf the kernel accepts."""
    g = Add((Const(y0),) + tuple(Mul((Const(yj), m.fn)) for yj, m in zip(y, goal.moments)))
    return Min((Add((Const(Q(1)), Neg(g))), Max((Neg(g), goal.fail))))
