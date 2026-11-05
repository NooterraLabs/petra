"""R5 solver. Untrusted.

1. Sample the fail region on a grid over (support x hyp box) to find the smallest
   failing load x_c(h) (for monotone margins this is one threshold).
2. Solve the dual LP (scipy.optimize.linprog): minimise y0 + sum_j y_j m_j subject to
   g(x_k) >= 1 at sampled failing points and g(x_k) >= 0 at all sampled points.
   For range [a, b] and mean m with one threshold c this recovers the Markov-type bound
   (m - a) / (c - a).
3. Round y down/up by sign so the bound stays <= p, then build the domination partition
   with r4_enclosure.search over the two-branch condition.
"""
from __future__ import annotations

from typing import Iterable

from ..kernel import Evidence, Statement


def solve(statement: Statement) -> Iterable[Evidence]:
    raise NotImplementedError
