"""R4 solver: branch and bound over the hypothesis box. Untrusted, but it evaluates with
kernel.enclose so that every leaf it reports is a leaf the kernel will accept.

Loop (best-first on the largest upper enclosure):
  cell passes if every expr encloses <= 0 -> leaf
  cell fails at its centre point or its leaning corner (point enclosure > 0)
    -> PointWitness, stop
  otherwise split the symbol whose halves lower the worst upper enclosure most
  (measured by enclosing on both halves), at the midpoint rounded to a short dyadic so
  leaf boundaries stay cheap to encode.
Gives up after max_cells and returns nothing (the obligation becomes UNKNOWN).

A violating point is moved to the worst corner it can reach by coordinate ascent, so a
refutation names the worst-case input rather than the first failing one.

A statement with DefinedHyps reaches `solve` with each one replaced by a RangeHyp over
its proposed range (see SolverSource). A proof there proves the original, but a
violating point does not refute it: the defined symbol need not take its true value
there. So when no proof is found, the same ascent searches the original statement's
RangeHyp box, scoring each point with the R3 lemma ranges proved at it, which is how the
kernel checks the refutation.

Also used by r5_moment.py for R5 domination trees and by library/transport.py to re-split
the part of a query box that a family partition does not cover.
"""
from __future__ import annotations

import heapq
from fractions import Fraction
from typing import Callable, Iterable

from ..kernel import (
    DefinedHyp,
    Evidence,
    Expr,
    Interval,
    Leaf,
    Partition,
    RangeHyp,
    Split,
    Statement,
    enclose,
)
from ..kernel.rules.r4_enclosure import MAX_DEPTH, AllNonpositive, Enclosure, PointWitness
from .r3_hypercircle import defined_ranges

_STATS: dict[str, int] = {"cells": 0, "enclosures": 0, "max_depth": 0}


def solve(statement: Statement, max_cells: int = 20000, original: Statement | None = None) -> Iterable[Evidence]:
    """Proof or refutation evidence for an AllNonpositive statement, or nothing.

    Nothing for a statement with a DefinedHyp, whose range only a lemma proves.
    SolverSource passes `statement` with each DefinedHyp replaced by a RangeHyp over its
    proposed range, and the statement as written as `original`. When no proof is found
    and `original` has a DefinedHyp, the only candidate is a witness for `original`,
    without DefinedRanges: SolverSource attaches the ones proved at its point."""
    if not isinstance(statement.goal, AllNonpositive) or any(isinstance(h, DefinedHyp) for h in statement.hyps):
        return ()
    box = {h.sym: Interval(h.lo, h.hi) for h in statement.hyps if isinstance(h, RangeHyp)}
    found = search(statement.goal.exprs, box, max_cells)
    if isinstance(found, (Leaf, Split)):
        return (Evidence(Enclosure(found)),)
    if original is not None and any(isinstance(h, DefinedHyp) for h in original.hyps):
        point = _witness(original)
        return () if point is None else (point,)
    if isinstance(found, dict):
        which = next(k for k, e in enumerate(statement.goal.exprs) if _violates(e, found))
        return (Evidence(PointWitness(tuple((sym, found[sym]) for sym in box), which)),)
    return ()


def search(exprs: tuple[Expr, ...], box: dict, max_cells: int) -> Partition | dict | None:
    """Partition on success, a violating point (dict) on refutation, None on give-up."""
    _STATS.update(cells=0, enclosures=0, max_depth=0)
    widths = {sym: iv.width() for sym, iv in box.items()}
    splits: dict[int, tuple[str, Fraction, int, int]] = {}
    queue: list = []

    def push(cell: dict, depth: int) -> int:
        node = _STATS["cells"]
        _STATS["cells"] += 1
        _STATS["max_depth"] = max(_STATS["max_depth"], depth)
        uppers = tuple(_upper(e, cell) for e in exprs)
        heapq.heappush(queue, (_priority(uppers), node, cell, depth, uppers))
        return node

    push(dict(box), 0)
    while queue:
        _, node, cell, depth, uppers = heapq.heappop(queue)
        if all(u is not None and u <= 0 for u in uppers):
            break
        centre = {sym: _cut(iv) for sym, iv in cell.items()}
        if any(_violates(e, centre) for e in exprs):
            return _worst(lambda point: _score(exprs, point), box, centre)
        choice = _split_choice(exprs, cell, uppers, widths)
        if choice is None:
            return None
        sym, at, lean = choice
        if any(_violates(e, lean) for e in exprs):
            return _worst(lambda point: _score(exprs, point), box, lean)
        if _STATS["cells"] + 2 > max_cells or depth >= MAX_DEPTH:
            return None
        left = push({**cell, sym: Interval(cell[sym].lo, at)}, depth + 1)
        right = push({**cell, sym: Interval(at, cell[sym].hi)}, depth + 1)
        splits[node] = (sym, at, left, right)
    return _tree(0, splits)


def search_stats() -> dict:
    """Counters from the last search: cells visited, enclosures evaluated, max depth.
    The family benchmark reports these to explain its timing."""
    return dict(_STATS)


def _violates(expr: Expr, point: dict) -> bool:
    lo = _point_lo(expr, point)
    return lo is not None and lo > 0


def _tree(node: int, splits: dict[int, tuple[str, Fraction, int, int]]) -> Partition:
    if node not in splits:
        return Leaf()
    sym, at, left, right = splits[node]
    return Split(sym, at, _tree(left, splits), _tree(right, splits))


def _upper(expr: Expr, cell: dict) -> Fraction | None:
    """The kernel's upper enclosure, or None where the expression is undefined on part of
    the cell (a division by an interval holding 0, a square root of a negative)."""
    _STATS["enclosures"] += 1
    try:
        return enclose(expr, cell).hi
    except (ArithmeticError, ValueError):
        return None


def _point_lo(expr: Expr, point: dict) -> Fraction | None:
    return _lower(expr, {sym: Interval(v, v) for sym, v in point.items()})


def _lower(expr: Expr, box: dict) -> Fraction | None:
    """The kernel's lower enclosure, or None where the expression is undefined on the box."""
    _STATS["enclosures"] += 1
    try:
        return enclose(expr, box).lo
    except (ArithmeticError, ValueError):
        return None


def _score(exprs: tuple[Expr, ...], point: dict) -> Fraction | None:
    """The largest lower enclosure at a point: positive exactly when the kernel's
    refutation check passes for some expression there."""
    lows = [lo for lo in (_point_lo(e, point) for e in exprs) if lo is not None]
    return max(lows) if lows else None


def _priority(uppers: tuple[Fraction | None, ...]) -> tuple:
    """Undefined cells first, then the largest upper enclosure. Exact, so the first cell
    that passes proves that every cell still queued passes."""
    if any(u is None for u in uppers):
        return (0, Fraction(0))
    return (1, -max(uppers, default=Fraction(0)))


def _split_choice(exprs, cell: dict, uppers, widths: dict) -> tuple[str, Fraction, dict] | None:
    """The split that lowers the cell's worst upper enclosure most, measured on both
    halves; ties go to the symbol with the most width left relative to the root box.

    Also the cell's leaning corner: each symbol at the end of its worse half, or at the
    cut where the halves tie. A symbol whose enclosure is already tight never wins the
    split, so without this probe a false goal could exhaust the budget on the other
    symbols before a centre ever reached the violating corner."""
    failing = [e for e, u in zip(exprs, uppers) if u is None or u > 0]
    worst = _float_worst(uppers)
    best, lean = None, {}
    for sym, iv in cell.items():
        if iv.lo == iv.hi:
            lean[sym] = iv.lo
            continue
        at = _cut(iv)
        halves = ({**cell, sym: Interval(iv.lo, at)}, {**cell, sym: Interval(at, iv.hi)})
        left, right = (_float_worst(tuple(_upper(e, h) for e in failing)) for h in halves)
        lean[sym] = iv.lo if left > right else iv.hi if right > left else at
        after = max(left, right)
        gain = 0.0 if after == float("inf") else worst - after
        key = (gain, float(iv.width() / widths[sym]))
        if best is None or key > best[0]:
            best = (key, sym, at)
    return None if best is None else (best[1], best[2], lean)


def _float_worst(uppers) -> float:
    if any(u is None for u in uppers):
        return float("inf")
    try:
        return float(max(uppers, default=Fraction(0)))
    except OverflowError:
        return float("inf")


def _cut(iv: Interval) -> Fraction:
    """A short dyadic near the midpoint, strictly inside a non-degenerate interval: the
    midpoint rounded to a step of at most a quarter of the width."""
    if iv.lo == iv.hi:
        return iv.lo
    quarter, step = iv.width() / 4, Fraction(1)
    while step > quarter:
        step /= 2
    while step * 2 <= quarter:
        step *= 2
    return round(iv.midpoint() / step) * step


def _worst(score: Callable[[dict], Fraction | None], box: dict, start: dict) -> dict:
    """Coordinate ascent over the box's faces from `start`. Each move strictly raises the
    score (any score beats an undefined one), so the loop ends, and a violating start
    stays violating."""
    best, best_score = dict(start), score(start)
    improved = True
    while improved:
        improved = False
        for sym, iv in box.items():
            for value in (iv.lo, iv.hi):
                if value == best[sym]:
                    continue
                candidate = {**best, sym: value}
                found = score(candidate)
                if found is not None and (best_score is None or found > best_score):
                    best, best_score, improved = candidate, found, True
    return best


def _witness(statement: Statement) -> Evidence | None:
    """A PointWitness for an AllNonpositive statement with DefinedHyps, or None.

    The kernel checks it at a point h0 of the RangeHyp box with each defined symbol over
    the range its lemma proves at h0, so a candidate scores the largest lower enclosure
    over h0 and the R3 lemma ranges at h0, and a point whose lemma fails scores nothing.
    The ascent starts from the box's centre; its end is a witness when the score there is
    positive."""
    box = {h.sym: Interval(h.lo, h.hi) for h in statement.hyps if isinstance(h, RangeHyp)}

    def lows(point: dict) -> list[Fraction | None]:
        at = {sym: Interval(v, v) for sym, v in point.items()}
        try:
            ranges = defined_ranges(statement, at)
        except (ArithmeticError, ValueError):
            return []
        cell = {**at, **{r.sym: Interval(r.lo, r.hi) for r in ranges}}
        return [_lower(e, cell) for e in statement.goal.exprs]

    def score(point: dict) -> Fraction | None:
        found = [lo for lo in lows(point) if lo is not None]
        return max(found) if found else None

    point = _worst(score, box, {sym: _cut(iv) for sym, iv in box.items()})
    which = next((k for k, lo in enumerate(lows(point)) if lo is not None and lo > 0), None)
    return None if which is None else Evidence(PointWitness(tuple(point.items()), which))
