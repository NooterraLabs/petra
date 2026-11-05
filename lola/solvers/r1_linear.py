"""R1 solver: scipy.optimize.linprog (HiGHS) per vertex, then exact repair. Untrusted.

Proof: for each vertex, maximise the minimum slack to the bounds (a Chebyshev-style LP)
so the rounded point stays strictly inside, then project onto A x = b exactly.
Refutation: if any vertex LP is infeasible, read the dual ray (HiGHS marginals of the
infeasibility certificate), rationalise it as y, and evaluate the Farkas inequality
exactly before offering it. In truss terms y is a collapse mechanism.
"""
from __future__ import annotations

from typing import Iterable

from ..kernel import Evidence, Statement


def solve(statement: Statement) -> Iterable[Evidence]:
    raise NotImplementedError


def farkas_ray(statement: Statement, vertex: dict) -> Evidence | None:
    raise NotImplementedError
