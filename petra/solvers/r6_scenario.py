"""R6 solver. The kernel computes the tail itself, so the only evidence is Arithmetic().
The solver still computes the tail in floats first and offers nothing when it clearly
exceeds beta, so a false claim reports UNKNOWN with a reason instead of a rejection."""
from __future__ import annotations

import math
from typing import Iterable

from ..kernel import Evidence, Interval, RangeHyp, Statement, enclose
from ..kernel.rules.r6_scenario import Arithmetic, BinomialTail

_SLACK = 1e-9
"""Relative float error the tail may carry before a claim counts as clearly unsupported.
Inside it the kernel's exact tail decides."""


def solve(statement: Statement) -> Iterable[Evidence]:
    goal = statement.goal
    if not isinstance(goal, BinomialTail):
        return ()
    box = {h.sym: Interval(h.lo, h.hi) for h in statement.hyps if isinstance(h, RangeHyp)}
    return () if _clearly_exceeds(goal, box) else (Evidence(Arithmetic()),)


def _clearly_exceeds(goal: BinomialTail, box: dict) -> bool:
    """False whenever the numbers are not in the form the kernel checks, so the kernel,
    not the solver, names what is wrong with them."""
    try:
        values = [enclose(e, box) for e in (goal.n, goal.k, goal.eps, goal.beta)]
    except (ArithmeticError, ValueError):
        return False
    if any(v.lo != v.hi for v in values):
        return False
    n, k, eps, beta = (v.lo for v in values)
    if not (n.denominator == k.denominator == 1 and 0 <= k <= n and 0 < eps < 1):
        return False
    return _float_tail(int(n), int(k), float(eps)) > float(beta) * (1 + _SLACK)


def _float_tail(n: int, k: int, eps: float) -> float:
    """sum_{i<=k} C(n, i) eps^i (1 - eps)^(n - i), each term through logs so that a large
    n neither overflows the binomial coefficient nor underflows the power."""
    log_eps, log_rest = math.log(eps), math.log1p(-eps)
    log_n = math.lgamma(n + 1)
    return math.fsum(
        math.exp(log_n - math.lgamma(i + 1) - math.lgamma(n - i + 1) + i * log_eps + (n - i) * log_rest)
        for i in range(k + 1)
    )
